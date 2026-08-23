// ---- 二階層ナビゲーション（全システム共通） ----
// レールの親カテゴリを押すと、その配下の子項目だけをパネルに出す。
//
// カテゴリの定義は DOM が持つ（レール項目の data-nav-cat / data-cat-label、
// ナビ項目の data-nav-cat）。JS 側に系ごとの対応表を持つと、画面を足すたびに
// 2 箇所を直すことになり、必ず片方が古くなる。
(function () {
  'use strict';

  function railItems() { return document.querySelectorAll('.ta2-rail-item[data-nav-cat]'); }
  function navItems() { return document.querySelectorAll('.app-nav-item[data-nav-cat]'); }

  function isVisible(el) { return el.offsetParent !== null || getComputedStyle(el).display !== 'none'; }

  function openCategory(cat) {
    if (!cat) return;
    navItems().forEach((el) => {
      if (el.dataset.navCat === cat) el.setAttribute('data-cat-open', '');
      else el.removeAttribute('data-cat-open');
    });
    let label = '';
    railItems().forEach((el) => {
      const on = el.dataset.navCat === cat;
      el.setAttribute('aria-selected', String(on));
      if (on) label = el.dataset.catLabel || el.textContent.trim();
    });
    const title = document.getElementById('ta2-cat-title');
    if (title) title.textContent = label;

    // 子が 1 件だけのカテゴリでは、カテゴリ名と子の名前が同じものになる
    // （例: ダッシュボード）。同じ語を 2 行続けても選ぶ余地は増えないので、
    // 子リストは出さない。レールを押した時点でその画面へ着いている。
    const open = document.querySelectorAll('.app-nav-item[data-cat-open]');
    const head = document.querySelector('.ta2-panel-head');
    const solo = open.length === 1 && open[0].textContent.trim() === label;
    if (head) head.classList.toggle('is-solo', solo);
    open.forEach((el) => { el.hidden = solo; });
  }

  function categoryOfActiveView() {
    const active = document.querySelector('.view.is-active');
    if (!active) return '';
    const view = active.id.replace(/^view-/, '');
    const item = document.querySelector(`.app-nav-item[data-view="${view}"][data-nav-cat]`);
    return item ? item.dataset.navCat : '';
  }

  // 現在の系で最初に表示されているレール項目。系を切り替えた直後の既定に使う。
  function firstVisibleCategory() {
    let cat = '';
    railItems().forEach((el) => { if (!cat && isVisible(el)) cat = el.dataset.navCat; });
    return cat;
  }

  function hasVisibleRail(cat) {
    let ok = false;
    railItems().forEach((el) => { if (el.dataset.navCat === cat && isVisible(el)) ok = true; });
    return ok;
  }

  function syncToCurrentView() {
    const cat = categoryOfActiveView();
    openCategory(hasVisibleRail(cat) ? cat : firstVisibleCategory());
  }

  function init() {
    railItems().forEach((btn) => {
      btn.addEventListener('click', () => {
        const cat = btn.dataset.navCat;
        openCategory(cat);
        // 子を開くだけで終わらせない。押した親の先頭画面まで連れて行く。
        const first = document.querySelector(`.app-nav-item[data-nav-cat="${cat}"]`);
        if (!first) return;
        if (first.dataset.view && typeof switchView === 'function') switchView(first.dataset.view);
        else first.click();   // 履歴ボタンのように data-view を持たない項目
      });
    });

    syncToCurrentView();
    // ビュー切替は core.js が .view.is-active を付け替える。切り替わったら追従する。
    const stage = document.getElementById('app-content') || document.body;
    new MutationObserver(syncToCurrentView).observe(stage, {
      subtree: true, attributes: true, attributeFilter: ['class'],
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window.navTwoLevel = { openCategory, syncToCurrentView };
})();
