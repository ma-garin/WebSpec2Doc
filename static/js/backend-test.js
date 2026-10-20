/* バッチ・バックエンドのテスト（System 08）の画面。API: /api/backend-test/jobs（BD-008 5 章）。
 * ここで描くのは 案件一覧・段階ナビ・承認バー・段階 1〜5（段階 6 の「作る」も受ける）。段階 7・8 などは
 * backend-test-run.js（window.BackendTestRun）が描く。案件の更新は 'bs:job' イベントで知らせる。
 * 表示は ホーム／実行履歴／観点カタログ／案件。URL ハッシュは #job=<id>&stage=<n>・#runs・#catalog。 */
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
  var ORACLE_ST = { auto: ['機械判定', 'badge-info'], human: ['人が確定', 'badge-low'], unconfirmed: ['確定待ち', 'badge-high'] };
  var TECHS = ['同値分割法（5.2.1）', '分類木法（5.2.2）', '境界値分析（5.2.3）', '構文テスト（5.2.4）', '組合せテスト（5.2.5）', 'デシジョンテーブルテスト（5.2.6）',
    '原因結果グラフ（5.2.7）', '状態遷移テスト（5.2.8）', 'シナリオテスト（5.2.9）', 'ランダムテスト（5.2.10）', 'メタモルフィックテスト（5.2.11）', '要件ベーステスト（5.2.12）', '技法なし（経験ベース）'];
  /* 優先度は案件の値の種類（MoSCoW か 高中低）に合わせて選択肢を出す */
  var PRI_SETS = [{ Must: '必須', Should: '推奨', Could: '余力があれば', "Won't": '今回は見送り' }, { high: '高', medium: '中', low: '低' }];
  var KIND_LABEL = { table: 'テーブル', column: '列', constraint: '制約', jobarg: 'ジョブの引数', io: '入出力', rc: '終了コード', commit: 'コミット', rule: '業務ルール', formula: '計算式', date_rule: '日付の規則' };
  var REASON_NEEDED = { excluded: 1, discarded: 1 };
  var RANK = { qa: 1, senior_qa: 2 };
  var LOCK = '<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.6" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>';
  var state = { jobs: [], job: null, stage: 1, me: '', role: '', meAsked: false, adding: false, oracleFor: '', detailFor: '', view: 'home', summary: null };
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
    return p.then(function (d) { if (d && d.my_role) state.role = d.my_role; if (d && d.job) setJob(d.job); if (okMsg) toast(okMsg); return d; })
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
  /* KPI は System 01 と同じ部品（アイコン・見出し・数・補足）。k = [数, 見出し, 'ok'|'wa'|'ng'|'', 補足, アイコン名] */
  var ICONS = {
    file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>',
    check: '<path d="M9 11l3 3 8-8"/><path d="M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.4a2.5 2.5 0 1 1 3.2 2.4c-.6.2-.8.7-.8 1.4"/><path d="M12 16.6h.01"/>',
    warn: '<path d="M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>',
    list: '<path d="M4 6h16M4 12h16M4 18h10"/>',
    cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    pass: '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>',
    fail: '<circle cx="12" cy="12" r="9"/><path d="M15 9l-6 6M9 9l6 6"/>',
    minus: '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>',
    flag: '<path d="M5 21V4h11l-2 4 2 4H5"/>',
    folder: '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2.5h8.5A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/>',
    play: '<path d="M7 4.5v15l12-7.5z"/>',
    eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'
  };
  function kpis(el, list) {
    el.innerHTML = '';
    list.forEach(function (k) {
      var d = document.createElement('div'), tone = k[2] === 'ok' ? ' is-ok' : k[2] ? ' is-warn' : '';
      d.className = 'stat-card';
      d.innerHTML = '<div class="stat-card-head"><span class="stat-card-icon' + tone + '"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        + (ICONS[k[4]] || ICONS.list) + '</svg></span><span class="stat-card-label"></span></div><div class="stat-card-num"></div><div class="stat-card-sub"></div>';
      $('.stat-card-label', d).textContent = k[1]; $('.stat-card-num', d).textContent = k[0]; $('.stat-card-sub', d).textContent = k[3] || '';
      el.appendChild(d);
    });
  }
  /* 根拠の内部表記（調査の番号・[S1] などの出典番号）は画面に出さない。古い案件の観点は分類名で示す */
  function cleanBasis(v, cat) {
    var s = text(v).replace(/^根拠[:：]\s*/, '');
    if (!/調査\s*\d|\[S\d+b?\]/.test(s)) return s;
    if (cat) return '実務観点: ' + cat;
    return s.replace(/調査\s*\d+\s*[\d.]*\s*/g, '').replace(/\[S\d+b?\]/g, '').replace(/[（(][^）)]*[）)]/g, '').replace(/\s*根拠[:：]\s*$/, '').trim() || '実務観点';
  }
  /* ---- 表の絞り込みとページ分け（状態は画面内だけに持つ。50 件ごと） ---- */
  var PAGE = 50, DEC_LABEL = { emit: '出す', adopted: '採用', edited: '修正して採用', excluded: '対象外', discarded: '破棄' }, flt;
  function resetFlt() { flt = { 3: { cat: '', pri: '', dec: '', page: 0 }, 4: { chip: '', q: '', shown: 50 } }; }
  resetFlt();
  function priLabel(p) { var set = PRI_SETS.filter(function (x) { return p in x; })[0]; return set ? set[p] : p; }
  function fillFilter(n, key, opts, all) {
    var s = $('#bs-stage-' + n + ' [data-flt="' + key + '"]'), cur = flt[n][key];
    s.innerHTML = ''; s.appendChild(new Option(all, ''));
    Object.keys(opts).forEach(function (v) { s.appendChild(new Option(opts[v], v)); });
    if (!Object.prototype.hasOwnProperty.call(opts, cur)) flt[n][key] = cur = '';
    s.value = cur;
  }
  function table(n, all, rows, body, cols, emptyAll, emptyFlt) {
    var f = flt[n], panel = $('#bs-stage-' + n), pg = $('.bs-pager', panel), bar = $('.bs-filter', panel);
    var pages = Math.max(1, Math.ceil(rows.length / PAGE)), active = Object.keys(f).some(function (k) { return k !== 'page' && f[k]; });
    if (f.page >= pages) f.page = pages - 1;
    if (f.page < 0) f.page = 0;
    var start = f.page * PAGE, part = rows.slice(start, start + PAGE);
    bar.hidden = !all; pg.hidden = !all; $('[data-act="flt-clear"]', bar).disabled = !active;
    $('[data-pg="count"]', pg).textContent = rows.length ? (start + 1) + '–' + (start + part.length) + ' / ' + rows.length + ' 件' + (active ? '（全 ' + all + ' 件から絞り込み）' : '') : '0 / ' + all + ' 件';
    $('[data-act="pg-prev"]', pg).disabled = f.page <= 0; $('[data-act="pg-next"]', pg).disabled = f.page >= pages - 1;
    if (!all) noneRow(body, cols, emptyAll); else if (!rows.length) noneRow(body, cols, emptyFlt); else body.innerHTML = '';
    return part;
  }
  function onFilter(t) { var n = +t.closest('.bs-panel').dataset.stage; flt[n][t.dataset.flt] = t.value; flt[n].page = 0; renderPanel(); }
  function pageAct(t, act) {
    var n = +t.closest('.bs-panel').dataset.stage, f = flt[n];
    if (act === 'flt-clear') Object.keys(f).forEach(function (k) { f[k] = k === 'page' ? 0 : ''; }); else f.page += act === 'pg-next' ? 1 : -1;
    renderPanel();
    var c = $('#app-content'), card = $('#bs-stage-' + n + ' .bs-filter'), bar = $('#bs-approve');
    if (act !== 'flt-clear' && c && card) c.scrollTop += card.getBoundingClientRect().top - c.getBoundingClientRect().top - (bar ? bar.offsetHeight : 0) - 24;
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
  /* 工程の状態は WS2D.status の語彙で出す（内部の state はそのまま）。差し戻しは語彙に無いので「確認待ち」の形で文字だけ残す */
  var STEP_LABEL = { draft: '未開始', generated: '承認待ち', approved: '完了', rejected: '差し戻し' };
  var WS_STATUS = { draft: ['not_started'], generated: ['waiting_approval'], approved: ['done'], rejected: ['waiting_review', '差し戻し'] };
  function stageBadge(job, n) {
    var st = stageOf(job, n), code, label, m;
    if (st.stale) { code = 'waiting_review'; label = '前段が変わりました'; }
    else if (n === 7 && st.status !== 'approved' && isRunning(job)) { code = 'running'; }
    else { m = WS_STATUS[st.status] || WS_STATUS.draft; code = m[0]; label = m[1]; }
    if (!window.WS2D) return esc(label || STEP_LABEL[st.status] || STEP_LABEL.draft);
    return window.WS2D.status.html(code, label);
  }
  var LEVEL_FULL = { integration_internal: '結合テスト（内部）', integration_external: '結合テスト（外部）', system: 'システムテスト', acceptance: '受け入れテスト' };
  var CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
  var RUN_ST = { running: ['実行中', 'badge-info'], queued: ['待機中', 'badge-info'], done: ['終了', 'badge-low'], error: ['失敗', 'badge-critical'], cancelled: ['キャンセル', 'badge-muted'] };
  var TITLES = { home: 'ホーム', runs: '実行履歴', catalog: '観点カタログ' };
  function stageOf(job, n) { return (job && job.stages && job.stages[n]) || { status: 'draft', version: 0 }; }
  function currentStage(job) { for (var n = 1; n <= 8; n++) { if (stageOf(job, n).status !== 'approved') return n; } return 8; }
  function myRole() { var j = state.job || {}; return j.my_role || state.role || (j.members || {})[state.me] || ''; }
  function required(n) { return ((state.job || {}).approver_roles || {})[n] || (n === 4 || n === 8 ? 'senior_qa' : 'qa'); }
  function isSenior() { return myRole() === 'senior_qa'; }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function lastRun(j) { var r = j.runs || []; return r[r.length - 1] || null; }
  function isRunning(j) { var r = lastRun(j); return !!(j.running || (r && /^(running|queued|starting)$/.test(r.status || ''))); }
  /* 実行ボタンを押せない理由（押せるときは空） */
  function runBlock(j) {
    if (isRunning(j)) return '実行中です';
    for (var n = 1; n <= 6; n++) { if (stageOf(j, n).status !== 'approved') return '段階 6 のテストコードを承認すると実行できます'; }
    return '';
  }
  function targetText(j) {
    var tg = ((state.summary || {}).targets || {})[j.id];
    if (!j.targets && tg != null) return tg;
    var t = (j.targets || [])[0] || {};
    var nm = function (l) { return (l || []).map(function (x) { return x && typeof x === 'object' ? (x.name || x.table || x.path || '') : String(x || ''); }).filter(Boolean).join('・'); };
    var i = nm(t.inputs), o = nm(t.outputs);
    return i || o ? (i || '入力未設定') + ' → ' + (o || '出力未設定') : (t.command || tg || '');
  }
  function envName(j) { var e = (j.envs || []).filter(function (x) { return x.id === j.current_env; })[0]; return e ? (e.name || e.id) : ''; }
  function fresh(t) {
    var d = t ? new Date(t) : null;
    if (!d || isNaN(d)) return ['', ''];
    var now = new Date(), days = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 864e5);
    if (days <= 0) return ['fresh-today', '今日 ' + d.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' })];
    return [days < 7 ? 'fresh-week' : 'fresh-month', days + '日前'];
  }
  function progressHtml(j) {
    var cur = currentStage(j), running = isRunning(j), p = (lastRun(j) || {}).progress || {}, cells = '', all = true, t;
    for (var n = 1; n <= 8; n++) {
      var st = stageOf(j, n), cls = st.stale || st.status === 'rejected' ? 'is-back' : st.status === 'approved' ? 'is-done' : st.status === 'generated' ? 'is-wait' : '';
      var lab = st.stale ? '前段が変わりました' : STEP_LABEL[st.status] || STEP_LABEL.draft;
      if (n === 7 && running) { cls = 'is-run'; lab = '実行中'; }
      if (st.status !== 'approved') all = false;
      cells += '<i class="' + cls + '" title="段階 ' + n + ' ' + NAMES[n] + ': ' + lab + '"></i>';
    }
    var cs = stageOf(j, cur);
    if (all) t = '<b>完了</b>・8 段階すべて承認済み';
    else if (running) t = '<b>段階 7 実行</b>・実行中' + (p.total ? ' ' + (p.done || 0) + ' / ' + p.total + ' 件' : '');
    else if (cs.stale || cs.status === 'rejected') t = '<span class="is-back">段階 ' + cur + ' ' + NAMES[cur] + '・' + (cs.stale ? '前段が変わりました' : '差し戻し') + '</span>';
    else t = '<b>段階 ' + cur + ' ' + NAMES[cur] + '</b>・' + (STEP_LABEL[cs.status] || STEP_LABEL.draft);
    return '<div class="s8-prog" role="img" aria-label="' + (all ? '8 段階すべて承認済み' : '段階 ' + cur + ' ' + NAMES[cur]) + '">' + cells + '</div><div class="s8-prog-t">' + t + '</div>';
  }
  function resultsHtml(j) {
    var s = (j.judgement || {}).summary, out = '';
    if (s) {
      if (s.pass) out += '<span class="badge badge-low">合格 ' + (+s.pass) + '</span>';
      if (s.fail) out += '<span class="badge badge-critical">不合格 ' + (+s.fail) + '</span>';
      if (s.unverified) out += '<span class="badge badge-muted">未検証 ' + (+s.unverified) + '</span>';
    }
    if (!out) out = '<span class="s8-none">' + (isRunning(j) ? '実行中です' : (j.runs || []).length ? 'まだ判定していません' : 'まだ実行していません') + '</span>';
    return '<div class="s8-results">' + out + '</div>';
  }
  function loadJobs() { return api('GET', API).then(function (d) { state.jobs = d.jobs || []; renderHome(); renderRuns(); }).catch(notify); }
  function loadSummary() {
    return api('GET', '/api/backend-test/summary').then(function (d) { state.summary = d; renderHome(); renderCatalog(); })
      .catch(function (e) { console.warn('BackendTest: まとめを取得できませんでした', e); renderCatalog(); });
  }

  /* ---- ホーム（KPI・案件一覧）・実行履歴・観点カタログ ---- */
  function renderHome() {
    var js = state.jobs, body = $('#s8-jobs'), running = js.filter(isRunning), fail = 0, uv = 0;
    js.forEach(function (j) { var s = (j.judgement || {}).summary || {}; fail += +s.fail || 0; uv += +s.unverified || 0; });
    var r0 = running[0], p = r0 ? ((lastRun(r0) || {}).progress || {}) : {};
    kpis($('#s8-home-kpis'), [[js.length, '案件', '', '登録済みの案件数', 'folder'],
      [running.length, '実行中', '', r0 ? (r0.name || '名前のない案件') + (p.total ? '（' + (p.done || 0) + ' / ' + p.total + ' 件）' : '') : '実行中の案件はありません', 'play'],
      [fail, '不合格', 'wa', '直近の実行で不合格のケース', 'fail'], [uv, '未検証', 'wa', '確かめられなかったケース', 'warn']]);
    $('#s8-sample').hidden = !js.length;
    if (!js.length) return noneRow(body, 5, 'まだ案件がありません。上の「案件を作る」から始めます。');
    body.innerHTML = '';
    js.forEach(function (j) {
      var tr = document.createElement('tr'), f = fresh(j.updated_at), why = runBlock(j), sub = targetText(j), lv = LEVELS[j.level] || '';
      tr.innerHTML = '<td><div class="s8-name"><strong></strong>' + (lv ? '<span class="badge badge-info">' + esc(lv) + '</span>' : '') + '</div><div class="s8-sub"></div></td>'
        + '<td>' + progressHtml(j) + '</td><td><span class="freshness ' + f[0] + '">' + esc(f[1]) + '</span></td><td>' + resultsHtml(j) + '</td>'
        + '<td><div class="history-actions"><button type="button" class="btn-primary is-sm" data-open>開く</button>'
        + '<button type="button" class="btn-outline-sm" data-run' + (why ? ' disabled title="' + esc(why) + '"' : '') + '>実行</button>'
        + '<button type="button" class="btn-outline-sm" data-del>削除</button></div></td>';
      $('strong', tr).textContent = j.name || '名前のない案件';
      $('.s8-sub', tr).textContent = sub; $('.s8-sub', tr).hidden = !sub;
      $$('[data-open],[data-run],[data-del]', tr).forEach(function (b) { b.dataset.id = j.id; });
      body.appendChild(tr);
    });
  }
  function renderRuns() {
    var body = $('#s8-runs'), rows = [];
    state.jobs.forEach(function (j) { (j.runs || []).forEach(function (r) { rows.push([j, r]); }); });
    rows.sort(function (a, b) { return String(b[1].started_at || '').localeCompare(String(a[1].started_at || '')); });
    if (!rows.length) return noneRow(body, 7, 'まだ実行した案件はありません。案件の段階 7 で実行すると、ここに並びます。');
    body.innerHTML = '';
    rows.forEach(function (x) {
      var j = x[0], r = x[1], p = r.progress || {}, s = RUN_ST[r.status] || [r.status || '不明', 'badge-muted'], tr = document.createElement('tr');
      tr.innerHTML = '<td><strong></strong></td><td></td><td></td><td></td><td><span class="badge ' + s[1] + '"></span></td><td></td><td><button type="button" class="btn-outline-sm" data-run>開く</button></td>';
      var td = tr.children;
      $('strong', tr).textContent = j.name || '名前のない案件'; td[1].textContent = fmtTime(r.started_at); td[2].textContent = r.env_name || r.env || '';
      td[3].textContent = r.business_date || ''; $('.badge', tr).textContent = s[0]; td[5].textContent = p.total ? (p.done || 0) + ' / ' + p.total + ' 件' : '';
      $('[data-run]', tr).dataset.id = j.id; body.appendChild(tr);
    });
  }
  function renderCatalog() {
    var body = $('#s8-catalog'), list = (state.summary || {}).catalog || [], q = ($('#s8-cat-q').value || '').trim().toLowerCase();
    var rows = list.filter(function (v) { return !q || [v.id, v.cat_name, v.name, v.technique].join(' ').toLowerCase().indexOf(q) >= 0; });
    $('#s8-cat-count').textContent = list.length ? rows.length + ' / ' + list.length + ' 件' : '';
    if (!rows.length) return noneRow(body, 6, list.length ? '条件に合う観点はありません。探す言葉を変えてください。' : '観点カタログを読み込めませんでした。画面を再読み込みしてください。');
    body.innerHTML = '';
    rows.forEach(function (v) {
      var tr = document.createElement('tr');
      tr.innerHTML = '<td class="s8-id"></td><td></td><td><strong></strong></td><td></td><td></td><td></td>';
      var td = tr.children;
      td[0].textContent = v.id; td[1].textContent = v.cat_name || ''; $('strong', tr).textContent = v.name || '';
      td[3].textContent = v.technique || ''; td[4].textContent = priLabel(v.priority || '');
      td[5].textContent = (v.levels || []).map(function (l) { return LEVELS[l] || l; }).join('・');
      body.appendChild(tr);
    });
  }

  /* ---- 表示の切り替え（ホーム／実行履歴／観点カタログ／案件）と URL ハッシュ ---- */
  /* push=true は画面（ホーム・履歴・カタログ・案件）の切替。段階など画面内の選択は replaceState */
  function setHash(h, push) {
    var want = location.pathname + (h ? '#' + h : '');
    if (location.pathname + location.search + location.hash === want) return;
    history[push ? 'pushState' : 'replaceState'](null, '', want);
  }
  function setView(v, navKey) {
    state.view = v;
    $$('.s8-view').forEach(function (s) { s.classList.toggle('is-active', s.id === 'view-' + v); });
    var nav = navKey || (v === 'job' ? 'jobs' : v);
    $$('.app-nav-item[data-nav]').forEach(function (a) {
      var on = a.dataset.nav === nav;
      a.classList.toggle('is-active', on);
      if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    if (v !== 'job' && state.job) { state.job = null; if (window.BackendTestRun && window.BackendTestRun.stop) window.BackendTestRun.stop(); }
    if (v !== 'job') { $('#bs-prod-banner').hidden = true; $('#bs-approve').hidden = true; }
    renderTop();
  }
  function goNav(v) {
    var c = $('#app-content');
    if (v === 'home' || v === 'jobs') {
      setHash('', true); setView('home', v); renderHome();
      if (v === 'jobs') $('#jobs').scrollIntoView({ block: 'start' }); else c.scrollTop = 0;
      return;
    }
    setHash(v, true); setView(v); c.scrollTop = 0;
    if (v === 'catalog' && !state.summary) loadSummary();
  }
  function route() {
    var h = location.hash.replace(/^#/, ''), p = new URLSearchParams(h), old = /^s([1-8])$/.exec(h);
    var jid = p.get('job') || new URLSearchParams(location.search).get('job');
    if (jid) return openJob(jid, p.get('stage') || (old && old[1]), true);
    if (h === 'runs' || h === 'catalog') { setView(h); if (h === 'catalog' && !state.summary) loadSummary(); return; }
    setView('home');
  }
  function renderTop() {
    var j = state.view === 'job' ? state.job : null, crumb = $('#topbar-breadcrumb'), chips = $('#s8-chips'), act = $('#s8-head-actions');
    if (!j) {
      crumb.innerHTML = '<span>WebSpec2Doc</span><span class="sep">/</span><span></span>';
      crumb.lastChild.textContent = TITLES[state.view] || 'ホーム';
      $('#topbar-title').textContent = 'バッチ・バックエンドのテスト'; chips.innerHTML = ''; act.hidden = true;
      document.title = 'ホーム - バッチ・バックエンドのテスト - WebSpec2Doc';
      return;
    }
    var nm = j.name || '名前のない案件', why = runBlock(j), env = envName(j), tg = targetText(j), rb = $('#s8-run-head');
    crumb.innerHTML = '<span><a href="#" data-nav="home">ホーム</a></span><span class="sep">/</span><span><a href="#" data-nav="jobs">案件</a></span><span class="sep">/</span><span></span>';
    crumb.lastChild.textContent = nm; $('#topbar-title').textContent = nm; document.title = nm + ' - バッチ・バックエンドのテスト - WebSpec2Doc';
    chips.innerHTML = '';
    [['badge-info', LEVEL_FULL[j.level] || ''], ['badge-muted', '対象: ' + (tg || '未設定')], ['badge-muted', '接続先: ' + (env || '未設定')]].forEach(function (c) {
      if (!c[1]) return;
      var s = document.createElement('span'); s.className = 'badge ' + c[0]; s.textContent = c[1]; chips.appendChild(s);
    });
    act.hidden = false; rb.disabled = !!why; rb.title = why;
    renderHeadState();
  }
  /* page header: 現在の工程状態（WS2D.status）と、その理由 1 行（WS2D.reason）。案件の外は画面の説明を 1 行 */
  var VIEW_REASON = { home: '案件を作ると、資料の読み取りから判定までを 8 段階で進めます。各段階は承認してから次へ進みます。',
    runs: '実行した結果の履歴です。合格に数えるのは実行で確かめたケースだけで、確かめていないものは未検証として別に数えます。',
    catalog: '案件で使える観点の一覧です。ここは記録で、案件に取り込んで承認するまでは使われません。' };
  function renderHeadState() {
    var j = state.view === 'job' ? state.job : null, chips = $('#s8-chips'), host = $('#s8-reason'), old = $('#s8-state-chip'), n, st, msg, kind, lock, env, prod;
    if (old) old.parentNode.removeChild(old);
    if (!host) return;
    if (!j) { host.hidden = false; if (window.WS2D) window.WS2D.reason(host, VIEW_REASON[state.view] || VIEW_REASON.home, 'info'); return; }
    n = state.stage; st = stageOf(j, n);
    var chip = document.createElement('span'); chip.id = 's8-state-chip'; chip.innerHTML = stageBadge(j, n); chips.insertBefore(chip, chips.firstChild);
    lock = $('#bs-approve-lock'); msg = lock && !lock.hidden && lock.textContent ? lock.textContent : (st.stale ? '前の段階が変わりました。内容を確かめてから承認してください。' : DESC[st.status] || DESC.draft);
    kind = st.stale || st.status === 'rejected' || (lock && !lock.hidden) ? 'warning' : st.status === 'approved' ? 'success' : 'info';
    env = (j.envs || []).filter(function (e) { return e.id === j.current_env; })[0]; prod = !!(env && env.production);
    if (prod) { msg += ' 接続先は本番らしいため、データを書き換える操作は止めています。'; kind = 'warning'; }
    host.hidden = false;
    if (window.WS2D) window.WS2D.reason(host, '段階 ' + n + ' ' + NAMES[n] + '：' + msg, kind); else host.textContent = msg;
  }
  function openJob(id, stage, fromUrl) {
    notify('');
    return api('GET', API + '/' + encodeURIComponent(id)).then(function (d) {
      if (!state.job || state.job.id !== d.job.id) { resetFlt(); state.detailFor = ''; }
      state.role = d.my_role || '';
      state.view = 'job'; state.stage = +(stage || currentStage(d.job)); setJob(d.job); setView('job'); showStage(state.stage, !fromUrl);
      /* 役割が応答に無いとき（古いサーバ）だけ利用者名を問い合わせて members と突き合わせる */
      if (!d.my_role && !state.meAsked) { state.meAsked = true; loadMe().then(function () { if (state.job) renderAll(); }); }
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

  /* ---- ステッパー・承認バー ---- */
  function renderStepper() {
    var j = state.job, ol = $('#s8-stepper');
    ol.innerHTML = '';
    if (!j) return;
    for (var n = 1; n <= 8; n++) {
      var st = stageOf(j, n), cur = n === state.stage, back = st.stale || st.status === 'rejected', done = st.status === 'approved' && !st.stale;
      var lab = st.stale ? '前段が変わりました' : STEP_LABEL[st.status] || STEP_LABEL.draft, li = document.createElement('li');
      li.className = 's8-step' + (cur ? ' is-current' : back ? ' is-back' : done ? ' is-done' : '');
      li.dataset.step = n; li.tabIndex = 0; li.setAttribute('role', 'button');
      li.title = '段階 ' + n + ' ' + NAMES[n] + '：' + lab;
      if (cur) li.setAttribute('aria-current', 'step');
      li.innerHTML = '<span class="s8-step-n">' + (done && !cur ? CHECK : n) + '</span><span><span class="s8-step-name"></span><span class="s8-step-st"></span></span>';
      $('.s8-step-name', li).textContent = NAMES[n]; $('.s8-step-st', li).innerHTML = stageBadge(j, n);
      ol.appendChild(li);
    }
  }
  function renderApprove() {
    var j = state.job, n = state.stage, st = stageOf(j, n), bar = $('#bs-approve'), mine = myRole(), lock = $('#bs-approve-lock');
    var allowed = (RANK[mine] || 0) >= (RANK[required(n)] || 1), ready = st.status === 'generated' || (n === 1 && st.status !== 'approved');
    var canReject = st.status === 'generated' || st.status === 'approved', cases = j.cases || [];
    var open = n === 4 ? cases.filter(function (c) { return !c.oracle || c.oracle.state === 'unconfirmed'; }).length : 0;
    var rej = +st.reject_count || +st.rejections || 0;
    bar.dataset.stage = n; bar.dataset.version = st.version || 0;
    $('#bs-approve-title').textContent = '段階 ' + n + ' ' + NAMES[n] + ' の承認';
    var meta = st.version ? '第 ' + st.version + ' 版' + (rej ? '（差し戻し ' + rej + ' 回）' : '') : 'まだ作っていません';
    if (n === 4 && cases.length) meta += '・確定 <b>' + (cases.length - open) + ' / ' + cases.length + '</b> 件・人の確定待ち <b>' + open + '</b> 件';
    $('#bs-approve-desc').innerHTML = meta;
    var next = st.status === 'approved' && n < 8, btn = $('#bs-approve-btn'), waitOpen = n === 4 && open > 0 && !next;
    btn.textContent = next ? '次の段階へ' : '承認して次へ';
    btn.disabled = next ? false : (!allowed || !ready || waitOpen);
    var msg = next ? '' : !allowed ? (mine ? 'この段階の承認はシニア QA が行います。気づいたことは理由を書いて差し戻せます。'
      : 'この案件のメンバーではないため承認できません。承認が必要なら案件の作成者に依頼してください。')
      : st.status === 'approved' ? 'すべての段階を承認しました。報告書は下の「書き出し」から取り出せます。'
      : st.status === 'rejected' ? '差し戻し中のため承認できません。内容を直して作り直すと承認できます。'
      : waitOpen ? '確定待ちが ' + open + ' 件あります。すべて確定すると承認できます。'
      : !ready ? (n === 7 ? 'まだ実行していないため承認できません。下の「実行する」で実行が終わると承認できます。'
        : 'まだ内容がないため承認できません。下の「作る」ボタンで内容を作ると承認できます。')
      : st.stale ? '前の段階が変わりました。内容を確かめてから承認してください。' : '';
    lock.textContent = msg; lock.hidden = !msg;
    bar.classList.toggle('locked', !allowed && !next);
    $('#bs-reject').disabled = !canReject; $('#bs-reject-reason').disabled = !canReject;
    $('#bs-revert').hidden = !((st.version || 0) >= 2);
  }
  function renderProd() {
    var j = state.job, env = j && (j.envs || []).filter(function (e) { return e.id === j.current_env; })[0], on = !!(env && env.production);
    $('#bs-prod-banner').hidden = !on;
    if (on) { $('#bs-prod-env').textContent = env.name || ''; $('#bs-prod-reasons').textContent = text(env.production_reasons || []); }
  }
  function renderPanel() {
    var j = state.view === 'job' ? state.job : null, n = state.stage, fn = renderers[n];
    $$('.bs-panel').forEach(function (p) { p.hidden = !j || +p.dataset.stage !== n; });
    $('#bs-approve').hidden = !j;
    if (!j) return;
    renderApprove(); renderHeadState();
    if (!fn) return;
    try { fn(j, n); } catch (e) { console.error('BackendTest stage ' + n, e); notify('画面の一部を表示できませんでした。画面を再読み込みしてください。'); }
  }
  function renderAll() {
    if (state.view === 'job' && state.job) { renderStepper(); renderProd(); renderPanel(); }
    renderTop(); renderHome(); renderRuns();
  }
  function showStage(n, push) {
    n = Math.min(8, Math.max(1, parseInt(n, 10) || 1));
    state.stage = n; state.oracleFor = ''; state.adding = false; state.detailFor = '';
    if (state.job) setHash('job=' + encodeURIComponent(state.job.id) + '&stage=' + n, !!push);
    renderStepper(); renderPanel();
    var c = $('#app-content'); if (c) c.scrollTop = 0;
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
    fillList('#bs-questions', qs, function (q) { return li(q.id || '', text(q.text), where(q.source)); }, '確認したいことはありません。');
    fillList('#bs-unread', un, function (u) {
      return typeof u === 'string' ? li('', u) : li('', text(u.reason || u.text || u.file), where(u.source || u));
    }, '読めなかった資料はありません。');
    kpis($('#bs-facts-kpis'), [[files.length, '資料', '', '取り込んだファイル', 'file'], [facts.length, '読み取った事実', facts.length ? 'ok' : '', '根拠の行が付いた事実', 'check'],
      [qs.length, '確認したいこと', qs.length ? 'wa' : '', '業務の担当者に確かめること', 'help'], [un.length, '読めなかった文', un.length ? 'wa' : '', '取り込めなかった資料・文', 'warn']]);
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
    var f = flt[3], cats = {}, pris = {}, decs = {};
    vps.forEach(function (v) { var k = v.cat_name || v.cat; if (k) cats[k] = k; if (v.priority) pris[v.priority] = priLabel(v.priority); if (v.decision) decs[v.decision] = DEC_LABEL[v.decision] || v.decision; });
    fillFilter(3, 'cat', cats, 'すべてのカテゴリ'); fillFilter(3, 'pri', pris, 'すべての優先度'); fillFilter(3, 'dec', decs, 'すべての扱い');
    var rows = vps.filter(function (v) { return (!f.cat || (v.cat_name || v.cat) === f.cat) && (!f.pri || v.priority === f.pri) && (!f.dec || v.decision === f.dec); });
    table(3, vps.length, rows, body, 7, 'まだ観点がありません。前の段階を承認してから「観点を作る」を押してください。', '条件に合う観点はありません。「絞り込みを解除」を押すと全件に戻ります。')
      .forEach(function (v) { body.appendChild(vpRow(v, edit)); });
    if (state.adding) body.insertBefore(addRow(), body.firstChild);
  };
  function vpRow(v, edit) {
    var tr = fill('bs-tpl-viewpoint', { id: v.id, name: v.name, basis: cleanBasis(v.basis, v.cat_name) }), tech = $('[data-f="technique"]', tr);
    var dec = $('[data-f="decision"]', tr), rs = $('[data-f="reason"]', tr);
    tr.dataset.vp = v.id; tech.textContent = '';
    tech.appendChild(select(TECHS.indexOf(v.technique) >= 0 ? TECHS : [v.technique || ''].concat(TECHS), v.technique || '', 'technique', '技法', !edit));
    var set = PRI_SETS.filter(function (s) { return v.priority in s; })[0] || PRI_SETS[0], keys = Object.keys(set), labels = Object.assign({ '': '未設定' }, set);
    if (!v.priority) keys = [''].concat(keys); else if (!(v.priority in labels)) { keys = [v.priority].concat(keys); labels[v.priority] = v.priority; }
    $('[data-f="priority"]', tr).appendChild(select(keys, v.priority || '', 'priority', '優先度', !edit, labels));
    dec.value = v.decision; dec.disabled = !edit; rs.value = v.reason || ''; rs.disabled = !edit;
    $('[data-f="unverified"]', tr).hidden = !v.unverified;
    return tr;
  }
  function addRow() {
    var tr = document.createElement('tr'), td = document.createElement('td'), f = document.createElement('form');
    var mk = function (name, ph) { var i = document.createElement('input'); i.name = name; i.maxLength = 200; i.placeholder = ph; i.setAttribute('aria-label', ph); return i; };
    var bt = function (type, cls, label, act) { var b = document.createElement('button'); b.type = type; b.className = cls; b.textContent = label; if (act) b.dataset.act = act; return b; };
    td.colSpan = 7; f.id = 'bs-vp-addform'; f.className = 'bs-row';
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

  /* ---- 段階 4 ケース表（見本 job.html: 絞り込みチップ＋検索＋7 列の表＋読み方） ---- */
  var METHOD_SHORT = { db_diff: '前後比較', alt_sql: '別の計算', golden: '承認済みの期待値', schema: '定義の検査' };
  function summary(j, c) {
    var o = c.oracle || {}, sums = (j.code && j.code.summaries) || {};
    if (c.summary || c.summary_ja || sums[c.id]) return c.summary || c.summary_ja || sums[c.id];
    return (c.pre ? '「' + text(c.pre) + '」の状態で、' : '') + ((c.steps || []).length ? c.steps.length + ' つの手順を行い、' : '')
      + '期待値を「' + (METHODS[o.method] || '未設定の方法') + '」で確かめます。' + (o.alt_sql_ja ? '別の計算: ' + o.alt_sql_ja : '');
  }
  function howSub(o) {
    var key = o.key || [], ex = o.exclude || [];
    if (o.method === 'alt_sql') return o.tolerance != null && o.tolerance !== '' ? '許す差: ' + text(o.tolerance) : '';
    if (o.method === 'golden') return o.state === 'unconfirmed' ? '期待値: 確定待ち' : '';
    if (o.method === 'schema') return '';
    if (key.length) return '突き合わせ: ' + key.join('・') + (ex.length ? '／比べない列: ' + ex.join('・') : '');
    if (ex.length) return '比べない列: ' + ex.join('・');
    return o.method === 'db_diff' ? '件数で比べる' : '';
  }
  function oracleRow(c) {
    var o = c.oracle || {}, tr = document.createElement('tr'), td = document.createElement('td');
    var f = document.getElementById('bs-tpl-oracle').content.firstElementChild.cloneNode(true), E = function (n) { return f.elements.namedItem(n); };
    f.dataset.case = c.id; E('method').value = o.method || 'db_diff'; E('key').value = (o.key || []).join(', '); E('exclude').value = (o.exclude || []).join(', ');
    E('tolerance').value = typeof o.tolerance === 'string' ? o.tolerance : text(o.tolerance);
    $('[data-f="warn"]', f).textContent = text(o.warnings || []);
    td.colSpan = 7; td.appendChild(f); tr.appendChild(td); return tr;
  }
  function detailRow(j, c) {
    var tr = document.createElement('tr'), td = document.createElement('td'), dl = document.createElement('dl'), o = c.oracle || {};
    td.colSpan = 7; dl.className = 's8-detail';
    [['前提データ', text(c.pre)], ['要約', summary(j, c)], ['別の計算', o.alt_sql || ''], ['根拠の事実', text(c.req_ids)]].forEach(function (x) {
      if (!x[1]) return;
      var dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = x[0]; dd.textContent = x[1]; dl.appendChild(dt); dl.appendChild(dd);
    });
    td.appendChild(dl); tr.appendChild(td); return tr;
  }
  renderers[4] = function (j) {
    var cases = j.cases || [], senior = isSenior(), body = $('#bs-cases'), f = flt[4], vmap = {}, cnt = { auto: 0, human: 0, unconfirmed: 0 }, meth = {}, st4 = stageOf(j, 4);
    (j.viewpoints || []).forEach(function (v) { vmap[v.id] = v; });
    var stOf = function (c) { var s = (c.oracle || {}).state; return ORACLE_ST[s] ? s : 'unconfirmed'; };
    cases.forEach(function (c) { cnt[stOf(c)]++; var m = (c.oracle || {}).method; if (m) meth[m] = (meth[m] || 0) + 1; });
    var chips = [['', 'すべて', cases.length], ['st:unconfirmed', '確定待ち', cnt.unconfirmed], ['st:human', '人が確定', cnt.human], ['st:auto', '機械判定', cnt.auto]];
    Object.keys(METHOD_SHORT).forEach(function (m) { if (meth[m]) chips.push(['m:' + m, METHOD_SHORT[m], meth[m]]); });
    if (!chips.some(function (c) { return c[0] === f.chip; })) f.chip = '';
    var box = $('#s8-case-chips'); box.innerHTML = ''; box.hidden = !cases.length; $('#s8-q').hidden = !cases.length;
    chips.forEach(function (c) {
      var b = document.createElement('button'); b.type = 'button'; b.className = 'fchip' + (c[0] === f.chip ? ' on' : ''); b.dataset.chip = c[0];
      b.setAttribute('aria-pressed', String(c[0] === f.chip)); b.textContent = c[1] + ' ' + c[2]; box.appendChild(b);
    });
    $('#bs-stage-4 [data-act="generate"]').hidden = st4.status === 'approved' || (st4.status === 'generated' && cases.length > 0);
    var q = (f.q || '').trim().toLowerCase();
    var rows = cases.filter(function (c) {
      var o = c.oracle || {}, ok = !f.chip || (f.chip.indexOf('st:') === 0 ? stOf(c) === f.chip.slice(3) : o.method === f.chip.slice(2));
      if (!ok || !q) return ok;
      return [c.id, c.viewpoint, (vmap[c.viewpoint] || {}).name, text(c.expected)].join(' ').toLowerCase().indexOf(q) >= 0;
    });
    var shown = rows.slice(0, f.shown || PAGE);
    if (!cases.length) noneRow(body, 7, 'まだケースがありません。観点表を承認してから「ケースを作る」を押してください。');
    else if (!rows.length) noneRow(body, 7, '条件に合うケースはありません。「すべて」を押すと全件に戻ります。');
    else body.innerHTML = '';
    shown.forEach(function (c) {
      var o = c.oracle || {}, sk = stOf(c), v = vmap[c.viewpoint] || {};
      var tr = fill('bs-tpl-case', { id: c.id, vpname: v.name || c.viewpoint || '', technique: v.technique || '', expected: c.expected, method: METHODS[o.method] || '確かめ方が未設定', howsub: howSub(o) });
      var ol = $('[data-f="steps"]', tr), pill = $('[data-f="state"]', tr), b = $('[data-act="oracle"]', tr), d = $('[data-act="case-detail"]', tr);
      tr.dataset.case = c.id;
      (c.steps || []).forEach(function (s) { ol.appendChild(li('', text(s))); });
      pill.textContent = ORACLE_ST[sk][0]; pill.className = 'badge ' + ORACLE_ST[sk][1];
      b.hidden = !senior || sk !== 'unconfirmed'; b.dataset.case = c.id;
      d.hidden = !b.hidden; d.dataset.case = c.id; d.setAttribute('aria-expanded', String(state.detailFor === c.id));
      body.appendChild(tr);
      if (state.oracleFor === c.id) body.appendChild(oracleRow(c));
      if (state.detailFor === c.id) body.appendChild(detailRow(j, c));
    });
    $('#s8-case-count').textContent = cases.length ? rows.length + ' 件中 ' + shown.length + ' 件を表示' : '';
    $('#s8-case-more').hidden = shown.length >= rows.length;
    var vpn = (j.viewpoints || []).filter(function (v) { return !REASON_NEEDED[v.decision]; }).length;
    kpis($('#bs-case-kpis'), [[cases.length, 'ケース', '', '観点 ' + vpn + ' 件から作成', 'list'], [cnt.auto, '機械判定', 'ok', '冪等性・件数・前後比較・定義の検査', 'cpu'],
      [cnt.human, '人が確定', '', '業務判断を含む期待値', 'user'], [cnt.unconfirmed, '確定待ち', 'wa', 'シニア QA の確定が必要', 'clock']]);
  };
  function submitOracle(f) {
    var E = function (n) { return f.elements.namedItem(n); };
    var split = function (s) { return s.split(/[,、]/).map(function (x) { return x.trim(); }).filter(Boolean); };
    var method = E('method').value, key = split(E('key').value);
    if (method === 'db_diff' && !key.length) { notify('行を突き合わせる列が空です。例のように列名をカンマで区切って入れてください。', '確定できませんでした'); E('key').focus(); return; }
    var tol = E('tolerance').value.trim().replace(/[，,]/g, '');
    if (tol && !isFinite(Number(tol))) { notify('許す差は数で入れてください（例: 1）。数を直してもう一度「確定する」を押してください。', '確定できませんでした'); E('tolerance').focus(); return; }
    // API は「前後比較の設定（configure_db_diff）」と「確定（confirm）」を別の操作として受ける。順に送る
    var path = jobPath('/cases/' + encodeURIComponent(f.dataset.case) + '/oracle');
    var altSql = E('alt_sql') ? E('alt_sql').value.trim() : '';
    if (method === 'alt_sql' && !altSql) { notify('別の計算の SQL が空です。比べる値を求める SQL を入れてください。', '確定できませんでした'); E('alt_sql').focus(); return; }
    var steps = method === 'db_diff'
      ? api('PATCH', path, { action: 'configure_db_diff', keys: key, exclude: split(E('exclude').value), tolerance: tol ? Number(tol) : null })
          .then(function () { return api('PATCH', path, { action: 'confirm' }); })
      : method === 'alt_sql'
        ? api('PATCH', path, { action: 'set_alt_sql', sql: altSql })
            .then(function () { return api('PATCH', path, { action: 'confirm' }); })
        : api('PATCH', path, { action: 'confirm' });
    // 期待値の API はケースだけを返すので、案件を読み直して表と件数を更新する
    steps = steps.then(function () { return api('GET', jobPath()); });
    run(f.querySelector('[type=submit]'), steps, '期待値を確定しました')
      .then(function (d) { if (d && d.job) { state.oracleFor = ''; renderPanel(); } });
  }

  /* ---- 段階 5 テストデータ仕様 ---- */
  renderers[5] = function (j) {
    var ds = j.data_specs || [], body = $('#bs-data-specs');
    if (!ds.length) return noneRow(body, 8, 'まだデータ仕様がありません。ケース表を承認してから「データ仕様を作る」を押してください。');
    body.innerHTML = '';
    ds.forEach(function (d) {
      body.appendChild(fill('bs-tpl-dataspec', { id: d.id, case: d.case, table: d.table, conditions: d.conditions, rows: d.rows,
        encoding: d.encoding, mask: (d.mask_cols || []).length ? d.mask_cols : 'なし', basis: cleanBasis(d.basis) }));
    });
  };

  /* ---- 段階の操作（生成・承認・差し戻し・取消） ---- */
  function generate(btn) {
    var n = +btn.dataset.stage, approved = stageOf(state.job, n).status === 'approved';
    return run(btn, api('POST', jobPath('/stages/' + n + '/generate')), approved ? '承認済みのため内容は変えず、変更の候補として受け付けました' : '作りました。内容を確かめてください');
  }
  function approve(btn) {
    var n = state.stage, st = stageOf(state.job, n);
    if (st.status === 'approved' && n < 8) return showStage(n + 1);
    var first = n === 1 && st.status !== 'generated' ? api('POST', jobPath('/stages/1/generate')) : Promise.resolve({ job: state.job });
    var p = first.then(function (d) { return api('POST', jobPath('/stages/' + n + '/approve'), { version: stageOf(d.job, n).version }); });
    // 判定（期待値との照合）は段階 7（実行）の承認が前提。承認できたらここで判定まで進め、段階 8 に結果を出す
    if (n === 7) p = p.then(function () { return api('POST', jobPath('/judge'), {}); }).then(function () { return api('GET', jobPath()); });
    return run(btn, p, '段階 ' + n + ' を承認しました').then(function (d) { if (d && d.job && n < 8) showStage(n + 1); });
  }
  function reject(btn) {
    var r = $('#bs-reject-reason'), reason = r.value.trim();
    if (!reason) { notify('差し戻す理由が空です。何を直してほしいかを 1 行で書いてください。', '理由を書いてください'); r.focus(); return; }
    run(btn, api('POST', jobPath('/stages/' + state.stage + '/reject'), { reason: reason, comments: {} }), '差し戻しました')
      .then(function (d) { if (d && d.job) r.value = ''; });
  }

  /* ---- イベント ---- */
  function focusNew() { goNav('home'); var i = $('#s8-name'); i.scrollIntoView({ block: 'center' }); i.focus(); }
  function createJob(btn) {
    var nameEl = $('#s8-name'), name = nameEl.value.trim();
    if (!name) { notify('バッチ名が空です。テストするバッチの名前を入れてから「案件を作る」を押してください。', '案件を作れませんでした'); nameEl.focus(); return; }
    run(btn, api('POST', API, { name: name, target_kind: 'batch', level: $('#s8-level').value, purpose: '', scope: '' }), '案件を作りました')
      .then(function (d) { if (d && d.job) { nameEl.value = ''; resetFlt(); state.view = 'job'; setView('job'); showStage(1); renderTop(); } });
  }
  function delJob(id, btn) {
    var j = state.jobs.filter(function (x) { return x.id === id; })[0] || {};
    if (!window.confirm('「' + (j.name || '名前のない案件') + '」を削除します。資料・ケース・実行の記録もすべて消え、元に戻せません。削除しますか。')) return;
    notify(''); busy(btn, true);
    api('DELETE', API + '/' + encodeURIComponent(id)).then(function () {
      state.jobs = state.jobs.filter(function (x) { return x.id !== id; }); renderHome(); renderRuns(); toast('案件を削除しました');
    }).catch(notify).then(function () { busy(btn, false); });
  }
  var CLICK = {
    'bs-approve-btn': approve, 'bs-reject': reject,
    'bs-revert': function (t) { run(t, api('POST', jobPath('/stages/' + state.stage + '/revert')), '前の版に戻しました'); },
    'bs-vp-add': function () { state.adding = true; renderPanel(); var i = $('#bs-vp-addform input'); if (i) i.focus(); },
    'bs-banner-retry': function () { return state.job ? openJob(state.job.id, state.stage) : loadJobs(); },
    's8-create': createJob,
    's8-reload': function (t) { busy(t, true); loadJobs().then(function () { busy(t, false); }); },
    's8-case-more': function () { flt[4].shown = (flt[4].shown || PAGE) + PAGE; renderPanel(); },
    's8-run-head': function () { showStage(7); },
    's8-export-head': function () { showStage(8); var e = $('#s8-export'); if (e) e.scrollIntoView({ block: 'start' }); }
  };
  document.addEventListener('click', function (e) {
    var t = e.target.closest('button, a[data-nav], a[data-new], a[data-act], [data-step]'), act = t && t.dataset.act;
    if (!t || t.disabled) return;
    if (t.dataset.nav) { e.preventDefault(); return goNav(t.dataset.nav); }
    if ('new' in t.dataset) { e.preventDefault(); return focusNew(); }
    if (act === 'sample') { e.preventDefault(); return state.jobs[0] && openJob(state.jobs[0].id); }
    if (t.dataset.step) return showStage(t.dataset.step);
    if ('open' in t.dataset) return openJob(t.dataset.id);
    if ('run' in t.dataset) return openJob(t.dataset.id, 7);
    if ('del' in t.dataset) return delJob(t.dataset.id, t);
    if ('chip' in t.dataset) { flt[4].chip = t.dataset.chip; flt[4].shown = PAGE; return renderPanel(); }
    if (t.dataset.level) return patch({ level: t.dataset.level }, 'テストレベルを保存しました');
    if (act === 'generate' && +t.dataset.stage <= 6) return generate(t);
    if (act === 'file-del') return run(t, api('DELETE', jobPath('/files/' + encodeURIComponent(t.dataset.file))), '資料を取り除きました');
    if (act === 'oracle' || act === 'oracle-cancel') { state.oracleFor = act === 'oracle' ? t.dataset.case : ''; return renderPanel(); }
    if (act === 'case-detail') { state.detailFor = state.detailFor === t.dataset.case ? '' : t.dataset.case; return renderPanel(); }
    if (act === 'vp-add-cancel') { state.adding = false; return renderPanel(); }
    if (act === 'flt-clear' || act === 'pg-prev' || act === 'pg-next') return pageAct(t, act);
    if (CLICK[t.id]) CLICK[t.id](t);
  });
  document.addEventListener('keydown', function (e) {
    var t = e.target;
    if ((e.key === 'Enter' || e.key === ' ') && t.matches && t.matches('[data-step]')) { e.preventDefault(); showStage(t.dataset.step); }
    if (e.key === 'Enter' && t.id === 's8-name' && !e.isComposing) { e.preventDefault(); createJob($('#s8-create')); }
  });
  function submitVp(f) {
    var name = f.elements.namedItem('name').value.trim();
    if (!name) return notify('観点が空です。確かめたいことを 1 行で書いてください。', '追加できませんでした');
    var item = { name: name, technique: f.querySelector('[data-field="technique"]').value, basis: f.elements.namedItem('basis').value.trim() };
    run(f.querySelector('[type=submit]'), api('POST', jobPath('/stages/3/items'), { item: item }), '観点を追加しました')
      .then(function (d) { if (d && d.job) { state.adding = false; renderPanel(); } });
  }
  document.addEventListener('submit', function (e) {
    var f = e.target, fn = f.id === 'bs-vp-addform' ? submitVp : f.classList.contains('bs-oracle') ? submitOracle : null;
    if (fn) { e.preventDefault(); fn(f); }
  });
  document.addEventListener('input', function (e) {
    if (e.target.id === 's8-q') { flt[4].q = e.target.value; flt[4].shown = PAGE; renderPanel(); }
    if (e.target.id === 's8-cat-q') renderCatalog();
  });
  document.addEventListener('change', function (e) {
    var t = e.target;
    if (!state.job || t.closest('#bs-vp-addform') || t.id === 's8-q') return;
    if (t.dataset.flt) return onFilter(t);
    if (t.id === 'bs-file') { upload(t.files); t.value = ''; return; }
    if (t.dataset.f === 'kind' && t.dataset.file) return run(null, api('PATCH', jobPath('/files/' + encodeURIComponent(t.dataset.file)), { kind: t.value }), '資料の種類を変えました');
    if (t.closest('#bs-stage-1')) return changeS1(t);
    if (t.closest('#bs-stage-3')) changeVp(t);
  });
  var drop = $('#bs-drop');
  ['dragenter', 'dragover'].forEach(function (n) { drop.addEventListener(n, function (e) { e.preventDefault(); drop.classList.add('over'); }); });
  ['dragleave', 'drop'].forEach(function (n) { drop.addEventListener(n, function (e) { e.preventDefault(); drop.classList.remove('over'); }); });
  drop.addEventListener('drop', function (e) { upload(e.dataTransfer.files); });
  // 実行が終わったら案件を読み直す（再読み込みしなくても段階 7 の承認と結果表が最新になる）
  document.addEventListener('bs:run-finished', function () {
    if (!state.job) return;
    api('GET', jobPath()).then(function (d) { if (d && d.job) { setJob(d.job); renderPanel(); } }).catch(function () {});
  });
  window.addEventListener('popstate', route);   // 戻る・進む・ハッシュの手入力。pushState では hashchange が出ないため popstate で受ける

  /* 段階 6〜8 の担当（backend-test-run.js）が使う共通の入口。role は setJob のたびに更新する文字列 */
  Object.assign(NS, {
    cleanBasis: cleanBasis, api: api, run: run, notify: notify, toast: toast, fill: fill, text: text, kpis: kpis, noneRow: noneRow, li: li, fmtTime: fmtTime,
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
  /* 見本の見出し行: 題名の横にチップ、右に書き出し・実行する（共通の上部バーに差し込む） */
  (function () {
    var h1 = $('#topbar-title'), row = document.createElement('div');
    row.className = 's8-title-row'; h1.parentNode.insertBefore(row, h1); row.appendChild(h1); row.appendChild($('#s8-chips'));
    var slot = $('#topbar-actions'); if (slot) slot.appendChild($('#s8-head-actions'));
  })();
  /* 根拠の種類は WS2D.evidence の語（実測・記録・文書・未確認）で示す。data-ev に code を書く */
  $$('[data-ev]').forEach(function (el) { if (window.WS2D) el.innerHTML = window.WS2D.evidence.html(el.dataset.ev); });
  setView('home');
  loadJobs().then(route); loadSummary();
})();
