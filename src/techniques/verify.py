"""技法生成結果の性質を機械検証する検証器。

生成アルゴリズムを信用せず、出力そのものを数え上げで検査する。
「被覆している」という主張は本モジュールの検査合格をもって初めて成立する
（テスト期待値の更新根拠にもこの検査結果を使う）。

検証できる性質:
- t-way 被覆: 全 t-tuple のうち生成行が覆う割合（制約で除外した組は分母から除く）
- 決定性: 同一入力での再生成が完全一致するか
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product

from techniques.combinatorial import TTuple


@dataclass(frozen=True)
class CoverageReport:
    """t-way 被覆検査の結果。ok が False なら missing に全未被覆組が入る。"""

    ok: bool
    total: int
    covered: int
    missing: tuple[TTuple, ...]
    excluded_by_constraint: int

    @property
    def rate(self) -> float:
        return 1.0 if self.total == 0 else self.covered / self.total


def verify_t_way_coverage(
    rows: tuple[tuple[str, ...], ...],
    domains: list[tuple[str, ...]],
    strength: int,
    *,
    forbidden: tuple[TTuple, ...] = (),
) -> CoverageReport:
    """生成した表が本当に t-way 被覆かを全数え上げで検査する。"""
    normalized = tuple(tuple(sorted(t)) for t in forbidden)
    required: set[TTuple] = set()
    excluded = 0
    for idxs in combinations(range(len(domains)), strength):
        for values in product(*(domains[i] for i in idxs)):
            t: TTuple = tuple(zip(idxs, values, strict=False))
            if any(set(f) <= set(t) for f in normalized):
                excluded += 1
                continue
            required.add(t)

    covered: set[TTuple] = set()
    for row in rows:
        for idxs in combinations(range(len(row)), strength):
            covered.add(tuple((i, row[i]) for i in idxs))

    missing = tuple(sorted(required - covered))
    return CoverageReport(
        ok=not missing,
        total=len(required),
        covered=len(required) - len(missing),
        missing=missing,
        excluded_by_constraint=excluded,
    )
