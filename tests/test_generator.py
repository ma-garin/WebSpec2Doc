"""mermaid_generator.py / markdown_generator.py / transition_graph.py のユニットテスト"""

from __future__ import annotations

from analyzer.html_analyzer import analyze_pages
from crawler.page_crawler import PageData
from generator.markdown_generator import generate_forms_markdown, generate_screens_markdown
from generator.mermaid_generator import generate_mermaid
from graph.transition_graph import build_graph

# ---------- build_graph ----------


class TestBuildGraph:
    def test_nodes_created_for_each_page(self, page_top: PageData, page_about: PageData) -> None:
        analyzed = analyze_pages([page_top, page_about])
        graph = build_graph(analyzed)
        assert len(graph.nodes) == 2

    def test_node_has_required_attributes(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        node_data = graph.nodes["P001"]
        assert "url" in node_data
        assert "title" in node_data
        assert "page_id" in node_data
        assert "forms_count" in node_data
        assert "fields_count" in node_data

    def test_edges_created_for_links(self, page_top: PageData, page_about: PageData) -> None:
        analyzed = analyze_pages([page_top, page_about])
        graph = build_graph(analyzed)
        # top → about のエッジが存在するはず
        assert graph.has_edge("P001", "P002")

    def test_no_edges_for_unvisited_links(self, page_top: PageData) -> None:
        # page_top は about/contact にリンクするが about/contact はクロール済みリストにない
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        assert len(graph.edges) == 0

    def test_forms_count_in_node(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        assert graph.nodes["P001"]["forms_count"] == 1

    def test_fields_count_in_node(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        assert graph.nodes["P001"]["fields_count"] == 1

    def test_empty_pages(self) -> None:
        graph = build_graph([])
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0


# ---------- generate_mermaid ----------


class TestGenerateMermaid:
    def test_starts_with_graph_lr(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_mermaid(graph, analyzed)
        assert result.startswith("graph LR")

    def test_contains_page_ids(self, page_top: PageData, page_about: PageData) -> None:
        analyzed = analyze_pages([page_top, page_about])
        graph = build_graph(analyzed)
        result = generate_mermaid(graph, analyzed)
        assert "P001" in result
        assert "P002" in result

    def test_contains_edge_arrow(self, page_top: PageData, page_about: PageData) -> None:
        analyzed = analyze_pages([page_top, page_about])
        graph = build_graph(analyzed)
        result = generate_mermaid(graph, analyzed)
        assert "-->" in result

    def test_contains_url_path(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_mermaid(graph, analyzed)
        assert "/" in result

    def test_ends_with_newline(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_mermaid(graph, analyzed)
        assert result.endswith("\n")

    def test_empty_graph(self) -> None:
        graph = build_graph([])
        result = generate_mermaid(graph, [])
        assert result.startswith("graph LR")

    def test_special_chars_escaped_in_label(self) -> None:
        from crawler.page_crawler import PageData as PD

        page = PD(
            url='https://example.com/path"with"quotes',
            title='Title "quoted"',
            headings=(),
            links=(),
            forms=(),
            screenshot_path=None,
        )
        analyzed = analyze_pages([page])
        graph = build_graph(analyzed)
        result = generate_mermaid(graph, analyzed)
        # ダブルクォートがシングルクォートにエスケープされていること
        assert '"' not in result.split("graph LR")[1] or "'" in result


# ---------- generate_screens_markdown ----------


class TestGenerateScreensMarkdown:
    def test_contains_header(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_screens_markdown(analyzed, graph, page_top.url)
        assert "# 画面一覧" in result

    def test_contains_target_url(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_screens_markdown(analyzed, graph, page_top.url)
        assert page_top.url in result

    def test_contains_page_id(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_screens_markdown(analyzed, graph, page_top.url)
        assert "P001" in result

    def test_table_header_present(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_screens_markdown(analyzed, graph, page_top.url)
        assert "画面ID" in result
        assert "URL" in result
        assert "タイトル" in result

    def test_page_title_in_output(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_screens_markdown(analyzed, graph, page_top.url)
        assert "テストサイト - トップ" in result

    def test_transition_destinations(self, page_top: PageData, page_about: PageData) -> None:
        analyzed = analyze_pages([page_top, page_about])
        graph = build_graph(analyzed)
        result = generate_screens_markdown(analyzed, graph, page_top.url)
        # P001 の遷移先に P002 が含まれること
        assert "P002" in result

    def test_ends_with_newline(self, page_top: PageData) -> None:
        analyzed = analyze_pages([page_top])
        graph = build_graph(analyzed)
        result = generate_screens_markdown(analyzed, graph, page_top.url)
        assert result.endswith("\n")

    def test_pipe_in_title_escaped(self) -> None:
        page = PageData(
            url="https://example.com/",
            title="Title | with | pipes",
            headings=(),
            links=(),
            forms=(),
            screenshot_path=None,
        )
        analyzed = analyze_pages([page])
        graph = build_graph(analyzed)
        result = generate_screens_markdown(analyzed, graph, page.url)
        # Markdown テーブルが壊れないようにパイプがエスケープされること
        lines = [row for row in result.splitlines() if "Title" in row]
        assert all("\\|" in line or line.count("|") <= 7 for line in lines)


# ---------- generate_forms_markdown ----------


class TestGenerateFormsMd:
    def test_contains_header(self, page_top: PageData) -> None:
        from analyzer.form_analyzer import summarize_forms

        analyzed = analyze_pages([page_top])
        summary = summarize_forms(analyzed)
        result = generate_forms_markdown(summary)
        assert "# フォーム一覧" in result

    def test_contains_field_name(self, page_top: PageData) -> None:
        from analyzer.form_analyzer import summarize_forms

        analyzed = analyze_pages([page_top])
        summary = summarize_forms(analyzed)
        result = generate_forms_markdown(summary)
        assert "q" in result

    def test_required_shown_as_yes(self, page_contact: PageData) -> None:
        from analyzer.form_analyzer import summarize_forms

        analyzed = analyze_pages([page_contact])
        summary = summarize_forms(analyzed)
        result = generate_forms_markdown(summary)
        assert "Yes" in result

    def test_optional_shown_as_no(self, page_top: PageData) -> None:
        from analyzer.form_analyzer import summarize_forms

        analyzed = analyze_pages([page_top])
        summary = summarize_forms(analyzed)
        result = generate_forms_markdown(summary)
        assert "No" in result

    def test_empty_summary(self) -> None:
        result = generate_forms_markdown([])
        assert "# フォーム一覧" in result
        assert result.endswith("\n")
