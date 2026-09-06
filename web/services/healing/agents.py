"""オートヒーリング（System 05）の修正エージェント層。

この機能の「並列・切り出しができる仕組み」の実体。1 件の Defect を 1 本の
エージェントに丸ごと委任し、結果を FixProposal（判断）として回収する。
orchestrator は types.HealingAgent Protocol にしか依存しないため、
ここへの追加・差し替え・別プロセスへの切り出しは自由に行える。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess  # nosec B404 - shell=False固定・固定コマンド列のみ実行
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from web.services.healing import git_ops
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
最後に、次の 2 つを**日本語で**述べること。この文章は顧客に出す保守報告書に
そのまま載るため、英語・Markdown の装飾（**太字**・見出し・コードフェンス）を使わない。

原因: 何がどうなっていたのか。1〜2 文。
対応: 何をどう変えたのか。1〜2 文。原因の文をそのまま繰り返さない。

例:
原因: 予約確認画面の確定ボタンが管理者ロールに限定されており、一般利用者に表示されていませんでした。
対応: ロールの条件を外し、確定ボタンを常時表示に戻しました。
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


# ─────────────────── LLM API エージェント共通（OpenAI / Ollama） ───────────────────

_OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
_OLLAMA_DEFAULT_MODEL = "qwen2.5-coder:7b"
_OLLAMA_DEFAULT_HOST = "http://127.0.0.1:11434"
_OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

_SYSTEM_PROMPT = (
    "あなたは熟練のソフトウェアエンジニアです。"
    "変更は unified diff だけで返し、説明文やファイル全文を出してはいけません。"
)

# ファイル全文を JSON で返させると、モデルは長い出力の途中で JSON を壊す。
# 壊れれば修正はまるごと失われ、しかも「何を直そうとしたか」も残らない。
# diff なら出力が短く、当たらなければ git 自身が理由を教えてくれる。
_DIFF_FORMAT_INSTRUCTIONS = """

# 出力形式（厳守）
変更は unified diff だけを ```diff で囲んで返してください。
形式:
```diff
--- a/相対パス
+++ b/相対パス
@@ -開始行,行数 +開始行,行数 @@
 変えない行
