"""LLM 呼び出しのアクティビティログ。

生成 AI を使う経路では必ず記録を残す（採用時だけでなく、呼び出しそのものを
成功・退避・失敗を問わず記録する）。プロンプト本文は保存せず、目的・接続先・
モデル・結果・所要時間・プロンプト長のみを JSONL に追記する。
記録の失敗は LLM 呼び出し自体を妨げない（best-effort）。
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

ACTIVITY_LOG_FILE_NAME = "llm_activity.jsonl"
#: 既定の書き込み先ディレクトリを上書きする環境変数
ACTIVITY_LOG_DIR_ENV = "WEBSPEC2DOC_LLM_ACTIVITY_DIR"
_DEFAULT_LOG_DIR = "output"
_DETAIL_MAX_CHARS = 500

_context: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "llm_activity_context", default=None
)


@contextlib.contextmanager
def llm_activity_context(
    *,
    purpose: str = "",
    domain: str = "",
    stage_id: str = "",
    output_dir: Path | str | None = None,
) -> Iterator[None]:
    """このブロック内の LLM 呼び出し記録に付与する文脈（目的・対象・出力先）。"""
    values = {
        "purpose": purpose,
        "domain": domain,
        "stage_id": stage_id,
        "output_dir": str(output_dir) if output_dir else "",
    }
    token = _context.set(values)
    try:
        yield
    finally:
        _context.reset(token)


def _log_path() -> Path:
    ctx = _context.get() or {}
    base = (
        ctx.get("output_dir")
        or os.environ.get(ACTIVITY_LOG_DIR_ENV, "").strip()
        or _DEFAULT_LOG_DIR
    )
    return Path(base) / ACTIVITY_LOG_FILE_NAME


def record_llm_activity(
    *,
    purpose: str = "",
    endpoint_url: str = "",
    model: str = "",
    outcome: str = "",
    detail: str = "",
    prompt_chars: int = 0,
    duration_ms: int | None = None,
) -> Path | None:
    """LLM 呼び出し 1 件を JSONL に追記する。失敗しても例外は送出しない。

    outcome: "ok" / "unavailable" / "invalid_response" / "http_error" /
    "not_configured" など。detail にはモード（json_schema / json_object_fallback）
    やエラー要約を入れる。プロンプト本文・API キーは記録しない（秘匿保護）。
    """
    ctx = _context.get() or {}
    entry: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "purpose": purpose or ctx.get("purpose") or "unknown",
        "domain": ctx.get("domain") or "",
        "stage_id": ctx.get("stage_id") or "",
        "endpoint": endpoint_url,
        "model": model,
        "outcome": outcome,
        "detail": detail[:_DETAIL_MAX_CHARS],
        "prompt_chars": prompt_chars,
        "duration_ms": duration_ms,
    }
    path = _log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("LLM アクティビティログの書き込みに失敗しました: %s (%s)", path, exc)
        return None
    return path
