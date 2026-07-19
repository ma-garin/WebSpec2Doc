"""ペアワイズ法（2因子網羅）による組合せテストデータ生成。

選択肢を持つ項目が n 個あるフォームの全組合せは積で爆発するが、実務上の欠陥の
大半は2因子の相互作用で発現することが経験的に知られている（組合せテストの古典、
IPO/IPOG 系）。ここでは貪欲法で「全ての値ペアを最低1回含む」最小に近い組を作る。

方針:
- 値は**実測した選択肢（options）だけ**を使う。存在しない値を発明しない。
- 決定的であること（同一入力→同一出力）。乱択は使わない。
- 対象は選択肢が確定している項目（select / radio / checkbox）に限る。
  自由入力の代表値化は境界値分析（既存 test_data）の担当で、二重にしない。
"""

from __future__ import annotations

from itertools import combinations, product
from typing import Any

CLAIM_SCOPE = "measured_options_only"

MAX_FACTORS = 12  # 因子過多のフォームは表が読めなくなるため上限を置く
MIN_FACTORS = 2  # ペアが成立しない1因子以下は対象外
CHECKBOX_VALUES = ("on", "off")


def extract_factors(screen: dict[str, Any]) -> list[dict[str, Any]]:
    """画面の実測フォームから、組合せ対象の因子（項目と選択肢）を取り出す。"""
    factors: list[dict[str, Any]] = []
    for form in screen.get("forms", []):
        if not isinstance(form, dict):
            continue
        for field in form.get("fields", []):
            if not isinstance(field, dict):
                continue
            name = str(field.get("name", ""))
            if not name:
                continue
            field_type = str(field.get("field_type", ""))
            options = [str(v) for v in field.get("options", []) if str(v)]
            if field_type in ("select", "radio") and len(options) >= 2:
                factors.append({"name": name, "field_type": field_type, "values": options})
            elif field_type == "checkbox":
                factors.append(
                    {"name": name, "field_type": field_type, "values": list(CHECKBOX_VALUES)}
                )
    return factors[:MAX_FACTORS]


def generate_pairwise_rows(factors: list[dict[str, Any]]) -> list[dict[str, str]]:
    """全ての値ペアを最低1回含む行集合を貪欲法で構築する（決定的）。"""
    if len(factors) < MIN_FACTORS:
        return []
    names = [f["name"] for f in factors]
    values = [f["values"] for f in factors]

    # 覆うべき全ペア: (因子i, 値a, 因子j, 値b)
    uncovered: set[tuple[int, str, int, str]] = set()
    for (i, vi), (j, vj) in combinations(enumerate(values), 2):
        for a, b in product(vi, vj):
            uncovered.add((i, a, j, b))

    rows: list[dict[str, str]] = []
    while uncovered:
        best_row: list[str] | None = None
        best_gain = -1
        # 先頭の未カバーペアを種にし、残り因子を貪欲に決める
        seed = min(uncovered)  # 決定性のため辞書順最小を種とする
        si, sa, sj, sb = seed
        candidate = [""] * len(factors)
        candidate[si], candidate[sj] = sa, sb
        for k in range(len(factors)):
            if candidate[k]:
                continue
            gain_by_value = []
            for v in values[k]:
                trial = list(candidate)
                trial[k] = v
                gain = _covered_count(trial, uncovered)
                gain_by_value.append((gain, v))
            candidate[k] = max(gain_by_value)[1]
        best_row, best_gain = candidate, _covered_count(candidate, uncovered)
        if best_gain <= 0:
            break  # 理論上到達しないが、無限ループは絶対に避ける
        uncovered -= _pairs_of(best_row)
        rows.append(dict(zip(names, best_row, strict=True)))
    return rows


def build_pairwise_cases(report: dict[str, Any]) -> list[dict[str, Any]]:
    """report.json の全画面からペアワイズ組合せケースを生成する。"""
    cases: list[dict[str, Any]] = []
    for screen in report.get("screens", []):
        if not isinstance(screen, dict):
            continue
        factors = extract_factors(screen)
        rows = generate_pairwise_rows(factors)
        if not rows:
            continue
        exhaustive = 1
        for f in factors:
            exhaustive *= len(f["values"])
        page_id = str(screen.get("page_id", ""))
        for index, row in enumerate(rows, 1):
            cases.append(
                {
                    "case_id": f"PW2-{page_id}-{index:03d}",
                    "page_id": page_id,
                    "page_url": str(screen.get("url", "")),
                    "combination": row,
                    "factors": len(factors),
                    "exhaustive_total": exhaustive,
                    "pairwise_total": len(rows),
                    "claim_scope": CLAIM_SCOPE,
                    "evidence": "measured_options",
                }
            )
    return cases


def _pairs_of(row: list[str]) -> set[tuple[int, str, int, str]]:
    return {(i, row[i], j, row[j]) for i, j in combinations(range(len(row)), 2)}


def _covered_count(row: list[str], uncovered: set[tuple[int, str, int, str]]) -> int:
    count = 0
    for i, j in combinations(range(len(row)), 2):
        if row[i] and row[j] and (i, row[i], j, row[j]) in uncovered:
            count += 1
    return count
