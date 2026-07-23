"""L0 観測の完全性 — 「我々は全体を見たか？」

設計計画 rev.3 の Phase 1。

なぜ最初に問うか:
  見落とした画面があれば、下流の検証はすべて静かに狭くなる。
  これを問わない限り、他のどんな検証も「どの範囲についての結論か」が言えない。
  監査で「深さ2・最大8画面に勝手に絞った」検証を「通し実行」と報告した失敗も、
  この層が無かったことに起因する。

本モジュールは**既存の成果物のみを読む**。対象サイトへの追加アクセスは発生しない。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CoverageGap:
    """観測できなかった領域と、その理由。"""

    kind: str
    count: int
    reason: str
    samples: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "count": self.count,
            "reason": self.reason,
            "samples": list(self.samples),
        }


@dataclass
class ObservationCoverage:
    observed_pages: int = 0
    canonical_screens: int = 0
    gaps: list[CoverageGap] = field(default_factory=list)
    crawl_depth: int | None = None
    max_pages: int | None = None

    @property
    def is_complete(self) -> bool:
        return not self.gaps

    def to_dict(self) -> dict[str, Any]:
        return {
            "observed_pages": self.observed_pages,
            "canonical_screens": self.canonical_screens,
            "crawl_depth": self.crawl_depth,
            "max_pages": self.max_pages,
            "is_complete": self.is_complete,
            "gaps": [g.to_dict() for g in self.gaps],
            "scope_statement": self.scope_statement(),
        }

    def scope_statement(self) -> str:
        """以降のすべての報告へ継承させる範囲注記。

        条件2（未検証を問題なしと言わない）の起点。
        """
        base = f"本実行が観測できたのは {self.observed_pages} ページ（正規化後 {self.canonical_screens} 画面）です。"
        if not self.gaps:
            return (
                base
                + "観測範囲外として検出された領域はありません（ただし観測手段の限界は残ります）。"
            )
        listed = "、".join(f"{g.kind}（{g.count}）" for g in self.gaps)
        return (
            base
            + f"次の領域は観測できていません: {listed}。"
            + "これらについては何も検証しておらず、「問題なし」を意味しません。"
        )


def analyze(
    report: dict[str, Any] | None,
    job_log: list[str] | None = None,
    requested_depth: int | None = None,
    requested_max_pages: int | None = None,
) -> ObservationCoverage:
    """既存の成果物から観測の完全性を評価する（追加アクセスなし）。"""
    report = report or {}
    meta = report.get("meta") or {}
    screens = [s for s in (report.get("screens") or []) if isinstance(s, dict)]

    coverage = ObservationCoverage(
        observed_pages=int(meta.get("page_count", len(screens)) or len(screens)),
        canonical_screens=int(meta.get("screen_count", 0) or 0),
        crawl_depth=_int_or_none(meta.get("crawl_depth", requested_depth)),
        max_pages=_int_or_none(meta.get("max_pages", requested_max_pages)),
    )

    _detect_login_walls(coverage, job_log or [])
    _detect_limit_truncation(coverage, job_log or [])
    _detect_unreadable_frames(coverage, screens)
    _detect_unreached_transitions(coverage, screens)
    return coverage


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None


def _detect_login_walls(coverage: ObservationCoverage, log: list[str]) -> None:
    """ログイン必須で未観測の画面。スキップした場合は認証後が丸ごと未検証。"""
    for line in log:
        if "要ログイン" not in line:
            continue
        count = _extract_count(line, "要ログイン")
        if count:
            coverage.gaps.append(
                CoverageGap(
                    kind="認証が必要で未観測",
                    count=count,
                    reason=(
                        "ログイン壁を検出しましたが認証情報が与えられず、"
                        "認証後の画面は一切観測していません。"
                    ),
                )
            )
            return


def _detect_limit_truncation(coverage: ObservationCoverage, log: list[str]) -> None:
    """深さ・件数の上限で打ち切った場合、その先は未観測。"""
    if coverage.max_pages and coverage.observed_pages >= coverage.max_pages:
        coverage.gaps.append(
            CoverageGap(
                kind="件数上限で打ち切り",
                count=coverage.observed_pages,
                reason=(
                    f"最大ページ数 {coverage.max_pages} に到達したため、"
                    "それ以上のクロールを打ち切りました。上限を超えた領域は未観測です。"
                ),
            )
        )


def _detect_unreadable_frames(coverage: ObservationCoverage, screens: list[dict]) -> None:
    """読めなかった iframe の中身は未観測。"""
    unreadable = [
        str(frame.get("src", ""))
        for screen in screens
        for frame in (screen.get("embedded_frames") or [])
        if isinstance(frame, dict) and not frame.get("readable", True)
    ]
    if unreadable:
        coverage.gaps.append(
            CoverageGap(
                kind="読めなかった埋め込みフレーム",
                count=len(unreadable),
                reason="クロスオリジン等で内容を読み取れず、内部は未観測です。",
                samples=tuple(unreadable[:5]),
            )
        )


def _detect_unreached_transitions(coverage: ObservationCoverage, screens: list[dict]) -> None:
    """遷移先として参照されているが、実体を観測できていない画面。"""
    observed = {str(s.get("page_id", "")) for s in screens if s.get("page_id")}
    referenced: set[str] = set()
    for screen in screens:
        transitions = screen.get("transitions")
        if isinstance(transitions, dict):
            referenced.update(str(t) for t in (transitions.get("to") or []))
    missing = sorted(referenced - observed)
    if missing:
        coverage.gaps.append(
            CoverageGap(
                kind="遷移先が未観測",
                count=len(missing),
                reason="遷移先として参照されていますが、その画面自体は観測できていません。",
                samples=tuple(missing[:5]),
            )
        )


def _extract_count(line: str, marker: str) -> int:
    """'画面分析完了: 28件 (要ログイン: 4件)' のような行から件数を取る。"""
    index = line.find(marker)
    if index < 0:
        return 0
    digits = ""
    for char in line[index + len(marker) :]:
        if char.isdigit():
            digits += char
        elif digits:
            break
    return int(digits) if digits else 0
