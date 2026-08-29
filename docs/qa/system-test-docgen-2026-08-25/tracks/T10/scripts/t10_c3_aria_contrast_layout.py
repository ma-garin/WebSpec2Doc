# T10-C015〜C021: ラベル/ARIA(1.1.1/1.3.1/4.1.2)・コントラスト(1.4.3)・1280px幅・Landmark遷移
# 実行: venv/bin/python tracks/T10/scripts/t10_c3_aria_contrast_layout.py
import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright  # noqa: E402
from t10_common import (launch, open_generate, save_json, shot,  # noqa: E402
                        discover, EV, MOCK)

R = {"case_group": "C3 aria/contrast/layout", "obs": {}, "errors": []}

NAME_AUDIT_JS = """() => {
  const scope = document.querySelector('#view-generate');
  const els = [...scope.querySelectorAll('button, input, select, textarea, a[href], [tabindex]')]
    .filter(e => e.offsetParent);
  return els.map(e => {
    let label = '';
    if (e.labels && e.labels.length) label = e.labels[0].textContent.trim();
    const aria = e.getAttribute('aria-label') || '';
    const albl = e.getAttribute('aria-labelledby');
    const ref = albl ? ((document.getElementById(albl) || {}).textContent || '').trim() : '';
    const txt = (e.tagName === 'INPUT' || e.tagName === 'SELECT') ? '' : (e.textContent || '').trim();
    const name = aria || ref || label || txt || e.title || '';
    return { id: e.id || null, tag: e.tagName, type: e.type || null,
      name: name.slice(0, 60),
      placeholderOnly: !name && !!e.placeholder,
      noName: !name && !e.placeholder };
  });
}"""

ARIA_ATTRS_JS = """() => ({
  discover_phase_live: document.getElementById('discover-phase')?.getAttribute('aria-live') ?? null,
  count_label_live: document.getElementById('discover-count-label')?.getAttribute('aria-live') ?? null,
  scope_est_role: document.getElementById('discover-scope-est')?.getAttribute('role') ?? null,
  discover_status_role: document.getElementById('discover-status')?.getAttribute('role') ?? null,
  discover_status_live: document.getElementById('discover-status')?.getAttribute('aria-live') ?? null,
  url_msg_role: document.getElementById('url-input-message')?.getAttribute('role') ?? null,
  url_msg_live: document.getElementById('url-input-message')?.getAttribute('aria-live') ?? null,
  url_input_describedby: document.getElementById('url-input')?.getAttribute('aria-describedby') ?? null,
  url_input_required: document.getElementById('url-input')?.hasAttribute('required') || null,
  progressbar_role: document.getElementById('exec-progress-bar')?.getAttribute('role') ?? null,
  exec_log_live: document.getElementById('exec-log')?.getAttribute('aria-live') ?? null,
  exec_message_live: document.getElementById('exec-message')?.getAttribute('aria-live') ?? null,
  exec_elapsed_live: document.getElementById('exec-elapsed')?.getAttribute('aria-live') ?? null,
  ws_attrs: [1, 2, 3, 4].map(n => { const el = document.getElementById('ws-' + n);
    return { id: 'ws-' + n, cls: el ? el.className : null,
      ariaCurrent: el ? el.getAttribute('aria-current') : null }; }),
  wizard_bar_display: getComputedStyle(document.getElementById('wizard-progress-bar')).display,
  html_lang: document.documentElement.lang,
  title: document.title,
  landmarks: {
    header: document.querySelectorAll('header,[role=banner]').length,
    nav: document.querySelectorAll('nav,[role=navigation]').length,
    main: document.querySelectorAll('main,[role=main]').length },
  imgs: [...document.querySelectorAll('#view-generate img')].map(i =>
    ({ id: i.id || null, alt: i.getAttribute('alt') })),
  h_top: [...document.querySelectorAll('h1,h2')].filter(h => h.offsetParent)
    .map(h => h.tagName + ':' + h.textContent.trim().slice(0, 30)).slice(0, 8),
})"""

