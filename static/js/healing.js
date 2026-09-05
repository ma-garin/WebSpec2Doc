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
    selectedRunId: null,
    currentRun: null,
    pollRunId: null,
    pollTimer: null,
    historyRuns: [],
    historyLimit: 20,
    editingProjectId: null,
    focusRunId: '',
    activeView: 'run'
  };

  var $ = {};

  function cacheDom() {
    var ids = [
      'hl-error', 'hl-nav-run', 'hl-nav-projects', 'hl-nav-history', 'hl-add-project',
      'hl-view-run', 'hl-view-projects', 'hl-view-history',
      'hl-project-select', 'hl-project-meta', 'hl-instructions', 'hl-start',
      'hl-start-confirm', 'hl-start-yes', 'hl-start-no',
      'hl-check-btn', 'hl-checks',
      'hl-stat-projects', 'hl-stat-runs', 'hl-stat-fixed', 'hl-stat-pr',
      'hl-run-sub', 'hl-status',
      'hl-create-pr', 'hl-rerun', 'hl-approve', 'hl-merge', 'hl-reject', 'hl-cancel',
      'hl-merge-confirm', 'hl-merge-yes', 'hl-merge-no',
      'hl-reject-confirm', 'hl-reject-yes', 'hl-reject-no',
      'hl-cancel-confirm', 'hl-cancel-yes', 'hl-cancel-no',
      'hl-decision-note', 'hl-pr-info', 'hl-run-error',
      'hl-loop', 'hl-loop-empty', 'hl-log',
      'hl-unverified', 'hl-unverified-list',
      'hl-projects', 'hl-projects-empty',
      'hl-connect-form', 'hl-form-title',
      'hl-f-name', 'hl-f-path', 'hl-f-branch', 'hl-f-cmd', 'hl-f-remote',
      'hl-f-github', 'hl-f-agent', 'hl-f-max-iter', 'hl-f-concurrency',
      'hl-connect-submit', 'hl-connect-cancel',
      'hl-runs', 'hl-runs-empty', 'hl-runs-more'
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

  function statusBadgeClass(status) {
    if (status === 'succeeded' || status === 'no_defects') { return 'is-done'; }
    if (status === 'failed') { return 'is-failed'; }
    if (status === 'cancelled') { return 'is-cancelled'; }
    if (status === 'awaiting_human') { return 'is-waiting'; }
    return 'is-running';
  }

  function getProject(id) {
    var found = null;
    state.projects.forEach(function (p) { if (p.project_id === id) { found = p; } });
    return found;
  }

  /* ---------------- ビュー切り替え ---------------- */

  function switchView(view) {
    state.activeView = view;
    ['run', 'projects', 'history'].forEach(function (v) {
      $['hl-view-' + v].hidden = v !== view;
    });
    $['hl-nav-run'].classList.toggle('active', view === 'run');
    $['hl-nav-projects'].classList.toggle('active', view === 'projects');
    $['hl-nav-history'].classList.toggle('active', view === 'history');
  }

  /* ---------------- 統計 ---------------- */

  function loadStats() {
    $['hl-stat-projects'].textContent = String(state.projects.length);
    apiFetch('/runs?limit=200').then(function (data) {
      var runs = asList(data, 'runs');
      var fixed = 0;
      var waitingPr = 0;
      runs.forEach(function (r) {
        fixed += (r.fixed_count || 0);
        if (r.pr_number && r.pr_state === 'open') { waitingPr += 1; }
      });
      $['hl-stat-runs'].textContent = String(runs.length);
      $['hl-stat-fixed'].textContent = String(fixed);
      $['hl-stat-pr'].textContent = String(waitingPr);
    }).catch(function () {
      $['hl-stat-runs'].textContent = '-';
      $['hl-stat-fixed'].textContent = '-';
      $['hl-stat-pr'].textContent = '-';
    });
  }

  /* ---------------- 接続先（プロジェクト） ---------------- */

  function loadProjects() {
    return apiFetch('/projects').then(function (data) {
      state.projects = asList(data, 'projects');
      renderProjects();
      renderProjectSelect();
      if (state.selectedProjectId) { updateProjectMeta(); }
    }).catch(function (e) { showError('接続先の一覧を取得できませんでした: ' + e.message); });
  }

  function renderProjectSelect() {
    var sel = $['hl-project-select'];
    var prevValue = sel.value;
    sel.textContent = '';
    state.projects.forEach(function (p) {
      var opt = el('option', null, p.name || p.project_id);
      opt.value = p.project_id;
      sel.appendChild(opt);
    });
    if (state.selectedProjectId && getProject(state.selectedProjectId)) {
      sel.value = state.selectedProjectId;
    } else if (prevValue && getProject(prevValue)) {
      sel.value = prevValue;
    }
  }

  function checkProject(projectId) {
    return apiFetch('/projects/' + projectId + '/check', { method: 'POST', body: JSON.stringify({}) })
      .then(function (data) {
        var list = asList(data, 'checks');
        if (!list.length) {
          list = CHECK_DEFS.map(function (def) {
            return getCheckItem(data, def.key) || { key: def.key, label: def.label, ok: false, detail: '' };
          });
        }
        var okAll = list.length > 0 && list.every(function (item) { return item.ok === true; });
        state.checkResults[projectId] = okAll;
        return { list: list, okAll: okAll };
      });
  }

  function getCheckItem(data, key) {
    var list = asList(data, 'checks');
    for (var i = 0; i < list.length; i++) {
      if (list[i].key === key || list[i].name === key) { return list[i]; }
    }
    if (data && data[key] && typeof data[key] === 'object') { return data[key]; }
    return null;
  }

  function renderProjects() {
    var tbody = $['hl-projects'];
    tbody.textContent = '';
    $['hl-projects-empty'].hidden = state.projects.length > 0;
    state.projects.forEach(function (p) {
      var tr = el('tr');
      tr.appendChild(el('td', null, p.name || p.project_id || '(名称未設定)'));
      var tdPath = el('td', 'hl-kv', p.repo_path || '');
      tdPath.title = p.repo_path || '';
      tr.appendChild(tdPath);
      tr.appendChild(el('td', null, p.default_branch || p.branch || ''));
      var tdCmd = el('td', 'hl-kv', p.verify_command || '');
      tdCmd.title = p.verify_command || '';
      tr.appendChild(tdCmd);
      tr.appendChild(el('td', null, p.agent || ''));

      var tdActions = el('td', 'hl-row-actions');
      var useBtn = el('button', 'btn-primary', '対象にする');
      useBtn.type = 'button';
      useBtn.addEventListener('click', function () { selectProject(p.project_id); switchView('run'); });

      var checkBtn = el('button', 'btn-outline-sm', '接続を確認');
      checkBtn.type = 'button';
      var checkResult = el('span', 'hl-row-check-result');
      checkBtn.addEventListener('click', function () {
        checkResult.textContent = '確認中…';
        checkProject(p.project_id).then(function (result) {
          checkResult.textContent = result.okAll ? '接続OK' : '接続エラー';
        }).catch(function (e) {
          checkResult.textContent = '確認失敗';
          showError('接続確認に失敗しました: ' + e.message);
        });
      });

      var editBtn = el('button', 'btn-outline-sm', '編集');
      editBtn.type = 'button';
      editBtn.addEventListener('click', function () { showConnectForm(p); });

      var deleteBtn = el('button', 'btn-outline-sm', '削除');
      deleteBtn.type = 'button';

      var deleteConfirm = el('div', 'hl-merge-confirm');
      deleteConfirm.hidden = true;
      deleteConfirm.appendChild(el('span', null, '本当に削除しますか？'));
      var delYes = el('button', 'btn-primary', 'はい、削除する');
      delYes.type = 'button';
      delYes.addEventListener('click', function () { deleteConfirm.hidden = true; deleteProject(p.project_id); });
      var delNo = el('button', 'btn-outline-sm', 'やめる');
      delNo.type = 'button';
      delNo.addEventListener('click', function () { deleteConfirm.hidden = true; });
      deleteConfirm.appendChild(delYes);
      deleteConfirm.appendChild(delNo);
      deleteBtn.addEventListener('click', function () { deleteConfirm.hidden = false; });

      tdActions.appendChild(useBtn);
      tdActions.appendChild(checkBtn);
      tdActions.appendChild(checkResult);
      tdActions.appendChild(editBtn);
      tdActions.appendChild(deleteBtn);
      tdActions.appendChild(deleteConfirm);
      tr.appendChild(tdActions);
      tbody.appendChild(tr);
    });
  }

  function showConnectForm(project) {
    state.editingProjectId = project ? project.project_id : null;
    $['hl-connect-form'].hidden = false;
    if (project) {
      $['hl-form-title'].textContent = '接続を編集する';
      $['hl-connect-submit'].textContent = '保存する';
      $['hl-f-name'].value = project.name || '';
      $['hl-f-path'].value = project.repo_path || '';
      $['hl-f-branch'].value = project.default_branch || project.branch || 'main';
      $['hl-f-cmd'].value = project.verify_command || '';
      $['hl-f-remote'].value = project.remote || 'origin';
      $['hl-f-github'].value = project.github_repo || '';
      if (project.agent) { $['hl-f-agent'].value = project.agent; }
      $['hl-f-max-iter'].value = project.max_iterations || 3;
      $['hl-f-concurrency'].value = project.max_parallel_agents || 3;
    } else {
      $['hl-form-title'].textContent = 'コードベースを接続する';
      $['hl-connect-submit'].textContent = '接続する';
      $['hl-f-name'].value = '';
      $['hl-f-path'].value = '';
      $['hl-f-branch'].value = 'main';
      $['hl-f-cmd'].value = '';
      $['hl-f-remote'].value = 'origin';
      $['hl-f-github'].value = '';
      $['hl-f-max-iter'].value = 3;
      $['hl-f-concurrency'].value = 3;
    }
  }
  function hideConnectForm() {
    $['hl-connect-form'].hidden = true;
  }

  function submitConnectForm() {
    var name = $['hl-f-name'].value.trim();
    var path = $['hl-f-path'].value.trim();
    if (!name || !path) { showError('名前とリポジトリのパスは必須です。'); return; }
    // キー名は API（web/routes/healing.py）の受け口と 1 文字も違えられない。
    var payload = {
      name: name,
      repo_path: path,
      default_branch: $['hl-f-branch'].value.trim() || 'main',
      verify_command: $['hl-f-cmd'].value.trim(),
      remote: $['hl-f-remote'].value.trim() || 'origin',
      github_repo: $['hl-f-github'].value.trim(),
      agent: $['hl-f-agent'].value,
      max_iterations: parseInt($['hl-f-max-iter'].value, 10) || 3,
      max_parallel_agents: parseInt($['hl-f-concurrency'].value, 10) || 3
    };
    clearError();
    var editingId = state.editingProjectId;
    var req = editingId
      ? apiFetch('/projects/' + editingId, { method: 'PATCH', body: JSON.stringify(payload) })
      : apiFetch('/projects', { method: 'POST', body: JSON.stringify(payload) });
    req.then(function (data) {
      hideConnectForm();
      return loadProjects().then(function () {
        loadStats();
        if (editingId) {
          selectProject(editingId);
        } else {
          var created = asObj(data, 'project');
          if (created && created.project_id) { selectProject(created.project_id); }
        }
      });
    }).catch(function (e) { showError((editingId ? '更新' : '接続') + 'に失敗しました: ' + e.message); });
  }

  function deleteProject(projectId) {
    clearError();
    apiFetch('/projects/' + projectId, { method: 'DELETE' }).then(function () {
      return loadProjects().then(function () {
        loadStats();
        if (state.selectedProjectId === projectId) {
          if (state.projects.length) {
            selectProject(state.projects[0].project_id);
          } else {
            state.selectedProjectId = null;
            clearRunView();
          }
        }
      });
    }).catch(function (e) { showError('接続の削除に失敗しました: ' + e.message); });
  }

  /* ---------------- 実行ビュー: 対象・接続確認 ---------------- */

  function updateProjectMeta() {
    var p = getProject(state.selectedProjectId);
    if (!p) { $['hl-project-meta'].textContent = ''; return; }
    var parts = [
      p.default_branch || p.branch || '',
      p.verify_command || '',
      p.agent || '',
      '最大' + (p.max_iterations || 3) + '周 / 同時' + (p.max_parallel_agents || 3) + '本'
    ];
    $['hl-project-meta'].textContent = parts.filter(function (v) { return v; }).join(' ・ ');
  }

  function updateRunSub(run) {
    if (run) {
      $['hl-run-sub'].textContent = (run.project_name || '') + '・ブランチ ' + (run.branch || '');
      return;
    }
    var p = getProject(state.selectedProjectId);
    $['hl-run-sub'].textContent = p ? ((p.name || '') + '・ブランチ ' + (p.default_branch || p.branch || '')) : '';
  }

  function runCheck() {
    if (!state.selectedProjectId) { return; }
    clearError();
    $['hl-checks'].textContent = '';
    checkProject(state.selectedProjectId).then(function (result) {
      renderChecksList(result.list);
    }).catch(function (e) { showError('接続確認に失敗しました: ' + e.message); });
  }

  function renderChecksList(list) {
    var ul = $['hl-checks'];
    ul.textContent = '';
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
  }

  /* ---------------- 実行の選択・切り替え ---------------- */

  function hideAllConfirms() {
    $['hl-start-confirm'].hidden = true;
    $['hl-cancel-confirm'].hidden = true;
    $['hl-merge-confirm'].hidden = true;
    $['hl-reject-confirm'].hidden = true;
  }

  function clearRunView() {
    state.selectedRunId = null;
    state.currentRun = null;
    state.lastRenderedRun = null;
    stopPolling();
    hideAllConfirms();
    $['hl-checks'].textContent = '';
    updateProjectMeta();
    updateRunSub(null);
    renderLoop(null);
    renderLogLines([]);
    renderStatusBadge(null);
    renderPrInfo(null);
    renderUnverified(null);
    updateActionButtons(null);
  }

  function selectProject(id, opts) {
    opts = opts || {};
    state.selectedProjectId = id || null;
    if ($['hl-project-select']) { $['hl-project-select'].value = id || ''; }
    clearRunView();
    if (!id) { return; }
    if (opts.openRunId) { openRun(opts.openRunId); return; }
    apiFetch('/runs?project_id=' + encodeURIComponent(id) + '&limit=1').then(function (data) {
      var runs = asList(data, 'runs');
      if (runs.length) { openRun(runs[0].run_id); }
    }).catch(function (e) { showError('実行状況の取得に失敗しました: ' + e.message); });
  }

  function startRun() {
    if (!state.selectedProjectId) { return; }
    clearError();
    var payload = {
      project_id: state.selectedProjectId,
      extra_instructions: ($['hl-instructions'] ? $['hl-instructions'].value.trim() : '')
    };
    $['hl-start'].disabled = true;
    apiFetch('/runs', { method: 'POST', body: JSON.stringify(payload) }).then(function (data) {
      $['hl-start'].disabled = false;
      var run = asObj(data, 'run');
      if (run && run.run_id) {
        openRun(run.run_id);
        loadStats();
        loadHistory(state.historyLimit || 20);
      }
    }).catch(function (e) {
      $['hl-start'].disabled = false;
      showError('ヒーリングの開始に失敗しました: ' + e.message);
    });
  }

  function openRun(runId) {
    state.selectedRunId = runId;
    hideAllConfirms();
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
        loadStats();
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

  /* ---------------- 実行の描画 ---------------- */

  function renderRun(run) {
    renderStatusBadge(run);
    updateRunSub(run);
    renderLoop(run);
    renderLogLines(run.log || []);
    renderPrInfo(run);
    renderUnverified(run);
    updateActionButtons(run);
  }

  function renderStatusBadge(run) {
    var badge = $['hl-status'];
    badge.className = 'hl-badge';
    if (!run) {
      badge.textContent = '未選択';
      $['hl-run-error'].hidden = true;
      $['hl-run-error'].textContent = '';
      return;
    }
    badge.classList.add(statusBadgeClass(run.status));
    var label = STATUS_LABELS[run.status] || run.status || '';
    var step = run.step_label || '';
    // step_label は状態名で始まることが多い（status=fixing / step_label="修正（1周目・1件）"）。
    // そのまま連結すると二重になるため、細かい方が状態名を含むならそちらだけを出す。
    if (step && step.indexOf(label) === 0) {
      badge.textContent = step;
    } else {
      badge.textContent = label + (step ? '（' + step + '）' : '');
    }
    if (run.error) {
      $['hl-run-error'].textContent = run.error;
      $['hl-run-error'].hidden = false;
    } else {
      $['hl-run-error'].textContent = '';
      $['hl-run-error'].hidden = true;
    }
  }

  function updateActionButtons(run) {
    var ids = ['hl-create-pr', 'hl-rerun', 'hl-approve', 'hl-merge', 'hl-reject', 'hl-cancel'];
    ids.forEach(function (id) { $[id].hidden = false; });

    if (!run) {
      ids.forEach(function (id) { $[id].disabled = true; });
    } else {
      var status = run.status;
      var hasPr = !!(run.pull_request && run.pull_request.number);
      var isTerminal = TERMINAL_STATUSES.indexOf(status) !== -1;
      var isAwaiting = status === 'awaiting_human';
      var isRunning = !isTerminal && !isAwaiting;

      if (isRunning) {
        $['hl-cancel'].disabled = false;
        $['hl-create-pr'].disabled = true;
        $['hl-rerun'].disabled = true;
        $['hl-approve'].disabled = true;
        $['hl-merge'].disabled = true;
        $['hl-reject'].disabled = true;
      } else if (isAwaiting) {
        $['hl-cancel'].hidden = true;
        $['hl-create-pr'].disabled = hasPr;
        $['hl-rerun'].disabled = false;
        $['hl-approve'].disabled = false;
        $['hl-reject'].disabled = false;
        $['hl-merge'].disabled = !hasPr;
      } else {
        // 終端（succeeded/no_defects/failed/cancelled）
        $['hl-cancel'].hidden = true;
        $['hl-rerun'].disabled = false;
        $['hl-create-pr'].disabled = hasPr;
        $['hl-approve'].disabled = true;
        $['hl-reject'].disabled = true;
        $['hl-merge'].disabled = !hasPr;
      }

      if (hasPr) {
        $['hl-create-pr'].hidden = true;
        $['hl-merge'].disabled = false;
      }
    }

    if ($['hl-cancel'].hidden) { $['hl-cancel-confirm'].hidden = true; }
    if ($['hl-merge'].hidden || $['hl-merge'].disabled) { $['hl-merge-confirm'].hidden = true; }
    if ($['hl-reject'].hidden || $['hl-reject'].disabled) { $['hl-reject-confirm'].hidden = true; }
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
      var cls = 'hl-step' + (st === 'pending' ? '' : ' is-' + st);
      var step = el('div', cls);
      step.appendChild(el('span', 'hl-step-dot'));
      step.appendChild(el('span', null, labels[i]));
      wrap.appendChild(step);
    });
    return wrap;
  }

  function renderVerifyResult(v) {
    var wrap = el('div', 'hl-verify-result');
    if (!v) { wrap.appendChild(el('span', null, '未実行')); return wrap; }
    // 検証そのものが動かなかった場合、件数だけを出すと「不具合が無かった」と読めてしまう。
    // 理由を最初に、目立つ形で出す。
    if (v.error) {
      wrap.appendChild(el('b', 'hl-verify-error', '検証を実行できませんでした'));
      wrap.appendChild(el('span', 'hl-verify-error-detail', v.error));
      if (v.command) { wrap.appendChild(el('span', 'hl-kv', v.command)); }
      return wrap;
    }
    var summary = '失敗 ' + (v.failed != null ? v.failed : '?') + ' / 全 ' + (v.total != null ? v.total : '?');
    if (typeof v.duration_sec === 'number') { summary += '（' + v.duration_sec.toFixed(1) + ' 秒）'; }
    wrap.appendChild(el('b', null, summary));
    if (v.command) { wrap.appendChild(el('span', 'hl-kv', v.command)); }
    return wrap;
  }

  // 該当箇所の根拠に付く理由コードの和訳。API が知らないコードを返しても
  // そのまま出す（空欄にすると「根拠が無い」と読めてしまう）。
  var REASON_LABELS = {
    traceback: '実行時トレース',
    'import': 'import 関係',
    'recent-change': '直近の変更',
    'test-name': 'テスト名'
  };
  var SEVERITY_RANK = { critical: 0, high: 1, medium: 2, low: 3 };

  function severityRank(sev) {
    var r = SEVERITY_RANK[sev];
    return r === undefined ? 9 : r;
  }

  /* 該当箇所の根拠。locations は古い実行履歴には存在しないので undefined 前提で守る。 */
  function renderEvidence(locations) {
    var wrap = el('div', 'hl-evidence');
    wrap.appendChild(el('div', 'hl-evidence-head', '該当箇所の根拠'));
    var list = (locations || []).slice();
    if (list.length === 0) {
      wrap.appendChild(el('p', 'hl-evidence-empty', '根拠を特定できませんでした。'));
      return wrap;
    }
    list.sort(function (a, b) { return (b.score || 0) - (a.score || 0); });
    var table = el('table', 'data hl-evidence-table');
    var thead = el('thead');
    var trh = el('tr');
    ['ファイル', '根拠', '確度'].forEach(function (t) { trh.appendChild(el('th', null, t)); });
    thead.appendChild(trh);
    table.appendChild(thead);
    var tbody = el('tbody');
    list.forEach(function (loc) {
      var tr = el('tr');
      var path = loc.path || '';
      var tdPath = el('td', 'hl-kv hl-ellipsis', path);
      tdPath.title = loc.detail ? (path + ' — ' + loc.detail) : path;
      tr.appendChild(tdPath);
      var tdReason = el('td', null, REASON_LABELS[loc.reason] || loc.reason || '不明');
      if (loc.detail) { tdReason.title = loc.detail; }
      tr.appendChild(tdReason);
      // score は 0〜1 で来る想定だが、0〜100 で来ても壊さない。
      var pct = null;
      if (typeof loc.score === 'number' && isFinite(loc.score)) {
        pct = loc.score <= 1 ? Math.round(loc.score * 100) : Math.round(loc.score);
      }
      tr.appendChild(el('td', 'num', pct === null ? '—' : pct + '%'));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  /* 確認が必要な点。risks が空でも黙らない（「兆候が無い＝正しい」ではないため）。 */
  function renderRisks(risks) {
    var wrap = el('div', 'hl-risk');
    wrap.appendChild(el('div', 'hl-risk-head', '確認が必要な点'));
    var list = (risks || []).slice();
    if (list.length === 0) {
      wrap.appendChild(el('p', 'hl-risk-none',
        '機械的な兆候はありませんでした。テストの通過は正しさを保証しません。差分を確認してください。'));
      return wrap;
    }
    list.sort(function (a, b) { return severityRank(a.severity) - severityRank(b.severity); });
    var ul = el('ul', 'hl-risk-list');
    list.forEach(function (r) {
      var sev = r.severity || 'low';
      var li = el('li', 'hl-risk-item is-' + sev);
      var line = el('div', 'hl-risk-line');
      line.appendChild(el('span', 'hl-risk-badge is-' + sev, SEVERITY_LABELS[sev] || sev));
      line.appendChild(el('span', 'hl-risk-label', r.label || r.code || ''));
      li.appendChild(line);
      if (r.detail) { li.appendChild(el('div', 'hl-risk-detail', r.detail)); }
      ul.appendChild(li);
    });
    wrap.appendChild(ul);
    return wrap;
  }

  /* ---------------- 最小の Markdown 変換（見出し・表・箇条書き・コードフェンスのみ） ----------------
     ライブラリも CDN も足さない。innerHTML を一切使わず DOM を組み立てるため、
     レポート本文がマークアップとして解釈されることはない（XSS 防止）。 */

  function appendInline(parent, text) {
    var rest = String(text == null ? '' : text);
    var re = /(`[^`]+`|\*\*[^*]+\*\*)/;
    while (rest) {
      var m = re.exec(rest);
      if (!m) { parent.appendChild(document.createTextNode(rest)); break; }
      if (m.index > 0) { parent.appendChild(document.createTextNode(rest.slice(0, m.index))); }
      var token = m[0];
      if (token.charAt(0) === '`') {
        parent.appendChild(el('code', 'hl-report-inline-code', token.slice(1, -1)));
      } else {
        parent.appendChild(el('b', null, token.slice(2, -2)));
      }
      rest = rest.slice(m.index + token.length);
    }
  }

  function isTableDivider(line) {
    return /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line);
  }
  function splitTableRow(line) {
    return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|')
      .map(function (c) { return c.trim(); });
  }

  function buildReportTable(rows) {
    var table = el('table', 'data hl-report-table');
    var tbody = el('tbody');
    var headDone = false;
    rows.forEach(function (raw, idx) {
      if (isTableDivider(raw)) { return; }
      var isHead = !headDone && idx === 0;
      var tr = el('tr');
      splitTableRow(raw).forEach(function (c) {
        var cell = el(isHead ? 'th' : 'td');
        appendInline(cell, c);
        tr.appendChild(cell);
      });
      if (isHead) {
        var thead = el('thead');
        thead.appendChild(tr);
        table.appendChild(thead);
        headDone = true;
      } else {
        tbody.appendChild(tr);
      }
    });
    table.appendChild(tbody);
    return table;
  }

  function renderMarkdown(md) {
    var root = el('div', 'hl-report-body');
    var lines = String(md || '').split('\n');
    var i = 0;
    while (i < lines.length) {
      var line = lines[i];

      if (/^\s*```/.test(line)) {
        i += 1;
        var code = [];
        while (i < lines.length && !/^\s*```/.test(lines[i])) { code.push(lines[i]); i += 1; }
        i += 1;
        root.appendChild(el('pre', 'hl-report-code', code.join('\n')));
        continue;
      }

      var h = /^\s*(#{1,6})\s+(.*)$/.exec(line);
      if (h) {
        // レポートは画面の一部なので、見出しレベルは h3 以下に押し下げる。
        var head = el('h' + Math.min(6, h[1].length + 2), 'hl-report-head');
        appendInline(head, h[2]);
        root.appendChild(head);
        i += 1;
        continue;
      }

      if (/^\s*\|/.test(line)) {
        var rows = [];
        while (i < lines.length && /^\s*\|/.test(lines[i])) { rows.push(lines[i]); i += 1; }
        root.appendChild(buildReportTable(rows));
        continue;
      }

      if (/^\s*[-*+]\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line)) {
        var ordered = /^\s*\d+[.)]\s+/.test(line);
        var listEl = el(ordered ? 'ol' : 'ul', 'hl-report-list');
        var itemRe = ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*+]\s+/;
        while (i < lines.length && itemRe.test(lines[i])) {
          var li = el('li');
          appendInline(li, lines[i].replace(itemRe, ''));
          listEl.appendChild(li);
          i += 1;
        }
        root.appendChild(listEl);
        continue;
      }

      if (!line.trim()) { i += 1; continue; }

      var para = [];
      while (i < lines.length && lines[i].trim()
             && !/^\s*(```|#{1,6}\s|[-*+]\s|\d+[.)]\s|\|)/.test(lines[i])) {
        para.push(lines[i].trim());
        i += 1;
      }
      if (para.length) {
        var p = el('p', 'hl-report-p');
        appendInline(p, para.join(' '));
        root.appendChild(p);
      } else {
        i += 1;
      }
    }
    return root;
  }

  /* バグレポート。開閉は「差分を見る」と同じ形にそろえる。 */
  function buildReportBlock(reportMd) {
    var wrap = el('div', 'hl-report');
    var toggle = el('button', 'btn-outline-sm', 'バグレポートを見る');
    toggle.type = 'button';
    var body = renderMarkdown(reportMd);
    body.hidden = true;
    toggle.addEventListener('click', function () {
      body.hidden = !body.hidden;
      toggle.textContent = body.hidden ? 'バグレポートを見る' : 'バグレポートを隠す';
    });
    wrap.appendChild(toggle);
    wrap.appendChild(body);
    return wrap;
  }

  function renderDefectsTable(defects) {
    if (!defects || defects.length === 0) {
      return el('p', 'hl-hint', '検出した不具合はありません。');
    }
    var table = el('table', 'data dashboard-table');
    var thead = el('thead');
    var trh = el('tr');
    ['重大度', '事象', '失敗したテスト', '該当しそうなファイル'].forEach(function (t) { trh.appendChild(el('th', null, t)); });
    thead.appendChild(trh);
    table.appendChild(thead);
    var tbody = el('tbody');
    defects.forEach(function (d) {
      var tr = el('tr');
      var tdSev = el('td');
      tdSev.appendChild(el('span', 'hl-sev is-' + d.severity, SEVERITY_LABELS[d.severity] || d.severity));
      tr.appendChild(tdSev);
      tr.appendChild(el('td', null, d.title || d.message || ''));
      var tdTest = el('td', 'hl-kv hl-ellipsis', d.test_id || '');
      tdTest.title = d.test_id || '';
      tr.appendChild(tdTest);
      var files = (d.suspect_files || []).join(', ');
      var tdFile = el('td', 'hl-kv hl-ellipsis', files);
      tdFile.title = files;
      tr.appendChild(tdFile);
      tbody.appendChild(tr);

      // なぜそのファイルが疑われるのかを、欠陥のすぐ下に出す。
      var evTr = el('tr', 'hl-evidence-row');
      var evTd = el('td');
      evTd.colSpan = 4;
      evTd.appendChild(renderEvidence(d.locations));
      evTr.appendChild(evTd);
      tbody.appendChild(evTr);
    });
    table.appendChild(tbody);
    return table;
  }

  function buildDiffElement(diffText) {
    var pre = el('pre', 'hl-diff');
    (diffText || '').split('\n').forEach(function (line) {
      var span;
      if (line.indexOf('+') === 0 && line.indexOf('+++') !== 0) { span = el('span', 'add', line); }
      else if (line.indexOf('-') === 0 && line.indexOf('---') !== 0) { span = el('span', 'del', line); }
      else { span = el('span', null, line); }
      pre.appendChild(span);
    });
    return pre;
  }

  function pillEl(status) {
    return el('span', 'hl-pill ' + status, PROPOSAL_STATUS_LABELS[status] || status);
  }

  function renderProposalsTable(proposals) {
    if (!proposals || proposals.length === 0) {
      return el('p', 'hl-hint', '修正はまだありません。');
    }
    // 列幅は CSS で決める（「差分を見る」が 3 行に折れないだけの幅が要る）。
    var table = el('table', 'data dashboard-table hl-proposals-table');
    var thead = el('thead');
    var trh = el('tr');
    ['エージェント', '状態', '何をどう直したか', '変更ファイル', '差分'].forEach(function (t) { trh.appendChild(el('th', null, t)); });
    thead.appendChild(trh);
    table.appendChild(thead);
    var tbody = el('tbody');
    proposals.forEach(function (p) {
      var tr = el('tr');
      var tdAgent = el('td', null, p.agent || '');
      tdAgent.title = p.agent || '';
      tr.appendChild(tdAgent);

      var tdStatus = el('td');
      tdStatus.appendChild(pillEl(p.status));
      tr.appendChild(tdStatus);

      var tdSummary = el('td');
      tdSummary.appendChild(document.createTextNode(p.summary || ''));
      // 失敗/時間切れ/変更なしの理由は必ず出す（2 エージェントの競合など、他に出典が無いため）。
      if ((p.status === 'failed' || p.status === 'timeout' || p.status === 'skipped') && p.error) {
        var errEl = el('div', 'hl-err', p.error);
        tdSummary.appendChild(errEl);
      }
      tr.appendChild(tdSummary);

      var filesN = (p.files_changed || []).length;
      tr.appendChild(el('td', null, filesN + ' ファイル変更'));

      var tdDiff = el('td');
      tr.appendChild(tdDiff);
      tbody.appendChild(tr);
      if (p.diff) {
        var toggle = el('button', 'btn-outline-sm', '差分を見る');
        toggle.type = 'button';
        tdDiff.appendChild(toggle);
        var diffTr = el('tr');
        diffTr.hidden = true;
        var diffTd = el('td');
        diffTd.colSpan = 5;
        diffTd.appendChild(buildDiffElement(p.diff));
        diffTr.appendChild(diffTd);
        tbody.appendChild(diffTr);
        toggle.addEventListener('click', function () {
          diffTr.hidden = !diffTr.hidden;
          toggle.textContent = diffTr.hidden ? '差分を見る' : '差分を隠す';
        });
      }

      // 確認が必要な点は常に出す（空でも「兆候が無かった」と書く）。
      // バグレポートは差分と同じ形のトグルで開閉する。
      var detailTr = el('tr', 'hl-detail-row');
      var detailTd = el('td');
      detailTd.colSpan = 5;
      detailTd.appendChild(renderRisks(p.risks));
      if (p.report_md) { detailTd.appendChild(buildReportBlock(p.report_md)); }
      detailTr.appendChild(detailTd);
      tbody.appendChild(detailTr);
    });
    table.appendChild(tbody);
    return table;
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
      block.appendChild(el('h4', 'hl-sub', '検証結果'));
      block.appendChild(renderVerifyResult(iter.verify_before));
      if (iter.defects) {
        block.appendChild(el('h4', 'hl-sub', '検出した不具合'));
        block.appendChild(renderDefectsTable(iter.defects));
      }
      if (iter.proposals) {
        block.appendChild(el('h4', 'hl-sub', '修正'));
        block.appendChild(renderProposalsTable(iter.proposals));
      }
      if (iter.verify_after) {
        block.appendChild(el('h4', 'hl-sub', '再検証結果'));
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

  function renderPrInfo(run) {
    var wrap = $['hl-pr-info'];
    wrap.textContent = '';
    var pr = run && run.pull_request;
    if (!pr || !pr.number) { wrap.hidden = true; return; }
    wrap.hidden = false;
    wrap.appendChild(el('span', 'hl-badge', pr.state || ''));
    wrap.appendChild(el('div', null, '#' + pr.number + ' ' + (pr.title || '')));
    var link = el('a', null, pr.url || '');
    link.href = pr.url || '#';
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    wrap.appendChild(link);
    if (run.decisions && run.decisions.length > 0) {
      var hist = el('ul');
      run.decisions.forEach(function (d) {
        var actionLabel = d.action === 'approve' ? '承認' : (d.action === 'merge' ? 'マージ' : (d.action === 'reject' ? '却下' : d.action));
        var text = fmtTime(d.at) + ' ' + actionLabel + (d.actor ? '（' + d.actor + '）' : '') + (d.note ? ': ' + d.note : '');
        hist.appendChild(el('li', null, text));
      });
      wrap.appendChild(hist);
    }
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
    var note = $['hl-decision-note'] ? $['hl-decision-note'].value.trim() : '';
    apiFetch('/runs/' + state.selectedRunId + '/decision', { method: 'POST', body: JSON.stringify({ action: action, note: note }) })
      .then(function () {
        if ($['hl-decision-note']) { $['hl-decision-note'].value = ''; }
        return fetchAndRenderRun(state.selectedRunId);
      })
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

  /* ---------------- 実行履歴ビュー ---------------- */

  function loadHistory(limit) {
    limit = limit || 20;
    state.historyLimit = limit;
    return apiFetch('/runs?limit=' + limit).then(function (data) {
      state.historyRuns = asList(data, 'runs');
      renderHistory();
    }).catch(function (e) { showError('実行履歴を取得できませんでした: ' + e.message); });
  }

  function renderHistory() {
    var tbody = $['hl-runs'];
    tbody.textContent = '';
    var runs = state.historyRuns || [];
    $['hl-runs-empty'].hidden = runs.length > 0;
    $['hl-runs-more'].hidden = runs.length < (state.historyLimit || 20);
    runs.forEach(function (r) {
      var tr = el('tr');
      var tdStatus = el('td');
      tdStatus.appendChild(el('span', 'hl-badge ' + statusBadgeClass(r.status), STATUS_LABELS[r.status] || r.status));
      tr.appendChild(tdStatus);
      tr.appendChild(el('td', null, fmtTime(r.started_at)));
      tr.appendChild(el('td', null, r.project_name || r.project_id || ''));
      tr.appendChild(el('td', 'num', r.iterations != null ? String(r.iterations) : ''));
      tr.appendChild(el('td', 'num', r.fixed_count != null ? String(r.fixed_count) : ''));
      var prText = r.pr_number ? ('#' + r.pr_number + (r.pr_state ? '（' + r.pr_state + '）' : '')) : '';
      tr.appendChild(el('td', null, prText));

      var tdActions = el('td');
      var openBtn = el('button', 'btn-outline-sm', '開く');
      openBtn.type = 'button';
      openBtn.addEventListener('click', function () {
        selectProject(r.project_id, { openRunId: r.run_id });
        switchView('run');
      });
      tdActions.appendChild(openBtn);
      tr.appendChild(tdActions);

      tbody.appendChild(tr);
    });
  }

  /* ---------------- 初期化 ---------------- */

  function init() {
    cacheDom();
    state.focusRunId = document.body.getAttribute('data-focus-run-id') || '';

    $['hl-nav-run'].addEventListener('click', function () { switchView('run'); });
    $['hl-nav-projects'].addEventListener('click', function () { switchView('projects'); });
    $['hl-nav-history'].addEventListener('click', function () { switchView('history'); });
    $['hl-add-project'].addEventListener('click', function () { switchView('projects'); showConnectForm(null); });
    // 接続先ビューにも同じ入口を置いてある。サイドバーまで戻らせないため。
    var addOnList = document.getElementById('hl-add-project-2');
    if (addOnList) { addOnList.addEventListener('click', function () { showConnectForm(null); }); }

    $['hl-project-select'].addEventListener('change', function () { selectProject(this.value); });

    $['hl-connect-submit'].addEventListener('click', submitConnectForm);
    $['hl-connect-cancel'].addEventListener('click', hideConnectForm);

    $['hl-check-btn'].addEventListener('click', runCheck);

    $['hl-start'].addEventListener('click', function () { $['hl-start-confirm'].hidden = false; });
    $['hl-start-yes'].addEventListener('click', function () { $['hl-start-confirm'].hidden = true; startRun(); });
    $['hl-start-no'].addEventListener('click', function () { $['hl-start-confirm'].hidden = true; });

    $['hl-cancel'].addEventListener('click', function () { $['hl-cancel-confirm'].hidden = false; });
    $['hl-cancel-yes'].addEventListener('click', function () { $['hl-cancel-confirm'].hidden = true; cancelRun(); });
    $['hl-cancel-no'].addEventListener('click', function () { $['hl-cancel-confirm'].hidden = true; });

    $['hl-merge'].addEventListener('click', function () { $['hl-merge-confirm'].hidden = false; });
    $['hl-merge-yes'].addEventListener('click', function () { $['hl-merge-confirm'].hidden = true; submitDecision('merge'); });
    $['hl-merge-no'].addEventListener('click', function () { $['hl-merge-confirm'].hidden = true; });

    $['hl-reject'].addEventListener('click', function () { $['hl-reject-confirm'].hidden = false; });
    $['hl-reject-yes'].addEventListener('click', function () { $['hl-reject-confirm'].hidden = true; submitDecision('reject'); });
    $['hl-reject-no'].addEventListener('click', function () { $['hl-reject-confirm'].hidden = true; });

    $['hl-approve'].addEventListener('click', function () { submitDecision('approve'); });
    $['hl-create-pr'].addEventListener('click', createPullRequest);
    $['hl-rerun'].addEventListener('click', function () { submitDecision('rerun'); });

    $['hl-runs-more'].addEventListener('click', function () {
      loadHistory((state.historyLimit || 20) + 20);
    });

    switchView('run');

    loadProjects().then(function () {
      loadStats();
      if (!state.projects.length) { clearRunView(); return; }
      if (state.focusRunId) {
        var fid = state.focusRunId;
        state.focusRunId = '';
        apiFetch('/runs/' + encodeURIComponent(fid)).then(function (data) {
          var run = asObj(data, 'run');
          selectProject(run.project_id || state.projects[0].project_id, { openRunId: fid });
        }).catch(function () { selectProject(state.projects[0].project_id); });
      } else {
        selectProject(state.projects[0].project_id);
      }
    });

    loadHistory(20);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
