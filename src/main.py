from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import networkx as nx
import openpyxl
from dotenv import load_dotenv

from analyzer.form_analyzer import summarize_forms
from analyzer.html_analyzer import AnalyzedPage, analyze_pages
from crawler.auth import DEFAULT_AUTH_FILE, capture_auth_state
from crawler.page_crawler import (
    DEFAULT_DEPTH,
    DEFAULT_MAX_PAGES,
    PageData,
    crawl_site,
    crawl_urls,
    discover_pages,
)
from crawler.session_guard import SessionExpiredError
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
SUPPORTED_FORMATS = frozenset({"md", "html", "excel", "pdf", "json"})
XLSX_FILE_NAME = "spec.xlsx"
PDF_FILE_NAME = "report.pdf"
JSON_REPORT_FILE_NAME = "report.json"
DIFF_REPORT_FILE_NAME = "diff_report.html"
FIRST_SNAPSHOT_MESSAGE = "初回スナップショットを保存しました。次回実行から差分を検出できます"

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOGGER_FORMAT)
    load_dotenv()
    run(parse_args())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WebSpec2Doc web crawler")
    parser.add_argument("--url", help="クロール対象URL")
    parser.add_argument(
        "--urls",
        help="リンク追跡せず指定URLのみクロール（カンマ区切り）。--url の代わりに使用",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="リンク追跡で到達するページ一覧(URL+タイトル)をJSONでstdoutに出力して終了",
    )
    parser.add_argument("--login", help="ログインセッション保存モード: ログインページURL（CLI用）")
    parser.add_argument(
        "--login-signal",
        type=Path,
        help="GUI 手渡しログイン用: このファイルが出現したらセッションを保存する（廃止予定）",
    )
    parser.add_argument(
        "--login-simple", action="store_true", help="ID/PASSWORDをstdinのJSONで受取り自動ログイン"
    )
    parser.add_argument("--login-simple-url", help="--login-simple: ログインページURL")
    parser.add_argument(
        "--login-scrape", help="ログインURLのフォームフィールドを取得してJSONで出力"
    )
    parser.add_argument(
        "--login-submit",
        action="store_true",
        help="ログインフォーム自動送信（フィールド値はstdinからJSON受取）",
    )
    parser.add_argument("--login-current-url", help="--login-submit: フォーム送信先URL（MFA対応）")
    parser.add_argument("--login-temp-session", type=Path, help="MFA中間セッション保存パス")
    parser.add_argument("--auth", type=Path, help="保存済みセッション(auth.json)を使ってクロール")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help="クロール深度")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help="最大クロールページ数",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="出力先")
    parser.add_argument("--llm", action="store_true", help="LLM解析を有効化")
    parser.add_argument(
        "--format", default=DEFAULT_FORMATS, help="出力形式: md,html,excel,pdf,json"
    )
    parser.add_argument("--compare", action="store_true", help="前回スナップショットとの差分を出力")
    return parser.parse_args()


def run(args: argparse.Namespace) -> None:
    login_url = getattr(args, "login", None)
    auth_path = getattr(args, "auth", None)
    signal_path = getattr(args, "login_signal", None)
    if getattr(args, "login_simple", False):
        _submit_login_simple(args)
        return
    if login_scrape_url := getattr(args, "login_scrape", None):
        _scrape_login(str(login_scrape_url))
        return
    if getattr(args, "login_submit", False):
        _submit_login(args)
        return
    if login_url:
        _capture_login(str(login_url), auth_path, signal_path)
        return
    if bool(getattr(args, "discover", False)):
        _discover(args, auth_path)
        return

    url_list = _parse_url_list(getattr(args, "urls", None))
    primary_url = url_list[0] if url_list else (args.url or "")
    if not primary_url:
        logger.error("--url / --urls / --login のいずれかを指定してください")
        return

    formats = _parse_formats(str(args.format))
    output_dir = Path(args.output) / _domain_name(primary_url)
    prior_snapshot = latest_snapshot(output_dir)
    if args.llm:
        logger.warning("--llm は未実装のため無視します")

    crawled_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    auth_state = Path(auth_path) if auth_path else None
    try:
        if url_list:
            pages = crawl_urls(url_list, output_dir=output_dir, auth_state=auth_state)
        else:
            pages = crawl_site(
                url=primary_url,
                depth=int(args.depth),
                max_pages=int(args.max_pages),
                output_dir=output_dir,
                auth_state=auth_state,
            )
    except SessionExpiredError as exc:
        # snapshot 保存前に中断。古い結果を上書きせず GUI に再ログインを促す
        logger.error("%s", exc)
        sys.stdout.write("SESSION_EXPIRED\n")
        sys.exit(2)
    analyzed_pages = analyze_pages(pages)
    graph = build_graph(analyzed_pages)
    form_summary = summarize_forms(analyzed_pages)
    save_outputs(
        analyzed_pages,
        graph,
        form_summary,
        output_dir,
        formats,
        crawl_depth=int(args.depth),
        crawl_max_pages=int(args.max_pages),
        crawled_at=crawled_at,
    )
    new_snapshot = save_snapshot(pages, output_dir)
    if bool(getattr(args, "compare", False)):
        _save_diff_report(prior_snapshot, new_snapshot, pages, output_dir, primary_url)
    logger.info("出力が完了しました: %s", output_dir)


