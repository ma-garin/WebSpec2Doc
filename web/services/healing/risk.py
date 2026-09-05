"""修正案の過適合リスク検出。
判定はしない。危険兆候を列挙するだけ。
"""

from __future__ import annotations

from dataclasses import dataclass
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
# 行単位の正規表現（複数行をまたがせない。必ず 1 行ずつ当てる）
# ─────────────────────────────────────────────────────────────────

_DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)")
_CLASS_RE = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)")
_HUNK_RE = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")
_FENCE_RE = re.compile(r"^\s*```")
_SKIP_PATTERNS = (r"@pytest\.mark\.skip", r"@unittest\.skip", r"pytest\.xfail")

#: 全面書き換えとみなす削除比率（元行数比）。
_FULL_REWRITE_RATIO = 0.8
#: 元行数が取れない場合の代替しきい値。
_FALLBACK_REMOVED_LINES = 20
_FALLBACK_REMOVED_RATIO = 0.6


# ─────────────────────────────────────────────────────────────────
# diff パース
# ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Hunk:
    """統一 diff のハンクヘッダ 1 個分（@@ -old_start,old_count +new_start,new_count @@）。"""

    old_start: int
    old_count: int
    new_start: int
    new_count: int


@dataclass(frozen=True)
class _FileDiff:
    """1 ファイル分の diff。追加行・削除行は先頭の +/- を除いた内容だけを持つ。"""

    path: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    hunks: tuple[_Hunk, ...]


def parse_diff_stats(diff: str) -> dict[str, dict[str, int]]:
    """統一 diff をファイル別の {"added": n, "removed": n} に分解する。

    `diff --git` 形式と `--- a/` 単独形式の両方に対応している。

    Args:
        diff: diff 形式の文字列

    Returns:
        {ファイルパス: {"added": 行数, "removed": 行数}}
    """
    # _parse_file_diffs で完全にパースして、結果から統計を導出する
    files = _parse_file_diffs(diff)
    stats: dict[str, dict[str, int]] = {}
    for file_diff in files:
        stats[file_diff.path] = {
            "added": len(file_diff.added),
            "removed": len(file_diff.removed),
        }
    return stats


def _new_block(path: str) -> dict:
    """パース途中のファイルブロック 1 個を作る。"""
    return {"path": path, "added": [], "removed": [], "hunks": [], "seen": False}


def _path_from_git_line(line: str) -> str:
    """`diff --git a/x b/x` から b/ 側のパスを取る。取れなければ空文字。"""
    parts = line.split(" b/", 1)
    return parts[1].strip() if len(parts) == 2 else ""


def _strip_ab(text: str) -> str:
    """`--- a/path` / `+++ b/path` の値からプレフィクスと日時を落とす。"""
    path = text.strip().split("\t", 1)[0].strip()
    if path in ("", "/dev/null"):
        return ""
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def _parse_hunk(line: str) -> _Hunk | None:
    """ハンクヘッダ 1 行を _Hunk にする。形式が合わなければ None。"""
    match = _HUNK_RE.match(line)
    if match is None:
        return None
    old_start, old_count, new_start, new_count = match.groups()
    return _Hunk(
        old_start=int(old_start),
        old_count=int(old_count) if old_count is not None else 1,
        new_start=int(new_start),
        new_count=int(new_count) if new_count is not None else 1,
    )


def _parse_file_diffs(diff: str) -> tuple[_FileDiff, ...]:
    """統一 diff をファイル単位（追加行・削除行・ハンク）に分解する。1 行ずつ処理する。"""
    blocks: list[dict] = []
    current: dict | None = None

    for line in diff.splitlines():
        if line.startswith("diff --git"):
            current = _new_block(_path_from_git_line(line))
            blocks.append(current)
        elif line.startswith("--- "):
            if current is None or current["seen"]:
                current = _new_block("")
                blocks.append(current)
            if not current["path"]:
                current["path"] = _strip_ab(line[4:])
        elif line.startswith("+++ "):
            if current is not None and not current["path"]:
                current["path"] = _strip_ab(line[4:])
        elif line.startswith("@@"):
            hunk = _parse_hunk(line)
            if current is not None and hunk is not None:
                current["hunks"].append(hunk)
                current["seen"] = True
        elif line.startswith("+") and current is not None:
            current["added"].append(line[1:])
            current["seen"] = True
        elif line.startswith("-") and current is not None:
            current["removed"].append(line[1:])
            current["seen"] = True

    return tuple(
        _FileDiff(
            path=block["path"] or "(ファイル名不明)",
            added=tuple(block["added"]),
            removed=tuple(block["removed"]),
            hunks=tuple(block["hunks"]),
        )
        for block in blocks
    )


