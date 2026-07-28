"""分類ツリー法（Classification Tree Method）— 階層的な組合せ設計を実測から導く。

ペアワイズは「項目 × 値」の平坦な組合せしか表現できず、1 画面に複数のフォームが
あっても区別しない。分類ツリー法は対象を階層（画面 → フォーム → 項目 → 同値クラス）
へ分解し、葉であるクラスの組合せとしてテストケースを構成する
（Grochtmann & Grimm, "Classification trees for partition testing", 1993）。

本モジュールの階層は実測データだけから作る:

- 第1層 = 画面（root）
- 第2層 = 観測したフォーム（別フォームの項目は同時送信されないため組合せない）
- 第3層 = フォーム内の入力項目（分類 / classification）
- 第4層 = 項目の同値クラス（クラス / class）— `techniques.equivalence_classes` を再利用

観測されていない階層・値は作らない（evidence-only）。生成は純関数で決定的。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autorun.techniques import TECHNIQUE_EQUIVALENCE, equivalence_classes

TECHNIQUE_CLASSIFICATION_TREE = "分類ツリー法"

#: 1 分類あたりに載せるクラスの上限。組合せ行数は最大クラス数で決まるため、
#: 選択肢が極端に多い項目で表が読めなくなるのを防ぐ。切り捨てた事実は必ず報告する。
MAX_CLASSES_PER_CLASSIFICATION = 8

_SKIP_FIELD_TYPES = frozenset({"hidden", "submit", "button", "reset", "image"})


@dataclass(frozen=True)
class TreeClass:
    """分類ツリーの葉。項目が取りうる 1 つの同値クラス。"""

    label: str
    value: str
    valid: bool
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": self.value,
            "valid": self.valid,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class Classification:
    """分類ツリーの内部節点。1 つの入力項目とそのクラス集合。"""

    name: str
    field_type: str
    branch: str  # 所属フォーム（第2層）の識別子
    classes: tuple[TreeClass, ...]
    truncated: int = 0  # 上限で切り捨てたクラス数

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "field_type": self.field_type,
            "branch": self.branch,
            "classes": [c.to_dict() for c in self.classes],
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class TreeBranch:
    """第2層。1 フォーム分の分類集合と、その中で閉じた組合せ表。"""

    branch_id: str
    label: str
    classifications: tuple[Classification, ...]
    combinations: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "label": self.label,
            "classifications": [c.to_dict() for c in self.classifications],
            "combinations": list(self.combinations),
        }


@dataclass(frozen=True)
class ClassificationTree:
    """画面 1 枚分の分類ツリー。"""

    root: str
    branches: tuple[TreeBranch, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"root": self.root, "branches": [b.to_dict() for b in self.branches]}


# =========================================================================
# 構築
# =========================================================================
def build_classification_tree(screen: dict[str, Any]) -> ClassificationTree:
    """1 画面の実測データから分類ツリーを構築する。"""
    root = str(screen.get("page_id", "")) or str(screen.get("url", ""))
    branches: list[TreeBranch] = []
    for index, form in enumerate(screen.get("forms") or [], start=1):
        if not isinstance(form, dict):
            continue
        branch_id = f"form{index}"
        classifications = _classifications_of(form, branch_id)
        if not classifications:
            continue
        branches.append(
            TreeBranch(
                branch_id=branch_id,
                label=_form_label(form, index),
                classifications=classifications,
                combinations=minimal_combinations(classifications),
            )
        )
    return ClassificationTree(root=root, branches=tuple(branches))


def _form_label(form: dict[str, Any], index: int) -> str:
    for key in ("name", "id", "action"):
        value = str(form.get(key) or "").strip()
        if value:
            return value
    return f"フォーム{index}"


def _classifications_of(form: dict[str, Any], branch_id: str) -> tuple[Classification, ...]:
    out: list[Classification] = []
    for field in form.get("fields") or []:
        if not isinstance(field, dict):
            continue
        if str(field.get("field_type", "")) in _SKIP_FIELD_TYPES:
            continue
        classes = _classes_of(field)
        if not classes:
            continue
        truncated = max(0, len(classes) - MAX_CLASSES_PER_CLASSIFICATION)
        out.append(
            Classification(
                name=str(field.get("name") or field.get("label") or ""),
                field_type=str(field.get("field_type", "")),
                branch=branch_id,
                classes=classes[:MAX_CLASSES_PER_CLASSIFICATION],
                truncated=truncated,
            )
        )
    return tuple(out)


def _classes_of(field: dict[str, Any]) -> tuple[TreeClass, ...]:
    """同値分割の結果をそのまま葉に使う（技法間で同値クラスの定義を二重化しない）。"""
    return tuple(
        TreeClass(label=v.label, value=v.value, valid=v.valid, rationale=v.rationale)
        for v in equivalence_classes(field)
        if v.technique == TECHNIQUE_EQUIVALENCE
    )


# =========================================================================
# 組合せ（クラス被覆）
# =========================================================================
def minimal_combinations(
    classifications: tuple[Classification, ...],
) -> tuple[dict[str, Any], ...]:
    """全クラスを最低 1 回通す最小の組合せ表を作る（クラス被覆 / 1-wise）。

    行数は「最もクラス数が多い分類のクラス数」に一致し、これがクラス被覆の下限。
    各分類は自分のクラスを循環させて割り当てるため、同一入力から必ず同一の表が出る。
    """
    if not classifications:
        return ()
    rows_needed = max(len(c.classes) for c in classifications)
    rows: list[dict[str, Any]] = []
    for row_index in range(rows_needed):
        selection: dict[str, str] = {}
        rationales: list[str] = []
        all_valid = True
        for classification in classifications:
            chosen = classification.classes[row_index % len(classification.classes)]
            selection[classification.name] = chosen.label
            if not chosen.valid:
                all_valid = False
                rationales.append(f"{classification.name}: {chosen.rationale}")
        rows.append(
            {
                "case": f"CT{row_index + 1}",
                "selection": selection,
                "expected_valid": all_valid,
                "expected": (
                    "送信が受理される"
                    if all_valid
                    else "拒否され、無効クラスの項目についてエラーが示される"
                ),
                "rationale": "全クラスが有効同値クラス" if all_valid else " / ".join(rationales),
            }
        )
    return tuple(rows)


# =========================================================================
# 統合エントリ
# =========================================================================
def classification_tree(screen: dict[str, Any]) -> dict[str, Any]:
    """`techniques.apply_all` から呼ぶ辞書インタフェース。"""
    tree = build_classification_tree(screen)
    if not tree.branches:
        return {
            "applicable": False,
            "technique": TECHNIQUE_CLASSIFICATION_TREE,
            "reason": "クラスを構成できる入力項目が観測されていません。",
        }
    total_classes = sum(len(c.classes) for b in tree.branches for c in b.classifications)
    total_rows = sum(len(b.combinations) for b in tree.branches)
    truncated = sum(c.truncated for b in tree.branches for c in b.classifications)
    return {
        "applicable": True,
        "technique": TECHNIQUE_CLASSIFICATION_TREE,
        "tree": tree.to_dict(),
        "branch_count": len(tree.branches),
        "classification_count": sum(len(b.classifications) for b in tree.branches),
        "class_count": total_classes,
        "case_count": total_rows,
        "coverage": (
            f"クラス被覆: {total_classes} クラスを {total_rows} ケースで全て 1 回以上通る"
            "（フォームをまたぐ組合せは、同時送信されないため作らない）"
        ),
        "truncated_classes": truncated,
        "notice": (
            f"選択肢が多い項目で {truncated} クラスを表示上限で除外した。" if truncated else ""
        ),
    }
