"""SPEC-1-3: RFP要件トレーサビリティマトリクスのテスト。

対象:
    - src/ingest/req_tracer.py::trace_requirements（要件→画面→テストケースの連鎖）
    - src/generator/trace_reporter.py::trace_to_dict / save_trace_outputs
    - web/routes/traceability.py::api_traceability_matrix の document_requirements 追加
"""

from __future__ import annotations

import json
from pathlib import Path

from analyzer.html_analyzer import analyze_pages
from crawler.page_crawler import FieldData, FormData, PageData, SourceEvidence
from generator.trace_reporter import (
    TRACE_JSON_NAME,
    TRACE_MD_NAME,
    save_trace_outputs,
    trace_to_dict,
)
from ingest.loader import load_reference_documents
from ingest.matcher import fuse
from ingest.models import DocumentBundle, DocumentedRequirement, DocumentedScreen, DocumentEvidence
from ingest.req_tracer import trace_requirements

# ---------- 共通フィクスチャ ----------


def _field(name: str, required: bool = False) -> FieldData:
    return FieldData(
        field_type="text",
        name=name,
        placeholder="",
        required=required,
        evidence=SourceEvidence(selector=f"[name='{name}']"),
    )


def _page(url: str, title: str, fields: tuple[FieldData, ...] = ()) -> PageData:
    forms = (FormData(action="/submit", method="post", fields=fields),) if fields else ()
    return PageData(
        url=url, title=title, headings=(title,), links=(), forms=forms, screenshot_path=None
    )


def _requirement(req_id: str, title: str, description: str = "") -> DocumentedRequirement:
    return DocumentedRequirement(
        req_id=req_id,
        title=title,
        description=description,
        evidence=DocumentEvidence(file="rfp.md", location="line 3", quote=title),
    )


def _empty_bundle(requirements: tuple[DocumentedRequirement, ...]) -> DocumentBundle:
    return DocumentBundle(
        screens=(), fields=(), source_files=("rfp.md",), requirements=requirements
    )


# ---------- AC-3: 要件→画面のマッピング ----------


class TestRequirementScreenMatching:
    def test_requirement_mapped_to_screen(self) -> None:
        """AC-3: 要件文が画面タイトルを内包する場合、score>=0.6 でその画面に対応づく。"""
        pages = analyze_pages(
            [
                _page(
                    "https://example.com/search",
                    "商品検索",
                    fields=(_field("keyword", required=True),),
                )
            ]
        )
        requirement = _requirement("REQ-001", "商品検索ができること")
        bundle = _empty_bundle((requirement,))
        result = fuse(pages, bundle)

        traces = trace_requirements(bundle, result, pages, [])

        assert len(traces) == 1
        trace = traces[0]
        assert trace.page_id == pages[0].page_id
        assert trace.page_url == "https://example.com/search"
        assert trace.match_score >= 0.6
        assert trace.match_method == "name"

    def test_official_name_priority(self) -> None:
        """official_names（文書上の正式名称）が一致する場合 method="official_name" になる。"""
        pages = analyze_pages([_page("https://example.com/search", "SRCH-001", fields=())])
        screen = DocumentedScreen(screen_id="S1", name="商品検索", url_hint="/search")
        requirement = _requirement("REQ-001", "商品検索ができること")
        bundle = DocumentBundle(
            screens=(screen,), fields=(), source_files=("rfp.md",), requirements=(requirement,)
        )
        result = fuse(pages, bundle)
        assert result.official_names[pages[0].page_id] == "商品検索"

        traces = trace_requirements(bundle, result, pages, [])

        trace = traces[0]
        assert trace.match_method == "official_name"
        assert trace.match_score == 1.0


# ---------- AC-4: テストケースの紐づけ ----------


