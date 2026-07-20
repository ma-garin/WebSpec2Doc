"""AutoRun 実行結果レポート専用ページ（仕様15〜17）のテスト。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.autorun_report as report_mod

DOMAIN = "example.com"

SECTIONS = ["dashboard", "spec", "plan", "analysis", "design", "cases", "script", "results"]


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    base = tmp_path / DOMAIN
    qa = base / "qa_process"
    qa.mkdir(parents=True)

    (base / "report.json").write_text(
        json.dumps(
            {
                "screens": [
                    {
                        "page_id": "P001",
                        "url": "https://example.com/",
                        "title": "トップ",
                        "forms": [{"fields": [{"name": "q", "required": True}]}],
                        "transitions": {"to": [], "from": []},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (base / "screens.md").write_text("# 画面仕様\n\n- トップ", encoding="utf-8")
    (qa / "test_plan.md").write_text("# テスト計画\n\nスコープ: 1画面", encoding="utf-8")
    (qa / "test_analysis.md").write_text("# テスト分析", encoding="utf-8")
    (qa / "test_design.md").write_text("# テスト設計", encoding="utf-8")
    (qa / "autorun.spec.ts").write_text("import { test } from '@playwright/test';", encoding="utf-8")
    # playwright_executor.py の実際の出力形式（total/passed/failed はトップレベル。
    # {"summary": {...}} ではない）に合わせる。過去このズレにより、実行済みでも
    # ダッシュボードが「未実行」と表示される不具合があった（監査で発覚・修正済み）。
    (qa / "playwright_report.json").write_text(
        json.dumps({"total": 3, "passed": 2, "failed": 1,
                    "tests": [{"title": "予約フォーム", "status": "failed", "error": "timeout"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(report_mod, "scoped_output_dir", lambda _root: tmp_path)
    return tmp_path


@pytest.fixture()
def client(workspace):
    return appmod.app.test_client()


class TestReportPage:
    """仕様16: 専用ページが開く。"""

    def test_page_opens_for_known_domain(self, client) -> None:
        res = client.get(f"/autorun/report/{DOMAIN}")
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert DOMAIN in html

    def test_page_lists_all_eight_sections(self, client) -> None:
        """仕様17: ダッシュボード/QA仕様書/計画/分析/設計/ケース/スクリプト/実行結果。"""
        html = client.get(f"/autorun/report/{DOMAIN}").get_data(as_text=True)
        for label in ("ダッシュボード", "QA仕様書", "計画", "分析", "設計",
                      "ケース", "スクリプト", "実行結果"):
            assert label in html

    def test_unknown_domain_is_404(self, client) -> None:
        assert client.get("/autorun/report/not-analyzed.example").status_code == 404

    def test_invalid_domain_is_404(self, client) -> None:
        assert client.get("/autorun/report/..%2Fetc").status_code == 404


class TestReportApi:
    @pytest.mark.parametrize("section", SECTIONS)
    def test_every_section_responds(self, client, section: str) -> None:
        res = client.get(f"/api/autorun/report/{DOMAIN}?section={section}")
        assert res.status_code == 200
        assert res.get_json()["section"] == section

    def test_rejects_unknown_section(self, client) -> None:
        res = client.get(f"/api/autorun/report/{DOMAIN}?section=nope")
        assert res.status_code == 400

    def test_dashboard_summarises_observation_and_results(self, client) -> None:
        data = client.get(f"/api/autorun/report/{DOMAIN}?section=dashboard").get_json()["data"]
        assert data["screen_count"] == 1
        assert data["form_count"] == 1
        assert data["input_count"] == 1
        assert data["test_total"] == 3
        assert data["test_passed"] == 2
        assert data["test_failed"] == 1

    def test_dashboard_states_claim_scope(self, client) -> None:
        """数値だけを見て「問題なし」と読まれないようにする。"""
        data = client.get(f"/api/autorun/report/{DOMAIN}?section=dashboard").get_json()["data"]
        assert "未検証" in data["claim_scope"]

    def test_dashboard_does_not_show_not_executed_when_tests_ran(
        self, client, workspace
    ) -> None:
        """回帰テスト：実行済みなのに「未実行」（test_total が None）と表示される不具合の再発防止。

        playwright_report.json の実際の形式（total/passed/failed がトップレベル）に対し、
        以前は {"summary": {...}} を前提に読んでいたため test_total が常に None になり、
        フロントで「未実行」と表示されていた。
        """
        data = client.get(f"/api/autorun/report/{DOMAIN}?section=dashboard").get_json()["data"]
        assert data["test_total"] is not None
        assert data["test_total"] == 3
        assert data["test_passed"] == 2
        assert data["test_failed"] == 1
        assert "証明ではありません" in data["claim_scope"]

    def test_dashboard_shows_self_check_score_when_available(
        self, client, workspace
    ) -> None:
        """AutoRun自身のミューテーションテスト自己検証スコアをダッシュボードに表示する。"""
        qa = workspace / DOMAIN / "qa_process"
        (qa / "mutation_verification.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "applicable": True,
                    "total": 10,
                    "detected": 9,
                    "survivors": ["PW-0005 x [P001]"],
                    "survivor_count": 1,
                    "score": 90.0,
                }
            ),
            encoding="utf-8",
        )
        data = client.get(f"/api/autorun/report/{DOMAIN}?section=dashboard").get_json()["data"]
        assert data["self_check_score"] == 90.0
        assert data["self_check_survivor_count"] == 1

    def test_dashboard_self_check_is_none_when_not_yet_run(self, client) -> None:
        data = client.get(f"/api/autorun/report/{DOMAIN}?section=dashboard").get_json()["data"]
        assert data["self_check_score"] is None

    def test_plan_section_returns_generated_document(self, client) -> None:
        body = client.get(f"/api/autorun/report/{DOMAIN}?section=plan").get_json()
        assert body["kind"] == "markdown"
        assert "テスト計画" in body["text"]

    def test_script_section_returns_playwright_source(self, client) -> None:
        body = client.get(f"/api/autorun/report/{DOMAIN}?section=script").get_json()
        assert body["kind"] == "code"
        assert "@playwright/test" in body["text"]

    def test_results_section_returns_execution_detail(self, client) -> None:
        body = client.get(f"/api/autorun/report/{DOMAIN}?section=results").get_json()
        assert body["kind"] == "results"
        # results セクションは playwright_report.json をそのまま返す（total/passed/failed はトップレベル）。
        assert body["data"]["failed"] == 1

    def test_large_report_json_is_not_truncated(self, client, workspace) -> None:
        """表示用の文字数上限を JSON 読み取りに適用してはいけない。

        切り詰めると解析に失敗し「画面0件」に見えてしまう（実際には在る）。
        """
        screens = [
            {
                "page_id": f"P{i:03d}",
                "url": f"https://example.com/page{i}",
                "title": f"画面{i}" + "あ" * 200,  # 上限を超える大きさにする
                "forms": [{"fields": [{"name": "q", "required": True}]}],
                "transitions": {"to": [], "from": []},
            }
            for i in range(400)
        ]
        path = workspace / DOMAIN / "report.json"
        path.write_text(json.dumps({"screens": screens}, ensure_ascii=False), encoding="utf-8")
        assert path.stat().st_size > report_mod.MAX_TEXT_CHARS

        data = client.get(f"/api/autorun/report/{DOMAIN}?section=dashboard").get_json()["data"]
        assert data["screen_count"] == 400
        assert data["input_count"] == 400

    def test_missing_artifact_is_reported_as_absent_not_empty(self, client, workspace) -> None:
        """未生成は None を返し、UI 側が「未生成」と明示できるようにする。"""
        (workspace / DOMAIN / "qa_process" / "test_design.md").unlink()
        body = client.get(f"/api/autorun/report/{DOMAIN}?section=design").get_json()
        assert body["text"] is None
        assert body["source"] == "test_design.md"


class TestTestCaseSection:
    """仕様13の成果を仕様17の「ケース」欄で見せる。"""

    def test_falls_back_to_markdown_without_pipeline(self, client, workspace) -> None:
        (workspace / DOMAIN / "qa_process" / "test_cases.md").write_text(
            "# テストケース", encoding="utf-8"
        )
        body = client.get(f"/api/autorun/report/{DOMAIN}?section=cases").get_json()
        assert body["kind"] == "markdown"

    def test_uses_pipeline_table_when_available(self, client, workspace) -> None:
        stages = {
            "stages": [
                {
                    "stage_id": "test_cases",
                    "status": "approved",
                    "items": [
                        {
                            "item_id": "tc-1",
                            "title": "No.1",
                            "detail": "",
                            "data": {
                                "no": 1, "screen": "トップ", "case_type": "正常系",
                                "viewpoint": "表示・レイアウト", "category_large": "トップ",
                                "category_medium": "表示・レイアウト", "category_small": "実測比較",
                                "precondition": "", "steps": "1. 開く",
                                "expected": "表示される", "note": "",
                            },
                        }
                    ],
                }
            ]
        }
        (workspace / DOMAIN / "qa_process" / "stages.json").write_text(
            json.dumps(stages, ensure_ascii=False), encoding="utf-8"
        )
        body = client.get(f"/api/autorun/report/{DOMAIN}?section=cases").get_json()
        assert body["kind"] == "table"
        assert [c["label"] for c in body["columns"]][:4] == ["No", "画面", "正常系/異常系", "観点名"]
        assert body["rows"][0]["screen"] == "トップ"
