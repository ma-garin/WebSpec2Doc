/* ============================================================================
 * TA2 / state.js — 全モジュール共有の状態・API・イベントバス（FE-A 所有）
 *
 * 読み込み順: state → list → editor → viewer → panels → modals → app
 *
 * FE-B（panels.js / modals.js）が使う公開 API:
 *   TA2.state    … 下の state を直接読む（書き換えは TA2 のヘルパ経由で）
 *   TA2.api.*    … fetch ラッパ。応答に error キーがあれば throw new Error(error)
 *   TA2.on(evt, fn) / TA2.off(evt, fn) / TA2.emit(evt, payload) / TA2.has(evt)
 *   TA2.select(id) / TA2.setView('test'|'run'|'drift'|'site')
 *   TA2.toast(msg, 'ok'|'ng'|'') / TA2.render()
 *
 * イベント:
 *   'render' 全再描画 / 'tests' / 'select' / 'view' / 'run' / 'drift' / 'map' / 'toast'
 *   'new'   {screen}  … 「＋ 新しいテスト」要求（modals.js が受けて #ov-new を開く）
 *   'trace' {test}    … Trace 要求（modals.js が受けて #ov-trace を開く）
 *                       listener が居ないときは editor.js が trace ファイルを直接開く
 *
 * 描画ヘルパ:
 *   TA2.repaint(fn) … 同一フレーム内の重複呼び出しを 1 回にまとめた関数を返す。
 *                     TA2.on('render', draw) と TA2.on('tests', draw) を両方張ってよい。
 *
 * 状態の永続化は URL ハッシュのみ（#/tests/<id> #/run #/drift #/site）。
 * localStorage は使わない。サーバが正。
 * ========================================================================== */
