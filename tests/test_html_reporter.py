"""html_reporter.py のスモークテスト。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import html as html_module

import networkx as nx

from analyzer.html_analyzer import AnalyzedPage, analyze_pages
from crawler.page_crawler import FieldData, FormData, PageData
from generator.coverage_gap import CoverageGap
from generator.html_reporter import generate_html_report
from generator.test_design import TestDesignParams as DesignParams
from generator.test_design import build_test_design


def _make_analyzed_page(
    url: str = "https://example.com/",
    title: str = "Test Page",
    forms: tuple[FormData, ...] = (),
) -> AnalyzedPage:
    """テスト用 AnalyzedPage を生成するヘルパー。"""
    page_data = PageData(
        url=url,
        title=title,
        headings=("Test Heading",),
        links=(),
        forms=forms,
        screenshot_path=None,
    )
    analyzed = analyze_pages([page_data])
    return analyzed[0]


def _empty_graph() -> nx.DiGraph:
    return nx.DiGraph()


def test_html_reporter_creates_output_file(tmp_path: Path) -> None:
    """html_reporter が HTML 文字列を返す基本スモークテスト。"""
    analyzed = [_make_analyzed_page()]
    graph = _empty_graph()
    graph.add_node(
        "P001",
        url="https://example.com/",
        title="Test Page",
        page_id="P001",
        forms_count=0,
        fields_count=0,
    )

    result = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content="graph LR\n  P001\n",
    )

    assert isinstance(result, str)
    assert len(result) > 0

    # ファイルに書き出して存在確認
    out = tmp_path / "report.html"
    out.write_text(result, encoding="utf-8")
    assert out.exists()
    assert out.stat().st_size > 0


class TestCoverageGapSection:
    """「カバレッジと未確認領域」節（AC-5・AC-8）。"""

    def _generate(self, coverage_gaps: tuple[CoverageGap, ...] = ()) -> str:
        analyzed = [_make_analyzed_page()]
        graph = _empty_graph()
        graph.add_node(
            "P001",
            url="https://example.com/",
            title="Test Page",
            page_id="P001",
            forms_count=0,
            fields_count=0,
        )
        return generate_html_report(
            pages=analyzed,
            graph=graph,
            form_summary=[],
            target_url="https://example.com/",
            mermaid_content="graph LR\n  P001\n",
            coverage_gaps=coverage_gaps,
        )

    def test_gap_section_absent_when_empty(self) -> None:
        """test_gap_section_absent_when_empty: ギャップ 0 件 → 既存出力と同一
        （report.html に節が無い・AC-8）。"""
        result = self._generate(())
        assert 'id="coverage-gaps"' not in result
        assert "カバレッジと未確認領域" not in result

    def test_gap_section_present_with_gaps(self) -> None:
        gaps = (
            CoverageGap(
                kind="robots_skipped",
                subject="https://example.com/admin",
                reason="robots.txt により対象外（未確認）",
            ),
        )
        result = self._generate(gaps)
        assert 'id="coverage-gaps"' in result
        assert "カバレッジと未確認領域" in result
        assert "https://example.com/admin" in result
        assert "未確認" in result
        # 「問題なし」と断定しないこと（evidence-only 原則）: 否定形でのみ言及可
        assert "問題なし」を意味しません" in result
        assert "<b>問題なし</b>" not in result


def test_sidebar_nav_shows_coverage_and_impact_when_present() -> None:
    """カバレッジ・差分影響セクションがある場合、サイドバーにナビが追加される。"""
    analyzed = [_make_analyzed_page()]
    graph = _empty_graph()
    graph.add_node("P001", url="https://example.com/", title="T", page_id="P001")
    coverage = {
        "0-switch": {
            "coverage_type": "0-switch",
            "covered": 1,
            "total": 1,
            "rate": 1.0,
            "definition_source": "ISO/IEC/IEEE 29119-4",
        }
    }
    impact = {
        "total": 0,
        "breaking": 0,
        "warning": 0,
        "info": 0,
        "tests": [],
        "rerun_recommended": [],
    }

    html_text = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content="graph LR\n P001\n",
        transition_coverage=coverage,
        impact_report=impact,
    )
    assert '<a href="#coverage" class="nav-item">遷移テストカバレッジ</a>' in html_text
    assert '<a href="#impact" class="nav-item">差分影響・再実行推奨</a>' in html_text


def test_sidebar_nav_omits_coverage_and_impact_when_absent() -> None:
    """カバレッジ・差分影響が無い場合、サイドバーにナビは出ない。"""
    analyzed = [_make_analyzed_page()]
    graph = _empty_graph()
    graph.add_node("P001", url="https://example.com/", title="T", page_id="P001")

    html_text = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content="graph LR\n P001\n",
    )
    assert 'href="#coverage"' not in html_text
    assert 'href="#impact"' not in html_text


def test_html_reporter_returns_valid_html_structure(tmp_path: Path) -> None:
    """生成された HTML が基本的な構造タグを持つ。"""
    analyzed = [_make_analyzed_page()]
    graph = _empty_graph()

    result = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content="graph LR\n",
    )

    assert "<!doctype html>" in result.lower() or "<!DOCTYPE html>" in result
    assert "<html" in result
    assert "</html>" in result
    assert "<body" in result
    assert "</body>" in result


def test_html_reporter_contains_page_id(tmp_path: Path) -> None:
    """生成 HTML に画面 ID (P001) が含まれる。"""
    analyzed = [_make_analyzed_page()]
    graph = _empty_graph()

    result = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content="graph LR\n",
    )

    assert "P001" in result


def test_html_reporter_escapes_xss_in_title(tmp_path: Path) -> None:
    """ページタイトルの XSS 文字が html.escape() でエスケープされる。"""
    xss_title = "<script>alert(1)</script>"
    analyzed = [_make_analyzed_page(title=xss_title)]
    graph = _empty_graph()

    result = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content="graph LR\n",
    )

    # リテラルの <script> タグがそのまま出力されてはいけない
    assert "<script>alert(1)</script>" not in result
    # エスケープ済み文字列が含まれること
    assert html_module.escape(xss_title) in result


def test_html_reporter_escapes_xss_in_target_url(tmp_path: Path) -> None:
    """target_url の XSS 文字がエスケープされる。"""
    xss_url = 'https://example.com/"><script>alert(1)</script>'
    analyzed = [_make_analyzed_page(url="https://example.com/")]
    graph = _empty_graph()

    result = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url=xss_url,
        mermaid_content="graph LR\n",
    )

    # 生の <script> タグが注入されていないこと
    assert '"><script>alert(1)</script>' not in result


def test_html_reporter_with_form(tmp_path: Path) -> None:
    """フォームを持つページの HTML レポートにフォーム情報が含まれる。"""
    field = FieldData(
        field_type="text",
        name="username",
        placeholder="ユーザー名",
        required=True,
    )
    form = FormData(action="/login", method="post", fields=(field,))
    analyzed = [
        _make_analyzed_page(url="https://example.com/login", title="ログイン", forms=(form,))
    ]
    graph = _empty_graph()

    result = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content="graph LR\n",
    )

    assert "username" in result
    assert "/login" in result


def test_html_reporter_multiple_pages(tmp_path: Path) -> None:
    """複数ページのレポートに全ページの ID が含まれる。"""
    page1 = PageData(
        url="https://example.com/",
        title="Home",
        headings=(),
        links=("https://example.com/about",),
        forms=(),
        screenshot_path=None,
    )
    page2 = PageData(
        url="https://example.com/about",
        title="About",
        headings=(),
        links=(),
        forms=(),
        screenshot_path=None,
    )
    analyzed = analyze_pages([page1, page2])

    graph = nx.DiGraph()
    graph.add_node("P001")
    graph.add_node("P002")
    graph.add_edge("P001", "P002")

    result = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content="graph LR\n  P001-->P002\n",
    )

    assert "P001" in result
    assert "P002" in result


# =========================================================================
# B-1: Mermaid をアプリ内で描画（R3-18a）
# =========================================================================
def test_mermaid_script_uses_local_vendor() -> None:
    """`_mermaid_script()` はアプリ内では同梱版 static/vendor/mermaid/mermaid.min.js を
    'self' から読み込み、securityLevel:'strict' で初期化する。
    static/vendor/mermaid.min.js 本体の有無に依存しないよう、生成HTML文字列自体を
    検証する（ネットワーク遮断環境でも実行可能なテスト）。"""
    analyzed = [_make_analyzed_page()]
    graph = _empty_graph()
    graph.add_node("P001", url="https://example.com/", title="T", page_id="P001")

    result = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content="graph LR\n  P001\n",
    )

    assert '<script src="/static/vendor/mermaid/mermaid.min.js"></script>' in result
    assert "securityLevel:'strict'" in result
    # CSP 変更禁止（規約0-6）: cdn.jsdelivr.net への直接 <script src> 埋め込みは行わない
    # （フォールバックは window.mermaid 未定義時のみ動的に document.head へ追加する）。
    assert '<script src="https://cdn.jsdelivr.net' not in result


# =========================================================================
# B-2: 具体的テスト設計の注入（R3-18b）
# =========================================================================
def _bva_field(name: str, **kw: object) -> dict:
    base: dict = {
        "name": name,
        "field_type": "text",
        "required": False,
        "maxlength": None,
        "minlength": None,
        "min_value": None,
        "max_value": None,
        "pattern": None,
        "options": [],
    }
    base.update(kw)
    return base


def _td_screen(
    page_id: str, *, fields: list[dict] | None = None, to: list[str] | None = None
) -> dict:
    forms = [{"action": "/submit", "method": "post", "fields": fields}] if fields else []
    return {
        "page_id": page_id,
        "title": f"画面 {page_id}",
        "buttons": [],
        "forms": forms,
        "transitions": {"to": to or [], "from": []},
    }


def _generate_with_test_design(test_design) -> str:
    analyzed = [_make_analyzed_page()]
    graph = _empty_graph()
    graph.add_node("P001", url="https://example.com/", title="T", page_id="P001")
    return generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content="graph LR\n  P001\n",
        test_design=test_design,
    )


class TestTestDesignSection:
    def test_test_design_section_renders_dt_truth_table(self) -> None:
        """必須2条件の合成reportでY/N表とルール4列（2^2）が出ること。"""
        report = {
            "screens": [
                _td_screen(
                    "P001",
                    fields=[
                        _bva_field("card", required=True),
                        _bva_field("cvv", required=True),
                    ],
                )
            ]
        }
        design = build_test_design(report, DesignParams(enabled_techniques=("dt",)))
        result = _generate_with_test_design(design)

        assert 'id="test-design"' in result
        assert "デシジョンテーブル" in result
        for i in range(1, 5):
            assert f"ルール{i}" in result
        assert "期待アクション" in result
        assert "<td>Y</td>" in result
        assert "<td>N</td>" in result
        assert "送信成功" in result

    def test_test_design_section_renders_bva_with_evidence_badge(self) -> None:
        """maxlength=100 のフィールドで境界値と確信度1.0バッジが出ること。"""
        report = {
            "screens": [
                _td_screen("P001", fields=[_bva_field("comment", maxlength=100)]),
            ]
        }
        design = build_test_design(report, DesignParams(enabled_techniques=("bva",)))
        result = _generate_with_test_design(design)

        assert "境界値分析（BVA）" in result
        assert "100文字" in result
        assert "101文字" in result
        assert "確信度1.0" in result

    def test_test_design_none_keeps_backward_compat(self) -> None:
        """test_design=None（既定）でも既存セクション構成は不変で、
        テスト設計節には「データなし」の明記のみが追加される。"""
        analyzed = [_make_analyzed_page()]
        graph = _empty_graph()
        graph.add_node("P001", url="https://example.com/", title="T", page_id="P001")

        result = generate_html_report(
            pages=analyzed,
            graph=graph,
            form_summary=[],
            target_url="https://example.com/",
            mermaid_content="graph LR\n  P001\n",
        )

        # 既存セクション・ナビは従来どおり存在する
        assert '<a href="#summary" class="nav-item">サマリー</a>' in result
        assert '<section class="block" id="screens">' in result
        # 新設のテスト設計節は「データなし」で明記される（捏造しない）
        assert 'id="test-design"' in result
        assert "テスト設計データなし" in result
        assert "--format json" in result

    def test_screen_card_links_to_test_design_only_when_present(self) -> None:
        """テスト設計が生成された画面にのみ「テスト設計を見る」リンクを出す
        （存在しないアンカーへリンクしない＝捏造禁止）。"""
        report = {
            "screens": [
                _td_screen(
                    "P001", fields=[_bva_field("a", required=True), _bva_field("b", required=True)]
                ),
            ]
        }
        design = build_test_design(report, DesignParams(enabled_techniques=("dt",)))
        result = _generate_with_test_design(design)
        assert '<a href="#td-P001">テスト設計を見る</a>' in result

        result_none = _generate_with_test_design(None)
        assert "テスト設計を見る" not in result_none
