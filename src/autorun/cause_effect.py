"""原因結果グラフ法（Cause-Effect Graphing）— 条件と結果の論理関係を明示する。

デシジョンテーブルは規則を並べるだけで「なぜその規則になるか」の論理を持たない。
原因結果グラフは入力条件（原因）と出力（結果）を論理ゲートで結び、そこから
デシジョンテーブルを導出する。Myers, "The Art of Software Testing" の古典的技法で、
条件間の制約（E/I/O/R/M）を表現できる点がデシジョンテーブル単独との差になる。

本モジュールの原因・結果・制約はすべて DOM 実測から導く:

- 原因 = 項目ごとの検証条件（必須充足 / 形式一致 / 長さ上限内 / 範囲内）
- 結果 = 送信受理、および条件違反ごとのエラー表示
- 制約 = radio グループの O（唯一1つ）、必須未入力が形式検査を隠す M（マスク）

観測されていない条件は作らない（evidence-only）。生成は純関数で決定的。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TECHNIQUE_CAUSE_EFFECT = "原因結果グラフ"

#: 制約記号。ISTQB / Myers の慣習に合わせる。
CONSTRAINT_EXCLUSIVE = "E"  # 同時に真になれない
CONSTRAINT_INCLUSIVE = "I"  # 少なくとも1つは真
CONSTRAINT_ONE_ONLY = "O"  # ちょうど1つだけ真
CONSTRAINT_REQUIRES = "R"  # 一方が真なら他方も真
CONSTRAINT_MASKS = "M"  # 一方が真なら他方の結果は現れない

_SKIP_FIELD_TYPES = frozenset({"hidden", "submit", "button", "reset", "image"})


@dataclass(frozen=True)
class Cause:
    """入力条件（原因）。真のとき「条件を満たしている」を意味する。"""

    cause_id: str
    field: str
    description: str
    source_attribute: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.cause_id,
            "field": self.field,
            "description": self.description,
            "source_attribute": self.source_attribute,
        }


@dataclass(frozen=True)
class Effect:
    """出力（結果）。"""

    effect_id: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.effect_id, "description": self.description}


@dataclass(frozen=True)
class Node:
    """原因から結果へのゲート。`operator` は AND / NOT。"""

    effect_id: str
    operator: str
    causes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "effect": self.effect_id,
            "operator": self.operator,
            "causes": list(self.causes),
        }


@dataclass(frozen=True)
class Constraint:
    """原因どうしの制約。"""

    kind: str
    members: tuple[str, ...]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "members": list(self.members),
            "description": self.description,
        }


@dataclass(frozen=True)
class CauseEffectGraph:
    causes: tuple[Cause, ...]
    effects: tuple[Effect, ...]
    nodes: tuple[Node, ...]
    constraints: tuple[Constraint, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "causes": [c.to_dict() for c in self.causes],
            "effects": [e.to_dict() for e in self.effects],
            "nodes": [n.to_dict() for n in self.nodes],
            "constraints": [c.to_dict() for c in self.constraints],
        }


# =========================================================================
# 構築
# =========================================================================
def _field_name(field: dict[str, Any]) -> str:
    return str(field.get("name") or field.get("label") or "")


def _conditions_of(field: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(条件の説明, 違反時の結果の説明, 根拠属性) を実測属性から導く。"""
    name = _field_name(field)
    out: list[tuple[str, str, str]] = []
    if field.get("required"):
        out.append((f"「{name}」が入力されている", f"「{name}」の必須エラーが表示される", "required"))
    if field.get("maxlength") not in (None, ""):
        limit = field["maxlength"]
        out.append(
            (
                f"「{name}」が {limit} 文字以内である",
                f"「{name}」の文字数超過エラーが表示される",
                f"maxlength={limit}",
            )
        )
    if field.get("minlength") not in (None, ""):
        limit = field["minlength"]
        out.append(
            (
                f"「{name}」が {limit} 文字以上である",
                f"「{name}」の文字数不足エラーが表示される",
                f"minlength={limit}",
            )
        )
    if field.get("min_value") not in (None, "") or field.get("max_value") not in (None, ""):
        low = field.get("min_value", "")
        high = field.get("max_value", "")
        out.append(
            (
                f"「{name}」が範囲（{low}〜{high}）内である",
                f"「{name}」の範囲外エラーが表示される",
                f"min={low} / max={high}",
            )
        )
    if field.get("pattern"):
        out.append(
            (
                f"「{name}」が形式（pattern）に一致する",
                f"「{name}」の形式エラーが表示される",
                f"pattern={field['pattern']}",
            )
        )
    elif str(field.get("field_type", "")) in ("email", "tel", "url", "date"):
        field_type = str(field.get("field_type"))
        out.append(
            (
                f"「{name}」が {field_type} の形式に一致する",
                f"「{name}」の形式エラーが表示される",
                f"type={field_type}",
            )
        )
    return out


