"""オートヒーリング（System 05）の修正エージェント層。

この機能の「並列・切り出しができる仕組み」の実体。1 件の Defect を 1 本の
エージェントに丸ごと委任し、結果を FixProposal（判断）として回収する。
orchestrator は types.HealingAgent Protocol にしか依存しないため、
ここへの追加・差し替え・別プロセスへの切り出しは自由に行える。
"""

from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404 - shell=False固定・固定コマンド列のみ実行
import time
from typing import Any

from web.services.healing.types import (
    AgentTask,
    ConnectionCheck,
    FixProposal,
    HealingAgent,
    HealingError,
)

# ─────────────────────────── プロンプト ───────────────────────────


def build_prompt(task: AgentTask) -> str:
    """エージェントに渡す日本語の指示文を組み立てる。"""
    defect = task.defect
    evidence = (defect.evidence or "")[:4000]
    suspects = ", ".join(defect.suspect_files) if defect.suspect_files else "（推定できず）"
    test_id = defect.test_id or "（なし）"
    extra = task.extra_instructions or "（なし）"

    return f"""あなたはこのリポジトリの不具合を 1 件だけ直します。

# 対象の不具合
タイトル: {defect.title}
重大度: {defect.severity}
失敗したテスト: {test_id}
メッセージ:
```
{defect.message}
```
証跡:
```
{evidence}
```
該当しそうなファイル: {suspects}

# 守ること
- 直すのは上の 1 件だけ。ついでの整形・リファクタリング・依存の更新をしない。
- テストを通すためにテスト側を書き換えて逃げない。実装を直す。それが不可能なら理由を述べて何も変更しない。
- 変更は最小にする。
- コミットはしない（差分は呼び出し側が回収する）。
- `{task.verify_command}` で検証できる。実行して確認してよい。

# 追加の指示
{extra}

# 出力
最後に、何が原因で・何をどう直したかを 3 行以内で述べること。
"""


# ─────────────────────────── 共通ヘルパー ───────────────────────────


