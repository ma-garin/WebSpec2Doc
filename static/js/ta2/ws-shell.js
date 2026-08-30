/* ============================================================================
 * TA2 / ws-shell.js — 統合ワークスペースの左ペイン切替（A4）
 *
 * 左ペイン .list は view ごとに中身が変わる。切替を行うのはこのファイルだけ。
 *   home         … #site-items  + #list-f-home
 *   spec / site  … #screen-items
 *   test / run   … 既存の検索・チップ・#items + #list-f-tests
 *   その他       … #ctx-card（選択中サイトの要約）
 *
 * 既存 list.js は 'render' / 'tests' でヘッダを書き換えるため、こちらは同じ
 * イベントに後から乗って上書きする（読み込み順が list.js より後）。
 * ========================================================================== */
(function () {
  'use strict';
  var T = window.TA2, S = T.state, $ = T.$, esc = T.esc;

  /** ホーム以外の view → URL パスの末尾 */
  var WS_PATH = {
    spec: 'spec', site: 'spec', test: 'tests', run: 'tests',
    drift: 'changes', schedule: 'schedule', report: 'report', team: 'team'
  };
  var TITLE_OF = {
    home: 'サイト', spec: '画面', site: '画面',
    drift: '変更', schedule: '定期実行と通知', report: '報告', team: 'チーム'
  };

  function setHidden(sel, hide) {
    var el = $(sel);
    if (el) el.hidden = !!hide;
  }

  function modeOf(v) {
    if (v === 'home') return 'home';
    if (v === 'spec' || v === 'site') return 'spec';
    if (v === 'test' || v === 'run') return 'tests';
    return 'ctx';
  }

  function applyListMode(view) {
    var m = modeOf(view || S.view);

    setHidden('#site-items', m !== 'home');
    setHidden('#site-search', m !== 'home');
    setHidden('#list-f-home', m !== 'home');
    setHidden('#screen-items', m !== 'spec');
    setHidden('#ctx-card', m !== 'ctx');
    setHidden('#items', m !== 'tests');
    setHidden('#list-f-tests', m !== 'tests');
    setHidden('#fchips', m !== 'tests');
    /* テスト用の検索欄は #q を持つ方だけ。ホームの絞り込み（#site-search）と
       取り違えないよう、クラスではなく #q から親をたどる */
    var qi = $('#q');
    var search = qi && qi.closest ? qi.closest('.search') : null;
    if (search) search.hidden = m !== 'tests';

    var name = $('#site-name');
    if (name) name.textContent = m === 'home' ? 'サイト' : (S.domain || 'サイト');

    if (m === 'tests') return; // 件数と絞り込み導線は list.js が書く

    var cnt = $('#cnt-all');
    if (cnt) cnt.textContent = '';
    var sub = $('#list-sub');
    if (sub) sub.textContent = subFor(m, view || S.view);
    if (m === 'ctx') renderCtx();
  }

  function subFor(m, view) {
    if (m === 'home') {
      var n = (S.history || []).length;
      return n ? n + ' サイト' : '';
    }
    if (m === 'spec') {
      var s = (S.spec && S.spec.report && S.spec.report.screens) || S.map || [];
      return s.length ? s.length + ' 画面' : '';
    }
    return TITLE_OF[view] || '';
  }

  /* ------------------------------------------------- 選択中サイトの要約カード */
  function historyItem(domain) {
    var items = S.history || [];
    for (var i = 0; i < items.length; i++) if (items[i].domain === domain) return items[i];
    return null;
  }

  function renderCtx() {
    var box = $('#ctx-card');
    if (!box) return;
    var it = historyItem(S.domain);
    if (!it) {
      box.innerHTML = '<h4>' + esc(S.domain || 'サイト') + '</h4>'
        + '<dl><dt>状態</dt><dd>解析結果を読み込んでいます…</dd></dl>';
      loadHistory().then(function () { if (modeOf(S.view) === 'ctx') renderCtx(); });
      return;
    }
    var fails = 0;
    S.tests.forEach(function (t) { if (t.status === 'fail') fails++; });
    box.innerHTML = '<h4>' + esc(it.domain) + '</h4><dl>'
      + '<dt>対象</dt><dd>' + esc(it.site_url || '（記録なし）') + '</dd>'
      + '<dt>画面</dt><dd>' + esc(it.screens) + '</dd>'
      + '<dt>テスト</dt><dd>' + esc(S.tests.length) + '（失敗 ' + fails + '）</dd>'
      + '<dt>最終解析</dt><dd>' + esc(it.updated || '—') + '</dd>'
      + '</dl><a class="btn" id="ctx-spec" style="width:100%;justify-content:center;margin-top:10px" href="'
      + '/sites/' + encodeURIComponent(it.domain) + '/spec">仕様を開く</a>';
  }

  /** 解析履歴（/api/history）。ホームと要約カードで共有するので state に持つ */
  var loading = null;
  function loadHistory(force) {
    if (S.history && !force) return Promise.resolve(S.history);
    if (loading) return loading;
    loading = T.api.get('/api/history').then(function (r) {
      S.history = (r && r.items) || [];
      loading = null;
      T.emit('history', S.history);
      return S.history;
    }, function () {
      S.history = S.history || [];
      loading = null;
      return S.history;
    });
    return loading;
  }

  /* ----------------------------------- ホームから他の WS へ移るときのサイト解決
   * ホーム（対象サイト未確定）でレールを押したときだけ、選択中サイトの URL へ移す。
   * 'view' イベントではなくクリックで判定するのは、他モジュールの setView() を
   * 勝手なページ遷移に化けさせないため。 */
  function bindRailFromHome() {
    var rail = document.querySelector('.rail');
    if (!rail) return;
    rail.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('[data-view]');
      if (!b) return;
      var v = b.dataset.view;
      if (v === 'home' || S.domain) return;   // 対象サイトが決まっていれば SPA のまま
      var seg = WS_PATH[v];
      if (!seg) return;
      e.stopPropagation();                    // app.js の setView を走らせない
      e.preventDefault();
      var d = (T.wsHomeDomain && T.wsHomeDomain()) || '';
      if (!d) {
        T.toast('先に URL を入れてサイトを取り込んでください', 'ng');
        return;
      }
      location.assign('/sites/' + encodeURIComponent(d) + '/' + seg);
    }, true);
  }

  T.state.history = null;
  T.loadHistory = loadHistory;
  T.historyItem = historyItem;

  bindRailFromHome();

  T.on('view', applyListMode);
  T.on('render', function () { applyListMode(S.view); });
  T.on('tests', function () { applyListMode(S.view); });
  T.on('history', function () { applyListMode(S.view); });
  T.on('boot', function () {
    applyListMode(S.view);
    loadHistory().then(function () { applyListMode(S.view); });
  });
})();
