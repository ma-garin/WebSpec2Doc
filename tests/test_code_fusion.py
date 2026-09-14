"""Code Fusion（ソースコード走査＋実測突合）のユニットテスト。

主張境界の確認も含む: 未到達ルートを欠陥と断定しないこと、
到達率を品質指標として扱わないことをテキストレベルで固定する。
"""

from __future__ import annotations

import json
from pathlib import Path

from analyzer.html_analyzer import analyze_pages
from crawler.page_crawler import PageData
from generator.code_fusion_reporter import (
    CODE_FUSION_JSON_NAME,
    CODE_FUSION_MD_NAME,
    build_code_fusion_markdown,
    build_code_fusion_payload,
    save_code_fusion_outputs,
)
from ingest.code_models import KIND_API, KIND_PAGE, CodeBundle, CodeEvidence, CodeRoute
from ingest.code_reader import scan_source_tree
from ingest.route_matcher import (
    REASON_API,
    REASON_AUTH,
    REASON_DUPLICATE,
    REASON_PARAM,
    effective_path,
    fuse_code,
    normalize_route_pattern,
    route_to_regex,
)


def _page(url: str, title: str) -> PageData:
    return PageData(
        url=url,
        title=title,
        headings=(title,),
        links=(),
        forms=(),
        screenshot_path=None,
    )


def _route(
    path: str,
    *,
    methods: tuple[str, ...] = ("GET",),
    kind: str = KIND_PAGE,
    prefix: str = "",
    file: str = "app.py",
    line: int = 1,
) -> CodeRoute:
    return CodeRoute(
        path=path,
        methods=methods,
        framework="flask",
        handler="view",
        kind=kind,
        prefix=prefix,
        evidence=CodeEvidence(file=file, line=line, quote=""),
    )


# ---------- パス正規化 ----------


class TestNormalize:
    def test_framework_param_notations(self) -> None:
        assert normalize_route_pattern("/r/<int:run_id>") == "/r/{}"
        assert normalize_route_pattern("/r/<run_id>") == "/r/{}"
        assert normalize_route_pattern("/r/:id") == "/r/{}"
        assert normalize_route_pattern("/r/[id]") == "/r/{}"
        assert normalize_route_pattern("/r/{id}") == "/r/{}"

    def test_trailing_slash_is_normalized_but_root_is_kept(self) -> None:
        assert normalize_route_pattern("/report/") == "/report"
        assert normalize_route_pattern("/") == "/"

    def test_regex_matches_concrete_url(self) -> None:
        regex = route_to_regex("/healing/reports/<report_id>")
        assert regex.fullmatch("/healing/reports/r123")
        assert not regex.fullmatch("/healing/reports/r123/print")

    def test_effective_path_joins_prefix(self) -> None:
        assert effective_path(_route("/items", prefix="/api")) == "/api/items"


# ---------- 突合 ----------


class TestFuseCode:
    def test_exact_match_wins_over_catch_all(self) -> None:
        """catch-all が exact 一致済みページを吸わない（到達率の水増し防止）。"""
        pages = analyze_pages([_page("https://example.com/team", "チーム")])
        bundle = CodeBundle(
            root=".",
            routes=(_route("/team"), _route("/<view_name>")),
            frameworks=("flask",),
        )
        result = fuse_code(pages, bundle)
        assert len(result.matches) == 1
        assert result.matches[0].method == "exact"
        assert result.matches[0].route.path == "/team"

    def test_specific_route_wins_over_catch_all(self) -> None:
        """定義順ではなく具体度順に当てる（catch-all の横取り防止）。"""
        pages = analyze_pages([_page("https://example.com/a/b/c", "詳細")])
        bundle = CodeBundle(
            root=".",
            routes=(_route("/<path:rest>"), _route("/a/b/<name>")),
            frameworks=("flask",),
        )
        result = fuse_code(pages, bundle)
        assert len(result.matches) == 1
        assert result.matches[0].route.path == "/a/b/<name>"

    def test_unreached_reasons_do_not_assert_defect(self) -> None:
        pages = analyze_pages([_page("https://example.com/", "ホーム")])
        bundle = CodeBundle(
            root=".",
            routes=(
                _route("/"),
                _route("/admin/console"),
                _route("/report/<run_id>"),
                _route("/items", methods=("POST",), kind=KIND_API, prefix="/api"),
            ),
            frameworks=("flask",),
        )
        result = fuse_code(pages, bundle)
        reasons = {u.route.path: u.reason for u in result.unreached}
        assert reasons["/admin/console"] == REASON_AUTH
        assert reasons["/report/<run_id>"] == REASON_PARAM
        assert reasons["/items"] == REASON_API
        for reason in reasons.values():
            assert "欠陥" not in reason
            assert "バグ" not in reason

    def test_duplicate_definition_is_labelled(self) -> None:
        pages = analyze_pages([_page("https://example.com/", "ホーム")])
        bundle = CodeBundle(
            root=".",
            routes=(_route("/", file="a.py"), _route("/", file="b.py")),
            frameworks=("flask",),
        )
        result = fuse_code(pages, bundle)
        assert len(result.matches) == 1
        assert [u.reason for u in result.unreached] == [REASON_DUPLICATE]

    def test_api_routes_are_excluded_from_ratio(self) -> None:
        pages = analyze_pages([_page("https://example.com/", "ホーム")])
        bundle = CodeBundle(
            root=".",
            routes=(_route("/"), _route("/x", kind=KIND_API, prefix="/api")),
            frameworks=("flask",),
        )
        result = fuse_code(pages, bundle)
        assert result.page_route_total == 1
        assert result.reached_ratio == 1.0

    def test_crawl_only_page_is_reported(self) -> None:
        pages = analyze_pages([_page("https://example.com/ghost", "謎")])
        bundle = CodeBundle(root=".", routes=(_route("/known"),), frameworks=("flask",))
        result = fuse_code(pages, bundle)
        assert len(result.crawl_only_page_ids) == 1
        assert not result.matches