def build_graph(fields: list[dict[str, Any]]) -> CauseEffectGraph:
    """実測項目から原因結果グラフを構築する。"""
    causes: list[Cause] = []
    effects: list[Effect] = []
    nodes: list[Node] = []
    constraints: list[Constraint] = []
    per_field_causes: dict[str, list[str]] = {}

    counter = 0
    for field in fields:
        if str(field.get("field_type", "")) in _SKIP_FIELD_TYPES:
            continue
        name = _field_name(field)
        for description, effect_text, attribute in _conditions_of(field):
            counter += 1
            cause_id = f"C{counter}"
            effect_id = f"E{counter}"
            causes.append(Cause(cause_id, name, description, attribute))
            effects.append(Effect(effect_id, effect_text))
            nodes.append(Node(effect_id, "NOT", (cause_id,)))
            per_field_causes.setdefault(name, []).append(cause_id)

    if causes:
        effects.append(Effect("E0", "送信が受理される"))
        nodes.append(Node("E0", "AND", tuple(c.cause_id for c in causes)))

    # 必須未入力は、同じ項目の形式・長さ検査の結果を隠す（M 制約）。
    for name, ids in per_field_causes.items():
        if len(ids) > 1:
            constraints.append(
                Constraint(
                    CONSTRAINT_MASKS,
                    tuple(ids),
                    f"「{name}」が未入力のとき、同項目の形式・長さの結果は現れない",
                )
            )

    # radio グループは選択肢のうち唯一1つだけが真になる（O 制約）。
    radio_groups: dict[str, list[str]] = {}
    for field in fields:
        if str(field.get("field_type", "")) == "radio":
            radio_groups.setdefault(_field_name(field), []).extend(
                per_field_causes.get(_field_name(field), [])
            )
    for name, ids in radio_groups.items():
        if ids:
            constraints.append(
                Constraint(
                    CONSTRAINT_ONE_ONLY,
                    tuple(ids),
                    f"「{name}」は選択肢のうちちょうど1つだけが選択される",
                )
            )

    return CauseEffectGraph(
        causes=tuple(causes),
        effects=tuple(effects),
        nodes=tuple(nodes),
        constraints=tuple(constraints),
    )


def derive_decision_table(graph: CauseEffectGraph) -> tuple[dict[str, Any], ...]:
    """グラフから判定表を導く。全真の 1 規則 + 各原因を単独で偽にする n 規則。

    全組合せ 2^n を採らないのは、M 制約により多くの組合せが観測不能
    （マスクされて結果が現れない）になり、規則として検証できないため。
    """
    if not graph.causes:
        return ()
    ids = [c.cause_id for c in graph.causes]
    rules: list[dict[str, Any]] = [
        {
            "rule": "R1",
            "conditions": dict.fromkeys(ids, True),
            "effect": "E0",
            "expected": "送信が受理される",
        }
    ]
    effect_by_cause = {n.causes[0]: n.effect_id for n in graph.nodes if n.operator == "NOT"}
    effect_text = {e.effect_id: e.description for e in graph.effects}
    for index, cause_id in enumerate(ids, start=2):
        effect_id = effect_by_cause.get(cause_id, "")
        rules.append(
            {
                "rule": f"R{index}",
                "conditions": {i: (i != cause_id) for i in ids},
                "effect": effect_id,
                "expected": effect_text.get(effect_id, "エラーが表示される"),
            }
        )
    return tuple(rules)


# =========================================================================
# 統合エントリ
# =========================================================================
def cause_effect_graph(fields: list[dict[str, Any]]) -> dict[str, Any]:
    """`techniques.apply_all` から呼ぶ辞書インタフェース。"""
    graph = build_graph(fields)
    if not graph.causes:
        return {
            "applicable": False,
            "technique": TECHNIQUE_CAUSE_EFFECT,
            "reason": "検証条件を構成できる属性（required / maxlength / pattern 等）が観測されていません。",
        }
    rules = derive_decision_table(graph)
    return {
        "applicable": True,
        "technique": TECHNIQUE_CAUSE_EFFECT,
        "graph": graph.to_dict(),
        "rules": list(rules),
        "cause_count": len(graph.causes),
        "effect_count": len(graph.effects),
        "constraint_count": len(graph.constraints),
        "case_count": len(rules),
        "coverage": (
            f"原因 {len(graph.causes)} 件・結果 {len(graph.effects)} 件を "
            f"{len(rules)} 規則で検証（各原因を単独で偽にする規則被覆）"
        ),
    }
