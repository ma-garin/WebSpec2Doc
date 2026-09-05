"""修正案の過適合リスク検出。
判定はしない。危険兆候を列挙するだけ。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Pattern
import re

from web.services.healing.types import FixProposal


# ─────────────────────────────────────────────────────────────────
# リスク信号の型
# ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RiskSignal:
    """修正案から検出された過適合の兆候 1 件。

    code: 識別子（tests-only / assert-removed / ... ）
    label: 画面に出す短い日本語
    detail: 根拠（該当ファイル名・行番号など）
    severity: "high" | "medium" | "low"
    """

    code: str
    label: str
    detail: str
    severity: str


# ─────────────────────────────────────────────────────────────────
# diff パース
# ─────────────────────────────────────────────────────────────────


def parse_diff_stats(diff: str) -> dict[str, dict[str, int]]:
    """統一 diff をファイル別の {"added": n, "removed": n} に分解する。

    Args:
        diff: git diff 形式の文字列

    Returns:
        {ファイルパス: {"added": 行数, "removed": 行数}}
    """
    stats: dict[str, dict[str, int]] = {}
    current_file = ""

    for line in diff.splitlines():
        # diff --git の行でファイル名を抽出
        if line.startswith("diff --git"):
            # "diff --git a/path/to/file b/path/to/file" から b/ の側を抽出
            parts = line.split(" b/", 1)
            if len(parts) == 2:
                current_file = parts[1]
                if current_file not in stats:
                    stats[current_file] = {"added": 0, "removed": 0}

        # +++ / --- で区切られた位置に統一 diff の行カウント開始
        if line.startswith("@@"):
            continue

        # 実際の追加・削除行をカウント（+/- で始まる行）
        if current_file and line.startswith("+") and not line.startswith("+++"):
            stats[current_file]["added"] += 1
        elif current_file and line.startswith("-") and not line.startswith("---"):
            stats[current_file]["removed"] += 1

    return stats


# ─────────────────────────────────────────────────────────────────
# リスク検出
# ─────────────────────────────────────────────────────────────────


def assess(proposal: FixProposal) -> tuple[RiskSignal, ...]:
    """修正案から過適合のおそれがある兆候を列挙する。重大度降順。

    Args:
        proposal: 修正案

    Returns:
        検出された RiskSignal のタプル（降順で並ぶ）
    """
    signals: list[RiskSignal] = []

    # 兆候 1: empty-diff (high)
    if not proposal.diff or not proposal.files_changed:
        signals.append(
            RiskSignal(
                code="empty-diff",
                label="変更がありません",
                detail="diff が空、または変更ファイルが 0 件",
                severity="high",
            )
        )
        # diff が空なら以降の検出は飛ばす
        if not proposal.diff:
            return tuple(_sort_by_severity(signals))

    # diff をパース
    diff_stats = parse_diff_stats(proposal.diff)

    # 兆候 2: tests-only (high)
    if proposal.files_changed and all(_is_test_file(f) for f in proposal.files_changed):
        signals.append(
            RiskSignal(
                code="tests-only",
                label="テストだけを書き換えています",
                detail=f"変更: {', '.join(proposal.files_changed)}",
                severity="high",
            )
        )

    # 兆候 3: test-modified (medium)
    has_test = any(_is_test_file(f) for f in proposal.files_changed)
    has_non_test = any(not _is_test_file(f) for f in proposal.files_changed)
    if has_test and has_non_test:
        test_files = [f for f in proposal.files_changed if _is_test_file(f)]
        signals.append(
            RiskSignal(
                code="test-modified",
                label="製品コードとテストの両方を変更しています",
                detail=f"テスト: {', '.join(test_files)}",
                severity="medium",
            )
        )

    # 兆候 4: large-diff (medium)
    total_added = sum(s["added"] for s in diff_stats.values())
    total_removed = sum(s["removed"] for s in diff_stats.values())
    if (total_added + total_removed) > 300:
        signals.append(
            RiskSignal(
                code="large-diff",
                label="変更量が多いです",
                detail=f"追加 {total_added} 行 + 削除 {total_removed} 行",
                severity="medium",
            )
        )

    # 兆候 5: assert-removed (high)
    if _has_removed_assert(proposal.diff):
        signals.append(
            RiskSignal(
                code="assert-removed",
                label="アサーションが削除されています",
                detail="削除行に assert または self.assert が含まれる",
                severity="high",
            )
        )

    # 兆候 6: skip-added (high)
    if _has_skip_added(proposal.diff):
        signals.append(
            RiskSignal(
                code="skip-added",
                label="テストスキップが追加されています",
                detail="追加行に @pytest.mark.skip / @unittest.skip / pytest.xfail",
                severity="high",
            )
        )

    # 兆候 7: exception-swallowed (medium)
    if _has_exception_swallowed(proposal.diff):
        signals.append(
            RiskSignal(
                code="exception-swallowed",
                label="例外が握り潰されています",
                detail="追加行に except → pass",
                severity="medium",
            )
        )

    return tuple(_sort_by_severity(signals))


# ─────────────────────────────────────────────────────────────────
# ヘルパー関数
# ─────────────────────────────────────────────────────────────────


def _is_test_file(path: str) -> bool:
    """ファイルパスがテストファイルかを判定する。"""
    return (
        path.startswith("test_")
        or path.startswith("tests/")
        or path.endswith("_test.py")
        or "/tests/" in path
    )


def _has_removed_assert(diff: str) -> bool:
    """削除行に assert を含むかを判定する。"""
    for line in diff.splitlines():
        if line.startswith("-") and not line.startswith("---"):
            # 削除行の内容（- を除いた部分）
            content = line[1:]
            if "assert" in content.lower():
                return True
    return False


def _has_skip_added(diff: str) -> bool:
    """追加行にテストスキップ指示を含むかを判定する。"""
    patterns = [
        r"@pytest\.mark\.skip",
        r"@unittest\.skip",
        r"pytest\.xfail",
    ]
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            content = line[1:]
            for pattern in patterns:
                if re.search(pattern, content):
                    return True
    return False


def _has_exception_swallowed(diff: str) -> bool:
    """追加行に except → pass を含むかを判定する。"""
    lines = diff.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("+") and not line.startswith("+++"):
            content = line[1:].strip()
            if content.startswith("except"):
                # 次の行を確認（pass かどうか）
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    if next_line.startswith("+") and not next_line.startswith("+++"):
                        next_content = next_line[1:].strip()
                        if next_content == "pass":
                            return True
    return False


def _sort_by_severity(signals: list[RiskSignal]) -> list[RiskSignal]:
    """重大度順（high → medium → low）にソートする。"""
    severity_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(signals, key=lambda s: severity_order.get(s.severity, 3))
