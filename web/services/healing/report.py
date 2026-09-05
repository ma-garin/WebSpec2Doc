"""欠陥レポートを Markdown で組み立てるモジュール。

出力は画面と PR 本文の両方で使う。ここで書いてよいのは「観測された事実」と
「エージェントが自己申告した判断」だけで、修正の正しさを断定してはならない。
"""

from typing import Sequence

from . import localization, risk
from . import types

#: 重大度の表示ラベル。types.SEVERITIES の語彙に合わせる。
_SEVERITY_LABELS: dict[str, str] = {
    "critical": "重大",
    "high": "高",
    "medium": "中",
    "low": "低",
}

#: 検出元の表示ラベル。types.Defect.source の語彙（verify / static / manual）が正。
#: 旧語彙で保存された履歴も読めるよう、旧キーも残す。未知の値は原文のまま出す。
_SOURCE_LABELS: dict[str, str] = {
    "verify": "検証",
    "static": "静的解析",
    "manual": "手動",
    "validation": "検証",
    "static_analysis": "静的解析",
}

#: 限局の根拠の表示ラベル。
_REASON_LABELS: dict[str, str] = {
    "traceback": "実行時トレース",
    "import": "import 関係",
    "recent-change": "直近の変更",
    "test-name": "テスト名",
}

#: 修正エージェントの表示ラベル。agents.py のレジストリキーが正。
#: 未知の値は原文のまま出す（勝手に別名へ寄せない）。
_AGENT_LABELS: dict[str, str] = {
    "claude": "Claude Code",
    "codex": "Codex",
    "openai": "OpenAI",
    "ollama": "Ollama",
    "dryrun": "動作確認用",
}

#: エージェントの説明に必ず添える注記。内容の正しさは保証できない。
_AGENT_DISCLAIMER = "※ これはエージェントの自己申告です。差分で確認してください。"


def _escape_pipe(text: str) -> str:
    r"""Markdown テーブル内の | を \| にエスケープ。"""
    return text.replace("|", "\\|")


def _agent_label(agent: str) -> str:
    """エージェントキーを表示名にする。未知の値は原文のまま返す。"""
    return _AGENT_LABELS.get(agent, agent)


def _count_risks(risks: Sequence[risk.RiskSignal]) -> tuple[int, int, int]:
    """リスク信号を (高, 中, 低) の件数に数える。未知の severity は低に寄せない。"""
    high = sum(1 for s in risks if s.severity == "high")
    medium = sum(1 for s in risks if s.severity == "medium")
    low = sum(1 for s in risks if s.severity == "low")
    return high, medium, low


def _format_risk_counts(risks: Sequence[risk.RiskSignal]) -> str:
    """「高 N 件 / 中 M 件 / 低 K 件」の表記を作る。"""
    high, medium, low = _count_risks(risks)
    return f"高 {high} 件 / 中 {medium} 件 / 低 {low} 件"


def _first_line(text: str) -> str:
    """複数行の値から先頭の非空行だけを取り出す（見出しを壊さないため）。"""
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _build_header(
    defect: types.Defect,
    proposal: types.FixProposal | None,
    run_id: str,
    repo: str,
    started_at: str,
    risks: Sequence[risk.RiskSignal] = (),
) -> list[str]:
    """見出しと基本情報表を組み立てる。"""
    # 見出しは「何が失敗したか」。失敗メッセージそのものは事象節に置く。
    subject = defect.test_id or _first_line(defect.title) or "不明なテスト"
    agent = _agent_label(proposal.agent) if proposal else ""
    rows = [
        # 重大度は検出時の値をそのまま出す（リスクで書き換えると事実が歪む）。
        f"| 重大度 | {_SEVERITY_LABELS.get(defect.severity, defect.severity)} |",
        f"| 検出元 | {_SOURCE_LABELS.get(defect.source, defect.source)} |",
        f"| テスト | {_escape_pipe(defect.test_id) or '—'} |",
        f"| 担当エージェント | {_escape_pipe(agent) or '—'} |",
    ]
    # 高リスクがあるときだけ、重大度とは別の行として件数を添える。
    if any(signal.severity == "high" for signal in risks):
        rows.append(f"| 確認が必要な点 | {_escape_pipe(_format_risk_counts(risks))} |")
    # 実行の文脈は渡されたときだけ足す（PR へ単体で貼っても話が通じるように）。
    context = (("実行 ID", run_id), ("対象", repo), ("開始", started_at))
    rows += [f"| {label} | {_escape_pipe(value)} |" for label, value in context if value]
    return [
        f"### {_first_line(subject)} が失敗しています",
        "",
        "| 項目 | 内容 |",
        "|---|---|",
        *rows,
        "",
    ]


