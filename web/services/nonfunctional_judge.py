"""L4 非機能の合否判定 — 既存の観測データを判定へ接続する。

設計計画 rev.3 の Phase 1。**新規開発ではなく接続作業**である。

背景（監査で判明）:
  アクセシビリティ違反は既に 635 件（serious 253 / moderate 382）観測されていたが、
  実行結果には「アクセシビリティ自動確認 1件 skipped」としか出ていなかった。
  性能も lcp_ms / cls / ttfb_ms 等を実測済み。**判定していないだけ**だった。

基準線方式（オオカミ少年の回避):
  635 件を即座に「不合格」にすると、ほぼ全ての実サイトが常時不合格となり
  信号が意味を失う。初回は基準線を確立するのみとし、2回目以降は
  **新規に増えた違反**を不合格条件とする（回帰防止）。
  ただし critical は初回から不合格とする（重大な障壁は待たない）。

claim_scope の厳守:
  性能は `lab_single_run_this_environment` と記録されている。これは
  **実利用環境の性能ではない**。判定結果に必ずこの限界を併記する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ─────────────────── 閾値（公開基準を既定とする） ───────────────────

#: Core Web Vitals の「良好」しきい値（https://web.dev/vitals/）
CWV_LCP_MS = 2500.0
CWV_CLS = 0.1
#: TTFB は補助指標（Google の推奨は 800ms 以下）
TTFB_MS = 800.0

#: WCAG 2.2 AA として不合格にする impact
BLOCKING_IMPACTS = frozenset({"critical"})
#: 要確認（不合格にはしないが必ず提示する）
REVIEW_IMPACTS = frozenset({"serious", "moderate"})

VERDICT_PASS = "pass"
VERDICT_FAIL = "fail"
VERDICT_BASELINE = "baseline_established"
VERDICT_UNKNOWN = "unknown"


@dataclass(frozen=True)
class Judgement:
    """1 領域の判定結果。"""

    area: str
    verdict: str
    summary: str
    #: 「この判定が何について言えるか」。未検証を問題なしと読ませないための注記。
    claim_scope: str
    details: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "area": self.area,
            "verdict": self.verdict,
            "summary": self.summary,
            "claim_scope": self.claim_scope,
            "details": list(self.details),
        }


def judge_all(
    report: dict[str, Any] | None,
    accessibility: dict[str, Any] | None,
    technical_health: dict[str, Any] | None,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """非機能3領域を判定する。

    baseline は前回実行の本関数の出力（`to_dict()` 済み）。
    None の場合は初回とみなし、a11y は基準線確立のみとする。
    """
    judgements = [
        judge_performance(report),
        judge_accessibility(accessibility, baseline),
        judge_technical_health(technical_health),
    ]
    verdicts = [j.verdict for j in judgements]
    if VERDICT_FAIL in verdicts:
        overall = VERDICT_FAIL
    elif all(v == VERDICT_UNKNOWN for v in verdicts):
        overall = VERDICT_UNKNOWN
    elif VERDICT_BASELINE in verdicts:
        overall = VERDICT_BASELINE
    else:
        overall = VERDICT_PASS
    return {
        "overall": overall,
        "judgements": [j.to_dict() for j in judgements],
        # 条件2: 「問題なし」とは書かない
        "notice": (
            "本判定は観測できた範囲についてのものです。"
            "基準を満たすことは、欠陥が無いことの証明ではありません。"
        ),
    }


# ─────────────────── 性能 ───────────────────


def judge_performance(report: dict[str, Any] | None) -> Judgement:
    screens = (report or {}).get("screens") or []
    measured = [s for s in screens if isinstance(s, dict) and s.get("performance")]
    if not measured:
        return Judgement(
            area="performance",
            verdict=VERDICT_UNKNOWN,
            summary="性能の実測データがありません（未検証）。",
            claim_scope="未検証",
        )

    failures: list[dict[str, Any]] = []
    for screen in measured:
        perf = screen["performance"]
        exceeded = []
        if _num(perf.get("lcp_ms")) > CWV_LCP_MS:
            exceeded.append(f"LCP {perf['lcp_ms']}ms > {CWV_LCP_MS}ms")
        if _num(perf.get("cls")) > CWV_CLS:
            exceeded.append(f"CLS {perf['cls']} > {CWV_CLS}")
        if _num(perf.get("ttfb_ms")) > TTFB_MS:
            exceeded.append(f"TTFB {perf['ttfb_ms']}ms > {TTFB_MS}ms")
        if exceeded:
            failures.append(
                {
                    "page_id": screen.get("page_id", ""),
                    "url": screen.get("url", ""),
                    "exceeded": exceeded,
                }
            )

    # 観測データ自身が申告している主張範囲を引き継ぐ（ラボ単回計測）
    scope = str(measured[0]["performance"].get("claim_scope") or "")
    claim = (
        "この環境での単回計測（ラボ計測）。実利用環境・実ユーザーの体感性能ではありません。"
        if scope == "lab_single_run_this_environment"
        else f"計測条件: {scope or '不明'}"
    )
    if failures:
        return Judgement(
            area="performance",
            verdict=VERDICT_FAIL,
            summary=f"{len(failures)}/{len(measured)} 画面が Core Web Vitals の基準を超えました。",
            claim_scope=claim,
            details=tuple(failures),
        )
    return Judgement(
        area="performance",
        verdict=VERDICT_PASS,
        summary=f"{len(measured)} 画面すべてが Core Web Vitals の基準内でした。",
        claim_scope=claim,
    )


def _num(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


# ─────────────────── アクセシビリティ（基準線方式） ───────────────────


def judge_accessibility(
    accessibility: dict[str, Any] | None, baseline: dict[str, Any] | None
) -> Judgement:
    summary = (accessibility or {}).get("summary")
    if not isinstance(summary, dict):
        return Judgement(
            area="accessibility",
            verdict=VERDICT_UNKNOWN,
            summary="アクセシビリティ監査の結果がありません（未検証）。",
            claim_scope="未検証",
        )

    critical = int(summary.get("critical", 0) or 0)
    serious = int(summary.get("serious", 0) or 0)
    moderate = int(summary.get("moderate", 0) or 0)
    total = int(summary.get("violations", 0) or 0)
    claim = (
        "自動検査（axe-core相当）で検出できた範囲。"
        "自動検査はWCAG適合の一部しか判定できず、適合の証明にはなりません。"
    )

    # critical は初回から不合格（重大な障壁は基準線を待たない）
    if critical:
        return Judgement(
            area="accessibility",
            verdict=VERDICT_FAIL,
            summary=f"critical な違反が {critical} 件あります（合計 {total} 件）。",
            claim_scope=claim,
            details=({"critical": critical, "serious": serious, "moderate": moderate},),
        )

    previous = _previous_a11y(baseline)
    if previous is None:
        return Judgement(
            area="accessibility",
            verdict=VERDICT_BASELINE,
            summary=(
                f"基準線を確立しました（合計 {total} 件: serious {serious} / moderate {moderate}）。"
                "初回のため合否判定は行いません。次回以降、新規に増えた違反を不合格とします。"
            ),
            claim_scope=claim,
            details=({"critical": critical, "serious": serious, "moderate": moderate},),
        )

    increased = total - previous
    if increased > 0:
        return Judgement(
            area="accessibility",
            verdict=VERDICT_FAIL,
            summary=f"違反が基準線より {increased} 件増えました（{previous} → {total}）。",
            claim_scope=claim,
            details=({"baseline": previous, "current": total, "increased": increased},),
        )
    return Judgement(
        area="accessibility",
        verdict=VERDICT_PASS,
        summary=f"基準線比で悪化はありません（{previous} → {total}）。",
        claim_scope=claim,
        details=({"baseline": previous, "current": total},),
    )


def _previous_a11y(baseline: dict[str, Any] | None) -> int | None:
    """前回判定から a11y の違反総数を取り出す。無ければ None（初回）。"""
    for item in (baseline or {}).get("judgements", []):
        if not isinstance(item, dict) or item.get("area") != "accessibility":
            continue
        for detail in item.get("details") or []:
            if isinstance(detail, dict) and "current" in detail:
                return int(detail["current"])
            if isinstance(detail, dict) and "critical" in detail:
                return (
                    int(detail.get("critical", 0))
                    + int(detail.get("serious", 0))
                    + int(detail.get("moderate", 0))
                )
    return None


# ─────────────────── 技術的健全性 ───────────────────


def judge_technical_health(technical_health: dict[str, Any] | None) -> Judgement:
    summary = (technical_health or {}).get("summary")
    if not isinstance(summary, dict):
        return Judgement(
            area="technical_health",
            verdict=VERDICT_UNKNOWN,
            summary="技術的健全性のデータがありません（未検証）。",
            claim_scope="未検証",
        )

    checks = {
        "page_http_errors": "HTTPエラー",
        "broken_links": "リンク切れ",
        "console_errors": "コンソールエラー",
        "mixed_content": "混在コンテンツ",
    }
    problems = [
        {"kind": label, "count": int(summary.get(key, 0) or 0)}
        for key, label in checks.items()
        if int(summary.get(key, 0) or 0) > 0
    ]
    claim = str((technical_health or {}).get("claim_boundary") or "観測できた範囲のみ")

    if problems:
        listed = " / ".join(f"{p['kind']} {p['count']}件" for p in problems)
        return Judgement(
            area="technical_health",
            verdict=VERDICT_FAIL,
            summary=f"技術的な問題を検出しました: {listed}",
            claim_scope=claim,
            details=tuple(problems),
        )
    return Judgement(
        area="technical_health",
        verdict=VERDICT_PASS,
        summary="HTTPエラー・リンク切れ・コンソールエラー・混在コンテンツは検出されませんでした。",
        claim_scope=claim,
    )
