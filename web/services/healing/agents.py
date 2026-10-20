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
- 検証は呼び出し側が `{task.verify_command}` で行う（あなたはコマンドを実行できない）。

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
    """workdir の変更（差分とファイル一覧）を git_ops 経由で回収する。

    差分は画面・レポート用の表示にだけ使い、再適用しない。
    """
    try:
        diff = git_ops.worktree_diff(Path(workdir))
        files = tuple(f for f in git_ops.changed_files(Path(workdir)) if f.strip())
    except Exception:  # noqa: BLE001 - 回収失敗は「変更なし」扱いにせず空で返し、呼び出し側が skipped にする
        return "", ()
    return diff, files


# ─────────────────────────── エージェント実装 ───────────────────────────


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
    "変更は指定された JSON（edits）だけで返し、説明文やファイル全文を出してはいけません。"
)

# 変更は「このテキストをこのテキストに置き換える」編集の列で返させる。
# unified diff は行番号のずれで当たらず、ファイル全文は長い出力の途中で壊れる。
# 完全一致の置換なら、当たる／当たらないが明確で、当たらない理由も言える。
_EDITS_FORMAT_INSTRUCTIONS = """

# 出力形式（厳守）
変更は次の JSON オブジェクトだけを返してください。
{
  "summary": "対応の要約（日本語 1 文）",
  "rationale": "原因: ...（日本語 1〜2 文）\\n対応: ...（日本語 1〜2 文）",
  "edits": [
    {"path": "リポジトリルートからの相対パス", "old": "置換前のテキスト", "new": "置換後のテキスト"}
  ]
}
- old は対象ファイル内で 1 箇所だけに一致する長さにする（前後の行を含めて一意にする）。空白・改行・インデントも含めて完全に一致させる。
- 新しいファイルを作るときは old を空文字にする（既存ファイルには使えない）。
- path に絶対パスや `..` を含めない。
- 変更が必要ない場合は edits を空配列にする。
- JSON 以外（前置き・コードフェンス・説明文）を出力しない。
"""

#: 応答から JSON を取り出すためのフェンス。
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)


class EditError(Exception):
    """edits を適用できなかった理由（モデルに返して出し直させる文言）。"""


def _parse_edits(text: str) -> dict[str, Any]:
    """モデルの応答から {summary, rationale, edits} を取り出す。壊れていれば EditError。"""
    raw = (text or "").strip()
    candidates = [raw]
    candidates += [m.group(1).strip() for m in _JSON_FENCE_RE.finditer(raw)]
    start, end = raw.find("{"), raw.rfind("}")
    if 0 <= start < end:
        candidates.append(raw[start : end + 1])
    for cand in candidates:
        try:
            data = json.loads(cand)
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("edits"), list):
            return data
    raise EditError("応答が {\"edits\": [...]} 形式の JSON として読めませんでした")


def _resolve_inside(root: Path, rel: str) -> Path:
    """rel を root 配下の絶対パスにする。外へ出るパスは EditError（パストラバーサル防止）。"""
    if not isinstance(rel, str) or not rel.strip():
        raise EditError("path が空です")
    if "\x00" in rel:
        raise EditError(f"path が不正です: {rel!r}")
    candidate = Path(rel)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise EditError(f"path はリポジトリ内の相対パスだけ指定できます: {rel}")
    root_resolved = root.resolve()
    target = (root_resolved / candidate).resolve()  # シンボリックリンクも解決して判定する
    if root_resolved != target and root_resolved not in target.parents:
        raise EditError(f"path がリポジトリの外を指しています: {rel}")
    if ".git" in target.relative_to(root_resolved).parts:
        raise EditError(f".git 配下は変更できません: {rel}")
    return target


def apply_edits(workdir: Path, edits: list[Any]) -> list[str]:
    """edits を完全一致置換で適用し、変更したファイルの相対パスを返す。

    全 edits をメモリ上で適用して検証し、すべて成功したときだけ書き込む
    （1 件でも不一致なら木は一切変わらない）。同じファイルへの複数 edit は
    記載順に、直前の結果へ適用する。失敗は EditError（行き先と理由つき）。
    """
    pending: dict[Path, str] = {}
    created: set[Path] = set()
    for index, edit in enumerate(edits, start=1):
        label = f"edit {index}"
        if not isinstance(edit, dict):
            raise EditError(f"{label}: オブジェクトではありません")
        rel = edit.get("path")
        old, new = edit.get("old"), edit.get("new")
        if not isinstance(old, str) or not isinstance(new, str):
            raise EditError(f"{label}: old と new は文字列で指定してください（{rel}）")
        target = _resolve_inside(workdir, str(rel))
        if target in pending:
            content = pending[target]
        elif target.is_file():
            try:
                with open(target, encoding="utf-8", newline="") as fh:
                    content = fh.read()
            except (OSError, UnicodeDecodeError) as exc:
                raise EditError(f"{label}: {rel} を読めません（{type(exc).__name__}）") from exc
        else:
            content = None
        if old == "":
            if content is not None:
                raise EditError(f"{label}: {rel} は既に存在します。old に置換前のテキストを指定してください")
            pending[target] = new
            created.add(target)
            continue
        if content is None:
            raise EditError(f"{label}: {rel} が存在しません")
        count = content.count(old)
        if count == 0:
            raise EditError(f"{label}: {rel} に old と一致する箇所がありません（空白・インデントを含め完全一致が必要です）")
        if count > 1:
            raise EditError(f"{label}: {rel} で old が {count} 箇所に一致します。前後の行を含めて 1 箇所に絞ってください")
        pending[target] = content.replace(old, new, 1)

    for target, content in pending.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
    root = workdir.resolve()
    return sorted(str(t.relative_to(root)) for t in pending)


