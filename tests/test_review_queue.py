"""要確認キューのテスト。

「AI 由来または高リスクだけを人が見る」判定と、その API を検証する。
自動承認が高リスク項目を勝手に通さないことを重点的に確認する。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from autorun.review_queue import (  # noqa: E402
    CONFIDENCE_ASSUMED,
    CONFIDENCE_LLM,
    CONFIDENCE_MEASURED,
    CONFIDENCE_USER,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    build_review_queue,
    confidence_of,
    needs_review,
    page_urls_from_report,
    risk_of,
    summarize,
)
from autorun.stages import Pipeline, StageItem  # noqa: E402


def _item(**kwargs) -> StageItem:
    base = {"item_id": "i1", "title": "検索を空文字で送信", "detail": "必須メッセージ"}
    base.update(kwargs)
    return StageItem(**base)


class TestConfidence:
    def test_rule_is_measured(self) -> None:
        assert confidence_of(_item(source="rule")) == CONFIDENCE_MEASURED

    def test_llm_is_llm(self) -> None:
        assert confidence_of(_item(source="llm")) == CONFIDENCE_LLM

    def test_user_edited_is_user(self) -> None:
        assert confidence_of(_item(source="user")) == CONFIDENCE_USER

    def test_assumed_beats_source(self) -> None:
        """前提は最も弱い根拠。source が rule でも前提が優先される。"""
        assert confidence_of(_item(source="rule", assumed=True)) == CONFIDENCE_ASSUMED


class TestRisk:
    def test_payment_wording_is_high(self) -> None:
        assert risk_of(_item(title="決済フォームの送信")) == RISK_HIGH

    def test_login_wording_is_high(self) -> None:
        assert risk_of(_item(title="ログイン後の遷移", detail="")) == RISK_HIGH

    def test_cart_wording_is_medium(self) -> None:
        assert risk_of(_item(title="カートの数量変更")) == RISK_MEDIUM

    def test_plain_wording_is_low(self) -> None:
        assert risk_of(_item(title="見出しの表示", detail="h1 が1つ")) == RISK_LOW

    def test_risk_from_page_url(self) -> None:
        """題名が無害でも、紐づく画面が決済なら高リスクにする。"""
        item = _item(title="入力欄の確認", data={"page_id": "P005"})
        assert risk_of(item, {"P005": "https://example.com/checkout"}) == RISK_HIGH

    def test_risk_from_screen_ids(self) -> None:
        item = _item(title="項目の確認", data={"screen_ids": ["P001", "P009"]})
        assert risk_of(item, {"P009": "https://example.com/admin/users"}) == RISK_HIGH


class TestNeedsReview:
    def test_llm_needs_review(self) -> None:
        assert needs_review(CONFIDENCE_LLM, RISK_LOW) is True

    def test_assumed_needs_review(self) -> None:
        assert needs_review(CONFIDENCE_ASSUMED, RISK_LOW) is True

    def test_measured_high_risk_needs_review(self) -> None:
        """実測でも高リスクなら人が見る（観測しても影響の大きさは下がらない）。"""
        assert needs_review(CONFIDENCE_MEASURED, RISK_HIGH) is True

    def test_measured_low_risk_is_auto(self) -> None:
        assert needs_review(CONFIDENCE_MEASURED, RISK_LOW) is False

    def test_measured_medium_risk_is_auto(self) -> None:
        assert needs_review(CONFIDENCE_MEASURED, RISK_MEDIUM) is False


class TestPageUrls:
    def test_maps_page_id_to_url(self) -> None:
        report = {"pages": [{"page_id": "P001", "url": "https://example.com/"}]}
        assert page_urls_from_report(report) == {"P001": "https://example.com/"}

    def test_missing_report_is_empty(self) -> None:
        assert page_urls_from_report(None) == {}

    def test_ignores_incomplete_entries(self) -> None:
        report = {"pages": [{"page_id": "P001"}, {"url": "u"}, "bad"]}
        assert page_urls_from_report(report) == {}


def _pipeline_with(items: list[StageItem]) -> Pipeline:
    pipeline = Pipeline.initial()
    stage = pipeline.get("features").with_items(tuple(items))
    return pipeline.replaced(stage)


class TestBuildQueue:
    def test_flattens_items_with_classification(self) -> None:
        pipeline = _pipeline_with(
            [
                _item(item_id="a", title="見出しの表示", source="rule"),
                _item(item_id="b", title="クーポン併用", source="llm"),
                _item(item_id="c", title="在庫上限", source="rule", assumed=True),
            ]
        )
        entries = build_review_queue(pipeline)
        assert [e.item_id for e in entries] == ["a", "b", "c"]
        assert [e.needs_review for e in entries] == [False, True, True]
        assert entries[0].stage_name == "テストフィーチャー分析"

    def test_reason_is_human_readable(self) -> None:
        pipeline = _pipeline_with([_item(item_id="b", source="llm")])
        assert "LLM" in build_review_queue(pipeline)[0].reason

    def test_summary_counts(self) -> None:
        pipeline = _pipeline_with(
            [
                _item(item_id="a", title="見出し", source="rule"),
                _item(item_id="b", title="クーポン", source="llm"),
                _item(item_id="c", title="在庫", source="rule", assumed=True, approved=True),
            ]
        )
        counts = summarize(build_review_queue(pipeline))
        assert counts["total"] == 3
        assert counts["auto"] == 1
        assert counts["review"] == 2
        assert counts["review_done"] == 1
        assert counts["review_pending"] == 1

    def test_empty_pipeline_has_no_entries(self) -> None:
        assert build_review_queue(Pipeline.initial()) == []


class TestReviewQueueApi:
    def _client(self):
        import app as appmod

        return appmod.app.test_client()

    @pytest.fixture()
    def domain_dir(self, tmp_path, monkeypatch):
        import web.routes.autorun_stages as mod

        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(mod, "scoped_output_dir", lambda base: base)
        return tmp_path

    def _write_pipeline(self, domain_dir: Path, items: list[StageItem]) -> None:
        pipeline = _pipeline_with(items)
        path = domain_dir / "example.com" / "qa_process" / "stages.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(pipeline.to_dict(), ensure_ascii=False), encoding="utf-8")

    def test_returns_entries_and_counts(self, domain_dir) -> None:
        self._write_pipeline(
            domain_dir,
            [
                _item(item_id="a", title="見出しの表示", source="rule"),
                _item(item_id="b", title="クーポン併用", source="llm"),
            ],
        )
        res = self._client().get("/api/autorun/review-queue?domain=example.com")
        assert res.status_code == 200
        body = res.get_json()
        assert body["counts"]["review"] == 1
        assert body["counts"]["auto"] == 1
        assert [e["item_id"] for e in body["entries"]] == ["a", "b"]

    def test_rejects_missing_domain(self) -> None:
        assert self._client().get("/api/autorun/review-queue").status_code == 400

    def test_auto_approve_only_touches_non_review(self, domain_dir) -> None:
        self._write_pipeline(
            domain_dir,
            [
                _item(item_id="a", title="見出しの表示", source="rule"),
                _item(item_id="b", title="クーポン併用", source="llm"),
                _item(item_id="c", title="決済フォームの送信", source="rule"),
            ],
        )
        res = self._client().post(
            "/api/autorun/review-queue/auto-approve", json={"domain": "example.com"}
        )
        assert res.status_code == 200
        body = res.get_json()
        assert body["approved"] == 1
        by_id = {e["item_id"]: e for e in body["entries"]}
        assert by_id["a"]["approved"] is True
        # LLM 提案と高リスクは自動承認しない
        assert by_id["b"]["approved"] is False
        assert by_id["c"]["approved"] is False

    def test_auto_approve_is_recorded_in_audit(self, domain_dir) -> None:
        self._write_pipeline(domain_dir, [_item(item_id="a", title="見出し", source="rule")])
        self._client().post(
            "/api/autorun/review-queue/auto-approve", json={"domain": "example.com"}
        )
        saved = json.loads(
            (domain_dir / "example.com" / "qa_process" / "stages.json").read_text(encoding="utf-8")
        )
        actions = [e["action"] for e in saved["audit"]]
        assert "item_approve" in actions
        assert any("自動承認" in e["detail"] for e in saved["audit"])

    def test_auto_approve_is_idempotent(self, domain_dir) -> None:
        self._write_pipeline(domain_dir, [_item(item_id="a", title="見出し", source="rule")])
        client = self._client()
        client.post("/api/autorun/review-queue/auto-approve", json={"domain": "example.com"})
        second = client.post(
            "/api/autorun/review-queue/auto-approve", json={"domain": "example.com"}
        )
        assert second.get_json()["approved"] == 0
