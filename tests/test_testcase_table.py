"""ローレベルテストケース表（9列）の生成・編集・履歴のテスト。

「初めてシステムを触る作業者が読んでも同じ結果になる」ことを機械的に検証する:
曖昧語の不在・具体値の存在・URL の明示・決定性を assert する。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import pytest
import web.routes.qa_process as qa_mod
from web.services import testcase_table_store as store

from generator.test_design import TestDesignParams as _DesignParams
from generator.test_design import build_test_design
from generator.testcase_table import build_testcase_table

DOMAIN = "tc-table.example.com"

# 実行者ごとに結果が変わる曖昧語（手順に出てはいけない）
_VAGUE_WORDS = ("適切な", "適当な", "規定内", "任意の値", "正しい値", "など")


def _report() -> dict:
    return {
        "meta": {"target_url": f"https://{DOMAIN}/", "page_count": 2},
        "screens": [
            {
                "page_id": "P001",
                "url": f"https://{DOMAIN}/form.html",
                "title": "申込入力 | サンプル",
                "headings": ["申込入力"],
                "buttons": ["確認画面へ"],
                "forms": [
                    {
                        "action": "/confirm",
                        "method": "post",
                        "fields": [
                            {
                                "name": "user_name",
                                "element_id": "user_name",
                                "field_type": "text",
                                "required": True,
                                "maxlength": 20,
                                "label_text": "氏名",
                                "locators": ["#user_name"],
                                "options": [],
                            },
                            {
                                "name": "user_zip",
                                "element_id": "user_zip",
                                "field_type": "text",
                                "required": True,
                                "maxlength": 8,
                                "label_text": "",
                                "locators": ["#user_zip"],
                                "options": [],
                            },
                            {
                                "name": "plan",
                                "element_id": "plan",
                                "field_type": "select",
                                "required": True,
                                "label_text": "プラン",
                                "locators": ["#plan"],
                                "options": ["選択してください", "light", "standard"],
                            },
                        ],
                    }
                ],
                "transitions": {"to": ["P002"], "from": []},
            },
            {
                "page_id": "P002",
                "url": f"https://{DOMAIN}/done.html",
                "title": "完了 | サンプル",
                "headings": ["完了"],
                "buttons": [],
                "forms": [],
                "transitions": {"to": [], "from": ["P001"]},
            },
        ],
    }


def _rows() -> list:
    report = _report()
    design = build_test_design(report, _DesignParams())
    return list(build_testcase_table(report, design))


def _write_report(base: Path) -> Path:
    domain_dir = base / DOMAIN
    domain_dir.mkdir(parents=True, exist_ok=True)
    (domain_dir / "report.json").write_text(json.dumps(_report()), encoding="utf-8")
    return domain_dir


@pytest.fixture()
def output_dir(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(qa_mod, "OUTPUT_DIR", tmp_path)
    _write_report(tmp_path)
    return tmp_path


class TestGeneration:
    def test_generates_cases_for_every_technique(self) -> None:
        rows = _rows()
        viewpoints = {r.viewpoint.split("／")[0] for r in rows}
        assert "画面表示確認" in viewpoints
        assert "境界値分析" in viewpoints
        assert "デシジョンテーブル" in viewpoints
        assert any(v.startswith("ペアワイズ") for v in viewpoints)
        assert "画面遷移" in viewpoints

    def test_all_nine_columns_are_filled(self) -> None:
        for row in _rows():
            assert row.case_id and row.name and row.screen and row.function
            assert row.viewpoint and row.automation
            assert row.preconditions, f"{row.case_id}: 前提条件が空"
            assert row.steps, f"{row.case_id}: 手順が空"
            assert row.expected, f"{row.case_id}: 期待結果が空"

    def test_case_ids_are_unique(self) -> None:
        ids = [r.case_id for r in _rows()]
        assert len(ids) == len(set(ids))

    def test_steps_start_by_opening_a_concrete_url(self) -> None:
        for row in _rows():
            assert "https://" in row.steps[0], f"{row.case_id}: 開くURLが手順に無い"

    def test_steps_have_no_vague_wording(self) -> None:
        """「適切な値」のような、実行者に判断を委ねる語を含まないこと。"""
        for row in _rows():
            for step in row.steps:
                for word in _VAGUE_WORDS:
                    assert word not in step, f"{row.case_id}: 曖昧語『{word}』: {step}"

    def test_input_steps_name_both_label_and_locator(self) -> None:
        bva = [r for r in _rows() if "境界値分析" in r.viewpoint]
        target = next(r for r in bva if "user_name" in r.name)
        input_step = next(s for s in target.steps if "を入力する" in s)
        assert "「氏名」欄" in input_step  # 画面上のラベル
        assert "#user_name" in input_step  # 自動化用ロケータ

    def test_other_required_fields_get_concrete_values(self) -> None:
        """検証対象以外の必須項目も、具体値つきで手順に展開されること。"""
        target = next(r for r in _rows() if r.case_id.endswith("BVA-001"))
        joined = "\n".join(target.steps)
        assert "#user_zip" in joined
        assert "1000001" in joined  # 郵便番号の既定値
        assert "「standard」を選択する" in joined or "「light」を選択する" in joined

    def test_deterministic(self) -> None:
        assert _rows() == _rows()


class TestStore:
    def test_compose_returns_columns_and_rows(self, output_dir: Path) -> None:
        payload = store.compose(DOMAIN, _report())
        assert [c["key"] for c in payload["columns"]] == [
            "case_id",
            "name",
            "screen",
            "function",
            "viewpoint",
            "preconditions",
            "steps",
            "expected",
            "automation",
            "result",
        ]
        assert payload["count"] == len(payload["rows"]) > 0

    def test_update_cell_persists_and_records_history(self, output_dir: Path) -> None:
        report = _report()
        case_id = store.compose(DOMAIN, report)["rows"][0]["case_id"]
        result = store.update_cell(DOMAIN, report, case_id, "name", "手で直した名前")

        assert result["changed"] is True
        assert result["row"]["name"] == "手で直した名前"
        assert result["row"]["edited_columns"] == ["name"]

        again = store.compose(DOMAIN, report)
        row = next(r for r in again["rows"] if r["case_id"] == case_id)
        assert row["name"] == "手で直した名前"
        assert again["edited_cells"] == 1

        history = store.load_history(DOMAIN)
        assert history[0]["action"] == "edit"
        assert history[0]["column"] == "name"
        assert history[0]["after"] == "手で直した名前"

    def test_list_column_accepts_newline_text(self, output_dir: Path) -> None:
        report = _report()
        case_id = store.compose(DOMAIN, report)["rows"][0]["case_id"]
        store.update_cell(DOMAIN, report, case_id, "steps", "1つ目\n2つ目\n")
        row = next(
            r for r in store.compose(DOMAIN, report)["rows"] if r["case_id"] == case_id
        )
        assert row["steps"] == ["1つ目", "2つ目"]

    def test_reset_cell_restores_generated_value(self, output_dir: Path) -> None:
        report = _report()
        case_id = store.compose(DOMAIN, report)["rows"][0]["case_id"]
        original = store.compose(DOMAIN, report)["rows"][0]["name"]
        store.update_cell(DOMAIN, report, case_id, "name", "編集後")
        store.reset_cell(DOMAIN, report, case_id, "name")

        row = next(
            r for r in store.compose(DOMAIN, report)["rows"] if r["case_id"] == case_id
        )
        assert row["name"] == original
        assert row["edited_columns"] == []
        assert [h["action"] for h in store.load_history(DOMAIN)][:2] == ["reset", "edit"]

    def test_edit_back_to_generated_value_clears_edited_mark(self, output_dir: Path) -> None:
        """生成値と同じ値に戻したら「編集済み」印を残さない（取り消し操作の後始末）。"""
        report = _report()
        row0 = store.compose(DOMAIN, report)["rows"][0]
        case_id, original = row0["case_id"], row0["name"]

        store.update_cell(DOMAIN, report, case_id, "name", "編集後")
        store.update_cell(DOMAIN, report, case_id, "name", original)

        after = store.compose(DOMAIN, report)
        row = next(r for r in after["rows"] if r["case_id"] == case_id)
        assert row["name"] == original
        assert row["edited_columns"] == []
        assert after["edited_cells"] == 0
        assert store.load_history(DOMAIN)[0]["action"] == "reset"

    def test_uneditable_column_is_rejected(self, output_dir: Path) -> None:
        with pytest.raises(store.TestcaseStoreError):
            store.update_cell(DOMAIN, _report(), "TC-P001-DSP-001", "case_id", "X")

    def test_unknown_case_is_rejected(self, output_dir: Path) -> None:
        with pytest.raises(store.TestcaseStoreError):
            store.update_cell(DOMAIN, _report(), "NO-SUCH", "name", "X")

    def test_add_and_delete_row(self, output_dir: Path) -> None:
        report = _report()
        before = store.compose(DOMAIN, report)["count"]
        added = store.add_row(DOMAIN, report)
        assert store.compose(DOMAIN, report)["count"] == before + 1

        store.delete_row(DOMAIN, added["row"]["case_id"])
        assert store.compose(DOMAIN, report)["count"] == before

    def test_delete_and_restore_generated_row(self, output_dir: Path) -> None:
        report = _report()
        case_id = store.compose(DOMAIN, report)["rows"][0]["case_id"]
        store.delete_row(DOMAIN, case_id)
        assert all(r["case_id"] != case_id for r in store.compose(DOMAIN, report)["rows"])

        store.restore_row(DOMAIN, case_id)
        assert any(r["case_id"] == case_id for r in store.compose(DOMAIN, report)["rows"])


class TestApi:
    def _client(self):
        return appmod.app.test_client()

    def test_table_endpoint(self, output_dir: Path) -> None:
        res = self._client().get(f"/api/testcases/table?domain={DOMAIN}")
        data = res.get_json()
        assert res.status_code == 200
        assert data["count"] > 0
        assert len(data["columns"]) == 10

    def test_table_endpoint_404_for_unknown_domain(self, output_dir: Path) -> None:
        res = self._client().get("/api/testcases/table?domain=no-such.example")
        assert res.status_code == 404

    def test_cell_endpoint_updates_and_history_endpoint_lists_it(self, output_dir: Path) -> None:
        client = self._client()
        case_id = store.compose(DOMAIN, _report())["rows"][0]["case_id"]
        res = client.post(
            "/api/testcases/cell",
            json={"domain": DOMAIN, "case_id": case_id, "column": "name", "value": "APIで編集"},
        )
        assert res.status_code == 200
        assert res.get_json()["row"]["name"] == "APIで編集"

        hist = client.get(f"/api/testcases/history?domain={DOMAIN}").get_json()
        assert hist["items"][0]["case_id"] == case_id

    def test_cell_endpoint_rejects_uneditable_column(self, output_dir: Path) -> None:
        res = self._client().post(
            "/api/testcases/cell",
            json={"domain": DOMAIN, "case_id": "TC-P001-DSP-001", "column": "case_id", "value": "X"},
        )
        assert res.status_code == 400

    def test_row_endpoint_add_delete(self, output_dir: Path) -> None:
        client = self._client()
        added = client.post("/api/testcases/row", json={"domain": DOMAIN, "action": "add"})
        assert added.status_code == 200
        case_id = added.get_json()["row"]["case_id"]

        deleted = client.post(
            "/api/testcases/row", json={"domain": DOMAIN, "action": "delete", "case_id": case_id}
        )
        assert deleted.status_code == 200

    def test_row_endpoint_rejects_unknown_action(self, output_dir: Path) -> None:
        res = self._client().post("/api/testcases/row", json={"domain": DOMAIN, "action": "zap"})
        assert res.status_code == 400
