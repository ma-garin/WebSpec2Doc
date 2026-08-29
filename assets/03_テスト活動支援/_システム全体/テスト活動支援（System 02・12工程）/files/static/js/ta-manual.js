// ---- テスト活動支援 / 手動テスト実行 ----
// 自動化できないケースを人が実施し、結果と証跡を記録する。
// 記録は消化率（テスト完了工程の終了基準）に効くので、「実施したのに残らない」を作らない。
//
// 対象ドメインはこの画面自身の <select id="ta-manual-domain"> で持つ。
// 以前は他ビュー（設計）の #ta-design-domain を間借りしていたが、その要素は
// アクティブでないビューの中にあり display:none で「DOM上に存在するが操作不能」になる。
// この画面単体でデータ投入経路が完全に塞がっていたため、実体をここに置いて解消する。
(function () {
  'use strict';

  const RESULT_LABELS = { passed: '合格', failed: '不合格', blocked: 'ブロック' };
  const DOMAIN_KEY = 'webspec2doc.ta.domain';

  let _cases = [];
  let _latest = {};
  let _records = [];
  let _currentId = '';
  let _domainsLoaded = false;
  let _loaded = false;
  let _busy = false;

  const esc = (v) => (typeof escHtml === 'function'
    ? escHtml(String(v))
    : String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

  function rememberDomain(v) { try { sessionStorage.setItem(DOMAIN_KEY, v); } catch (e) { /* 非対応環境 */ } }
  function recallDomain() { try { return sessionStorage.getItem(DOMAIN_KEY) || ''; } catch (e) { return ''; } }

  function domain() {
    const sel = document.getElementById('ta-manual-domain');
    return sel && sel.value ? sel.value : '';
  }

  // ---- 集計はサーバの stats を鵜呑みにしない。API の stats.total は
  // 「このドメインの全ケース」（自動化可も含む）が母数なので、手動対象だけに
  // 絞った _cases と食い違う。ゲージ・数値行の内訳が必ず合計と一致するよう、
  // 表示に使う集計は _cases + _latest から自前で作る。
  function computeStats() {
    let passed = 0, failed = 0, blocked = 0;
    _cases.forEach((c) => {
      const rec = _latest[c.case_id];
      if (!rec || !rec.result) return;
      if (rec.result === 'passed') passed++;
      else if (rec.result === 'failed') failed++;
      else if (rec.result === 'blocked') blocked++;
    });
    const total = _cases.length;
    const done = passed + failed + blocked;
    const open = Math.max(total - done, 0);
    const rate = total ? done / total : 0;
    return { total, passed, failed, blocked, done, open, rate };
  }

  function pct(n, total) { return total ? Math.round((n / total) * 1000) / 10 : 0; }

  function renderBarAndGauge(s) {
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = String(v); };
    set('ta-manual-stat-open', s.open);
    set('ta-manual-stat-total', s.total);
    set('ta-manual-stat-failed', s.failed);
    set('ta-manual-stat-blocked', s.blocked);
    set('ta-manual-stat-passed', s.passed);
    set('ta-manual-stat-open2', s.open);
    set('ta-manual-stat-rate', Math.round(s.rate * 100) + '%');

    const setW = (id, v) => { const el = document.getElementById(id); if (el) el.style.width = pct(v, s.total) + '%'; };
    setW('ta-manual-gauge-failed', s.failed);
    setW('ta-manual-gauge-blocked', s.blocked);
    setW('ta-manual-gauge-passed', s.passed);
    setW('ta-manual-gauge-open', s.open);
    const gauge = document.getElementById('ta-manual-gauge');
    if (gauge) {
      gauge.setAttribute('aria-label',
        `実施状況の内訳: 失敗 ${s.failed} ブロック ${s.blocked} 成功 ${s.passed} 未消化 ${s.open}（全 ${s.total}）`);
    }

    const startBtn = document.getElementById('ta-manual-start');
    if (startBtn) {
      const ready = Boolean(domain()) && s.open > 0;
      startBtn.disabled = !ready;
      startBtn.title = !domain() ? '対象ドメインを選択してください'
        : (s.open > 0 ? '未消化のケースを1件開きます' : '未消化のケースはありません');
    }
  }

  function findCase(caseId) { return _cases.find((c) => c.case_id === caseId) || null; }

  function firstOpenCase(excludeId) {
    return _cases.find((c) => c.case_id !== excludeId && !(_latest[c.case_id] && _latest[c.case_id].result)) || null;
  }

  function fillCaseSelect() {
    const sel = document.getElementById('ta-manual-case');
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = '<option value="">ケースを選択</option>' + _cases.map((c) => {
      const rec = _latest[c.case_id];
      const state = rec && rec.result ? `（${RESULT_LABELS[rec.result] || rec.result}）` : '（未実施）';
      return `<option value="${esc(c.case_id)}">${esc(c.case_id)} ${esc(c.name || '')}${esc(state)}</option>`;
    }).join('');
    if (current && _cases.some((c) => c.case_id === current)) sel.value = current;
  }

  function stepsHtml(list) {
    const items = Array.isArray(list) ? list.filter((s) => String(s || '').trim()) : [];
    if (!items.length) return '<div class="muted-copy">手順の記載がありません</div>';
    return items.map((s, i) => `<div class="ta-step"><div class="ta-step-desc">${i + 1}. ${esc(s)}</div></div>`).join('');
  }

  function expectedHtml(list) {
    const items = Array.isArray(list) ? list.filter((s) => String(s || '').trim()) : [];
    if (!items.length) return '<span class="muted-copy">記載がありません</span>';
    return items.map((s) => esc(s)).join(' / ');
  }

  function renderCurrent() {
    const empty = document.getElementById('ta-manual-current-empty');
    const detail = document.getElementById('ta-manual-current-detail');
    const sub = document.getElementById('ta-manual-current-sub');
    const c = findCase(_currentId);
    if (!c) {
      _currentId = '';
      if (empty) empty.style.display = '';
      if (detail) detail.style.display = 'none';
      if (sub) {
        if (!domain()) sub.textContent = '対象を選ぶと未消化のケースがここに出ます';
        else if (!_cases.length) sub.textContent = '手動対象のケースがありません';
        else if (computeStats().open === 0) sub.textContent = '未消化のケースはありません（全て実施済みです）';
        else sub.textContent = 'ケースを選択するか［次のケースを開始］を押してください';
      }
      return;
    }
    if (empty) empty.style.display = 'none';
    if (detail) detail.style.display = '';
    if (sub) sub.textContent = `${c.case_id} を実施します`;
    const idEl = document.getElementById('ta-manual-current-id');
    const nameEl = document.getElementById('ta-manual-current-name');
    if (idEl) idEl.textContent = c.case_id;
    if (nameEl) nameEl.textContent = c.name || '';
    const stepsEl = document.getElementById('ta-manual-current-steps');
    if (stepsEl) stepsEl.innerHTML = stepsHtml(c.steps);
    const expectedEl = document.getElementById('ta-manual-current-expected');
    if (expectedEl) expectedEl.innerHTML = expectedHtml(c.expected);
    const sel = document.getElementById('ta-manual-case');
    if (sel) sel.value = c.case_id;
  }

  function setCurrent(caseId) {
    _currentId = caseId || '';
    renderCurrent();
  }

  function resultBadge(result) {
    if (!result) return '<span class="ta2-badge ta2-badge-muted">未実施</span>';
    const cls = result === 'passed' ? 'ok' : (result === 'failed' ? 'ng' : 'wa');
    return `<span class="ta2-badge ta2-badge-${cls}">${esc(RESULT_LABELS[result] || result)}</span>`;
  }

  function evidenceHtml(evidence) {
    const v = String(evidence || '').trim();
    if (!v) return '<span class="muted-copy">—</span>';
    if (/^https?:\/\//.test(v)) return `<a href="${esc(v)}" target="_blank" rel="noopener">証跡</a>`;
    return `<span class="muted-copy">${esc(v)}</span>`;
  }

  // 失敗を最左（このテーブルでは最上段）に固定する。同じ結果内は新しい順を保つ
  // （_records は API がすでに新しい順で返す。sort は安定ソートなので順序が保たれる）。
  function renderStream() {
    const tbody = document.getElementById('ta-manual-stream-body');
    if (!tbody) return;
    if (!_records.length) {
      tbody.innerHTML = `<tr><td colspan="5"><div class="empty">${domain() ? '実施記録はまだありません' : '対象を選ぶと実施記録がここに出ます'}</div></td></tr>`;
      return;
    }
    const weight = { failed: 0, blocked: 1, passed: 2 };
    const rows = _records.slice().sort((a, b) => (weight[a.result] ?? 3) - (weight[b.result] ?? 3));
    tbody.innerHTML = rows.map((r) => {
      const c = findCase(r.case_id);
      const caseLabel = c ? `${esc(r.case_id)} ${esc(c.name || '')}` : esc(r.case_id);
      const at = String(r.at || '').replace('T', ' ').slice(0, 19);
      return `<tr>
        <td>${resultBadge(r.result)}</td>
        <td>${caseLabel}</td>
        <td>${r.note ? esc(r.note) : '<span class="muted-copy">—</span>'}</td>
        <td>${evidenceHtml(r.evidence)}</td>
        <td class="muted-copy">${esc(at)}</td>
      </tr>`;
    }).join('');
  }

  // ---- 読み込み ----
  async function load() {
    const dom = domain();
    if (!dom) {
      _cases = []; _latest = {}; _records = []; _currentId = '';
      renderBarAndGauge(computeStats());
      fillCaseSelect();
      renderCurrent();
      renderStream();
      return;
    }
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
      _records = runs.records || [];
      if (!_currentId || !findCase(_currentId)) {
        const open = firstOpenCase('');
        _currentId = open ? open.case_id : '';
      }
      renderBarAndGauge(computeStats());
      fillCaseSelect();
      renderCurrent();
      renderStream();
      _loaded = true;
    } catch (e) {
      const tbody = document.getElementById('ta-manual-stream-body');
      if (tbody) tbody.innerHTML = `<tr><td colspan="5"><div class="empty">${esc(String(e && e.message ? e.message : e))}</div></td></tr>`;
    }
  }

  // ---- ドメイン一覧（この画面自身が対象を選べるようにする） ----
  async function loadDomains() {
    const sel = document.getElementById('ta-manual-domain');
    if (!sel) return;
    try {
      const res = await fetch('/api/history');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      // ケース表を組めるのは report.json（JSON 形式の成果物）を持つドメインだけ。
      const items = (data.items || []).filter(
        (it) => it.domain && Number(it.screens) > 0 && (it.formats || []).includes('JSON'),
      );
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
      const tbody = document.getElementById('ta-manual-stream-body');
      if (tbody) tbody.innerHTML = `<tr><td colspan="5"><div class="empty">ドメイン一覧の取得に失敗しました（${esc(String(e && e.message ? e.message : e))}）</div></td></tr>`;
    }
  }

  // ---- 記録（結果チップ = 送信ボタン。選ぶだけで即記録し、次のケースへ進む） ----
  function setResultBusy(busy) {
    _busy = busy;
    const box = document.getElementById('ta-manual-result');
    if (box) box.querySelectorAll('button').forEach((b) => { b.disabled = busy; });
  }

  async function submitResult(result) {
    if (_busy) return;
    const dom = domain();
    const caseId = _currentId || (document.getElementById('ta-manual-case') || {}).value;
    if (!dom || !caseId) return;
    const note = document.getElementById('ta-manual-note');
    const evidence = document.getElementById('ta-manual-evidence');
    setResultBusy(true);
    try {
      const res = await fetch('/api/ta/manual-runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          domain: dom,
          case_id: caseId,
          result,
          note: note ? note.value : '',
          evidence: evidence ? evidence.value : '',
        }),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || '保存に失敗しました');
      if (note) note.value = '';
      if (evidence) evidence.value = '';
      const doneId = caseId;
      await load();
      const next = firstOpenCase(doneId);
      setCurrent(next ? next.case_id : '');
    } catch (e) {
      const tbody = document.getElementById('ta-manual-stream-body');
      if (tbody) tbody.insertAdjacentHTML('afterbegin',
        `<tr><td colspan="5"><div class="empty">${esc(String(e && e.message ? e.message : e))}</div></td></tr>`);
    } finally {
      setResultBusy(false);
    }
  }

  function wireResultChips() {
    const box = document.getElementById('ta-manual-result');
    if (!box || box.dataset.wired) return;
    box.dataset.wired = '1';
    box.querySelectorAll('button[data-value]').forEach((b) => {
      b.addEventListener('click', () => submitResult(b.dataset.value));
    });
  }

  let _booted = false;
  function init() {
    if (_booted) return;
    _booted = true;

    const domSel = document.getElementById('ta-manual-domain');
    if (domSel) domSel.addEventListener('change', () => { rememberDomain(domSel.value); _currentId = ''; load(); });

    const caseSel = document.getElementById('ta-manual-case');
    if (caseSel) caseSel.addEventListener('change', () => setCurrent(caseSel.value));

    document.getElementById('ta-manual-start')?.addEventListener('click', () => {
      const next = firstOpenCase('');
      if (next) setCurrent(next.case_id);
    });
    document.getElementById('ta-manual-reload')?.addEventListener('click', () => { loadDomains(); });

    wireResultChips();
  }

  if (typeof onViewEnter === 'function') {
    onViewEnter('manual-execution', () => {
      init();
      if (!_domainsLoaded) loadDomains();
      else if (!_loaded) load();
    });
  }
})();
