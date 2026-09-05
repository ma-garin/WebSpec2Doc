'use strict';

(function () {
  var API_BASE = '/api/healing';
  var POLL_MS = 2000;

  var STATUS_LABELS = {
    queued: '受付', preparing: '準備', verifying: '検証', analyzing: '欠陥の切り出し',
    fixing: '修正', reverifying: '再検証', awaiting_human: '人の判断待ち',
    succeeded: '完了', no_defects: '不具合なし', failed: '失敗', cancelled: '中止'
  };
  var TERMINAL_STATUSES = ['succeeded', 'no_defects', 'failed', 'cancelled'];
  // ポーリングを止めてよい状態。awaiting_human は「終わった」わけではないが、
  // 人が操作するまで中身は 1 文字も変わらない。ここで回し続けると、利用者が
  // まさに差分を読んでいる最中に 2 秒ごとに再描画され、開いた差分が閉じる。
  var POLL_STOP_STATUSES = TERMINAL_STATUSES.concat(['awaiting_human']);
  var SEVERITY_LABELS = { critical: '重大', high: '高', medium: '中', low: '低' };
  var PROPOSAL_STATUS_LABELS = { proposed: '提案', applied: '適用', failed: '失敗', skipped: '変更なし', timeout: '時間切れ' };
  var CHECK_DEFS = [
    { key: 'repository', label: 'リポジトリ' },
    { key: 'git', label: 'git' },
    { key: 'remote', label: 'リモート' },
    { key: 'github', label: 'GitHub' },
    { key: 'verify_command', label: '検証コマンド' }
  ];

  var state = {
    projects: [],
    //: project_id -> 接続確認の結果（true/false）。未確認なら未定義。
    checkResults: {},
    //: 直近に描画した run の JSON 文字列。同じなら描き直さない。
    lastRenderedRun: null,
    selectedProjectId: null,
    runs: [],
    selectedRunId: null,
    currentRun: null,
    pollRunId: null,
    pollTimer: null
  };

  var $ = {};

  function cacheDom() {
    var ids = [
      'hl-error', 'hl-projects-empty', 'hl-projects', 'hl-add-project',
      'hl-main-empty', 'hl-connect-form', 'hl-project-view',
      'hl-f-name', 'hl-f-path', 'hl-f-branch', 'hl-f-cmd', 'hl-f-remote',
      'hl-f-github', 'hl-f-agent', 'hl-f-max-iter', 'hl-f-concurrency',
      'hl-connect-submit', 'hl-connect-cancel',
      'hl-project-name', 'hl-project-path', 'hl-project-branch', 'hl-project-cmd',
      'hl-check-btn', 'hl-checks', 'hl-instructions', 'hl-start',
      'hl-loop-empty', 'hl-loop', 'hl-log',
      'hl-status', 'hl-cancel', 'hl-cancel-confirm', 'hl-cancel-yes', 'hl-cancel-no',
      'hl-pr', 'hl-unverified', 'hl-unverified-list',
      'hl-runs-empty', 'hl-runs'
    ];
    ids.forEach(function (id) { $[id] = document.getElementById(id); });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function showError(message) {
    $['hl-error'].textContent = message;
    $['hl-error'].hidden = false;
  }
  function clearError() {
    $['hl-error'].hidden = true;
    $['hl-error'].textContent = '';
  }

  function apiFetch(path, opts) {
    opts = opts || {};
    var headers = { 'X-Requested-With': 'XMLHttpRequest' };
    if (opts.body) { headers['Content-Type'] = 'application/json'; }
    var fetchOpts = { credentials: 'same-origin', method: opts.method || 'GET', headers: headers };
    if (opts.body) { fetchOpts.body = opts.body; }
    return fetch(API_BASE + path, fetchOpts).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        if (text) { try { data = JSON.parse(text); } catch (e) { data = null; } }
        if (!res.ok) {
          var msg = (data && (data.error || data.message)) || ('通信に失敗しました（コード ' + res.status + '）');
          throw new Error(msg);
        }
        return data;
      });
    });
  }

  function asList(data, key) {
    if (Array.isArray(data)) { return data; }
    if (data && Array.isArray(data[key])) { return data[key]; }
    return [];
  }
  function asObj(data, key) {
    if (data && data[key] && typeof data[key] === 'object') { return data[key]; }
    return data || {};
  }
  function fmtTime(s) {
    if (!s) { return ''; }
    return String(s).replace('T', ' ').slice(0, 19);
  }

  /* ---------------- プロジェクト ---------------- */

  function loadProjects() {
    return apiFetch('/projects').then(function (data) {
      state.projects = asList(data, 'projects');
      renderProjects();
    }).catch(function (e) { showError('接続先の一覧を取得できませんでした: ' + e.message); });
  }

  function renderProjects() {
    var ul = $['hl-projects'];
    ul.textContent = '';
    $['hl-projects-empty'].hidden = state.projects.length > 0;
    state.projects.forEach(function (p) {
      var li = el('li', 'hl-project-card');
      if (p.project_id === state.selectedProjectId) { li.classList.add('is-selected'); }
      li.appendChild(el('div', 'hl-pc-name', p.name || p.project_id || '(名称未設定)'));
      li.appendChild(el('div', 'hl-pc-path hl-mono hl-ellipsis', p.repo_path || ''));
      li.lastChild.title = p.repo_path || '';

      var statusRow = el('div', 'hl-pc-status');
      var dot = el('span', 'hl-dot');
      var connected = state.checkResults[p.project_id];
      dot.classList.add(connected === true ? 'is-ok' : (connected === false ? 'is-bad' : 'is-unknown'));
      statusRow.appendChild(dot);
      statusRow.appendChild(el('span', null, connected === true ? '接続OK' : (connected === false ? '接続エラー' : '未確認')));
      li.appendChild(statusRow);

      if (p.last_run_status) {
        li.appendChild(el('div', 'hl-pc-last-run', '前回: ' + (STATUS_LABELS[p.last_run_status] || p.last_run_status)));
      }

      li.addEventListener('click', function () { selectProject(p.project_id); });
      ul.appendChild(li);
    });
  }

  function selectProject(id) {
    state.selectedProjectId = id;
    state.selectedRunId = null;
    state.currentRun = null;
    stopPolling();
    hideConnectForm();
    renderProjects();
    var project = state.projects.filter(function (p) { return p.project_id === id; })[0];
    if (!project) { return; }

    $['hl-main-empty'].hidden = true;
    $['hl-project-view'].hidden = false;
    $['hl-project-name'].textContent = project.name || project.project_id;
    $['hl-project-path'].textContent = project.repo_path || '';
    $['hl-project-path'].title = project.repo_path || '';
    $['hl-project-branch'].textContent = project.branch || project.default_branch || '';
    $['hl-project-cmd'].textContent = project.verify_command || '';
    $['hl-project-cmd'].title = project.verify_command || '';

    $['hl-checks'].textContent = '';
    renderLoop(null);
    renderLogLines([]);
    renderStatusBadge(null);
    renderPrBlock(null);
    renderUnverified(null);

    loadRuns(id);
  }

  function showConnectForm() {
    $['hl-main-empty'].hidden = true;
    $['hl-project-view'].hidden = true;
    $['hl-connect-form'].hidden = false;
  }
  function hideConnectForm() {
    $['hl-connect-form'].hidden = true;
  }

  function submitConnectForm() {
    var name = $['hl-f-name'].value.trim();
    var path = $['hl-f-path'].value.trim();
    if (!name || !path) { showError('名前とリポジトリのパスは必須です。'); return; }
    // キー名は API（web/routes/healing.py）の受け口と 1 文字も違えられない。
    // path/branch/concurrency のような「短い呼び方」で送ると 400 になる。
    var payload = {
      name: name,
      repo_path: path,
      default_branch: $['hl-f-branch'].value.trim() || 'main',
      verify_command: $['hl-f-cmd'].value.trim(),
      remote: $['hl-f-remote'].value.trim() || 'origin',
      // 空欄は null ではなく空文字。null は「owner/name の形式違反」として弾かれる。
      github_repo: $['hl-f-github'].value.trim(),
      agent: $['hl-f-agent'].value,
      max_iterations: parseInt($['hl-f-max-iter'].value, 10) || 3,
      max_parallel_agents: parseInt($['hl-f-concurrency'].value, 10) || 3
    };
    clearError();
    apiFetch('/projects', { method: 'POST', body: JSON.stringify(payload) }).then(function (data) {
      hideConnectForm();
      return loadProjects().then(function () {
        var created = asObj(data, 'project');
        if (created && created.project_id) { selectProject(created.project_id); }
      });
    }).catch(function (e) { showError('接続に失敗しました: ' + e.message); });
  }

  /* ---------------- 接続確認 ---------------- */

  function getCheckItem(data, key) {
    var list = asList(data, 'checks');
    for (var i = 0; i < list.length; i++) {
      if (list[i].key === key || list[i].name === key) { return list[i]; }
    }
    if (data && data[key] && typeof data[key] === 'object') { return data[key]; }
    return null;
  }

  function runCheck() {
    if (!state.selectedProjectId) { return; }
    clearError();
    $['hl-checks'].textContent = '';
    apiFetch('/projects/' + state.selectedProjectId + '/check', { method: 'POST', body: JSON.stringify({}) })
      .then(function (data) { renderChecks(data); })
      .catch(function (e) { showError('接続確認に失敗しました: ' + e.message); });
  }

  function renderChecks(data) {
    var ul = $['hl-checks'];
    ul.textContent = '';
    // サーバが返した項目をそのまま、返ってきた順に描く。
    // 画面側で項目名（key）を持って突き合わせると、片方の名前が変わっただけで
    // 「✕ 確認できませんでした」と出て、実際は成功しているのに失敗に見える
    // （実画面で repo / repository の食い違いにより発生）。ラベルもサーバの値を使う。
    var list = asList(data, 'checks');
    if (!list.length) {
      list = CHECK_DEFS.map(function (def) {
        return getCheckItem(data, def.key) || { key: def.key, label: def.label, ok: false, detail: '' };
      });
    }
    list.forEach(function (item) {
      var ok = item.ok === true;
      var li = el('li', 'hl-check-row');
      li.appendChild(el('span', 'hl-check-icon ' + (ok ? 'is-ok' : 'is-bad'), ok ? '✓' : '✕'));
      li.appendChild(el('span', 'hl-check-label', item.label || item.key || ''));
      var detail = item.detail || (ok ? '' : '確認できませんでした');
      li.appendChild(el('span', 'hl-check-detail', detail));
      li.title = detail;
      ul.appendChild(li);
    });
    // 左レールのカードにも結果を反映する。確認したのに「未確認」のままだと、
    // 押した操作が効いていないように見える。
    var okAll = list.length > 0 && list.every(function (item) { return item.ok === true; });
    state.checkResults[state.selectedProjectId] = okAll;
    renderProjects();
  }

  /* ---------------- 実行 ---------------- */

  function loadRuns(projectId) {
    return apiFetch('/runs?project_id=' + encodeURIComponent(projectId)).then(function (data) {
      state.runs = asList(data, 'runs').slice(0, 10);
      renderRunsList();
      if (state.focusRunId && state.runs.some(function (r) { return r.run_id === state.focusRunId; })) {
        openRun(state.focusRunId);
      } else if (state.runs.length > 0) {
        openRun(state.runs[0].run_id);
      }
    }).catch(function (e) { showError('実行履歴を取得できませんでした: ' + e.message); });
  }

  function renderRunsList() {
    var ul = $['hl-runs'];
    ul.textContent = '';
    $['hl-runs-empty'].hidden = state.runs.length > 0;
    state.runs.forEach(function (r) {
      var li = el('li', 'hl-run-row');
      if (r.run_id === state.selectedRunId) { li.classList.add('is-selected'); }
      var badge = el('span', 'hl-status-badge ' + statusBadgeClass(r.status), STATUS_LABELS[r.status] || r.status);
      li.appendChild(badge);
      li.appendChild(el('span', 'hl-run-time', fmtTime(r.started_at)));
      var prNo = r.pull_request && r.pull_request.number;
      li.appendChild(el('span', 'hl-run-pr', prNo ? ('PR #' + prNo) : ''));
      li.addEventListener('click', function () { openRun(r.run_id); });
      ul.appendChild(li);
    });
  }

  function startRun() {
    if (!state.selectedProjectId) { return; }
    clearError();
    var payload = {
      project_id: state.selectedProjectId,
      extra_instructions: ($['hl-instructions'] ? $['hl-instructions'].value.trim() : '')
    };
    var instructions = $['hl-instructions'].value.trim();
    if (instructions) { payload.instructions = instructions; }
    $['hl-start'].disabled = true;
    apiFetch('/runs', { method: 'POST', body: JSON.stringify(payload) }).then(function (data) {
      $['hl-start'].disabled = false;
      var run = asObj(data, 'run');
      if (run && run.run_id) {
        return loadRuns(state.selectedProjectId).then(function () { openRun(run.run_id); });
      }
    }).catch(function (e) {
      $['hl-start'].disabled = false;
      showError('ヒーリングの開始に失敗しました: ' + e.message);
    });
  }

  function openRun(runId) {
    state.selectedRunId = runId;
    stopPolling();
    // 別の実行を開くときは前回の署名を捨てる（同じ内容でも描き直す必要がある）。
    state.lastRenderedRun = null;
    fetchAndRenderRun(runId);
  }

  function fetchAndRenderRun(runId) {
    return apiFetch('/runs/' + encodeURIComponent(runId)).then(function (data) {
      var run = asObj(data, 'run');
      state.currentRun = run;
      // 中身が 1 文字も変わっていないなら描き直さない。描き直すと、開いてある
      // 差分・スクロール位置・選択がその都度失われる（差分は毎回閉じる）。
      var signature = JSON.stringify(run);
      if (signature !== state.lastRenderedRun) {
        state.lastRenderedRun = signature;
        renderRun(run);
        renderRunsList();
      }
      if (POLL_STOP_STATUSES.indexOf(run.status) === -1) {
        startPolling(runId);
      } else {
        stopPolling();
      }
    }).catch(function (e) { showError('実行状況を取得できませんでした: ' + e.message); });
  }

  function startPolling(runId) {
    state.pollRunId = runId;
    if (document.hidden) { return; }
    clearPollTimer();
    state.pollTimer = setInterval(function () { fetchAndRenderRun(runId); }, POLL_MS);
  }
  function clearPollTimer() {
    if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
  }
  function stopPolling() {
    state.pollRunId = null;
    clearPollTimer();
  }
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      clearPollTimer();
    } else if (state.pollRunId) {
      var id = state.pollRunId;
      fetchAndRenderRun(id);
      state.pollTimer = setInterval(function () { fetchAndRenderRun(id); }, POLL_MS);
    }
  });

  function statusBadgeClass(status) {
    if (status === 'succeeded' || status === 'no_defects') { return 'is-done'; }
    if (status === 'failed') { return 'is-failed'; }
    if (status === 'cancelled') { return 'is-cancelled'; }
    if (status === 'awaiting_human') { return 'is-waiting'; }
    return 'is-running';
  }

  function renderRun(run) {
    renderStatusBadge(run);
    renderLoop(run);
    renderLogLines(run.log || []);
    renderPrBlock(run);
    renderUnverified(run);
  }

  function renderStatusBadge(run) {
    var badge = $['hl-status'];
    badge.className = 'hl-status-badge';
    if (!run) {
      badge.textContent = '未選択';
      $['hl-cancel'].hidden = true;
      $['hl-cancel-confirm'].hidden = true;
      return;
    }
    badge.classList.add(statusBadgeClass(run.status));
    var label = STATUS_LABELS[run.status] || run.status || '';
    var step = run.step_label || '';
    // step_label は状態名で始まることが多い（status=fixing / step_label="修正（1周目・1件）"）。
    // そのまま連結すると「修正（修正（1周目・1件））」と二重になる。
    // 細かい方（step_label）が状態名を含んでいるなら、そちらだけを出す。
    if (step && step.indexOf(label) === 0) {
      badge.textContent = step;
    } else {
      badge.textContent = label + (step ? '（' + step + '）' : '');
    }
    // 中止ボタンは実行が終わっていない間だけ出す（succeeded/no_defects/failed/cancelled 以外）。
    var isRunning = TERMINAL_STATUSES.indexOf(run.status) === -1;
    $['hl-cancel'].hidden = !isRunning;
    if (!isRunning) { $['hl-cancel-confirm'].hidden = true; }
  }

  /* ---------------- ループ表示 ---------------- */

  function stepStates(iter, isActive) {
    var s1 = iter.verify_before ? 'done' : (isActive ? 'current' : 'pending');
    var s2 = s1 === 'done' ? (iter.defects ? 'done' : (isActive ? 'current' : 'pending')) : 'pending';
    var s3 = s2 === 'done' ? (iter.proposals ? 'done' : (isActive ? 'current' : 'pending')) : 'pending';
    var s4 = s3 === 'done' ? (iter.verify_after ? 'done' : (isActive ? 'current' : 'pending')) : 'pending';
    return [s1, s2, s3, s4];
  }

  function renderStepper(states) {
    var labels = ['検証', '欠陥', '修正', '再検証'];
    var wrap = el('div', 'hl-stepper');
    states.forEach(function (st, i) {
      var step = el('div', 'hl-step is-' + st);
      step.appendChild(el('span', 'hl-step-dot'));
      step.appendChild(el('span', null, labels[i]));
      wrap.appendChild(step);
    });
    return wrap;
  }

  function renderVerifyResult(v) {
    var wrap = el('div', 'hl-verify-result');
    if (!v) { wrap.appendChild(el('span', null, '未実行')); return wrap; }
    // 検証そのものが動かなかった場合、件数（失敗 0 / 全 0）だけを出すと
    // 「不具合が無かった」と読めてしまう。理由を最初に、目立つ形で出す。
    if (v.error) {
      wrap.appendChild(el('b', 'hl-verify-error', '検証を実行できませんでした'));
      wrap.appendChild(el('span', 'hl-verify-error-detail', v.error));
      if (v.command) { wrap.appendChild(el('span', 'hl-mono', v.command)); }
      return wrap;
    }
    var summary = '失敗 ' + (v.failed != null ? v.failed : '?') + ' / 全 ' + (v.total != null ? v.total : '?');
    // 生の浮動小数（0.0015079999575391412 秒）は読めない。小数 1 桁に丸める。
    if (typeof v.duration_sec === 'number') { summary += '（' + v.duration_sec.toFixed(1) + ' 秒）'; }
    wrap.appendChild(el('b', null, summary));
    if (v.command) { wrap.appendChild(el('span', 'hl-mono', v.command)); }
    return wrap;
  }

  function renderDefectsTable(defects) {
    if (!defects || defects.length === 0) {
      return el('p', 'hl-hint', '検出した不具合はありません。');
    }
    var table = el('table', 'hl-defects-table');
    var thead = el('thead');
    var trh = el('tr');
    ['重大度', '事象', '失敗したテスト', '該当しそうなファイル'].forEach(function (t) { trh.appendChild(el('th', null, t)); });
    thead.appendChild(trh);
    table.appendChild(thead);
    var tbody = el('tbody');
    defects.forEach(function (d) {
      var tr = el('tr');
      var tdSev = el('td');
      tdSev.appendChild(el('span', 'hl-badge-sev hl-badge-sev-' + d.severity, SEVERITY_LABELS[d.severity] || d.severity));
      tr.appendChild(tdSev);
      tr.appendChild(el('td', null, d.title || d.message || ''));
      var tdTest = el('td', 'hl-td-test hl-mono hl-ellipsis', d.test_id || '');
      tdTest.title = d.test_id || '';
      tr.appendChild(tdTest);
      var files = (d.suspect_files || []).join(', ');
      var tdFile = el('td', 'hl-td-file hl-mono hl-ellipsis', files);
      tdFile.title = files;
      tr.appendChild(tdFile);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    return table;
  }

  function buildDiffElement(diffText) {
    var pre = el('pre', 'hl-diff');
    pre.hidden = true;
    (diffText || '').split('\n').forEach(function (line) {
      var cls = 'hl-diff-ctx';
      if (line.indexOf('+') === 0 && line.indexOf('+++') !== 0) { cls = 'hl-diff-add'; }
      else if (line.indexOf('-') === 0 && line.indexOf('---') !== 0) { cls = 'hl-diff-del'; }
      pre.appendChild(el('span', cls, line));
    });
    return pre;
  }

  function renderProposals(proposals) {
    var wrap = el('div');
    if (!proposals || proposals.length === 0) {
      wrap.appendChild(el('p', 'hl-hint', '修正はまだありません。'));
      return wrap;
    }
    var list = el('ul', 'hl-proposals');
    proposals.forEach(function (p) {
      var row = el('li', 'hl-proposal-row');
      row.appendChild(el('span', 'hl-proposal-agent', p.agent || ''));
      row.appendChild(el('span', 'hl-badge-proposal hl-badge-proposal-' + p.status, PROPOSAL_STATUS_LABELS[p.status] || p.status));
      row.appendChild(el('span', 'hl-proposal-summary', p.summary || ''));
      var filesN = (p.files_changed || []).length;
      row.appendChild(el('span', 'hl-proposal-files', filesN + ' ファイル変更'));
      if (p.diff) {
        var diffEl = buildDiffElement(p.diff);
        var toggle = el('button', 'hl-diff-toggle', '差分を見る');
        toggle.type = 'button';
        toggle.addEventListener('click', function () {
          diffEl.hidden = !diffEl.hidden;
          toggle.textContent = diffEl.hidden ? '差分を見る' : '差分を隠す';
        });
        row.appendChild(toggle);
        list.appendChild(row);
        var diffLi = el('li');
        diffLi.appendChild(diffEl);
        list.appendChild(diffLi);
      } else {
        list.appendChild(row);
      }
    });
    wrap.appendChild(list);
    return wrap;
  }

  function renderLoop(run) {
    var loopEl = $['hl-loop'];
    loopEl.textContent = '';
    var iterations = run && run.iterations ? run.iterations : [];
    $['hl-loop-empty'].hidden = iterations.length > 0;
    if (iterations.length === 0) { return; }

    var isRunTerminal = run && TERMINAL_STATUSES.indexOf(run.status) !== -1;
    iterations.forEach(function (iter, idx) {
      var isActive = !isRunTerminal && idx === iterations.length - 1;
      var block = el('div', 'hl-iter');
      block.appendChild(el('h3', 'hl-iter-head', '第 ' + iter.index + ' 周'));
      block.appendChild(renderStepper(stepStates(iter, isActive)));
      block.appendChild(el('h4', 'hl-hint', '検証結果'));
      block.appendChild(renderVerifyResult(iter.verify_before));
      if (iter.defects) {
        block.appendChild(el('h4', 'hl-hint', '検出した不具合'));
        block.appendChild(renderDefectsTable(iter.defects));
      }
      if (iter.proposals) {
        block.appendChild(el('h4', 'hl-hint', '修正'));
        block.appendChild(renderProposals(iter.proposals));
      }
      if (iter.verify_after) {
        block.appendChild(el('h4', 'hl-hint', '再検証結果'));
        block.appendChild(renderVerifyResult(iter.verify_after));
      }
      loopEl.appendChild(block);
    });
  }

  function renderLogLines(lines) {
    var logEl = $['hl-log'];
    logEl.textContent = '';
    if (!lines || !lines.length) {
      // 空の黒い箱だけを置くと「壊れている」ように見える。何が入る場所かを書く。
      logEl.appendChild(el('div', 'hl-log-placeholder', 'ヒーリングを開始すると、ここに進行が 1 行ずつ出ます。'));
      return;
    }
    lines.forEach(function (line) {
      logEl.appendChild(el('div', 'hl-log-line', line));
    });
    logEl.scrollTop = logEl.scrollHeight;
  }

  /* ---------------- PR・判断 ---------------- */

  function renderPrBlock(run) {
    var wrap = $['hl-pr'];
    wrap.textContent = '';
    if (!run) { return; }
    var pr = run.pull_request;

    if (!pr || !pr.number) {
      var empty = el('div', 'hl-pr-empty');
      empty.appendChild(el('p', null, 'まだ PR は作成されていません。'));
      var btn = el('button', 'hl-btn-primary', 'PR を作成');
      btn.type = 'button';
      btn.id = 'hl-create-pr';
      btn.disabled = !isAwaitingOrDone(run.status);
      btn.addEventListener('click', createPullRequest);
      empty.appendChild(btn);
      empty.appendChild(el('p', 'hl-pr-warn', '作成前に差分を確認してください。'));
      wrap.appendChild(empty);
      return;
    }

    var info = el('div', 'hl-pr-info');
    info.appendChild(el('span', 'hl-badge-pr', pr.state || ''));
    info.appendChild(el('div', 'hl-pr-info-title', '#' + pr.number + ' ' + (pr.title || '')));
    var link = el('a', 'hl-pr-info-link', pr.url || '');
    link.href = pr.url || '#';
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    info.appendChild(link);
    wrap.appendChild(info);

    var decisions = el('div', 'hl-decisions');
    var buttons = el('div', 'hl-decision-buttons');

    var approveBtn = el('button', 'hl-btn-sub', '承認（記録のみ）');
    approveBtn.type = 'button'; approveBtn.id = 'hl-approve';
    approveBtn.addEventListener('click', function () { submitDecision('approve'); });

    var mergeBtn = el('button', 'hl-btn-danger', 'マージ');
    mergeBtn.type = 'button'; mergeBtn.id = 'hl-merge';

    var rejectBtn = el('button', 'hl-btn-sub', '却下');
    rejectBtn.type = 'button'; rejectBtn.id = 'hl-reject';
    rejectBtn.addEventListener('click', function () { submitDecision('reject'); });

    buttons.appendChild(approveBtn);
    buttons.appendChild(mergeBtn);
    buttons.appendChild(rejectBtn);
    decisions.appendChild(buttons);

    var confirmRow = el('div', 'hl-merge-confirm');
    confirmRow.hidden = true;
    confirmRow.appendChild(el('span', null, '本当にマージしますか？'));
    var yesBtn = el('button', 'hl-btn-danger', 'はい、マージする');
    yesBtn.type = 'button';
    yesBtn.addEventListener('click', function () { confirmRow.hidden = true; submitDecision('merge'); });
    var noBtn = el('button', 'hl-btn-sub', 'やめる');
    noBtn.type = 'button';
    noBtn.addEventListener('click', function () { confirmRow.hidden = true; });
    confirmRow.appendChild(yesBtn);
    confirmRow.appendChild(noBtn);
    mergeBtn.addEventListener('click', function () { confirmRow.hidden = false; });
    decisions.appendChild(confirmRow);

    var note = el('textarea');
    note.id = 'hl-decision-note';
    note.rows = 2;
    note.placeholder = 'メモ（任意）';
    decisions.appendChild(note);

    if (run.decisions && run.decisions.length > 0) {
      var hist = el('ul', 'hl-decision-history');
      run.decisions.forEach(function (d) {
        var actionLabel = d.action === 'approve' ? '承認' : (d.action === 'merge' ? 'マージ' : (d.action === 'reject' ? '却下' : d.action));
        var text = fmtTime(d.at) + ' ' + actionLabel + (d.actor ? '（' + d.actor + '）' : '') + (d.note ? ': ' + d.note : '');
        hist.appendChild(el('li', null, text));
      });
      decisions.appendChild(hist);
    }

    wrap.appendChild(decisions);
  }

  function isAwaitingOrDone(status) {
    return status === 'awaiting_human' || status === 'succeeded' || status === 'no_defects';
  }

  function createPullRequest() {
    if (!state.selectedRunId) { return; }
    clearError();
    apiFetch('/runs/' + state.selectedRunId + '/pull-request', { method: 'POST', body: JSON.stringify({}) })
      .then(function () { return fetchAndRenderRun(state.selectedRunId); })
      .catch(function (e) { showError('PR の作成に失敗しました: ' + e.message); });
  }

  function cancelRun() {
    if (!state.selectedRunId) { return; }
    clearError();
    apiFetch('/runs/' + state.selectedRunId + '/cancel', { method: 'POST', body: JSON.stringify({}) })
      .then(function () { return fetchAndRenderRun(state.selectedRunId); })
      .catch(function (e) { showError('実行の中止に失敗しました: ' + e.message); });
  }

  function submitDecision(action) {
    if (!state.selectedRunId) { return; }
    clearError();
    var noteEl = document.getElementById('hl-decision-note');
    var note = noteEl ? noteEl.value.trim() : '';
    apiFetch('/runs/' + state.selectedRunId + '/decision', { method: 'POST', body: JSON.stringify({ action: action, note: note }) })
      .then(function () { return fetchAndRenderRun(state.selectedRunId); })
      .catch(function (e) { showError('判断の記録に失敗しました: ' + e.message); });
  }

  function renderUnverified(run) {
    var block = $['hl-unverified'];
    var list = run && run.unverified ? run.unverified : [];
    if (!list || list.length === 0) { block.hidden = true; return; }
    block.hidden = false;
    $['hl-unverified-list'].textContent = '';
    list.forEach(function (item) {
      $['hl-unverified-list'].appendChild(el('li', null, item));
    });
  }

  /* ---------------- 初期化 ---------------- */

  function init() {
    cacheDom();
    state.focusRunId = document.body.getAttribute('data-focus-run-id') || '';

    $['hl-add-project'].addEventListener('click', showConnectForm);
    $['hl-connect-cancel'].addEventListener('click', function () {
      hideConnectForm();
      if (state.selectedProjectId) {
        $['hl-project-view'].hidden = false;
      } else {
        $['hl-main-empty'].hidden = false;
      }
    });
    $['hl-connect-submit'].addEventListener('click', submitConnectForm);
    $['hl-check-btn'].addEventListener('click', runCheck);
    $['hl-start'].addEventListener('click', startRun);
    $['hl-cancel'].addEventListener('click', function () { $['hl-cancel-confirm'].hidden = false; });
    $['hl-cancel-yes'].addEventListener('click', function () { $['hl-cancel-confirm'].hidden = true; cancelRun(); });
    $['hl-cancel-no'].addEventListener('click', function () { $['hl-cancel-confirm'].hidden = true; });

    loadProjects();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
