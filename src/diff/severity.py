"""差分の重要度スコアリング（ルールベース・決定的）。

同じ差分でも「画面が消えた」と「見出しの文言が変わった」では読む優先度が違う。
ここでは各変更に重要度と**根拠文言**を付け、レポートで並べ替えられるようにする。

方針:
- LLM を使わない。同一入力なら常に同一出力（決定的）であること。
- 重要度は必ず根拠とセットで返す。根拠なしの数値は価値判断に見えてしまうため。
- 語彙は differ.py の SEVERITY_BREAKING / WARNING / INFO に揃える（新語彙を作らない）。

主張境界: ここで付くのは「ルールが分類した結果」であり、変更が安全か危険かの判断ではない。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from diff.differ import (
    CHANGE_ADDED,
    CHANGE_REMOVED,
    SEVERITY_BREAKING,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)

if TYPE_CHECKING:
    from diff.differ import DiffResult
    from diff.impact_analyzer import ImpactedTest

SEVERITY_ORDER = {SEVERITY_BREAKING: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}

CLAIM_SCOPE = "rule_based_classification_only"


def score_changes(
    diff_result: DiffResult, impacted: list[ImpactedTest] | None = None
) -> list[dict[str, Any]]:
    """各変更に重要度と根拠を付け、重要度順（同率は種別・対象順）で返す。"""
    impact_counts = _impact_counts(impacted or [])
    scored: list[dict[str, Any]] = []

    for change in diff_result.removed_pages:
        scored.append(
            _entry(
                "removed_page",
                SEVERITY_BREAKING,
                "画面が削除され、到達できない経路が発生",
                str(change.url),
                str(change.url),
                impact_counts,
            )
        )

    for change in diff_result.added_pages:
        scored.append(
            _entry(
                "added_page",
                SEVERITY_INFO,
                "画面の追加（既存経路への影響なし）",
                str(change.url),
                str(change.url),
                impact_counts,
            )
        )

    for change in diff_result.field_changes:
        severity, reason = _field_change_verdict(change)
        scored.append(
            _entry(
                "field_change",
                severity,
                reason,
                str(change.page_url),
                f"{change.page_url} / {change.field_name}",
                impact_counts,
            )
        )

    for change in diff_result.attribute_diffs:
        severity, reason = _attribute_verdict(change)
        scored.append(
            _entry(
                "attribute_diff",
                severity,
                reason,
                str(change.page_url),
                f"{change.page_url} / {change.field_name}.{change.attribute}",
                impact_counts,
            )
        )

    for change in diff_result.link_changes:
        removed = str(change.change_type) == CHANGE_REMOVED
        scored.append(
            _entry(
                "link_change",
                SEVERITY_WARNING if removed else SEVERITY_INFO,
                "遷移リンクの削除により到達経路が減少" if removed else "遷移リンクの追加",
                str(change.page_url),
                f"{change.page_url} → {change.link}",
                impact_counts,
            )
        )

    for change in diff_result.title_changes:
        scored.append(
            _entry(
                "title_change",
                SEVERITY_INFO,
                "表示文言の変化",
                str(change.url),
                str(change.url),
                impact_counts,
            )
        )

    for change in diff_result.api_changes:
        severity, reason = _api_verdict(str(change.change_type))
        scored.append(
            _entry(
                "api_change",
                severity,
                reason,
                str(change.page_url),
                f"{change.method} {change.path}",
                impact_counts,
            )
        )

    return sorted(
        scored,
        key=lambda item: (
            SEVERITY_ORDER.get(str(item["severity"]), 9),
            str(item["category"]),
            str(item["label"]),
        ),
    )


def summarize_severity(scored: list[dict[str, Any]]) -> dict[str, int]:
    """重要度ごとの件数（レポート冒頭のバッジ用）。"""
    summary = {SEVERITY_BREAKING: 0, SEVERITY_WARNING: 0, SEVERITY_INFO: 0}
    for item in scored:
        key = str(item.get("severity", ""))
        if key in summary:
            summary[key] += 1
    return summary


def summarize_change_text(diff_result: DiffResult) -> str:
    """変更全体の要約文をテンプレートで組み立てる（LLM を使わない既定経路）。"""
    parts: list[str] = []
    removed_fields = sum(
        1 for c in diff_result.field_changes if str(c.change_type) == CHANGE_REMOVED
    )
    added_fields = sum(1 for c in diff_result.field_changes if str(c.change_type) == CHANGE_ADDED)
    newly_required = sum(
        1
        for c in diff_result.attribute_diffs
        if str(c.attribute) == "required" and _is_truthy(str(c.after))
    )
    if diff_result.removed_pages:
        parts.append(f"画面 {len(diff_result.removed_pages)} 件が削除")
    if diff_result.added_pages:
        parts.append(f"画面 {len(diff_result.added_pages)} 件が追加")
    if removed_fields:
        parts.append(f"入力項目 {removed_fields} 件が削除")
    if added_fields:
        parts.append(f"入力項目 {added_fields} 件が追加")
    if newly_required:
        parts.append(f"必須化 {newly_required} 件")
    if diff_result.link_changes:
        parts.append(f"リンク変更 {len(diff_result.link_changes)} 件")
    if diff_result.title_changes:
        parts.append(f"文言変更 {len(diff_result.title_changes)} 件")
    if not parts:
        return "検出された変更はありません。"
    return "、".join(parts) + "。"


# ─────────────────── 個別判定 ───────────────────


def _field_change_verdict(change: Any) -> tuple[str, str]:
    change_type = str(change.change_type)
    if change_type == CHANGE_REMOVED:
        return SEVERITY_BREAKING, "入力項目が削除され、送信できる値の範囲が狭まった"
    if change_type == CHANGE_ADDED:
        if _is_required(change.after):
            return SEVERITY_BREAKING, "必須の入力項目が追加され、従来の送信が通らなくなる"
        return SEVERITY_INFO, "任意の入力項目が追加"
    return SEVERITY_WARNING, "入力項目の定義が変化"


def _attribute_verdict(change: Any) -> tuple[str, str]:
    attribute = str(change.attribute)
    if attribute == "required" and _is_truthy(str(change.after)):
        return SEVERITY_BREAKING, "任意項目が必須化され、従来の入力が受け付けられなくなる"
    if attribute in ("field_type", "pattern", "options"):
        return SEVERITY_WARNING, f"{attribute} の変更により受け付ける値が変化"
    if attribute in ("maxlength", "minlength", "min_value", "max_value"):
        return SEVERITY_WARNING, f"{attribute} の変更により入力制約が変化"
    return SEVERITY_INFO, f"{attribute} の変更"


def _api_verdict(change_type: str) -> tuple[str, str]:
    if change_type == CHANGE_REMOVED:
        return SEVERITY_BREAKING, "呼び出していた API が消失"
    if change_type == CHANGE_ADDED:
        return SEVERITY_INFO, "API 呼び出しの追加"
    return SEVERITY_WARNING, "API 呼び出しの変化"


# ─────────────────── 補助 ───────────────────


def _entry(
    category: str,
    severity: str,
    reason: str,
    page_url: str,
    label: str,
    impact_counts: dict[str, int],
) -> dict[str, Any]:
    count = impact_counts.get(page_url, 0)
    if count:
        severity = SEVERITY_BREAKING
        reason = f"{reason}（影響テスト {count} 件）"
    return {
        "category": category,
        "severity": severity,
        "reason": reason,
        "page_url": page_url,
        "label": label,
        "impacted_test_count": count,
        "claim_scope": CLAIM_SCOPE,
    }


def _impact_counts(impacted: list[ImpactedTest]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for test in impacted:
        url = str(getattr(test, "page_url", ""))
        if url:
            counts[url] = counts.get(url, 0) + 1
    return counts


def _is_required(field: Any) -> bool:
    return bool(getattr(field, "required", False))


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes", "required", "必須"}