COLOR_JS = """(sels) => sels.map(sel => {
  const el = document.querySelector(sel);
  if (!el || (!el.offsetParent && getComputedStyle(el).position !== 'fixed'))
    return { sel, missing: true };
  const cs = getComputedStyle(el);
  const stack = [];
  let node = el;
  while (node && node.nodeType === 1) {
    const b = getComputedStyle(node).backgroundColor;
    const m = b && b.match(/rgba?\\(([^)]+)\\)/);
    if (m) {
      const parts = m[1].split(',').map(parseFloat);
      const a = parts.length > 3 ? parts[3] : 1;
      if (a > 0) { stack.push(b); if (a >= 1) break; }
    }
    node = node.parentElement;
  }
  return { sel, color: cs.color, fontSize: cs.fontSize, fontWeight: cs.fontWeight,
    bgStack: stack, text: (el.textContent || '').trim().slice(0, 28) };
})"""


def parse_rgb(s):
    m = re.match(r"rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)", s)
    if not m:
        return None
    r, g, bch = float(m.group(1)), float(m.group(2)), float(m.group(3))
    a = float(m.group(4)) if m.group(4) is not None else 1.0
    return (r, g, bch, a)


def composite(stack):
    """bgStack(要素→祖先の順) を合成し不透明 RGB を返す。空なら白。"""
    base = (255.0, 255.0, 255.0)
    for s in reversed(stack):
        c = parse_rgb(s)
        if not c:
            continue
        r, g, bch, a = c
        base = (r * a + base[0] * (1 - a),
                g * a + base[1] * (1 - a),
                bch * a + base[2] * (1 - a))
    return base


