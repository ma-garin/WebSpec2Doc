"""画面/項目名の類似度判定・URL パス正規化の共通ヘルパー。

Doc Fusion（ingest/matcher.py）と現新比較（diff/pair_matcher.py）で同一の
名称類似判定ロジックを共有するために切り出した（docs/11 §6-4 の設計指針）。
どちらの利用側も挙動を変えないよう、ロジック自体は移設前と同一にしている。
"""

from __future__ import annotations

from difflib import SequenceMatcher
from urllib.parse import urlparse


def normalize_path(url_or_path: str) -> str:
    """URL またはパス文字列を比較用に正規化する（末尾スラッシュ除去・小文字化）。"""
    parsed = urlparse(url_or_path)
    path = parsed.path or url_or_path
    return path.rstrip("/").lower() or "/"


def name_similarity(left: str, right: str) -> float:
    """2 つの名称文字列の類似度（0.0〜1.0）を返す。どちらかが空なら 0.0。"""
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()
