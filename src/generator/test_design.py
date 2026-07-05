"""モデルベースドテスト（MBT）設計エンジン（純関数・evidence-only）。

`report.json`（`build_report` の出力 dict）を入力に、画面ごとのテスト設計を
決定的に生成する。UI やファイル I/O は持たない純粋なデータ変換であり、
出力はすべて frozen dataclass（不変）。

対応技法:
- bva  境界値分析      : maxlength/minlength/min_value/max_value の実測制約から境界ケース
- dt   デシジョンテーブル: 必須フィールドの入力有無の全組み合わせ（2^k 真理値表）
- pw   ペアワイズ       : 自前の貪欲 AETG 系アルゴリズム（決定的・乱数不使用）で t-way 被覆
- st   状態遷移テスト   : 遷移グラフから N スイッチ経路を列挙

evidence-only 原則:
- 実測（report の制約・遷移グラフ）由来のケースは confidence=1.0（`EVIDENCE_MEASURED`）
- テスト値カタログ（既知境界値の一般知識）由来は confidence=0.9（`EVIDENCE_CATALOG`）
- 解析対象サイト固有のデータを捏造しない。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from itertools import combinations, product
from typing import Any

# ---- 確信度バッジ ----
EVIDENCE_MEASURED = 1.0  # 実測データ由来（report の制約・遷移）
EVIDENCE_CATALOG = 0.9  # テスト値カタログ（既知境界値の一般知識）由来

SUPPORTED_TECHNIQUES: tuple[str, ...] = ("bva", "dt", "pw", "st")

# 入力値として扱わないフィールド種別（view-design.js の SKIP と一致）
_SKIP_FIELD_TYPES = frozenset({"hidden", "submit", "button", "reset", "image"})

# フィールド種別 → 値カタログのカテゴリ（同一ストア instance/test_design_settings.json）
_FIELD_TYPE_TO_CATALOG: dict[str, str] = {
    "email": "email",
    "tel": "phone_jp",
    "date": "date",
    "password": "password",
}

# カタログのラベルから期待結果を推定する決定的キーワード分類
_INVALID_KEYWORDS = (
    "+1",
    "-1",
    "超過",
    "違反",
    "不正",
    "範囲外",
    "未満",
    "混入",
    "文字種不足",
    "空白",
)
_VALID_KEYWORDS = ("上限値", "下限値", "境界")


# =========================================================================
# パラメータ
# =========================================================================
@dataclass(frozen=True)
class TestDesignParams:
    """テスト設計の技法選択とパラメータ（設定 API と共有）。"""

    enabled_techniques: tuple[str, ...] = SUPPORTED_TECHNIQUES
    bva_offset: int = 1
    pairwise_strength: int = 2  # 2（2-way）または 3（3-way）
    n_switch: int = 0  # 0（0-switch）または 1（1-switch）
    max_dt_conditions: int = 4
    value_catalog: Mapping[str, list[dict[str, str]]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # frozen のため object.__setattr__ で正規化（不正値を安全側へ丸める）
        object.__setattr__(self, "bva_offset", max(1, int(self.bva_offset)))
        object.__setattr__(self, "pairwise_strength", 3 if int(self.pairwise_strength) >= 3 else 2)
        object.__setattr__(self, "n_switch", 1 if int(self.n_switch) >= 1 else 0)
        object.__setattr__(self, "max_dt_conditions", max(1, int(self.max_dt_conditions)))
        object.__setattr__(
            self,
            "enabled_techniques",
            tuple(t for t in self.enabled_techniques if t in SUPPORTED_TECHNIQUES),
        )

    def enabled(self, technique: str) -> bool:
        return technique in self.enabled_techniques


# =========================================================================
# 結果モデル（すべて frozen）
# =========================================================================
@dataclass(frozen=True)
class BvaCase:
    field_name: str
    label: str
    value: str
    expected: str  # "有効" / "無効" / "要確認"
    confidence: float
    evidence: str


@dataclass(frozen=True)
class BvaTable:
    field_name: str
    field_type: str
    cases: tuple[BvaCase, ...]


@dataclass(frozen=True)
class DecisionRule:
    conditions: tuple[bool, ...]  # 各条件（必須フィールド）の入力有無
    action: str


@dataclass(frozen=True)
class DecisionTable:
    conditions: tuple[str, ...]  # 条件ラベル（必須フィールド名）
    rules: tuple[DecisionRule, ...]
    confidence: float = EVIDENCE_MEASURED


@dataclass(frozen=True)
class PairwiseParam:
    name: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class PairwiseTable:
    params: tuple[PairwiseParam, ...]
    rows: tuple[tuple[str, ...], ...]  # 各行はパラメータごとの値
    strength: int
    confidence: float = EVIDENCE_MEASURED


@dataclass(frozen=True)
class TransitionSequence:
    steps: tuple[str, ...]  # 画面 ID の並び


@dataclass(frozen=True)
class StateTransitionSet:
    n_switch: int
    sequences: tuple[TransitionSequence, ...]
    confidence: float = EVIDENCE_MEASURED


@dataclass(frozen=True)
class ScreenTestDesign:
    page_id: str
    title: str
    bva: tuple[BvaTable, ...]
    decision_table: DecisionTable | None
    pairwise: PairwiseTable | None
    state_transitions: StateTransitionSet | None

    def is_empty(self) -> bool:
        return not (self.bva or self.decision_table or self.pairwise or self.state_transitions)


@dataclass(frozen=True)
class TestDesign:
    screens: tuple[ScreenTestDesign, ...]
    params: TestDesignParams


# =========================================================================
# エントリポイント
# =========================================================================
def build_test_design(report: Mapping[str, Any], params: TestDesignParams) -> TestDesign:
    """report(dict) から画面別のテスト設計を決定的に生成する純関数。"""
    screens = report.get("screens") or []
    succ = _successor_map(screens)
    designs: list[ScreenTestDesign] = []
    for screen in screens:
        design = _design_for_screen(screen, params, succ)
        if not design.is_empty():
            designs.append(design)
    return TestDesign(screens=tuple(designs), params=params)


def _design_for_screen(
    screen: Mapping[str, Any],
    params: TestDesignParams,
    succ: Mapping[str, tuple[str, ...]],
) -> ScreenTestDesign:
    fields = _input_fields(screen)
    bva = _build_bva(fields, params) if params.enabled("bva") else ()
    dt = _build_decision_table(fields, params) if params.enabled("dt") else None
    pw = _build_pairwise(fields, params) if params.enabled("pw") else None
    st = _build_state_transitions(screen, succ, params) if params.enabled("st") else None
    return ScreenTestDesign(
        page_id=str(screen.get("page_id", "")),
        title=str(screen.get("title", "")),
        bva=bva,
        decision_table=dt,
        pairwise=pw,
        state_transitions=st,
    )


# =========================================================================
# フィールド抽出ユーティリティ
# =========================================================================
def _input_fields(screen: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    out: list[dict[str, Any]] = []
    for form in screen.get("forms") or []:
        for fld in form.get("fields") or []:
            if str(fld.get("field_type", "")) not in _SKIP_FIELD_TYPES:
                out.append(fld)
    return tuple(out)


def _field_label(fld: Mapping[str, Any]) -> str:
    return str(fld.get("name") or fld.get("field_type") or "field")


def _option_values(fld: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for opt in fld.get("options") or []:
        if isinstance(opt, Mapping):
            values.append(str(opt.get("value") or opt.get("label") or ""))
        else:
            values.append(str(opt))
    return tuple(v for v in values if v != "")


# =========================================================================
# 境界値分析（BVA）
# =========================================================================
def _build_bva(
    fields: tuple[dict[str, Any], ...], params: TestDesignParams
) -> tuple[BvaTable, ...]:
    tables: list[BvaTable] = []
    for fld in fields:
        cases = _bva_cases(fld, params)
        if cases:
            tables.append(
                BvaTable(
                    field_name=_field_label(fld),
                    field_type=str(fld.get("field_type", "")),
                    cases=cases,
                )
            )
    return tuple(tables)


def _bva_cases(fld: Mapping[str, Any], params: TestDesignParams) -> tuple[BvaCase, ...]:
    name = _field_label(fld)
    off = params.bva_offset
    cases: list[BvaCase] = []

    def measured(label: str, value: str, expected: str, evidence: str) -> BvaCase:
        return BvaCase(name, label, value, expected, EVIDENCE_MEASURED, evidence)

    maxlength = _to_int(fld.get("maxlength"))
    if maxlength is not None:
        cases.append(measured("上限ちょうど", f"{maxlength}文字", "有効", f"maxlength={maxlength}"))
        cases.append(
            measured("上限超過", f"{maxlength + off}文字", "無効", f"maxlength={maxlength}")
        )
    minlength = _to_int(fld.get("minlength"))
    if minlength is not None:
        cases.append(measured("下限ちょうど", f"{minlength}文字", "有効", f"minlength={minlength}"))
        if minlength - off >= 0:
            cases.append(
                measured("下限未満", f"{minlength - off}文字", "無効", f"minlength={minlength}")
            )
    min_value = _to_number(fld.get("min_value"))
    if min_value is not None:
        cases.append(measured("最小ちょうど", _num_str(min_value), "有効", f"min={min_value}"))
        cases.append(measured("最小未満", _num_str(min_value - off), "無効", f"min={min_value}"))
    max_value = _to_number(fld.get("max_value"))
    if max_value is not None:
        cases.append(measured("最大ちょうど", _num_str(max_value), "有効", f"max={max_value}"))
        cases.append(measured("最大超過", _num_str(max_value + off), "無効", f"max={max_value}"))

    cases.extend(_catalog_cases(fld, params))
    return tuple(cases)


def _catalog_cases(fld: Mapping[str, Any], params: TestDesignParams) -> tuple[BvaCase, ...]:
    category = _FIELD_TYPE_TO_CATALOG.get(str(fld.get("field_type", "")))
    if category is None:
        return ()
    entries = params.value_catalog.get(category) or []
    name = _field_label(fld)
    out: list[BvaCase] = []
    for entry in entries:
        label = str(entry.get("label", ""))
        out.append(
            BvaCase(
                field_name=name,
                label=label,
                value=str(entry.get("value", "")),
                expected=_classify_catalog(label),
                confidence=EVIDENCE_CATALOG,
                evidence=f"値カタログ:{category}",
            )
        )
    return tuple(out)


def _classify_catalog(label: str) -> str:
    if any(k in label for k in _INVALID_KEYWORDS):
        return "無効"
    if any(k in label for k in _VALID_KEYWORDS):
        return "有効"
    return "要確認"


# =========================================================================
# デシジョンテーブル（必須フィールドの入力有無 2^k）
# =========================================================================
def _build_decision_table(
    fields: tuple[dict[str, Any], ...], params: TestDesignParams
) -> DecisionTable | None:
    required = [f for f in fields if f.get("required")]
    if len(required) < 2:
        return None
    chosen = required[: params.max_dt_conditions]
    names = tuple(_field_label(f) for f in chosen)
    rules: list[DecisionRule] = []
    for combo in product((True, False), repeat=len(names)):
        rules.append(DecisionRule(conditions=combo, action=_dt_action(names, combo)))
    return DecisionTable(conditions=names, rules=tuple(rules))


def _dt_action(names: tuple[str, ...], combo: tuple[bool, ...]) -> str:
    missing = [n for n, present in zip(names, combo, strict=False) if not present]
    if not missing:
        return "送信成功"
    return "エラー: " + "、".join(f"{n}未入力" for n in missing)


# =========================================================================
# ペアワイズ（自前・決定的な貪欲 t-way 被覆）
# =========================================================================
def _build_pairwise(
    fields: tuple[dict[str, Any], ...], params: TestDesignParams
) -> PairwiseTable | None:
    par = _pairwise_params(fields)
    strength = params.pairwise_strength
    if len(par) <= strength:
        # パラメータが強度以下なら全数（デカルト積）で足りるため、ペアワイズ不要
        return None
    rows = _greedy_cover([p.values for p in par], strength)
    return PairwiseTable(params=tuple(par), rows=tuple(rows), strength=strength)


def _pairwise_params(fields: tuple[dict[str, Any], ...]) -> list[PairwiseParam]:
    par: list[PairwiseParam] = []
    for fld in fields:
        opts = _option_values(fld)
        if len(opts) >= 2:
            values = opts
        else:
            values = ("有効値", "無効値")  # 同値クラス（有効/無効の2値）
        par.append(PairwiseParam(name=_field_label(fld), values=values))
    return par


def _greedy_cover(domains: list[tuple[str, ...]], strength: int) -> list[tuple[str, ...]]:
    """全 t-way 組み合わせを被覆する行集合を決定的に生成する（AETG 系の貪欲法）。

    各行は未被覆の t-tuple を1つ「種」として固定し、残りの列を貪欲に埋める。
    種は必ず新規被覆になるため未被覆集合は毎回真に減少し、有限回で全被覆に至る。
    種の選択（`min`）と値の先頭優先タイブレークにより、同一入力→同一出力（決定的）。
    """
    uncovered = _all_t_tuples(domains, strength)
    rows: list[tuple[str, ...]] = []
    while uncovered:
        seed = min(uncovered)  # 決定的な種の選択
        row = _build_row(domains, strength, uncovered, seed)
        uncovered -= _tuples_in_row(row, strength)
        rows.append(row)
    return rows


def _all_t_tuples(
    domains: list[tuple[str, ...]], strength: int
) -> set[tuple[tuple[int, str], ...]]:
    tuples: set[tuple[tuple[int, str], ...]] = set()
    for idxs in combinations(range(len(domains)), strength):
        for values in product(*(domains[i] for i in idxs)):
            tuples.add(tuple(zip(idxs, values, strict=False)))
    return tuples


def _build_row(
    domains: list[tuple[str, ...]],
    strength: int,
    uncovered: set[tuple[tuple[int, str], ...]],
    seed: tuple[tuple[int, str], ...],
) -> tuple[str, ...]:
    row: list[str | None] = [None] * len(domains)
    for idx, value in seed:  # 種のタプルを固定（この行は必ずこれを被覆する）
        row[idx] = value
    for i in range(len(domains)):
        if row[i] is not None:
            continue
        best_value = domains[i][0]
        best_gain = -1
        for value in domains[i]:
            gain = _gain(row, i, value, strength, uncovered)
            if gain > best_gain:  # 先頭優先の決定的タイブレーク
                best_gain = gain
                best_value = value
        row[i] = best_value
    return tuple(v for v in row if v is not None)


def _gain(
    row: list[str | None],
    idx: int,
    value: str,
    strength: int,
    uncovered: set[tuple[tuple[int, str], ...]],
) -> int:
    """value を idx に置いたとき、既に確定済みの列との組で新たに覆う t-tuple 数。"""
    fixed = [j for j in range(len(row)) if j != idx and row[j] is not None]
    if len(fixed) < strength - 1:
        return 0
    count = 0
    for combo in combinations(fixed, strength - 1):
        key = tuple(sorted([(j, row[j]) for j in combo] + [(idx, value)]))
        if key in uncovered:
            count += 1
    return count


def _tuples_in_row(row: tuple[str, ...], strength: int) -> set[tuple[tuple[int, str], ...]]:
    covered: set[tuple[tuple[int, str], ...]] = set()
    for idxs in combinations(range(len(row)), strength):
        covered.add(tuple((i, row[i]) for i in idxs))
    return covered


# =========================================================================
# 状態遷移テスト（N スイッチ経路列挙）
# =========================================================================
def _successor_map(screens: list[Mapping[str, Any]]) -> dict[str, tuple[str, ...]]:
    succ: dict[str, tuple[str, ...]] = {}
    for screen in screens:
        pid = str(screen.get("page_id", ""))
        to = screen.get("transitions", {}).get("to") or []
        succ[pid] = tuple(str(t) for t in to if str(t) != pid)
    return succ


def _build_state_transitions(
    screen: Mapping[str, Any],
    succ: Mapping[str, tuple[str, ...]],
    params: TestDesignParams,
) -> StateTransitionSet | None:
    pid = str(screen.get("page_id", ""))
    if not succ.get(pid):
        return None
    depth = params.n_switch + 1  # スイッチ数 + 1 本の遷移（辺）を辿る
    sequences = tuple(TransitionSequence(steps=path) for path in _enumerate_paths(pid, succ, depth))
    if not sequences:
        return None
    return StateTransitionSet(n_switch=params.n_switch, sequences=sequences)


def _enumerate_paths(
    start: str, succ: Mapping[str, tuple[str, ...]], edges: int
) -> list[tuple[str, ...]]:
    """start から edges 本の遷移を辿る経路を決定的に列挙する（自己ループは除外）。"""
    paths: list[tuple[str, ...]] = [(start,)]
    for _ in range(edges):
        extended: list[tuple[str, ...]] = []
        for path in paths:
            for nxt in succ.get(path[-1], ()):  # succ は挿入順を保持（決定的）
                if nxt not in path:  # サイクルを避けて有限化
                    extended.append(path + (nxt,))
        paths = extended
    return paths


# =========================================================================
# 数値パース補助
# =========================================================================
def _to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _num_str(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return str(value)
