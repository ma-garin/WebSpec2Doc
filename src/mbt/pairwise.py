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

from itertools import combinations
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
    """全ての値ペアを最低1回含む行集合を構築する（決定的）。

    正準実装 techniques.combinatorial（決定的な貪欲 AETG 系）への委譲。
    旧実装は同一アルゴリズムの重複だったため本体を削除した。
    2-way 被覆は techniques.verify.verify_t_way_coverage で機械検証できる。
    """
    from techniques.combinatorial import generate_covering_array

    if len(factors) < MIN_FACTORS:
        return []
    names = [f["name"] for f in factors]
    values = [tuple(f["values"]) for f in factors]
    result = generate_covering_array(list(values), 2)
    return [dict(zip(names, row, strict=True)) for row in result.rows]


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


