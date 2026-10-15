/* バッチ・バックエンドのテスト（System 08）の画面。API: /api/backend-test/jobs（BD-008 5 章）。
 * ここで描くのは 案件一覧・段階ナビ・承認バー・段階 1〜5（段階 6 の「作る」も受ける）。段階 7・8 などは
 * backend-test-run.js（window.BackendTestRun）が描く。案件の更新は 'bs:job' イベントで知らせる。
 * 選んだ案件は ?job=、段階は #s<n> に持つ。 */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var NS = window.BackendTest = window.BackendTest || {};
  var API = '/api/backend-test/jobs';
  var NAMES = { 1: '目的・範囲', 2: '対象の読み取り', 3: '観点表', 4: 'ケース表', 5: 'テストデータ', 6: 'テストコード', 7: '実行', 8: '判定・報告' };
  var LEVELS = { integration_internal: '結合（内部）', integration_external: '結合（外部）', system: 'システム', acceptance: '受け入れ' };
  /* 段階の状態: [表示名, 見出しの pill, ナビの色] */
  var STATUS = { draft: ['未作成', 'p-new', ''], generated: ['承認待ち', 'p-flaky', 'wait'], approved: ['承認済み', 'p-pass', 'ok'], rejected: ['差し戻し', 'p-fail', 'back'] };
  var DESC = { draft: 'まだ作っていません。内容を作ってから承認します。', generated: '内容を確かめて、承認するか理由を書いて差し戻してください。',
    approved: '承認済みです。直すときは理由を書いて差し戻してください。', rejected: '差し戻しました。直して作り直してから承認します。' };
  var METHODS = { db_diff: '実行前後のデータを比べる', alt_sql: '別の計算で求めた値と比べる', golden: '承認済みの期待値と比べる', schema: 'テーブル定義に合うか確かめる' };
  var ORACLE_ST = { auto: ['機械が判定', 'p-pass'], human: ['人が確定', 'p-fixed'], unconfirmed: ['確定待ち', 'p-flaky'] };
  var TECHS = ['同値分割法（5.2.1）', '分類木法（5.2.2）', '境界値分析（5.2.3）', '構文テスト（5.2.4）', '組合せテスト（5.2.5）', 'デシジョンテーブルテスト（5.2.6）',
    '原因結果グラフ（5.2.7）', '状態遷移テスト（5.2.8）', 'シナリオテスト（5.2.9）', 'ランダムテスト（5.2.10）', 'メタモルフィックテスト（5.2.11）', '要件ベーステスト（5.2.12）', '技法なし（経験ベース）'];
  var PRIORITY = { high: '優先度 高', medium: '優先度 中', low: '優先度 低' };
  var KIND_LABEL = { table: 'テーブル', column: '列', constraint: '制約', jobarg: 'ジョブの引数', io: '入出力', rc: '終了コード', commit: 'コミット', rule: '業務ルール', formula: '計算式', date_rule: '日付の規則' };
  var REASON_NEEDED = { excluded: 1, discarded: 1 };
  var RANK = { qa: 1, senior_qa: 2 };
  var LOCK = '<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.6" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>';
  var state = { jobs: [], job: null, stage: 1, me: '', adding: false, oracleFor: '' };
  var renderers = {};

  /* ---- 共通 ---- */
  function obj(k, v) { var o = {}; o[k] = v; return o; }
  function text(v) {
    if (v == null) return '';
    if (Array.isArray(v)) return v.map(text).filter(Boolean).join('、');
    if (typeof v === 'object') return Object.keys(v).map(function (k) { return k + ': ' + text(v[k]); }).join('、');
    return String(v);
  }
  function api(method, path, body) {
    var opt = { method: method, headers: {}, credentials: 'same-origin' };
    if (body instanceof FormData) opt.body = body;
    else if (body) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    return fetch(path, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (r.ok) return d;
        var e = new Error(d.error || '処理できませんでした（' + r.status + '）。時間をおいてもう一度お試しください。');
        e.status = r.status; throw e;
      });
    }, function () { var e = new Error('サーバにつながりません。接続を確かめて「もう一度接続する」を押してください。'); e.network = true; throw e; });
  }
  /* 失敗の通知。API の理由（「理由。次の行動。」）は書き換えず 2 行に分けて出す（403 も同じ） */
  function notify(e, title) {
    var msg = String((e && e.message) || e || ''), b = $('#bs-banner');
    if (!msg) { b.hidden = true; return; }
    var i = msg.indexOf('。'), cut = i >= 0 && i < msg.length - 1;
    $('#bs-banner-title').textContent = title || (e && e.status === 403 ? 'この操作の権限がありません' : 'うまくいきませんでした');
    $('#bs-banner-msg').textContent = cut ? msg.slice(0, i + 1) : msg;
    $('#bs-banner-next').textContent = cut ? msg.slice(i + 1) : '内容を確かめて、もう一度お試しください。';
    $('#bs-banner-retry').hidden = !(e && e.network);
    b.hidden = false;
  }
  function toast(msg) {
    var t = $('#bs-toast'); t.textContent = msg; t.hidden = false;
    clearTimeout(toast.id); toast.id = setTimeout(function () { t.hidden = true; }, 3000);
  }
  function busy(el, on) { if (el) { el.classList.toggle('bs-busy', on); if ('disabled' in el) el.disabled = on; } }
  function run(el, p, okMsg) {
    notify(''); busy(el, true);
    return p.then(function (d) { if (d && d.job) setJob(d.job); if (okMsg) toast(okMsg); return d; })
      .catch(function (e) { notify(e); }).then(function (d) { busy(el, false); return d; });
  }
  function jobPath(suffix) { return API + '/' + encodeURIComponent(state.job.id) + (suffix || ''); }
  function patch(body, msg) { return run(null, api('PATCH', jobPath(), body), msg || '保存しました'); }
  function fmtSize(n) { return n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : n >= 1024 ? (n / 1024).toFixed(1) + ' KB' : n + ' B'; }
  function fmtTime(t) {
    var d = t ? new Date(t) : null;
    return d && !isNaN(d) ? d.toLocaleString('ja-JP', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
  }
  function fill(id, data) {
    var node = document.getElementById(id).content.firstElementChild.cloneNode(true);
    Object.keys(data).forEach(function (k) { var el = node.querySelector('[data-f="' + k + '"]'); if (el) el.textContent = text(data[k]); });
    return node;
  }
  function noneRow(tbody, cols, msg) {
    var tr = document.createElement('tr'), td = document.createElement('td');
    td.colSpan = cols; td.className = 'bs-none'; td.textContent = msg; tr.appendChild(td); tbody.innerHTML = ''; tbody.appendChild(tr);
  }
  function kpis(el, list) {
    el.innerHTML = '';
    list.forEach(function (k) {
      var d = document.createElement('div'), b = document.createElement('b'), s = document.createElement('span');
      d.className = 'kpi' + (k[2] ? ' ' + k[2] : ''); b.textContent = k[0]; s.textContent = k[1]; d.appendChild(b); d.appendChild(s); el.appendChild(d);
    });
  }
  function li(head, body, foot) {
    var el = document.createElement('li');
    if (head) { var b = document.createElement('b'); b.textContent = head + ' '; el.appendChild(b); }
    el.appendChild(document.createTextNode(body || ''));
    if (foot) { var s = document.createElement('small'); s.textContent = ' ' + foot; el.appendChild(s); }
    return el;
  }
  function fillList(sel, items, make, empty) {
    var ul = $(sel); ul.innerHTML = '';
    if (!items.length) { var e = li('', empty); e.className = 'bs-mut'; ul.appendChild(e); return; }
    items.forEach(function (it) { ul.appendChild(make(it)); });
  }
  function where(s) { s = s || {}; return s.file ? '（' + s.file + (s.line ? ' ' + s.line + ' 行目' : '') + '）' : ''; }
  function select(values, cur, field, label, disabled, labels) {
    var s = document.createElement('select');
    s.dataset.field = field; s.setAttribute('aria-label', label); s.disabled = !!disabled;
    values.forEach(function (v) { var o = document.createElement('option'); o.value = v; o.textContent = labels ? labels[v] : v; s.appendChild(o); });
    s.value = cur; return s;
  }

  /* ---- 案件と権限 ---- */
  function stageOf(job, n) { return (job && job.stages && job.stages[n]) || { status: 'draft', version: 0 }; }
  function currentStage(job) { for (var n = 1; n <= 8; n++) { if (stageOf(job, n).status !== 'approved') return n; } return 8; }
  function myRole() { var j = state.job || {}; return j.my_role || (j.members || {})[state.me] || ''; }
  function required(n) { return ((state.job || {}).approver_roles || {})[n] || (n === 4 || n === 8 ? 'senior_qa' : 'qa'); }
  function isSenior() { return myRole() === 'senior_qa'; }
  function loadJobs() { return api('GET', API).then(function (d) { state.jobs = d.jobs || []; renderJobs(); }).catch(notify); }
  function jobState(j) {
    if (!j.stages) return '';
    var n = currentStage(j), st = stageOf(j, n);
    return '段階 ' + n + ' ' + NAMES[n] + '・' + (st.stale ? '前段が変わりました' : (STATUS[st.status] || STATUS.draft)[0]);
  }
  function renderJobs() {
    var q = ($('#bs-q').value || '').trim().toLowerCase(), box = $('#bs-jobs'), cur = state.job && state.job.id;
    var list = state.jobs.filter(function (j) { return !q || String(j.name || '').toLowerCase().indexOf(q) >= 0; });
    $('#bs-cnt').textContent = state.jobs.length; box.innerHTML = '';
    if (!list.length) {
      var p = document.createElement('div'); p.className = 'item empty';
      p.textContent = state.jobs.length ? '一致する案件はありません' : 'まだ案件がありません'; box.appendChild(p);
    }
    list.forEach(function (j) {
      var it = fill('bs-tpl-job', { name: j.name || '名前のない案件', level: LEVELS[j.level] || '', state: jobState(j) });
      it.dataset.job = j.id; it.classList.toggle('on', j.id === cur); it.setAttribute('aria-current', String(j.id === cur)); box.appendChild(it);
    });
    $('#bs-empty').hidden = !!state.job;
    $('#bs-empty h2').textContent = state.jobs.length ? '左の一覧から案件を選んでください' : 'テストするバッチを登録してください';
  }
  function openJob(id, stage) {
    notify('');
    return api('GET', API + '/' + encodeURIComponent(id)).then(function (d) {
      state.stage = +(stage || currentStage(d.job)); setJob(d.job); showStage(state.stage);
    }).catch(notify);
  }
  /* 案件を読み込む・更新するたびに通る。段階 6〜8 の担当へも同じ案件を渡す */
  function setJob(job) {
    var known = state.jobs.some(function (j) { return j.id === job.id; });
    state.job = job;
    state.jobs = known ? state.jobs.map(function (j) { return j.id === job.id ? job : j; }) : [job].concat(state.jobs);
    NS.role = myRole();
    renderAll();
    document.dispatchEvent(new CustomEvent('bs:job', { detail: { job: job } }));
    if (window.BackendTestRun && window.BackendTestRun.setJob) window.BackendTestRun.setJob(job);
  }

  /* ---- 段階ナビ・見出し・承認バー ---- */
  function renderNav() {
    var j = state.job;
    $$('#bs-nav [data-stage]').forEach(function (b) {
      var n = +b.dataset.stage, st = j ? stageOf(j, n) : null, s = st ? (STATUS[st.status] || STATUS.draft) : STATUS.draft;
      var on = !!j && n === state.stage, cls = st && st.stale ? 'back' : s[2], num = $('[data-num]', b), lab = $('[data-state]', b);
      b.disabled = !j; b.classList.toggle('on', on);
      if (on) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current');
      num.className = 'bs-num' + (on ? ' on' : cls ? ' ' + cls : '');
      if (st && st.status === 'approved') num.innerHTML = LOCK; else num.textContent = n;
      lab.className = 'bs-navst' + (cls && cls !== 'ok' ? ' ' + cls : '');
      lab.textContent = !st || st.status === 'draft' ? '' : st.stale ? '前段変更' : s[0];
      b.title = NAMES[n] + (st ? '：' + (st.stale ? '前段が変わりました' : s[0]) : '');
    });
  }
  function renderHead() {
    var n = state.stage, st = stageOf(state.job, n), s = STATUS[st.status] || STATUS.draft, pill = $('#bs-stage-pill');
    $('#bs-stage-no').textContent = '段階 ' + n; $('#bs-stage-name').textContent = NAMES[n];
    pill.className = 'pill ' + s[1]; pill.textContent = s[0]; $('#bs-stage-stale').hidden = !st.stale;
    $('#bs-stage-meta').textContent = st.version ? '版 ' + st.version + (st.approved_at ? '・承認 ' + fmtTime(st.approved_at) : '') : '';
  }
  function renderApprove() {
    var j = state.job, n = state.stage, st = stageOf(j, n), bar = $('#bs-approve'), mine = myRole(), lock = $('#bs-approve-lock');
    var allowed = (RANK[mine] || 0) >= (RANK[required(n)] || 1), ready = st.status === 'generated' || (n === 1 && st.status !== 'approved');
    var canReject = st.status === 'generated' || st.status === 'approved';
    var open = n === 4 ? (j.cases || []).filter(function (c) { return !c.oracle || c.oracle.state === 'unconfirmed'; }).length : 0;
    bar.dataset.stage = n; bar.dataset.version = st.version || 0;
    $('#bs-approve-title').textContent = '段階 ' + n + '「' + NAMES[n] + '」の承認';
    $('#bs-approve-desc').textContent = st.stale ? '前の段階が変わりました。内容を確かめてから承認し直してください。'
      : n === 1 && st.status === 'draft' ? '目的と範囲を選んだら承認してください。' : DESC[st.status] || DESC.draft;
    $('#bs-approve-version').textContent = st.version || '-'; $('#bs-approve-open').textContent = open;
    $('#bs-approve-btn').disabled = !allowed || !ready; lock.hidden = allowed;
    lock.textContent = mine ? 'この段階の承認はシニア QA が行います。気づいたことは理由を書いて差し戻せます。'
      : 'この案件のメンバーではないため承認できません。承認が必要なら案件の作成者に依頼してください。';
    $('#bs-reject').disabled = !canReject; $('#bs-reject-reason').disabled = !canReject;
    $('#bs-revert').hidden = !((st.version || 0) >= 2);
  }
  function renderProd() {
    var j = state.job, env = j && (j.envs || []).filter(function (e) { return e.id === j.current_env; })[0], on = !!(env && env.production);
    $('#bs-prod-banner').hidden = !on;
    if (on) { $('#bs-prod-env').textContent = env.name || ''; $('#bs-prod-reasons').textContent = text(env.production_reasons || []); }
  }
  function renderPanel() {
    var j = state.job, n = state.stage, fn = renderers[n];
    $$('.bs-panel').forEach(function (p) { p.hidden = !j || +p.dataset.stage !== n; });
    $('#bs-stagehead').hidden = !j; $('#bs-approve').hidden = !j;
    $('#topbar-title').textContent = j ? (j.name || '名前のない案件') : '案件を選んでください';
    if (!j) return;
    renderHead(); renderApprove();
    if (!fn) return;
    try { fn(j, n); } catch (e) { console.error('BackendTest stage ' + n, e); notify('画面の一部を表示できませんでした。画面を再読み込みしてください。'); }
  }
  function renderAll() { renderJobs(); renderNav(); renderProd(); renderPanel(); }
  function showStage(n) {
    n = Math.min(8, Math.max(1, parseInt(n, 10) || 1));
    state.stage = n; state.oracleFor = ''; state.adding = false;
    if (state.job) history.replaceState(null, '', '?job=' + encodeURIComponent(state.job.id) + '#s' + n);
    renderNav(); renderPanel();
    var c = $('#bs-content'); if (c) c.scrollTop = 0;
    if (n >= 6 && state.job && window.BackendTestRun && window.BackendTestRun.show) window.BackendTestRun.show(n);
  }

  /* ---- 段階 1 目的・範囲 ---- */
  function setVal(sel, v, lock) { var el = $(sel); if (document.activeElement !== el) el.value = v; el.disabled = !!lock; }
  renderers[1] = function (j) {
    var lock = stageOf(j, 1).status === 'approved', t = (j.targets || [])[0] || {};
    $$('#bs-level [data-level]').forEach(function (b) { b.setAttribute('aria-checked', String(b.dataset.level === j.level)); b.disabled = lock; });
    $$('#bs-target-kind [data-kind]').forEach(function (b) { b.setAttribute('aria-checked', String(b.dataset.kind === (j.target_kind || 'batch'))); });
    setVal('#bs-target-cmd', t.command || '', lock); setVal('#bs-purpose', j.purpose || '', lock); setVal('#bs-scope', j.scope || '', lock);
    setVal('#bs-llm', (j.llm && j.llm.provider) || 'openai', lock); setVal('#bs-retention', j.retention_days || 90, lock);
  };
  function changeS1(t) {
    var j = state.job, key = { 'bs-purpose': 'purpose', 'bs-scope': 'scope' }[t.id];
    if (key) return patch(obj(key, t.value.trim()));
    if (t.id === 'bs-llm') return patch({ llm: Object.assign({}, j.llm, { provider: t.value, external_scope: 'schema_spec' }) }, '資料を読ませる AI を保存しました');
    if (t.id === 'bs-retention') {
      var d = parseInt(t.value, 10);
      if (d >= 1 && d <= 3650) return patch({ retention_days: d }, '保存する日数を保存しました');
      return notify('保存する日数は 1〜3650 の数で入れてください。数を直すと保存します。', '保存できませんでした');
    }
    if (t.id !== 'bs-target-cmd') return;
    var list = j.targets || [], cur = list[0] || { id: 't1', kind: 'batch', launch: 'command', inputs: [], outputs: [] };
    var next = [Object.assign({}, cur, { command: t.value.trim() })].concat(list.slice(1));
    return run(null, api('PUT', jobPath('/targets'), { targets: next }), '起動のしかたを保存しました');
  }

  /* ---- 段階 2 対象の読み取り ---- */
  renderers[2] = function (j) {
    var files = j.files || [], facts = j.facts || [], qs = j.questions || [], un = j.unread || j.unparsed || [], body = $('#bs-files'), fb = $('#bs-facts');
    if (!files.length) noneRow(body, 5, 'まだ資料がありません。テーブル定義やジョブ定義をここへ落としてください。'); else body.innerHTML = '';
    files.forEach(function (f) {
      var n = (f.redactions || []).length, tr = fill('bs-tpl-file', { name: f.name, size: fmtSize(f.size || 0), redactions: n ? n + ' 箇所' : 'なし' }), sel = $('[data-f="kind"]', tr);
      sel.value = f.kind || 'other'; sel.dataset.file = f.name; sel.setAttribute('aria-label', f.name + ' の種類');
      $('[data-act="file-del"]', tr).dataset.file = f.name; body.appendChild(tr);
    });
    fb.innerHTML = '';
    facts.forEach(function (x) {
      var s = x.source || {}, head = KIND_LABEL[x.kind] ? KIND_LABEL[x.kind] + '：' : '';
      fb.appendChild(fill('bs-tpl-fact', { id: x.id, text: head + text(x.subject) + (x.value ? ' — ' + text(x.value) : ''),
        file: s.file || '根拠の資料なし', line: s.line ? s.line + ' 行目' : '', quote: s.text || '' }));
    });
    $('#bs-facts-none').hidden = facts.length > 0;
    fillList('#bs-questions', qs, function (q) { return li('確認したいこと', text(q.text), where(q.source)); }, '確認したいことはありません。');
    fillList('#bs-unread', un, function (u) {
      return typeof u === 'string' ? li('', u) : li('', text(u.reason || u.text || u.file), where(u.source || u));
    }, '読めなかった資料はありません。');
    kpis($('#bs-facts-kpis'), [[files.length, '資料'], [facts.length, '読み取った事実', facts.length ? 'ok' : ''],
      [qs.length, '確認したいこと', qs.length ? 'wa' : ''], [un.length, '読めなかった文', un.length ? 'wa' : '']]);
  };
  function upload(files) {
    if (!files || !files.length || !state.job) return;
    var fd = new FormData();
    Array.prototype.forEach.call(files, function (f) { fd.append('files', f); });
    run($('#bs-drop'), api('POST', jobPath('/files'), fd), files.length + ' 件の資料を取り込みました');
  }

  /* ---- 段階 3 観点表（優先度・技法・扱いの切替） ---- */
  renderers[3] = function (j) {
    var vps = j.viewpoints || [], edit = stageOf(j, 3).status === 'generated', senior = isSenior(), techs = {};
    var body = $('#bs-viewpoints'), chips = $('#bs-techs'), add = $('#bs-vp-add');
    vps.forEach(function (v) { if (v.decision !== 'discarded') techs[v.technique] = (techs[v.technique] || 0) + 1; });
    chips.innerHTML = '';
    Object.keys(techs).forEach(function (t) {
      var s = document.createElement('span'), em = document.createElement('em');
      s.className = 'fchip'; s.textContent = t + ' '; em.textContent = techs[t]; s.appendChild(em); chips.appendChild(s);
    });
    if (!vps.length) chips.textContent = '観点を作ると、使った技法が並びます。';
    var emit = vps.filter(function (v) { return !REASON_NEEDED[v.decision]; }).length;
    $('#bs-vp-count').textContent = vps.length ? vps.length + ' 件（出す ' + emit + '・対象外と破棄 ' + (vps.length - emit) + '）' : '';
    add.disabled = !senior || !edit; add.title = !senior ? '観点の追加はシニア QA が行います' : !edit ? '承認待ちの段階でだけ追加できます' : '';
    if (!vps.length) noneRow(body, 6, 'まだ観点がありません。前の段階を承認してから「観点を作る」を押してください。'); else body.innerHTML = '';
    vps.forEach(function (v) { body.appendChild(vpRow(v, edit)); });
    if (state.adding) body.insertBefore(addRow(), body.firstChild);
  };
  function vpRow(v, edit) {
    var tr = fill('bs-tpl-viewpoint', { id: v.id, name: v.name, basis: v.basis }), tech = $('[data-f="technique"]', tr);
    var dec = $('[data-f="decision"]', tr), rs = $('[data-f="reason"]', tr);
    tr.dataset.vp = v.id; tech.textContent = '';
    tech.appendChild(select(TECHS.indexOf(v.technique) >= 0 ? TECHS : [v.technique || ''].concat(TECHS), v.technique || '', 'technique', '技法', !edit));
    $('[data-f="name"]', tr).appendChild(select(Object.keys(PRIORITY), v.priority || 'medium', 'priority', '優先度', !edit, PRIORITY));
    dec.value = v.decision; dec.disabled = !edit; rs.value = v.reason || ''; rs.disabled = !edit;
    $('[data-f="unverified"]', tr).hidden = !v.unverified;
    return tr;
  }
  function addRow() {
    var tr = document.createElement('tr'), td = document.createElement('td'), f = document.createElement('form');
    var mk = function (name, ph) { var i = document.createElement('input'); i.name = name; i.maxLength = 200; i.placeholder = ph; i.setAttribute('aria-label', ph); return i; };
    var bt = function (type, cls, label, act) { var b = document.createElement('button'); b.type = type; b.className = cls; b.textContent = label; if (act) b.dataset.act = act; return b; };
    td.colSpan = 6; f.id = 'bs-vp-addform'; f.className = 'bs-row';
    [mk('name', '観点（例: 締め日が月末の土日にあたる）'), select(TECHS, TECHS[2], 'technique', '技法'), mk('basis', '根拠（例: 仕様書 3.2 締め日の規則）'),
      bt('submit', 'btn sm pri', '追加する'), bt('button', 'btn sm ghost', 'やめる', 'vp-add-cancel')].forEach(function (el) { f.appendChild(el); });
    td.appendChild(f); tr.appendChild(td); return tr;
  }
  function changeVp(t) {
    var tr = t.closest('[data-vp]');
    if (!tr) return;
    var dec = $('[data-f="decision"]', tr).value, rs = $('[data-f="reason"]', tr), reason = rs.value.trim(), body = { decision: dec, reason: reason };
    if (t.dataset.field) body = { decision: dec === 'emit' || dec === 'adopted' ? 'edited' : dec, reason: reason, value: obj(t.dataset.field, t.value) };
    else if (REASON_NEEDED[dec] && !reason) { notify('対象外・破棄には理由が要ります。理由の欄に 1 行書くと保存します。', '理由を書いてください'); rs.focus(); return; }
    run(null, api('PATCH', jobPath('/stages/3/items/' + encodeURIComponent(tr.dataset.vp)), body), '観点を更新しました');
  }

  /* ---- 段階 4 ケース表 ---- */
  function summary(j, c) {
    var o = c.oracle || {}, sums = (j.code && j.code.summaries) || {};
    if (c.summary || sums[c.id]) return c.summary || sums[c.id];
    return (c.pre ? '「' + text(c.pre) + '」の状態で、' : '') + ((c.steps || []).length ? c.steps.length + ' つの手順を行い、' : '')
      + '期待値を「' + (METHODS[o.method] || '未設定の方法') + '」で確かめます。' + (o.alt_sql_ja ? '別の計算: ' + o.alt_sql_ja : '');
  }
  function oracleRow(c) {
    var o = c.oracle || {}, tr = document.createElement('tr'), td = document.createElement('td');
    var f = document.getElementById('bs-tpl-oracle').content.firstElementChild.cloneNode(true), E = function (n) { return f.elements.namedItem(n); };
    f.dataset.case = c.id; E('method').value = o.method || 'db_diff'; E('key').value = (o.key || []).join(', '); E('exclude').value = (o.exclude || []).join(', ');
    E('tolerance').value = typeof o.tolerance === 'string' ? o.tolerance : text(o.tolerance);
    $('[data-f="warn"]', f).textContent = text(o.warnings || []);
    td.colSpan = 8; td.appendChild(f); tr.appendChild(td); return tr;
  }
  renderers[4] = function (j) {
    var cases = j.cases || [], senior = isSenior(), body = $('#bs-cases'), cnt = { auto: 0, human: 0, unconfirmed: 0 };
    if (!cases.length) noneRow(body, 8, 'まだケースがありません。観点表を承認してから「ケースを作る」を押してください。'); else body.innerHTML = '';
    cases.forEach(function (c) {
      var o = c.oracle || {}, sk = ORACLE_ST[o.state] ? o.state : 'unconfirmed';
      var tr = fill('bs-tpl-case', { id: c.id, viewpoint: c.viewpoint, pre: c.pre, expected: c.expected, method: METHODS[o.method] || '未設定', summary: summary(j, c) });
      var ol = $('[data-f="steps"]', tr), sql = $('[data-f="sql"]', tr), pill = $('[data-f="state"]', tr), b = $('[data-act="oracle"]', tr);
      cnt[sk]++; tr.dataset.case = c.id;
      (c.steps || []).forEach(function (s) { ol.appendChild(li('', text(s))); });
      sql.textContent = o.alt_sql || ''; sql.hidden = !o.alt_sql;
      pill.textContent = ORACLE_ST[sk][0]; pill.className = 'pill ' + ORACLE_ST[sk][1];
      b.hidden = !senior || sk !== 'unconfirmed'; b.dataset.case = c.id;
      body.appendChild(tr);
      if (state.oracleFor === c.id) body.appendChild(oracleRow(c));
    });
    kpis($('#bs-case-kpis'), [[cases.length, 'ケース'], [cnt.auto, '機械が判定', cnt.auto ? 'ok' : ''], [cnt.human, '人が確定'],
      [cnt.unconfirmed, senior ? '確定待ち' : '確定待ち（シニア QA が確定）', cnt.unconfirmed ? 'wa' : '']]);
  };
  function submitOracle(f) {
    var E = function (n) { return f.elements.namedItem(n); };
    var split = function (s) { return s.split(/[,、]/).map(function (x) { return x.trim(); }).filter(Boolean); };
    var method = E('method').value, key = split(E('key').value);
    if (method === 'db_diff' && !key.length) { notify('行を突き合わせる列が空です。例のように列名をカンマで区切って入れてください。', '確定できませんでした'); E('key').focus(); return; }
    var body = { method: method, config: { key: key, exclude: split(E('exclude').value), tolerance: E('tolerance').value.trim() }, confirm: true };
    run(f.querySelector('[type=submit]'), api('PATCH', jobPath('/cases/' + encodeURIComponent(f.dataset.case) + '/oracle'), body), '期待値を確定しました')
      .then(function (d) { if (d && d.job) { state.oracleFor = ''; renderPanel(); } });
  }

  /* ---- 段階 5 テストデータ仕様 ---- */
  renderers[5] = function (j) {
    var ds = j.data_specs || [], body = $('#bs-data-specs');
    if (!ds.length) return noneRow(body, 8, 'まだデータ仕様がありません。ケース表を承認してから「データ仕様を作る」を押してください。');
    body.innerHTML = '';
    ds.forEach(function (d) {
      body.appendChild(fill('bs-tpl-dataspec', { id: d.id, case: d.case, table: d.table, conditions: d.conditions, rows: d.rows,
        encoding: d.encoding, mask: (d.mask_cols || []).length ? d.mask_cols : 'なし', basis: d.basis }));
    });
  };

  /* ---- 段階の操作（生成・承認・差し戻し・取消） ---- */
  function generate(btn) {
    var n = +btn.dataset.stage, approved = stageOf(state.job, n).status === 'approved';
    return run(btn, api('POST', jobPath('/stages/' + n + '/generate')), approved ? '承認済みのため内容は変えず、変更の候補として受け付けました' : '作りました。内容を確かめてください');
  }
  function approve(btn) {
    var n = state.stage, st = stageOf(state.job, n);
    var first = n === 1 && st.status !== 'generated' ? api('POST', jobPath('/stages/1/generate')) : Promise.resolve({ job: state.job });
    var p = first.then(function (d) { return api('POST', jobPath('/stages/' + n + '/approve'), { version: stageOf(d.job, n).version }); });
    return run(btn, p, '段階 ' + n + ' を承認しました').then(function (d) { if (d && d.job && n < 8) showStage(n + 1); });
  }
  function reject(btn) {
    var r = $('#bs-reject-reason'), reason = r.value.trim();
    if (!reason) { notify('差し戻す理由が空です。何を直してほしいかを 1 行で書いてください。', '理由を書いてください'); r.focus(); return; }
    run(btn, api('POST', jobPath('/stages/' + state.stage + '/reject'), { reason: reason, comments: {} }), '差し戻しました')
      .then(function (d) { if (d && d.job) r.value = ''; });
  }

  /* ---- イベント ---- */
  function openNew() { $('#bs-newform').hidden = false; $('#bs-newname').focus(); }
  var CLICK = {
    'bs-new': openNew, 'bs-empty-new': openNew, 'bs-newcancel': function () { $('#bs-newform').hidden = true; },
    'bs-approve-btn': approve, 'bs-reject': reject,
    'bs-revert': function (t) { run(t, api('POST', jobPath('/stages/' + state.stage + '/revert')), '前の版に戻しました'); },
    'bs-vp-add': function () { state.adding = true; renderPanel(); var i = $('#bs-vp-addform input'); if (i) i.focus(); },
    'bs-banner-retry': function () { return state.job ? openJob(state.job.id, state.stage) : loadJobs(); }
  };
  document.addEventListener('click', function (e) {
    var t = e.target.closest('button, [data-job]'), act = t && t.dataset.act;
    if (!t || t.disabled) return;
    if (t.dataset.job) return openJob(t.dataset.job);
    if (t.dataset.stage && t.closest('#bs-nav')) return showStage(t.dataset.stage);
    if (t.dataset.level) return patch({ level: t.dataset.level }, 'テストレベルを保存しました');
    if (act === 'generate' && +t.dataset.stage <= 6) return generate(t);
    if (act === 'file-del') return run(t, api('DELETE', jobPath('/files/' + encodeURIComponent(t.dataset.file))), '資料を取り除きました');
    if (act === 'oracle' || act === 'oracle-cancel') { state.oracleFor = act === 'oracle' ? t.dataset.case : ''; return renderPanel(); }
    if (act === 'vp-add-cancel') { state.adding = false; return renderPanel(); }
    if (CLICK[t.id]) CLICK[t.id](t);
  });
  document.addEventListener('keydown', function (e) {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('[data-job]')) { e.preventDefault(); openJob(e.target.dataset.job); }
  });
  function submitNew(f) {
    var name = $('#bs-newname').value.trim();
    if (!name) return notify('案件名が空です。テストするバッチの名前を入れてください。', '作成できませんでした');
    run(f.querySelector('[type=submit]'), api('POST', API, { name: name, target_kind: 'batch', level: 'system', purpose: '', scope: '' }), '案件を作りました')
      .then(function (d) { if (d && d.job) { f.hidden = true; $('#bs-newname').value = ''; showStage(1); } });
  }
  function submitVp(f) {
    var name = f.elements.namedItem('name').value.trim();
    if (!name) return notify('観点が空です。確かめたいことを 1 行で書いてください。', '追加できませんでした');
    var item = { name: name, technique: f.querySelector('[data-field="technique"]').value, basis: f.elements.namedItem('basis').value.trim() };
    run(f.querySelector('[type=submit]'), api('POST', jobPath('/stages/3/items'), { item: item }), '観点を追加しました')
      .then(function (d) { if (d && d.job) { state.adding = false; renderPanel(); } });
  }
  document.addEventListener('submit', function (e) {
    var f = e.target, fn = f.id === 'bs-newform' ? submitNew : f.id === 'bs-vp-addform' ? submitVp : f.classList.contains('bs-oracle') ? submitOracle : null;
    if (fn) { e.preventDefault(); fn(f); }
  });
  document.addEventListener('change', function (e) {
    var t = e.target;
    if (!state.job || t.closest('#bs-vp-addform')) return;
    if (t.id === 'bs-file') { upload(t.files); t.value = ''; return; }
    if (t.dataset.f === 'kind' && t.dataset.file) return run(null, api('PATCH', jobPath('/files/' + encodeURIComponent(t.dataset.file)), { kind: t.value }), '資料の種類を変えました');
    if (t.closest('#bs-stage-1')) return changeS1(t);
    if (t.closest('#bs-stage-3')) changeVp(t);
  });
  var drop = $('#bs-drop');
  ['dragenter', 'dragover'].forEach(function (n) { drop.addEventListener(n, function (e) { e.preventDefault(); drop.classList.add('over'); }); });
  ['dragleave', 'drop'].forEach(function (n) { drop.addEventListener(n, function (e) { e.preventDefault(); drop.classList.remove('over'); }); });
  drop.addEventListener('drop', function (e) { upload(e.dataTransfer.files); });
  $('#bs-q').addEventListener('input', renderJobs);
  window.addEventListener('hashchange', function () { var m = /^#s([1-8])$/.exec(location.hash); if (m && state.job) showStage(m[1]); });

  /* 段階 6〜8 の担当（backend-test-run.js）が使う共通の入口。role は setJob のたびに更新する文字列 */
  Object.assign(NS, {
    api: api, run: run, notify: notify, toast: toast, fill: fill, text: text, kpis: kpis, noneRow: noneRow, li: li, fmtTime: fmtTime,
    fmtSize: fmtSize, jobPath: jobPath, stageOf: stageOf, isSenior: isSenior, showStage: showStage, setJob: setJob, generate: generate, role: '',
    job: function () { return state.job; }, stage: function () { return state.stage; },
    refresh: function () { return state.job ? openJob(state.job.id, state.stage) : loadJobs(); },
    register: function (n, fn) { renderers[n] = fn; if (state.job && state.stage === +n) renderPanel(); }
  });

  /* 利用者名は承認可否の判定にだけ使う。取れないときは案件側の my_role に任せる */
  function loadMe() {
    return fetch('/api/auth/me', { credentials: 'same-origin' }).then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (d) { var u = (d && d.user) || {}; state.me = u.username || u.email || u.id || ''; })
      .catch(function (e) { console.warn('BackendTest: 利用者情報を取得できませんでした', e); });
  }
  var jid = new URLSearchParams(location.search).get('job'), hm = /^#s([1-8])$/.exec(location.hash);
  Promise.all([loadMe(), loadJobs()]).then(function () { if (jid) return openJob(jid, hm && hm[1]); renderAll(); });
})();
