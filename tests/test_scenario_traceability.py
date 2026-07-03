"""シナリオ生成とトレーサビリティ（Layer 3）のユニット・受け入れテスト。"""

from __future__ import annotations

import json
from pathlib import Path

from web.services.spec_ts_generator import generate_spec_ts, metadata_file_path
from web.services.traceability import build_matrix

from crawler.page_crawler import FieldData, FormData, PageData
from graph.transition_graph import (
    COVERAGE_DEFINITION_SOURCE,
    business_flows_to_dict,
    classify_pages_for_flows,
    compute_switch_coverage,
    generate_transition_tests,
    prioritize_business_flows,
    switch_coverage_to_dict,
)


def _page(url: str, title: str, links: tuple[str, ...] = ()) -> PageData:
    return PageData(
        url=url,
        title=title,
        headings=(title,),
        links=links,
        forms=(),
        screenshot_path=None,
    )


def _linear_pages() -> list[PageData]:
    """A→B→C の直線グラフ（エッジ2本・連続2遷移ペア1つ）。"""
    return [
        _page("https://example.com/a", "A", links=("https://example.com/b",)),
        _page("https://example.com/b", "B", links=("https://example.com/c",)),
        _page("https://example.com/c", "C"),
    ]


# ---------- 受け入れ条件: カバレッジ率が手計算と一致 ----------


class TestSwitchCoverage:
    def test_full_coverage_matches_manual_calculation(self) -> None:
        """既知の小規模グラフ（A→B→C）で手計算と一致することを確認する。

        手計算: 単一遷移は {A→B, B→C} の2本、連続2遷移ペアは {A→B→C} の1つ。
        1-switch モードの生成パスは全エッジをカバーするため
        0-switch カバレッジ = 2/2 = 1.0、1-switch カバレッジ = 0/1 = 0.0
        （エッジ単位のパスでは連続2遷移を通過しない）。
        """
        pages = _linear_pages()
        paths = generate_transition_tests(pages, coverage="1-switch")
        coverage = compute_switch_coverage(pages, paths)

        assert coverage["0-switch"].covered == 2
        assert coverage["0-switch"].total == 2
        assert coverage["0-switch"].rate == 1.0
        assert coverage["1-switch"].covered == 0
        assert coverage["1-switch"].total == 1
        assert coverage["1-switch"].rate == 0.0

    def test_2switch_paths_cover_pairs(self) -> None:
        """2-switch モードの生成パス（A→B→C）は連続2遷移ペアを網羅する。"""
        pages = _linear_pages()
        paths = generate_transition_tests(pages, coverage="2-switch")
        coverage = compute_switch_coverage(pages, paths)

        assert coverage["1-switch"].covered == 1
        assert coverage["1-switch"].total == 1
        assert coverage["1-switch"].rate == 1.0

    def test_partial_coverage_manual_calculation(self) -> None:
        """パスがエッジの一部しか通らない場合の率も手計算と一致する。"""
        pages = _linear_pages()
        all_paths = generate_transition_tests(pages, coverage="1-switch")
        # A→B のパスだけを採用（B→C は未カバー）
        partial = [p for p in all_paths if p.nodes[0] == "https://example.com/a"]
        coverage = compute_switch_coverage(pages, partial)

        assert coverage["0-switch"].covered == 1
        assert coverage["0-switch"].total == 2
        assert coverage["0-switch"].rate == 0.5

    def test_definition_source_is_iso29119(self) -> None:
        """定義出典として ISO/IEC/IEEE 29119-4 が明記される。"""
        pages = _linear_pages()
        paths = generate_transition_tests(pages, coverage="1-switch")
        as_dict = switch_coverage_to_dict(compute_switch_coverage(pages, paths))

        assert "29119-4" in as_dict["0-switch"]["definition_source"]
        assert as_dict["0-switch"]["definition_source"] == COVERAGE_DEFINITION_SOURCE

    def test_empty_graph_gives_rate_one(self) -> None:
        pages = [_page("https://example.com/solo", "Solo")]
        coverage = compute_switch_coverage(pages, [])
        assert coverage["0-switch"].total == 0
        assert coverage["0-switch"].rate == 1.0