class TestTestCaseLinking:
    def test_test_ids_linked(self) -> None:
        """AC-4: playwright_candidates.json の該当 URL の candidate id が紐づき covered になる。"""
        pages = analyze_pages([_page("https://example.com/search", "商品検索", fields=())])
        requirement = _requirement("REQ-001", "商品検索ができること")
        bundle = _empty_bundle((requirement,))
        result = fuse(pages, bundle)
        candidates = [{"id": "TC-001", "steps": [{"url": "https://example.com/search"}]}]

        traces = trace_requirements(bundle, result, pages, candidates)

        trace = traces[0]
        assert trace.status == "covered"
        assert trace.test_condition_count == 0
        assert trace.candidate_ids == ("TC-001",)

    def test_condition_count_from_fields(self) -> None:
        """candidates が無くても、フィールドのテスト条件件数があれば covered になる。"""
        pages = analyze_pages(
            [
                _page(
                    "https://example.com/search",
                    "商品検索",
                    fields=(_field("keyword", required=True),),
                )
            ]
        )
        requirement = _requirement("REQ-001", "商品検索ができること")
        bundle = _empty_bundle((requirement,))
        result = fuse(pages, bundle)

        traces = trace_requirements(bundle, result, pages, [])

        trace = traces[0]
        assert trace.status == "covered"
        assert trace.test_condition_count > 0
        assert trace.candidate_ids == ()

    def test_screen_only_without_tests(self) -> None:
        """対応画面はあるがフィールド・candidateどちらも無ければ screen_only。"""
        pages = analyze_pages([_page("https://example.com/search", "商品検索", fields=())])
        requirement = _requirement("REQ-001", "商品検索ができること")
        bundle = _empty_bundle((requirement,))
        result = fuse(pages, bundle)

        traces = trace_requirements(bundle, result, pages, [])

        assert traces[0].status == "screen_only"


# ---------- AC-5: 未実装疑い ----------


class TestUnimplementedSuspect:
    def test_unmatched_requirement_suspect(self) -> None:
        """AC-5 / §8: しきい値未満は unimplemented_suspect となり、近い画面が併記される。"""
        pages = analyze_pages([_page("https://example.com/history", "ポイント履歴", fields=())])
        requirement = _requirement("REQ-999", "ポイント付与ができること")
        bundle = _empty_bundle((requirement,))
        result = fuse(pages, bundle)

        traces = trace_requirements(bundle, result, pages, [])

        trace = traces[0]
        assert trace.status == "unimplemented_suspect"
        assert trace.page_id == ""
        assert trace.near_page_title == "ポイント履歴"
        assert 0 < trace.near_score < 0.6

    def test_md_contains_disclaimer_for_suspects(self, tmp_path: Path) -> None:
        pages = analyze_pages([_page("https://example.com/history", "ポイント履歴", fields=())])
        requirement = _requirement("REQ-999", "ポイント付与ができること")
        bundle = _empty_bundle((requirement,))
        result = fuse(pages, bundle)
        traces = trace_requirements(bundle, result, pages, [])

        save_trace_outputs(traces, bundle, tmp_path)

        markdown = (tmp_path / TRACE_MD_NAME).read_text(encoding="utf-8")
        assert "未実装疑い" in markdown
        assert "断定" in markdown
        assert "ポイント履歴" in markdown

    def test_md_escapes_pipe_in_requirement_title(self, tmp_path: Path) -> None:
        """要件名に | が含まれてもマトリクス表が崩れない（セルをエスケープする・回帰）。"""
        pages = analyze_pages([_page("https://example.com/x", "X画面", fields=())])
        # 文書由来の要件名に区切り文字 | を含む
        requirement = _requirement("REQ-001", "ログイン|会員登録画面が使えること")
        bundle = _empty_bundle((requirement,))
        result = fuse(pages, bundle)
        traces = trace_requirements(bundle, result, pages, [])

        save_trace_outputs(traces, bundle, tmp_path)

        markdown = (tmp_path / TRACE_MD_NAME).read_text(encoding="utf-8")
        # 生の | ではなくエスケープされた \| で埋め込まれる（列ずれを防ぐ）
        assert "ログイン\\|会員登録画面が使えること" in markdown
        # マトリクス表の各データ行は列数（6 列 = 7 本の |）を保つ
        matrix_rows = [line for line in markdown.splitlines() if line.startswith("| REQ-001")]
        assert matrix_rows
        assert all(row.count("|") - row.count("\\|") == 7 for row in matrix_rows)


# ---------- AC-6: 要件が無い場合はオプトイン（出力しない） ----------


class TestOptInOutput:
    def test_no_requirements_no_output(self, tmp_path: Path) -> None:
        bundle = DocumentBundle(screens=(), fields=(), source_files=(), requirements=())
        result = fuse([], bundle)

        traces = trace_requirements(bundle, result, [], [])

        assert traces == ()
        save_trace_outputs(traces, bundle, tmp_path)
        assert not (tmp_path / TRACE_JSON_NAME).exists()
        assert not (tmp_path / TRACE_MD_NAME).exists()


# ---------- req_id 重複 ----------


