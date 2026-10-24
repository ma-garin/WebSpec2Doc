#!/usr/bin/env python3
"""見切れ検査（INC-2026-003 の是正）。全画面を実際のブラウザで開き、見えない・スクロールでも届かない要素を数える。

「見切れ」の定義: 要素がはみ出した先を、切り取っている祖先（overflow が visible 以外）か画面（viewport）が
スクロールで見せられない状態。overflow:auto/scroll で実際にスクロールできる祖先の中なら見切れではない。

使い方（認証オフの検証用サーバに対して。H-2 の 8766）:
    venv/bin/python scripts/check_clipping.py http://127.0.0.1:8766 [/systems /docverify ...]
画面を省略すると、引数なしで開ける全 GET 画面を対象にする。見切れが 1 件でもあれば終了コード 1。
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys

from playwright.sync_api import sync_playwright

VIEWPORTS = ((1440, 900), (1280, 720))
_SKIP = ("/api", "/static", "/auth/oidc", "/download", "/metrics", "/open", "/preview", "/review/export")

GATE_VIEWPORTS = ((1440, 900), (1280, 800), (1280, 720))
GATE_PAGES = ("/dashboard", "/generate", "/docverify")  # 01・06 の対象
ALL_GATES = ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8")

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
  const el = document.querySelector('.c-drawer');
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
        page.wait_for_selector("#spec-reverse [role=tablist]", state="visible", timeout=10000)
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
        page.click("#spec-reverse table tbody tr", timeout=5000)
        page.wait_for_selector(".c-drawer", state="visible", timeout=5000)
        screens += 1
        page.wait_for_timeout(300)
        total += _report(w, h, name + ":drawer", page.evaluate(_JS, ".c-drawer") + page.evaluate(_JS_DRAWER))
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
    except Exception as exc:
        print(f"NG {w}x{h} {name}:drawer: 開けない（{type(exc).__name__}）")
        total, screens = total + 1, screens + 1
    tabs = page.eval_on_selector_all("#spec-reverse [role=tab][data-tab]", "els => els.map(e => e.dataset.tab)")
    for tab in tabs:
        try:
            page.click(f'#spec-reverse [role=tab][data-tab="{tab}"]', timeout=5000)
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


def _pop_opt(args: list[str], name: str) -> str | None:
    if name not in args:
        return None
    i = args.index(name)
    val = args[i + 1] if i + 1 < len(args) else ""
    del args[i:i + 2]
    return val


def _gate_run(browser, base: str, pages: list[str], gates: set[str], states: bool, snap_dir: str | None) -> dict:
    """G-1〜G-7 を画面 x 幅で走らせる。G-8 は既存の見切れ検査。戻り値は集計 dict。"""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts.ui_gates import g1_g2, g3, g4, g5, g6_g7
    counts = {f"G-{n}": 0 for n in range(1, 9)}
    snaps = 0
    fixtures = g4.load_fixtures() if "G4" in gates and states else None
    for w, h in GATE_VIEWPORTS:
        ctx = browser.new_context(viewport={"width": w, "height": h})
        page = ctx.new_page()
        for path in pages:
            try:
                resp = page.goto(base + path, wait_until="load", timeout=15000)
                page.wait_for_timeout(500)
            except Exception as exc:
                print(f"NG {w}x{h} {path} G-8: 開けない（{type(exc).__name__}）")
                counts["G-8"] += 1
                continue
            if resp is None or resp.status >= 400 or "html" not in (resp.headers.get("content-type") or ""):
                continue
            found: list[tuple[str, str]] = []
            if "G1" in gates:
                found += [("G-1", m) for m in g1_g2.run_g1(page)]
            if "G2" in gates:
                found += [("G-2", m) for m in g1_g2.run_g2(page)]
            if "G3" in gates:
                found += [("G-3", m) for m in g3.run_g3(page, path)]
            if "G5" in gates:
                found += [("G-5", m) for m in g5.check(page)]
            if "G6" in gates:
                found += [("G-6", m) for m in g6_g7.check_dynamic(page)]
            if "G7" in gates:
                found += [("G-7", m) for m in g6_g7.check_auto(page)]
            if "G8" in gates:
                found += [("G-8", m) for m in page.evaluate(_JS)]
            if snap_dir and "G7" in gates:
                snaps += g6_g7.snapshot(page, snap_dir, f"{path}_{w}x{h}")
            if "G4" in gates and states and (w, h) == GATE_VIEWPORTS[0]:
                found += [("G-4", m) for m in g4.check(ctx, base, path, fixtures)]
            for g, m in found[:60]:
                print(f"NG {w}x{h} {path} {m if m.startswith('G-') else g + ': ' + m}")
            for g, _ in found:
                counts[g] += 1
        ctx.close()
    return {"counts": counts, "snaps": snaps}


def _main_gates(base, pages, gates_arg, states, snap_dir, json_out) -> int:
    gates = {g.strip().upper() for g in gates_arg.split(",") if g.strip()} or set(ALL_GATES)
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            browser = p.chromium.launch(channel="chrome")
        res = _gate_run(browser, base, pages, gates, states, snap_dir)
        browser.close()
    c, total = res["counts"], sum(res["counts"].values())
    if snap_dir:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from scripts.ui_gates import g6_g7
        print(g6_g7.visual_count_line(res["snaps"]))
    print(" / ".join(f"G-{n} {c[f'G-{n}']}件" for n in range(1, 9)) + f" / 合計 {total}件（{len(pages)} 画面 × {len(GATE_VIEWPORTS)} 幅）")
    if json_out:
        try:
            rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        except Exception:
            rev = ""
        data = {k: {"count": v, "screens": len(pages)} for k, v in c.items()}
        data.update({"date": datetime.date.today().isoformat(), "git": rev, "base": base,
                     "pages": pages, "widths": [f"{w}x{h}" for w, h in GATE_VIEWPORTS], "total": total})
        os.makedirs(os.path.dirname(os.path.abspath(json_out)), exist_ok=True)
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return 1 if total else 0


def main() -> int:
    base = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8766"
    args = sys.argv[2:]
    gates_arg = _pop_opt(args, "--gates")
    json_out = _pop_opt(args, "--json")
    snap_dir = _pop_opt(args, "--snap-dir")
    states = "--states" in args
    if states:
        args.remove("--states")
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
    if gates_arg is not None:
        return _main_gates(base, args or list(GATE_PAGES), gates_arg, states, snap_dir, json_out)
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
