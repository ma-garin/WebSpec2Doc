"""差分の誤検知フィルタ（無視ルール）。

日付表示・アクセスカウンタのような動的要素は、実装が変わっていなくても毎回差分として
検出される。利用者が指定したパターンをここで退避させ、レポートの信号対雑音比を上げる。

除外した変更は**捨てずに記録として返す**。黙って消すとフィルタ自体が信用を失い、
「本当は変わっていたのに気づけなかった」を検知できなくなるため（evidence-only 原則）。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from diff.differ import DiffResult

logger = logging.getLogger(__name__)

KIND_FIELD = "field"
KIND_SELECTOR = "selector"
KIND_REGEX = "regex"
KIND_URL = "url"
IGNORE_KINDS = (KIND_FIELD, KIND_SELECTOR, KIND_REGEX, KIND_URL)

IGNORE_RULES_FILENAME = "diff_ignore.json"


@dataclass(frozen=True)
class IgnoreRule:
    """1件の無視ルール。

    kind:
        field    — フォーム項目名の完全一致
        selector — 要素ID の一致（先頭の '#' は許容）
        regex    — 変更されたテキストへの正規表現一致
        url      — ページURL への正規表現一致
    """

    kind: str
    pattern: str
    note: str = ""


@dataclass(frozen=True)
class _Target:
    """変更1件を、ルール照合できる形に正規化したもの。"""

    category: str
    url: str
    field_name: str
    element_id: str
    texts: tuple[str, ...]
    label: str


def load_ignore_rules(path: Path) -> list[IgnoreRule]:
    """diff_ignore.json を読む。存在しない・壊れている場合は空リストを返す。"""
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("無視ルールを読めませんでした: %s (%s)", path, exc)
        return []
    rules: list[IgnoreRule] = []
    for item in payload.get("rules", []):
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).strip()
        pattern = str(item.get("pattern", "")).strip()
        if kind not in IGNORE_KINDS or not pattern:
            logger.warning("無視ルールを無視しました（kind/pattern が不正）: %r", item)
            continue
        if kind in (KIND_REGEX, KIND_URL) and _compile(pattern) is None:
            logger.warning("無視ルールを無視しました（正規表現が不正）: %r", pattern)
            continue
        rules.append(IgnoreRule(kind=kind, pattern=pattern, note=str(item.get("note", ""))))
    return rules


def apply_ignore_rules(
    diff_result: DiffResult, rules: list[IgnoreRule]
) -> tuple[DiffResult, list[dict[str, Any]]]:
    """ルールに一致する変更を退避し、(除外後のDiffResult, 除外記録) を返す。

    入力の DiffResult は変更しない（immutability）。
    """
    if not rules:
        return diff_result, []

    excluded: list[dict[str, Any]] = []

    def keep(change: Any, target: _Target) -> bool:
        rule = _first_match(target, rules)
        if rule is None:
            return True
        excluded.append(
            {
                "category": target.category,
                "label": target.label,
                "url": target.url,
                "rule_kind": rule.kind,
                "rule_pattern": rule.pattern,
                "rule_note": rule.note,
            }
        )
        return False

    added_pages = tuple(
        c for c in diff_result.added_pages if keep(c, _page_target(c, "added_page"))
    )
    removed_pages = tuple(
        c for c in diff_result.removed_pages if keep(c, _page_target(c, "removed_page"))
    )
    field_changes = tuple(c for c in diff_result.field_changes if keep(c, _field_target(c)))
    link_changes = tuple(c for c in diff_result.link_changes if keep(c, _link_target(c)))
    title_changes = tuple(c for c in diff_result.title_changes if keep(c, _title_target(c)))
    attribute_diffs = tuple(c for c in diff_result.attribute_diffs if keep(c, _attribute_target(c)))
    api_changes = tuple(c for c in diff_result.api_changes if keep(c, _api_target(c)))

    filtered = replace(
        diff_result,
        added_pages=added_pages,
        removed_pages=removed_pages,
        field_changes=field_changes,
        link_changes=link_changes,
        title_changes=title_changes,
        attribute_diffs=attribute_diffs,
        api_changes=api_changes,
        has_changes=any((added_pages, removed_pages, field_changes, link_changes, title_changes)),
    )
    return filtered, excluded


def summarize_exclusions(excluded: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """除外記録をルール単位で集計する（レポートの「除外N件」内訳用）。"""
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for item in excluded:
        key = (str(item.get("rule_kind", "")), str(item.get("rule_pattern", "")))
        bucket = buckets.setdefault(
            key,
            {
                "rule_kind": key[0],
                "rule_pattern": key[1],
                "rule_note": str(item.get("rule_note", "")),
                "count": 0,
            },
        )
        bucket["count"] += 1
    return sorted(buckets.values(), key=lambda b: (-int(b["count"]), str(b["rule_pattern"])))


# ─────────────────── 照合 ───────────────────


def _first_match(target: _Target, rules: list[IgnoreRule]) -> IgnoreRule | None:
    for rule in rules:
        if _matches(target, rule):
            return rule
    return None


def _matches(target: _Target, rule: IgnoreRule) -> bool:
    if rule.kind == KIND_FIELD:
        return bool(target.field_name) and target.field_name == rule.pattern
    if rule.kind == KIND_SELECTOR:
        wanted = rule.pattern.lstrip("#")
        return bool(target.element_id) and target.element_id == wanted
    if rule.kind == KIND_URL:
        compiled = _compile(rule.pattern)
        return compiled is not None and bool(target.url) and compiled.search(target.url) is not None
    if rule.kind == KIND_REGEX:
        compiled = _compile(rule.pattern)
        if compiled is None:
            return False
        return any(text and compiled.search(text) is not None for text in target.texts)
    return False


def _compile(pattern: str) -> re.Pattern[str] | None:
    try:
        return re.compile(pattern)
    except re.error:
        return None


# ─────────────────── 変更 → 照合対象 ───────────────────


def _element_id_of(field: Any) -> str:
    return str(getattr(field, "element_id", "") or "")


def _page_target(change: Any, category: str) -> _Target:
    return _Target(
        category=category,
        url=str(change.url),
        field_name="",
        element_id="",
        texts=(str(change.title),),
        label=str(change.url),
    )


def _field_target(change: Any) -> _Target:
    element_id = _element_id_of(change.after) or _element_id_of(change.before)
    return _Target(
        category="field_change",
        url=str(change.page_url),
        field_name=str(change.field_name),
        element_id=element_id,
        texts=(str(change.field_name),),
        label=f"{change.page_url} / {change.field_name}",
    )


def _link_target(change: Any) -> _Target:
    return _Target(
        category="link_change",
        url=str(change.page_url),
        field_name="",
        element_id="",
        texts=(str(change.link),),
        label=f"{change.page_url} → {change.link}",
    )


def _title_target(change: Any) -> _Target:
    return _Target(
        category="title_change",
        url=str(change.url),
        field_name="",
        element_id="",
        texts=(str(change.before), str(change.after)),
        label=str(change.url),
    )


def _attribute_target(change: Any) -> _Target:
    return _Target(
        category="attribute_diff",
        url=str(change.page_url),
        field_name=str(change.field_name),
        element_id="",
        texts=(str(change.before), str(change.after)),
        label=f"{change.page_url} / {change.field_name}.{change.attribute}",
    )


def _api_target(change: Any) -> _Target:
    return _Target(
        category="api_change",
        url=str(change.page_url),
        field_name="",
        element_id="",
        texts=(str(change.path),),
        label=f"{change.method} {change.path}",
    )
