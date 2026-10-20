/* バッチ・バックエンドのテスト（System 08）の画面: 段階 6 テストコード・7 実行・8 判定と書き出し。
 * API: /api/backend-test/jobs/<jid>/...（BD-008 5 章）。案件・段階ナビ・承認バーは backend-test.js が持つ。
 * 案件の受け取り: window.BackendTest.onJob／document の "bs:job" イベント（detail.job）／URL の ?job= の順。
 * 接続のパスワードは入力欄から要求本文に入れるだけで、変数に残さない。実行が終わると入力欄も空にする。 */
(function () { 'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };
  var API = '/api/backend-test/jobs';
  var POLL_MS = 2000;
  var ACTIVE = { queued: 1, running: 1 };
  var STATE_JA = { pass: '合格', fail: '不合格', undetermined: '判定できない', not_run: '未実行', error: '実行エラー',
    queued: '待機中', running: '実行中', done: '完了', cancelled: 'キャンセル', timeout: 'タイムアウト' };
  var PILL = { pass: 'p-pass', fail: 'p-fail', undetermined: 'p-flaky', not_run: 'p-new', error: 'p-fail',
    queued: 'p-running', running: 'p-running', done: 'p-pass', cancelled: 'p-new', timeout: 'p-fail' };
  var SEV_JA = { critical: '致命的', high: '高', medium: '中', low: '低' };
  var END_MSG = { done: '実行が終わりました。判定の段階で結果を確かめてください。',
    cancelled: 'キャンセルしました。終わったケースの結果は残っています。',
    timeout: '時間内に終わりませんでした。ケースを絞ってもう一度実行してください。',
    error: '実行が途中で止まりました。接続先とテストコードを確かめてから、まだ実行していないケースを実行してください。' };
  var S = { job: null, file: '', run: null, timer: 0, preview: null, pending: null };
  /* ---- 共通 ---- */
  function jid() { return (S.job && S.job.id) || new URLSearchParams(location.search).get('job') || ''; }
  function api(method, path, body) { var opt = { method: method, headers: {} };
    if (body) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    return fetch(API + '/' + encodeURIComponent(jid()) + path, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) { var er = new Error(d.error || '処理できませんでした（' + r.status + '）。時間をおいてもう一度お試しください。'); er.status = r.status; throw er; }
        return d; });
    }, function () { throw new Error('サーバにつながりません。画面を再読み込みしてください。'); }); }
  function showError(msg) { var b = $('#bs-banner'); if (!b) return toast(msg);
    var text = String(msg || ''), i = text.indexOf('。');
    $('#bs-banner-title').textContent = i >= 0 ? text.slice(0, i + 1) : text;
    $('#bs-banner-msg').textContent = '';
    $('#bs-banner-next').textContent = i >= 0 ? text.slice(i + 1) : '';
    $('#bs-banner-retry').hidden = true;
    b.hidden = false; }
  function clearError() { var b = $('#bs-banner'); if (b) b.hidden = true; }
  function toast(msg) { var t = $('#bs-toast'); if (!t) return;
    t.textContent = msg; t.hidden = false;
    clearTimeout(toast.id); toast.id = setTimeout(function () { t.hidden = true; }, 3000); }
  function busy(el, on) { if (el) { el.disabled = on; el.setAttribute('aria-busy', on ? 'true' : 'false'); } }
  function fill(tplId, values) { var node = document.getElementById(tplId).content.firstElementChild.cloneNode(true);
    Object.keys(values).forEach(function (k) { var sel = '[data-f="' + k + '"]', el = node.matches(sel) ? node : node.querySelector(sel);
      if (el && el.tagName !== 'SELECT' && el.tagName !== 'INPUT') el.textContent = values[k] == null ? '' : values[k]; });
    return node; }
  function pill(el, st) { el.className = 'pill ' + (PILL[st] || ''); el.textContent = STATE_JA[st] || st || '—'; }
  function fmtSec(s) { s = Math.max(0, Math.round(Number(s) || 0));
    return s >= 60 ? Math.floor(s / 60) + ' 分 ' + (s % 60) + ' 秒' : s + ' 秒'; }
  function caseById(cid) { return (S.job.cases || []).filter(function (c) { return c.id === cid; })[0] || null; }
  function caseName(cid) { var c = caseById(cid); if (!c) return '';
    var vp = (S.job.viewpoints || []).filter(function (v) { return v.id === c.viewpoint; })[0];
    return (vp && vp.name) || c.expected || ''; }
  function factText(f) { if (f == null) return '—';
    if (typeof f !== 'object') return String(f);
    var p = [];
    if (f.rc != null) p.push('終了コード ' + f.rc);
    ['added', 'removed', 'updated'].forEach(function (k, i) {
      var v = f[k]; if (v != null) p.push(['追加', '削除', '更新'][i] + ' ' + (Array.isArray(v) ? v.length : v) + ' 行'); });
    if (f.actual != null) p.push('実際の値 ' + f.actual);
    if (f.reason) p.push(f.reason);
    if (f.diff && !p.length) p.push('前後の差分を証跡に保存');
    return p.join('・') || '—'; }
  function setJob(job) { if (!job) return;
    S.job = job; render();
    var bt = window.BackendTest;
    if (bt && typeof bt.setJob === 'function') bt.setJob(job); }
  function onJob(job) { if (!job || job === S.job) return;
    if (S.job && S.job.id !== job.id) { stopPoll(); S.run = null; S.file = ''; }
    S.job = job; render(); }
  function loadJob() { if (!jid()) return Promise.resolve();
    return api('GET', '').then(function (d) { onJob(d.job || d); }).catch(function (e) { showError(e.message); }); }
  function render() { if (!S.job) return;
    renderCode(); renderRunSetup(); renderRun(); renderJudge(); renderExport();
    var last = (S.job.runs || []).slice(-1)[0];
    if (!S.run && last && ACTIVE[last.status]) { S.run = last; renderRun(); poll(); } }
  /* ---- 段階 6 テストコード ---- */
  function renderCode() { var code = S.job.code || {}, files = code.files || [];
    var st = (S.job.stages || {})['6'] || {};
    $('#bs-code-meta').textContent = files.length ? files.length + ' ファイル・版 ' + (st.version || 1) : 'まだ作っていません';
    if (!files.some(function (f) { return f.path === S.file; })) S.file = files[0] ? files[0].path : '';
    var tabs = $('#bs-code-tabs'); tabs.innerHTML = '';
    files.forEach(function (f) { var t = fill('bs-tpl-codetab', { path: f.path.replace(/^tests\//, '') });
      t.setAttribute('aria-selected', f.path === S.file ? 'true' : 'false');
      t.addEventListener('click', function () { S.file = f.path; renderCode(); });
      tabs.appendChild(t); });
    var cur = files.filter(function (f) { return f.path === S.file; })[0];
    $('#bs-code').textContent = !cur ? '「コードを作る」を押すと、承認したケース表からテストコードを作ります。'
      : (cur.text != null ? cur.text : 'このファイルの本文は、書き出しの「テストコード一式」で確かめられます。');
    renderSummary(code, cur);
    renderGate(code.gate || [], files.length);
    $('#bs-code-edit-open').hidden = !cur || cur.text == null || myRole() !== 'senior_qa'; }
  function myRole() { var bt = window.BackendTest;
    return S.job.my_role || (bt && typeof bt.role === 'function' ? bt.role() : bt && bt.role) || ''; }
  function renderSummary(code, cur) { var box = $('#bs-code-sum'); box.innerHTML = '';
    var map = code.map || {}, sums = code.summaries || {};
    var ids = Object.keys(sums).filter(function (cid) { if (!cur) return false;
      var test = map[cid] || '';
      return (cur.text && test && cur.text.indexOf(test) >= 0) || cur.path.toLowerCase().indexOf(cid.toLowerCase()) >= 0; });
    if (!cur) { box.textContent = 'コードを作ると、ここに各ケースが何を確かめるかを日本語で出します。'; return; }
    if (!ids.length && !/test_/.test(cur.path)) { box.textContent = '接続やデータ投入の共通部品です。期待値は含みません。'; return; }
    if (!ids.length) { box.textContent = 'このファイルのケースの要約はまだありません。ケース表の「日本語の要約」で確かめられます。'; return; }
    ids.forEach(function (cid) { var p = document.createElement('p'), b = document.createElement('b');
      b.textContent = cid + ' '; p.appendChild(b);
      p.appendChild(document.createTextNode(sums[cid] || '要約はまだありません。'));
      box.appendChild(p); }); }
  function renderGate(gate, nFiles) { var ul = $('#bs-gate'); ul.innerHTML = '';
    if (!nFiles) { ul.innerHTML = '<li class="bs-mut">コードを作ると、ここに確かめた結果が出ます。</li>'; return; }
    if (!gate.length) { ul.innerHTML = '<li>問題は見つかりませんでした。</li>'; return; }
    gate.forEach(function (g) { var li = document.createElement('li');
      var where = g.file ? '（' + g.file + (g.line ? ' ' + g.line + ' 行目' : '') + '）' : '';
      li.textContent = (typeof g === 'string' ? g : (g.message || g.text || g.rule || '')) + where;
      if (g.level === 'error' || g.blocking) li.className = 'bs-ng';
      ul.appendChild(li); }); }
  function bindCode() { $('#bs-code-edit-open').addEventListener('click', function () {
      var cur = (S.job.code.files || []).filter(function (f) { return f.path === S.file; })[0];
      $('#bs-code-text').value = cur ? cur.text : '';
      $('#bs-code-edit').hidden = false; $('#bs-code-text').focus(); });
    $('#bs-code-cancel').addEventListener('click', function () { $('#bs-code-edit').hidden = true; });
    $('#bs-code-edit').addEventListener('submit', function (e) { e.preventDefault(); clearError();
      var btn = e.target.querySelector('[type="submit"]'); busy(btn, true);
      api('PUT', '/code', { path: S.file, text: $('#bs-code-text').value }).then(function (d) {
        $('#bs-code-edit').hidden = true; setJob(d.job); toast('保存しました。確かめた結果を更新しました。');
      }).catch(function (er) { showError(er.message); }).then(function () { busy(btn, false); }); });
    if (window.BackendTest) return; // 再生成は共通部の「作る」に任せる
    $$('[data-act="generate"][data-stage="6"]').forEach(function (btn) { btn.addEventListener('click', function () { clearError(); busy(btn, true);
        api('POST', '/stages/6/generate').then(function (d) { setJob(d.job || d); toast('テストコードを作りました。'); })
          .catch(function (er) { showError(er.message); }).then(function () { busy(btn, false); }); }); }); }
  /* ---- 段階 7 実行 ---- */
  function envById(id) { return (S.job.envs || []).filter(function (e) { return e.id === id; })[0] || null; }
  function renderRunSetup() { var sel = $('#bs-env'), prev = sel.value, envs = S.job.envs || [];
    sel.innerHTML = '';
    envs.forEach(function (e) { var o = document.createElement('option'); o.value = e.id;
      o.textContent = e.name + (e.production ? '（本番らしい・読み取り専用）' : ''); sel.appendChild(o); });
    sel.value = envById(prev) ? prev : (S.job.current_env || (envs[0] && envs[0].id) || '');
    if (!$('#bs-bizdate').value) $('#bs-bizdate').value = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    var hasCode = ((S.job.code || {}).files || []).length > 0;
    $('#bs-run').disabled = !envs.length || !hasCode || !!(S.run && ACTIVE[S.run.status]);
    $('#bs-env-status').textContent = !envs.length ? '接続先がまだありません。下の「接続先を登録する」から登録してください。'
      : !hasCode ? 'テストコードがまだありません。テストコードの段階でコードを作ってください。' : '';
    renderProd(envById(sel.value)); }
  function renderProd(env, reasons) { var b = $('#bs-prod-banner'); if (!b) return;
    b.hidden = !(env && env.production);
    if (b.hidden) return;
    $('#bs-prod-env').textContent = env.name || '';
    var r = reasons || env.production_reasons || [];
    $('#bs-prod-reasons').textContent = r.length ? '判定の理由: ' + r.join('・') : ''; }
  function runBody() { var scope = $('#bs-run-scope').value;
    return { env_id: $('#bs-env').value, business_date: $('#bs-bizdate').value,
      case_ids: scope === 'remaining' ? 'remaining' : (S.job.cases || []).map(function (c) { return c.id; }) }; }
  function startRun() { clearError();
    var body = runBody(), btn = $('#bs-run');
    if (!body.env_id) return showError('接続先が選ばれていません。接続先を選んでから実行してください。');
    if (!body.business_date) return showError('業務日付が入っていません。業務日付を入れてから実行してください。');
    busy(btn, true);
    api('POST', '/runs/preview', Object.assign({}, body, { secret: $('#bs-secret').value })).then(function (d) { S.preview = d;
      renderProd({ name: d.env_name, production: d.production }, d.production_reasons);
      if (d.production && d.writes) { throw new Error('本番らしい接続先では、データを書き換える実行はできません。テスト用の接続先を選んでください。'); }
      if (!d.writes) return launch(body, null);
      openConfirm({ env: d.env_name, tables: d.affected_tables, action: function () { return launch(body, d.confirm_token); } });
    }).catch(function (e) { showError(e.message); if (e.status === 409) { var s = $('#bs-secret'); s.value = ''; s.focus(); } }).then(function () { busy(btn, false); renderRunSetup(); }); }
  function launch(body, token) { var payload = Object.assign({}, body, { secret: $('#bs-secret').value, confirm_token: token });
    $('#bs-secret').value = '';
    return api('POST', '/runs', payload).then(function (d) { S.run = d.run || d; renderRun(); renderRunSetup(); poll(); toast('実行を始めました。'); }); }
  function openConfirm(o) { var ul = $('#bs-confirm-tables'); ul.innerHTML = '';
    $('#bs-confirm-env').textContent = o.env || '';
    (o.tables || []).forEach(function (t) { var li = document.createElement('li'); li.textContent = t; ul.appendChild(li); });
    if (!(o.tables || []).length) ul.innerHTML = '<li>（テーブル名を特定できませんでした）</li>';
    $('#bs-confirm-check').checked = false; $('#bs-confirm-ok').disabled = true;
    S.opener = document.activeElement; S.pending = o; $('#bs-confirm').hidden = false; $('#bs-confirm-check').focus(); }
  // 閉じたら開いた元（実行する）へフォーカスを戻す
  function closeConfirm() { $('#bs-confirm').hidden = true; S.pending = null;
    // 確認は実行前の下見（非同期）の後に開くため、その間に元のボタンがフォーカスを失っていることがある
    var o = S.opener; S.opener = null;
    if (!(o && o.isConnected && o !== document.body && o.focus)) o = $('#bs-run');
    if (o && o.focus) o.focus(); }
  function stopPoll() { clearTimeout(S.timer); S.timer = 0; }
  function poll() { stopPoll();
    if (!S.run || !ACTIVE[S.run.status]) return;
    S.timer = setTimeout(function () { api('GET', '/runs/' + encodeURIComponent(S.run.id)).then(function (d) { S.run = d.run || d; renderRun();
        if (ACTIVE[S.run.status]) poll(); else finishRun();
      }).catch(function (e) { showError(e.message + ' 画面を再読み込みすると、実行の続きを表示します。'); });
    }, POLL_MS); }
  function finishRun() { stopPoll(); $('#bs-secret').value = '';
    toast(END_MSG[S.run.status] || '実行が終わりました。');
    // 判定は段階 7 の承認後（backend-test.js の approve）に行う。ここでは結果を読み直し、
    // 承認の可否と結果表を持つ本体（backend-test.js）にも読み直させる
    loadJob().then(function () { document.dispatchEvent(new CustomEvent('bs:run-finished')); }); }
  function renderRun() { var r = S.run, card = $('#bs-run-card');
    card.hidden = !r;
    if (r) { var on = !!ACTIVE[r.status], pg = r.progress || {}, done = pg.done || 0, total = pg.total || 0;
      var pct = total ? Math.round(done * 100 / total) : 0;
      $('#bs-run-title').textContent = on ? '実行中' : '実行 ' + (STATE_JA[r.status] || r.status);
      pill($('#bs-run-count'), r.status); $('#bs-run-count').textContent = done + ' / ' + total + ' 件';
      $('#bs-run-bar').style.width = pct + '%'; $('#bs-run-prog').setAttribute('aria-valuenow', String(pct));
      $('#bs-run-env').textContent = '接続先: ' + (r.env_name || r.env || '');
      var t0 = Date.parse(r.started_at), t1 = r.ended_at ? Date.parse(r.ended_at) : Date.now();
      $('#bs-run-elapsed').textContent = isNaN(t0) ? '' : '経過 ' + fmtSec((t1 - t0) / 1000);
      $('#bs-run-current').textContent = on && pg.current ? '実行中のケース: ' + pg.current : '';
      $('#bs-run-cancel').hidden = !on;
      $('#bs-rollback').hidden = on || !r.can_rollback; }
    renderRunRows(r); }
  function renderRunRows(r) { var rows = (r && (r.results || r.partial)) ||
      (S.job.results || []).filter(function (x) { return r && x.run === r.id; });
    var tb = $('#bs-run-rows'); tb.innerHTML = '';
    var count = {};
    rows.forEach(function (x) { count[x.state] = (count[x.state] || 0) + 1;
      var tr = fill('bs-tpl-run', { id: x.case, name: caseName(x.case),
        time: x.duration != null ? fmtSec(x.duration) : '—', actual: x.actual != null ? x.actual : factText(x.fact) });
      pill(tr.querySelector('[data-f="state"]'), x.state); tb.appendChild(tr); });
    $('#bs-run-none').hidden = rows.length > 0;
    $('#bs-run-summary').textContent = rows.length ? Object.keys(count).map(function (k) { return (STATE_JA[k] || k) + ' ' + count[k];
    }).join('・') : ''; }
  // 接続先の登録（POST /envs）。パスワードは接続確認にだけ使われ、サーバは保存しない
  function bindEnvAdd() { var f = $('#bs-envadd-form'); if (!f) return;
    f.addEventListener('submit', function (e) { e.preventDefault();
      var v = function (n) { return (f.elements.namedItem(n).value || '').trim(); }, st = $('#bs-envadd-status');
      var body = { name: v('name'), declared_production: f.elements.namedItem('declared_production').checked,
        db: { host: v('host'), port: Number(v('port') || 5432), dbname: v('dbname'), user: v('user') } };
      if (v('password')) body.password = v('password');
      st.textContent = '登録しています…';
      api('POST', '/envs', body).then(function (d) {
        var c = d && d.check; f.elements.namedItem('password').value = '';
        st.textContent = '登録しました。' + (c ? (c.reachable && c.auth ? '接続を確かめました。' : '接続できませんでした: ' + (c.message || '到達または認証に失敗しました')) : 'パスワードが無いため接続はまだ確かめていません。');
        loadJob(); })
        .catch(function (err) { st.textContent = '登録できませんでした: ' + err.message; }); }); }
  function bindRun() { bindEnvAdd(); $('#bs-env').addEventListener('change', function () { renderProd(envById(this.value)); });
    $('#bs-run').addEventListener('click', startRun);
    $('#bs-env-check').addEventListener('click', function () { var btn = this, eid = $('#bs-env').value; clearError();
      if (!eid) return showError('接続先が選ばれていません。接続先を選んでから確かめてください。');
      busy(btn, true); $('#bs-env-status').textContent = '確かめています…';
      api('POST', '/envs/' + encodeURIComponent(eid) + '/check', { secret: $('#bs-secret').value }).then(function (d) {
        $('#bs-env-status').textContent = d.message || (d.reachable ? 'つながりました。' : 'つながりませんでした。');
        renderProd({ name: (envById(eid) || {}).name, production: d.production }, d.production_reasons);
      }).catch(function (e) { $('#bs-env-status').textContent = ''; showError(e.message); })
        .then(function () { busy(btn, false); }); });
    $('#bs-run-cancel').addEventListener('click', function () { var btn = this; busy(btn, true);
      api('POST', '/runs/' + encodeURIComponent(S.run.id) + '/cancel').then(function (d) {
        S.run = d.run || d; renderRun(); if (!ACTIVE[S.run.status]) finishRun();
      }).catch(function (e) { showError(e.message); }).then(function () { busy(btn, false); }); });
    $('#bs-rollback').addEventListener('click', function () { var r = S.run;
      openConfirm({ env: r.env_name || r.env, tables: (S.preview || {}).affected_tables, action: function () {
        return api('POST', '/rollback', { env_id: r.env, run_id: r.id, secret: $('#bs-secret').value,
          confirm_token: (S.preview || {}).confirm_token }).then(function (d) {
          toast(d.match === false ? '戻しましたが、実行前と一致しない行があります。証跡を確かめてください。' : '実行前の状態に戻しました。'); });
      } }); });
    $('#bs-confirm-check').addEventListener('change', function () { $('#bs-confirm-ok').disabled = !this.checked; });
    $('#bs-confirm-cancel').addEventListener('click', closeConfirm);
    $('#bs-confirm-ok').addEventListener('click', function () { var p = S.pending; closeConfirm(); if (!p) return;
      Promise.resolve(p.action()).catch(function (e) { showError(e.message); }); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !$('#bs-confirm').hidden) closeConfirm(); }); }
  /* ---- 段階 8 判定・報告 ---- */
  function latestResults() { var by = {};
    (S.job.results || []).forEach(function (r) { by[r.case] = r; });
    return Object.keys(by).sort().map(function (k) { return by[k]; }); }
  function unverifiedItems(latest) { if (Array.isArray(S.job.unverified)) return S.job.unverified.map(function (u) { return u.text || String(u); });
    var seen = {}, out = [];
    latest.forEach(function (r) { seen[r.case] = 1;
      if (r.state === 'not_run' || r.state === 'undetermined' || r.state === 'error') {
        out.push(r.case + ': ' + STATE_JA[r.state] + (r.cause ? '（' + r.cause + '）' : '')); } });
    (S.job.cases || []).forEach(function (c) { if (!seen[c.id]) out.push(c.id + ': まだ実行していません');
      if (c.oracle && c.oracle.state === 'unconfirmed') out.push(c.id + ': 期待値が確定していません'); });
    (S.job.viewpoints || []).forEach(function (v) {
      if (v.unverified && v.decision !== 'excluded' && v.decision !== 'discarded') out.push('観点 ' + v.id + ' ' + v.name + ': 根拠を確かめていません'); });
    return out; }
  function renderKpis(latest, uv, candidates) { var c = {}; latest.forEach(function (r) { c[r.state] = (c[r.state] || 0) + 1; });
    var tiles = [[uv.length, '未検証', uv.length ? 'wa' : '', 'この結果では確かめていないこと', 'eye'], [c.pass || 0, '合格', c.pass ? 'ok' : '', '期待値どおりだったケース', 'pass'],
      [c.fail || 0, '不合格', c.fail ? 'ng' : '', '期待値と違ったケース', 'fail'], [c.undetermined || 0, '判定できない', '', '期待値が決まらず判定できない', 'help'],
      [(c.not_run || 0) + (c.error || 0), '未実行・実行エラー', '', '実行していない・途中で止まった', 'minus'], [candidates.length, '不具合候補', candidates.length ? 'wa' : '', '記録を検討する不一致', 'flag']];
    var box = $('#bs-result-kpis'), bt = window.BackendTest;
    if (bt && bt.kpis) return bt.kpis(box, tiles);
    box.innerHTML = ''; tiles.forEach(function (t) { var d = document.createElement('div'); d.className = 'stat-card'; d.textContent = t[1] + ' ' + t[0]; box.appendChild(d); }); }
  function renderFacts(latest) { var f = $('#bs-judge-facts'), h = $('#bs-judge-human'); f.innerHTML = ''; h.innerHTML = '';
    var last = (S.job.runs || []).slice(-1)[0];
    var add = function (ul, text) { var li = document.createElement('li'); li.textContent = text; ul.appendChild(li); };
    if (last) add(f, '最後の実行 ' + last.id + '・接続先 ' + (last.env_name || last.env) + '・業務日付 ' + (last.business_date || '—') + '・' + (STATE_JA[last.status] || last.status));
    latest.forEach(function (r) { add(f, r.case + ': ' + factText(r.fact) + (r.auto && r.auto.verdict ? ' → 機械の判定 ' + (STATE_JA[r.auto.verdict] || r.auto.verdict) : '')); });
    if (!latest.length) add(f, 'まだ実行していません。実行の段階で実行してください。');
    latest.filter(function (r) { return r.human && r.human.verdict; }).forEach(function (r) {
      add(h, r.case + ': ' + STATE_JA[r.human.verdict] + (r.human.reason ? ' — ' + r.human.reason : '') + (r.human.by ? '（' + r.human.by + '）' : '')); });
    if (!h.children.length) add(h, '人の判断はまだありません。機械が判定できないケースは、下の表で判断を入れてください。'); }
  function renderResults(latest) { var tb = $('#bs-results'); tb.innerHTML = '';
    latest.forEach(function (r) {
      var auto = r.auto && r.auto.verdict ? (STATE_JA[r.auto.verdict] || r.auto.verdict) + (r.auto.rule ? '（' + r.auto.rule + '）' : '') : '—';
      var tr = fill('bs-tpl-result', { id: r.case, name: caseName(r.case), fact: factText(r.fact), auto: auto });
      var sel = tr.querySelector('[data-f="human"]'), rsn = tr.querySelector('[data-f="reason"]');
      sel.value = (r.human && r.human.verdict) || ''; rsn.value = (r.human && r.human.reason) || '';
      var send = function () {
        api('PATCH', '/results/' + encodeURIComponent(r.run) + '/' + encodeURIComponent(r.case), { verdict: sel.value || null, reason: rsn.value })
          .then(function (d) { setJob(d.job); toast(r.case + ' の判断を保存しました。'); }).catch(function (e) { showError(e.message); }); };
      sel.addEventListener('change', send); rsn.addEventListener('change', send);
      pill(tr.querySelector('[data-f="state"]'), r.state); tb.appendChild(tr); }); }
  function renderDefects(latest, candidates) { var tb = $('#bs-defects'); tb.innerHTML = '';
    (S.job.defects || []).forEach(function (d) {
      var tr = fill('bs-tpl-defect', { id: d.id, title: d.title, severity: SEV_JA[d.severity] || d.severity, case: d.case });
      tr.querySelector('[data-f="severity"]').classList.add(d.severity || 'medium'); tb.appendChild(tr); });
    candidates.forEach(function (r) { var tr = fill('bs-tpl-defect', { id: '—', title: '不合格のケース（まだ記録していません）', severity: '—', case: r.case });
      var st = tr.querySelector('[data-f="state"]'); st.className = 'pill p-flaky'; st.textContent = '候補';
      tr.tabIndex = 0; tr.title = '押すと、このケースで不具合を記録します';
      tr.addEventListener('click', function () { openDefect(r.case); }); tb.appendChild(tr); });
    var sel = $('#bs-defect-form [name="case_id"]'); sel.innerHTML = '';
    latest.forEach(function (r) { var o = document.createElement('option'); o.value = r.case;
      o.textContent = r.case + '（' + (STATE_JA[r.state] || r.state) + '）'; sel.appendChild(o); }); }
  function openDefect(cid) { var f = $('#bs-defect-form');
    if (!f.case_id.options.length) return showError('不具合を記録できるケースがありません。先に実行してください。');
    f.hidden = false; if (cid) f.case_id.value = cid; f.title.focus(); }
  function renderJudge() { var latest = latestResults(), uv = unverifiedItems(latest);
    var recorded = {}; (S.job.defects || []).forEach(function (d) { recorded[d.case] = 1; });
    var candidates = latest.filter(function (r) { return r.state === 'fail' && !recorded[r.case]; });
    renderKpis(latest, uv, candidates); renderFacts(latest); renderResults(latest); renderDefects(latest, candidates);
    renderUnverified(uv); }
  /* 未検証: 件数と理由別チップを先頭に、一覧は既定で折りたたみ（開くと高さ固定の内側スクロール） */
  function renderUnverified(uv) { var ul = $('#bs-unverified'), box = $('#bs-uv-box');
    if (!box) { box = document.createElement('div'); box.id = 'bs-uv-box'; ul.parentNode.appendChild(box); }
    var wasOpen = !!box.querySelector('.bs-uv-table:not([hidden])'); box.innerHTML = '';
    if (!uv.length) { ul.hidden = false; ul.innerHTML = ''; var li0 = document.createElement('li');
      li0.textContent = '確かめていない項目はありません。'; ul.appendChild(li0); return; }
    ul.hidden = true; ul.innerHTML = '';
    var rows = [], order = [], cnt = {};
    uv.forEach(function (t) { var m = /^([^:：\s]+)[:：]\s*(.*)$/.exec(t), id = m ? m[1] : '—', rsn = m ? m[2] : t;
      var key = rsn.replace(/[（(].*$/, '').trim() || rsn;
      if (!(key in cnt)) { cnt[key] = 0; order.push(key); } cnt[key]++; rows.push([id, rsn, key]); });
    var head = document.createElement('p'); head.className = 'bs-uv-head';
    head.textContent = '未検証 ' + uv.length + ' 件 — 合格には数えません'; box.appendChild(head);
    var chips = document.createElement('div'); chips.className = 'bs-uv-chips';
    order.sort(function (a, b) { return cnt[b] - cnt[a]; }).forEach(function (k) { var c = document.createElement('span');
      c.className = 'bs-uv-chip'; c.textContent = k + ' ' + cnt[k] + ' 件'; chips.appendChild(c); });
    box.appendChild(chips);
    var btn = document.createElement('button'); btn.type = 'button'; btn.className = 'btn btn-sm bs-uv-toggle';
    var wrap = document.createElement('div'); wrap.className = 'bs-uv-table'; wrap.hidden = !wasOpen;
    var table = document.createElement('table'); table.className = 'bs-table';
    var thead = document.createElement('thead'), hr = document.createElement('tr');
    ['ID', 'ケース名', '理由'].forEach(function (h) { var th = document.createElement('th'); th.textContent = h; hr.appendChild(th); });
    thead.appendChild(hr); table.appendChild(thead);
    var tb = document.createElement('tbody');
    rows.forEach(function (r) { var tr = document.createElement('tr');
      [r[0], r[0] === '—' ? '—' : (caseName(r[0]) || '—'), r[1]].forEach(function (v) { var td = document.createElement('td');
        td.textContent = v; tr.appendChild(td); }); tb.appendChild(tr); });
    table.appendChild(tb); wrap.appendChild(table);
    var label = function () { btn.textContent = wrap.hidden ? '一覧を表示（' + uv.length + ' 件）' : '一覧を閉じる'; };
    btn.setAttribute('aria-expanded', String(!wrap.hidden)); label();
    btn.addEventListener('click', function () { wrap.hidden = !wrap.hidden; btn.setAttribute('aria-expanded', String(!wrap.hidden)); label(); });
    box.appendChild(btn); box.appendChild(wrap); }
  function bindJudge() { $('#bs-defect-open').addEventListener('click', function () { openDefect(''); });
    $('#bs-defect-cancel').addEventListener('click', function () { $('#bs-defect-form').hidden = true; });
    $('#bs-defect-form').addEventListener('submit', function (e) { e.preventDefault(); clearError();
      var f = e.target, cid = f.case_id.value, btn = f.querySelector('[type="submit"]');
      var r = latestResults().filter(function (x) { return x.case === cid; })[0];
      busy(btn, true);
      api('POST', '/defects', { run_id: r ? r.run : '', case_id: cid, severity: f.severity.value, priority: f.priority.value, title: f.title.value.trim() })
        .then(function (d) { f.reset(); f.hidden = true; setJob(d.job); toast('不具合を記録しました。'); })
        .catch(function (er) { showError(er.message); }).then(function () { busy(btn, false); }); }); }
  /* ---- 書き出し（URL は /api/backend-test/jobs/<jid>/export/<kind>） ---- */
  function exportUrl(kind) { var last = (S.job.runs || []).slice(-1)[0];
    var url = API + '/' + encodeURIComponent(jid()) + '/export/' + encodeURIComponent(kind);
    return kind === 'evidence.zip' ? (last ? url + '?run=' + encodeURIComponent(last.id) : '') : url; }
  function renderExport() { $$('[data-export]').forEach(function (a) { var url = exportUrl(a.getAttribute('data-export'));
      if (url) { a.href = url; a.removeAttribute('aria-disabled'); a.removeAttribute('title'); }
      else { a.removeAttribute('href'); a.setAttribute('aria-disabled', 'true'); a.title = '実行の証跡は、実行したあとに書き出せます'; } }); }
  function bindExport() { $$('[data-export]').forEach(function (a) { a.addEventListener('click', function (e) {
        e.preventDefault(); if (!a.href) return; clearError();
        fetch(a.href).then(function (r) { if (r.ok) return r.blob().then(function (b) {
            var u = URL.createObjectURL(b), tmp = document.createElement('a');
            tmp.href = u; tmp.download = a.getAttribute('data-export'); document.body.appendChild(tmp); tmp.click();
            tmp.remove(); setTimeout(function () { URL.revokeObjectURL(u); }, 1000); });
          return r.json().catch(function () { return {}; }).then(function (d) {
            throw new Error(d.error || '書き出せませんでした（' + r.status + '）。時間をおいてもう一度お試しください。'); });
        }, function () { throw new Error('サーバにつながりません。画面を再読み込みしてください。'); })
          .catch(function (er) { showError(er.message); }); }); }); }
  /* ---- 起動 ---- */
  function init() { if (!$('#bs-stage-6')) return;
    bindCode(); bindRun(); bindJudge(); bindExport();
    document.addEventListener('bs:job', function (e) { onJob(e.detail && (e.detail.job || e.detail)); });
    window.BackendTestRun = { setJob: onJob, refresh: loadJob, stop: stopPoll };
    var bt = window.BackendTest;
    if (bt && typeof bt.onJob === 'function') bt.onJob(onJob);
    var initial = bt && (typeof bt.job === 'function' ? bt.job() : bt.job || (bt.state && bt.state.job));
    if (initial) onJob(initial); else if (!bt) loadJob();
    document.addEventListener('click', function (e) { var n = e.target.closest && e.target.closest('.bs-nav [data-stage]');
      if (n && Number(n.getAttribute('data-stage')) >= 6 && !S.job) loadJob(); }); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