def _tail(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _collect_worktree_change(workdir: str) -> tuple[str, tuple[str, ...]]:
    """workdir の変更をコミットせずに git add + diff で回収する。

    git_ops は import しない（他エージェントが並行実装中で未完成の可能性が
    あるため）。ここだけ自前で最小限の 3 コマンドを呼ぶ。
    """
    try:
        subprocess.run(  # nosec B603 - shell=False固定・固定引数のみ
            ["git", "-C", workdir, "add", "-A"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        diff_proc = subprocess.run(  # nosec B603 - shell=False固定・固定引数のみ
            ["git", "-C", workdir, "diff", "--cached"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        names_proc = subprocess.run(  # nosec B603 - shell=False固定・固定引数のみ
            ["git", "-C", workdir, "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "", ()

    diff = diff_proc.stdout or ""
    files = tuple(f for f in (names_proc.stdout or "").splitlines() if f.strip())
    return diff, files


def _extract_result_text(stdout: str) -> tuple[str, str]:
    """claude CLI の --output-format json 出力から result フィールドを取り出す。

    取得できない場合は空文字と、取れなかった理由の注記を返す（黙って諦めない）。
    """
    text = (stdout or "").strip()
    if not text:
        return "", "CLI標準出力が空でした。"
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError:
        lines = text.splitlines()
        last_line = lines[-1] if lines else ""
        try:
            data = json.loads(last_line)
        except json.JSONDecodeError:
            return "", "CLI出力をJSONとして解釈できませんでした。"
    if isinstance(data, dict):
        result = data.get("result")
        if isinstance(result, str) and result.strip():
            return result.strip(), ""
    return "", "JSON出力にresultフィールドが見つかりませんでした。"


# ─────────────────────────── エージェント実装 ───────────────────────────


class ClaudeCodeAgent:
    """claude CLI に 1 件の Defect を丸ごと委任するエージェント。"""

    name = "claude"

    def is_available(self) -> ConnectionCheck:
        path = shutil.which("claude")
        if path:
            return ConnectionCheck(key="agent", label="Claude Code（claude CLI）", ok=True, detail=path)
        return ConnectionCheck(
            key="agent",
            label="Claude Code（claude CLI）",
            ok=False,
            detail="claude コマンドが見つかりません（PATH を確認してください）",
        )

    def propose_fix(self, task: AgentTask) -> FixProposal:
        """例外は投げない。失敗時も必ず FixProposal を返す。"""
        prompt = build_prompt(task)
        start = time.monotonic()
        try:
            proc = subprocess.run(  # nosec B603 - shell=False固定・引数固定・プロンプトはstdinで渡す
                ["claude", "-p", "--permission-mode", "acceptEdits", "--output-format", "json"],
                cwd=task.workdir,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=task.timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - start
            out = exc.stdout if isinstance(exc.stdout, str) else ""
            err = exc.stderr if isinstance(exc.stderr, str) else ""
            return FixProposal(
                defect_id=task.defect.defect_id,
                agent=self.name,
                status="timeout",
                summary=f"{task.timeout_sec} 秒で時間切れになりました",
                duration_sec=duration,
                log_tail=_tail(out + err),
                error="timeout",
            )
        except OSError as exc:
            duration = time.monotonic() - start
            return FixProposal(
                defect_id=task.defect.defect_id,
                agent=self.name,
                status="failed",
                summary="claude CLI を起動できませんでした",
                duration_sec=duration,
                error=str(exc),
            )

        duration = time.monotonic() - start
        raw_output = (proc.stdout or "") + (proc.stderr or "")
        result_text, missing_note = _extract_result_text(proc.stdout or "")
        diff, files = _collect_worktree_change(task.workdir)

        if not diff:
            return FixProposal(
                defect_id=task.defect.defect_id,
                agent=self.name,
                status="skipped",
                summary="変更なし（エージェントは修正不要と判断したか、失敗した）",
                rationale=result_text or missing_note,
                log_tail=_tail(raw_output),
                duration_sec=duration,
            )

        if result_text:
            summary = result_text
            rationale = result_text
        else:
            summary = _tail(raw_output, 400)
            rationale = f"{missing_note}（CLI出力からresultフィールドを取得できなかったため、log_tail末尾をsummaryに使用）"

        return FixProposal(
            defect_id=task.defect.defect_id,
            agent=self.name,
            status="applied",
            summary=summary,
            rationale=rationale,
            diff=diff,
            files_changed=files,
            log_tail=_tail(raw_output),
            duration_sec=duration,
        )


class CodexAgent:
    """codex CLI に 1 件の Defect を丸ごと委任するエージェント。"""

    name = "codex"

    def is_available(self) -> ConnectionCheck:
        path = shutil.which("codex")
        if path:
            return ConnectionCheck(key="agent", label="Codex（codex CLI）", ok=True, detail=path)
        return ConnectionCheck(
            key="agent",
            label="Codex（codex CLI）",
            ok=False,
            detail="codex コマンドが見つかりません（PATH を確認してください）",
        )

    def propose_fix(self, task: AgentTask) -> FixProposal:
        """例外は投げない。失敗時も必ず FixProposal を返す。"""
        prompt = build_prompt(task)
        start = time.monotonic()
        try:
            proc = subprocess.run(  # nosec B603 - shell=False固定・引数固定
                ["codex", "exec", "--full-auto", prompt],
                cwd=task.workdir,
                capture_output=True,
                text=True,
                timeout=task.timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - start
            out = exc.stdout if isinstance(exc.stdout, str) else ""
            err = exc.stderr if isinstance(exc.stderr, str) else ""
            return FixProposal(
                defect_id=task.defect.defect_id,
                agent=self.name,
                status="timeout",
                summary=f"{task.timeout_sec} 秒で時間切れになりました",
                duration_sec=duration,
                log_tail=_tail(out + err),
                error="timeout",
            )
        except OSError as exc:
            duration = time.monotonic() - start
            return FixProposal(
                defect_id=task.defect.defect_id,
                agent=self.name,
                status="failed",
                summary="codex CLI を起動できませんでした",
                duration_sec=duration,
                error=str(exc),
            )

        duration = time.monotonic() - start
        raw_output = (proc.stdout or "") + (proc.stderr or "")
        diff, files = _collect_worktree_change(task.workdir)

        if not diff:
            return FixProposal(
                defect_id=task.defect.defect_id,
                agent=self.name,
                status="skipped",
                summary="変更なし（エージェントは修正不要と判断したか、失敗した）",
                log_tail=_tail(raw_output),
                duration_sec=duration,
            )

        return FixProposal(
            defect_id=task.defect.defect_id,
            agent=self.name,
            status="applied",
            summary=_tail(raw_output, 400),
            rationale="codex CLIの出力にはresult相当のフィールドが無いため、log_tail末尾をsummaryに使用。",
            diff=diff,
            files_changed=files,
            log_tail=_tail(raw_output),
            duration_sec=duration,
        )


class DryRunAgent:
    """外部プロセスを起動しない既定フォールバック。CI・エージェント未導入環境で必ず動く。"""

    name = "dryrun"

    def is_available(self) -> ConnectionCheck:
        return ConnectionCheck(key="agent", label="ドライラン（修正しない）", ok=True, detail="")

    def propose_fix(self, task: AgentTask) -> FixProposal:
        suspects = ", ".join(task.defect.suspect_files) if task.defect.suspect_files else "（推定できず）"
        return FixProposal(
            defect_id=task.defect.defect_id,
            agent=self.name,
            status="proposed",
            summary=f"dryrun: 実際のコード修正は行いません。対象: {suspects}",
            rationale="dryrunエージェントのため常にコード変更は行わない。",
            diff="",
            duration_sec=0.0,
        )


# ─────────────────────────── レジストリ ───────────────────────────

_AGENT_CLASSES: dict[str, type[HealingAgent]] = {
    "claude": ClaudeCodeAgent,
    "codex": CodexAgent,
    "dryrun": DryRunAgent,
}


def available_agents() -> list[str]:
    """レジストリに登録済みのエージェント名一覧。"""
    return list(_AGENT_CLASSES.keys())


def get_agent(name: str) -> HealingAgent:
    """名前からエージェントのインスタンスを得る。未知の名前は HealingError。"""
    cls = _AGENT_CLASSES.get(name)
    if cls is None:
        raise HealingError(f"未知のエージェントです: {name}")
    return cls()


def describe_agents() -> list[dict[str, Any]]:
    """画面の選択肢用に、利用可否込みで一覧化する。"""
    result: list[dict[str, Any]] = []
    for name in available_agents():
        check = get_agent(name).is_available()
        result.append(
            {
                "name": name,
                "label": check.label,
                "available": check.ok,
                "detail": check.detail,
            }
        )
    return result
