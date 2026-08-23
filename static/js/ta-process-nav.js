// ---- テスト活動支援 / 工程ナビゲーション ----
// 工程の順序を 1 箇所で定義し、ホームの工程ストリップと各画面の前後ナビを配線する。
//
// 2026-08-23 のペルソナ評価で「次の工程へ進む導線が画面上に無く、最初のスタートで躓く」
// という指摘が独立に複数出たため追加した。順路は画面から読めなければならない。
(function () {
  'use strict';

  // ISO/IEC/IEEE 29119 の工程順。ホーム（入口）と連携設定（工程外）は含めない。
  const TA_PROCESS = [
    { view: 'test-plan', label: 'テスト計画' },
    { view: 'test-analysis', label: 'テスト基本設計' },
    { view: 'test-strategy', label: 'テスト詳細設計' },
    { view: 'test-design', label: 'テストケース実装' },
    { view: 'test-implementation', label: '自動テストケース実装' },
    { view: 'test-execution', label: '自動テスト実行' },
    { view: 'manual-execution', label: '手動テスト実行' },
    { view: 'defect-analysis', label: '不具合分析' },
    { view: 'code-fix', label: 'コード修正提案' },
    { view: 'test-completion', label: 'テスト完了' },
  ];

  function go(view) {
    if (typeof switchView === 'function') switchView(view);
  }

  // ---- ホームの工程ストリップ ----
  function wirePipeline() {
    const strip = document.getElementById('ta-pipeline');
    if (!strip) return;
    strip.querySelectorAll('.ta-pipeline-step[data-view]').forEach((btn) => {
      btn.addEventListener('click', () => go(btn.dataset.view));
    });
  }

  // 進捗は実データが決める。ここでは推測で「完了」を塗らない（偽の現在地を出さない）。
  function markPipeline(currentView) {
    const strip = document.getElementById('ta-pipeline');
    if (!strip) return;
    strip.querySelectorAll('.ta-pipeline-step').forEach((btn) => {
      btn.classList.toggle('is-current', btn.dataset.view === currentView);
    });
  }

  // ---- 各工程画面の末尾に「← 前 / 工程 n/10 / 次 →」を挿す ----
  // 全画面の HTML に同じ塊を書き写すと、工程の増減で 10 箇所の修正漏れが起きる。
  function injectStepNav() {
    TA_PROCESS.forEach((step, i) => {
      const section = document.getElementById('view-' + step.view);
      if (!section || section.querySelector('.ta2-stepnav')) return;

      const prev = i === 0 ? { view: 'test-activity', label: 'ホーム' } : TA_PROCESS[i - 1];
      const next = i < TA_PROCESS.length - 1 ? TA_PROCESS[i + 1] : null;

      const nav = document.createElement('div');
      nav.className = 'ta2-stepnav';

      const back = document.createElement('button');
      back.type = 'button';
      back.className = 'btn-outline-sm';
      back.textContent = '← ' + prev.label;
      back.addEventListener('click', () => go(prev.view));
      nav.appendChild(back);

      const pos = document.createElement('span');
      pos.className = 'ta2-pos';
      pos.textContent = `工程 ${i + 1} / ${TA_PROCESS.length}`;
      nav.appendChild(pos);

      const spacer = document.createElement('span');
      spacer.className = 'ta2-spacer';
      nav.appendChild(spacer);

      if (next) {
        const fwd = document.createElement('button');
        fwd.type = 'button';
        fwd.className = 'btn-primary';
        fwd.textContent = next.label + ' →';
        fwd.addEventListener('click', () => go(next.view));
        nav.appendChild(fwd);
      }
      section.appendChild(nav);
    });
  }

  // ---- サイドバー上部の「はじめる」: 最初の未完了工程へ送る ----
  // 進捗が分かるまでは先頭工程へ送る。「始める」と言いながら何も起きない状態を作らない。
  function wireStartButton() {
    const btn = document.getElementById('ta-new-btn');
    if (!btn) return;
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      go(TA_PROCESS[0].view);
    });
  }

  // ---- 二階層ナビ: 親カテゴリのレールと、その配下だけを出す子パネル ----
  // 12 工程を 1 列に並べると今どの局面にいるか読めないため、親で束ねる。
  const CAT_LABELS = {
    home: 'ホーム', design: '計画・設計', run: '実装・実行',
    improve: '改善・完了', config: '設定',
  };

  function catOfView(view) {
    const item = document.querySelector(`.app-nav-item[data-view="${view}"][data-nav-cat]`);
    return item ? item.dataset.navCat : '';
  }

  function openCategory(cat) {
    if (!cat) return;
    document.querySelectorAll('.app-nav-item[data-nav-cat]').forEach((el) => {
      if (el.dataset.navCat === cat) el.setAttribute('data-cat-open', '');
      else el.removeAttribute('data-cat-open');
    });
    document.querySelectorAll('.ta2-rail-item').forEach((el) => {
      el.setAttribute('aria-selected', String(el.dataset.navCat === cat));
    });
    const title = document.getElementById('ta2-cat-title');
    if (title) title.textContent = CAT_LABELS[cat] || '';
  }

  function wireRail() {
    document.querySelectorAll('.ta2-rail-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        const cat = btn.dataset.navCat;
        openCategory(cat);
        // 子を開くだけで終わらせない。押した親の先頭画面まで連れて行く。
        const first = document.querySelector(`.app-nav-item[data-nav-cat="${cat}"][data-view]`);
        if (first) go(first.dataset.view);
      });
    });
  }

  function init() {
    wirePipeline();
    injectStepNav();
    wireStartButton();
    wireRail();
    // 開いている画面の親カテゴリを開く。初期表示で子が全部閉じた状態を作らない。
    const active = document.querySelector('.view.is-active');
    openCategory(catOfView(active ? active.id.replace(/^view-/, '') : 'test-activity') || 'home');
    ['test-activity', 'integrations'].concat(TA_PROCESS.map((s2) => s2.view)).forEach((view) => {
      if (typeof onViewEnter === 'function') {
        onViewEnter(view, () => { markPipeline(view); openCategory(catOfView(view)); });
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.TA_PROCESS = TA_PROCESS;
})();