# ─────────────────────────────────────────────────────────────────
# リスク検出
# ─────────────────────────────────────────────────────────────────


def assess(proposal: FixProposal) -> tuple[RiskSignal, ...]:
    """修正案から過適合のおそれがある兆候を列挙する。重大度降順。

    Args:
        proposal: 修正案

    Returns:
        検出された RiskSignal のタプル（severity 降順・同 severity 内は code 昇順）
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
            return tuple(_sort_signals(signals))

    files = _parse_file_diffs(proposal.diff)

    signals.extend(_assess_file_scope(proposal))
    signals.extend(_assess_diff_content(proposal.diff))
    signals.extend(_assess_rewrite(files))

    return tuple(_sort_signals(signals))


def _assess_file_scope(proposal: FixProposal) -> list[RiskSignal]:
    """変更ファイルの構成と変更量から出る兆候（tests-only / test-modified / large-diff）。"""
    signals: list[RiskSignal] = []
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

    return signals


def _assess_diff_content(diff: str) -> list[RiskSignal]:
    """diff の中身から出る兆候（assert-removed / skip-added / exception-swallowed）。"""
    signals: list[RiskSignal] = []

    # 兆候 5: assert-removed (high)
    if _has_removed_assert(diff):
        signals.append(
            RiskSignal(
                code="assert-removed",
                label="アサーションが削除されています",
                detail="削除行に assert または self.assert が含まれる",
                severity="high",
            )
        )

    # 兆候 6: skip-added (high)
    if _has_skip_added(diff):
        signals.append(
            RiskSignal(
                code="skip-added",
                label="テストスキップが追加されています",
                detail="追加行に @pytest.mark.skip / @unittest.skip / pytest.xfail",
                severity="high",
            )
        )

    # 兆候 7: exception-swallowed (medium)
    if _has_exception_swallowed(diff):
        signals.append(
            RiskSignal(
                code="exception-swallowed",
                label="例外が握り潰されています",
                detail="追加行に except → pass",
                severity="medium",
            )
        )

    return signals


def _assess_rewrite(files: tuple[_FileDiff, ...]) -> list[RiskSignal]:
    """書き換え方から出る兆候（symbol-removed / code-fence-written / full-rewrite / ... ）。"""
    detected = (
        _detect_symbol_removed(files),
        _detect_code_fence_written(files),
        _detect_full_rewrite(files),
        _detect_unrelated_addition(files),
        _detect_type_hints_dropped(files),
    )
    return [signal for signal in detected if signal is not None]


# ─────────────────────────────────────────────────────────────────
# 新規兆候の検出
# ─────────────────────────────────────────────────────────────────


def _detect_symbol_removed(files: tuple[_FileDiff, ...]) -> RiskSignal | None:
    """兆候 8: 削除行にあった def / class が、追加行に同名で現れない (high)。"""
    lost: list[str] = []
    for file_diff in files:
        added_names = set(_defined_names(file_diff.added))
        for name in _defined_names(file_diff.removed):
            if name not in added_names:
                lost.append(f"{file_diff.path}: {name}")
    if not lost:
        return None
    return RiskSignal(
        code="symbol-removed",
        label="既存の関数・クラスが削除されています",
        detail="追加行に同名の定義が無い: " + ", ".join(lost),
        severity="high",
    )


def _detect_code_fence_written(files: tuple[_FileDiff, ...]) -> RiskSignal | None:
    """兆候 9: 追加行に ``` で始まる行がある (high)。"""
    hits: list[str] = []
    for file_diff in files:
        count = sum(1 for line in file_diff.added if _FENCE_RE.match(line))
        if count:
            hits.append(f"{file_diff.path}: {count} 行")
    if not hits:
        return None
    return RiskSignal(
        code="code-fence-written",
        label="モデルがコードフェンスをファイルに書き込んでいます",
        detail="``` で始まる追加行 — " + ", ".join(hits),
        severity="high",
    )


