"""成果物（md / html / json / excel / pdf）の書き出し。

src/main.py から分離した。クロール結果を受け取ってファイルへ落とす責務だけを持ち、
クロールや差分計算は行わない。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import networkx as nx

from analyzer.html_analyzer import AnalyzedPage
from crawler.page_crawler import DEFAULT_DEPTH, DEFAULT_MAX_PAGES
from crawler.url_safety import domain_key_from_url
from generator.excel_reporter import save_excel_output as _save_excel_output
from generator.markdown_generator import (
    generate_forms_markdown,
    generate_screens_markdown,
)
from generator.mermaid_generator import generate_mermaid

if TYPE_CHECKING:
    from generator.test_design import TestDesign

logger = logging.getLogger(__name__)

FORMAT_SEPARATOR = ","
SUPPORTED_FORMATS = frozenset({"md", "html", "excel", "pdf", "json"})
PDF_FILE_NAME = "report.pdf"
JSON_REPORT_FILE_NAME = "report.json"


def save_outputs(
    pages: list[AnalyzedPage],
    graph: nx.DiGraph,
    form_summary: list[dict[str, object]],
    output_dir: Path,
    formats: Sequence[str],
    llm_insights: object | None = None,
    crawl_depth: int = DEFAULT_DEPTH,
    crawl_max_pages: int = DEFAULT_MAX_PAGES,
    crawled_at: str = "",
    transition_coverage: dict[str, dict] | None = None,
    business_flows: list[dict] | None = None,
    impact_report: dict | None = None,
    official_names: dict[str, str] | None = None,
    exploration_coverage: dict[str, object] | None = None,
    rule_conditions: dict[tuple[str, str], tuple] | None = None,
    ux_review: dict[str, object] | None = None,
    accessibility_audit: dict[str, object] | None = None,
    coverage_gaps: tuple = (),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    from health.technical_health import build_technical_health, save_technical_health

    technical_health = build_technical_health([page.page_data for page in pages])
    save_technical_health(technical_health, output_dir)
    target_url = pages[0].page_data.url if pages else ""
    transition_mmd = generate_mermaid(graph, pages)
    _save_markdown_outputs(pages, graph, form_summary, output_dir, target_url, transition_mmd)
    if "html" in formats or "pdf" in formats:
        _save_html_outputs(
            pages,
            graph,
            form_summary,
            output_dir,
            target_url,
            transition_mmd,
            formats,
            crawl_depth,
            crawl_max_pages,
            crawled_at,
            transition_coverage=transition_coverage,
            business_flows=business_flows,
            impact_report=impact_report,
            exploration_coverage=exploration_coverage,
            technical_health=technical_health,
            ux_review=ux_review,
            accessibility_audit=accessibility_audit,
            coverage_gaps=coverage_gaps,
        )
    if "json" in formats:
        _save_json_output(
            pages,
            graph,
            output_dir,
            target_url,
            crawl_depth,
            crawl_max_pages,
            crawled_at,
            transition_coverage=transition_coverage,
            business_flows=business_flows,
            official_names=official_names,
            rule_conditions=rule_conditions,
        )
    if "excel" in formats:
        _save_excel_output(output_dir, pages, form_summary, official_names)
    if llm_insights is not None:
        logger.warning("llm_insights は現在保存対象外です")


def _save_markdown_outputs(
    pages: list[AnalyzedPage],
    graph: nx.DiGraph,
    form_summary: list[dict[str, object]],
    output_dir: Path,
    target_url: str,
    transition_mmd: str,
) -> None:
    from generator.architecture_generator import (
        generate_architecture_mermaid,
        merge_api_endpoints,
        merge_stack_infos,
    )

    screens_md = generate_screens_markdown(pages, graph, target_url)
    forms_md = generate_forms_markdown(form_summary)
    (output_dir / "screens.md").write_text(screens_md, encoding="utf-8")
    (output_dir / "forms.md").write_text(forms_md, encoding="utf-8")
    (output_dir / "transition.mmd").write_text(transition_mmd, encoding="utf-8")

    stacks = [p.page_data.stack_info for p in pages if p.page_data.stack_info]
    merged_endpoints = merge_api_endpoints([p.page_data.api_calls for p in pages])
    arch_mmd = generate_architecture_mermaid(
        domain_key_from_url(target_url), merge_stack_infos(stacks), merged_endpoints
    )
    (output_dir / "architecture.mmd").write_text(arch_mmd, encoding="utf-8")


def _save_html_outputs(
    pages: list[AnalyzedPage],
    graph: nx.DiGraph,
    form_summary: list[dict[str, object]],
    output_dir: Path,
    target_url: str,
    transition_mmd: str,
    formats: Sequence[str],
    crawl_depth: int,
    crawl_max_pages: int,
    crawled_at: str,
    transition_coverage: dict[str, dict] | None = None,
    business_flows: list[dict] | None = None,
    impact_report: dict | None = None,
    exploration_coverage: dict[str, object] | None = None,
    technical_health: dict[str, object] | None = None,
    ux_review: dict[str, object] | None = None,
    accessibility_audit: dict[str, object] | None = None,
    coverage_gaps: tuple = (),
) -> None:
    from generator.html_reporter import generate_html_report

    screenshots_dir = output_dir / "screenshots"
    test_design = _build_test_design_for_report(
        pages,
        graph,
        target_url,
        crawl_depth,
        crawl_max_pages,
        crawled_at,
        transition_coverage,
        business_flows,
    )
    report_html = generate_html_report(
        pages,
        graph,
        form_summary,
        target_url,
        transition_mmd,
        screenshots_dir=screenshots_dir if screenshots_dir.is_dir() else None,
        crawl_depth=crawl_depth,
        crawl_max_pages=crawl_max_pages,
        crawled_at=crawled_at,
        transition_coverage=transition_coverage,
        business_flows=business_flows,
        impact_report=impact_report,
        exploration_coverage=exploration_coverage,
        technical_health=technical_health,
        ux_review=ux_review,
        accessibility_audit=accessibility_audit,
        coverage_gaps=coverage_gaps,
        test_design=test_design,
    )
    html_path = output_dir / "report.html"
    html_path.write_text(report_html, encoding="utf-8")
    if "pdf" in formats:
        from generator.pdf_reporter import generate_pdf

        generate_pdf(html_path, output_dir / PDF_FILE_NAME)


_TEST_DESIGN_SETTINGS_PATH = Path("instance/test_design_settings.json")


def _build_test_design_for_report(
    pages: list[AnalyzedPage],
    graph: nx.DiGraph,
    target_url: str,
    crawl_depth: int,
    crawl_max_pages: int,
    crawled_at: str,
    transition_coverage: dict[str, dict] | None,
    business_flows: list[dict] | None,
) -> TestDesign | None:
    """report.html の「テスト設計（技法別）」節向けに MBT エンジンの入力を組む（R3-18b）。

    generate_json_report と同一の report dict を JSON 経由で組み立て、
    instance/test_design_settings.json の設定を適用して build_test_design() を呼ぶ。
    失敗してもテスト設計は付加機能のため、レポート生成全体は止めず test_design=None で
    継続する（既存出力へのフォールバック方針は他セクションの集計処理と同様）。
    """
    try:
        from generator.json_reporter import generate_json_report
        from generator.test_design import build_test_design, load_params_from_file

        report_json_str = generate_json_report(
            pages,
            graph,
            target_url,
            crawl_depth=crawl_depth,
            crawl_max_pages=crawl_max_pages,
            crawled_at=crawled_at,
            transition_coverage=transition_coverage,
            business_flows=business_flows,
        )
        report_dict = json.loads(report_json_str)
        params = load_params_from_file(_TEST_DESIGN_SETTINGS_PATH)
        return build_test_design(report_dict, params)
    except Exception as exc:  # noqa: BLE001 - テスト設計生成の失敗でレポート生成全体を止めない
        logger.warning("テスト設計（技法別）の生成に失敗しました（節を省略します）: %s", exc)
        return None


def _save_json_output(
    pages: list[AnalyzedPage],
    graph: nx.DiGraph,
    output_dir: Path,
    target_url: str,
    crawl_depth: int,
    crawl_max_pages: int,
    crawled_at: str,
    transition_coverage: dict[str, dict] | None = None,
    business_flows: list[dict] | None = None,
    official_names: dict[str, str] | None = None,
    rule_conditions: dict[tuple[str, str], tuple] | None = None,
) -> None:
    from generator.json_reporter import generate_json_report

    report_json = generate_json_report(
        pages,
        graph,
        target_url,
        crawl_depth=crawl_depth,
        crawl_max_pages=crawl_max_pages,
        crawled_at=crawled_at,
        transition_coverage=transition_coverage,
        business_flows=business_flows,
        official_names=official_names,
        rule_conditions=rule_conditions,
    )
    (output_dir / JSON_REPORT_FILE_NAME).write_text(report_json, encoding="utf-8")


def _parse_formats(raw_formats: str) -> tuple[str, ...]:
    formats = tuple(
        item.strip().lower() for item in raw_formats.split(FORMAT_SEPARATOR) if item.strip()
    )
    unknown = sorted(set(formats) - SUPPORTED_FORMATS)
    known = tuple(item for item in formats if item in SUPPORTED_FORMATS)
    if unknown:
        logger.warning("未対応の出力形式を無視します: %s", ", ".join(unknown))
    if not known:
        # 有効な形式が 1 つも残らないのに成功で終わると、指定した成果物が
        # 出ていないことに気づけない。何を指定でき、何が不明だったかを示して止める。
        logger.error(
            "出力形式が 1 つも指定されていません（不明: %s）。指定できるのは %s です。",
            ", ".join(unknown) or "なし",
            ", ".join(sorted(SUPPORTED_FORMATS)),
        )
        raise SystemExit(2)
    return known