# ---------- ソース走査 ----------


class TestScanSourceTree:
    def test_flask_routes_with_blueprint_prefix(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text(
            'from flask import Blueprint\n'
            'bp = Blueprint("api", __name__, url_prefix="/api/v1")\n'
            '@bp.route("/items", methods=["GET", "POST"])\n'
            'def items():\n'
            '    return ""\n',
            encoding="utf-8",
        )
        bundle = scan_source_tree(tmp_path)
        assert len(bundle.routes) == 1
        route = bundle.routes[0]
        assert route.path == "/items"
        assert route.prefix == "/api/v1"
        assert route.kind == KIND_API
        assert route.evidence is not None
        assert route.evidence.file == "app.py"

    def test_empty_tree_returns_no_routes(self, tmp_path: Path) -> None:
        bundle = scan_source_tree(tmp_path)
        assert bundle.routes == ()

    def test_self_scan_finds_this_repository_routes(self) -> None:
        """実データ検証: 本リポジトリ自身の Flask ルートが取れる。"""
        bundle = scan_source_tree(Path(__file__).resolve().parents[1])
        assert "flask" in bundle.frameworks
        page_routes = [r for r in bundle.routes if r.kind == KIND_PAGE]
        assert len(page_routes) > 20
        assert any(r.path == "/usage" for r in page_routes)


# ---------- レポート ----------


class TestReporter:
    def _result(self, tmp_path: Path):
        pages = analyze_pages([_page("https://example.com/", "ホーム")])
        bundle = CodeBundle(
            root=str(tmp_path),
            routes=(_route("/"), _route("/admin/console"), _route("/x", kind=KIND_API)),
            source_files=("app.py",),
            frameworks=("flask",),
        )
        return fuse_code(pages, bundle), bundle

    def test_markdown_states_claim_boundary(self, tmp_path: Path) -> None:
        result, bundle = self._result(tmp_path)
        markdown = build_code_fusion_markdown(result, bundle)
        assert "品質指標" in markdown
        assert "## 未到達ルート" in markdown
        # 未到達節がサマリーより後・対応節より前にあること（作業リストが主役）
        assert markdown.index("## 未到達ルート") < markdown.index("## 対応が取れたルート")

    def test_pipe_in_path_is_escaped(self, tmp_path: Path) -> None:
        bundle = CodeBundle(root=".", routes=(_route("/we|rd"),), frameworks=("flask",))
        result = fuse_code([], bundle)
        markdown = build_code_fusion_markdown(result, bundle)
        assert "/we\\|rd" in markdown

    def test_payload_totals_are_consistent(self, tmp_path: Path) -> None:
        result, bundle = self._result(tmp_path)
        payload = build_code_fusion_payload(result, bundle)
        summary = payload["summary"]
        assert summary["matched"] + summary["unreached"] == len(bundle.routes)
        assert 0.0 <= summary["reached_ratio"] <= 1.0

    def test_save_creates_both_files(self, tmp_path: Path) -> None:
        result, bundle = self._result(tmp_path)
        out = tmp_path / "out" / "nested"
        save_code_fusion_outputs(result, bundle, out)
        assert (out / CODE_FUSION_MD_NAME).is_file()
        loaded = json.loads((out / CODE_FUSION_JSON_NAME).read_text(encoding="utf-8"))
        assert loaded["frameworks"] == ["flask"]
