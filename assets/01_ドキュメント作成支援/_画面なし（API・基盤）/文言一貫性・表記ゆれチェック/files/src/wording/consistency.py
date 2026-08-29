"""辞書ベースの表記ゆれ検出。

方針:
- 辞書に無いものは指摘しない。汎用の日本語校正を目指すと誤検知が増え、
  「指摘が多すぎて誰も読まない」状態になるため。
- 同義語は「どちらが正しい」ではなく**混在していること**を指摘する。
  正解を決めるのは組織であってツールではない。
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CLAIM_SCOPE = "dictionary_matches_only"

CLAIM_NOTICE = "本結果は辞書に登録されたパターンの検出であり、文章の品質を評価するものではない。"

DICTIONARY_FILENAME = "wording_dictionary.json"

ISSUE_SYNONYM = "synonym_mixed"
ISSUE_WIDTH = "width_mixed"
ISSUE_STYLE = "style_mixed"

# 敬体（です・ます）と常体（だ・である）の語尾。文末のみを見る。
_POLITE_ENDINGS = ("です", "ます", "ません", "でした", "ましょう", "ください")
_PLAIN_ENDINGS = ("である", "だった", "した", "する", "ない", "だ")

_SENTENCE_SPLIT = re.compile(r"[。\n]+")


@dataclass(frozen=True)
class SynonymGroup:
    """同義語の集合。どれが正でも構わないが、混在は指摘する。"""

    terms: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True)
class WordingDictionary:
    synonyms: tuple[SynonymGroup, ...] = ()
    check_width: bool = True
    check_style: bool = True
    ignore_terms: frozenset[str] = field(default_factory=frozenset)


DEFAULT_DICTIONARY = WordingDictionary(
    synonyms=(
        SynonymGroup(("ログイン", "サインイン"), "認証操作の呼び方"),
        SynonymGroup(("ログアウト", "サインアウト"), "認証解除の呼び方"),
        SynonymGroup(("登録", "申し込み", "申込"), "新規作成の呼び方"),
        SynonymGroup(("削除", "消去"), "破棄操作の呼び方"),
        SynonymGroup(("送信", "送付"), "データ送出の呼び方"),
    )
)


def load_dictionary(path: Path) -> WordingDictionary:
    """辞書を読む。無い・壊れている場合は既定辞書を使う。"""
    if not path.is_file():
        return DEFAULT_DICTIONARY
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("文言辞書を読めませんでした: %s (%s)", path, exc)
        return DEFAULT_DICTIONARY

    groups = tuple(
        SynonymGroup(
            terms=tuple(str(term) for term in item.get("terms", []) if str(term)),
            note=str(item.get("note", "")),
        )
        for item in payload.get("synonyms", [])
        if isinstance(item, dict) and len(item.get("terms", [])) >= 2
    )
    return WordingDictionary(
        synonyms=groups or DEFAULT_DICTIONARY.synonyms,
        check_width=bool(payload.get("check_width", True)),
        check_style=bool(payload.get("check_style", True)),
        ignore_terms=frozenset(str(term) for term in payload.get("ignore_terms", [])),
    )


def check_wording(
    texts: dict[str, list[str]], dictionary: WordingDictionary | None = None
) -> dict[str, Any]:
    """画面ごとのテキスト集合を検査する。

    texts: 画面URL -> その画面で観測したテキスト一覧
    """
    active = dictionary or DEFAULT_DICTIONARY
    issues: list[dict[str, Any]] = []

    if active.synonyms:
        issues.extend(_synonym_issues(texts, active))
    if active.check_width:
        issues.extend(_width_issues(texts, active))
    if active.check_style:
        issues.extend(_style_issues(texts))

    return {
        "meta": {"claim_scope": CLAIM_SCOPE, "claim_notice": CLAIM_NOTICE},
        "issues": issues,
        "summary": {
            "total": len(issues),
            ISSUE_SYNONYM: sum(1 for i in issues if i["type"] == ISSUE_SYNONYM),
            ISSUE_WIDTH: sum(1 for i in issues if i["type"] == ISSUE_WIDTH),
            ISSUE_STYLE: sum(1 for i in issues if i["type"] == ISSUE_STYLE),
        },
    }


def _synonym_issues(
    texts: dict[str, list[str]], dictionary: WordingDictionary
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for group in dictionary.synonyms:
        found: dict[str, list[str]] = {}
        for page_url, page_texts in texts.items():
            joined = " ".join(page_texts)
            for term in group.terms:
                if term in dictionary.ignore_terms:
                    continue
                if term in joined:
                    found.setdefault(term, []).append(page_url)
        if len(found) >= 2:
            issues.append(
                {
                    "type": ISSUE_SYNONYM,
                    "terms": sorted(found),
                    "note": group.note,
                    "occurrences": {term: sorted(set(pages)) for term, pages in found.items()},
                    "message": (
                        f"同義語が混在しています: {' / '.join(sorted(found))}"
                        "（どれを正とするかは組織で決めてください）"
                    ),
                }
            )
    return issues


def _width_issues(
    texts: dict[str, list[str]], dictionary: WordingDictionary
) -> list[dict[str, Any]]:
    """同じ語が全角・半角の両方で現れているものを拾う。"""
    seen: dict[str, dict[str, list[str]]] = {}
    for page_url, page_texts in texts.items():
        for text in page_texts:
            for token in re.findall(r"[０-９Ａ-Ｚａ-ｚ0-9A-Za-z]{2,}", text):
                if token in dictionary.ignore_terms:
                    continue
                normalized = unicodedata.normalize("NFKC", token)
                seen.setdefault(normalized, {}).setdefault(token, []).append(page_url)

    issues: list[dict[str, Any]] = []
    for normalized, variants in seen.items():
        if len(variants) >= 2:
            issues.append(
                {
                    "type": ISSUE_WIDTH,
                    "normalized": normalized,
                    "variants": sorted(variants),
                    "occurrences": {v: sorted(set(pages)) for v, pages in variants.items()},
                    "message": f"全角/半角が混在しています: {' / '.join(sorted(variants))}",
                }
            )
    return issues


def _style_issues(texts: dict[str, list[str]]) -> list[dict[str, Any]]:
    """1画面内で敬体と常体が混ざっているものを拾う。"""
    issues: list[dict[str, Any]] = []
    for page_url, page_texts in sorted(texts.items()):
        polite, plain = 0, 0
        for text in page_texts:
            for sentence in _SENTENCE_SPLIT.split(text):
                stripped = sentence.strip()
                if len(stripped) < 4:
                    continue
                if stripped.endswith(_POLITE_ENDINGS):
                    polite += 1
                elif stripped.endswith(_PLAIN_ENDINGS):
                    plain += 1
        if polite and plain:
            issues.append(
                {
                    "type": ISSUE_STYLE,
                    "page_url": page_url,
                    "polite_sentences": polite,
                    "plain_sentences": plain,
                    "message": (f"敬体（{polite}文）と常体（{plain}文）が同一画面に混在しています"),
                }
            )
    return issues


def texts_from_pages(pages: list[Any]) -> dict[str, list[str]]:
    """PageData 一覧から検査対象テキストを集める（見出しとタイトル）。"""
    collected: dict[str, list[str]] = {}
    for page in pages:
        values = [str(getattr(page, "title", ""))]
        values.extend(str(heading) for heading in getattr(page, "headings", ()))
        collected[str(getattr(page, "url", ""))] = [value for value in values if value]
    return collected
