"""特定のテスト管理ツールに依存しない汎用テストケース CSV を生成する（検証会社向け）。"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from crawler.page_crawler import PageData

CSV_ENCODING = "utf-8-sig"

_SCREEN_HEADER = [
    "ページ番号",
    "ページ名",
    "URL",
    "フォームアクション",
    "フィールド名",
    "フィールド種別",
    "必須",
    "テスト条件",
]

_TESTCASE_HEADER = [
    "ID",
    "タイトル",
    "ステップ",
    "期待結果",
    "自動化ステータス",
    "トレースID",
]

_EMPTY_FORM_LABEL = "(空のフォーム)"

logger = logging.getLogger(__name__)


def generate_csv_report(pages: list[PageData], output_path: Path) -> Path:
    """各ページのフォーム・テスト条件を Excel で開ける CSV として出力。"""
    from analyzer.test_conditions import derive_conditions

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding=CSV_ENCODING) as f:
        writer = csv.writer(f)
        writer.writerow(_SCREEN_HEADER)
        for page_no, page in enumerate(pages, start=1):
            _write_page_rows(writer, page_no, page, derive_conditions)
    logger.info("CSV レポート出力完了: %s (%d ページ)", output_path, len(pages))
    return output_path


def _write_page_rows(
    writer: Any,
    page_no: int,
    page: PageData,
    derive_conditions: object,
) -> None:
    """1 ページ分のフォーム行を writer に書き出す。"""
    if not page.forms:
        writer.writerow([page_no, page.title, page.url, "", _EMPTY_FORM_LABEL, "", "", ""])
        return
    for form in page.forms:
        if not form.fields:
            writer.writerow(
                [
                    page_no,
                    page.title,
                    page.url,
                    form.action,
                    _EMPTY_FORM_LABEL,
                    "",
                    "",
                    "",
                ]
            )
            continue
        for field in form.fields:
            conditions = derive_conditions(field)  # type: ignore[operator]
            conditions_str = "\n".join(str(c) for c in conditions)
            writer.writerow(
                [
                    page_no,
                    page.title,
                    page.url,
                    form.action,
                    field.name,
                    field.field_type,
                    "Yes" if field.required else "No",
                    conditions_str,
                ]
            )


def generate_testcase_csv(test_cases: list[dict], output_path: Path) -> Path:
    """openai_qa.py 等の出力した test_cases リストを CSV 化する。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding=CSV_ENCODING) as f:
        writer = csv.writer(f)
        writer.writerow(_TESTCASE_HEADER)
        for case in test_cases:
            steps = case.get("steps", "")
            if isinstance(steps, list):
                steps = "\n".join(str(s) for s in steps)
            writer.writerow(
                [
                    case.get("id", ""),
                    case.get("title", ""),
                    steps,
                    case.get("expected", ""),
                    case.get("automation_status", ""),
                    case.get("trace_id", ""),
                ]
            )
    logger.info("テストケース CSV 出力完了: %s (%d 件)", output_path, len(test_cases))
    return output_path