def _parse_url_list(raw_urls: str | None) -> list[str]:
    if not raw_urls:
        return []
    seen: dict[str, None] = {}
    for item in raw_urls.split(FORMAT_SEPARATOR):
        cleaned = item.strip()
        if cleaned:
            seen.setdefault(cleaned, None)
    return list(seen)


def _submit_login_simple(args: argparse.Namespace) -> None:
    """ID/PASSWORDをstdinのJSONで受取り、type属性ベースで自動マッピングしてログインする。"""
    from dataclasses import asdict

    from crawler.auto_login import submit_login_simple

    login_url = getattr(args, "login_simple_url", None) or ""
    if not login_url:
        sys.stdout.write(json.dumps({"success": False, "error": "--login-simple-url が必要です"}))
        return
    auth_path = Path(args.auth) if args.auth else Path(DEFAULT_AUTH_FILE)
    try:
        raw = sys.stdin.read().strip() if not sys.stdin.isatty() else "{}"
        creds: dict[str, str] = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        sys.stdout.write(json.dumps({"success": False, "error": "認証情報JSONが不正です"}))
        return
    result = submit_login_simple(
        username=creds.get("username", ""),
        password=creds.get("password", ""),
        login_url=login_url,
        auth_path=auth_path,
    )
    sys.stdout.write(
        json.dumps(
            {
                "success": result.success,
                "needs_more_fields": result.needs_more_fields,
                "fields": [asdict(f) for f in result.fields],
                "current_url": result.current_url,
                "error": result.error,
            },
            ensure_ascii=False,
        )
    )


def _scrape_login(url: str) -> None:
    """ログインページのフォームフィールドを取得してJSONをstdoutに出力する。"""
    from dataclasses import asdict

    from crawler.auto_login import scrape_login_fields

    result = scrape_login_fields(url)
    sys.stdout.write(
        json.dumps(
            {
                "ok": result.ok,
                "fields": [asdict(f) for f in result.fields],
                "current_url": result.current_url,
                "error": result.error,
            },
            ensure_ascii=False,
        )
    )


def _submit_login(args: argparse.Namespace) -> None:
    """フォーム値をstdinからJSON受取して自動送信し、結果をstdoutに出力する。"""
    from dataclasses import asdict

    from crawler.auto_login import submit_login_form

    current_url = getattr(args, "login_current_url", None) or ""
    if not current_url:
        sys.stdout.write(json.dumps({"success": False, "error": "--login-current-url が必要です"}))
        return

    auth_path = Path(args.auth) if args.auth else Path(DEFAULT_AUTH_FILE)
    temp_session = getattr(args, "login_temp_session", None)

    try:
        raw = sys.stdin.read().strip() if not sys.stdin.isatty() else "{}"
        field_values: dict[str, str] = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        sys.stdout.write(json.dumps({"success": False, "error": "フィールドJSONが不正です"}))
        return

    result = submit_login_form(
        field_values=field_values,
        current_url=current_url,
        auth_path=auth_path,
        temp_session_path=temp_session,
    )
    sys.stdout.write(
        json.dumps(
            {
                "success": result.success,
                "needs_more_fields": result.needs_more_fields,
                "fields": [asdict(f) for f in result.fields],
                "current_url": result.current_url,
                "error": result.error,
            },
            ensure_ascii=False,
        )
    )


