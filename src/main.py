from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse

import networkx as nx
import openpyxl
from dotenv import load_dotenv

from analyzer.form_analyzer import summarize_forms
from analyzer.html_analyzer import AnalyzedPage, analyze_pages
from crawler.page_crawler import DEFAULT_DEPTH, DEFAULT_MAX_PAGES, PageData, crawl_site
from diff.differ import compute_diff
from diff.snapshot import latest_snapshot, load_snapshot, save_snapshot
from generator.diff_reporter import generate_diff_report
from generator.markdown_generator import (
    generate_forms_markdown,
    generate_screens_markdown,
)
from generator.mermaid_generator import generate_mermaid
from graph.transition_graph import build_graph

DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_FORMATS = "md"
FORMAT_SEPARATOR = ","
LOGGER_FORMAT = "%(levelname)s:%(name)s:%(message)s"
SUPPORTED_FORMATS = frozenset({"md", "html", "excel"})
XLSX_FILE_NAME = "spec.xlsx"
DIFF_REPORT_FILE_NAME = "diff_report.html"
FIRST_SNAPSHOT_MESSAGE = "初回スナップショットを保存しました。次回実行から差分を検出できます"

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOGGER_FORMAT)
    load_dotenv()
    run(parse_args())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WebSpec2Doc web crawler")
    parser.add_argument("--url", required=True, help="クロール対象URL")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help="クロール深度")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help="最大クロールページ数",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="出力先")
    parser.add_argument("--llm", action="store_true", help="LLM解析を有効化")
    parser.add_argument("--format", default=DEFAULT_FORMATS, help="出力形式: md,html,excel")
    parser.add_argument("--compare", action="store_true", help="前回スナップショットとの差分を出力")
    return parser.parse_args()


def run(args: argparse.Namespace) -> None:
    formats = _parse_formats(str(args.format))
    output_dir = Path(args.output) / _domain_name(str(args.url))
    prior_snapshot = latest_snapshot(output_dir)
    if args.llm:
        logger.warning("--llm は未実装のため無視します")

    pages = crawl_site(
        url=str(args.url),
        depth=int(args.depth),
        max_pages=int(args.max_pages),
        output_dir=output_dir,
    )
    analyzed_pages = analyze_pages(pages)
    graph = build_graph(analyzed_pages)
    form_summary = summarize_forms(analyzed_pages)
    save_outputs(analyzed_pages, graph, form_summary, output_dir, formats)
    new_snapshot = save_snapshot(pages, output_dir)
    if bool(getattr(args, "compare", False)):
        _save_diff_report(prior_snapshot, new_snapshot, pages, output_dir, str(args.url))
    logger.info("出力が完了しました: %s", output_dir)


def _save_diff_report(
    prior_snapshot: Path | None,
    new_snapshot: Path,
    pages: list[PageData],
    output_dir: Path,
    target_url: str,
) -> None:
    if prior_snapshot is None:
        logger.info(FIRST_SNAPSHOT_MESSAGE)
        return
    old_pages = load_snapshot(prior_snapshot)
    diff = compute_diff(old_pages, pages)
    report_html = generate_diff_report(
        diff=diff,
        old_label=prior_snapshot.name,
        new_label=new_snapshot.name,
        target_url=target_url,
    )
    (output_dir / DIFF_REPORT_FILE_NAME).write_text(report_html, encoding="utf-8")


def save_outputs(
    pages: list[AnalyzedPage],
    graph: nx.DiGraph,
    form_summary: list[dict[str, object]],
    output_dir: Path,
    formats: Sequence[str],
    llm_insights: object | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_url = pages[0].page_data.url if pages else ""
    screens_md = generate_screens_markdown(pages, graph, target_url)
    forms_md = generate_forms_markdown(form_summary)
    transition_mmd = generate_mermaid(graph, pages)

    (output_dir / "screens.md").write_text(screens_md, encoding="utf-8")
    (output_dir / "forms.md").write_text(forms_md, encoding="utf-8")
    (output_dir / "transition.mmd").write_text(transition_mmd, encoding="utf-8")
    if "html" in formats:
        from generator.html_reporter import generate_html_report
        screenshots_dir = output_dir / "screenshots"
        report_html = generate_html_report(
            pages, graph, form_summary, target_url, transition_mmd,
            screenshots_dir=screenshots_dir if screenshots_dir.is_dir() else None,
        )
        (output_dir / "report.html").write_text(report_html, encoding="utf-8")
    if "excel" in formats:
        _save_excel_output(output_dir, pages, form_summary)
    if llm_insights is not None:
        logger.warning("llm_insights は現在保存対象外です")


def _parse_formats(raw_formats: str) -> tuple[str, ...]:
    formats = tuple(
        item.strip().lower()
        for item in raw_formats.split(FORMAT_SEPARATOR)
        if item.strip()
    )
    unknown = sorted(set(formats) - SUPPORTED_FORMATS)
    if unknown:
        logger.warning("未対応の出力形式を無視します: %s", ", ".join(unknown))
    return tuple(item for item in formats if item in SUPPORTED_FORMATS)


def _domain_name(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.replace("/", "_") or "site"



def _save_excel_output(
    output_dir: Path,
    pages: list[AnalyzedPage],
    form_summary: list[dict[str, object]],
) -> None:
    wb = openpyxl.Workbook()

    _write_screens_sheet(wb.active, pages)
    wb.active.title = "Screens"

    forms_sheet = wb.create_sheet("Forms")
    _write_forms_sheet(forms_sheet, form_summary)

    wb.save(output_dir / XLSX_FILE_NAME)


def _write_screens_sheet(ws: openpyxl.worksheet.worksheet.Worksheet, pages: list[AnalyzedPage]) -> None:
    ws.append(["画面ID", "URL", "タイトル", "フォーム数"])
    for page in pages:
        ws.append([page.page_id, page.page_data.url, page.page_data.title, len(page.page_data.forms)])


def _write_forms_sheet(
    ws: openpyxl.worksheet.worksheet.Worksheet,
    form_summary: list[dict[str, object]],
) -> None:
    ws.append(["画面ID", "URL", "フィールド名", "型", "必須", "placeholder"])
    for item in form_summary:
        ws.append([
            item.get("page_id", ""),
            item.get("url", ""),
            item.get("name", ""),
            item.get("field_type", ""),
            item.get("required", False),
            item.get("placeholder", ""),
        ])


if __name__ == "__main__":
    main()
