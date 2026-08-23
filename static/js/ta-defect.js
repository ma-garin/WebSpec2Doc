// ---- テスト活動支援 / 不具合分析 ----
// 観測された事実（API から取れる実データ）と、AI の推定（odc_type 等・未設定なら「未分析」）を
// 地色で分ける。表ではなく「左に一覧・中央に事実・右に推定」のマスターディテールにする。
(function () {
  'use strict';

  const STATE_LABELS = { new: '新規', fixing: '修正中', retest: '再テスト待ち', closed: 'クローズ' };
  const DOMAIN_KEY = 'webspec2doc.ta.domain';

  let _items = [];
  let _selectedId = null;
  let _loaded = false;
  let _domainsLoaded = false;

  const esc = (v) => (typeof escHtml === 'function'
    ? escHtml(String(v))
    : String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

  function rememberDomain(v) { try { sessionStorage.setItem(DOMAIN_KEY, v); } catch (e) { /* 非対応環境 */ } }
  function recallDomain() { try { return sessionStorage.getItem(DOMAIN_KEY) || ''; } catch (e) { return ''; } }

  // 対象ドメインはこの画面自身の <select id="ta-defect-domain"> で持つ。
  // 以前はテストケース実装ビューの select を間借りしており、そのビューが非表示のとき
  // display:none で操作不能になり一覧が永久に空になっていた（ta-manual.js と同じ症状・同じ解消法）。
  function domain() {
    const sel = document.getElementById('ta-defect-domain');
    return sel && sel.value ? sel.value : '';
  }

  async function loadDomains() {
    const sel = document.getElementById('ta-defect-domain');
    const list = document.getElementById('ta-defect-list');
    if (!sel) return;
    try {
      const res = await fetch('/api/history');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      const items = (data.items || []).filter((it) => it.domain);
      const current = sel.value;
      const recalled = recallDomain();
      sel.innerHTML = '<option value="">ドメインを選択</option>'
        + items.map((it) => `<option value="${esc(it.domain)}">${esc(it.domain)}</option>`).join('');
      if (items.length) {
        if (items.some((it) => it.domain === current)) sel.value = current;
        else if (items.some((it) => it.domain === recalled)) sel.value = recalled;
        else sel.value = items[0].domain;
        rememberDomain(sel.value);
      }
      _domainsLoaded = true;
      await load();
    } catch (e) {
      if (list) list.innerHTML = `<div class="empty">ドメイン一覧の取得に失敗しました（${esc(String(e && e.message ? e.message : e))}）</div>`;
    }
  }

  function stateBadgeClass(state) {
    if (state === 'closed') return 'ok';
    if (state === 'new') return 'ng';
    return 'wa';
  }

  function severityBarColor(sev) {
    if (sev === 'critical' || sev === 'high') return 'var(--d-ng-text)';
    if (sev === 'medium') return 'var(--d-wa-text)';
    return 'var(--d-ok-text)';
  }

  function renderStats(stats) {
    const s = stats || {};
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = String(v); };
    set('ta-defect-stat-total', s.total ?? 0);
    set('ta-defect-stat-open', s.open ?? 0);
    set('ta-defect-stat-fixed', s.closed ?? 0);
    set('ta-defect-critical-open', s.critical_open ?? 0);
  }

  function renderList() {
    const box = document.getElementById('ta-defect-list');
    if (!box) return;
    if (!_items.length) {
      box.innerHTML = '<div class="empty">［再読み込み］を押すと不具合が表示されます</div>';
      return;
    }
    box.innerHTML = _items.map((it) => {
      const selected = it.id === _selectedId;
      const bg = selected ? 'var(--d-primary-pale)' : 'transparent';
      return `<div data-defect-row="${esc(it.id)}" style="cursor:pointer; padding:var(--space-2) var(--space-2) var(--space-2) var(--space-3); border-left:4px solid ${severityBarColor(it.severity)}; background:${bg}; border-radius:var(--radius-md);">
        <div style="font-weight:700; font-size:var(--text-sm);">${esc(it.id)}</div>
        <div class="muted-copy" style="font-size:var(--text-xs); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${esc(it.summary || '（概要なし）')}</div>
      </div>`;
    }).join('');
    box.querySelectorAll('[data-defect-row]').forEach((row) => {
      row.addEventListener('click', () => selectDefect(row.dataset.defectRow));
    });
  }

  function renderDetail() {
    const box = document.getElementById('ta-defect-detail');
    if (!box) return;
    const item = _items.find((i) => i.id === _selectedId);
    if (!item) { box.innerHTML = '<div class="empty">左の一覧から不具合を選ぶと、観測された事実が表示されます</div>'; return; }
    const hist = (item.history || []).map((h) => `<div class="muted-copy">${esc(h.at || '')} ・ ${esc(STATE_LABELS[h.state] || h.state || '')}</div>`).join('')
      || '<div class="empty">履歴がありません</div>';
    box.innerHTML = `<div class="ta-kv">
      <div class="ta-kv-row"><div class="ta-kv-key">不具合ID</div><div class="ta-kv-val"><b>${esc(item.id)}</b> <span class="ta2-badge ta2-badge-${stateBadgeClass(item.state)}">${esc(STATE_LABELS[item.state] || item.state)}</span></div></div>
      <div class="ta-kv-row"><div class="ta-kv-key">概要</div><div class="ta-kv-val">${esc(item.summary || '—')}</div></div>
      <div class="ta-kv-row"><div class="ta-kv-key">発生ケース</div><div class="ta-kv-val">${esc(item.case_id || '—')}</div></div>
      <div class="ta-kv-row"><div class="ta-kv-key">検出工程</div><div class="ta-kv-val">${esc(item.detected_phase || '—')}</div></div>
      <div class="ta-kv-row"><div class="ta-kv-key">混入工程</div><div class="ta-kv-val">${esc(item.injected_phase || '—')}</div></div>
      <div class="ta-kv-row"><div class="ta-kv-key">状態履歴</div><div class="ta-kv-val">${hist}</div></div>
    </div>`;
  }

  function renderAI() {
    const box = document.getElementById('ta-defect-ai');
    if (!box) return;
    const item = _items.find((i) => i.id === _selectedId);
    if (!item) { box.innerHTML = '<div class="empty">不具合を選んでください</div>'; return; }
    if (!item.odc_type) {
      box.innerHTML = '<span class="ta2-badge ta2-badge-muted">未分析</span>'
        + '<div class="muted-copy" style="margin-top:var(--space-2);">ODC 分類（Defect Type）はまだ設定されていません。</div>';
      return;
    }
    const related = _items.filter((i) => i.odc_type === item.odc_type && i.id !== item.id).length;
    box.innerHTML = `<span class="ta2-badge ta2-badge-pri">${esc(item.odc_type)}</span>
      <div class="muted-copy" style="margin-top:var(--space-2);">同じ分類の他の不具合: ${related} 件</div>`;
  }

  function groupCount(items, key) {
    const map = {};
    items.forEach((it) => {
      const v = String(it[key] || '').trim() || '未設定';
      map[v] = (map[v] || 0) + 1;
    });
    return Object.entries(map).sort((a, b) => b[1] - a[1]);
  }

  function renderDist(id, items, key, emptyMsg) {
    const box = document.getElementById(id);
    if (!box) return;
    if (!items.length) { box.innerHTML = `<div class="empty">${esc(emptyMsg)}</div>`; return; }
    box.innerHTML = `<div class="ta-chips">${groupCount(items, key).map(([label, n]) => `<span class="ta-chip">${esc(label)}（${n}）</span>`).join('')}</div>`;
  }

  function selectDefect(id) {
    _selectedId = id;
    renderList();
    renderDetail();
    renderAI();
  }

  async function load() {
    const dom = domain();
    const list = document.getElementById('ta-defect-list');
    if (!dom) {
      if (list) list.innerHTML = '<div class="empty">対象ドメインを選択してください</div>';
      _items = []; _selectedId = null;
      renderStats({});
      renderDetail();
      renderAI();
      renderDist('ta-defect-phase-chart', [], 'injected_phase', '対象を選ぶと混入工程の分布が表示されます');
      renderDist('ta-defect-type-chart', [], 'odc_type', '対象を選ぶと Defect Type の分布が表示されます');
      return;
    }
    if (list) list.innerHTML = '<div class="empty">読み込んでいます…</div>';
    try {
      const res = await fetch('/api/ta/defects?domain=' + encodeURIComponent(dom));
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || '不具合を取得できませんでした');
      _items = data.items || [];
      if (!_items.some((i) => i.id === _selectedId)) _selectedId = _items.length ? _items[0].id : null;
      renderStats(data.stats);
      renderList();
      renderDetail();
      renderAI();
      renderDist('ta-defect-phase-chart', _items, 'injected_phase', '不具合が登録されると混入工程の分布が表示されます');
      renderDist('ta-defect-type-chart', _items, 'odc_type', 'ODC 分類（Defect Type）が設定されると分布が表示されます');
      _loaded = true;
    } catch (e) {
      if (list) list.innerHTML = `<div class="empty">${esc(String(e && e.message ? e.message : e))}</div>`;
    }
  }

  let _booted = false;
  function init() {
    if (_booted) return;
    _booted = true;
    const domSel = document.getElementById('ta-defect-domain');
    if (domSel) domSel.addEventListener('change', () => { rememberDomain(domSel.value); _selectedId = null; load(); });
    document.getElementById('ta-defect-reload')?.addEventListener('click', () => { loadDomains(); });
  }

  if (typeof onViewEnter === 'function') {
    onViewEnter('defect-analysis', () => {
      init();
      if (!_domainsLoaded) loadDomains();
      else if (!_loaded) load();
    });
  }
})();