(function () {
  'use strict';

  var $ = function (s, root) { return (root || document).querySelector(s); };
  var $$ = function (s, root) { return Array.prototype.slice.call((root || document).querySelectorAll(s)); };
  var enc = encodeURIComponent;

  function esc(s) {
    return String(s === null || s === undefined ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  var stabLabel = { high: '安定 高', mid: '安定 中', low: '安定 低' };
  var statusLabel = {
    pass: '成功', fail: '失敗', flaky: '不安定',
    'new': '未実行', fixed: '修正済 · 未実行', running: '実行中'
  };

  /* ---------------------------------------------------------------- state */
  var state = {
    domain: '',
    sites: [],          // [{domain,name,screens,tests,fails,last_run_at}]
    tests: [],          // [Test]（契約 §2）
    elements: {},       // {P004:{name:{key,label,type,loc,stab}, …}}
    screens: [],        // [{id,name,path}]
    sel: null,
    step: 0,
    mode: 'now',        // 'fail' | 'expect' | 'now'
    filter: 'all',
    q: '',
    view: 'test',
    run: { running: false, run_id: null, total: 0, done: 0, passed: 0, failed: 0, current_id: null, tests: [], skipped: [] },
    runs: [],           // [{run_id,at,passed,failed,total,duration_ms}]
    drift: [],          // [{id,kind,screen,title,old,now,impact,fix,state}]（契約どおり配列）
    // ペイロード全体（reason / baseline_at / current_at）はここに保つ。
    // items が空でも「差分なし」と「基準なし」は別物なので、reason を捨てない（B-4）
    driftMeta: { baseline_at: null, current_at: null, reason: '', loaded: false },
    map: [],            // [{id,name,path,tests,fails,coverage,gaps:[…]}]
    ready: false
  };

  /* ------------------------------------------------------------------ bus */
  var bus = {};
  function on(evt, fn) {
    (bus[evt] = bus[evt] || []).push(fn);
    return function () { off(evt, fn); };
  }
  function off(evt, fn) {
    var a = bus[evt];
    if (!a) return;
    var i = a.indexOf(fn);
    if (i >= 0) a.splice(i, 1);
  }
  function emit(evt, payload) {
    (bus[evt] || []).slice().forEach(function (fn) {
      try { fn(payload); } catch (e) { console.error('[TA2] ' + evt, e); }
    });
  }
  function has(evt) { return !!(bus[evt] && bus[evt].length); }

  /** 同一フレーム内の重複呼び出しを 1 回にまとめる */
  function repaint(fn) {
    var queued = false;
    return function () {
      if (queued) return;
      queued = true;
      requestAnimationFrame(function () {
        queued = false;
        try { fn(); } catch (e) { console.error('[TA2] repaint', e); }
      });
    };
  }

  /* ------------------------------------------------------------------ api */
  function request(method, url, body) {
    var opt = { method: method, credentials: 'same-origin', headers: { 'Accept': 'application/json' } };
    if (body !== undefined) {
      opt.headers['Content-Type'] = 'application/json';
      opt.body = JSON.stringify(body);
    }
    return fetch(url, opt).then(
      function (res) {
        var ct = res.headers.get('content-type') || '';
        if (ct.indexOf('json') < 0) {
          if (!res.ok) throw new Error('通信に失敗しました（HTTP ' + res.status + '）');
          throw new Error('サーバの応答を解釈できませんでした');
        }
        return res.json().then(function (json) {
          if (json && json.error) throw new Error(json.error);
          if (!res.ok) throw new Error('通信に失敗しました（HTTP ' + res.status + '）');
          return json;
        }, function () {
          throw new Error('サーバの応答を解釈できませんでした');
        });
      },
      function () { throw new Error('サーバに接続できませんでした'); }
    );
  }
  var GET = function (u) { return request('GET', u); };
  var POST = function (u, b) { return request('POST', u, b || {}); };

  var api = {
    /* ws-*.js が /api/ta2 以外の既存 API を叩くための素の口。応答の error は throw される */
    get: GET,
    post: POST,
    sites: function () { return GET('/api/ta2/sites'); },
    tests: function (d) { return GET('/api/ta2/tests?domain=' + enc(d)); },
    create: function (d, body) { return POST('/api/ta2/tests', Object.assign({ domain: d }, body || {})); },
    update: function (d, id, body) { return request('PUT', '/api/ta2/tests/' + enc(id), Object.assign({ domain: d }, body || {})); },
    remove: function (d, id) { return request('DELETE', '/api/ta2/tests/' + enc(id) + '?domain=' + enc(d)); },
    duplicate: function (d, id) { return POST('/api/ta2/tests/' + enc(id) + '/duplicate', { domain: d }); },
    fix: function (d, id, step) { return POST('/api/ta2/tests/' + enc(id) + '/fix', { domain: d, step: step }); },
    run: function (d, ids) { return POST('/api/ta2/run', { domain: d, ids: ids || [] }); },
    runStatus: function (d) { return GET('/api/ta2/run/status?domain=' + enc(d)); },
    cancel: function (d) { return POST('/api/ta2/run/cancel', { domain: d }); },
    runs: function (d) { return GET('/api/ta2/runs?domain=' + enc(d)); },
    map: function (d) { return GET('/api/ta2/map?domain=' + enc(d)); },
    drift: function (d) { return GET('/api/ta2/drift?domain=' + enc(d)); },
    driftApply: function (d, id) { return POST('/api/ta2/drift/' + enc(id) + '/apply', { domain: d }); },
    driftDismiss: function (d, id) { return POST('/api/ta2/drift/' + enc(id) + '/dismiss', { domain: d }); },
    recrawl: function (d) { return POST('/api/ta2/recrawl', { domain: d }); },
    /** 証跡ファイルの URL（kind: 'trace' | 'screenshot' | 'report'） */
    artifactUrl: function (d, id, kind) {
      return '/api/ta2/artifact?domain=' + enc(d) + '&id=' + enc(id) + '&kind=' + enc(kind);
    },
    /** クロール時の画面キャプチャ URL */
    screenshotUrl: function (d, screen) {
      return '/api/ta2/screenshot?domain=' + enc(d) + '&screen=' + enc(screen);
    }
  };

  /* -------------------------------------------------------------- helpers */
  function byId(id) {
    for (var i = 0; i < state.tests.length; i++) if (state.tests[i].id === id) return state.tests[i];
    return null;
  }
  function current() { return byId(state.sel); }
  function screenOf(id) {
    for (var i = 0; i < state.screens.length; i++) if (state.screens[i].id === id) return state.screens[i];
    return { id: id, name: id, path: '' };
  }
  function stepsOf(t) { return (t && t.steps) || []; }

  /** toast(msg, cls, action)
   *  action = {label, fn} … 取り消しなど、その場でやり直せる操作を 1 つだけ添える。
   *  操作付きのときは消えるまでを長めにする（読んで押す時間が要るため）。 */
  function toast(msg, cls, action) {
    var box = $('#toasts');
    if (box) {
      var d = document.createElement('div');
      d.className = 'toast ' + (cls || '');
      var s = document.createElement('span');
      s.textContent = msg;
      d.appendChild(s);
      if (action && action.label && typeof action.fn === 'function') {
        var b = document.createElement('button');
        b.className = 'tact';
        b.type = 'button';
        b.textContent = action.label;
        b.addEventListener('click', function () { d.remove(); action.fn(); });
        d.appendChild(b);
      }
      box.appendChild(d);
      setTimeout(function () { d.remove(); }, action ? 7000 : 2600);
    }
    emit('toast', { msg: msg, cls: cls || '' });
  }

  /* ----------------------------------------------------------- navigation */
  var hashLock = false;

  /** view → URL パス。同じパスを共有する view はハッシュで見分ける（hashFor）。 */
  var PATH_OF = {
    home: null,           // 常に '/'
    spec: 'spec', site: 'spec',
    test: 'tests', run: 'tests',
    drift: 'changes',
    schedule: 'schedule', report: 'report', team: 'team'
  };
  /** レールのボタンは親の WS に寄せる（地図は仕様の中、実行結果はテストの中） */
  var RAIL_OF = { site: 'spec', run: 'test' };

  /* テスト自動化専用シェル（/test-automation）で開いたか。
     ここで開いた画面の URL を "/" に書き換えると、リロード・ブックマーク・
     共有で /dashboard（ドキュメント作成）に着地してしまい、元の画面に戻れない。 */
  function isTestOnly() {
    return document.body && document.body.dataset.mode === 'test-only';
  }

  function pathFor(v) {
    var seg = PATH_OF[v];
    var home = isTestOnly() ? '/test-automation' : '/';
    if (!seg) return home;
    /* チームはワークスペース全体の設定で、サイトに属さない。
       サイト未選択でもここへ入れないと、サイトが 0 件のテナントは同僚を招けない。 */
    if (!state.domain) return v === 'team' ? '/team' : home;
    return '/sites/' + enc(state.domain) + '/' + seg;
  }

  function hashFor() {
    if (state.view === 'test') return state.sel ? '#/tests/' + state.sel : '';
    if (state.view === 'run') return '#/run';
    if (state.view === 'site') return '#/map';
    return '';
  }

  /** パスとハッシュを現在の view に合わせる。
      画面（view）が変わったときは pushState（戻るで前の画面へ）、同じ画面内の選択（テスト切替など）は replaceState。
      起動時・戻る/進むによる復元では履歴を積まない。 */
  var lastSyncedView = null;
  var restoring = false;
  function syncUrl() {
    var want = pathFor(state.view) + hashFor();
    var push = !restoring && lastSyncedView !== null && lastSyncedView !== state.view;
    lastSyncedView = state.view;
    if (location.pathname + location.hash === want) return;
    hashLock = true;
    try { history[push ? 'pushState' : 'replaceState'](null, '', want); }
    catch (e) { location.hash = hashFor(); }
    setTimeout(function () { hashLock = false; }, 0);
  }

  /** 戻る・進む: URL（ハッシュ→無ければパス）から view を復元する。履歴は積まない */
  var VIEW_OF_SEG = { spec: 'spec', tests: 'test', changes: 'drift', schedule: 'schedule', report: 'report', team: 'team' };
  function restoreFromUrl() {
    var v = null;
    if (readHash()) { v = state.view; }
    else {
      var seg = (location.pathname.replace(/\/+$/, '').split('/').pop() || '');
      v = VIEW_OF_SEG[seg] || (isTestOnly() ? 'test' : 'home');
      if (!document.getElementById('p-' + v)) v = state.view;
    }
    restoring = true;
    try { setView(v); render(); } finally { restoring = false; }
  }
  window.addEventListener('popstate', restoreFromUrl);

  /** URL ハッシュを読んで state.view / state.sel を決める。戻り値: 変化したか */
  function readHash() {
    var m = /^#\/(tests|run|drift|site|map|home|spec|schedule|report|team)(?:\/(.+))?$/.exec(location.hash || '');
    if (!m) return false;
    if (m[1] === 'tests') {
      state.view = 'test';
      if (m[2] && byId(decodeURIComponent(m[2]))) state.sel = decodeURIComponent(m[2]);
    } else {
      state.view = m[1] === 'map' ? 'site' : m[1];
    }
    return true;
  }
  function isHashLocked() { return hashLock; }

  function setView(v) {
    state.view = v;
    var rail = RAIL_OF[v] || v;
    $$('.ws-rail [data-view]').forEach(function (b) { b.classList.toggle('on', b.dataset.view === rail); });
    /* 非表示のビューは class だけでなく hidden も落とす。
       display:none だけだと将来のレイアウト用 display に負けて中身が
       innerText・支援技術・Playwright の可視判定に漏れる（検証ループ1 B-4）。 */
    $$('.panel').forEach(function (p) {
      var on = p.id === 'p-' + v;
      p.classList.toggle('on', on);
      p.hidden = !on;
    });
    /* テスト編集ペインはパネルの下に敷かれたまま残るため、
       テスト以外のビューでは明示的に畳む（同 B-4 の実害はここ）。 */
    var edOn = (v === 'test');
    $$('.main > .ed-h, .main > .ed-b').forEach(function (e) { e.hidden = !edOn; });
    syncUrl();
    emit('view', v);
  }

  function select(id) {
    var t = byId(id);
    if (!t) return;
    state.sel = id;
    var last = t.last || {};
    var n = stepsOf(t).length;
    state.step = (last.step !== null && last.step !== undefined) ? last.step : 0;
    if (state.step >= n) state.step = Math.max(0, n - 1);
    state.mode = t.status === 'fail' ? 'fail' : 'now';
    setView('test');
    emit('select', t);
    render();
  }

  function render() {
    emit('render');
    emit('tests');
    emit('select', current());
    emit('run');
    emit('drift');
    emit('map');
  }

  /* -------------------------------------------------------------- loaders */
  function setDomain(d) { state.domain = d || ''; }

  function loadSites() {
    return api.sites().then(function (r) {
      state.sites = (r && r.sites) || [];
      return state.sites;
    }, function (e) {
      state.sites = [];
      throw e;
    });
  }

  function loadTests() {
    return api.tests(state.domain).then(function (r) {
      state.tests = (r && r.tests) || [];
      state.elements = (r && r.elements) || {};
      state.screens = (r && r.screens) || [];
      if (!byId(state.sel)) state.sel = state.tests.length ? state.tests[0].id : null;
      emit('tests');
      return r;
    });
  }

  function loadDrift() {
    return api.drift(state.domain).then(function (r) {
      state.drift = (r && r.items) || [];
      state.driftMeta = {
        baseline_at: r && r.baseline_at ? r.baseline_at : null,
        current_at: r && r.current_at ? r.current_at : null,
        reason: (r && r.reason) || '',
        loaded: true
      };
      emit('drift');
      return r;
    }, function (e) {
      state.drift = [];
      state.driftMeta = { baseline_at: null, current_at: null, reason: e.message, loaded: true };
      emit('drift');
      return null;
    });
  }

  function loadMap() {
    return api.map(state.domain).then(function (r) {
      state.map = (r && r.screens) || [];
      emit('map');
      return r;
    }, function () {
      state.map = [];
      emit('map');
      return null;
    });
  }

  function loadRuns() {
    return api.runs(state.domain).then(function (r) {
      state.runs = (r && r.runs) || [];
      emit('run');
      return r;
    }, function () {
      state.runs = [];
      emit('run');
      return null;
    });
  }

  /* ------------------------------------------------------------- run/poll */
  var pollTimer = null;

  /* 実行の進捗は run/status が返すぶんだけ反映する。
     ステップ番号が返らない実装なら、ステップ単位の表示は付けない（捏造しない）。*/
  function applyStepProgress(st) {
    var cur = st.current_id ? byId(st.current_id) : null;
    state.tests.forEach(function (t) {
      if (t === cur) return;
      stepsOf(t).forEach(function (s) { s._run = false; s._done = false; });
    });
    if (!cur) return;
    var rt = null;
    (st.tests || []).forEach(function (x) { if (x.id === cur.id) rt = x; });
    var idx = null;
    if (st.current_step !== null && st.current_step !== undefined) idx = st.current_step;
    else if (rt && rt.step !== null && rt.step !== undefined) idx = rt.step;
    stepsOf(cur).forEach(function (s, i) {
      s._run = idx !== null && i === idx;
      s._done = idx !== null && i < idx;
    });
  }

  function pollOnce() {
    return api.runStatus(state.domain).then(function (st) {
      var prevSkipped = (state.run && state.run.skipped) || [];
      state.run = st || state.run;
      // status が skipped を返さない実装でも、開始時に受け取った除外一覧は落とさない
      if (state.run && !Array.isArray(state.run.skipped)) state.run.skipped = prevSkipped;
      (st.tests || []).forEach(function (rt) {
        var t = byId(rt.id);
        if (!t) return;
        if (rt.status) t.status = rt.status;
        if (rt.duration_ms !== null && rt.duration_ms !== undefined) {
          t.last = t.last || {};
          t.last.dur_ms = rt.duration_ms;
        }
        if (rt.error !== null && rt.error !== undefined) {
          t.last = t.last || {};
          t.last.error = rt.error;
        }
      });
      if (st.current_id) {
        var c = byId(st.current_id);
        if (c) c.status = 'running';
      }
      applyStepProgress(st);
      emit('run');
      emit('tests');
      if (!st.running) {
        stopPolling();
        return loadTests().then(function () {
          state.tests.forEach(function (t) {
            stepsOf(t).forEach(function (s) { s._run = false; s._done = false; s._ms = ''; });
          });
          render();
        });
      }
      return null;
    }, function (e) {
      stopPolling();
      toast(e.message, 'ng');
    });
  }

  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(pollOnce, 1000);
    pollOnce();
  }
  function stopPolling() {
    if (!pollTimer) return;
    clearInterval(pollTimer);
    pollTimer = null;
  }

  /** テストを実行する。ids 未指定なら全件。開始できたら 1 秒ポーリングを始める */
  function runIds(ids) {
    if (!state.domain) { toast('対象サイトが選ばれていません', 'ng'); return Promise.reject(new Error('no domain')); }
    if (state.run && state.run.running) { toast('すでに実行中です', 'ng'); return Promise.reject(new Error('running')); }
    return api.run(state.domain, ids).then(function (r) {
      state.run = {
        running: true, run_id: r.run_id, total: r.total || (ids || []).length,
        done: 0, passed: 0, failed: 0, current_id: null, tests: [],
        skipped: Array.isArray(r.skipped) ? r.skipped : []
      };
      emit('run');
      startPolling();
      if (state.run.skipped.length) {
        toast('実行できなかったテストが ' + state.run.skipped.length + ' 件あります', 'ng');
      }
      return r;
    }, function (e) {
      toast(e.message, 'ng');
      throw e;
    });
  }

  function cancelRun() {
    return api.cancel(state.domain).then(function (r) {
      toast('実行を中止しました');
      return r;
    }, function (e) {
      toast(e.message, 'ng');
      throw e;
    });
  }

  /* --------------------------------------------------------------- export */
  window.TA2 = {
    state: state,
    api: api,
    on: on, off: off, emit: emit, has: has,
    select: select, setView: setView, toast: toast, render: render,
    boot: null, // app.js が入れる

    // 共有ヘルパ（FE-B も使ってよい）
    $: $, $$: $$, esc: esc, enc: enc,
    stabLabel: stabLabel, statusLabel: statusLabel,
    repaint: repaint,
    byId: byId, current: current, screenOf: screenOf, stepsOf: stepsOf,

    // データ読み込み
    setDomain: setDomain,
    loadSites: loadSites, loadTests: loadTests, loadDrift: loadDrift,
    loadMap: loadMap, loadRuns: loadRuns,

    // 実行
    runIds: runIds, cancelRun: cancelRun,
    startPolling: startPolling, stopPolling: stopPolling,

    // URL（パス＋ハッシュ）
    syncUrl: syncUrl, syncHash: syncUrl, pathFor: pathFor, RAIL_OF: RAIL_OF,
    readHash: readHash, isHashLocked: isHashLocked
  };
})();
