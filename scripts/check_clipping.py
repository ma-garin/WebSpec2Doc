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

REVERSE_VIEWPORTS = ((816, 900), (1440, 900))

_JS = r"""(rootSel) => {
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
  for (const el of document.querySelectorAll((rootSel ? rootSel + ' ' : '') + 'a,button,input,select,textarea,label,h1,h2,h3,p,li,td,th,[class*=card]')) {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    if (r.width < 3 || r.height < 3 || s.visibility === 'hidden' || el.closest('[hidden],[aria-hidden=true],dialog:not([open])')) continue;
    const why = clipped(el);
    if (why) out.push(`${el.tagName.toLowerCase()}「${(el.innerText || el.value || '').trim().slice(0, 24)}」: ${why}`);
  }
  return out;
}"""


_JS_EXTRA = r"""() => {
  const out = [], vw = innerWidth, vh = innerHeight, d = document.scrollingElement;
  if (d.scrollWidth > d.clientWidth) out.push(`ページが横にスクロールする（${d.scrollWidth} > ${d.clientWidth}）`);
  const rv = document.querySelector('#spec-reverse');
  if (rv) {
    const r = rv.getBoundingClientRect();
    if (rv.scrollWidth > rv.clientWidth + 1) out.push(`#spec-reverse が横にはみ出す（${rv.scrollWidth} > ${rv.clientWidth}）`);
    if (r.right > vw + 1) out.push(`#spec-reverse の右 ${Math.round(r.right - vw)}px が画面外`);
  }
  return out;
}"""

_JS_DRAWER = r"""() => {
  const el = document.querySelector('.rv-drawer');
  if (!el) return ['ドロワーが見つからない'];
  const r = el.getBoundingClientRect(), vw = innerWidth, vh = innerHeight, out = [];
  if (r.left < -1 || r.top < -1 || r.right > vw + 1 || r.bottom > vh + 1)
    out.push(`ドロワーが画面に収まらない（left=${Math.round(r.left)} top=${Math.round(r.top)} right=${Math.round(r.right)}/${vw} bottom=${Math.round(r.bottom)}/${vh}）`);
  return out;
}"""


def _report(w: int, h: int, name: str, found: list[str]) -> int:
    for f in found[:5]:
        print(f"NG {w}x{h} {name}: {f}")
    if len(found) > 5:
        print(f"NG {w}x{h} {name}: ほか {len(found) - 5} 件")
    return len(found)


def _check_reverse(page, base: str, domain: str, w: int, h: int) -> tuple[int, int]:
    """リバース解析画面（一覧・ドロワー・各タブ）を検査する。(NG 件数, 検査した画面数) を返す。"""
    name = f"/sites/{domain}/spec#reverse"
    try:
        page.goto(f"{base}/sites/{domain}/spec", wait_until="load", timeout=15000)
        page.click('#spec-seg button[data-m="reverse"]', timeout=10000)
        page.wait_for_selector("#spec-reverse .rv", state="visible", timeout=10000)
    except Exception as exc:
        print(f"NG {w}x{h} {name}: 開けない（{type(exc).__name__}）")
        return 1, 1
    total, screens = 0, 0

    def run(label: str, root: str) -> None:
        nonlocal total, screens
        screens += 1
        page.wait_for_timeout(300)
        total += _report(w, h, label, page.evaluate(_JS, root) + page.evaluate(_JS_EXTRA))

    run(name, "#spec-reverse")
    try:
        page.click("#spec-reverse .rv-panel tbody tr", timeout=5000)
        page.wait_for_selector(".rv-drawer", state="visible", timeout=5000)
        screens += 1
        page.wait_for_timeout(300)
        total += _report(w, h, name + ":drawer", page.evaluate(_JS, ".rv-drawer") + page.evaluate(_JS_DRAWER))
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
    except Exception as exc:
        print(f"NG {w}x{h} {name}:drawer: 開けない（{type(exc).__name__}）")
        total, screens = total + 1, screens + 1
    tabs = page.eval_on_selector_all(".rv-tab[data-tab]", "els => els.map(e => e.dataset.tab)")
    for tab in tabs:
        try:
            page.click(f'.rv-tab[data-tab="{tab}"]', timeout=5000)
        except Exception as exc:
            print(f"NG {w}x{h} {name}:{tab}: 開けない（{type(exc).__name__}）")
            total, screens = total + 1, screens + 1
            continue
        run(f"{name}:{tab}", "#spec-reverse")
    return total, screens


def _routes() -> list[str]:
    os.environ.setdefault("FLASK_TESTING", "1")
    os.environ.setdefault("WEBSPEC2DOC_AUTH_MODE", "off")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from web import create_app
    rules = create_app().url_map.iter_rules()
    return sorted({r.rule for r in rules if "GET" in r.methods and "<" not in r.rule and not r.rule.startswith(_SKIP)})


def main() -> int:
    base = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8766"
    args = sys.argv[2:]
    review = None
    if "--docverify-review" in args:  # System 06 のレビュー内の画面（開いたレビューが要る）も見る
        i = args.index("--docverify-review")
        review = args[i + 1]
        args = args[:i] + args[i + 2:]
    reverse = []
    while "--reverse-analysis" in args:  # リバース解析画面（一覧・ドロワー・各タブ）を 816/1440 幅で見る
        i = args.index("--reverse-analysis")
        reverse.append(args[i + 1])
        args = args[:i] + args[i + 2:]
    pages = args or _routes()
    if review:
        pages = pages + [f"/docverify#{v}" for v in ("plan", "read", "triage", "questions", "followup", "screen", "gate")]
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
                    if review and "#" in path:
                        page.goto(base + "/docverify", wait_until="load", timeout=15000)
                        page.evaluate(f"sessionStorage.setItem('dv-review', '{review}')")
                    resp = page.goto(base + path, wait_until="load", timeout=15000)
                    if review and "#" in path:
                        page.reload(wait_until="load"); page.wait_for_timeout(800)
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
    if reverse:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception:
                browser = p.chromium.launch(channel="chrome")
            for w, h in REVERSE_VIEWPORTS:
                page = browser.new_page(viewport={"width": w, "height": h})
                for domain in reverse:
                    n, screens = _check_reverse(page, base, domain, w, h)
                    total += n
                    print(f"リバース解析 {w}x{h} {domain}: {screens} 画面 / NG {n} 件")
                page.close()
            browser.close()
    print(f"見切れ {total} 件（{len(pages)} 画面 × {len(VIEWPORTS)} 幅）")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
