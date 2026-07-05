"""Markdown 生成の共通ヘルパー。

複数のレポート生成器（refresh_reporter / trace_reporter 等）が同じ
テーブルセルのエスケープ処理を重複実装していたため共通化した。
"""

from __future__ import annotations


def escape_table_cell(value: str) -> str:
    """Markdown テーブルのセル内容をエスケープする。

    セル区切りの ``|`` をそのまま埋め込むと列がずれて表全体が壊れるため、
    ``\\|`` に置換する（改行はセル内に現れない前提で扱わない）。
    """
    return value.replace("|", "\\|")