def _llm_prompt(task: AgentTask) -> str:
    """既存の指示文に edits 出力の縛りを足す。"""
    return build_prompt(task) + _EDITS_FORMAT_INSTRUCTIONS


def _redact(text: str) -> str:
    """APIキーが混入していても外へ出さない。"""
    for name in ("OPENAI_API_KEY", "GITHUB_TOKEN"):
        key = os.environ.get(name, "").strip()
        if key and len(key) >= 8:
            text = text.replace(key, "***")
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
) -> tuple[dict[str, Any], str, str]:
    """モデルに edits を作らせて適用する。返すのは (解析結果, ログ, 失敗理由)。

    当たらなかったときは、不一致の理由をそのまま添えて 1 度だけ聞き直す。
    人が同じことをするからで、モデルは一意性の不足などをこれで直せることが多い。
    2 度目も失敗すれば諦める（3 度目が当たる見込みは薄く、時間だけ延びる）。
    """
    workdir = Path(task.workdir)
    prompt = _llm_prompt(task)
    content, log = call(prompt, float(task.timeout_sec))
    try:
        parsed = _parse_edits(content)
        if not parsed["edits"]:
            return parsed, log, ""
        apply_edits(workdir, parsed["edits"])
        return parsed, log, ""
    except EditError as exc:
        detail = str(exc)

    retry_prompt = (
        prompt
        + "\n\n# 直前の edits は適用できませんでした\n"
        + "理由:\n"
        + detail
        + "\n同じ内容を、1 箇所に完全一致する old を使った edits で出し直してください。"
    )
    content2, log2 = call(retry_prompt, float(task.timeout_sec))
    both_log = f"{log} / 再試行: {log2}"
    try:
        parsed2 = _parse_edits(content2)
        if parsed2["edits"]:
            apply_edits(workdir, parsed2["edits"])
        return parsed2, both_log, ""
    except EditError as exc2:
        return {}, both_log, f"修正を適用できませんでした（{exc2}）"


def _summary_from(parsed: dict[str, Any]) -> tuple[str, str]:
    """応答 JSON の summary / rationale を取り出す（人が読む「対応」の材料）。"""
    summary = parsed.get("summary") if isinstance(parsed, dict) else ""
    rationale = parsed.get("rationale") if isinstance(parsed, dict) else ""
    summary = summary.strip()[:200] if isinstance(summary, str) else ""
    rationale = rationale.strip()[:1000] if isinstance(rationale, str) else ""
    return summary, rationale


def _run_diff_fix(
    agent_name: str, task: AgentTask, call: Callable[[str, float], tuple[str, str]]
) -> FixProposal:
    """LLM に edits を作らせて適用し、差分を回収する。例外は投げない。"""
    start = time.monotonic()
    try:
        parsed, log, failure = _apply_with_retry(agent_name, task, call)
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
    summary, rationale = _summary_from(parsed)
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
    """OpenAI Chat Completions API に修正の edits を作らせるエージェント。"""

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
    """ローカルの Ollama に修正の edits を作らせるエージェント。"""

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
    "openai": OpenAIAgent,
    "ollama": OllamaAgent,
    "dryrun": DryRunAgent,
}


def available_agents() -> list[str]:
    """レジストリに登録済みのエージェント名一覧。"""
    return list(_AGENT_CLASSES.keys())


#: 撤去済みの旧エージェント名。保存済みデータに残っていても openai として動かす。
_LEGACY_AGENT_NAMES = frozenset({"claude", "codex"})


def get_agent(name: str) -> HealingAgent:
    """名前からエージェントのインスタンスを得る。未知の名前は HealingError。"""
    if name in _LEGACY_AGENT_NAMES:
        name = "openai"
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
