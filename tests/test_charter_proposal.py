"""SPEC-2-2: チャーター提案（propose_charters）とレポート統合のテスト。

対象:
    - src/capture/coverage.py::propose_charters / compute_exploration_coverage
    - src/generator/html_reporter.py::generate_html_report(exploration_coverage=...)
    - web/routes/report.py::api_result の files.exploration_heatmap / exploration_json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import networkx as nx

from analyzer.html_analyzer import analyze_pages
from capture.coverage import compute_exploration_coverage, propose_charters
from crawler.page_crawler import PageData
from generator.html_reporter import generate_html_report

FIXTURE_DOMAIN = "spec2-2.example.com"


def _base_coverage() -> dict:
    return {
        "summary": {
            "total_screens": 2,
            "explored_screens": 1,
            "unexplored_screens": 1,
            "coverage_ratio": 0.5,
            "total_states": 0,
            "touched_states": 0,
            "session_events": 3,
        },
        "screens": [
            {
                "page_id": "P001",
                "url": "https://example.com/",
                "title": "トップ",
                "visits": 1,
                "actions": 0,
                "states": [],
                "explored": True,
            },
            {
                "page_id": "P002",
                "url": "https://example.com/checkout",
                "title": "チェックアウト",
                "visits": 0,
                "actions": 0,
                "states": [],
                "explored": False,
            },
        ],
        "unmatched_footprints": [],
    }


class TestProposeCharters:
    def test_charter_unexplored_flow_screen_first(self) -> None:
        """未探索×flow通過画面が先頭・priority「高」・flowsに根拠が付く。"""
        coverage = _base_coverage()
        coverage["screens"].append(
            {
                "page_id": "P003",
                "url": "https://example.com/help",
                "title": "ヘルプ",
                "visits": 0,
                "actions": 0,
                "states": [],
                "explored": False,
            }
        )
        business_flows = [
            {
                "flow_name": "ログイン→決済",
                "path_id": "TP012",
                "nodes": ["https://example.com/checkout"],
            }
        ]
        charters = propose_charters(coverage, business_flows)
        assert [c["page_id"] for c in charters] == ["P002", "P003"]
        assert charters[0]["priority"] == "高"
        assert charters[0]["flows"] == [{"flow_name": "ログイン→決済", "path_id": "TP012"}]
        assert charters[1]["priority"] == "中"
        assert charters[1]["flows"] == []

    def test_charter_empty_without_flows(self) -> None:
        """business_flows=None の場合、"charters" キー自体が付かない。"""
        report = {"screens": [{"page_id": "P001", "url": "https://example.com/"}]}
        result = compute_exploration_coverage(report, events=[])
        assert "charters" not in result

    def test_charter_all_explored(self) -> None:
        """全画面 explored=true なら charters は空配列。"""
        coverage = _base_coverage()
        for screen in coverage["screens"]:
            screen["explored"] = True
        charters = propose_charters(coverage, business_flows=[])
        assert charters == []

    def test_charter_state_node_separator_is_stripped(self) -> None:
        """flow の nodes に状態ノード（#state=付き）が混ざっても URL 部分だけで照合する。"""
        coverage = _base_coverage()
        business_flows = [
            {
                "flow_name": "決済フロー",
                "path_id": "TP099",
                "nodes": ["https://example.com/checkout#state=modal-open"],
            }
        ]
        charters = propose_charters(coverage, business_flows)
        assert charters[0]["page_id"] == "P002"
        assert charters[0]["priority"] == "高"


class TestComputeExplorationCoverageSchema:
    def test_coverage_json_schema_unchanged(self) -> None:
        """business_flows 未指定時、既存3キー（summary/screens/unmatched_footprints）のみ。"""
        report = {
            "screens": [
                {"page_id": "P001", "url": "https://example.com/", "page_states": []},
            ]
        }
        result = compute_exploration_coverage(report, events=[])
        assert set(result.keys()) == {"summary", "screens", "unmatched_footprints"}

    def test_compute_exploration_coverage_adds_charters_when_flows_given(self) -> None:
        report = {
            "screens": [
                {"page_id": "P001", "url": "https://example.com/", "page_states": []},
            ]
        }
        events = [{"kind": "visit", "path": "/"}]
        result = compute_exploration_coverage(report, events=events, business_flows=[])
        assert result["charters"] == []


