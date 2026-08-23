// ---- テスト活動支援 / 手動テスト実行 ----
// 自動化できないケースを人が実施し、結果と証跡を記録する。
// 記録は消化率（テスト完了工程の終了基準）に効くので、「実施したのに残らない」を作らない。
(function () {
  'use strict';

  const RESULT_LABELS = { passed: '成功', failed: '失敗', blocked: 'ブロック' };
  let _cases = [];
  let _latest = {};
  let _result = 'passed';
  let _loaded = false;

  const esc = (v) => (typeof escHtml === 'function'
    ? escHtml(String(v))
    : String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

  function domain() {
    const sel = document.getElementById('ta-design-domain') || document.getElementById('ta-exec-suite');
    return sel && sel.value ? sel.value : '';
  }

  function resultBadge(result) {
    if (!result) return '<span class="ta2-badge ta2-badge-muted">未実施</span>';
    const cls = result === 'passed' ? 'ok' : (result === 'failed' ? 'ng' : 'wa');
    return `<span class="ta2-badge ta2-badge-${cls}">${esc(RESULT_LABELS[result] || result)}</span>`;
  }

  function renderCases() {
    const tbody = document.getElementById('ta-manual-case-body');
    if (!tbody) return;
    if (!_cases.length) {
      tbody.innerHTML = '<tr><td colspan="5"><div class="empty">自動化判定が「手動」のケースがありません</div></td></tr>';
      return;
    }
    tbody.innerHTML = _cases.map((c) => {
      const rec = _latest[c.case_id] || null;
      const evidence = rec && rec.evidence
        ? `<a href="${esc(rec.evidence)}">証跡</a>` : '<span class="muted-copy">—</span>';
      const note = rec && rec.note ? `<div class="muted-copy">${esc(rec.note)}</div>` : '';
      return `<tr>
        <td><b>${esc(c.case_id)}</b></td>
        <td>${esc(c.name || '')}${note}</td>
        <td>${resultBadge(rec && rec.result)}</td>
        <td>${evidence}</td>
        <td><button type="button" class="btn-outline-sm" data-manual-pick="${esc(c.case_id)}">記録する</button></td>
      </tr>`;
    }).join('');
    tbody.querySelectorAll('[data-manual-pick]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const sel = document.getElementById('ta-manual-case');
        if (sel) sel.value = btn.dataset.manualPick;
      });
    });
  }

  function renderStats(stats) {
    const s = stats || {};
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = String(v); };
    set('ta-manual-stat-total', s.total ?? _cases.length);
    set('ta-manual-stat-done', s.done ?? 0);
    set('ta-manual-stat-failed', s.failed ?? 0);
  }

  function fillCaseSelect() {
    const sel = document.getElementById('ta-manual-case');
    if (!sel) return;
    sel.innerHTML = '<option value="">ケースを選択</option>'
      + _cases.map((c) => `<option value="${esc(c.case_id)}">${esc(c.case_id)} ${esc(c.name || '')}</option>`).join('');
  }

  async function load() {
    const dom = domain();
    const tbody = document.getElementById('ta-manual-case-body');
    if (!dom) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="5"><div class="empty">対象ドメインを選択してください（テストケース実装の画面で選べます）</div></td></tr>';
      return;
    }
    if (tbody) tbody.innerHTML = '<tr><td colspan="5"><div class="empty">読み込んでいます…</div></td></tr>';
    try {
      const [tableRes, runsRes] = await Promise.all([
        fetch('/api/testcases/table?domain=' + encodeURIComponent(dom)),
        fetch('/api/ta/manual-runs?domain=' + encodeURIComponent(dom)),
      ]);
      const table = await tableRes.json();
      const runs = await runsRes.json();
      if (!tableRes.ok) throw new Error(table.error || 'テストケースを取得できませんでした');
      if (!runsRes.ok) throw new Error(runs.error || '実施記録を取得できませんでした');
      // 手動の対象は「自動実行されないケース」。自動実行の判定は
      // testcase_spec_generator が「自動化判定 == 自動化可」で決めているので、その補集合を取る。
      // 「手動」という語の有無で判定すると、空欄・未判定の行が誰にも実行されず落ちる。
      _cases = (table.rows || []).filter((r) => String(r.automation || '').trim() !== '自動化可');
      _latest = runs.latest || {};
      renderCases();
      fillCaseSelect();
      renderStats(Object.assign({}, runs.stats, { total: _cases.length }));
      _loaded = true;
    } catch (e) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="5"><div class="empty">${esc(String(e && e.message ? e.message : e))}</div></td></tr>`;
    }
  }

  async function save() {
    const dom = domain();
    const sel = document.getElementById('ta-manual-case');
    const note = document.getElementById('ta-manual-note');
    const btn = document.getElementById('ta-manual-save');
    if (!dom || !sel || !sel.value) return;
    btn.disabled = true;
    try {
      const res = await fetch('/api/ta/manual-runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: dom, case_id: sel.value, result: _result, note: note ? note.value : '' }),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || '保存に失敗しました');
      if (note) note.value = '';
      await load();
    } catch (e) {
      const tbody = document.getElementById('ta-manual-case-body');
      if (tbody) tbody.insertAdjacentHTML('afterbegin',
        `<tr><td colspan="5"><div class="empty">${esc(String(e && e.message ? e.message : e))}</div></td></tr>`);
    } finally {
      btn.disabled = false;
    }
  }

  function wireResultChips() {
    const box = document.getElementById('ta-manual-result');
    if (!box) return;
    const map = { pass: 'passed', fail: 'failed', blocked: 'blocked' };
    box.querySelectorAll('button').forEach((b) => {
      b.addEventListener('click', () => {
        box.querySelectorAll('button').forEach((x) => x.classList.remove('is-on'));
        b.classList.add('is-on');
        _result = map[b.dataset.value] || b.dataset.value || 'passed';
      });
    });
  }

  if (typeof onViewEnter === 'function') {
    onViewEnter('manual-execution', () => { if (!_loaded) load(); wireResultChips(); });
  }
  document.getElementById('ta-manual-reload')?.addEventListener('click', load);
  document.getElementById('ta-manual-save')?.addEventListener('click', save);
})();
