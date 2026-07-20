"""AutoRun 段階承認 API のテスト（Flask テストクライアント）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.autorun_stages as stages_mod

DOMAIN = "example.com"

REPORT = {
    "screens": [
        {
            "page_id": "P001",
            "url": "https://example.com/",
            "title": "トップ",
            "forms": [],
            "transitions": {"to": ["P002"], "from": []},
        },
        {
            "page_id": "P002",
            "url": "https://example.com/reserve.html",
            "title": "予約",
            "forms": [{"inputs": [{"name": "date", "required": True}]}],
            "transitions": {"to": [], "from": ["P001"]},
        },
    ]
}


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """出力先を一時ディレクトリへ隔離する。"""
    domain_dir = tmp_path / DOMAIN
    (domain_dir / "qa_process").mkdir(parents=True)
    (domain_dir / "report.json").write_text(
        json.dumps(REPORT, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(stages_mod, "scoped_output_dir", lambda _root: tmp_path)
    return tmp_path


@pytest.fixture()
def client(workspace):
    return appmod.app.test_client()


def _post(client, path, payload):
    return client.post(path, json=payload)


class TestStageListing:
    def test_returns_seven_stages_pending(self, client) -> None:
        res = client.get(f"/api/autorun/stages?domain={DOMAIN}")
        assert res.status_code == 200
        body = res.get_json()
        assert len(body["stages"]) == 7
        assert body["current_stage_id"] == "test_objective"
        assert body["all_approved"] is False

    def test_rejects_missing_domain(self, client) -> None:
        assert client.get("/api/autorun/stages").status_code == 400

    def test_rejects_invalid_domain(self, client) -> None:
        assert client.get("/api/autorun/stages?domain=../etc").status_code == 400


class TestGenerateAndApprove:
    def test_generates_test_objective_from_observation(self, client) -> None:
        res = _post(client, "/api/autorun/stages/generate",
                    {"domain": DOMAIN, "stage_id": "test_objective"})
        assert res.status_code == 200
        stage = next(s for s in res.get_json()["stages"] if s["stage_id"] == "test_objective")
        assert stage["status"] == "generated"
        assert any("欠陥" in i["title"] for i in stage["items"])

    def test_approving_advances_to_next_stage(self, client) -> None:
        _post(client, "/api/autorun/stages/generate",
              {"domain": DOMAIN, "stage_id": "test_objective"})
        res = _post(client, "/api/autorun/stages/approve",
                    {"domain": DOMAIN, "stage_id": "test_objective"})
        assert res.status_code == 200
        assert res.get_json()["current_stage_id"] == "test_plan"

    def test_rejects_unknown_stage(self, client) -> None:
        res = _post(client, "/api/autorun/stages/generate",
                    {"domain": DOMAIN, "stage_id": "nope"})
        assert res.status_code == 400

    def test_state_persists_across_requests(self, client, workspace) -> None:
        _post(client, "/api/autorun/stages/generate",
              {"domain": DOMAIN, "stage_id": "test_objective"})
        assert (workspace / DOMAIN / "qa_process" / "stages.json").is_file()

        body = client.get(f"/api/autorun/stages?domain={DOMAIN}").get_json()
        stage = next(s for s in body["stages"] if s["stage_id"] == "test_objective")
        assert stage["items"], "保存した内容が読み戻せること"


class TestFeatureApprovalGate:
    """仕様9: 全フィーチャーの承認が無いと段階を承認できない。"""

    def _reach_features(self, client) -> dict:
        for stage_id in ("test_objective", "test_plan"):
            _post(client, "/api/autorun/stages/generate",
                  {"domain": DOMAIN, "stage_id": stage_id})
            _post(client, "/api/autorun/stages/approve",
                  {"domain": DOMAIN, "stage_id": stage_id})
        return _post(client, "/api/autorun/stages/generate",
                     {"domain": DOMAIN, "stage_id": "features"}).get_json()

    def test_blocks_approval_while_items_unapproved(self, client) -> None:
        self._reach_features(client)
        res = _post(client, "/api/autorun/stages/approve",
                    {"domain": DOMAIN, "stage_id": "features"})
        assert res.status_code == 409
        assert "承認" in res.get_json()["error"]

    def test_allows_approval_after_every_item_approved(self, client) -> None:
        body = self._reach_features(client)
        stage = next(s for s in body["stages"] if s["stage_id"] == "features")
        for item in stage["items"]:
            _post(client, "/api/autorun/stages/item", {
                "domain": DOMAIN, "stage_id": "features",
                "item_id": item["item_id"], "approved": True,
            })
        res = _post(client, "/api/autorun/stages/approve",
                    {"domain": DOMAIN, "stage_id": "features"})
        assert res.status_code == 200


class TestSkipRules:
    """仕様8: スキップは同一URLの2回目以降のみ。"""

    def test_first_run_cannot_skip(self, client) -> None:
        res = _post(client, "/api/autorun/stages/skip",
                    {"domain": DOMAIN, "stage_id": "test_plan"})
        assert res.status_code == 409

    def test_non_skippable_stage_is_rejected(self, client) -> None:
        res = _post(client, "/api/autorun/stages/skip",
                    {"domain": DOMAIN, "stage_id": "features"})
        assert res.status_code == 400

    def test_rerun_can_skip_test_plan(self, client, workspace) -> None:
        snapshots = workspace / DOMAIN / "snapshots"
        snapshots.mkdir(parents=True, exist_ok=True)
        (snapshots / "prev.json").write_text("{}", encoding="utf-8")
        # 前回スナップショットを認識させるため状態を作り直す
        _post(client, "/api/autorun/stages/reset", {"domain": DOMAIN})

        res = _post(client, "/api/autorun/stages/skip",
                    {"domain": DOMAIN, "stage_id": "test_plan"})
        assert res.status_code == 200
        stage = next(s for s in res.get_json()["stages"] if s["stage_id"] == "test_plan")
        assert stage["status"] == "skipped"


class TestItemEditing:
    def test_editing_marks_item_as_user_edited(self, client) -> None:
        body = _post(client, "/api/autorun/stages/generate",
                     {"domain": DOMAIN, "stage_id": "test_objective"}).get_json()
        stage = next(s for s in body["stages"] if s["stage_id"] == "test_objective")
        item_id = stage["items"][0]["item_id"]

        res = _post(client, "/api/autorun/stages/item", {
            "domain": DOMAIN, "stage_id": "test_objective",
            "item_id": item_id, "title": "書き換えた目的",
        })
        assert res.status_code == 200
        updated = next(
            i for s in res.get_json()["stages"] if s["stage_id"] == "test_objective"
            for i in s["items"] if i["item_id"] == item_id
        )
        assert updated["title"] == "書き換えた目的"
        assert updated["source"] == "user"

    def test_rejects_unknown_item(self, client) -> None:
        _post(client, "/api/autorun/stages/generate",
              {"domain": DOMAIN, "stage_id": "test_objective"})
        res = _post(client, "/api/autorun/stages/item", {
            "domain": DOMAIN, "stage_id": "test_objective",
            "item_id": "missing", "approved": True,
        })
        assert res.status_code == 404


class TestSuggestAndAdopt:
    """LLM 提案は補助。段階の内容を壊さないこと。"""

    def test_suggest_without_llm_is_not_an_error(self, client, monkeypatch) -> None:
        """LLM 未設定でも 200 で返し、利用不可であることを伝える。"""
        import autorun.suggest as suggest_mod

        class _NoKey:
            api_key = ""
            model = "m"
            base_url = "http://127.0.0.1:11434/v1"

        monkeypatch.setattr(suggest_mod, "resolve_endpoint", lambda: _NoKey())
        _post(client, "/api/autorun/stages/generate",
              {"domain": DOMAIN, "stage_id": "test_objective"})
        res = _post(client, "/api/autorun/stages/suggest",
                    {"domain": DOMAIN, "stage_id": "test_objective"})
        assert res.status_code == 200
        assert res.get_json()["available"] is False

    def test_suggest_rejects_unknown_stage(self, client) -> None:
        res = _post(client, "/api/autorun/stages/suggest",
                    {"domain": DOMAIN, "stage_id": "nope"})
        assert res.status_code == 400

    def test_adopting_appends_item_marked_as_llm(self, client) -> None:
        _post(client, "/api/autorun/stages/generate",
              {"domain": DOMAIN, "stage_id": "test_objective"})
        before = client.get(f"/api/autorun/stages?domain={DOMAIN}").get_json()
        count = len(next(s for s in before["stages"] if s["stage_id"] == "test_objective")["items"])

        res = _post(client, "/api/autorun/stages/adopt", {
            "domain": DOMAIN, "stage_id": "test_objective",
            "title": "セッション期限切れの確認", "detail": "期限切れ後の操作",
        })
        assert res.status_code == 200
        stage = next(s for s in res.get_json()["stages"] if s["stage_id"] == "test_objective")
        assert len(stage["items"]) == count + 1
        adopted = stage["items"][-1]
        assert adopted["title"] == "セッション期限切れの確認"
        assert adopted["source"] == "llm"

    def test_adopt_rejects_empty_title(self, client) -> None:
        res = _post(client, "/api/autorun/stages/adopt",
                    {"domain": DOMAIN, "stage_id": "test_objective", "title": "  "})
        assert res.status_code == 400


class TestTestCaseExport:
    """仕様13: QualityForward のカラム構成で取り出せる。"""

    def _run_all_stages(self, client) -> None:
        order = ["test_objective", "test_plan", "features", "viewpoints",
                 "basic_design", "detail_design", "test_cases"]
        for stage_id in order:
            body = _post(client, "/api/autorun/stages/generate",
                         {"domain": DOMAIN, "stage_id": stage_id}).get_json()
            stage = next(s for s in body["stages"] if s["stage_id"] == stage_id)
            if stage["requires_item_approval"]:
                for item in stage["items"]:
                    _post(client, "/api/autorun/stages/item", {
                        "domain": DOMAIN, "stage_id": stage_id,
                        "item_id": item["item_id"], "approved": True,
                    })
            _post(client, "/api/autorun/stages/approve",
                  {"domain": DOMAIN, "stage_id": stage_id})

    def test_full_pipeline_completes(self, client) -> None:
        self._run_all_stages(client)
        body = client.get(f"/api/autorun/stages?domain={DOMAIN}").get_json()
        assert body["all_approved"] is True
        assert body["current_stage_id"] is None

    def test_table_uses_qualityforward_columns(self, client) -> None:
        self._run_all_stages(client)
        body = client.get(f"/api/autorun/stages/testcases?domain={DOMAIN}").get_json()
        labels = [c["label"] for c in body["columns"]]
        assert labels == [
            "No", "画面", "正常系/異常系", "観点名", "大項目", "中項目",
            "小項目", "前提条件", "手順", "期待結果", "備考",
        ]
        assert body["rows"], "テストケースが生成されていること"

    def test_csv_export_is_downloadable(self, client) -> None:
        self._run_all_stages(client)
        res = client.get(f"/api/autorun/stages/testcases?domain={DOMAIN}&format=csv")
        assert res.status_code == 200
        assert "attachment" in res.headers["Content-Disposition"]
        first_line = res.get_data(as_text=True).splitlines()[0]
        assert first_line.startswith("No,画面,正常系/異常系")
