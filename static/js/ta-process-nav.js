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

  function init() {
    wirePipeline();
    injectStepNav();
    wireStartButton();
    TA_PROCESS.forEach((step) => {
      if (typeof onViewEnter === 'function') {
        onViewEnter(step.view, () => markPipeline(step.view));
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
