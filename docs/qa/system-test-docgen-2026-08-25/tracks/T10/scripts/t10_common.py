# T10 共通ヘルパ: 起動・ビュー到達・発見操作・証跡保存
import json
import os

BASE = "http://127.0.0.1:8765"
MOCK = "http://127.0.0.1:9110"
EV = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evidence"))


def launch(p):
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.set_default_timeout(20000)
    return browser, page


def open_generate(page):
    """ドキュメント作成ビューを開く。到達できたら True。"""
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    active = page.evaluate(
        "() => { const v = document.getElementById('view-generate');"
        " return !!v && v.classList.contains('is-active'); }")
    if not active:
        page.evaluate(
            """() => {
              const byData = document.querySelector('[data-view="generate"]');
              if (byData) { byData.click(); return; }
              const els = [...document.querySelectorAll('a,button')];
              const hit = els.find(e => /ドキュメント作成|ドキュメント生成/.test(e.textContent || ''));
              if (hit) hit.click();
            }""")
        page.wait_for_timeout(700)
    return page.evaluate(
        "() => { const v = document.getElementById('view-generate');"
        " return !!v && v.classList.contains('is-active'); }")


def save_json(name, data):
    path = os.path.join(EV, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return path


def shot(page, name, selector=None):
    path = os.path.join(EV, name)
    try:
        if selector:
            page.locator(selector).screenshot(path=path)
        else:
            page.screenshot(path=path)
    except Exception as e:  # 証跡取得失敗はテスト自体を落とさない
        print(f"shot failed {name}: {e}")
    return path


def set_scope(page, preset):
    """解析範囲プリセット: single / standard / wide / custom"""
    page.check(f"#discover-scope-{preset}")


def discover(page, url, preset="single", timeout=40000):
    """URL を入力して画面解析し、完了時の要約/メッセージを返す。"""
    page.fill("#url-input", url)
    if preset:
        set_scope(page, preset)
    page.click("#discover-btn")
    page.wait_for_function(
        """() => {
          const s = document.getElementById('p1-summary');
          const st = document.getElementById('discover-status');
          const ld = document.getElementById('discover-loading');
          const done = (s && s.style.display !== 'none') ||
                       (st && st.textContent.trim() !== '');
          const idle = !ld || ld.style.display === 'none';
          return done && idle;
        }""",
        timeout=timeout)
    return page.evaluate(
        """() => ({
          summary_visible: document.getElementById('p1-summary').style.display !== 'none',
          screens: document.getElementById('p1-screens-num').textContent.trim(),
          status: document.getElementById('discover-status').textContent.trim(),
          status_error: document.getElementById('discover-status')
                        .classList.contains('discover-status-error'),
          url_msg: document.getElementById('url-input-message').textContent.trim(),
        })""")
