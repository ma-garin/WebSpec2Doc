"""組合せテスト（被覆配列生成）の正準実装。

一次出典:
- Cohen, Dalal, Fredman, Patton, "The AETG System: An Approach to Testing
  Based on Combinatorial Design", IEEE Trans. Software Eng. 23(7), 1997.
- Kuhn, Wallace, Gallo, "Software Fault Interactions and Implications for
  Software Testing", IEEE Trans. Software Eng. 30(6), 2004（相互作用ルール:
  実欠陥の大半は少数因子の相互作用で発現する）。
- Kuhn, Kacker, Lei, "Practical Combinatorial Testing", NIST SP 800-142, 2010.

アルゴリズムは AETG 系の貪欲法だが、オリジナルの AETG が乱数候補から
最良行を選ぶのに対し、本実装は種の選択（未被覆 t-tuple の辞書順最小）と
値のタイブレーク（先頭優先）を固定した**決定的**変種である。同一入力から
必ず同一の表が出る（差分比較のため）。この変更によりオリジナルより行数が
増える場合があるが、被覆率 100% は verify.verify_t_way_coverage で機械検証できる。

対応する拡張:
- 制約（forbidden tuples）: 同時に現れてはならない値組を除外して生成する。
  制約により被覆不能になった t-tuple は黙って捨てず `uncoverable` に全件記録する
  （SAT/CSP による完全な充足判定は決定性・依存追加の観点から採らない。
  貪欲充填で行を構成できなかった組を被覆不能として報告する近似である）。
- mixed-strength: 因子部分集合ごとに異なる強度を要求できる
  （CoverageRequirement の列で指定。全体 2-way + 重要3因子だけ 3-way など）。
- seeding: 既存のテスト行を種として渡すと、その行が既に覆う t-tuple を
  差し引いてから不足分だけを生成する（既存ケースの再利用。NIST SP 800-142）。
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product

#: t-tuple の表現: ((因子番号, 値), ...) を因子番号順に並べたもの。
TTuple = tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class CoverageRequirement:
    """被覆要求 1 件。`factor_indices` の部分集合内で強度 `strength` の被覆を求める。

    factor_indices が None なら全因子が対象（通常の t-way）。
    """

    strength: int
    factor_indices: tuple[int, ...] | None = None

    def indices(self, factor_count: int) -> tuple[int, ...]:
        if self.factor_indices is None:
            return tuple(range(factor_count))
        return self.factor_indices


@dataclass(frozen=True)
class CoveringArrayResult:
    """生成結果。行に加えて、制約で被覆できなかった t-tuple を必ず持つ。"""

    rows: tuple[tuple[str, ...], ...]
    #: 制約（forbidden）により行を構成できなかった t-tuple。黙って捨てない。
    uncoverable: tuple[TTuple, ...]
    #: 種行（seeds）が事前に覆っていた t-tuple 数。
    covered_by_seeds: int


# =========================================================================
# 公開 API
# =========================================================================
def generate_covering_array(
    domains: list[tuple[str, ...]],
    strength: int = 2,
    *,
    requirements: tuple[CoverageRequirement, ...] = (),
    forbidden: tuple[TTuple, ...] = (),
    seeds: tuple[tuple[str, ...], ...] = (),
) -> CoveringArrayResult:
    """被覆配列を決定的に生成する。

    Args:
        domains: 因子ごとの水準列。
        strength: 既定の強度（全因子に適用）。requirements を渡すと無視される。
        requirements: mixed-strength 用の被覆要求列。空なら全因子 strength。
        forbidden: 同時に現れてはならない値組（各要素は因子番号順の t-tuple）。
        seeds: 既存テスト行。これらが覆う t-tuple は生成対象から除く。
    """
    if not domains or any(not d for d in domains):
        return CoveringArrayResult(rows=(), uncoverable=(), covered_by_seeds=0)

    reqs = requirements or (CoverageRequirement(strength=strength),)
    normalized_forbidden = tuple(tuple(sorted(t)) for t in forbidden)

    uncovered: set[TTuple] = set()
    for req in reqs:
        indices = req.indices(len(domains))
        if req.strength > len(indices):
            continue
        uncovered |= _all_t_tuples_of(domains, indices, req.strength)

    # 禁止組を部分に含む t-tuple はそもそも被覆対象にしない。
    uncovered = {t for t in uncovered if not _contains_forbidden(t, normalized_forbidden)}

    # mixed-strength では uncovered に異なる長さの t-tuple が混在する。
    # 消し込みは「要求に現れる全強度」それぞれで行う（最大強度だけで消すと、
    # 小さい強度の組が行に覆われても残り続け、被覆不能へ誤分類される）。
    strengths = tuple(sorted({r.strength for r in reqs}))

    covered_by_seeds = 0
    for seed_row in seeds:
        before = len(uncovered)
        uncovered -= _tuples_in_row_multi(seed_row, strengths)
        covered_by_seeds += before - len(uncovered)

    rows: list[tuple[str, ...]] = []
    uncoverable: list[TTuple] = []
    while uncovered:
        target = min(uncovered)  # 決定的な種の選択
        row = _build_row(domains, strengths, uncovered, target, normalized_forbidden)
        if row is None:
            # 貪欲充填では制約を満たす行を構成できなかった。
            # 黙って握り潰さず被覆不能として記録し、次の種へ進む。
            uncovered.discard(target)
            uncoverable.append(target)
            continue
        newly = _tuples_in_row_multi(row, strengths)
        if target not in newly:  # 種を覆えない行は無限ループの芽。構成失敗として扱う。
            uncovered.discard(target)
            uncoverable.append(target)
            continue
        uncovered -= newly
        rows.append(row)
    return CoveringArrayResult(
        rows=tuple(rows),
        uncoverable=tuple(uncoverable),
        covered_by_seeds=covered_by_seeds,
    )


# =========================================================================
# 内部: t-tuple 演算（generator/test_design.py から移設した正準実装）
# =========================================================================
def _all_t_tuples_of(
    domains: list[tuple[str, ...]], indices: tuple[int, ...], strength: int
) -> set[TTuple]:
    tuples: set[TTuple] = set()
    for idxs in combinations(indices, strength):
        for values in product(*(domains[i] for i in idxs)):
            tuples.add(tuple(zip(idxs, values, strict=False)))
    return tuples


def _tuples_in_row(row: tuple[str, ...], strength: int) -> set[TTuple]:
    covered: set[TTuple] = set()
    for idxs in combinations(range(len(row)), strength):
        covered.add(tuple((i, row[i]) for i in idxs))
    return covered


def _tuples_in_row_multi(row: tuple[str, ...], strengths: tuple[int, ...]) -> set[TTuple]:
    """要求に現れる全強度について、行が覆う t-tuple を返す。"""
    covered: set[TTuple] = set()
    for strength in strengths:
        if strength <= len(row):
            covered |= _tuples_in_row(row, strength)
    return covered


def _contains_forbidden(t: TTuple, forbidden: tuple[TTuple, ...]) -> bool:
    entries = set(t)
    return any(set(f) <= entries for f in forbidden)


def _violates(row: list[str | None], idx: int, value: str, forbidden: tuple[TTuple, ...]) -> bool:
    """idx に value を置いたとき、確定済みの列と禁止組を作るか。"""
    assigned = {(j, v) for j, v in enumerate(row) if v is not None and j != idx}
    assigned.add((idx, value))
    return any(set(f) <= assigned for f in forbidden)


def _build_row(
    domains: list[tuple[str, ...]],
    strengths: tuple[int, ...],
    uncovered: set[TTuple],
    seed: TTuple,
    forbidden: tuple[TTuple, ...],
) -> tuple[str, ...] | None:
    """種の t-tuple を固定し、残り列を貪欲に埋める。制約を満たせなければ None。"""
    row: list[str | None] = [None] * len(domains)
    for idx, value in seed:
        row[idx] = value
    for i in range(len(domains)):
        if row[i] is not None:
            continue
        best_value: str | None = None
        best_gain = -1
        for value in domains[i]:
            if _violates(row, i, value, forbidden):
                continue
            gain = _gain(row, i, value, strengths, uncovered)
            if gain > best_gain:  # 先頭優先の決定的タイブレーク
                best_gain = gain
                best_value = value
        if best_value is None:
            return None  # この列に置ける値が無い（制約が強すぎる）
        row[i] = best_value
    return tuple(v for v in row if v is not None)


def _gain(
    row: list[str | None],
    idx: int,
    value: str,
    strengths: tuple[int, ...],
    uncovered: set[TTuple],
) -> int:
    """value を idx に置いたとき、確定済みの列との組で新たに覆う t-tuple 数。

    mixed-strength では全強度の未被覆組を同じ土俵で数える（強度間の重み付けは
    しない。小強度の組は数が少なく早期に尽きるため、実質的に大強度が支配する）。
    """
    fixed = [j for j in range(len(row)) if j != idx and row[j] is not None]
    count = 0
    for strength in strengths:
        if len(fixed) < strength - 1:
            continue
        for combo in combinations(fixed, strength - 1):
            key = tuple(sorted([(j, row[j]) for j in combo] + [(idx, value)]))
            if key in uncovered:
                count += 1
    return count
