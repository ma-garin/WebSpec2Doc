/* ============================================================================
 * TA2 / app.js — 起動と全体配線（FE-A 所有）
 * 読み込み順の最後。TA2.boot() を定義して即実行する。
 * ========================================================================== */
(function () {
  'use strict';
  var T = window.TA2, S = T.state, $ = T.$, $$ = T.$$;

  function paramDomain() {
    try { return new URLSearchParams(location.search).get('domain') || ''; }
    catch (e) { return ''; }
  }

  /** ハッシュから初期の view と選択 id を取り出す（tests 読み込み前でも使える） */
  function parseHash() {
    var m = /^#\/(tests|run|drift|site)(?:\/(.+))?$/.exec(location.hash || '');
    if (!m) return { view: 'test', id: null };
    return {
      view: m[1] === 'tests' ? 'test' : m[1],
      id: m[2] ? decodeURIComponent(m[2]) : null
    };
  }

  function fatal(msg) {
    var items = $('#items');
    if (items) {
      items.innerHTML = '<div class="it empty" style="display:block;padding:16px;line-height:1.7">'
        + '<b>' + T.esc(msg) + '</b></div>';
    }
    var box = $('#ed-h');
    if (box) box.innerHTML = '<h1>読み込めませんでした</h1>';
    T.toast(msg, 'ng');
  }

  function bindRail() {
    $$('.rail [data-view]').forEach(function (b) {
      b.addEventListener('click', function () {
        T.setView(b.dataset.view);
        T.render();
      });
    });
  }

  function bindReset() {
    var btn = $('#reset-btn');
    if (!btn) return;
    btn.addEventListener('click', function () {
      btn.disabled = true;
      reloadAll().then(function () {
        btn.disabled = false;
        T.toast('サーバから読み直しました', 'ok');
      }, function (e) {
        btn.disabled = false;
        T.toast(e.message, 'ng');
      });
    });
  }

  function bindHash() {
    window.addEventListener('hashchange', function () {
      if (T.isHashLocked()) return;
      var h = parseHash();
      if (h.view === 'test' && h.id && h.id !== S.sel && T.byId(h.id)) {
        T.select(h.id);
        return;
      }
      if (h.view !== S.view) {
        T.setView(h.view);
        T.render();
      }
    });
  }

  function bindOverlayEscape() {
    // modals.js も同じことをするが、二重に閉じても害はない
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      $$('.ov.on').forEach(function (o) { o.classList.remove('on'); });
    });
  }

  function reloadAll() {
    return T.loadTests().then(function () {
      T.render();
      return Promise.all([T.loadDrift(), T.loadMap(), T.loadRuns()]);
    }).then(function () {
      T.render();
    });
  }

  function boot() {
    bindRail();
    bindReset();
    bindHash();
    bindOverlayEscape();

    var h = parseHash();
    var wanted = paramDomain();

    return T.loadSites().then(function (sites) {
      if (!sites.length) {
        fatal('クロール済みのサイトがありません。先にドキュメント作成でサイトを取り込んでください。');
        return null;
      }
      var domain = '';
      sites.forEach(function (s) { if (s.domain === wanted) domain = s.domain; });
      if (!domain) domain = sites[0].domain;
      T.setDomain(domain);
      return T.loadTests();
    }).then(function (r) {
      if (!r) return null;
      S.ready = true;
      if (h.id && T.byId(h.id)) S.sel = h.id;
      var t = T.current();
      if (t) {
        var last = t.last || {};
        var n = (t.steps || []).length;
        S.step = (last.step !== null && last.step !== undefined) ? last.step : 0;
        if (S.step >= n) S.step = Math.max(0, n - 1);
        S.mode = t.status === 'fail' ? 'fail' : 'now';
      }
      T.setView(h.view);
      T.render();
      // 一覧が出たあとで、パネル用のデータを取りに行く
      return Promise.all([T.loadDrift(), T.loadMap(), T.loadRuns()]).then(function () {
        T.render();
        return T.api.runStatus(S.domain).then(function (st) {
          S.run = st || S.run;
          if (st && st.running) T.startPolling();
          else T.emit('run');
        }, function () { /* 実行状態が取れなくても画面は使える */ });
      });
    }).catch(function (e) {
      S.ready = true;
      fatal(e.message || '読み込みに失敗しました');
    });
  }

  T.boot = boot;
  T.reloadAll = reloadAll;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
