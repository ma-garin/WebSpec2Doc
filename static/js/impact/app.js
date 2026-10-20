/* System 09 影響度分析 — 共通部品・画面の切り替え（DD-008）。
   URL: /impact ・ ?sys=<id> ・ ?sys=<id>&cr=<CR-ID> ・ ?view=guide（tab= で画面内の区分）。全遷移を /impact 内で完結する。 */
(function () {
  'use strict';
  var IM = window.IM;
  var api = IM.api;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* ---------- 共通部品 ---------- */
  function esc(v) {
    return String(v === undefined || v === null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function fmtDate(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return esc(iso);
    var p = function (n) { return (n < 10 ? '0' : '') + n; };
    return d.getFullYear() + '/' + p(d.getMonth() + 1) + '/' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }
  var STATUS = { draft: '起票', analyzing: '分析中', review: 'レビュー待ち', approved: '承認済み', returned: '差し戻し',
    rejected: '却下', implemented: '実装済み', verified: '検証済み' };
  var ROLE = { admin: '管理者', analyst: '分析担当', approver: '承認者', viewer: '閲覧者' };
  var KIND = { requirement: '要件', design: '設計書', screen: '画面仕様書', testcase: 'テストケース', other: 'その他' };
  var POLICY = { none: '送らない', local: 'ローカル LLM のみ', external: '外部 LLM 可' };
  var CAN = { /* DD-003 */
    view: ['admin', 'analyst', 'approver', 'viewer'], edit_system: ['admin'], members: ['admin'], policy: ['admin'],
    documents: ['admin', 'analyst'], baselines: ['admin', 'analyst'], links: ['admin', 'analyst'],
    cr_write: ['admin', 'analyst'], analyze: ['admin', 'analyst'], resolve: ['admin', 'analyst'],
    override: ['admin', 'analyst'], actuals: ['admin', 'analyst'], approve: ['admin', 'approver'], audit_view: ['admin', 'approver']
  };
  function can(role, action) { return (CAN[action] || []).indexOf(role) >= 0; }
  // CR は分析の完了後も「レビューに回す」まで analyzing のまま。終わっているのに「分析中」と見せないため、
  // CR を渡されたときは分析結果の有無で言い分ける
  function statusBadge(s, cr) {
    var label = STATUS[s] || s;
    if (s === 'analyzing' && cr && (cr.analyzed_at || Number((cr.summary || {}).total) > 0)) label = '分析済み（レビュー前）';
    return '<span class="im-st st-' + esc(s) + '">' + esc(label) + '</span>';
  }
  function priBadge(p) { return p ? '<span class="im-pri p' + esc(p) + '">P' + esc(p) + '</span>' : '<span class="im-pri p0">—</span>'; }

  function loading(el, msg) { el.innerHTML = '<div class="im-state" role="status" aria-live="polite"><span class="im-spin" aria-hidden="true"></span>' + esc(msg || '読み込み中…') + '</div>'; }
  function failed(el, err, retry) {
    el.innerHTML = '<div class="im-state im-state-ng" role="alert"><b>読み込めませんでした</b><p>' + esc(err && err.message || err) +
      '</p>' + (retry ? '<button type="button" class="btn-outline-sm" data-retry>もう一度読み込む</button>' : '') + '</div>';
    if (retry) $('[data-retry]', el).addEventListener('click', retry);
  }
  function empty(o) {
    var steps = (o.steps || []).map(function (s, i) {
      return (i ? '<div class="onboard-arrow" aria-hidden="true">→</div>' : '') +
        '<div class="onboard-step"><span class="onboard-num">' + (i + 1) + '</span><strong>' + esc(s[0]) + '</strong><span>' + esc(s[1]) + '</span></div>';
    }).join('');
    return '<div class="dashboard-empty"><div class="dashboard-empty-title">' + esc(o.title) + '</div>' +
      '<div class="dashboard-empty-desc">' + esc(o.desc || '') + '</div>' +
      (steps ? '<div class="onboard-steps">' + steps + '</div>' : '') + (o.actions || '') + '</div>';
  }
  function toast(msg) {
    var t = $('#bt-toast'); t.textContent = msg; t.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(function () { t.hidden = true; }, 3200);
  }
  function banner(msg) { var b = $('#bt-banner'); b.textContent = msg || ''; b.hidden = !msg; }

  /* モーダル: onSubmit(form) が Promise を返す。失敗はモーダル内に表示して閉じない。Esc で閉じる */
  var lastFocus = null;
  function closeModal() {
    var m = $('#im-modal'); m.hidden = true; $('#im-modal-body').innerHTML = '';
    document.removeEventListener('keydown', onKey, true);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  function onKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); closeModal(); return; }
    if (e.key !== 'Tab') return;
    // フォーカスを窓の中に閉じ込める（REQ-N-012: キーボードだけで操作を終えられる）
    var f = $$('#im-modal button, #im-modal input, #im-modal select, #im-modal textarea, #im-modal a[href]')
      .filter(function (x) { return !x.disabled && x.offsetParent !== null; });
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
  function modal(o) {
    lastFocus = document.activeElement;
    var m = $('#im-modal'), form = $('#im-modal-form');
    $('#im-modal-t').textContent = o.title;
    $('#im-modal-body').innerHTML = o.body || '';
    var ok = $('#im-modal-ok'); ok.textContent = o.submit || '実行'; ok.className = o.danger ? 'btn-danger im-btn-danger' : 'btn-primary';
    ok.disabled = false;
    $('#im-modal-err').hidden = true;
    m.hidden = false;
    document.addEventListener('keydown', onKey, true);
    var first = $('input,select,textarea', form) || ok; first.focus();
    form.onsubmit = function (e) {
      e.preventDefault();
      ok.disabled = true;
      Promise.resolve(o.onSubmit ? o.onSubmit(form) : null).then(function () { closeModal(); }, function (err) {
        ok.disabled = false;
        var box = $('#im-modal-err'); box.textContent = err && err.message || String(err); box.hidden = false;
      });
    };
    if (o.onOpen) o.onOpen(form);
  }
  function confirmBox(o) {
    return new Promise(function (resolve) {
      modal({ title: o.title, body: '<p class="im-confirm">' + esc(o.message) + '</p>', submit: o.submit || '実行する',
        danger: o.danger !== false, onSubmit: function () { resolve(true); } });
    });
  }
  function need(v, label) { if (!String(v || '').trim()) throw new Error(label + 'を入力してください。'); return String(v).trim(); }

  /* ---------- 画面の切り替え ---------- */
  var state = { sid: '', cr: '', tab: '', view: '', system: null };
  function readUrl() {
    var q = new URLSearchParams(location.search);
    return { sid: q.get('sys') || '', cr: q.get('cr') || '', tab: q.get('tab') || '', view: q.get('view') || '', site: q.get('site') || '' };
  }
  function go(p, replace) {
    var q = {};
    if (p.view) q.view = p.view;
    if (p.sid) q.sys = p.sid;
    if (p.cr) q.cr = p.cr;
    if (p.tab) q.tab = p.tab;
    if (p.site) q.site = p.site;  // 指揮などから渡されたサイト（候補の提示とコード依存の初期選択だけに使う）
    var url = '/impact' + api.query(q);
    history[replace ? 'replaceState' : 'pushState'](q, '', url);
    render();
  }
  function setTitle(crumb, title) {
    var c = $('#topbar-breadcrumb'); var t = $('#topbar-title');
    if (c) c.innerHTML = '<span>WebSpec2Doc</span><span class="sep">/</span><span>影響度分析</span>' +
      (crumb ? '<span class="sep">/</span><span>' + esc(crumb) + '</span>' : '');
    if (t) t.textContent = title;
    document.title = title + ' - 影響度分析 - WebSpec2Doc';
  }
  function syncNav() {
    var inSys = !!state.sid && state.view !== 'guide', inCr = inSys && !!state.cr;
    $$('[data-scope=sys]').forEach(function (b) { b.hidden = !inSys; });
    $$('[data-scope=cr]').forEach(function (b) { b.hidden = !inCr; });
    var cur = state.view === 'guide' ? 'guide' : inCr ? 'cr:' + (state.tab || 'changes') : inSys ? 'sys:' + (state.tab || 'overview') : 'home';
    $$('.app-nav-item').forEach(function (b) {
      var key = b.dataset.nav || (b.dataset.scope + ':' + b.dataset.tab);
      var on = key === cur;
      b.classList.toggle('active', on);
      if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    var name = $('#im-nav-sysname'); if (name) name.textContent = state.system ? state.system.name : '対象システム';
    var crh = $('#im-nav-crname'); if (crh) crh.textContent = state.cr || '変更要求';
  }
  function loadSystem(sid) {
    if (state.system && state.system.id === sid) return Promise.resolve(state.system);
    return api.system(sid).then(function (d) { state.system = Object.assign({ id: sid }, api.obj(d, 'system'), d && d.my_role ? { my_role: d.my_role } : {}); return state.system; });
  }
  function render() {
    var u = readUrl(), root = $('#im-root');
    if (u.sid !== state.sid) state.system = null;
    Object.assign(state, u);
    banner('');
    if (IM.cr && IM.cr.leave) IM.cr.leave(state.sid, state.cr);
    syncNav();
    if (state.view === 'guide') { renderGuide(root); return; }
    if (!state.sid) { renderHome(root); return; }
    loading(root);
    loadSystem(state.sid).then(function (sys) {
      syncNav();
      var ctx = { sid: state.sid, system: sys, role: sys.my_role || 'viewer', tab: state.tab, cr: state.cr };
      if (state.cr) IM.cr.render(root, ctx); else IM.system.render(root, ctx);
    }, function (e) { setTitle('', '対象システム'); failed(root, e, render); });
  }
  function refreshSystem() { state.system = null; return loadSystem(state.sid); }

  /* ---------- 対象システム一覧 ---------- */
  function newSystem() {
    modal({ title: '新しい対象システム', submit: '作成する',
      body: '<label class="bt-field">名前<input name="name" maxlength="100" required placeholder="例: 会員管理システム"></label>' +
        '<label class="bt-field">説明<textarea name="description" rows="3" maxlength="1000" class="im-ta"></textarea></label>',
      onSubmit: function (f) {
        var name = need(f.name.value, '名前');
        return api.createSystem({ name: name, description: f.description.value.trim() }).then(function (d) {
          var s = api.obj(d, 'system'); toast('対象システムを作成しました'); go({ sid: s.id });
        });
      } });
  }
  function trySample(btn) {
    btn.disabled = true; btn.textContent = '見本を作っています…';
    api.sample().then(function (d) {
      var s = api.obj(d, 'system'), cr = (d && d.cr) || {}; toast('見本の対象システムを作り、分析を始めました'); go({ sid: s.id || s.system_id, cr: cr.code, tab: cr.code ? 'impacts' : '' });
    }, function (e) { btn.disabled = false; btn.textContent = '見本で試す'; banner(e.message); });
  }
  function sysCard(s) {
    var c = s.counts || {};
    return '<li class="im-card"><button type="button" class="im-card-main" data-sid="' + esc(s.id) + '" aria-label="' + esc(s.name) + ' を開く">' +
      '<span class="im-card-name">' + esc(s.name) + '</span><span class="im-card-desc">' + esc(s.description || '説明なし') + '</span>' +
      '<span class="im-card-foot"><span class="pill p-new">' + esc(ROLE[s.role || s.my_role] || '') + '</span>' +
      '<span>文書 ' + (c.documents || 0) + '</span><span>変更要求 ' + (c.crs || 0) + '</span><span>' + fmtDate(s.updated_at || s.created_at) + '</span></span>' +
      '</button></li>';
  }
  function heroHtml() {
    return '<div class="dash-hero"><div class="dash-hero-main"><h1 class="dash-hero-title">仕様の変更から、テストすべき影響範囲を洗い出す</h1>' +
      '<p class="dash-hero-sub">対象システムごとに文書・ベースライン・項目のつながりを持ち、変更要求ごとに影響・リスク・確かめるテストを根拠つきで示します。</p>' +
      '<div class="dash-hero-steps" aria-label="影響度分析の流れ"><span class="dash-hero-step"><b>1</b> 文書を取り込む</span><span class="dash-hero-arrow" aria-hidden="true">→</span>' +
      '<span class="dash-hero-step"><b>2</b> 変更要求を起票して分析</span><span class="dash-hero-arrow" aria-hidden="true">→</span><span class="dash-hero-step"><b>3</b> 影響を解消して承認</span></div>' +
      '<div class="im-hero-actions"><button type="button" class="btn-primary dash-hero-start" data-act="new-sys">新しい対象システム</button>' +
      '<button type="button" class="btn-sample-report" data-act="sample">見本で試す<span class="sample-zero">文書なし</span></button></div></div></div>';
  }
  function renderHome(root) {
    setTitle('', '対象システム一覧');
    root.innerHTML = heroHtml() + '<div class="dashboard-section-head"><div><h2 class="dash-section-title">対象システム</h2>' +
      '<p class="dashboard-section-copy">役割を持っている対象システムだけを表示します。</p></div><div class="dashboard-section-actions">' +
      '<button type="button" class="btn-outline-sm" data-act="reload">再読み込み</button></div></div><div id="im-home-body"></div>';
    bindHome(root);
    var body = $('#im-home-body'); loading(body);
    api.systems().then(function (d) {
      var rows = api.list(d, 'systems');
      var site = state.site;
      if (!rows.length) {
        body.innerHTML = empty({ title: 'まだ対象システムがありません', desc: '対象システムを作って文書を取り込むと、変更要求ごとに影響を分析できます。',
          steps: [['対象システムを作る', '名前と説明を入れる'], ['文書を取り込む', '要件・設計書・テストケース'], ['変更要求を分析する', '影響とテストを確認']],
          actions: '<button type="button" class="btn-primary im-bigbtn" data-act="new-sys">新しい対象システム</button>' +
            '<button type="button" class="btn-sample-report" data-act="sample">見本で試す<span class="sample-zero">文書なし</span></button>' });
        if (site) body.insertBefore(siteCandidates(site, rows), body.firstChild);
        bindHome(body); return;
      }
      body.innerHTML = '<ul class="im-cards">' + rows.map(sysCard).join('') + '</ul>';
      if (site) body.insertBefore(siteCandidates(site, rows), body.firstChild);
      // サイトを渡されて開いたときは、選んだ対象システムの「コード依存」をそのサイトで開く（関連付けはしない）
      $$('[data-sid]', body).forEach(function (b) { b.addEventListener('click', function () { go(site ? { sid: b.dataset.sid, tab: 'rea', site: site } : { sid: b.dataset.sid }); }); });
    }, function (e) { failed(body, e, function () { renderHome(root); }); });
  }
  /* サイト（指揮などからの deep link）に対応する対象システムの候補。人が関連付けたもの（code_site）だけを候補にし、
     名前の一致などで自動に同一視しない。選ぶのは人。 */
  function siteCandidates(site, rows) {
    var cands = rows.filter(function (r) { return r.code_site && r.code_site === site; });
    var box = document.createElement('section');
    box.className = 'bt-card im-site-cand';
    box.setAttribute('aria-labelledby', 'im-site-cand-t');
    box.innerHTML = '<h2 class="dash-section-title" id="im-site-cand-t">サイト <code>' + esc(site) + '</code> から開きました</h2>' +
      '<p class="bt-hint">サイトと対象システムは自動で同一視しません。候補から選ぶか、下の一覧から選んでください。選ぶと、その対象システムの「コード依存」をこのサイトで開きます。</p>' +
      (cands.length ? '<p>このサイトを人が関連付けた対象システム（候補 ' + cands.length + ' 件）:</p><ul class="im-site-cand-list">' + cands.map(function (r) {
        return '<li><button type="button" class="btn-outline-sm" data-cand="' + esc(r.id) + '">' + esc(r.name) + ' のコード依存を開く</button></li>'; }).join('') + '</ul>'
        : '<p>このサイトを関連付けた対象システムはありません（候補 0 件）。一覧から選び、「コード依存」で管理者が関連付けられます。</p>');
    $$('[data-cand]', box).forEach(function (b) { b.addEventListener('click', function () { go({ sid: b.dataset.cand, tab: 'rea', site: site }); }); });
    return box;
  }
  function bindHome(el) {
    $$('[data-act=new-sys]', el).forEach(function (b) { b.addEventListener('click', newSystem); });
    $$('[data-act=sample]', el).forEach(function (b) { b.addEventListener('click', function () { trySample(b); }); });
    $$('[data-act=reload]', el).forEach(function (b) { b.addEventListener('click', render); });
  }

  /* ---------- ガイド（System 09 専用。他システムへ遷移しない） ---------- */
  function renderGuide(root) {
    setTitle('', 'ユーザーガイド');
    var card = function (t, items) { return '<div class="bt-card"><h3>' + t + '</h3><ul class="bt-list">' + items.map(function (i) { return '<li>' + i + '</li>'; }).join('') + '</ul></div>'; };
    root.innerHTML = '<div class="im-guide"><div class="bt-card"><h2>影響度分析の使い方</h2><p>仕様の変更が、どの要件・設計書・画面・既存テストに波及するかを洗い出し、リスクとテストの優先度を根拠つきで示します。</p></div>' +
      '<div class="bt-grid2">' + card('流れ', ['<b>文書</b>: 対象システムに要件・設計書・画面仕様書・テストケースを取り込みます。', '<b>ベースライン</b>: その時点の文書を版名つきで固定します。2 版の差分も見られます。',
        '<b>つながり</b>: 関係する 2 項目を登録します。候補を採用することもできます。', '<b>変更要求</b>: 題名・理由と、変更内容（文章か変更前後のベースライン）を入れて「分析する」を押します。',
        '<b>影響</b>: 影響ごとに「対応要」「対応不要」を理由つきで決めます。要確認が 0 件になればレビューに回せます。', '<b>承認</b>: 承認者が承認または差し戻します。']) +
      card('リスクと優先度', ['リスク値 R ＝ 影響度 I（1〜4）× 発生可能性 L（1〜3）。', '設定の閾値で P1・P2・P3 に分けます。P1 から順にテストします。',
        '値を直すときは理由が必須です。直した値と担当者を記録し、優先度を再計算します。', '根拠は「つながり」「意味検索」「語の一致」「LLM 判定」の種別と本文で示します。']) + '</div>' +
      '<div class="bt-grid2">' + card('役割', ['<b>管理者</b>: 設定・メンバー・すべての操作。', '<b>分析担当</b>: 文書・ベースライン・つながり・変更要求・分析・解消。',
        '<b>承認者</b>: 承認・差し戻し・監査ログの閲覧。', '<b>閲覧者</b>: 見るだけ。']) +
      card('うまくいかないとき', ['分析が「縮退」と出る: LLM・埋め込みが使えないため語の一致で分析しました。設定の送信方針と接続先を確認してください。',
        '影響が少なすぎる: 文書かつながりが足りません。取り込むかつながりを登録してから再分析してください。',
        '文書が取り込めない: 文書ごとに理由が出ます。形式や大きさを直して取り込み直してください。', 'ボタンが出ない: 役割が足りません。管理者に役割の付与を依頼してください。']) + '</div></div>';
  }

  /* ---------- 起動 ---------- */
  function initShell() {
    $$('.app-nav-item').forEach(function (b) {
      b.addEventListener('click', function () {
        if (b.dataset.nav === 'home') go({});
        else if (b.dataset.nav === 'guide') go({ view: 'guide' });
        else if (b.dataset.scope === 'sys') go({ sid: state.sid, tab: b.dataset.tab === 'overview' ? '' : b.dataset.tab });
        else if (b.dataset.scope === 'cr') go({ sid: state.sid, cr: state.cr, tab: b.dataset.tab === 'changes' ? '' : b.dataset.tab });
      });
    });
    $('[data-act=new-sys-side]').addEventListener('click', newSystem);
    $('#im-modal-cancel').addEventListener('click', closeModal);
    $('#im-modal').addEventListener('click', function (e) { if (e.target.id === 'im-modal') closeModal(); });
    var KEY = 'webspec2doc.sidebar-collapsed', shell = $('.app-shell'), tg = $('#sidebar-toggle-btn');
    var apply = function (c) { shell.classList.toggle('sidebar-collapsed', c); tg.title = c ? 'サイドバーを広げる' : 'サイドバーを折りたたむ'; tg.setAttribute('aria-label', tg.title); tg.setAttribute('aria-expanded', String(!c)); };
    try { apply(localStorage.getItem(KEY) === '1'); } catch (_) { apply(false); }
    tg.addEventListener('click', function () { var c = !shell.classList.contains('sidebar-collapsed'); apply(c); try { localStorage.setItem(KEY, c ? '1' : '0'); } catch (_) { /* 保存できなくても表示は切り替える */ } });
    window.addEventListener('popstate', render);
  }

  IM.ui = { $: $, $$: $$, esc: esc, fmtDate: fmtDate, STATUS: STATUS, ROLE: ROLE, KIND: KIND, POLICY: POLICY, can: can,
    statusBadge: statusBadge, priBadge: priBadge, loading: loading, failed: failed, empty: empty, toast: toast, banner: banner,
    modal: modal, confirm: confirmBox, closeModal: closeModal, need: need, setTitle: setTitle };
  IM.app = { go: go, render: render, state: state, refreshSystem: refreshSystem };

  // DEF-009: ブラウザ標準の英語の入力エラーを日本語にする
  document.addEventListener('invalid', function (e) {
    var t = e.target;
    if (t && t.validity && t.validity.valueMissing) t.setCustomValidity(t.tagName === 'SELECT' || t.type === 'radio' ? '選んでください。' : '入力してください。');
  }, true);
  document.addEventListener('input', function (e) { if (e.target && e.target.setCustomValidity) e.target.setCustomValidity(''); }, true);
  document.addEventListener('change', function (e) { if (e.target && e.target.setCustomValidity) e.target.setCustomValidity(''); }, true);

  document.addEventListener('DOMContentLoaded', function () { initShell(); render(); });
})();