-消す行
+足す行
```
- diff 以外を出力しない。説明文・前置き・ファイル全文・JSON を付けない。
- パスはリポジトリルートからの相対パスのみ。絶対パスや `..` を含めない。
- 変更が必要ない場合は、空の ```diff ``` を返す。
"""

#: 応答から diff を取り出す。フェンスが無い応答も拾う。
_DIFF_FENCE_RE = re.compile(r"```(?:diff|patch)?\s*\n(.*?)```", re.DOTALL)
#: diff の始まりらしい行。フェンスが無いときはここから末尾までを使う。
_DIFF_START_RE = re.compile(r"^(?:diff --git |--- )", re.MULTILINE)


def _extract_diff(text: str) -> str:
    """モデルの応答から unified diff を取り出す。無ければ空文字。"""
    for match in _DIFF_FENCE_RE.finditer(text or ""):
        body = match.group(1)
        if _DIFF_START_RE.search(body):
            return body.strip("\n")
    match = _DIFF_START_RE.search(text or "")
    return (text[match.start():]).strip("\n") if match else ""


def _llm_prompt(task: AgentTask) -> str:
    """既存の指示文に diff 出力の縛りを足す。"""
    return build_prompt(task) + _DIFF_FORMAT_INSTRUCTIONS


def _redact(text: str) -> str:
    """APIキーが混入していても外へ出さない。"""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key and len(key) >= 8:
        return text.replace(key, "***")
    return text


def _safe_error(exc: BaseException) -> str:
    """例外を日本語の短い文言に畳み、鍵を伏せる。"""
    return _redact(_tail(f"{type(exc).__name__}: {exc}", 500))


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
    """urllib だけで JSON を POST する（外部ライブラリを足さない）。"""
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    for name, value in headers.items():
        req.add_header(name, value)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - httpsまたはローカルhttpのみ
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("APIの応答がJSONオブジェクトではありません。")
    return data


def _apply_with_retry(
    agent_name: str,
    task: AgentTask,
    call: Callable[[str, float], tuple[str, str]],
) -> tuple[str, str, str]:
    """モデルに diff を作らせて当てる。返すのは (応答, ログ, 失敗理由)。

    当たらなかったときは、git のエラーをそのまま添えて 1 度だけ聞き直す。
    人が同じことをするからで、モデルは行番号のずれをこれで直せることが多い。
    2 度目も当たらなければ諦める（3 度目が当たる見込みは薄く、時間だけ延びる）。
    """
    prompt = _llm_prompt(task)
    content, log = call(prompt, float(task.timeout_sec))
    diff = _extract_diff(content)
    if not diff:
        return content, log, "差分が返ってきませんでした"

    ok, detail = git_ops.apply_patch(Path(task.workdir), diff)
    if ok:
        return content, log, ""

    retry_prompt = (
        prompt
        + "\n\n# 直前の差分が当たりませんでした\n"
        + "git apply の出力:\n"
        + detail
        + "\n同じ内容を、当たる形の unified diff で出し直してください。"
    )
    content2, log2 = call(retry_prompt, float(task.timeout_sec))
    diff2 = _extract_diff(content2)
    if not diff2:
        return content2, f"{log} / 再試行: {log2}", f"差分を当てられませんでした（{detail}）"
    ok2, detail2 = git_ops.apply_patch(Path(task.workdir), diff2)
    if ok2:
        return content2, f"{log} / 再試行: {log2}", ""
    return content2, f"{log} / 再試行: {log2}", f"差分を当てられませんでした（{detail2}）"


def _summary_from(content: str) -> tuple[str, str]:
    """diff の前に書かれた文があれば、要約と説明として拾う。

    出力形式では禁じているが、モデルは前置きを書くことがある。
    捨てずに使う（人が読む「対応」の材料になる）。
    """
    match = _DIFF_FENCE_RE.search(content or "") or _DIFF_START_RE.search(content or "")
    head = (content or "")[: match.start()].strip() if match else ""
    if not head:
        return "", ""
    lines = [line.strip() for line in head.splitlines() if line.strip()]
    if not lines:
        return "", ""
    return lines[0][:200], " ".join(lines)[:1000]


def _run_diff_fix(
    agent_name: str, task: AgentTask, call: Callable[[str, float], tuple[str, str]]
) -> FixProposal:
    """LLM に unified diff を作らせて当て、差分を回収する。例外は投げない。"""
    start = time.monotonic()
    try:
        content, log, failure = _apply_with_retry(agent_name, task, call)
    except Exception as exc:  # noqa: BLE001 - どんな失敗も FixProposal へ畳む
        return FixProposal(
            defect_id=task.defect.defect_id,
            agent=agent_name,
            status="failed",
            summary="修正案の生成に失敗しました",
            duration_sec=time.monotonic() - start,
            error=_safe_error(exc),
        )

    duration = time.monotonic() - start
    summary, rationale = _summary_from(content)
    rationale = _redact(rationale)
    if failure:
        return FixProposal(
            defect_id=task.defect.defect_id,
            agent=agent_name,
            status="failed",
            summary="修正を適用できませんでした",
            rationale=rationale,
            log_tail=_tail(_redact(log)),
            duration_sec=duration,
            error=failure[:300],
        )

    diff, changed = _collect_worktree_change(task.workdir)
    if not diff:
        return FixProposal(
            defect_id=task.defect.defect_id,
            agent=agent_name,
            status="skipped",
            summary=summary or "変更なし（モデルは修正不要と判断した）",
            rationale=rationale,
            log_tail=_tail(_redact(log)),
            duration_sec=duration,
        )
    return FixProposal(
        defect_id=task.defect.defect_id,
        agent=agent_name,
        # 変更はすでに worktree のファイルへ当たっているので "applied"。
        # "proposed" にすると統合段（orchestrator）が拾わず、直っているのに
        # 「修正が 1 件も適用されませんでした」で失敗する（2026-09-05 実機で確認）。
        status="applied",
        summary=summary or "LLMが修正案を作成しました",
        rationale=rationale,
        diff=diff,
        files_changed=changed,
        log_tail=_tail(_redact(log)),
        duration_sec=duration,
    )


class OpenAIAgent:
    """OpenAI Chat Completions API に修正後の全文を作らせるエージェント。"""

    name = "openai"
    label = "OpenAI API"

    def is_available(self) -> ConnectionCheck:
        if os.environ.get("OPENAI_API_KEY", "").strip():
            model = os.environ.get("WEBSPEC2DOC_HEALING_OPENAI_MODEL", _OPENAI_DEFAULT_MODEL)
            return ConnectionCheck(key="agent", label=self.label, ok=True, detail=f"モデル: {model}")
        return ConnectionCheck(
            key="agent",
            label=self.label,
            ok=False,
            detail="環境変数 OPENAI_API_KEY が設定されていません",
        )

    def propose_fix(self, task: AgentTask) -> FixProposal:
        """例外は投げない。失敗時も必ず FixProposal を返す。"""
        return _run_diff_fix(self.name, task, self._call)

    def _call(self, prompt: str, timeout: float) -> tuple[str, str]:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("環境変数 OPENAI_API_KEY が設定されていません。")
        model = os.environ.get("WEBSPEC2DOC_HEALING_OPENAI_MODEL", _OPENAI_DEFAULT_MODEL)
        data = _post_json(
            _OPENAI_ENDPOINT,
            {
                "model": model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            },
            {"Authorization": f"Bearer {api_key}"},  # 鍵はヘッダのみ。ログ・戻り値には載せない
            timeout,
        )
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError("OpenAI APIの応答に choices がありません。")
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ValueError("OpenAI APIの応答が空でした。")
        return content, f"model={model} finish_reason={choices[0].get('finish_reason')}"


def _ollama_host() -> str:
    """Ollama のエンドポイント（末尾スラッシュを落とす）。"""
    return os.environ.get("WEBSPEC2DOC_HEALING_OLLAMA_HOST", _OLLAMA_DEFAULT_HOST).rstrip("/")


def _has_model(tags_body: str, model: str) -> bool:
    """/api/tags の応答に、そのモデルがあるか。

    Ollama は "qwen2.5-coder:7b" を "qwen2.5-coder:7b" として返すが、
    タグ無しで指定されることもあるので前方一致も見る。
    """
    try:
        names = [str(m.get("name") or "") for m in json.loads(tags_body).get("models") or []]
    except (ValueError, AttributeError, TypeError):
        return True  # 読めないときは止めない（実行時のエラーに任せる）
    return any(name == model or name.split(":")[0] == model for name in names)


class OllamaAgent:
    """ローカルの Ollama に修正後の全文を作らせるエージェント。"""

    name = "ollama"
    label = "Ollama（ローカルLLM）"

    def is_available(self) -> ConnectionCheck:
        host = _ollama_host()
        try:
            req = urllib.request.Request(f"{host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:  # nosec B310 - ローカルの固定エンドポイント
                status = getattr(resp, "status", 0)
                body = resp.read().decode("utf-8", "ignore")
        except Exception as exc:  # noqa: BLE001 - 疎通確認の失敗は理由付きで ok=False に畳む
            return ConnectionCheck(
                key="agent",
                label=self.label,
                ok=False,
                detail=f"{host} に接続できません（{type(exc).__name__}）",
            )
        if status != 200:
            return ConnectionCheck(
                key="agent",
                label=self.label,
                ok=False,
                detail=f"{host}/api/tags が HTTP {status} を返しました",
            )
        model = os.environ.get("WEBSPEC2DOC_HEALING_OLLAMA_MODEL", _OLLAMA_DEFAULT_MODEL)
        # 繋がっていてもモデルが無ければ実行時に必ず失敗する。
        # 「接続 OK」と出したあとで失敗させるより、ここで手順まで示す。
        if not _has_model(body, model):
            return ConnectionCheck(
                key="agent",
                label=self.label,
                ok=False,
                detail=f"モデル {model} がありません。ollama pull {model} を実行してください",
            )
        return ConnectionCheck(key="agent", label=self.label, ok=True, detail=f"{host} / モデル: {model}")

    def propose_fix(self, task: AgentTask) -> FixProposal:
        """例外は投げない。失敗時も必ず FixProposal を返す。"""
        return _run_diff_fix(self.name, task, self._call)

    def _call(self, prompt: str, timeout: float) -> tuple[str, str]:
        host = _ollama_host()
        model = os.environ.get("WEBSPEC2DOC_HEALING_OLLAMA_MODEL", _OLLAMA_DEFAULT_MODEL)
        data = _post_json(
            f"{host}/api/chat",
            {
                "model": model,
                "stream": False,
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            },
            {},
            timeout,
        )
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollamaの応答が空でした。")
        return content, f"host={host} model={model} done_reason={data.get('done_reason')}"


# ─────────────────────────── レジストリ ───────────────────────────

_AGENT_CLASSES: dict[str, type[HealingAgent]] = {
    "claude": ClaudeCodeAgent,
    "codex": CodexAgent,
    "openai": OpenAIAgent,
    "ollama": OllamaAgent,
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