def _build_symptom(defect: types.Defect) -> list[str]:
    """事象節。観測されたメッセージをそのまま引用する。"""
    body = defect.message or defect.title
    lines = ["**事象**"]
    if body:
        # 全行に > を付ける。空行は > だけにしないと引用が途切れる。
        for line in body.splitlines():
            escaped = _escape_pipe(line)
            lines.append(f"> {escaped}" if escaped.strip() else ">")
    else:
        lines.append("> 記録なし")
    lines.append("")
    return lines


def _build_explanation(proposal: types.FixProposal | None) -> list[str]:
    """エージェントの説明節。原因である保証がないので原因とは名乗らせない。"""
    lines = ["**エージェントの説明**"]
    if proposal and proposal.rationale:
        lines.append(_escape_pipe(proposal.rationale))
    else:
        lines.append("説明なし（修正案が生成されていません）")
    lines += ["", _AGENT_DISCLAIMER, ""]
    return lines


def _build_evidence(evidence: Sequence[localization.LocationEvidence]) -> list[str]:
    """該当箇所の根拠節。スコア降順で並べる。"""
    lines = ["**該当箇所の根拠**"]
    if not evidence:
        return lines + ["根拠を特定できませんでした", ""]
    lines += ["| ファイル | 根拠 | 確度 |", "|---|---|---|"]
    for ev in sorted(evidence, key=lambda e: e.score, reverse=True):
        reason_label = _REASON_LABELS.get(ev.reason, ev.reason)
        lines.append(
            f"| {_escape_pipe(ev.path)} | {_escape_pipe(reason_label)} |"
            f" {int(ev.score * 100)}% |"
        )
    lines.append("")
    return lines


def _build_diff(proposal: types.FixProposal | None) -> list[str]:
    """修正差分節。見出しは「変更したファイル（N 件）」1 個だけにする。"""
    if not (proposal and proposal.files_changed):
        return ["**変更したファイル**", "差分なし", ""]
    lines = [f"**変更したファイル（{len(proposal.files_changed)} 件）**"]
    lines += [f"- {_escape_pipe(path)}" for path in proposal.files_changed]
    if proposal.diff:
        lines += ["", "```diff", proposal.diff, "```"]
    lines.append("")
    return lines


def _build_risks(risks: Sequence[risk.RiskSignal]) -> list[str]:
    """確認が必要な点。空でも「問題なし」とは書かない。"""
    lines = ["**確認が必要な点**"]
    if not risks:
        lines.append(
            "機械的に検出できる危険な兆候はありませんでした。"
            "ただしテストの通過は正しさを保証しません。差分を確認してください。"
        )
        return lines
    for signal in risks:
        prefix = "⚠ " if signal.severity == "high" else ""
        lines.append(f"- {prefix}{_escape_pipe(signal.label)}: {_escape_pipe(signal.detail)}")
    return lines


def build_report(
    defect: types.Defect,
    proposal: types.FixProposal | None,
    evidence: Sequence[localization.LocationEvidence] = (),
    risks: Sequence[risk.RiskSignal] = (),
    *,
    run_id: str = "",
    repo: str = "",
    started_at: str = "",
) -> str:
    """1 欠陥ぶんのバグレポートを Markdown で組み立てる。

    Args:
        defect: 欠陥情報
        proposal: 修正案（None の場合もある）
        evidence: 該当箇所の根拠（降順ソート済みが期待される）
        risks: 修正後の確認が必要な点
        run_id: 実行 ID。渡されたときだけ表に出す
        repo: 対象リポジトリ。渡されたときだけ表に出す
        started_at: 実行開始時刻。渡されたときだけ表に出す

    Returns:
        Markdown 形式のレポート文字列
    """
    lines = _build_header(defect, proposal, run_id, repo, started_at, risks)
    lines += _build_symptom(defect)
    lines += _build_explanation(proposal)
    lines += _build_evidence(evidence)
    lines += _build_diff(proposal)
    lines += _build_risks(risks)
    return "\n".join(lines)


def build_pr_section(
    reports: Sequence[str],
    risks: Sequence[risk.RiskSignal] = (),
) -> str:
    """複数のレポートを PR 本文用に連結する。

    Args:
        reports: build_report() の出力列
        risks: 全欠陥ぶんの確認が必要な点。総数の要約に使う

    Returns:
        PR 本文用の Markdown テキスト
    """
    if not reports:
        return ""
    header = [
        "このPRは自動生成された修正案です。テストの通過は正しさを保証しません。",
        "",
        f"**欠陥 {len(reports)} 件**の修正案を含みます。内容は人が確認してください。",
    ]
    if risks:
        # 高が 1 件でもあれば行頭に ⚠ を付けて目に入るようにする。
        mark = "⚠ " if any(s.severity == "high" for s in risks) else ""
        header += ["", f"{mark}**確認が必要な点**: {_format_risk_counts(risks)}"]
    # 各レポートの前に区切りを置く（GitHub 上で欠陥の境目が分かるように）。
    body = "".join(f"\n\n---\n\n{report}" for report in reports)
    return "\n".join(header) + body
