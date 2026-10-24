/* CLI / API 画面: ジョブの投入 → 状態 → 結果 → 証跡、と定期クロール設定の一覧・停止。
   本文コンテナの data-state で 9 状態（normal/empty/no-match/loading/error/forbidden/dirty/conflict/restored）を切り替える。 */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var body = $('cli-jobs-body'), detail = $('cli-detail-body'), gates = $('cli-gates');
  var sched = $('cli-sched-body'), form = $('cli-submit-form'), msg = $('cli-submit-msg');
  if (!body || !form) { return; }
  var KEY = 'ws2d.cli.job';
  var jobs = [], selected = '', lastConflictJob = '', polls = 0, timer = null;
  var STATUS = { queued: ['waiting_approval', '…'], running: ['running', '▶'], completed: ['done', '✓'], failed: ['failed', '✕'] };

  function esc(v) { var d = document.createElement('div'); d.textContent = v == null ? '' : String(v); return d.innerHTML; }
  function badge(job) {
    var s = STATUS[job.status] || ['unverified', '◌'];
    return '<span class="c-status c-status--' + s[0] + '"><span class="c-status__icon" aria-hidden="true">' + s[1] + '</span>' + esc(job.view.label) + '</span>';
  }
  function stateBox(kind, title, text, next, btn) {
    return '<div class="c-state c-state--' + kind + '"><p class="c-state__title">' + esc(title) + '</p><p class="c-state__msg">' + esc(text) +
      '</p><p class="c-state__next">次の行動: ' + esc(next) + '</p>' + (btn || '') + '</div>';
  }
  function errMsg(data, fallback) { return (data && data.error && data.error.message) || fallback; }
  function fmt(t) { return t ? String(t).replace('T', ' ') : '—'; }

  var STATES = {
    empty: function () { return stateBox('empty', 'ジョブはまだありません', 'このテナントで投入されたジョブが 0 件です。', '「1. 投入する」で対象 URL を入れて投入してください。'); },
    'no-match': function () { return stateBox('empty', '条件に合うジョブがありません', '「状態で絞る」の条件に一致するジョブが 0 件です。', '条件を解除して全件を表示してください。', '<button type="button" class="c-btn" data-act="clear-filter">条件を解除</button>'); },
    loading: function () { return '<div class="c-state c-state--loading"><span class="c-state__spinner" aria-hidden="true"></span><p class="c-state__title">ジョブ一覧を読み込んでいます</p></div>'; },
    error: function (t) { return stateBox('error', 'ジョブ一覧を読み込めませんでした', t || 'サーバに接続できませんでした。', '再試行を押してください。続く場合は管理者に連絡してください。', '<button type="button" class="c-btn" data-act="reload">再試行</button>'); },
    forbidden: function (t) { return stateBox('permission', '権限が不足しています', t || 'この操作には管理者の役割が必要です。', '管理者に依頼してください。表示中の一覧はそのまま見られます。'); },
    dirty: function () { return stateBox('partial', '未送信の入力があります', '「1. 投入する」に入力した URL がまだ投入されていません。', '投入するか、入力を消してから画面を移動してください。'); },
    conflict: function (t) { return stateBox('stale', '同じサイトのジョブが動いています', t || '待機中または実行中のジョブがあるため投入できませんでした。', '終わるのを待つか、動いているジョブを開いて状態を確認してください。', '<button type="button" class="c-btn" data-act="open-active">動いているジョブを開く</button>'); },
    restored: function () { return stateBox('unverified', '前回選んでいたジョブを復元しました', '再読込の前に選んでいたジョブを右側に表示しています。', '別のジョブを見るときは一覧から選んでください。') + table(jobs); }
  };

  function table(list) {
    var rows = list.map(function (j) {
      return '<tr data-job="' + esc(j.job_id) + '"' + (j.job_id === selected ? ' aria-selected="true" class="is-selected"' : '') + '>' +
        '<td data-label="対象"><button type="button" class="cli-link" data-act="select" data-job="' + esc(j.job_id) + '">' + esc(j.domain) + '</button></td>' +
        '<td data-label="状態">' + badge(j) + '</td><td data-label="投入">' + esc(fmt(j.started_at)) + '</td>' +
        '<td data-label="次の行動">' + esc(j.view.reason ? j.view.reason + ' ' : '') + esc(j.view.next_action) + '</td></tr>';
    }).join('');
    return '<div class="c-table-wrap"><table class="c-table cli-jobs-table"><thead><tr><th>対象</th><th>状態</th><th>投入</th><th>次の行動</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function render(state, text) {
    var filter = $('cli-job-filter').value;
    var list = filter ? jobs.filter(function (j) { return j.status === filter; }) : jobs;
    if (!state) { state = jobs.length === 0 ? 'empty' : (list.length === 0 ? 'no-match' : 'normal'); }
    body.setAttribute('data-state', state);
    body.innerHTML = state === 'normal' ? table(list) : STATES[state](text);
    renderGates();
  }

  function renderGates() {
    var failed = jobs.filter(function (j) { return j.status === 'failed'; });
    var active = jobs.filter(function (j) { return j.status === 'queued' || j.status === 'running'; });
    var all = jobs.length === 0 ? ['hold', '未判定', 'ジョブが 0 件のため判定できません。'] :
      failed.length ? ['ng', '不合格', '失敗: ' + failed.map(function (j) { return j.domain + '（' + fmt(j.started_at) + '）'; }).join('、')] :
      active.length ? ['hold', '未判定', '終わっていないジョブ: ' + active.map(function (j) { return j.domain; }).join('、')] :
      ['ok', '合格', '全 ' + jobs.length + ' 件が完了。結果の中身（画面数・差分）は未検証です。レポートで確かめてください。'];
    var last = jobs[0];
    var cur = !last ? ['hold', '未判定', '今回のジョブはありません。'] :
      last.status === 'failed' ? ['ng', '不合格', last.domain + ': ' + last.view.reason] :
      last.status === 'completed' ? ['ok', '合格', last.domain + ': 完了（終了コード ' + last.exit_code + '）'] :
      ['hold', '未判定', last.domain + ': ' + last.view.label];
    gates.innerHTML = [['全体', all], ['今回の投入分', cur]].map(function (g) {
      return '<div class="p5-gate ' + g[1][0] + '"><span class="p5-gate__k">' + g[0] + '</span><strong>' + g[1][1] + '</strong><span>' + esc(g[1][2]) + '</span></div>';
    }).join('');
  }

  function renderDetail() {
    var j = jobs.filter(function (x) { return x.job_id === selected; })[0];
    if (!j) { detail.innerHTML = '<p class="cli-hint">一覧からジョブを選ぶと、結果と証跡を表示します。</p>'; return; }
    var result = j.status === 'completed'
      ? '<p><a class="c-btn" href="/api/v1/sites/' + encodeURIComponent(j.domain) + '/report" target="_blank" rel="noopener">レポート（JSON）を開く</a></p>'
      : '<p class="cli-hint">' + esc(j.view.reason || j.view.next_action) + '</p>';
    detail.innerHTML = '<dl class="cli-dl"><dt>対象</dt><dd>' + esc(j.domain) + '</dd><dt>URL</dt><dd>' + esc(j.site_url) + '</dd><dt>状態</dt><dd>' + badge(j) +
      '</dd><dt>次の行動</dt><dd>' + esc(j.view.next_action) + '</dd></dl><h4 class="p3-sec-t">結果</h4>' + result +
      '<h4 class="p3-sec-t">証跡</h4><ul class="cli-ev"><li class="ev"><span class="who">' + esc(j.requested_by || '不明') + '</span> が投入 <span class="tm">' + esc(fmt(j.started_at)) + '</span></li>' +
      '<li class="ev">終了 <span class="tm">' + esc(fmt(j.finished_at)) + '</span>・終了コード ' + esc(j.exit_code == null ? '—' : j.exit_code) + '</li></ul>' +
      '<details class="cli-log"><summary>ログ末尾</summary><pre>' + esc(j.log_tail || '（まだありません）') + '</pre></details>' +
      '<p class="cli-hint">ジョブ ID: <code>' + esc(j.job_id) + '</code></p>';
  }

  function select(id) {
    selected = id;
    try { sessionStorage.setItem(KEY, id); } catch (e) { /* 保存できなくても表示は続ける */ }
    var u = new URL(location.href); u.searchParams.set('job', id); history.replaceState(null, '', u);
    render(); renderDetail();
  }

  function load(restore) {
    render('loading');
    return fetch('/api/v1/jobs', { credentials: 'same-origin' }).then(function (r) {
      return r.json().then(function (d) { return { r: r, d: d }; }, function () { return { r: r, d: null }; });
    }).then(function (x) {
      if (x.r.status === 403 || x.r.status === 401) { render('forbidden', errMsg(x.d)); return; }
      if (!x.r.ok || !x.d) { render('error', errMsg(x.d)); return; }
      jobs = x.d.jobs || [];
      var want = new URL(location.href).searchParams.get('job') || (function () { try { return sessionStorage.getItem(KEY); } catch (e) { return ''; } })();
      var found = want && jobs.some(function (j) { return j.job_id === want; });
      if (found) { selected = want; }
      render(restore && found ? 'restored' : ''); renderDetail();
      var busy = jobs.some(function (j) { return j.status === 'queued' || j.status === 'running'; });
      clearTimeout(timer);
      if (busy && polls < 60) { polls += 1; timer = setTimeout(function () { load(false); }, 3000); }
    }).catch(function () { render('error'); });
  }

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var url = $('cli-job-url').value.trim(), host = '';
    try { host = new URL(url).hostname; } catch (e) { host = ''; }
    msg.hidden = false;
    if (!host) { msg.textContent = '⚠ URL を http:// または https:// から入力してください。'; return; }
    msg.textContent = '投入しています…';
    fetch('/api/v1/sites/' + encodeURIComponent(host) + '/crawl', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: url, depth: Number($('cli-job-depth').value), max_pages: Number($('cli-job-max').value) })
    }).then(function (r) { return r.json().then(function (d) { return { r: r, d: d }; }); }).then(function (x) {
      if (x.r.status === 409) { lastConflictJob = x.d.error.job_id || ''; msg.textContent = '✕ ' + errMsg(x.d); render('conflict', errMsg(x.d)); return; }
      if (x.r.status === 403 || x.r.status === 401) { msg.textContent = '✕ ' + errMsg(x.d); render('forbidden', errMsg(x.d)); return; }
      if (!x.r.ok) { msg.textContent = '✕ ' + errMsg(x.d, '投入できませんでした。入力を見直してください。'); return; }
      msg.textContent = '✓ 投入しました（' + host + '）。状態は下の一覧に出ます。';
      $('cli-job-url').value = ''; polls = 0; selected = x.d.job_id; load(false);
    }).catch(function () { msg.textContent = '✕ サーバに接続できませんでした。再度投入してください。'; });
  });

  document.addEventListener('click', function (ev) {
    var t = ev.target.closest('[data-act]'); if (!t) { return; }
    var act = t.getAttribute('data-act');
    if (act === 'select') { select(t.getAttribute('data-job')); }
    if (act === 'reload') { polls = 0; load(false); }
    if (act === 'clear-filter') { $('cli-job-filter').value = ''; render(); }
    if (act === 'open-active') { if (lastConflictJob) { select(lastConflictJob); } else { load(false); } }
    if (act === 'stop-sched') { stopSchedule(t.getAttribute('data-domain')); }
  });
  $('cli-job-filter').addEventListener('change', function () { render(); });
  $('cli-job-reload').addEventListener('click', function () { polls = 0; load(false); });
  $('cli-state-switch').addEventListener('change', function () {
    var v = this.value; if (!v) { render(); return; }
    render(v); sched.setAttribute('data-state', v);
  });
  window.addEventListener('beforeunload', function (ev) {
    if ($('cli-job-url').value.trim()) { ev.preventDefault(); ev.returnValue = ''; }
  });
  $('cli-job-url').addEventListener('input', function () {
    if (this.value.trim() && body.getAttribute('data-state') === 'normal') { body.setAttribute('data-dirty', '1'); }
  });

  function loadSchedules() {
    sched.setAttribute('data-state', 'loading');
    sched.innerHTML = STATES.loading().replace('ジョブ一覧', '定期クロール設定');
    fetch('/api/v1/schedules', { credentials: 'same-origin' }).then(function (r) { return r.json().then(function (d) { return { r: r, d: d }; }); }).then(function (x) {
      if (!x.r.ok) { sched.setAttribute('data-state', x.r.status === 403 ? 'forbidden' : 'error'); sched.innerHTML = stateBox('error', '定期クロール設定を読み込めませんでした', errMsg(x.d, ''), '再読込してください。'); return; }
      var list = x.d.schedules || [];
      if (!list.length) { sched.setAttribute('data-state', 'empty'); sched.innerHTML = stateBox('empty', '定期クロールの設定はありません', '解析済みサイトに定期クロールの設定が 0 件です。', 'この画面では新しく作りません。手動で投入してください。'); return; }
      sched.setAttribute('data-state', 'normal');
      sched.innerHTML = '<div class="c-table-wrap"><table class="c-table"><thead><tr><th>対象</th><th>間隔</th><th>次回予定</th><th>操作</th></tr></thead><tbody>' +
        list.map(function (s) {
          var c = s.schedule || {};
          return '<tr><td data-label="対象">' + esc(s.domain) + '</td><td data-label="間隔">' + esc(c.interval || '—') + (c.enabled === false ? '（停止中）' : '') +
            '</td><td data-label="次回予定">' + esc(fmt(c.next_run_at)) + '</td><td data-label="操作"><button type="button" class="c-btn" data-act="stop-sched" data-domain="' + esc(s.domain) + '">停止する</button></td></tr>';
        }).join('') + '</tbody></table></div>';
    }).catch(function () { sched.setAttribute('data-state', 'error'); sched.innerHTML = stateBox('error', '定期クロール設定を読み込めませんでした', 'サーバに接続できませんでした。', '再読込してください。'); });
  }

  function stopSchedule(domain) {
    if (!window.confirm(domain + ' の定期クロール設定を削除して停止します。よろしいですか。')) { return; }
    fetch('/api/v1/sites/' + encodeURIComponent(domain) + '/schedule', { method: 'DELETE', credentials: 'same-origin' })
      .then(function (r) { return r.json().then(function (d) { return { r: r, d: d }; }); }).then(function (x) {
        if (x.r.status === 403 || x.r.status === 401) { sched.setAttribute('data-state', 'forbidden'); sched.insertAdjacentHTML('afterbegin', STATES.forbidden(errMsg(x.d))); return; }
        if (!x.r.ok) { sched.insertAdjacentHTML('afterbegin', stateBox('error', '停止できませんでした', errMsg(x.d, ''), '時間をおいて再度押してください。')); return; }
        loadSchedules();
      });
  }

  load(true); loadSchedules();
})();
