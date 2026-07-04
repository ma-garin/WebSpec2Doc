from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from web.config import ALLOWED_FORMATS, DOMAIN_RE, OUTPUT_DIR

_HTTP_URL_RE = re.compile(r"^https?://.{3,}", re.IGNORECASE)


def _clean_int(value: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _clean_formats(raw: str) -> list[str]:
    picked = [f.strip().lower() for f in raw.split(",") if f.strip()]
    return [f for f in picked if f in ALLOWED_FORMATS]


def _valid_domain(domain: str) -> bool:
    """ドメイン文字列の妥当性を検証する（パストラバーサル防止）。"""
    return bool(domain) and ".." not in domain and bool(DOMAIN_RE.match(domain))


def _safe_auth_path(raw: str) -> str:
    """auth.json はプロジェクト配下のファイルのみ許可（任意ファイル読み取りを防ぐ）。"""
    if not raw:
        return ""
    try:
        target = Path(raw).resolve()
    except (OSError, ValueError, RuntimeError):
        return ""
    base = Path.cwd().resolve()
    if (target == base or base in target.parents) and target.is_file():
        return str(target)
    return ""


def _safe_reference_doc_paths(raw: str, domain: str) -> list[str]:
    """カンマ区切りの参考文書パスを検証する。

    resolve 後に OUTPUT_DIR/{domain}/reference_docs/ 配下の実在ファイルのみ
    通す（_safe_auth_path と同じ resolve→parents 判定）。不正パスは黙って
    除外する（クロール自体は続行させる）。
    """
    if not raw or not _valid_domain(domain):
        return []
    base = (OUTPUT_DIR / domain / "reference_docs").resolve()
    result: list[str] = []
    for candidate in raw.split(","):
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            target = Path(candidate).resolve()
        except (OSError, ValueError, RuntimeError):
            continue
        if base in target.parents and target.is_file():
            result.append(str(target))
    return result


def _safe_output_path(raw: str) -> Path | None:
    """Resolve a path and ensure it stays inside OUTPUT_DIR (anti path-traversal)."""
    if not raw:
        return None
    try:
        target = Path(raw).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    base = OUTPUT_DIR.resolve()
    if target != base and base not in target.parents:
        return None
    return target if target.is_file() else None


def _valid_url(url: str) -> bool:
    """http/https スキームを持つ URL かを確認する（SSRF 対策の最低限チェック）。"""
    return bool(url) and bool(_HTTP_URL_RE.match(url.strip()))


def error_json(message: str, code: int = 400) -> tuple[dict[str, str], int]:
    """統一エラーレスポンスを生成する。"""
    return {"error": message}, code


def _sanitize(value: str) -> str:
    return value.strip().replace("\n", "").replace("\r", "")


def _domain_of(url: str) -> str:
    parsed = urlparse(url.strip())
    return parsed.netloc or "site"