# ---------- 受け入れ条件: 決済画面を含むパスが優先度「高」 ----------


class TestBusinessFlowPriority:
    def _auth_payment_pages(self) -> list[PageData]:
        login_field = FieldData(field_type="password", name="password", placeholder="", required=True)
        login_form = FormData(action="/login", method="post", fields=(login_field,))
        return [
            PageData(
                url="https://example.com/login",
                title="ログイン",
                headings=("ログイン",),
                links=("https://example.com/checkout",),
                forms=(login_form,),
                screenshot_path=None,
            ),
            PageData(
                url="https://example.com/checkout",
                title="決済",
                headings=("お支払い・決済",),
                links=(),
                forms=(),
                screenshot_path=None,
            ),
        ]

    def test_payment_path_labeled_high_priority(self) -> None:
        """決済画面を含むパスが優先度「高」でラベリングされる。"""
        pages = self._auth_payment_pages()
        paths = generate_transition_tests(pages, coverage="1-switch")
        url_types = classify_pages_for_flows(pages)
        flows = prioritize_business_flows(paths, url_types)

        assert flows
        assert all(flow.priority == "高" for flow in flows)
        payment_flows = [f for f in flows if "payment" in f.screen_types]
        assert payment_flows

    def test_flow_name_auto_generated(self) -> None:
        """フロー名（例: ログイン→決済）が自動命名される。"""
        pages = self._auth_payment_pages()
        paths = generate_transition_tests(pages, coverage="1-switch")
        flows = prioritize_business_flows(paths, classify_pages_for_flows(pages))

        assert any(flow.flow_name == "ログイン→決済" for flow in flows)

    def test_non_business_path_excluded(self) -> None:
        pages = _linear_pages()
        paths = generate_transition_tests(pages, coverage="1-switch")
        flows = prioritize_business_flows(paths, classify_pages_for_flows(pages))

        assert flows == []

    def test_flows_serializable(self) -> None:
        pages = self._auth_payment_pages()
        paths = generate_transition_tests(pages, coverage="1-switch")
        flows = prioritize_business_flows(paths, classify_pages_for_flows(pages))
        as_dict = business_flows_to_dict(flows)

        assert json.dumps(as_dict, ensure_ascii=False)
        assert all(item["priority"] == "高" for item in as_dict)


# ---------- spec_ts メタデータ JSON 併産 ----------


