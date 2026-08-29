"""画面別テスト設計 — 1画面で「何を確認するか」を条件として列挙する。

既存の `/api/test-design` は技法ごとの具体ケース（入力値・期待結果）を返すが、
画面を開いた人が最初に知りたいのは「この画面では何を確認するのか」である。
本モジュールは入力項目だけでなく、見出し・ボタン・遷移・画面全体という
非入力要素からも条件を導出する（入力項目が0件の画面でも条件が出る）。

対象へのアクセスは発生しない（観測済み report.json のみを使う純関数群）。
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

TECHNIQUE_DISPLAY = "表示確認"
TECHNIQUE_STATE_TRANSITION = "状態遷移"
TECHNIQUE_INPUT_VALIDATION = "入力値検証"
TECHNIQUE_EQUIVALENCE = "同値分割"
TECHNIQUE_BOUNDARY = "境界値分析"

#: `apply_all` の技法ブロックキー → 表示名（applicable=False の場合 technique キーが無いため）
_BLOCK_TECHNIQUES: tuple[tuple[str, str], ...] = (
    ("decision_table", "デシジョンテーブル"),
    ("pairwise", "ペアワイズ"),
    ("classification_tree", "分類ツリー法"),
    ("orthogonal_array", "直交表"),
    ("cause_effect", "原因結果グラフ"),
    ("domain_analysis", "ドメイン分析"),
    ("error_guessing", "エラー推測"),
)
# ブロック技法のうち、テストケース表に行が生まれるものだけ（P2-5）。
# generator/testcase_table.py の _dt_rows / _pairwise_rows に対応する。
_BLOCK_TRACE_SUFFIX: dict[str, str] = {"デシジョンテーブル": "DT", "ペアワイズ": "PW"}

#: 言語パス（/ja・/en-US 等）の判定
_LANG_SEGMENT = re.compile(r"^[a-z]{2}(-[A-Za-z]{2,4})?$")

_CLASS_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cc-req", ("必須",)),
    ("cc-bound", ("最大長", "最小長", "範囲", "境界")),
    ("cc-format", ("形式", "メール", "パターン", "日付", "電話", "数値", "パスワード")),
    ("cc-opt", ("選択肢", "ON / OFF", "未選択")),
)


def cond_class(text: str) -> str:
    """条件文をクラス分けする（static/js/view-overview.js の condClass と同じ規則）。"""
    for name, keywords in _CLASS_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return name
    return "cc-other"


def _condition(
    condition: str,
    source_kind: str,
    source_name: str,
    technique: str,
    trace_target: str = "",
) -> dict[str, Any]:
    """テスト条件 1 件。

    trace_target は遷移条件の遷移先 page_id。condition_id を組むときだけ使う
    （表示名は source_name に入れるため、page_id はここで別に持つ）。
    """
    return {
        "condition": condition,
        "source_kind": source_kind,
        "source_name": source_name,
        "technique": technique,
        "cond_class": cond_class(condition),
        "trace_target": trace_target,
    }


def _screen_fields(screen: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        field
        for form in (screen.get("forms") or [])
        if isinstance(form, dict)
        for field in (form.get("fields") or [])
        if isinstance(field, dict) and field.get("field_type") != "hidden"
    ]


def _field_name(field: dict[str, Any]) -> str:
    return str(field.get("name") or field.get("label") or "（無名項目）")


def _has_language_path(url: str) -> bool:
    """URL に言語パス（/ja・/en-US 等）が含まれるか。"""
    segments = [s for s in urlparse(url).path.split("/") if s]
    return any(_LANG_SEGMENT.match(s) for s in segments)


# ─────────────────── 非入力要素由来 ───────────────────


def _screen_wide_conditions(screen: dict[str, Any]) -> list[dict[str, Any]]:
    """画面全体に対する条件。観測できた事実からのみ作る（推測しない）。"""
    if not _has_language_path(str(screen.get("url", ""))):
        return []
    return [
        _condition(
            "言語が切り替わる",
            "画面",
            "（画面全体）",
            TECHNIQUE_DISPLAY,
        )
    ]


def _element_conditions(screen: dict[str, Any], titles: dict[str, str]) -> list[dict[str, Any]]:
    """見出し・ボタン・遷移先リンクから条件を導出する。"""
    conditions: list[dict[str, Any]] = []
    for heading in screen.get("headings") or []:
        text = str(heading).strip()
        if text:
            conditions.append(
                _condition(f"見出し「{text}」が表示される", "見出し", text, TECHNIQUE_DISPLAY)
            )
    for button in screen.get("buttons") or []:
        text = str(button).strip()
        if text:
            conditions.append(
                _condition(
                    f"{text} をクリックすると遷移する",
                    "ボタン",
                    text,
                    TECHNIQUE_STATE_TRANSITION,
                )
            )
    transitions = screen.get("transitions")
    targets = (transitions or {}).get("to") or [] if isinstance(transitions, dict) else []
    for target in targets:
        page_id = str(target)
        name = titles.get(page_id) or page_id
        conditions.append(
            _condition(
                f"{name} へ遷移する",
                "リンク",
                name,
                TECHNIQUE_STATE_TRANSITION,
                trace_target=page_id,
            )
        )
    return conditions


def _input_conditions(screen: dict[str, Any]) -> list[dict[str, Any]]:
    """クローラが観測した入力項目のテスト条件（report.json 由来）。"""
    conditions: list[dict[str, Any]] = []
    for field in _screen_fields(screen):
        name = _field_name(field)
        for raw in field.get("test_conditions") or []:
            text = str(raw).strip()
            if text:
                conditions.append(_condition(text, "入力項目", name, TECHNIQUE_INPUT_VALIDATION))
    return conditions


# ─────────────────── 技法エンジン由来 ───────────────────


def _block_condition_text(key: str, block: dict[str, Any]) -> str | None:
    """適用できた技法ブロックから、条件文（何を確認するか）を1つ作る。"""
    if key == "pairwise":
        factors = block.get("factors") or {}
        return (
            f"選択式項目 {len(factors)}因子の2因子間組合せ "
            f"{int(block.get('required_pairs') or 0)}ペアを網羅する"
        )
    if key == "classification_tree":
        return f"分類ツリーの全クラス {int(block.get('class_count') or 0)}件を1回以上通る"
    if key == "orthogonal_array":
        array = str(block.get("array") or "直交表")
        return f"{array} による {int(block.get('case_count') or 0)}通りの組合せで異常が出ない"
    if key == "cause_effect":
        return (
            f"原因 {int(block.get('cause_count') or 0)}件と結果 "
            f"{int(block.get('effect_count') or 0)}件の論理関係が満たされる"
        )
    if key == "domain_analysis":
        return f"境界を持つ属性 {int(block.get('boundary_count') or 0)}件の in/out/on/off が正しい"
    if key == "error_guessing":
        categories = block.get("categories") or []
        return f"エラー推測カテゴリ {len(categories)}種の異常入力で適切に拒否される"
    return None


def _technique_conditions(
    design: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """技法エンジンの結果を、条件リストと適用外リストに分解する。"""
    conditions: list[dict[str, Any]] = []
    unapplied: list[dict[str, str]] = []

    equivalence_used = False
    boundary_used = False
    for entry in design.get("fields") or []:
        name = str(entry.get("field", "")) or "（無名項目）"
        equivalence = entry.get("equivalence") or []
        boundary = entry.get("boundary") or []
        if equivalence:
            equivalence_used = True
            valid = sum(1 for v in equivalence if v.get("valid"))
            conditions.append(
                _condition(
                    f"「{name}」の同値クラス（有効 {valid}件 / 無効 {len(equivalence) - valid}件）"
                    "が正しく判定される",
                    "入力項目",
                    name,
                    TECHNIQUE_EQUIVALENCE,
                )
            )
        if boundary:
            boundary_used = True
            conditions.append(
                _condition(
                    f"「{name}」の境界値 {len(boundary)}点が正しく判定される",
                    "入力項目",
                    name,
                    TECHNIQUE_BOUNDARY,
                )
            )
    if not equivalence_used:
        unapplied.append(
            {
                "technique": TECHNIQUE_EQUIVALENCE,
                "reason": "同値クラスを構成できる入力項目がありません。",
            }
        )
    if not boundary_used:
        unapplied.append(
            {"technique": TECHNIQUE_BOUNDARY, "reason": "境界を持つ入力項目がありません。"}
        )

    for key, label in _BLOCK_TECHNIQUES:
        block = design.get(key)
        if not isinstance(block, dict):
            continue
        name = str(block.get("technique") or label)
        if not block.get("applicable"):
            unapplied.append(
                {"technique": name, "reason": str(block.get("reason") or "適用対象がありません。")}
            )
            continue
        if key == "decision_table":
            for rule in block.get("rules") or []:
                action = str(rule.get("action", "")).strip()
                if action:
                    conditions.append(
                        _condition(
                            f"{rule.get('rule', '')}: {action}".strip(": "),
                            "フォーム",
                            "（入力フォーム）",
                            name,
                        )
                    )
            continue
        text = _block_condition_text(key, block)
        if text:
            conditions.append(_condition(text, "フォーム", "（入力フォーム）", name))
    return conditions, unapplied


# ─────────────────── 組み立て ───────────────────


def _screen_design(screen: dict[str, Any]) -> dict[str, Any]:
    from autorun.techniques import apply_all

    result: dict[str, Any] = apply_all(screen)
    return result


def condition_id(page_id: str, cond: dict[str, Any]) -> str:
    """この条件を検証するテストケースの trace_id を返す（P2-5）。

    テストケース側は generator/testcase_table.py が既に安定 ID（trace_id）を
    振っている。条件側に同じ規則で ID を振れば、テストケース表のデータ構造を
    変えずに突き合わせられる。**規則を変えるときは両方を直すこと。**

    対応（generator/testcase_table.py の trace_id=... 行と 1 対 1）:
      入力項目          → "{page_id}:{項目名}"   （_bva_rows）
      デシジョンテーブル → "{page_id}:DT"        （_dt_rows）
      ペアワイズ         → "{page_id}:PW"        （_pairwise_rows）
      リンク遷移         → "{page_id}->{遷移先}" （_transition_rows）
      それ以外（表示等） → "{page_id}"           （_display_rows）
    """
    if not page_id:
        return ""
    if cond.get("source_kind") == "入力項目":
        return f"{page_id}:{cond.get('source_name', '')}"
    if cond.get("source_kind") == "リンク" and cond.get("trace_target"):
        return f"{page_id}->{cond['trace_target']}"
    if cond.get("source_kind") == "フォーム":
        # フォーム由来はブロック技法。テストケースを生むのはデシジョンテーブルと
        # ペアワイズだけで、分類ツリー法・直交表・原因結果グラフ等は対応する行が無い。
        # 無いものを既存 ID に寄せると「検証済み」と誤表示するため空 ID（＝対応なし）にする。
        suffix = _BLOCK_TRACE_SUFFIX.get(str(cond.get("technique") or ""))
        return f"{page_id}:{suffix}" if suffix else ""
    return page_id


def build_conditions(
    screen: dict[str, Any], titles: dict[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """1画面のテスト条件と、適用できなかった技法を返す。"""
    conditions = _screen_wide_conditions(screen)
    conditions += _element_conditions(screen, titles)
    conditions += _input_conditions(screen)
    technique_conditions, unapplied = _technique_conditions(_screen_design(screen))
    conditions += technique_conditions

    if not any(c["technique"] == TECHNIQUE_DISPLAY for c in conditions):
        unapplied.append(
            {
                "technique": TECHNIQUE_DISPLAY,
                "reason": "見出し・ボタン等の表示要素が観測されていません。",
            }
        )
    if not any(c["technique"] == TECHNIQUE_STATE_TRANSITION for c in conditions):
        unapplied.append(
            {"technique": TECHNIQUE_STATE_TRANSITION, "reason": "画面遷移が観測されていません。"}
        )

    page_id = str(screen.get("page_id", ""))
    numbered = [dict(c, no=index) for index, c in enumerate(conditions, start=1)]
    ordered = [
        {
            "no": c["no"],
            "condition": c["condition"],
            "source_kind": c["source_kind"],
            "source_name": c["source_name"],
            "technique": c["technique"],
            "cond_class": c["cond_class"],
            "condition_id": condition_id(page_id, c),
        }
        for c in numbered
    ]
    return ordered, unapplied


def _element_count(conditions: list[dict[str, Any]]) -> int:
    """条件を生んだ要素の実数（同じ要素からの複数条件は1つと数える）。"""
    return len({(c["source_kind"], c["source_name"]) for c in conditions})


def _titles(report: dict[str, Any]) -> dict[str, str]:
    return {
        str(s.get("page_id", "")): str(s.get("title") or s.get("page_id") or "")
        for s in (report.get("screens") or [])
        if isinstance(s, dict)
    }


def build_screen_index(report: dict[str, Any]) -> list[dict[str, Any]]:
    """画面リスト（左ペイン用）。画面ごとの要素数・条件数だけを返す。"""
    titles = _titles(report)
    screens: list[dict[str, Any]] = []
    for screen in report.get("screens") or []:
        if not isinstance(screen, dict):
            continue
        conditions, _ = build_conditions(screen, titles)
        screens.append(
            {
                "page_id": str(screen.get("page_id", "")),
                "title": str(screen.get("title") or ""),
                "element_count": _element_count(conditions),
                "condition_count": len(conditions),
            }
        )
    return screens


def build_screen_detail(report: dict[str, Any], page_id: str) -> dict[str, Any] | None:
    """1画面の条件一覧。該当画面が無ければ None。"""
    titles = _titles(report)
    target = next(
        (
            s
            for s in (report.get("screens") or [])
            if isinstance(s, dict) and str(s.get("page_id", "")) == page_id
        ),
        None,
    )
    if target is None:
        return None
    conditions, unapplied = build_conditions(target, titles)
    applied = len({c["technique"] for c in conditions})
    return {
        "page_id": str(target.get("page_id", "")),
        "title": str(target.get("title") or ""),
        "url": str(target.get("url") or ""),
        "summary": {
            "element_count": _element_count(conditions),
            "condition_count": len(conditions),
            "applied_techniques": applied,
            "unapplied_techniques": len(unapplied),
        },
        "conditions": conditions,
        "unapplied": unapplied,
    }
