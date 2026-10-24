"""G-1（画面骨格）・G-2（主操作）の判定。Playwright の page.evaluate に渡す JS と、結果を文字列にする関数。"""

OLD_PRIMARY = (
    ".c-btn--primary,.btn-primary,.dax-btn--primary,.pri,.is-primary,"
    ".sidebar-primary-action,.primary,.rv-btn-pri,.dv-btn-primary,"
    ".rh-open-primary,.p1-btn.is-primary"
)

JS_G1 = """() => {
  const out = [];
  const se = document.scrollingElement;
  if (se.scrollHeight > innerHeight + 1) out.push('G-1: 画面全体がスクロールする（' + se.scrollHeight + ' > ' + innerHeight + '）');
  const c = document.querySelector('#app-content') || document.querySelector('.app-content');
  if (!c) out.push('G-1: 本文領域（#app-content）が無い');
  else if (c.clientHeight / innerHeight < 0.6) out.push('G-1: 本文領域が画面の 60% 未満（' + Math.round(c.clientHeight / innerHeight * 100) + '%）');
  const vis = (e) => !!e && e.offsetParent !== null;
  if (!vis(document.querySelector('.app-sidebar'))) out.push('G-1: .app-sidebar が無い／非表示');
  if (!vis(document.querySelector('.app-header') || document.querySelector('.app-topbar'))) out.push('G-1: .app-header（.app-topbar）が無い／非表示');
  const n = document.querySelectorAll('[aria-current="page"]').length;
  if (n !== 1) out.push('G-1: aria-current="page" が ' + n + ' 個（1 個であるべき）');
  return out;
}"""

JS_G2 = """(oldPrimary) => {
  const out = [];
  const shown = (e) => e.offsetParent !== null && !e.closest('[hidden]') &&
    !e.closest('dialog:not([open])') && !e.closest('.c-modal:not(.is-open):not([open])');
  const pri = [...document.querySelectorAll(oldPrimary)].filter(shown);
  if (pri.length > 1) out.push('G-2: 表示中の主ボタンが ' + pri.length + ' 個（' + pri.map(e => (e.textContent || '').trim().slice(0, 12)).join('／') + '）');
  for (const b of document.querySelectorAll('.c-btn')) {
    if (!shown(b) || b.closest('.c-modal__foot')) continue;
    const w0 = b.getBoundingClientRect().width;
    const old = b.style.width;
    b.style.width = 'max-content';
    const w1 = b.getBoundingClientRect().width;
    b.style.width = old;
    const label = (b.textContent || '').trim().slice(0, 12);
    if (w0 >= 480) out.push('G-2: ボタン「' + label + '」の幅が 480px 以上（' + Math.round(w0) + 'px）');
    else if (Math.abs(w0 - w1) > 2) out.push('G-2: ボタン「' + label + '」の幅が内容幅と違う（' + Math.round(w0) + 'px / 内容 ' + Math.round(w1) + 'px）');
  }
  return out;
}"""


def run_g1(page):
    """G-1 の NG 文字列リストを返す。"""
    return list(page.evaluate(JS_G1))


def run_g2(page):
    """G-2 の NG 文字列リストを返す。"""
    return list(page.evaluate(JS_G2, OLD_PRIMARY))
