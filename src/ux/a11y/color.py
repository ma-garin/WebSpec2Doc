"""WCAG 2.x の相対輝度・コントラスト比（自前実装）と CSS 色のパース。"""
from __future__ import annotations

import re

RGBA = tuple[float, float, float, float]  # r,g,b は 0-255、a は 0-1

_FUNC = re.compile(r"^(rgba?|color)\((.*)\)$", re.I)
_HEX = re.compile(r"^#([0-9a-f]{3,8})$", re.I)
_NUM = r"[+-]?(?:\d+\.?\d*|\.\d+)"


def _num(tok: str, scale: float) -> float | None:
    tok = tok.strip()
    try:
        if tok.endswith("%"):
            return float(tok[:-1]) / 100.0 * scale
        return float(tok)
    except ValueError:
        return None


def parse_color(value: str | None) -> RGBA | None:
    """rgb()/rgba()/#hex/transparent/color(srgb ...) を RGBA に。解釈不能は None。"""
    if not value:
        return None
    v = value.strip().lower()
    if v == "transparent":
        return (0.0, 0.0, 0.0, 0.0)
    m = _HEX.match(v)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) not in (6, 8):
            return None
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        a = int(h[6:8], 16) / 255.0 if len(h) == 8 else 1.0
        return (float(r), float(g), float(b), a)
    m = _FUNC.match(v)
    if not m:
        return None
    kind, body = m.group(1), m.group(2).strip()
    if kind == "color":
        if not body.startswith("srgb"):
            return None
        body = body[4:].strip()
        scale_rgb, srgb = 1.0, True
    else:
        scale_rgb, srgb = 255.0, False
    alpha = 1.0
    if "/" in body:
        body, a_tok = body.split("/", 1)
        a = _num(a_tok, 1.0)
        if a is None:
            return None
        alpha = a
    parts = [p for p in re.split(r"[,\s]+", body.strip()) if p]
    if len(parts) == 4 and "/" not in value:
        a = _num(parts[3], 1.0)
        if a is None:
            return None
        alpha, parts = a, parts[:3]
    if len(parts) != 3:
        return None
    chans = []
    for p in parts:
        n = _num(p, scale_rgb)
        if n is None:
            return None
        chans.append(n * 255.0 if srgb else n)
    r, g, b = (min(255.0, max(0.0, c)) for c in chans)
    return (r, g, b, min(1.0, max(0.0, alpha)))


def _lin(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = (_lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: tuple[float, float, float], bg: tuple[float, float, float]) -> float:
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def blend(top: RGBA, bottom: tuple[float, float, float]) -> tuple[float, float, float]:
    """top（アルファ付き）を不透明な bottom の上に合成。"""
    a = top[3]
    return tuple(top[i] * a + bottom[i] * (1 - a) for i in range(3))  # type: ignore[return-value]
