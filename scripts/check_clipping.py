#!/usr/bin/env python3
"""見切れ検査（INC-2026-003 の是正）。全画面を実際のブラウザで開き、見えない・スクロールでも届かない要素を数える。

「見切れ」の定義: 要素がはみ出した先を、切り取っている祖先（overflow が visible 以外）か画面（viewport）が
スクロールで見せられない状態。overflow:auto/scroll で実際にスクロールできる祖先の中なら見切れではない。

使い方（認証オフの検証用サーバに対して。H-2 の 8766）:
    venv/bin/python scripts/check_clipping.py http://127.0.0.1:8766 [/systems /docverify ...]
画面を省略すると、引数なしで開ける全 GET 画面を対象にする。見切れが 1 件でもあれば終了コード 1。
"""
from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

VIEWPORTS = ((1440, 900), (1280, 720))
_SKIP = ("/api", "/static", "/auth/oidc", "/download", "/metrics", "/open", "/preview", "/review/export")

_JS = r"""() => {
  const vw = innerWidth, vh = innerHeight, out = [];
  const canScroll = (a, axis) => {
    const s = getComputedStyle(a), ov = axis === 'y' ? s.overflowY : s.overflowX;
    const big = axis === 'y' ? a.scrollHeight > a.clientHeight + 1 : a.scrollWidth > a.clientWidth + 1;
    return /(auto|scroll)/.test(ov) && big;
  };
  const docScroll = axis => {
    const d = document.scrollingElement, h = getComputedStyle(document.documentElement), b = getComputedStyle(document.body);
    const ov = axis === 'y' ? [h.overflowY, b.overflowY] : [h.overflowX, b.overflowX];
    const big = axis === 'y' ? d.scrollHeight > d.clientHeight + 1 : d.scrollWidth > d.clientWidth + 1;
    return big && !ov.includes('hidden') && !ov.includes('clip');
  };
  const clipped = el => {
    const r = el.getBoundingClientRect();
    for (let a = el.parentElement; a && a !== document.body && a !== document.documentElement; a = a.parentElement) {
      const s = getComputedStyle(a);
      if (s.position === 'fixed') break;
      const ar = a.getBoundingClientRect();
      for (const axis of ['y', 'x']) {
        const ov = axis === 'y' ? s.overflowY : s.overflowX;
        if (ov === 'visible') continue;
        const out_ = axis === 'y' ? r.bottom > ar.bottom + 1 : r.right > ar.right + 1;
        if (out_ && !canScroll(a, axis)) return `祖先 ${a.tagName.toLowerCase()}.${[...a.classList].join('.')} が切っている`;
        if (out_) return '';
      }
    }
    if (r.bottom > vh + 1 && !docScroll('y')) return `画面の下 ${Math.round(r.bottom - vh)}px が見えずスクロールもできない`;
    if (r.right > vw + 1 && !docScroll('x')) return `画面の右 ${Math.round(r.right - vw)}px が見えない`;
    return '';
  };
  for (const el of document.querySelectorAll('a,button,input,select,textarea,label,h1,h2,h3,p,li,td,th,[class*=card]')) {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    if (r.width < 3 || r.height < 3 || s.visibility === 'hidden' || el.closest('[hidden],[aria-hidden=true],dialog:not([open])')) continue;
    const why = clipped(el);
    if (why) out.push(`${el.tagName.toLowerCase()}「${(el.innerText || el.value || '').trim().slice(0, 24)}」: ${why}`);
  }
  return out;
}"""


def _routes() -> list[str]:
    os.environ.setdefault("FLASK_TESTING", "1")
    os.environ.setdefault("WEBSPEC2DOC_AUTH_MODE", "off")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from web import create_app
    rules = create_app().url_map.iter_rules()
    return sorted({r.rule for r in rules if "GET" in r.methods and "<" not in r.rule and not r.rule.startswith(_SKIP)})


def main() -> int:
    base = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8766"
    pages = sys.argv[2:] or _routes()
    total = 0
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:  # Playwright 同梱のブラウザが無い環境は手元の Chrome を使う
            browser = p.chromium.launch(channel="chrome")
        for w, h in VIEWPORTS:
            page = browser.new_page(viewport={"width": w, "height": h})
            for path in pages:
                try:
                    resp = page.goto(base + path, wait_until="networkidle", timeout=15000)
                except Exception as exc:  # 開けない画面は見切れ以前の問題として数える
                    print(f"NG {w}x{h} {path}: 開けない（{type(exc).__name__}）")
                    total += 1
                    continue
                if resp is None or resp.status >= 400 or "html" not in (resp.headers.get("content-type") or ""):
                    continue
                found = page.evaluate(_JS)
                for f in found[:5]:
                    print(f"NG {w}x{h} {path}: {f}")
                if len(found) > 5:
                    print(f"NG {w}x{h} {path}: ほか {len(found) - 5} 件")
                total += len(found)
            page.close()
        browser.close()
    print(f"見切れ {total} 件（{len(pages)} 画面 × {len(VIEWPORTS)} 幅）")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
