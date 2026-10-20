"""Native Accessibility Checker の契約（結果の状態・ルール仕様・検出結果）。

この層は他の a11y モジュール（rules_*/runner/reporter）が共有する唯一の契約である。
未実装・判定不能（NOT_EVALUATED）を PASS に変換する経路を作らないことが最重要の不変条件。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

ENGINE_NAME = "webspec2doc-native-a11y"
CATALOG_VERSION = "1.0.0"


class Status(str, Enum):
    """結果の状態。内部は 5 値、UI では 3 区分（ui_group）に束ねる。"""

    VIOLATION = "violation"
    PASS = "pass"
    INAPPLICABLE = "inapplicable"
    CANT_TELL = "cant_tell"
    NOT_IMPLEMENTED = "not_implemented"
    # 未評価（未実装・判定不能・実行失敗）の別名。NOT_IMPLEMENTED と同一メンバー。
    NOT_EVALUATED = "not_implemented"


class Implementation(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


class Level(str, Enum):
    A = "A"
    AA = "AA"
    BEST_PRACTICE = "best_practice"


IMPACTS: tuple[str, ...] = ("critical", "serious", "moderate", "minor")

# ルール既定の影響度が critical/serious の A/AA を「重大な A/AA」とする（Recall=1.00 の対象）。
_CRITICAL_IMPACTS = frozenset({"critical", "serious"})

_UI_GROUPS = {
    Status.VIOLATION: "violation",
    Status.PASS: "pass",
    Status.INAPPLICABLE: "pass",
    Status.CANT_TELL: "unevaluated",
    Status.NOT_IMPLEMENTED: "unevaluated",
}


def ui_group(status: Status) -> str:
    """UI 用の 3 区分: violation / pass / unevaluated（未実装・判定不能）。"""
    return _UI_GROUPS[status]


@dataclass(frozen=True)
class RuleSpec:
    """宣言ルール 1 件の仕様。カタログ（catalog.py）の要素。"""

    rule_id: str
    legacy_axe_ids: tuple[str, ...]
    act_ids: tuple[str, ...]
    wcag_sc: tuple[str, ...]
    wcag_level: Level
    implementation: Implementation
    category: str
    description_ja: str
    severity: str = "moderate"
    reason_if_unimplemented: str = ""

    def __post_init__(self) -> None:
        if self.severity not in IMPACTS:
            raise ValueError(f"{self.rule_id}: 不正な severity {self.severity!r}")
        if self.implementation is Implementation.NONE and not self.reason_if_unimplemented:
            raise ValueError(f"{self.rule_id}: 未実装ルールには reason_if_unimplemented が必要")

    @property
    def declared(self) -> bool:
        """WebSpec2Doc が対応を宣言するルール（品質ゲートの母集団）。"""
        return self.implementation is not Implementation.NONE

    @property
    def critical_aa(self) -> bool:
        """重大な WCAG A/AA ルールか（宣言ルールでは Recall=1.00 が合格線）。"""
        return self.wcag_level in (Level.A, Level.AA) and self.severity in _CRITICAL_IMPACTS

    @property
    def wcag_tags(self) -> tuple[str, ...]:
        """旧 axe 形式のタグ（例: wcag2a, wcag111）。best_practice は best-practice のみ。"""
        if self.wcag_level is Level.BEST_PRACTICE:
            return ("best-practice",)
        base = "wcag2a" if self.wcag_level is Level.A else "wcag2aa"
        return (base, *("wcag" + sc.replace(".", "") for sc in self.wcag_sc))


@dataclass(frozen=True)
class Finding:
    """ルールが要素 1 件について出した判定（NodeResult の実体）。"""

    rule_id: str
    status: Status
    selector: str = ""
    bbox: tuple[int, int, int, int] | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)
    impact: str = ""
    message: str = ""


NodeResult = Finding


@dataclass(frozen=True)
class RuleResult:
    """ルール単位の集約結果。"""

    rule_id: str
    status: Status
    nodes: tuple[Finding, ...] = ()
    counts: Mapping[str, int] = field(default_factory=dict)
    message: str = ""


@dataclass(frozen=True)
class PageA11yResult:
    """1 ページの結果。全カタログのルールを必ず 1 行ずつ持つ。"""

    url: str
    rules: tuple[RuleResult, ...]
    engine: str = ENGINE_NAME
    catalog_version: str = CATALOG_VERSION
    error: str | None = None

    def violations(self) -> tuple[Finding, ...]:
        return tuple(n for r in self.rules for n in r.nodes if n.status is Status.VIOLATION)

    def status_counts(self) -> dict[str, int]:
        counts = {s.value: 0 for s in Status if s.name != "NOT_EVALUATED"}
        for rule in self.rules:
            counts[rule.status.value] += 1
        return counts


def aggregate_status(
    spec: RuleSpec, findings: Iterable[Finding], *, executed: bool = True
) -> Status:
    """ルール単位に集約する。未実装・未実行は決して PASS にならない。

    優先順位: 未実装/未実行 > violation > cant_tell > pass > inapplicable。
    ただし未実装ルールでも violation を持つ入力は受け付けない（常に NOT_IMPLEMENTED）。
    """
    if spec.implementation is Implementation.NONE or not executed:
        return Status.NOT_IMPLEMENTED
    statuses = [f.status for f in findings]
    if Status.VIOLATION in statuses:
        return Status.VIOLATION
    if Status.CANT_TELL in statuses or Status.NOT_IMPLEMENTED in statuses:
        return Status.CANT_TELL
    if Status.PASS in statuses:
        return Status.PASS
    return Status.INAPPLICABLE


def aggregate_rule(
    spec: RuleSpec, findings: Sequence[Finding], *, executed: bool = True, message: str = ""
) -> RuleResult:
    status = aggregate_status(spec, findings, executed=executed)
    if status is Status.NOT_IMPLEMENTED:
        findings = ()
        message = message or spec.reason_if_unimplemented or "ルールが実行されなかった"
    counts = {
        "violation": sum(1 for f in findings if f.status is Status.VIOLATION),
        "pass": sum(1 for f in findings if f.status is Status.PASS),
        "cant_tell": sum(1 for f in findings if f.status is Status.CANT_TELL),
    }
    return RuleResult(spec.rule_id, status, tuple(findings), counts, message)


def build_page_result(
    url: str,
    catalog: Iterable[RuleSpec],
    findings: Iterable[Finding],
    *,
    ran_rules: Iterable[str] | None = None,
    error: str | None = None,
) -> PageA11yResult:
    """カタログ全件を 1 行ずつ出す。error があれば全ルールを未評価にする（違反なし扱いにしない）。

    ran_rules: 実際に実行したルール id。None なら宣言ルール全件を実行済みとみなす。
    """
    by_rule: dict[str, list[Finding]] = {}
    for f in findings:
        by_rule.setdefault(f.rule_id, []).append(f)
    ran = None if ran_rules is None else set(ran_rules)
    rows = []
    for spec in catalog:
        executed = error is None and (ran is None or spec.rule_id in ran)
        msg = f"実行失敗: {error}" if error else ""
        rows.append(aggregate_rule(spec, by_rule.get(spec.rule_id, ()), executed=executed, message=msg))
    return PageA11yResult(url=url, rules=tuple(rows), error=error)


@dataclass(frozen=True)
class A11yViolation:
    """従来の AxeViolation と同形の互換レコード（evidence は SourceEvidence）。"""

    rule_id: str
    impact: str
    description: str
    wcag_tags: tuple[str, ...]
    evidence: Any
    help_url: str = ""
    confidence: float = 1.0


# 1 リリース残す互換エイリアス
AxeViolation = A11yViolation


def to_legacy_violations(
    result: PageA11yResult,
    catalog: Mapping[str, RuleSpec],
    screenshot_path: str | None = None,
) -> tuple[A11yViolation, ...]:
    """violation ノードを従来形へ。rule_id は旧 axe id の先頭（無ければ native id）。"""
    from crawler.page_crawler import SourceEvidence

    out = []
    for node in result.violations():
        spec = catalog.get(node.rule_id)
        legacy = spec.legacy_axe_ids[0] if spec and spec.legacy_axe_ids else node.rule_id
        out.append(
            A11yViolation(
                rule_id=legacy,
                impact=node.impact or (spec.severity if spec else "moderate"),
                description=node.message or (spec.description_ja if spec else ""),
                wcag_tags=spec.wcag_tags if spec else (),
                evidence=SourceEvidence(
                    selector=node.selector, screenshot_path=screenshot_path, bbox=node.bbox
                ),
            )
        )
    return tuple(out)
