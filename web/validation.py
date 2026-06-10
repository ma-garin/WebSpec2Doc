from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from web.config import ALLOWED_FORMATS, DOMAIN_RE, OUTPUT_DIR


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


def _sanitize(value: str) -> str:
    return value.strip().replace("\n", "").replace("\r", "")


def _domain_of(url: str) -> str:
    parsed = urlparse(url.strip())
    return parsed.netloc or "site"