def _make_analyzed_pages():
    page_data = PageData(
        url="https://example.com/",
        title="Test Page",
        headings=("見出し",),
        links=(),
        forms=(),
        screenshot_path=None,
    )
    return analyze_pages([page_data])


def _empty_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("P001", url="https://example.com/", title="Test Page", page_id="P001")
    return graph


class TestExplorationSectionInReport:
    def test_report_html_without_coverage_identical(self) -> None:
        """exploration_coverage=None のとき、引数を渡さない場合と同一の出力。"""
        pages = _make_analyzed_pages()
        graph = _empty_graph()
        kwargs = dict(
            pages=pages,
            graph=graph,
            form_summary=[],
            target_url="https://example.com/",
            mermaid_content="graph LR\n P001\n",
        )
        with_none = generate_html_report(**kwargs, exploration_coverage=None)
        without_arg = generate_html_report(**kwargs)
        assert with_none == without_arg
        assert 'href="#exploration"' not in with_none

    def test_report_html_with_coverage_has_section(self) -> None:
        """カバレッジ集計済みなら、サイドバー項目とセクションが両方載る。"""
        pages = _make_analyzed_pages()
        graph = _empty_graph()
        coverage = _base_coverage()
        business_flows = [
            {
                "flow_name": "ログイン→決済",
                "path_id": "TP012",
                "nodes": ["https://example.com/checkout"],
            }
        ]
        coverage["charters"] = propose_charters(coverage, business_flows)

        html_text = generate_html_report(
            pages=pages,
            graph=graph,
            form_summary=[],
            target_url="https://example.com/",
            mermaid_content="graph LR\n P001\n",
            exploration_coverage=coverage,
        )
        assert '<a href="#exploration" class="nav-item">探索カバレッジ</a>' in html_text
        assert "探索カバレッジ" in html_text
        assert "次の探索チャーター（提案）" in html_text
        assert "ログイン→決済" in html_text
        assert "TP012" in html_text


class TestApiResultReturnsHeatmapPaths:
    def test_api_result_returns_heatmap_paths(self, tmp_path, monkeypatch) -> None:
        """/api/result の files に exploration_heatmap / exploration_json の実パスが載る。"""
        import app as appmod
        import web.routes.crawl as crawl_mod
        import web.routes.login as login_mod
        import web.routes.report as report_mod
        import web.routes.site as site_mod
        import web.summary as summary_mod

        for mod in (crawl_mod, login_mod, report_mod, site_mod, summary_mod):
            monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)

        domain_dir = tmp_path / FIXTURE_DOMAIN
        domain_dir.mkdir(parents=True, exist_ok=True)
        (domain_dir / "report.json").write_text(
            json.dumps(
                {"screens": [{"url": f"https://{FIXTURE_DOMAIN}/", "forms": [], "buttons": []}]}
            ),
            encoding="utf-8",
        )
        (domain_dir / "exploration_heatmap.html").write_text("<html></html>", encoding="utf-8")
        (domain_dir / "exploration_coverage.json").write_text("{}", encoding="utf-8")

        client = appmod.app.test_client()
        data = client.get(f"/api/result?domain={FIXTURE_DOMAIN}").get_json()
        assert data["files"]["exploration_heatmap"]
        assert data["files"]["exploration_json"]

    def test_api_result_files_empty_when_coverage_absent(self, tmp_path, monkeypatch) -> None:
        """カバレッジファイルが無いドメインでは files キーが空文字。"""
        import app as appmod
        import web.routes.crawl as crawl_mod
        import web.routes.login as login_mod
        import web.routes.report as report_mod
        import web.routes.site as site_mod
        import web.summary as summary_mod

        for mod in (crawl_mod, login_mod, report_mod, site_mod, summary_mod):
            monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)

        domain = "no-coverage.example.com"
        domain_dir = tmp_path / domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        (domain_dir / "report.json").write_text(
            json.dumps({"screens": [{"url": f"https://{domain}/", "forms": [], "buttons": []}]}),
            encoding="utf-8",
        )

        client = appmod.app.test_client()
        data = client.get(f"/api/result?domain={domain}").get_json()
        assert data["files"]["exploration_heatmap"] == ""
        assert data["files"]["exploration_json"] == ""
