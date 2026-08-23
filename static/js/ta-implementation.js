// ---- テスト活動支援 / 実装（テスト自動化） ----
// 変換帯（対象ケース・自動化率）は /api/ta/completion の終了基準データから実数を出す。
// コード生成・PR作成・ケース一覧の取り込みは対応APIが無いため準備中のまま（disabled data-wip）。
(function () {
  'use strict';

  let _loaded = false;

  const esc = (v) => (typeof escHtml === 'function'
    ? escHtml(String(v))
    : String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

  function domain() {
    const sel = document.getElementById('ta-design-domain') || document.getElementById('ta-exec-suite');
    return sel && sel.value ? sel.value : '';
  }

  // 終了基準の「消化率」current は "97.8%（32/1,641）" 形式（web/services/completion_criteria.py）。
  // 総ケース数はこの分母からしか取れないため、その前提でだけ数値を取り出す。
  function parseTotalCases(coverageCriterion) {
    const text = coverageCriterion && coverageCriterion.current ? String(coverageCriterion.current) : '';
    const m = text.match(/[／/]\s*([\d,]+)\s*[）)]/);
    if (!m) return null;
    const n = Number(m[1].replace(/,/g, ''));
    return Number.isFinite(n) ? n : null;
  }

  function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function render(data) {
    const criteria = Array.isArray(data && data.criteria) ? data.criteria : [];
    const coverage = criteria.find((c) => c && c.key === 'coverage');
    const automation = criteria.find((c) => c && c.key === 'automation');

    const total = parseTotalCases(coverage);
    setText('ta-impl-total-cases', total === null ? '—' : total.toLocaleString('ja-JP'));

    if (automation) {
      setText('ta-impl-automation-rate', automation.current || '—');
      setText('ta-impl-automation-target', `自動化率（目標 ${esc(automation.target || '—')}）`);
      const verdictEl = document.getElementById('ta-impl-automation-verdict');
      if (verdictEl) {
        verdictEl.textContent = automation.met ? '達成' : '未達';
        verdictEl.classList.remove('is-ok', 'is-wa');
        verdictEl.classList.add(automation.met ? 'is-ok' : 'is-wa');
      }
    } else {
      setText('ta-impl-automation-rate', '—');
      setText('ta-impl-automation-verdict', '—');
    }
  }

  async function load() {
    const dom = domain();
    if (!dom) return;
    try {
      const res = await fetch('/api/ta/completion?domain=' + encodeURIComponent(dom));
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || '終了基準を取得できませんでした');
      render(data);
      _loaded = true;
    } catch (e) {
      setText('ta-impl-total-cases', '—');
      setText('ta-impl-automation-rate', '—');
      setText('ta-impl-automation-verdict', '—');
    }
  }

  if (typeof onViewEnter === 'function') {
    onViewEnter('test-implementation', () => { _loaded = false; load(); });
  }

  document.getElementById('ta-impl-reload')?.addEventListener('click', load);

  // 生成オプションのチップは画面内だけの選択状態（バックエンドへ送る先がまだ無い）。
  document.getElementById('ta-impl-options')?.addEventListener('click', (ev) => {
    const btn = ev.target.closest('.ta-chip');
    if (!btn) return;
    btn.classList.toggle('is-on');
  });
})();
