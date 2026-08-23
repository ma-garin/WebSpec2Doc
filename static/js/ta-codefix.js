// ---- テスト活動支援 / コード修正提案 ----
// 修正提案そのものを作るAPIは無いため、不具合分析（/api/ta/defects）の結果を
// 「修正提案の元」として一覧化する。差分生成・影響再実行・PR作成は未実装のため
// data-wip で明示し、実データが取れる部分（不具合一覧・ODC分類・検出ケース）だけ表示する。
(function () {
  'use strict';

  const SEVERITY_CLASS = { critical: 'ng', high: 'ng', medium: 'wa', low: 'muted' };
  const SEVERITY_LABEL = { critical: '重大', high: '高', medium: '中', low: '低' };
  const STATE_CLASS = { new: 'ng', fixing: 'wa', retest: 'info', closed: 'ok' };
  const STATE_LABEL = { new: '新規', fixing: '修正中', retest: '再テスト待ち', closed: 'クローズ' };

  let _items = [];
  let _selectedId = '';
  let _loaded = false;

  const esc = (v) => (typeof escHtml === 'function'
    ? escHtml(String(v))
    : String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

  function domain() {
    const sel = document.getElementById('ta-design-domain') || document.getElementById('ta-exec-suite');
    return sel && sel.value ? sel.value : '';
  }

  function badge(cls, label) {
    return `<span class="ta2-badge ta2-badge-${cls}">${esc(label)}</span>`;
  }

  function selected() {
    return _items.find((d) => d.id === _selectedId) || null;
  }

  function renderList() {
    const box = document.getElementById('ta-fix-list');
    if (!box) return;
    if (!domain()) {
      box.innerHTML = '<div class="empty">対象ドメインを選択してください（テストケース実装の画面で選べます）</div>';
      return;
    }
    if (!_items.length) {
      box.innerHTML = '<div class="empty">不具合分析で原因を特定すると、ここに修正提案が出ます</div>';
      return;
    }
    box.innerHTML = _items.map((d) => {
      const sevCls = SEVERITY_CLASS[d.severity] || 'muted';
      const borderVar = sevCls === 'muted' ? 'var(--d-line, #E5E7EB)' : `var(--d-${sevCls})`;
      const on = d.id === _selectedId;
      const bg = on ? 'background:var(--d-primary-pale, #EDE7FE);' : '';
      return `<div data-fix-pick="${esc(d.id)}" style="cursor:pointer; padding:var(--space-2) var(--space-2) var(--space-2) var(--space-3);
        border-left:4px solid ${borderVar}; border-radius:var(--radius-md); ${bg}">
        <div style="font-weight:700; font-size:var(--text-sm);">${esc(d.id)}</div>
        <div class="muted-copy" style="font-size:var(--text-xs); margin:2px 0 4px;">${esc((d.summary || '（概要なし）').slice(0, 28))}</div>
        ${badge(STATE_CLASS[d.state] || 'muted', STATE_LABEL[d.state] || d.state || '不明')}
      </div>`;
    }).join('');
    box.querySelectorAll('[data-fix-pick]').forEach((row) => {
      row.addEventListener('click', () => {
        _selectedId = row.dataset.fixPick;
        renderList();
        renderDetail();
      });
    });
  }

  function renderCount() {
    const el = document.getElementById('ta-fix-open-count');
    if (!el) return;
    const open = _items.filter((d) => d.state !== 'closed').length;
    el.textContent = String(open);
    el.className = 'stat-card-value ' + (open > 0 ? 'is-ng' : 'is-ok');
  }

  function renderDetail() {
    const d = selected();
    const file = document.getElementById('ta-fix-file');
    const change = document.getElementById('ta-fix-change-summary');
    const src = document.getElementById('ta-fix-source-defect');
    const odc = document.getElementById('ta-fix-odc');
    const impactBody = document.getElementById('ta-fix-impact-body');
    const openBtn = document.getElementById('ta-fix-open-defect');
    if (!d) {
      if (file) file.innerHTML = '<div class="empty">左の一覧から不具合を選ぶと表示します</div>';
      if (change) change.innerHTML = '<div class="empty">左の一覧から不具合を選ぶと表示します</div>';
      if (src) src.innerHTML = '<div class="empty">未選択</div>';
      if (odc) odc.innerHTML = '<div class="empty">未選択</div>';
      if (impactBody) impactBody.innerHTML = '<tr><td colspan="3"><div class="empty">左の一覧から不具合を選ぶと、関連ケースを表示します</div></td></tr>';
      if (openBtn) openBtn.disabled = true;
      return;
    }
    if (file) file.innerHTML = '<span class="ta-wip-note">準備中（コード連携が未接続のため対象ファイルは未特定）</span>';
    if (change) change.textContent = d.summary || '（概要なし）';
    if (src) src.innerHTML = `<b>${esc(d.id)}</b> ${badge(SEVERITY_CLASS[d.severity] || 'muted', SEVERITY_LABEL[d.severity] || d.severity || '不明')}`;
    if (odc) odc.textContent = d.odc_type || '未分類';
    if (impactBody) {
      impactBody.innerHTML = d.case_id
        ? `<tr><td><b>${esc(d.case_id)}</b></td><td>-</td><td>-</td></tr>`
        : '<tr><td colspan="3"><div class="empty">この不具合に紐づくケースはありません</div></td></tr>';
    }
    if (openBtn) openBtn.disabled = false;
  }

  async function load() {
    const dom = domain();
    if (!dom) { renderList(); renderDetail(); return; }
    const box = document.getElementById('ta-fix-list');
    if (box) box.innerHTML = '<div class="empty">読み込んでいます…</div>';
    try {
      const res = await fetch('/api/ta/defects?domain=' + encodeURIComponent(dom));
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '不具合を取得できませんでした');
      _items = data.items || [];
      if (!_items.some((d) => d.id === _selectedId)) _selectedId = '';
      renderList();
      renderCount();
      renderDetail();
      _loaded = true;
    } catch (e) {
      if (box) box.innerHTML = `<div class="empty">${esc(String(e && e.message ? e.message : e))}</div>`;
    }
  }

  document.getElementById('ta-fix-reload')?.addEventListener('click', load);
  document.getElementById('ta-fix-open-defect')?.addEventListener('click', () => {
    if (document.getElementById('ta-fix-open-defect')?.disabled) return;
    if (typeof switchView === 'function') switchView('defect-analysis');
  });

  if (typeof onViewEnter === 'function') {
    onViewEnter('code-fix', () => { if (!_loaded) load(); });
  } else {
    document.addEventListener('DOMContentLoaded', load);
  }
})();
