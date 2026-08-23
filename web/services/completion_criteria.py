"""テスト終了基準（完了判定）の評価。

他のストア（テストケース表・不具合ストア）が集めた数値を受け取り、
終了基準を満たしているかを判定して返すだけの純粋関数群。**保存は一切しない。**

判定の既定値:

    消化率      テストケースの実行済み割合が 100% 以上
    重大不具合  severity=critical かつ未クローズが 0 件
    自動化率    自動化可ケースのうち自動化済みが 80% 以上

画面側で割り算・丸め・書式づくりをさせないため、表示文字列もここで作る。
総数 0 のときは率を 0.0 とし、表示は「—」にする（ゼロ除算を起こさない）。
"""

from __future__ import annotations

from typing import Any

DEFAULT_TARGETS: dict[str, float] = {
    "coverage_percent": 100.0,
    "critical_open_max": 0.0,
    "automation_percent": 80.0,
}

_NA = "—"


def _percent(numerator: int, denominator: int) -> float:
    """割合（%・小数第1位）。分母 0 は 0.0 を返す。"""
    if denominator <= 0:
        return 0.0
    return round(numerator * 100.0 / denominator, 1)


def _ratio_text(numerator: int, denominator: int) -> str:
    """`2.0%（32/1,641）` 形式。分母 0 のときは `—`。"""
    if denominator <= 0:
        return _NA
    return f"{_percent(numerator, denominator):.1f}%（{numerator:,}/{denominator:,}）"


def _percent_text(numerator: int, denominator: int) -> str:
    """`97.8%` 形式。分母 0 のときは `—`。"""
    if denominator <= 0:
        return _NA
    return f"{_percent(numerator, denominator):.1f}%"


def _merge_targets(targets: dict[str, Any] | None) -> dict[str, float]:
    """既定の目標値に呼び出し側の指定を重ねる（既存 dict は書き換えない）。"""
    merged = dict(DEFAULT_TARGETS)
    for key, value in (targets or {}).items():
        if key not in DEFAULT_TARGETS:
            continue
        try:
            merged[key] = float(value)
        except (TypeError, ValueError):
            continue  # 不正な目標値は既定のまま使う（画面入力を信用しない）
    return merged


def _coverage_criterion(total_cases: int, executed_cases: int, target: float) -> dict[str, Any]:
    current = _percent(executed_cases, total_cases)
    return {
        "key": "coverage",
        "label": "テストケース消化率",
        "target": f"{target:.0f}%",
        "current": _ratio_text(executed_cases, total_cases),
        "met": total_cases > 0 and current >= target,
    }


def _critical_criterion(critical_open: int, target: float) -> dict[str, Any]:
    return {
        "key": "critical",
        "label": "重大不具合の未解決",
        "target": f"{int(target)} 件",
        "current": f"{critical_open:,} 件",
        "met": critical_open <= int(target),
    }


def _automation_criterion(
    automatable_cases: int, automated_cases: int, target: float
) -> dict[str, Any]:
    current = _percent(automated_cases, automatable_cases)
    return {
        "key": "automation",
        "label": "自動化可ケースの自動化率",
        "target": f"{target:.0f}%",
        "current": _percent_text(automated_cases, automatable_cases),
        # 自動化可ケースが 0 件なら判定対象がないため達成扱いにする
        "met": automatable_cases <= 0 or current >= target,
    }


def evaluate(
    *,
    total_cases: int,
    executed_cases: int,
    critical_open: int,
    automatable_cases: int,
    automated_cases: int,
    targets: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """終了基準を評価して、基準ごとの達成状況と全体判定を返す。"""
    goals = _merge_targets(targets)
    criteria: list[dict[str, Any]] = [
        _coverage_criterion(
            max(int(total_cases), 0), max(int(executed_cases), 0), goals["coverage_percent"]
        ),
        _critical_criterion(max(int(critical_open), 0), goals["critical_open_max"]),
        _automation_criterion(
            max(int(automatable_cases), 0),
            max(int(automated_cases), 0),
            goals["automation_percent"],
        ),
    ]
    unmet_keys = [c["key"] for c in criteria if not c["met"]]
    met = not unmet_keys
    return {
        "criteria": criteria,
        "overall": {"met": met, "label": "達成（完了可）" if met else "未達（完了不可）"},
        "unmet_keys": unmet_keys,
    }
