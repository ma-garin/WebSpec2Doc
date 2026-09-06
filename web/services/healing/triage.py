"""E2E の失敗を「サイトの不具合」か「テストの書き方が古いだけ」かに振り分ける。

オートヒーリングは既定でサイト側（製品コード）を直しに行く。だが実際には、
テストが探している文言が画面の呼び方の変更などで単に古くなっているだけの
ケースがある。この場合にサイトのコードへ手を入れると、直す必要のない箇所を
書き換えることになり、かえって危険。

判定は上から順に一本道:
    1. E2E 起点でない・URL が無い          → unknown（判別対象外・従来どおり）
    2. セレクタの失敗ではない               → unknown（従来どおり）
    3. 探している文言が画面に「ある」        → product（表示か遷移の問題）
    4. 画面には無いが画面仕様には「ある」    → product（画面から消えている）
    5. どちらにも無い                      → script（テストの書き方が古い）

判断であって事実の書き換えではないため、この結果だけで自動的に何かを
書き換えることはしない（呼び出し側が kind を見て動く）。
"""

from __future__ import annotations

import difflib
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from web.services.healing.localization import _extract_selector_needles
from web.services.healing.spec_match import load_screen_spec
from web.services.healing.types import Defect

#: 候補として拾う文字列の長さ。1〜2 文字は「実行」「保存」等が多く当たりすぎる。
_MIN_CANDIDATE_LEN = 2
_MAX_CANDIDATE_LEN = 80
#: difflib の類似度の足切り。
_MIN_RATIO = 0.5
#: 候補の上限件数。
_MAX_CANDIDATES = 5


@dataclass(frozen=True)
class Triage:
    """1 件の欠陥に対する判別結果。"""

    kind: str  # "script" | "product" | "unknown"
    reason: str
    needle: str = ""
    candidates: tuple[str, ...] = ()


class _VisibleTextExtractor(HTMLParser):
    """script/style を除いた可視テキストだけを行ごとに集める。"""

    _SKIP_TAGS = frozenset({"script", "style", "noscript", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.lines: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self.lines.append(text)


def page_texts(url: str, *, timeout: float = 5.0) -> tuple[str, ...]:
    """URL を取得し、可視テキストを行ごとに返す。取得できなければ空。"""
    if not url:
        return ()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - 対象は自ドメインのみ想定
            charset = resp.headers.get_content_charset() or "utf-8"
            html_text = resp.read().decode(charset, errors="ignore")
    except (urllib.error.URLError, OSError, ValueError):
        return ()
    parser = _VisibleTextExtractor()
    try:
        parser.feed(html_text)
    except Exception:  # noqa: BLE001 - 壊れた HTML で判別を落とさない
        return ()
    return tuple(parser.lines)


def _spec_texts(out_dir: Path, domain: str, page_id: str) -> tuple[str, ...]:
    """画面仕様の見出し・ボタン・入力欄ラベル。読めなければ空。"""
    if not domain or not page_id:
        return ()
    try:
        spec = load_screen_spec(out_dir, domain, page_id)
    except Exception:  # noqa: BLE001 - 仕様が読めなくても判別は続ける
        return ()
    if spec is None:
        return ()
    return spec.headings + spec.buttons + spec.form_labels


def _candidates(needle: str, pool: Sequence[str]) -> tuple[str, ...]:
    """置き換え候補。似ている順・最大 5 件。"""
    scored: list[tuple[float, str]] = []
    seen: set[str] = set()
    for raw in pool:
        text = raw.strip()
        if not (_MIN_CANDIDATE_LEN <= len(text) <= _MAX_CANDIDATE_LEN):
            continue
        if text == needle or text in seen:
            continue
        ratio = difflib.SequenceMatcher(None, needle, text).ratio()
        if ratio >= _MIN_RATIO or needle in text or text in needle:
            scored.append((ratio, text))
            seen.add(text)
    scored.sort(key=lambda item: -item[0])
    return tuple(text for _, text in scored[:_MAX_CANDIDATES])


def classify(defect: Defect, *, out_dir: Path, domain: str) -> Triage:
    """欠陥 1 件を判別する。副作用なし（何も書き換えない）。"""
    if defect.source == "verify" or not defect.url:
        return Triage(kind="unknown", reason="E2E の失敗ではないため判別対象外")

    haystack = f"{defect.message}\n{defect.evidence}"
    needles = _extract_selector_needles(haystack)
    if not needles:
        return Triage(kind="unknown", reason="セレクタの失敗ではない")

    needle = needles[0][0]
    page = page_texts(defect.url)
    if any(needle in line for line in page):
        return Triage(
            kind="product",
            reason=f"画面に「{needle}」はあるが、テストの期待と一致しない（表示内容か遷移の問題）",
            needle=needle,
        )

    spec_texts = _spec_texts(out_dir, domain, defect.screen_id)
    if needle in spec_texts:
        return Triage(
            kind="product",
            reason=f"画面仕様にある「{needle}」が画面から消えている",
            needle=needle,
        )

    pool = tuple(page) + spec_texts
    return Triage(
        kind="script",
        reason=f"テストが探す「{needle}」は画面にも画面仕様にも無い。テストの書き方が古い",
        needle=needle,
        candidates=_candidates(needle, pool),
    )
