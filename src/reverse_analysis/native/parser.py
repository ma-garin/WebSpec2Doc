"""パーサの契約と唯一の差し替え点。tree_sitter を import してよいのは parser_ts.py だけ。"""

from __future__ import annotations

from typing import Protocol

from reverse_analysis.native.facts import ParsedFile


class Parser(Protocol):
    def parse(self, path: str, source: bytes) -> ParsedFile:
        """source を解析して ParsedFile を返す。例外は投げず、失敗は limitations に残す。"""
        ...


_parser: Parser | None = None


def get_parser() -> Parser:
    """既定は tree-sitter 実装。set_parser で差し替えられる。"""
    global _parser
    if _parser is None:
        from reverse_analysis.native.parser_ts import TreeSitterParser

        _parser = TreeSitterParser()
    return _parser


def set_parser(parser: Parser | None) -> None:
    """テスト・差し替え用。None で既定へ戻す。"""
    global _parser
    _parser = parser