class TestDuplicateReqId:
    def test_duplicate_req_id_warned_and_both_kept(self, caplog) -> None:
        pages = analyze_pages([_page("https://example.com/a", "A画面", fields=())])
        req1 = _requirement("REQ-001", "A画面が使えること")
        req2 = _requirement("REQ-001", "A画面の別要件")
        bundle = _empty_bundle((req1, req2))
        result = fuse(pages, bundle)

        with caplog.at_level("WARNING"):
            traces = trace_requirements(bundle, result, pages, [])

        assert len(traces) == 2
        assert "重複" in caplog.text
        data = trace_to_dict(traces, bundle)
        assert all(r["duplicate_req_id"] for r in data["requirements"])


# ---------- 結合テスト（6-2） ----------


class TestIntegrationPipeline:
    def test_full_pipeline_produces_both_statuses(self, tmp_path: Path) -> None:
        """要件表→load_reference_documents→fuse→trace_requirements→save_trace_outputs の通し。"""
        md = tmp_path / "rfp.md"
        md.write_text(
            "\n".join(
                [
                    "| 要件ID | 要件名 |",
                    "|---|---|",
                    "| REQ-A01 | 商品検索ができること |",
                    "| REQ-A02 | 外部会計システム連携ができること |",
                ]
            ),
            encoding="utf-8",
        )
        bundle = load_reference_documents([md])
        assert len(bundle.requirements) == 2

        pages = analyze_pages(
            [
                _page(
                    "https://example.com/search",
                    "商品検索",
                    fields=(_field("keyword", required=True),),
                )
            ]
        )
        result = fuse(pages, bundle)
        traces = trace_requirements(bundle, result, pages, [])
        out_dir = tmp_path / "out"
        save_trace_outputs(traces, bundle, out_dir)

        assert (out_dir / TRACE_JSON_NAME).exists()
        data = json.loads((out_dir / TRACE_JSON_NAME).read_text(encoding="utf-8"))
        statuses = {r["status"] for r in data["requirements"]}
        assert "covered" in statuses
        assert "unimplemented_suspect" in statuses

        markdown = (out_dir / TRACE_MD_NAME).read_text(encoding="utf-8")
        assert "トレーサビリティマトリクス" in markdown
        assert "未実装疑い" in markdown


# ---------- AC-7: /traceability/matrix の追加キー ----------


class TestApiAdditiveKey:
    def test_api_additive_key(self, tmp_path: Path, monkeypatch) -> None:
        import app as appmod
        import web.routes.traceability as traceability_mod

        monkeypatch.setattr(traceability_mod, "OUTPUT_DIR", tmp_path)
        domain_dir = tmp_path / "example.com"
        domain_dir.mkdir(parents=True)
        (domain_dir / "report.json").write_text(
            json.dumps({"screens": [{"url": "https://example.com/", "title": "トップ"}]}),
            encoding="utf-8",
        )
        client = appmod.app.test_client()

        resp_without = client.get("/traceability/matrix?domain=example.com")
        data_without = resp_without.get_json()
        assert "document_requirements" not in data_without

        trace_payload = {
            "meta": {"total_requirements": 1, "covered": 1},
            "requirements": [{"req_id": "REQ-001"}],
        }
        (domain_dir / "requirement_trace.json").write_text(
            json.dumps(trace_payload), encoding="utf-8"
        )

        resp_with = client.get("/traceability/matrix?domain=example.com")
        data_with = resp_with.get_json()

        assert data_with["document_requirements"] == trace_payload
        # 既存キーは変わらない（オプトイン追加のみ）
        for key in data_without:
            assert data_with[key] == data_without[key]

    def test_api_no_trace_file_matches_current_response(self, tmp_path: Path, monkeypatch) -> None:
        """requirement_trace.json が無い場合は現行応答と完全一致する（AC-7）。"""
        import app as appmod
        import web.routes.traceability as traceability_mod

        monkeypatch.setattr(traceability_mod, "OUTPUT_DIR", tmp_path)
        domain_dir = tmp_path / "example.com"
        domain_dir.mkdir(parents=True)
        (domain_dir / "report.json").write_text(
            json.dumps({"screens": [{"url": "https://example.com/", "title": "トップ"}]}),
            encoding="utf-8",
        )
        client = appmod.app.test_client()

        resp = client.get("/traceability/matrix?domain=example.com")
        data = resp.get_json()
        assert "document_requirements" not in data
        assert data["total_requirements"] == 1