def lum(rgb):
    def ch(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, bch = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(bch)


def contrast(fg, bg):
    l1, l2 = sorted([lum(fg), lum(bg)], reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def eval_contrast(items):
    out = []
    for it in items:
        if it.get("missing"):
            out.append(it)
            continue
        fg = parse_rgb(it["color"])
        bg = composite(it["bgStack"])
        if fg is None:
            it["ratio"] = None
            out.append(it)
            continue
        fga = fg[3]
        fgc = (fg[0] * fga + bg[0] * (1 - fga),
               fg[1] * fga + bg[1] * (1 - fga),
               fg[2] * fga + bg[2] * (1 - fga))
        ratio = contrast(fgc, bg)
        size = float(it["fontSize"].replace("px", ""))
        bold = int(it["fontWeight"]) >= 700 if it["fontWeight"].isdigit() else False
        large = size >= 24 or (size >= 18.66 and bold)
        req = 3.0 if large else 4.5
        it.update({"ratio": round(ratio, 2), "required": req,
                   "AA": "PASS" if ratio >= req else "FAIL",
                   "effective_bg": [round(x) for x in bg]})
        out.append(it)
    return out


def aria_snap(page, sel, fname):
    try:
        txt = page.locator(sel).aria_snapshot()
        with open(os.path.join(EV, fname), "w", encoding="utf-8") as f:
            f.write(txt)
        return True
    except Exception as e:
        R["errors"].append(f"aria_snapshot {fname}: {str(e)[:120]}")
        return False


def layout_check(page, label):
    return page.evaluate(
        """(label) => ({ state: label,
          scrollWidth: document.documentElement.scrollWidth,
          innerWidth: window.innerWidth,
          h_scroll: document.documentElement.scrollWidth > window.innerWidth })""",
        label)


with sync_playwright() as p:
    b, page = launch(p)
    open_generate(page)

    # C015/C016 ステップ1: aria snapshot・アクセシブル名・ARIA属性・ランドマーク
    aria_snap(page, "#view-generate", "c3_aria_p1.txt")
    R["obs"]["name_audit_p1"] = page.evaluate(NAME_AUDIT_JS)
    R["obs"]["aria_attrs_p1"] = page.evaluate(ARIA_ATTRS_JS)
    layouts = [layout_check(page, "p1")]

    # C018 コントラスト（ステップ1 + エラー文言）
    page.fill("#url-input", "not-a-url")
    page.wait_for_timeout(400)
    c_p1 = page.evaluate(COLOR_JS, [
        ".form-label", "#url-input", "#discover-btn", "#url-input-message",
        ".discover-scope-title", ".discover-scope-note", ".checkbox-chip",
        ".wizard-p1-hints span[title]", ".wizard-p1-hints p", "#sample-url-btn",
    ])

    # ステップ2へ（1画面解析）
    discover(page, MOCK + "/products/1", "single", 60000)
    c_sum = page.evaluate(COLOR_JS, [
        "#p1-screens-num", ".p1-result-label", "#p1-next-btn"])
    page.click("#p1-next-btn")
    page.wait_for_selector("#wizard-p2", state="visible")
    aria_snap(page, "#wizard-p2", "c3_aria_p2.txt")
    R["obs"]["name_audit_p2"] = page.evaluate(NAME_AUDIT_JS)
    R["obs"]["ws_attrs_p2"] = page.evaluate(
        """() => [1,2,3,4].map(n => { const el = document.getElementById('ws-' + n);
          return { id: 'ws-' + n, cls: el.className,
            ariaCurrent: el.getAttribute('aria-current') }; })""")
    layouts.append(layout_check(page, "p2"))
    c_p2 = page.evaluate(COLOR_JS, [
        "#submit-btn", ".app-sidebar-section", "#select-all-btn",
        "label[for=reference-doc-input]", ".wizard-p2-header h2",
        "#crawl-mode-field .form-label"])
    shot(page, "c3_p2.png")

    # 実行ビュー
    page.click("#submit-btn")
    page.wait_for_selector("#execution-view:not(.hidden)", state="attached")
    page.wait_for_timeout(1200)
    R["obs"]["aria_attrs_exec"] = page.evaluate(ARIA_ATTRS_JS)
    aria_snap(page, "#execution-view", "c3_aria_exec.txt")
    layouts.append(layout_check(page, "exec"))
    c_ex = page.evaluate(COLOR_JS, [
        "#exec-title", "#exec-message", "#exec-elapsed", "#exec-log",
        ".execution-step.is-active", ".execution-step:not(.is-active)",
        ".execution-meta-item dt", ".execution-meta-item dd", "#exec-stop-btn"])
    shot(page, "c3_exec.png")
    page.wait_for_selector("#exec-actions:not(.hidden)", state="attached",
                           timeout=240000)

    R["obs"]["contrast"] = eval_contrast(c_p1 + c_sum + c_p2 + c_ex)
    R["obs"]["layouts"] = layouts

    # C021 Landmark: レポートへ遷移→ナビの現在地→ドキュメント作成へ戻る
    try:
        nav_before = page.evaluate(
            """() => [...document.querySelectorAll('nav a, nav button, [data-view]')]
              .filter(e => e.offsetParent)
              .map(e => ({ text: (e.textContent || '').trim().slice(0, 20),
                view: e.dataset ? e.dataset.view || null : null,
                active: e.classList.contains('is-active') })).slice(0, 20)""")
        R["obs"]["nav_items"] = nav_before
        rb = page.evaluate(
            "() => document.getElementById('btn-view-report').style.display")
        if rb != "none":
            page.click("#btn-view-report")
            page.wait_for_timeout(1500)
            R["obs"]["after_report_nav"] = page.evaluate(
                """() => ({
                  active_view: (document.querySelector('.view.is-active') || {}).id || null,
                  nav_active: [...document.querySelectorAll('[data-view].is-active, nav .is-active')]
                    .map(e => (e.textContent || '').trim().slice(0, 20)),
                  heading: [...document.querySelectorAll('h1,h2')]
                    .filter(h => h.offsetParent).map(h => h.textContent.trim().slice(0, 30)).slice(0, 3)})""")
            shot(page, "c3_report_view.png")
            layouts.append(layout_check(page, "report"))
        back = open_generate(page)
        R["obs"]["back_to_generate"] = {
            "reached": back,
            "state": page.evaluate(
                """() => ({
                  p1_visible: !!document.getElementById('wizard-p1').offsetParent,
                  p2_visible: !!document.getElementById('wizard-p2').offsetParent,
                  url_value: document.getElementById('url-input').value})""")}
        shot(page, "c3_back_generate.png")
    except Exception as e:
        R["errors"].append(f"landmark: {str(e)[:200]}")

    save_json("c3_result.json", R)
    b.close()

fails = [c for c in R["obs"].get("contrast", []) if c.get("AA") == "FAIL"]
print("C3 done. contrast FAIL:", [(c["sel"], c["ratio"]) for c in fails])
print("layouts:", R["obs"].get("layouts"), "errors:", R["errors"])
