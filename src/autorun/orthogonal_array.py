"""直交表（Orthogonal Arrays）— 均等割付けされた組合せ表を生成する。

ペアワイズ（被覆配列）は「任意の 2 因子の全水準組が最低 1 回現れる」ことだけを保証し、
出現回数は揃わない。直交表はさらに**出現回数が全て等しい**（均等割付け）性質を持つ。
実験計画法の慣習で L9(3^4) のように表記し、日本の SIer 開発では組合せ試験の
標準成果物として要求されることがある。

表は文献から転記せず GF(p) 上の線形構成で**生成**する:

- 行 = GF(p)^k の全ベクトル（p^k 行）
- 列 = 非零ベクトルをスカラー倍で同一視した代表（(p^k - 1)/(p - 1) 列）
- 値 = 行ベクトルと列ベクトルの内積 mod p

相異なる 2 列は比例しないため、行を (列1, 列2) の値へ写す線形写像は全射で
各逆像の大きさが等しい。よって任意の 2 列で全 p^2 組が同数回現れる（強度 2 の直交性）。
この性質は `verify_orthogonality` で実際に検査でき、テストでも検査している。

水準数が列の水準数に満たない因子は水準を畳み込む（level collapsing）。畳み込んだ
因子については均等性が崩れるため、その事実を必ず出力に含める。
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product
from typing import Any

TECHNIQUE_ORTHOGONAL_ARRAY = "直交表"

#: 構成に使う素数の上限。これを超える水準数の因子が混ざる場合は適用しない。
MAX_PRIME = 7
#: 生成する表の行数の上限。超える場合は適用せず、ペアワイズを使うよう促す。
MAX_ROWS = 128


@dataclass(frozen=True)
class OrthogonalArray:
    """生成した直交表。`name` は L{行数}({水準}^{列数}) 表記。"""

    name: str
    levels: int
    rows: tuple[tuple[int, ...], ...]
    column_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "levels": self.levels,
            "row_count": len(self.rows),
            "column_count": self.column_count,
            "rows": [list(r) for r in self.rows],
        }


# =========================================================================
# 表の生成（GF(p) 線形構成）
# =========================================================================
def _is_prime(n: int) -> bool:
    if n < 2:
        return False
    for d in range(2, int(n**0.5) + 1):
        if n % d == 0:
            return False
    return True


def _next_prime_at_least(n: int) -> int | None:
    candidate = max(2, n)
    while candidate <= MAX_PRIME:
        if _is_prime(candidate):
            return candidate
        candidate += 1
    return None


def _column_vectors(prime: int, power: int) -> list[tuple[int, ...]]:
    """非零ベクトルをスカラー倍で同一視した代表（先頭の非零成分が 1）を列挙する。"""
    out: list[tuple[int, ...]] = []
    for vector in product(range(prime), repeat=power):
        first_nonzero = next((v for v in vector if v != 0), 0)
        if first_nonzero == 1:
            out.append(vector)
    return out


def build_array(prime: int, factor_count: int) -> OrthogonalArray | None:
    """水準数 `prime`・因子数 `factor_count` を収容する最小の直交表を生成する。"""
    if not _is_prime(prime):
        return None
    power = 2
    while True:
        row_count = prime**power
        if row_count > MAX_ROWS:
            return None
        columns = _column_vectors(prime, power)
        if len(columns) >= factor_count:
            rows = tuple(
                tuple(
                    sum(r * c for r, c in zip(row_vec, col, strict=True)) % prime
                    for col in columns[:factor_count]
                )
                for row_vec in product(range(prime), repeat=power)
            )
            name = f"L{row_count}({prime}^{factor_count})"
            return OrthogonalArray(
                name=name, levels=prime, rows=rows, column_count=factor_count
            )
        power += 1


def verify_orthogonality(array: OrthogonalArray) -> bool:
    """任意の 2 列で全水準組が同数回現れることを実際に数えて検査する。"""
    if array.column_count < 2:
        return True
    expected = len(array.rows) // (array.levels**2)
    for i, j in combinations(range(array.column_count), 2):
        counts: dict[tuple[int, int], int] = {}
        for row in array.rows:
            key = (row[i], row[j])
            counts[key] = counts.get(key, 0) + 1
        if len(counts) != array.levels**2:
            return False
        if any(count != expected for count in counts.values()):
            return False
    return True


# =========================================================================
# 統合エントリ
# =========================================================================
def _factor_levels(field: dict[str, Any]) -> list[str]:
    """ペアワイズと同じ因子抽出規則を使う（技法間で結果を比較できるようにする）。"""
    field_type = str(field.get("field_type", ""))
    if field_type == "select":
        return [str(o) for o in (field.get("options") or [])][:MAX_PRIME]
    if field_type in ("checkbox", "radio"):
        return ["on", "off"]
    return []


def orthogonal_array(fields: list[dict[str, Any]]) -> dict[str, Any]:
    """選択式項目から直交表による組合せ表を導出する。"""
    factors = [
        (str(f.get("name", "")), levels)
        for f in fields
        if (levels := _factor_levels(f)) and len(levels) >= 2
    ]
    if len(factors) < 2:
        return {
            "applicable": False,
            "technique": TECHNIQUE_ORTHOGONAL_ARRAY,
            "reason": "水準を 2 つ以上持つ選択式項目が 2 つ未満です。",
        }

    max_levels = max(len(levels) for _, levels in factors)
    prime = _next_prime_at_least(max_levels)
    if prime is None:
        return {
            "applicable": False,
            "technique": TECHNIQUE_ORTHOGONAL_ARRAY,
            "reason": (
                f"最大水準数 {max_levels} が上限 {MAX_PRIME} を超えるため、"
                "均等割付けの表を構成できません。ペアワイズを使ってください。"
            ),
        }

    array = build_array(prime, len(factors))
    if array is None:
        return {
            "applicable": False,
            "technique": TECHNIQUE_ORTHOGONAL_ARRAY,
            "reason": (
                f"因子 {len(factors)} 個・水準 {prime} を収容する表が "
                f"{MAX_ROWS} 行を超えます。ペアワイズを使ってください。"
            ),
        }

    collapsed = [name for name, levels in factors if len(levels) < prime]
    cases: list[dict[str, Any]] = []
    for row_index, row in enumerate(array.rows, start=1):
        selection = {
            name: levels[row[col] % len(levels)]
            for col, (name, levels) in enumerate(factors)
        }
        cases.append({"case": f"OA{row_index}", "selection": selection})

    return {
        "applicable": True,
        "technique": TECHNIQUE_ORTHOGONAL_ARRAY,
        "array": array.name,
        "orthogonal": verify_orthogonality(array),
        "factors": {name: levels for name, levels in factors},
        "case_count": len(cases),
        "cases": cases,
        "coverage": (
            f"{array.name} による均等割付け。任意の 2 因子について全水準組が"
            f" {len(array.rows) // (array.levels ** 2)} 回ずつ現れる"
        ),
        "collapsed_factors": collapsed,
        "notice": (
            "水準数が表より少ない項目（"
            + "、".join(collapsed)
            + "）は水準を畳み込んだため、その項目に限り出現回数は均等にならない。"
            if collapsed
            else ""
        ),
    }