def _detect_full_rewrite(files: tuple[_FileDiff, ...]) -> RiskSignal | None:
    """兆候 10: 1 ファイルがほぼ全面的に書き換えられている (high)。"""
    reasons: list[str] = []
    for file_diff in files:
        removed = len(file_diff.removed)
        added = len(file_diff.added)
        original = sum(hunk.old_count for hunk in file_diff.hunks)
        whole = _whole_file_hunk(file_diff)
        if original > 0 and removed >= original * _FULL_REWRITE_RATIO:
            reasons.append(f"{file_diff.path}: 元 {original} 行のうち {removed} 行を削除")
        elif whole is not None:
            reasons.append(
                f"{file_diff.path}: 先頭からの 1 ハンクで元 {whole.old_count} 行を"
                f" {whole.new_count} 行に置換"
            )
        elif (
            original == 0
            and removed >= _FALLBACK_REMOVED_LINES
            and removed >= added * _FALLBACK_REMOVED_RATIO
        ):
            reasons.append(f"{file_diff.path}: 削除 {removed} 行 / 追加 {added} 行（元行数は不明）")
    if not reasons:
        return None
    return RiskSignal(
        code="full-rewrite",
        label="ファイルがほぼ全面的に書き換えられています",
        detail=", ".join(reasons),
        severity="high",
    )


def _whole_file_hunk(file_diff: _FileDiff) -> _Hunk | None:
    """ファイル全体が 1 ハンクで置き換えられ、行数が 2 倍以上に膨らんでいれば返す。"""
    if len(file_diff.hunks) != 1:
        return None
    hunk = file_diff.hunks[0]
    if hunk.old_start > 1 or hunk.old_count <= 0:
        return None
    if hunk.new_count < hunk.old_count * 2:
        return None
    return hunk


def _detect_unrelated_addition(files: tuple[_FileDiff, ...]) -> RiskSignal | None:
    """兆候 11: 削除行に無い新しい def / class が 2 個以上追加されている (medium)。"""
    new_symbols: list[str] = []
    for file_diff in files:
        removed_names = set(_defined_names(file_diff.removed))
        for name in _defined_names(file_diff.added):
            if name not in removed_names:
                new_symbols.append(f"{file_diff.path}: {name}")
    if len(new_symbols) < 2:
        return None
    return RiskSignal(
        code="unrelated-addition",
        label="欠陥と関係のない定義が追加されている可能性があります",
        detail=f"削除行に無い新しい定義 {len(new_symbols)} 個: " + ", ".join(new_symbols),
        severity="medium",
    )


def _detect_type_hints_dropped(files: tuple[_FileDiff, ...]) -> RiskSignal | None:
    """兆候 12: 型注釈付きの関数が、同名の注釈なし関数に置き換わっている (low)。"""
    dropped: list[str] = []
    for file_diff in files:
        added_defs = _def_annotations(file_diff.added)
        for name, annotated in _def_annotations(file_diff.removed).items():
            if annotated and added_defs.get(name) is False:
                dropped.append(f"{file_diff.path}: {name}")
    if not dropped:
        return None
    return RiskSignal(
        code="type-hints-dropped",
        label="関数の型注釈が失われています",
        detail="削除行では注釈あり・追加行では注釈なし: " + ", ".join(dropped),
        severity="low",
    )


# ─────────────────────────────────────────────────────────────────
# ヘルパー関数
# ─────────────────────────────────────────────────────────────────


def _defined_names(lines: tuple[str, ...]) -> list[str]:
    """行の集合から def / class の名前を出現順・重複なしで取り出す。"""
    names: list[str] = []
    for line in lines:
        match = _DEF_RE.match(line) or _CLASS_RE.match(line)
        if match is not None and match.group(1) not in names:
            names.append(match.group(1))
    return names


def _def_annotations(lines: tuple[str, ...]) -> dict[str, bool]:
    """def 行から {関数名: 型注釈があるか} を作る。同名が複数あれば「注釈あり」を優先する。"""
    result: dict[str, bool] = {}
    for line in lines:
        match = _DEF_RE.match(line)
        if match is None:
            continue
        name = match.group(1)
        annotated = _is_annotated_def(line)
        result[name] = result.get(name, False) or annotated
    return result


def _is_annotated_def(line: str) -> bool:
    """def 行 1 行に引数注釈または戻り値注釈があるかを判定する。"""
    open_paren = line.find("(")
    close_paren = line.rfind(")")
    if open_paren < 0 or close_paren < open_paren:
        return False
    params = line[open_paren + 1 : close_paren]
    tail = line[close_paren + 1 :]
    return ":" in params or "->" in tail


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
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            content = line[1:]
            for pattern in _SKIP_PATTERNS:
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


def _sort_signals(signals: list[RiskSignal]) -> list[RiskSignal]:
    """重大度順（high → medium → low）、同 severity 内は code 昇順で安定させる。"""
    severity_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(signals, key=lambda s: (severity_order.get(s.severity, 3), s.code))


def _sort_by_severity(signals: list[RiskSignal]) -> list[RiskSignal]:
    """後方互換のための別名。_sort_signals を使うこと。"""
    return _sort_signals(signals)
