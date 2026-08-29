"""ドメイン分析（Domain Analysis）— 境界を ON/OFF/IN/OUT の 4 点で体系化する。

境界値分析は「境界とその前後」を並べるだけで、境界がその領域に**含まれるか**
（閉境界か開境界か）を明示しない。ドメイン分析は 1 つの境界につき

- ON  点: 境界そのものの値
- OFF 点: 境界のすぐ外側（開閉が逆側になる最小の値）
- IN  点: 領域の内側の代表値（境界から離れた典型値）
- OUT 点: 領域の外側の代表値（境界から離れた典型値）

の 4 点を定め、「1 つの境界だけを外し、他は正常」という 1x1 ドメイン行列を作る。
Beizer / Binder のドメインテスト、ISTQB CTAL-TA のドメイン分析に対応する。

境界は DOM 実測属性（min / max / minlength / maxlength）からのみ取る。
属性が無い項目には行を作らない（evidence-only）。生成は純関数で決定的。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TECHNIQUE_DOMAIN_ANALYSIS = "ドメイン分析"

#: IN / OUT の代表点を境界からどれだけ離すか。1 だと OFF 点と重なり区別が消える。
TYPICAL_OFFSET = 10
#: 文字列長の代表値を作るときの繰り返し文字。
_FILL_CHAR = "x"
#: 表に文字列リテラルを埋め込む上限。超えたら文字数表記に落とす。
MAX_LITERAL_LENGTH = 200

_SKIP_FIELD_TYPES = frozenset({"hidden", "submit", "button", "reset", "image"})


@dataclass(frozen=True)
class DomainRow:
    """1 つの境界に対する 1x1 ドメイン行列の 1 行。"""

    field: str
    boundary: str  # 例: "下限" / "上限" / "最小長" / "最大長"
    relation: str  # 例: "値 >= 10"
    on_point: str
    off_point: str
    in_point: str
    out_point: str
    on_valid: bool
    off_valid: bool
    source_attribute: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "boundary": self.boundary,
            "relation": self.relation,
            "on": {"value": self.on_point, "valid": self.on_valid},
            "off": {"value": self.off_point, "valid": self.off_valid},
            "in": {"value": self.in_point, "valid": True},
            "out": {"value": self.out_point, "valid": False},
            "source_attribute": self.source_attribute,
        }


def _to_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    number = _to_number(value)
    return None if number is None else int(number)


def _num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _text_of_length(length: int) -> str:
    if length < 0:
        return ""
    if length > MAX_LITERAL_LENGTH:
        return f"{_FILL_CHAR * MAX_LITERAL_LENGTH}…（合計{length}文字）"
    return _FILL_CHAR * length


def _field_name(field: dict[str, Any]) -> str:
    return str(field.get("name") or field.get("label") or "")


# =========================================================================
# 行の導出
# =========================================================================
def domain_rows(field: dict[str, Any]) -> tuple[DomainRow, ...]:
    """1 項目の実測属性から、境界ごとのドメイン行を導く。"""
    name = _field_name(field)
    rows: list[DomainRow] = []

    low = _to_number(field.get("min_value"))
    if low is not None:
        rows.append(
            DomainRow(
                field=name,
                boundary="下限",
                relation=f"値 >= {_num(low)}",
                on_point=_num(low),
                off_point=_num(low - 1),
                in_point=_num(low + TYPICAL_OFFSET),
                out_point=_num(low - TYPICAL_OFFSET),
                on_valid=True,
                off_valid=False,
                source_attribute=f"min={field.get('min_value')}",
            )
        )

    high = _to_number(field.get("max_value"))
    if high is not None:
        rows.append(
            DomainRow(
                field=name,
                boundary="上限",
                relation=f"値 <= {_num(high)}",
                on_point=_num(high),
                off_point=_num(high + 1),
                in_point=_num(high - TYPICAL_OFFSET),
                out_point=_num(high + TYPICAL_OFFSET),
                on_valid=True,
                off_valid=False,
                source_attribute=f"max={field.get('max_value')}",
            )
        )

    min_length = _to_int(field.get("minlength"))
    if min_length is not None:
        rows.append(
            DomainRow(
                field=name,
                boundary="最小長",
                relation=f"文字数 >= {min_length}",
                on_point=_text_of_length(min_length),
                off_point=_text_of_length(max(0, min_length - 1)),
                in_point=_text_of_length(min_length + TYPICAL_OFFSET),
                out_point=_text_of_length(max(0, min_length - TYPICAL_OFFSET)),
                on_valid=True,
                off_valid=min_length == 0,
                source_attribute=f"minlength={min_length}",
            )
        )

    max_length = _to_int(field.get("maxlength"))
    if max_length is not None:
        rows.append(
            DomainRow(
                field=name,
                boundary="最大長",
                relation=f"文字数 <= {max_length}",
                on_point=_text_of_length(max_length),
                off_point=_text_of_length(max_length + 1),
                in_point=_text_of_length(max(0, max_length - TYPICAL_OFFSET)),
                out_point=_text_of_length(max_length + TYPICAL_OFFSET),
                on_valid=True,
                off_valid=False,
                source_attribute=f"maxlength={max_length}",
            )
        )

    return tuple(rows)


def one_by_one_cases(rows: tuple[DomainRow, ...]) -> tuple[dict[str, Any], ...]:
    """1x1 ドメイン行列: 1 つの境界だけを外し、他の項目は IN 点に置くケース群。"""
    cases: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        cases.append(
            {
                "case": f"DA{index}",
                "field": row.field,
                "boundary": row.boundary,
                "point": "ON",
                "value": row.on_point,
                "expected_valid": row.on_valid,
                "expected": "受理される" if row.on_valid else "拒否される",
                "others": "他の項目はすべて IN 点（領域内の典型値）",
                "rationale": f"{row.relation} の境界そのもの（{row.source_attribute}）",
            }
        )
        cases.append(
            {
                "case": f"DA{index}-OFF",
                "field": row.field,
                "boundary": row.boundary,
                "point": "OFF",
                "value": row.off_point,
                "expected_valid": row.off_valid,
                "expected": "受理される" if row.off_valid else "拒否される",
                "others": "他の項目はすべて IN 点（領域内の典型値）",
                "rationale": f"{row.relation} の直外（{row.source_attribute}）",
            }
        )
    return tuple(cases)


# =========================================================================
# 統合エントリ
# =========================================================================
def domain_analysis(fields: list[dict[str, Any]]) -> dict[str, Any]:
    """`techniques.apply_all` から呼ぶ辞書インタフェース。"""
    rows: list[DomainRow] = []
    for field in fields:
        if str(field.get("field_type", "")) in _SKIP_FIELD_TYPES:
            continue
        rows.extend(domain_rows(field))
    if not rows:
        return {
            "applicable": False,
            "technique": TECHNIQUE_DOMAIN_ANALYSIS,
            "reason": "境界を持つ属性（min / max / minlength / maxlength）が観測されていません。",
        }
    cases = one_by_one_cases(tuple(rows))
    return {
        "applicable": True,
        "technique": TECHNIQUE_DOMAIN_ANALYSIS,
        "matrix": [r.to_dict() for r in rows],
        "cases": list(cases),
        "boundary_count": len(rows),
        "case_count": len(cases),
        "coverage": (
            f"1x1 ドメイン行列: {len(rows)} 境界について ON/OFF 点を個別に検証"
            "（IN/OUT 点は各行に併記）"
        ),
    }
