"""G-5 タイポと色（仕様 §7.6）。文字サイズ種類 5 以下・最小 12px 以上、WCAG コントラスト。"""
from __future__ import annotations

MAX_SIZES = 5
MIN_SIZE_PX = 12

JS_G5 = r"""() => {
  const vis = e => e.offsetParent !== null || getComputedStyle(e).position === 'fixed';
  const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return {r:p[0], g:p[1], b:p[2], a:p.length > 3 ? p[3] : 1}; };
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const bgOf = el => { for (let a = el; a; a = a.parentElement) { const c = parse(getComputedStyle(a).backgroundColor);
      if (c && c.a >= 0.99) return c; } return {r:255, g:255, b:255, a:1}; };
  const sel = el => { let s = el.tagName.toLowerCase(); if (el.id) return s + '#' + el.id;
    if (el.classList.length) s += '.' + [...el.classList].slice(0, 2).join('.'); return s; };
  const sizes = new Map(), contrast = [], seen = new Set();
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    if (!n.nodeValue.trim()) continue;
    const el = n.parentElement;
    if (!el || seen.has(el) || /^(SCRIPT|STYLE|NOSCRIPT)$/.test(el.tagName) || !vis(el) || el.closest('[hidden]')) continue;
    seen.add(el);
    const s = getComputedStyle(el), fs = parseFloat(s.fontSize);
    sizes.set(fs, (sizes.get(fs) || 0) + 1);
    if (el.disabled || el.closest(':disabled') || el.closest('[aria-disabled="true"]')) continue;
    const fg = parse(s.color), bg = bgOf(el); if (!fg) continue;
    const a = fg.a, mix = {r: fg.r * a + bg.r * (1 - a), g: fg.g * a + bg.g * (1 - a), b: fg.b * a + bg.b * (1 - a)};
    const l1 = lum(mix), l2 = lum(bg), ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    const bold = parseInt(s.fontWeight, 10) >= 700;
    const need = (fs >= 24 || (fs >= 18.66 && bold)) ? 3 : 4.5;
    if (ratio < need) contrast.push({sel: sel(el), color: s.color, ratio: Math.round(ratio * 100) / 100, need});
  }
  return {sizes: [...sizes.keys()].sort((a, b) => a - b), contrast};
}"""


def check(page) -> list[str]:
    r = page.evaluate(JS_G5)
    out: list[str] = []
    sizes = r["sizes"]
    if len(sizes) > MAX_SIZES:
        out.append(f"G-5: 文字サイズが {len(sizes)} 種類（{MAX_SIZES} 以下）: " + ",".join(f"{s:g}px" for s in sizes))
    if sizes and sizes[0] < MIN_SIZE_PX:
        out.append(f"G-5: 最小文字サイズ {sizes[0]:g}px（{MIN_SIZE_PX}px 以上）")
    for c in r["contrast"]:
        out.append(f"G-5: コントラスト {c['ratio']}:1（{c['need']}:1 必要） {c['sel']} color={c['color']}")
    return out
