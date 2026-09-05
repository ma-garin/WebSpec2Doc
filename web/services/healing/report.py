"""欠陥レポートを Markdown で組み立てるモジュール。"""

from typing import Sequence

from . import localization, risk
from . import types


def _escape_pipe(text: str) -> str:
    r"""Markdown テーブル内の | を \| にエスケープ。"""
    return text.replace("|", "\\|")


def build_report(
    defect: types.Defect,
    proposal: types.FixProposal | None,
    evidence: Sequence[localization.LocationEvidence] = (),
    risks: Sequence[risk.RiskSignal] = (),
) -> str:
    """1 欠陥ぶんのバグレポートを Markdown で組み立てる。

    Args:
        defect: 欠陥情報
        proposal: 修正案（None の場合もある）
        evidence: 該当箇所の根拠（降順ソート済みが期待される）
        risks: 修正後の確認が必要な点

    Returns:
        Markdown 形式のレポート文字列
    """
    severity_map = {"high": "高", "medium": "中", "low": "低"}
    source_map = {"validation": "検証", "static_analysis": "静的解析", "manual": "手動"}
    reason_map = {
        "traceback": "実行時トレース",
        "import": "import 関係",
        "recent-change": "直近の変更",
        "test-name": "テスト名",
    }

    # ヘッダと基本情報表
    lines = [
        f"### {_escape_pipe(defect.title)}",
        "",
        "| 項目 | 内容 |",
        "|---|---|",
        f"| 重大度 | {severity_map.get(defect.severity, defect.severity)} |",
        f"| 検出元 | {source_map.get(defect.source, defect.source)} |",
        f"| テスト | {defect.test_id or '—'} |",
        f"| 担当エージェント | {proposal.agent if proposal else '—'} |",
        "",
    ]

    # 事象
    lines.append("**事象**")
    if defect.message:
        lines.append(f"> {_escape_pipe(defect.message)}")
    else:
        lines.append("> 記録なし")
    lines.append("")

    # 原因の判定
    lines.append("**原因の判断**")
    if proposal and proposal.rationale:
        lines.append(_escape_pipe(proposal.rationale))
    else:
        lines.append("未判定（修正案が生成されていません）")
    lines.append("")

    # 該当箇所の根拠
    lines.append("**該当箇所の根拠**")
    if evidence:
        lines.append("| ファイル | 根拠 | 確度 |")
        lines.append("|---|---|---|")
        for ev in sorted(evidence, key=lambda e: e.score, reverse=True):
            reason_label = reason_map.get(ev.reason, ev.reason)
            confidence = int(ev.score * 100)
            lines.append(
                f"| {_escape_pipe(ev.path)} | {_escape_pipe(reason_label)} | {confidence}% |"
            )
    else:
        lines.append("根拠を特定できませんでした")
    lines.append("")

    # 修正差分
    lines.append("**修正差分**")
    if proposal and proposal.files_changed:
        for file_path in proposal.files_changed:
            lines.append(f"- {_escape_pipe(file_path)}")
        if proposal.diff:
            lines.append("")
            lines.append("```diff")
            lines.append(proposal.diff)
            lines.append("```")
    else:
        lines.append("差分なし")
    lines.append("")

    # 確認が必要な点
    lines.append("**確認が必要な点**")
    if risks:
        for signal in risks:
            prefix = "⚠ " if signal.severity == "high" else ""
            lines.append(f"- {prefix}{_escape_pipe(signal.label)}: {_escape_pipe(signal.detail)}")
    else:
        lines.append(
            "機械的に検出できる危険な兆候はありませんでした。"
            "ただしテストの通過は正しさを保証しません。差分を確認してください。"
        )

    return "\n".join(lines)


def build_pr_section(reports: Sequence[str]) -> str:
    """複数のレポートを PR 本文用に連結する。

    Args:
        reports: build_report() の出力列

    Returns:
        PR 本文用の Markdown テキスト
    """
    if not reports:
        return ""
    return "\n\n---\n\n".join(reports)
