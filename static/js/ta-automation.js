// テスト自動化（System 05）のダッシュボードと実行環境画面。
//
// 方針:
//  - 数字は必ず API の実測から出す。取れないものは「—」＋理由を出し、0 と混同させない。
//  - 「まだ取得していない」「取得したが 0 件」「取得に失敗した」を別の文言で出す。
//    3 つを同じ空表示にすると、利用者は「壊れているのか、データが無いのか」を判別できない。
//  - 語彙・値はサーバから取り、画面側に二重定義しない。
(function () {
  'use strict';

  // ---- 画面登録（core.js の表へ後から足す。core.js 側は変更しない） ----------
  // core.js は VIEW_PATHS / PATH_VIEWS / VIEW_HEADER を参照して URL 復元と
  // パンくずを行う。この系の 3 画面をここで登録しないと、直リンク・リロード・
  // ブラウザの戻るでダッシュボードへ落ちる。
  var VIEWS = {
    'test-automation': { path: '/test-automation', trail: ['テスト自動化', 'ダッシュボード'], title: 'テスト自動化' },
    'test-steps': { path: '/test-steps', trail: ['テスト自動化', 'ステップ編集'], title: 'ステップ編集（ノーコード）' },
    'test-environments': { path: '/test-environments', trail: ['テスト自動化', '実行環境'], title: '実行環境' }
  };
  try {
    Object.keys(VIEWS).forEach(function (name) {
      var v = VIEWS[name];
      if (typeof VIEW_PATHS === 'object') VIEW_PATHS[name] = v.path;
      if (typeof PATH_VIEWS === 'object') PATH_VIEWS[v.path] = name;
      if (typeof VIEW_HEADER === 'object') VIEW_HEADER[name] = { trail: v.trail, title: v.title };
    });
  } catch (e) { /* core.js より先に読まれた場合。ナビからの遷移は動く */ }

  // ---- 状態 -----------------------------------------------------------------
  // sites は「未取得(null)」と「取得したが 0 件([])」を型で区別する。
  var state = { sites: null, domain: '', loading: false };

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /** JSON を取る。失敗は理由付きの Error にして呼び出し元へ返す（黙って空にしない）。 */
  function getJSON(url) {
    return fetch(url, { headers: { Accept: 'application/json' } }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) throw new Error((data && data.error) || ('HTTP ' + res.status));
        return data;
      });
    });
  }

  function message(el, text, kind) {
    if (!el) return;
    el.textContent = text || '';
    el.className = 'au-message' + (text ? ' au-' + (kind || 'info') : '');
    el.hidden = !text;
  }

  /** 統計カード 1 枚を書く。value が null なら「未計測」として「—」を出す。 */
  function setStat(id, value, note) {
    var v = $('au-stat-' + id);
    var n = $('au-stat-' + id + '-note');
    if (v) v.textContent = (value === null || value === undefined || value === '') ? '—' : String(value);
    if (n) n.textContent = note || '';
  }

  function clearStats(note) {
    ['tests', 'passrate', 'flaky', 'failing', 'envs'].forEach(function (k) {
      setStat(k, null, note);
    });
  }

  // ---- サイト一覧 -----------------------------------------------------------
  function fillSelect(sel, sites, current) {
    if (!sel) return;
    sel.innerHTML = sites.map(function (s) {
      return '<option value="' + esc(s.domain) + '">' + esc(s.domain) + '</option>';
    }).join('');
    if (current) sel.value = current;
  }

  function loadSites() {
    return getJSON('/api/test-steps/sites').then(function (data) {
      state.sites = (data && data.sites) || [];
      if (!state.sites.length) {
        // 「サイトが 0 件」と「取得していない」を分ける。0 件は実測なのでそう書く。
        message($('au-message'), '対象サイトは 0 件です。先にドキュメント作成でサイトを解析するか、ステップ編集でテストを保存してください。', 'warn');
        message($('au-env-message'), '対象サイトは 0 件です。実行環境はサイト単位で持つため、まず対象サイトを用意してください。', 'warn');
        fillSelect($('au-domain'), [], '');
        fillSelect($('au-env-domain'), [], '');
        clearStats('対象サイトなし');
        emptyRow('au-runs-body', 'au-runs-empty', 5, '対象サイトが 0 件のため、実行はありません。');
        emptyRow('au-env-body', 'au-env-empty', 5, '対象サイトが 0 件のため、実行環境はありません。');
        return;
      }
      message($('au-message'), '');
      message($('au-env-message'), '');
      if (!state.domain || !state.sites.some(function (s) { return s.domain === state.domain; })) {
        state.domain = state.sites[0].domain;
      }
      fillSelect($('au-domain'), state.sites, state.domain);
      fillSelect($('au-env-domain'), state.sites, state.domain);
    }).catch(function (err) {
      state.sites = null;
      message($('au-message'), '対象サイトを取得できませんでした（' + err.message + '）。', 'ng');
      message($('au-env-message'), '対象サイトを取得できませんでした（' + err.message + '）。', 'ng');
      clearStats('取得失敗');
    });
  }

  function emptyRow(bodyId, emptyId, cols, text) {
    var body = $(bodyId);
    if (!body) return;
    body.innerHTML = '<tr><td colspan="' + cols + '"><div class="empty" id="' + emptyId + '">'
      + esc(text) + '</div></td></tr>';
  }

  // ---- ダッシュボード -------------------------------------------------------
  function loadSteps(domain) {
    return getJSON('/api/test-steps/' + encodeURIComponent(domain)).then(function (data) {
      var doc = (data && data.document) || {};
      var n = (doc.tests || []).length;
      // saved=false は「まだ保存されたステップが無い」。0 件（保存済みで空）と区別する。
      setStat('tests', n, data.saved ? '保存済み' : '未保存（ステップ未作成）');
    }).catch(function (err) {
      setStat('tests', null, '取得できませんでした（' + err.message + '）');
    });
  }

  function loadTrends(domain) {
    return getJSON('/api/runs/' + encodeURIComponent(domain) + '/trends').then(function (data) {
      var s = (data && data.summary) || {};
      var analyzed = data && data.runs_analyzed;
      if (!analyzed) {
        // 集計対象の実行回が 1 件も無い。数字は「0」ではなく「未計測」。
        setStat('passrate', null, '未計測（集計できる実行回なし）');
        setStat('flaky', null, '未計測（集計できる実行回なし）');
        setStat('failing', null, '未計測（集計できる実行回なし）');
        return;
      }
      var rate = s.latest_pass_rate;
      var delta = s.pass_rate_delta;
      var deltaText = (delta === null || delta === undefined) ? '前回比なし'
        : (delta > 0 ? '前回比 +' : '前回比 ') + delta + 'pt';
      setStat('passrate', (rate === null || rate === undefined) ? null : rate + '%',
        (rate === null || rate === undefined)
          ? '未計測（最新回にパス率なし）'
          : deltaText + ' / 実行回 ' + (s.latest_run_id || '—'));
      setStat('flaky', s.unstable_tests === undefined ? null : s.unstable_tests,
        '直近 ' + analyzed + ' 回で判定');
      setStat('failing', s.persistently_failing === undefined ? null : s.persistently_failing,
        '自己修復 ' + (s.healed_locators === undefined ? '—' : s.healed_locators) + ' 件');
    }).catch(function (err) {
      ['passrate', 'flaky', 'failing'].forEach(function (k) {
        setStat(k, null, '取得できませんでした（' + err.message + '）');
      });
    });
  }

  function loadEnvStat(domain) {
    return getJSON('/api/environments/' + encodeURIComponent(domain)).then(function (data) {
      var envs = ((data && data.document) || {}).environments || [];
      setStat('envs', envs.length, data.saved ? '保存済み' : '未登録（既定の実行先のみ）');
    }).catch(function (err) {
      setStat('envs', null, '取得できませんでした（' + err.message + '）');
    });
  }

  var STATE_LABEL = {
    queued: '待機中', running: '実行中', complete: '完了', failed: '失敗', cancelled: '中止'
  };

  function jobCount(job) {
    var r = job.result || {};
    if (r.total === undefined || r.total === null) return '未計測';
    return '成功 ' + (r.passed == null ? '—' : r.passed) + ' / 失敗 '
      + (r.failed == null ? '—' : r.failed) + ' / 全 ' + r.total;
  }

  function loadJobs(domain) {
    return getJSON('/api/test-runs/' + encodeURIComponent(domain) + '/jobs').then(function (data) {
      var jobs = (data && data.jobs) || [];
      if (!jobs.length) {
        // 実測して 0 件。未取得（初期表示）とは別の文言にする。
        emptyRow('au-runs-body', 'au-runs-empty', 5, '実行は 0 件です。ステップ編集の［▶ 実行］から始められます。');
        return;
      }
      var body = $('au-runs-body');
      if (!body) return;
      body.innerHTML = jobs.slice(0, 5).map(function (j) {
        return '<tr>'
          + '<td>' + esc(STATE_LABEL[j.status] || j.status || '—') + '</td>'
          + '<td>' + esc(jobCount(j)) + '</td>'
          + '<td>' + esc(j.run_id || '—') + '</td>'
          + '<td>' + esc(j.environment || '既定') + '</td>'
          + '<td>' + esc(j.requested_at || '—') + '</td>'
          + '</tr>';
      }).join('');
    }).catch(function (err) {
      emptyRow('au-runs-body', 'au-runs-empty', 5, '実行を取得できませんでした（' + err.message + '）。');
    });
  }

  function refresh() {
    var domain = state.domain;
    if (!domain) return Promise.resolve();
    if (state.loading) return Promise.resolve();
    state.loading = true;
    clearStats('取得中…');
    emptyRow('au-runs-body', 'au-runs-empty', 5, '取得中…');
    return Promise.all([
      loadSteps(domain), loadTrends(domain), loadEnvStat(domain), loadJobs(domain)
    ]).then(function () {
      var u = $('au-updated');
      if (u) u.textContent = '取得時刻 ' + new Date().toLocaleTimeString('ja-JP');
    }).catch(function () { /* 各ローダーが個別に理由を表示済み */ })
      .then(function () { state.loading = false; });
  }

  // ---- 実行環境 -------------------------------------------------------------
  function loadEnvTable() {
    var domain = state.domain;
    if (!domain) return Promise.resolve();
    emptyRow('au-env-body', 'au-env-empty', 5, '取得中…');
    return getJSON('/api/environments/' + encodeURIComponent(domain)).then(function (data) {
      var doc = (data && data.document) || {};
      var envs = doc.environments || [];
      if (!envs.length) {
        emptyRow('au-env-body', 'au-env-empty', 5,
          data.saved
            ? '登録された実行環境は 0 件です。'
            : 'このサイトの実行環境はまだ登録されていません（未登録）。実行は既定の実行先で行われます。');
        return;
      }
      var body = $('au-env-body');
      if (!body) return;
      body.innerHTML = envs.map(function (e) {
        return '<tr>'
          + '<td>' + esc(e.env_id) + '</td>'
          + '<td>' + esc(e.name) + '</td>'
          + '<td>' + esc(e.base_url) + '</td>'
          + '<td>' + (e.auth_path ? esc(e.auth_path) : 'なし') + '</td>'
          + '<td>' + (e.default ? '既定' : '') + '</td>'
          + '</tr>';
      }).join('');
    }).catch(function (err) {
      emptyRow('au-env-body', 'au-env-empty', 5, '実行環境を取得できませんでした（' + err.message + '）。');
    });
  }

  // ---- 配線 -----------------------------------------------------------------
  function go(view) {
    if (typeof switchView === 'function') switchView(view);
  }

  function init() {
    if (!$('view-test-automation')) return; // この系の画面が無いテンプレートでは何もしない

    var sel = $('au-domain');
    if (sel) {
      sel.addEventListener('change', function (e) {
        state.domain = e.target.value;
        var envSel = $('au-env-domain');
        if (envSel) envSel.value = state.domain;
        refresh();
      });
    }
    var envSel = $('au-env-domain');
    if (envSel) {
      envSel.addEventListener('change', function (e) {
        state.domain = e.target.value;
        if (sel) sel.value = state.domain;
        loadEnvTable();
      });
    }
    if ($('au-reload')) $('au-reload').addEventListener('click', function () { refresh(); });
    if ($('au-env-reload')) $('au-env-reload').addEventListener('click', function () { loadEnvTable(); });
    if ($('au-go-steps')) $('au-go-steps').addEventListener('click', function () { go('test-steps'); });
    if ($('au-go-envs')) $('au-go-envs').addEventListener('click', function () { go('test-environments'); });
    if ($('au-go-history')) $('au-go-history').addEventListener('click', function () { go('run-history'); });

    // ビューを開いたときに読む。開いていない画面のために毎回 4 本叩かない。
    if (typeof onViewEnter === 'function') {
      onViewEnter('test-automation', function () {
        ensureSites().then(refresh);
      });
      onViewEnter('test-environments', function () {
        ensureSites().then(loadEnvTable);
      });
    }

    // 直リンク（/test-automation 等）で開かれた場合、core.js の DOMContentLoaded は
    // すでに switchView 済み → onViewEnter が呼ばれない可能性があるため自分で拾う。
    var path = location.pathname;
    if (path === '/test-automation') ensureSites().then(refresh);
    else if (path === '/test-environments') ensureSites().then(loadEnvTable);
  }

  var sitesPromise = null;
  function ensureSites() {
    if (!sitesPromise) sitesPromise = loadSites();
    return sitesPromise;
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
