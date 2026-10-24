"""状態部品（partials/state.html）の呼び出し規則。CTA は loading 以外で必須。"""

from __future__ import annotations

KINDS = ("empty", "zero", "loading", "error", "forbidden")


def require_cta(kind: str, cta_label: str | None) -> str:
    """kind が loading 以外で cta_label が空なら ValueError。通れば空文字を返す（テンプレート内で出力されない）。"""
    if kind not in KINDS:
        raise ValueError(f"unknown state kind: {kind!r}")
    if kind != "loading" and not (cta_label or "").strip():
        raise ValueError(f"state '{kind}' requires cta_label (CTA は 1 個必須)")
    return ""