def _write_candidates(path: Path) -> None:
    payload = {
        "domain": "example.com",
        "candidates": [
            {
                "id": "PW-0001",
                "title": "画面表示スモーク",
                "trace_id": "P001",
                "automation_status": "auto",
                "steps": ["page.goto('https://example.com/login')"],
                "expected": "画面が表示される",
            },
            {
                "id": "PW-0002",
                "title": "画面遷移",
                "trace_id": "P001->P002",
                "automation_status": "auto",
                "steps": ["page.goto('https://example.com/login')", "遷移操作"],
                "expected": "遷移する",
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_report(path: Path) -> None:
    payload = {
        "meta": {},
        "screens": [
            {
                "page_id": "P001",
                "url": "https://example.com/login",
                "fingerprint": "fp-login",
                "fingerprint_version": 2,
            },
            {
                "page_id": "P002",
                "url": "https://example.com/home",
                "fingerprint": "fp-home",
                "fingerprint_version": 2,
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class TestSpecTsMetadata:
    def test_metadata_json_is_generated_with_fingerprint(self, tmp_path: Path) -> None:
        """各テストに test_id・page_id・fingerprint を含むメタデータ JSON が併産される。"""
        candidates_path = tmp_path / "playwright_candidates.json"
        report_path = tmp_path / "report.json"
        _write_candidates(candidates_path)
        _write_report(report_path)
        spec_path = tmp_path / "example.spec.ts"

        generate_spec_ts("example.com", candidates_path, spec_path)

        meta_path = metadata_file_path(spec_path)
        assert meta_path.exists()
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        assert metadata["domain"] == "example.com"
        tests = metadata["tests"]
        assert len(tests) == 2
        first = tests[0]
        assert first["test_id"] == "PW-0001"
        assert first["page_id"] == "P001"
        assert first["fingerprint"] == "fp-login"
        assert first["url"] == "https://example.com/login"
        # 遷移テストも先頭 page_id で紐づく
        assert tests[1]["page_id"] == "P001"

    def test_metadata_without_report_has_empty_fingerprint(self, tmp_path: Path) -> None:
        candidates_path = tmp_path / "playwright_candidates.json"
        _write_candidates(candidates_path)
        spec_path = tmp_path / "example.spec.ts"

        generate_spec_ts("example.com", candidates_path, spec_path)

        metadata = json.loads(metadata_file_path(spec_path).read_text(encoding="utf-8"))
        assert metadata["tests"][0]["fingerprint"] == ""
        assert metadata["tests"][0]["page_id"] == "P001"


# ---------- トレーサビリティのメタデータ照合 ----------


class TestTraceabilityMetadataMatching:
    def _report_data(self) -> dict:
        return {
            "screens": [
                {
                    "page_id": "P001",
                    "title": "ログイン",
                    "url": "https://example.com/login",
                    "fingerprint": "fp-login",
                }
            ]
        }

    def test_matrix_uses_fingerprint_matching(self) -> None:
        metadata = [
            {
                "test_id": "PW-0001",
                "page_id": "P001",
                "fingerprint": "fp-login",
                "url": "https://example.com/old-login",
            }
        ]
        matrix = build_matrix("example.com", self._report_data(), [], metadata)

        assert matrix.requirements[0].coverage == "covered"
        assert matrix.requirements[0].test_ids == ("PW-0001",)

    def test_matrix_falls_back_to_url_matching_without_metadata(self) -> None:
        candidates = [
            {
                "id": "TC-1",
                "steps": [{"url": "https://example.com/login"}],
            }
        ]
        matrix = build_matrix("example.com", self._report_data(), candidates, None)

        assert matrix.requirements[0].coverage == "covered"
        assert matrix.requirements[0].test_ids == ("TC-1",)


# ---------- report.html / report.json への統合表示 ----------


class TestReportIntegration:
    def test_html_report_shows_coverage_and_impact(self) -> None:
        from analyzer.html_analyzer import analyze_pages
        from generator.html_reporter import generate_html_report
        from graph.transition_graph import build_graph

        pages = analyze_pages(_linear_pages())
        graph = build_graph(pages)
        coverage = {
            "0-switch": {
                "coverage_type": "0-switch",
                "covered": 2,
                "total": 2,
                "rate": 1.0,
                "definition_source": COVERAGE_DEFINITION_SOURCE,
            }
        }
        flows = [{"flow_name": "ログイン→決済", "path_id": "TP001", "priority": "高"}]
        impact = {
            "total": 1,
            "breaking": 1,
            "warning": 0,
            "info": 0,
            "tests": [
                {
                    "test_id": "PW-0001",
                    "reason": "画面削除",
                    "page_url": "https://example.com/x",
                    "severity": "breaking",
                }
            ],
            "rerun_recommended": ["PW-0001"],
        }
        html_text = generate_html_report(
            pages,
            graph,
            [],
            "https://example.com/a",
            "graph TD;",
            transition_coverage=coverage,
            business_flows=flows,
            impact_report=impact,
        )
        assert "29119-4" in html_text
        assert "0-switch カバレッジ" in html_text
        assert "ログイン→決済" in html_text
        assert "再実行推奨テスト" in html_text
        assert "PW-0001" in html_text

    def test_json_report_includes_coverage_meta(self) -> None:
        from analyzer.html_analyzer import analyze_pages
        from generator.json_reporter import generate_json_report
        from graph.transition_graph import build_graph

        raw_pages = _linear_pages()
        pages = analyze_pages(raw_pages)
        paths = generate_transition_tests(raw_pages, coverage="1-switch")
        coverage = switch_coverage_to_dict(compute_switch_coverage(raw_pages, paths))
        report = json.loads(
            generate_json_report(
                pages,
                build_graph(pages),
                "https://example.com/a",
                transition_coverage=coverage,
                business_flows=[],
            )
        )
        assert report["meta"]["transition_coverage"]["0-switch"]["rate"] == 1.0
        assert "29119-4" in report["meta"]["transition_coverage"]["0-switch"]["definition_source"]
