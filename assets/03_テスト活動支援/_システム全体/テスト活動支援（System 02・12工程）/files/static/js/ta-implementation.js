// ---- テスト活動支援 / 実装（テスト自動化） ----
// 変換帯（対象ケース・自動化率）は /api/ta/completion の終了基準データから実数を出す。
// ケース一覧の取り込み・PR作成は対応APIが無いため準備中のまま（disabled data-wip）。
(function () {
  'use strict';

  let _loaded = false;
  let _caseFilter = 'all';

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

  // ---- ケース一覧の絞り込み（フロントのみ。行の表示切替） ----
  const CASE_FILTER_LABEL = { all: 'すべて', done: '自動化済', todo: '未自動化', failed: '失敗' };
  const DEFAULT_CASE_EMPTY_MSG = 'テストケース一覧の取り込みは準備中です。実装が完了すると、設計工程のケースがここに並びます。';
  const NO_MATCH_MSG = '該当0件です。';

  function caseBody() {
    return document.getElementById('ta-impl-case-body');
  }

  function caseRows() {
    const body = caseBody();
    return body ? Array.from(body.querySelectorAll('tr[data-ta-case]')) : [];
  }

  function setCaseEmptyMessage(msg) {
    const body = caseBody();
    if (!body) return;
    const row = body.querySelector('tr[data-ta-empty-row]');
    if (!row) return;
    const box = row.querySelector('.empty');
    if (box) box.textContent = msg;
    row.hidden = false;
  }

  function renderCaseFilterChips() {
    const rows = caseRows();
    const counts = { all: rows.length, done: 0, todo: 0, failed: 0 };
    rows.forEach((r) => {
      const st = r.getAttribute('data-ta-status');
      if (Object.prototype.hasOwnProperty.call(counts, st) && st !== 'all') counts[st] += 1;
    });
    Object.keys(CASE_FILTER_LABEL).forEach((key) => {
      const btn = document.getElementById('ta-impl-filter-' + key);
      if (!btn) return;
      btn.textContent = `${CASE_FILTER_LABEL[key]}（${counts[key]}）`;
      btn.classList.remove('ta2-badge-pri', 'ta2-badge-muted');
      btn.classList.add(key === _caseFilter ? 'ta2-badge-pri' : 'ta2-badge-muted');
      btn.setAttribute('aria-pressed', key === _caseFilter ? 'true' : 'false');
    });
    return { rows, counts };
  }

  function applyCaseFilter(key) {
    _caseFilter = key;
    const { rows } = renderCaseFilterChips();
    let visible = 0;
    rows.forEach((r) => {
      const show = key === 'all' || r.getAttribute('data-ta-status') === key;
      r.hidden = !show;
      if (show) visible += 1;
    });
    if (rows.length === 0) {
      setCaseEmptyMessage(key === 'all' ? DEFAULT_CASE_EMPTY_MSG : NO_MATCH_MSG);
    } else {
      setCaseEmptyMessage(visible === 0 ? NO_MATCH_MSG : '');
    }
  }

  document.getElementById('ta-impl-filter')?.addEventListener('click', (ev) => {
    const btn = ev.target.closest('.ta-chip');
    if (!btn || !btn.id || btn.id.indexOf('ta-impl-filter-') !== 0) return;
    const key = btn.id.replace('ta-impl-filter-', '');
    if (!Object.prototype.hasOwnProperty.call(CASE_FILTER_LABEL, key)) return;
    applyCaseFilter(key);
  });

  // ---- すべて選択（フロントのみ。表示中の行のチェックを一括トグル） ----
  document.getElementById('ta-impl-select-all')?.addEventListener('click', (ev) => {
    const btn = ev.currentTarget;
    const body = caseBody();
    const boxes = body
      ? Array.from(body.querySelectorAll('tr[data-ta-case]:not([hidden]) input[type="checkbox"]'))
      : [];
    const nextChecked = btn.getAttribute('data-ta-selected') !== '1';
    boxes.forEach((cb) => { cb.checked = nextChecked; });
    btn.setAttribute('data-ta-selected', nextChecked ? '1' : '0');
    btn.textContent = nextChecked ? '選択解除' : 'すべて選択';
  });

  // ---- AIでスクリプトを生成 ----
  function renderGeneratedCode(items) {
    const codeEl = document.getElementById('ta-impl-code');
    const emptyEl = document.getElementById('ta-impl-code-empty');
    if (!codeEl) return;
    const text = items
      .map((it) => (typeof it === 'string' ? it : JSON.stringify(it, null, 2)))
      .join('\n\n');
    codeEl.textContent = text;
    if (emptyEl) emptyEl.hidden = items.length > 0;
  }

  function setGenerateStatus(kind, text) {
    const el = document.getElementById('ta-impl-generate-status');
    if (!el) return;
    if (!text) { el.innerHTML = ''; return; }
    const cls = kind === 'ok' ? 'ta2-badge-ok' : kind === 'ng' ? 'ta2-badge-ng' : 'ta2-badge-info';
    el.innerHTML = `<span class="ta2-badge ${cls}">${esc(text)}</span>`;
  }

  document.getElementById('ta-impl-generate')?.addEventListener('click', async () => {
    const btn = document.getElementById('ta-impl-generate');
    if (!btn) return;
    const dom = domain();
    if (!dom) {
      setGenerateStatus('ng', '対象システムが未選択です');
      return;
    }
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = '生成中…';
    setGenerateStatus('info', '実行中…');
    try {
      const res = await fetch('/api/ta/ai/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: dom, kind: 'scripts' }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.status === 503) {
        throw new Error((data && data.error) || 'LLMが未設定です');
      }
      if (!res.ok || !data || data.ok !== true) {
        throw new Error((data && data.error) || 'コード生成に失敗しました');
      }
      const items = Array.isArray(data.items) ? data.items : [];
      renderGeneratedCode(items);
      setGenerateStatus('ok', `生成完了（${items.length}件）`);
    } catch (e) {
      setGenerateStatus('ng', e && e.message ? e.message : 'コード生成に失敗しました');
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  });

  if (typeof onViewEnter === 'function') {
    onViewEnter('test-implementation', () => {
      _loaded = false;
      load();
      renderCaseFilterChips();
    });
  }

  document.getElementById('ta-impl-reload')?.addEventListener('click', load);

  // 生成オプションのチップは画面内だけの選択状態（バックエンドへ送る先がまだ無い）。
  document.getElementById('ta-impl-options')?.addEventListener('click', (ev) => {
    const btn = ev.target.closest('.ta-chip');
    if (!btn) return;
    btn.classList.toggle('is-on');
  });
})();
