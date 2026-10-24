/* ============================================================================
 * TA2 / app.js — 起動と全体配線（FE-A 所有）
 * 読み込み順の最後。TA2.boot() を定義して即実行する。
 * ========================================================================== */
(function () {
  'use strict';
  var T = window.TA2, S = T.state, $ = T.$, $$ = T.$$;

  /** ワークスペース（URL パス）→ 初期 view */
  var WS_VIEW = {
    home: 'home', spec: 'spec', tests: 'test', changes: 'drift',
    schedule: 'schedule', report: 'report', team: 'team'
  };

  function bodyWs() {
    return (document.body.dataset.ws || 'home');
  }

  /** 対象ドメイン。パス（/sites/<domain>/…）が正で、?domain= は後方互換 */
  function paramDomain() {
    var d = document.body.dataset.domain || '';
    if (d) return d;
    try { return new URLSearchParams(location.search).get('domain') || ''; }
    catch (e) { return ''; }
  }

  /** ハッシュから初期の view と選択 id を取り出す（tests 読み込み前でも使える） */
  function parseHash() {
    var m = /^#\/(tests|run|drift|site|map|home|spec|schedule|report|team)(?:\/(.+))?$/.exec(location.hash || '');
    if (!m) return { view: null, id: null, hashed: false };
    var v = m[1] === 'tests' ? 'test' : (m[1] === 'map' ? 'site' : m[1]);
    return { view: v, id: m[2] ? decodeURIComponent(m[2]) : null, hashed: true };
  }

  /** 初期 view。ハッシュがあればそれが優先、無ければパスの ws から決める */
  function initialView() {
    var h = parseHash();
    if (h.hashed) return h.view;
    return WS_VIEW[bodyWs()] || 'test';
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

  /** 一覧ヘッダの下に、消えない案内を 1 本だけ置く（list.js は触らない領域） */
  function notice(msg) {
    var host = document.querySelector('.list-h');
    if (!host) { T.toast(msg, 'ng'); return; }
    var box = $('#ta2-notice');
    if (!box) {
      box = document.createElement('div');
      box.id = 'ta2-notice';
      box.style.cssText = 'margin:8px 0 0;padding:8px 10px;border-radius:8px;background:var(--wa-bg);'
        + 'color:var(--wa-tx);font-size:11.5px;line-height:1.6';
      host.appendChild(box);
    }
    box.textContent = msg;
    // サイトを選び直せるように、候補が 1 件でも選択欄は出す
    var sel = $('#site-sel');
    if (sel) sel.style.display = '';
  }

  /** レール下部のアカウントメニュー（Escape / 外側クリックで閉じる） */
  function bindUserMenu() {
    var btn = $('#user-btn'), pop = $('#user-pop');
    if (!btn || !pop) return;
    function setOpen(v) {
      pop.hidden = !v;
      btn.setAttribute('aria-expanded', v ? 'true' : 'false');
      if (v) { var f = pop.querySelector('a,button'); if (f) f.focus(); }
    }
    btn.addEventListener('click', function (e) { e.stopPropagation(); setOpen(pop.hidden); });
    document.addEventListener('click', function (e) {
      if (pop.hidden) return;
      if (e.target.closest && e.target.closest('#ta-user')) return;
      setOpen(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape' || pop.hidden) return;
      setOpen(false);
      btn.focus();
    });
  }

  function bindRail() {
    $$('.ws-rail [data-view]').forEach(function (b) {
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
      if (!h.hashed) return;
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
    bindUserMenu();

    var h = parseHash();
    var ws = bodyWs();
    var wanted = paramDomain();

    // ホームとチームはサイト一覧だけで成立する。チームはワークスペース全体の
    // 設定で、サイトが 1 件も無いテナントでも開けなければ同僚を招けない。
    if (ws === 'home' || (ws === 'team' && !wanted)) {
      return T.loadSites().catch(function () { S.sites = []; return S.sites; }).then(function () {
        S.ready = true;
        T.setDomain('');
        T.setView(ws === 'team' ? 'team' : 'home');
        T.render();
        T.emit('boot');
      });
    }

    return T.loadSites().then(function (sites) {
      var domain = '';
      sites.forEach(function (s) { if (s.domain === wanted) domain = s.domain; });
      if (!domain && wanted) {
        // 指定されたサイトが見つからないときだけ戻す。何を見ているのか
        // 分からないまま別サイトを出さない。
        location.replace('/');
        return null;
      }
      // domain 指定なしで開いた場合（/test-automation など）はこの画面に留まる。
      if (!domain) return null;
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
      T.setView(initialView());
      T.render();
      T.emit('boot');
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
