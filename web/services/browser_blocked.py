"""ブラウザ不在（BrowserUnavailable）を子プロセスの出力から判定し、BLOCKED として返す。

クロール系の子プロセスは Chrome / Edge が無いと BrowserUnavailable で異常終了する。
受け側はそれを成功にも汎用の失敗にもせず、BLOCKED と次の行動を利用者へ返す。
"""

from __future__ import annotations

BLOCKED_STATUS = "BLOCKED"
BLOCKED_REASON = "browser unavailable"
BLOCKED_MESSAGE = (
    "BLOCKED: ブラウザが見つからないため実行できません（browser unavailable）。"
    "Google Chrome か Microsoft Edge を導入してください。"
)

_MARKERS = ("BrowserUnavailable", "browser unavailable", "BLOCKED: browser")


class BrowserBlocked(RuntimeError):
    """子プロセスがブラウザ不在で終了した。"""


def is_browser_unavailable(*texts: str | None) -> bool:
    """子プロセスの出力（stdout / stderr / ログ）にブラウザ不在の印があるか。"""
    joined = "\n".join(t for t in texts if t)
    return any(marker in joined for marker in _MARKERS)


def blocked_payload(**extra: object) -> dict:
    """API 応答用。ok / success は False（成功扱いにしない）。"""
    return {
        "ok": False,
        "success": False,
        "status": BLOCKED_STATUS,
        "reason": BLOCKED_REASON,
        "error": BLOCKED_MESSAGE,
        **extra,
    }
