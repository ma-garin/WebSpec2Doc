// ---- テスト活動支援 / 不具合分析 ----
// 観測された事実（API から取れる実データ）と、AI の推定（odc_type 等・未設定なら「未分析」）を
// 地色で分ける。表ではなく「左に一覧・中央に事実・右に推定」のマスターディテールにする。
(function () {
  'use strict';

  const STATE_LABELS = { new: '新規', fixing: '修正中', retest: '再テスト待ち', closed: 'クローズ' };
  const DOMAIN_KEY = 'webspec2doc.ta.domain';
  const DEFECT_ID_KEY = 'webspec2doc.ta.defect_id';

  let _items = [];
  let _selectedId = null;
  let _loaded = false;
  let _domainsLoaded = false;
  let _analysisById = {};   // 不具合ID → { loading, error, items }（AIで原因分析の結果キャッシュ）
  let _jiraConfigured = false;   // /api/integrations で確認した Jira の設定有無

  const esc = (v) => (typeof escHtml === 'function'
    ? escHtml(String(v))
    : String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

  // AI 生成結果の1件は文字列 or オブジェクトの可能性があるため、表示用テキストに正規化する
  function itemText(x) {
    if (x === null || x === undefined) return '';
    if (typeof x === 'string') return x;
    if (typeof x === 'object') return x.text || x.why || x.content || x.label || x.summary || JSON.stringify(x);
    return String(x);
  }

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
    let html;
    if (!item.odc_type) {
      html = '<span class="ta2-badge ta2-badge-muted">未分析</span>'
        + '<div class="muted-copy" style="margin-top:var(--space-2);">ODC 分類（Defect Type）はまだ設定されていません。</div>';
    } else {
      const related = _items.filter((i) => i.odc_type === item.odc_type && i.id !== item.id).length;
      html = `<span class="ta2-badge ta2-badge-pri">${esc(item.odc_type)}</span>
        <div class="muted-copy" style="margin-top:var(--space-2);">同じ分類の他の不具合: ${related} 件</div>`;
    }
    const ana = _analysisById[item.id];
    if (ana) {
      if (ana.loading) {
        html += '<div class="muted-copy" style="margin-top:var(--space-3); border-top:1px solid var(--border); padding-top:var(--space-2);">分析しています…</div>';
      } else if (ana.error) {
        html += `<div style="margin-top:var(--space-3); border-top:1px solid var(--border); padding-top:var(--space-2);">
          <span class="ta2-badge ta2-badge-ng">失敗</span>
          <div class="muted-copy" style="margin-top:var(--space-2);">${esc(ana.error)}</div>
        </div>`;
      } else {
        const list = (ana.items || []).map((x) => `<li>${esc(itemText(x))}</li>`).join('') || '<li>（結果が空でした）</li>';
        html += `<div style="margin-top:var(--space-3); border-top:1px solid var(--border); padding-top:var(--space-2);">
          <span class="ta2-badge ta2-badge-ok">AIで原因分析・完了</span>
          <ul style="margin:var(--space-2) 0 0; padding-left:1.2em;">${list}</ul>
        </div>`;
      }
    }
    box.innerHTML = html;
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

  // AI/RCA 系のボタンは、不具合が選ばれていないと呼び出す対象がないため無効化する
  // （data-wip とは別軸: これは「未実装」ではなく「対象未選択」の無効化）
  function updateActionButtons() {
    const has = !!_selectedId;
    ['ta-defect-analyze', 'ta-defect-codefix', 'ta-defect-rca-suggest', 'ta-defect-rca-save'].forEach((id) => {
      const btn = document.getElementById(id);
      if (btn) btn.disabled = !has;
    });
    // Jira 起票は「不具合を選んでいる」かつ「Jira が設定済み」の両方が要る。
    // どちらが欠けているかを注記で必ず返す（押せない理由が分からない状態を作らない）。
    const syncBtn = document.getElementById('ta-defect-sync');
    const syncNote = document.getElementById('ta-defect-sync-note');
    if (syncBtn) syncBtn.disabled = !has || !_jiraConfigured;
    if (syncNote) {
      if (!_jiraConfigured) {
        syncNote.hidden = false;
        syncNote.textContent = 'Jira 未接続のため利用できません（連携設定へ）';
      } else if (!has) {
        syncNote.hidden = false;
        syncNote.textContent = '不具合を選ぶと起票できます';
      } else {
        syncNote.hidden = true;
      }
    }
  }

  // ---- Jira 連携の設定有無を確認する（未設定なら起票ボタンを開けない） ----
  async function loadJiraStatus() {
    try {
      const res = await fetch('/api/integrations');
      const data = await res.json().catch(() => ({}));
      _jiraConfigured = !!(res.ok && data && data.jira && data.jira.configured);
    } catch (e) {
      _jiraConfigured = false;
    }
    updateActionButtons();
  }

  // ---- 選択中の不具合を Jira 課題として起票する ----
  async function syncToJira() {
    const dom = domain();
    const item = _items.find((i) => i.id === _selectedId);
    if (!dom || !item) return;
    const btn = document.getElementById('ta-defect-sync');
    const note = document.getElementById('ta-defect-sync-note');
    const prev = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = '起票中…'; }
    if (note) { note.hidden = false; note.textContent = 'Jira へ送信しています…'; }
    try {
      const form = new FormData();
      form.append('domain', dom);
      form.append('defect_id', item.id);
      const res = await fetch('/api/integrations/jira/issues', { method: 'POST', body: form });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        throw new Error(data.error || ('起票に失敗しました（HTTP ' + res.status + '）'));
      }
      const key = data.issue_key || '';
      const url = data.issue_url || '';
      if (note) {
        note.hidden = false;
        note.textContent = '起票しました: ' + (key || '(キー不明)');
      }
      if (typeof appNotice === 'function') {
        appNotice('Jira に起票しました: ' + (key || '(キー不明)') + (url ? ' — ' + url : ''), false);
      }
    } catch (e) {
      const msg = String(e && e.message ? e.message : e);
      if (note) { note.hidden = false; note.textContent = '起票に失敗しました: ' + msg; }
      if (typeof appNotice === 'function') appNotice('Jira への起票に失敗しました: ' + msg, true);
    } finally {
      if (btn) btn.textContent = prev || 'Jira 課題として起票';
      updateActionButtons();
    }
  }

  function setRcaStatus(kind, text) {
    const el = document.getElementById('ta-defect-rca-status');
    if (!el) return;
    el.textContent = text || '';
    el.className = kind === 'ok' ? 'ta2-badge ta2-badge-ok' : kind === 'ng' ? 'ta2-badge ta2-badge-ng' : 'muted-copy';
    if (kind !== 'ok' && kind !== 'ng') el.style.fontSize = 'var(--text-xs)';
    else el.style.fontSize = '';
  }

  function clearRcaForm() {
    for (let i = 1; i <= 5; i++) {
      const input = document.getElementById('ta-defect-why-' + i);
      if (input) input.value = '';
    }
    setRcaStatus('idle', '');
  }

  function selectDefect(id) {
    _selectedId = id;
    clearRcaForm();
    renderList();
    renderDetail();
    renderAI();
    updateActionButtons();
  }

  async function load() {
    const dom = domain();
    const list = document.getElementById('ta-defect-list');
    _analysisById = {};
    if (!dom) {
      if (list) list.innerHTML = '<div class="empty">対象ドメインを選択してください</div>';
      _items = []; _selectedId = null;
      renderStats({});
      renderDetail();
      renderAI();
      updateActionButtons();
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
      updateActionButtons();
      renderDist('ta-defect-phase-chart', _items, 'injected_phase', '不具合が登録されると混入工程の分布が表示されます');
      renderDist('ta-defect-type-chart', _items, 'odc_type', 'ODC 分類（Defect Type）が設定されると分布が表示されます');
      _loaded = true;
    } catch (e) {
      if (list) list.innerHTML = `<div class="empty">${esc(String(e && e.message ? e.message : e))}</div>`;
    }
  }

  // ---- AIで原因分析（右ペイン・紫地に結果を出す） ----
  async function runAnalyze() {
    const dom = domain();
    const item = _items.find((i) => i.id === _selectedId);
    if (!dom || !item) return;
    const btn = document.getElementById('ta-defect-analyze');
    if (btn) btn.disabled = true;
    _analysisById[item.id] = { loading: true, error: null, items: null };
    renderAI();
    try {
      const res = await fetch('/api/ta/ai/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: dom, kind: 'rca' }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        throw new Error(data.error || (res.status === 503 ? 'LLMが未設定です' : 'AIによる原因分析に失敗しました'));
      }
      _analysisById[item.id] = { loading: false, error: null, items: data.items || [] };
    } catch (e) {
      _analysisById[item.id] = { loading: false, error: String(e && e.message ? e.message : e), items: null };
    } finally {
      updateActionButtons();
      renderAI();
    }
  }

  // ---- AIで下書き（Why1〜5 に流し込む） ----
  async function runRcaSuggest() {
    const dom = domain();
    if (!dom || !_selectedId) return;
    const btn = document.getElementById('ta-defect-rca-suggest');
    if (btn) btn.disabled = true;
    setRcaStatus('busy', '下書きを作成しています…');
    try {
      const res = await fetch('/api/ta/ai/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: dom, kind: 'rca' }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        throw new Error(data.error || (res.status === 503 ? 'LLMが未設定です' : '下書きの生成に失敗しました'));
      }
      const items = data.items || [];
      for (let i = 0; i < 5; i++) {
        const input = document.getElementById('ta-defect-why-' + (i + 1));
        if (input && items[i] !== undefined) input.value = itemText(items[i]);
      }
      setRcaStatus('ok', '下書きを反映しました');
    } catch (e) {
      setRcaStatus('ng', String(e && e.message ? e.message : e));
    } finally {
      updateActionButtons();
    }
  }

  // ---- RCA保存 ----
  async function runRcaSave() {
    const dom = domain();
    if (!dom || !_selectedId) return;
    const whys = [1, 2, 3, 4, 5].map((n) => (document.getElementById('ta-defect-why-' + n) || {}).value || '');
    const btn = document.getElementById('ta-defect-rca-save');
    if (btn) btn.disabled = true;
    setRcaStatus('busy', '保存しています…');
    try {
      const res = await fetch('/api/ta/rca', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: dom, defect_id: _selectedId, whys }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.error || data.ok === false) {
        throw new Error(data.error || (res.status === 503 ? 'LLMが未設定です' : '保存に失敗しました'));
      }
      setRcaStatus('ok', '保存しました');
    } catch (e) {
      setRcaStatus('ng', String(e && e.message ? e.message : e));
    } finally {
      updateActionButtons();
    }
  }

  // ---- コード修正提案へ送る（フロントのみ。選択中の不具合IDを引き継いで画面遷移） ----
  function sendToCodeFix() {
    if (!_selectedId) return;
    try { sessionStorage.setItem(DEFECT_ID_KEY, _selectedId); } catch (e) { /* 非対応環境 */ }
    if (typeof switchView === 'function') switchView('code-fix');
  }

  let _booted = false;
  function init() {
    if (_booted) return;
    _booted = true;
    const domSel = document.getElementById('ta-defect-domain');
    if (domSel) domSel.addEventListener('change', () => { rememberDomain(domSel.value); _selectedId = null; load(); });
    document.getElementById('ta-defect-reload')?.addEventListener('click', () => { loadDomains(); });
    document.getElementById('ta-defect-analyze')?.addEventListener('click', runAnalyze);
    document.getElementById('ta-defect-codefix')?.addEventListener('click', sendToCodeFix);
    document.getElementById('ta-defect-rca-suggest')?.addEventListener('click', runRcaSuggest);
    document.getElementById('ta-defect-rca-save')?.addEventListener('click', runRcaSave);
    // GitHub Issue 同期: トークン未接続のため実行できない。理由を明示し、連携設定への導線だけ出す
    document.getElementById('ta-defect-sync')?.addEventListener('click', syncToJira);
    // 未接続のときだけ連携設定への導線として働かせる（接続済みなら結果表示欄になる）。
    document.getElementById('ta-defect-sync-note')?.addEventListener('click', () => {
      if (_jiraConfigured) return;
      if (typeof switchView === 'function') switchView('integrations');
    });
    loadJiraStatus();
    updateActionButtons();
  }

  if (typeof onViewEnter === 'function') {
    onViewEnter('defect-analysis', () => {
      init();
      if (!_domainsLoaded) loadDomains();
      else if (!_loaded) load();
    });
  }
})();