def _capture_login(login_url: str, auth_path: Path | None, signal_path: Path | None = None) -> None:
    output_path = Path(auth_path) if auth_path else Path(DEFAULT_AUTH_FILE)
    if signal_path is not None:
        from crawler.auth import capture_auth_state_via_signal

        output_path.parent.mkdir(parents=True, exist_ok=True)
        saved = capture_auth_state_via_signal(login_url, output_path, Path(signal_path))
        if saved is None:
            logger.error("ログイン完了シグナルを待機中にタイムアウトしました")
            sys.exit(1)
        logger.info("ログインセッションを保存しました: %s", saved)
        return
    saved = capture_auth_state(login_url, output_path)
    logger.info(
        "ログインセッションを保存しました: %s （--auth %s でクロールに利用できます）", saved, saved
    )


def _discover(args: argparse.Namespace, auth_path: Path | None) -> None:
    """画面リストを探索し、JSON を stdout に出力する（GUI の画面リスト取得用）。"""
    if not args.url:
        sys.stdout.write(json.dumps({"pages": [], "error": "--url が必要です"}))
        return
    pages = discover_pages(
        url=str(args.url),
        depth=int(args.depth),
        max_pages=int(args.max_pages),
        auth_state=Path(auth_path) if auth_path else None,
    )
    sys.stdout.write(json.dumps({"pages": pages}, ensure_ascii=False))


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
    crawl_depth: int = DEFAULT_DEPTH,
    crawl_max_pages: int = DEFAULT_MAX_PAGES,
    crawled_at: str = "",
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_url = pages[0].page_data.url if pages else ""
    screens_md = generate_screens_markdown(pages, graph, target_url)
    forms_md = generate_forms_markdown(form_summary)
    transition_mmd = generate_mermaid(graph, pages)

    (output_dir / "screens.md").write_text(screens_md, encoding="utf-8")
    (output_dir / "forms.md").write_text(forms_md, encoding="utf-8")
    (output_dir / "transition.mmd").write_text(transition_mmd, encoding="utf-8")
    if "html" in formats or "pdf" in formats:
        from generator.html_reporter import generate_html_report

        screenshots_dir = output_dir / "screenshots"
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
        )
        html_path = output_dir / "report.html"
        html_path.write_text(report_html, encoding="utf-8")
        if "pdf" in formats:
            from generator.pdf_reporter import generate_pdf

            generate_pdf(html_path, output_dir / PDF_FILE_NAME)
    if "json" in formats:
        from generator.json_reporter import generate_json_report

        report_json = generate_json_report(
            pages,
            graph,
            target_url,
            crawl_depth=crawl_depth,
            crawl_max_pages=crawl_max_pages,
            crawled_at=crawled_at,
        )
        (output_dir / JSON_REPORT_FILE_NAME).write_text(report_json, encoding="utf-8")
    if "excel" in formats:
        _save_excel_output(output_dir, pages, form_summary)
    if llm_insights is not None:
        logger.warning("llm_insights は現在保存対象外です")


def _parse_formats(raw_formats: str) -> tuple[str, ...]:
    formats = tuple(
        item.strip().lower() for item in raw_formats.split(FORMAT_SEPARATOR) if item.strip()
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


def _write_screens_sheet(
    ws: openpyxl.worksheet.worksheet.Worksheet, pages: list[AnalyzedPage]
) -> None:
    ws.append(["画面ID", "URL", "タイトル", "フォーム数"])
    for page in pages:
        ws.append(
            [page.page_id, page.page_data.url, page.page_data.title, len(page.page_data.forms)]
        )


def _write_forms_sheet(
    ws: openpyxl.worksheet.worksheet.Worksheet,
    form_summary: list[dict[str, object]],
) -> None:
    ws.append(["画面ID", "URL", "フィールド名", "型", "必須", "placeholder"])
    for item in form_summary:
        ws.append(
            [
                item.get("page_id", ""),
                item.get("url", ""),
                item.get("name", ""),
                item.get("field_type", ""),
                item.get("required", False),
                item.get("placeholder", ""),
            ]
        )


if __name__ == "__main__":
    main()
