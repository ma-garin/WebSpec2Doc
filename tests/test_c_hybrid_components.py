"""C. Hybrid 共通部品（static/js/c-hybrid.js・static/css/c-hybrid.css）を実ブラウザで確かめる。

サーバは使わない。空のページに tokens.css・c-hybrid.css・c-hybrid.js を読み込み、
window.WS2D の部品を直接呼ぶ。Chromium が起動できない環境では skip する。
契約: docs/research/gui-commercial-v2/C_CONTRACT.md
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CSS = [ROOT / "static" / "tokens.css", ROOT / "static" / "css" / "c-hybrid.css"]
JS = ROOT / "static" / "js" / "c-hybrid.js"

sync_api = pytest.importorskip("playwright.sync_api")

_CONTRAST = """
(sel) => {
  function rgb(s) { const m = s.match(/[\\d.]+/g).map(Number); return m; }
  function lum(c) {
    const a = c.slice(0, 3).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2];
  }
  function bg(e) {
    while (e) { const c = rgb(getComputedStyle(e).backgroundColor); if (c.length < 4 || c[3] > 0) { return c; } e = e.parentElement; }
    return [255, 255, 255];
  }
  return [...document.querySelectorAll(sel)].map(e => {
    const f = lum(rgb(getComputedStyle(e).color)), b = lum(bg(e));
    return [e.getAttribute('data-code') || e.className, (Math.max(f, b) + 0.05) / (Math.min(f, b) + 0.05)];
  });
}
"""


@pytest.fixture(scope="module")
def browser():
    try:
        pw = sync_api.sync_playwright().start()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Playwright を起動できません: {exc}")
    try:
        b = pw.chromium.launch()
    except Exception as exc:  # noqa: BLE001
        pw.stop()
        pytest.skip(f"Chromium を起動できません: {exc}")
    yield b
    b.close()
    pw.stop()


def _page(browser, width=1280):
    page = browser.new_page(viewport={"width": width, "height": 900})
    page.set_content(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8"></head><body>'
        '<button id="opener" type="button">根拠を見る</button><div id="host"></div><div id="reason"></div>'
        "</body></html>"
    )
    for css in CSS:
        page.add_style_tag(path=str(css))
    page.add_script_tag(path=str(JS))
    return page


def test_badges_show_shape_text_and_escape(browser):
    page = _page(browser)
    got = page.evaluate("""() => {
      const h = document.getElementById('host');
      h.innerHTML = WS2D.status.html('failed') + WS2D.evidence.html('observed') + WS2D.status.html('<x>', '<img src=x>');
      return [...h.children].map(e => [e.className, e.querySelector('[aria-hidden]').textContent, e.innerText]);
    }""")
    assert got[0][0] == "c-status c-status--failed" and got[0][1] == "×" and "失敗" in got[0][2]
    assert got[1][0] == "c-ev c-ev--observed" and got[1][1] == "●" and "実測" in got[1][2]
    assert got[2][0] == "c-status c-status--unknown" and "<img src=x>" in got[2][2]
    assert page.evaluate("() => document.querySelector('#host img')") is None
    # 区分は契約どおり（文書の記述と曖昧は事実にしない）
    cats = page.evaluate("""() => ['observed','observed_auth','record','document','static','inferred','ambiguous','unverified','unavailable','zzz']
      .map(c => WS2D.evidence.category(c))""")
    assert cats == ["fact", "fact", "fact", "inference", "inference", "inference",
                    "unverified", "unverified", "unverified", "unverified"]
    page.close()


def test_badge_contrast_meets_aa(browser):
    page = _page(browser)
    page.evaluate("""() => {
      const h = document.getElementById('host');
      h.innerHTML = ['not_started','preparing','running','waiting_review','waiting_approval','partial','done','failed','cancelled','unverified','unavailable']
        .map(c => WS2D.status.html(c)).join('') +
        ['observed','observed_auth','record','document','static','inferred','ambiguous','unverified','unavailable']
        .map(c => WS2D.evidence.html(c)).join('');
    }""")
    low = [(c, round(r, 2)) for c, r in page.evaluate(_CONTRAST, ".c-status, .c-ev") if r < 4.5]
    assert low == []
    page.close()


def test_kpis_state_reason(browser):
    page = _page(browser)
    got = page.evaluate("""() => {
      const h = document.getElementById('host');
      WS2D.kpis(h, [{label: 'A', value: null}, {label: 'B', value: 3, href: '/x'}, {label: 'C', value: 0, onClick: () => {}}]);
      const k = [...h.children].map(e => [e.tagName, e.querySelector('.c-kpi__value').textContent]);
      WS2D.state(h, {kind: 'error', message: 'm', retained: true, next: 'n', onAction: () => {}});
      const s = h.firstChild;
      WS2D.reason(document.getElementById('reason'), '理由です', 'warning');
      const r = document.getElementById('reason');
      return {k, role: s.getAttribute('role'), text: s.innerText, btn: s.querySelector('button').textContent,
              rrole: r.getAttribute('role'), rcls: r.className, rtext: r.textContent};
    }""")
    assert got["k"] == [["DIV", "未計測"], ["A", "3"], ["BUTTON", "0"]]
    assert got["role"] == "alert" and "既存の結果は保持しています" in got["text"] and "次にすること: n" in got["text"]
    assert got["btn"] == "再試行"
    assert got["rrole"] == "status" and "c-reason--warning" in got["rcls"] and got["rtext"] == "理由です"
    for kind in ("loading", "empty", "partial", "permission", "unavailable", "unverified", "stale"):
        role = page.evaluate(f"() => {{ WS2D.state(document.getElementById('host'), {{kind: '{kind}'}});"
                             " return document.querySelector('#host .c-state').getAttribute('role'); }")
        assert role == "status", kind
    page.close()


def _open_drawer(page):
    page.focus("#opener")
    page.evaluate("""() => WS2D.drawer.open({title: 'API: GET /api/categories/:param/items/very-long-path-name-for-wrap-check', state: 'inferred', stateReason: '静的解析の候補です',
      claim: '主張', facts: [{label: 'HTTP', value: 200}], inferences: ['推論'], limitations: ['制限'],
      sources: [{label: 'provider', value: 'rea'}], returnFocus: document.getElementById('opener')})""")


def test_drawer_order_focus_trap_escape_and_return(browser):
    page = _page(browser, 1280)
    _open_drawer(page)
    d = page.locator(".c-drawer")
    assert d.get_attribute("role") == "dialog" and d.get_attribute("aria-modal") == "true"
    heads = page.locator(".c-drawer__sec h3").all_text_contents()
    assert heads == ["1. 主張", "2. 実測事実", "3. 推論", "4. 制限", "5. 出典・位置・provider・version"]
    assert "静的解析の候補です" in page.locator(".c-drawer__state").inner_text()
    assert page.evaluate("() => document.activeElement.textContent") == "閉じる"
    # 「閉じる」が 1 行に収まる（縦に割れない）
    btn_h = page.evaluate("() => document.querySelector('.c-drawer__head .c-btn').getBoundingClientRect().height")
    assert btn_h < 40, btn_h
    # 1280px はオーバーレイ（本文を押さない）
    assert page.evaluate("() => getComputedStyle(document.body).paddingRight") == "0px"
    for _ in range(3):
        page.keyboard.press("Tab")
        assert page.evaluate("() => !!document.activeElement.closest('.c-drawer')")
    page.keyboard.press("Escape")
    assert page.locator(".c-drawer").count() == 0
    assert page.evaluate("() => document.activeElement.id") == "opener"
    page.close()


def test_drawer_pushes_content_at_1440(browser):
    page = _page(browser, 1440)
    _open_drawer(page)
    assert page.evaluate("() => getComputedStyle(document.body).paddingRight") == "440px"
    page.click(".c-drawer button")
    assert page.evaluate("() => getComputedStyle(document.body).paddingRight") == "0px"
    assert page.evaluate("() => document.activeElement.id") == "opener"
    page.close()


def test_confirm_danger_focus_escape_and_ok(browser):
    page = _page(browser)
    page.focus("#opener")
    page.evaluate("() => { window.__r = 'pending'; WS2D.confirm({title: '削除', message: '消します', detail: '元に戻せません',"
                  " confirmLabel: '削除する', danger: true}).then(v => { window.__r = v; }); }")
    box = page.locator(".c-confirm")
    assert box.get_attribute("role") == "alertdialog"
    assert page.evaluate("() => document.activeElement.textContent") == "キャンセル"
    assert "元に戻せません" in box.inner_text()
    page.keyboard.press("Escape")
    assert page.evaluate("() => window.__r") is False
    assert page.evaluate("() => document.activeElement.id") == "opener"
    page.evaluate("() => { WS2D.confirm({title: 't', message: 'm', confirmLabel: '進める'}).then(v => { window.__r = v; }); }")
    assert page.evaluate("() => document.activeElement.textContent") == "進める"
    page.keyboard.press("Enter")
    assert page.evaluate("() => window.__r") is True
    assert page.locator(".c-confirm").count() == 0
    page.close()


def test_modal_escape_returns_focus(browser):
    page = _page(browser)
    page.focus("#opener")
    page.evaluate("() => WS2D.modal.open({title: 'M', body: '本文', actions: [{label: '了解', primary: true}]})")
    m = page.locator(".c-modal")
    assert m.get_attribute("role") == "dialog" and m.get_attribute("aria-modal") == "true"
    assert page.evaluate("() => document.activeElement.textContent") == "了解"
    page.keyboard.press("Escape")
    assert page.locator(".c-modal").count() == 0
    assert page.evaluate("() => document.activeElement.id") == "opener"
    page.close()


def test_toast_kind_is_text_not_only_color(browser):
    page = _page(browser)
    got = page.evaluate("""() => { WS2D.toast('保存しました', 'success'); WS2D.toast('失敗しました', 'error');
      const h = document.querySelector('.c-toast-host');
      return [h.getAttribute('aria-live'), [...h.children].map(t => t.innerText.replace(/\\s+/g, ' '))]; }""")
    assert got[0] == "polite"
    assert got[1][0].startswith("成功") and "保存しました" in got[1][0]
    assert got[1][1].startswith("エラー") and "失敗しました" in got[1][1]
    page.close()


def test_evidence_color_follows_category(browser):
    """形・文字だけでなく色の区分も category と一致する（文書を緑＝事実に見せない）。"""
    page = _page(browser)
    got = page.evaluate("""() => {
      const h = document.getElementById('host');
      const codes = ['observed','observed_auth','record','document','static','inferred','ambiguous','unverified','unavailable'];
      h.innerHTML = codes.map(c => WS2D.evidence.html(c)).join('');
      return [...h.children].map((e, i) => [WS2D.evidence.category(codes[i]), getComputedStyle(e).backgroundColor]);
    }""")
    by_cat: dict[str, set[str]] = {}
    for cat, color in got:
        by_cat.setdefault(cat, set()).add(color)
    assert all(len(v) == 1 for v in by_cat.values()), by_cat
    assert len({next(iter(v)) for v in by_cat.values()}) == 3
    page.close()


def test_confirm_over_drawer_escape_closes_only_top(browser):
    page = _page(browser)
    _open_drawer(page)
    page.evaluate("() => { window.__r = 'pending'; WS2D.confirm({title: 't', message: 'm', confirmLabel: 'OK'})"
                  ".then(v => { window.__r = v; }); }")
    page.keyboard.press("Escape")
    assert page.evaluate("() => window.__r") is False
    assert page.locator(".c-drawer").count() == 1
    assert page.evaluate("() => !!document.activeElement.closest('.c-drawer')")
    page.keyboard.press("Escape")
    assert page.locator(".c-drawer").count() == 0
    assert page.evaluate("() => document.activeElement.id") == "opener"
    page.close()


def test_hidden_attribute_wins_over_component_display(browser):
    """トップバーの空の理由欄（<p class="c-reason" hidden>）が帯として見えない。"""
    page = _page(browser)
    got = page.evaluate("""() => {
      const h = document.getElementById('host');
      h.innerHTML = '<p class="c-reason" id="a" hidden></p><p class="c-reason" id="b"></p><div class="c-state" id="c" hidden>x</div>';
      return ['a', 'b', 'c'].map(id => getComputedStyle(document.getElementById(id)).display);
    }""")
    assert got == ["none", "none", "none"]
    page.close()


def test_loading_spinner_stops_with_reduced_motion(browser):
    page = _page(browser)
    page.emulate_media(reduced_motion="reduce")
    page.evaluate("() => WS2D.state(document.getElementById('host'), {kind: 'loading'})")
    assert page.evaluate("() => getComputedStyle(document.querySelector('.c-state__spinner')).animationName") == "none"
    assert page.locator(".c-state").get_attribute("aria-busy") == "true"
    page.close()
