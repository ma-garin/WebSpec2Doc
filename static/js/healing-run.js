'use strict';

/* オートヒーリング設定画面（templates/healing.html）: 実行の詳細: 対象の選択・開始・ポーリング・状態とツールバー・工程・検証結果・根拠・修正案・ログ
   読み込み順: healing-core.js → healing-projects.js → healing-report.js → healing-run.js → healing-actions.js → healing-history.js → healing.js。
   ファイル間の共有は window.HealingApp（HL）だけ。他ファイルの関数は呼び出し時に HL から引く。 */
(function (HL) {
  /* ---- 他ファイルの宣言 ---- */
  var $ = HL.$;
  var POLL_MS = HL.POLL_MS;
  var POLL_STOP_STATUSES = HL.POLL_STOP_STATUSES;
  var PROPOSAL_STATUS_KIND = HL.PROPOSAL_STATUS_KIND;
  var PROPOSAL_STATUS_LABELS = HL.PROPOSAL_STATUS_LABELS;
  var PROPOSAL_STATUS_TITLES = HL.PROPOSAL_STATUS_TITLES;
  var SEVERITY_LABELS = HL.SEVERITY_LABELS;
  var STATUS_LABELS = HL.STATUS_LABELS;
  var TERMINAL_STATUSES = HL.TERMINAL_STATUSES;
  function agentDisplayName() { return HL.agentDisplayName.apply(this, arguments); }
  function apiFetch() { return HL.apiFetch.apply(this, arguments); }
  function applyFixedHint() { return HL.applyFixedHint.apply(this, arguments); }
  function asList() { return HL.asList.apply(this, arguments); }
  function asObj() { return HL.asObj.apply(this, arguments); }
  function buildDiffElement() { return HL.buildDiffElement.apply(this, arguments); }
  function clearCheckState() { return HL.clearCheckState.apply(this, arguments); }
  function clearError() { return HL.clearError.apply(this, arguments); }
  function closeAllConfirms() { return HL.closeAllConfirms.apply(this, arguments); }
  function el() { return HL.el.apply(this, arguments); }
  function fmtTime() { return HL.fmtTime.apply(this, arguments); }
  function flattenParens() { return HL.flattenParens.apply(this, arguments); }
  function humanizeError() { return HL.humanizeError.apply(this, arguments); }
  function loadHistory() { return HL.loadHistory.apply(this, arguments); }
  function loadStats() { return HL.loadStats.apply(this, arguments); }
  function nextActionFor() { return HL.nextActionFor.apply(this, arguments); }
  function renderDefectsTable() { return HL.renderDefectsTable.apply(this, arguments); }
  function renderMarkdown() { return HL.renderMarkdown.apply(this, arguments); }
  function renderPrInfo() { return HL.renderPrInfo.apply(this, arguments); }
  function renderProjects() { return HL.renderProjects.apply(this, arguments); }
  function renderUnverified() { return HL.renderUnverified.apply(this, arguments); }
  function setConfirmOpen() { return HL.setConfirmOpen.apply(this, arguments); }
  function setTail() { return HL.setTail.apply(this, arguments); }
  function showError() { return HL.showError.apply(this, arguments); }
  var state = HL.state;
  function statusBadgeClass() { return HL.statusBadgeClass.apply(this, arguments); }
  function syncHash() { return HL.syncHash.apply(this, arguments); }
  function updateProjectMeta() { return HL.updateProjectMeta.apply(this, arguments); }
  function updateRunSub() { return HL.updateRunSub.apply(this, arguments); }


  /* ---------------- 実行の選択・切り替え ---------------- */

  function hideAllConfirms() {
    closeAllConfirms(null);
  }

  function clearRunView() {
    state.selectedRunId = null;
    state.currentRun = null;
    state.lastRenderedRun = null;
    stopPolling();
    hideAllConfirms();
    // 接続先を切り替えたら前の接続確認の結果は無効。表示も開始ボタンの無効化も戻す。
    clearCheckState();
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
    state.highlightProjectId = null;
    state.selectedProjectId = id || null;
    if ($['hl-project-select']) { $['hl-project-select'].value = id || ''; }
    // 統計は選択中の接続先で絞るので、切り替えのたびに数え直す。
    loadStats();
    // 選択中の行の見た目を入れ替えるため、接続先の表を描き直す。
    if ($['hl-projects']) { renderProjects(); }
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
    if ($['hl-start']) { $['hl-start'].disabled = true; }
    apiFetch('/runs', { method: 'POST', body: JSON.stringify(payload) }).then(function (data) {
      if ($['hl-start']) { $['hl-start'].disabled = false; }
      var run = asObj(data, 'run');
      if (run && run.run_id) {
        openRun(run.run_id);
        loadStats();
        loadHistory(state.historyLimit || 20);
      }
    }).catch(function (e) {
      if ($['hl-start']) { $['hl-start'].disabled = false; }
      showError('ヒーリングの開始に失敗しました: ' + e.message);
    });
  }

  function openRun(runId) {
    state.selectedRunId = runId;
    if (state.activeView === 'run') { syncHash(false); }
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
    state.riskCounts = collectRiskCounts(run);
    renderStatusBadge(run);
    renderWsStatus(run);
    renderRunContext(run);
    updateRunSub(run);
    renderLoop(run);
    renderLogLines(run.log || [], run.error || '');
    renderPrInfo(run);
    renderUnverified(run);
    updateActionButtons(run);
    renderRiskSummary(run);
    renderBlockers(run);
    applyFixedHint();
  }

  /* ---------------- リスク要約（判断の直前に出す） ----------------
     危険な兆候が画面のはるか下にしか無いと、判断者はスクロールせずに PR を出す。
     判断ボタンと同じ視野に 1 行で出し、押せば該当箇所まで送る。 */

  function collectRiskCounts(run) {
    var counts = { total: 0, high: 0, medium: 0, low: 0 };
    var iterations = (run && run.iterations) ? run.iterations : [];
    iterations.forEach(function (iter) {
      (iter.proposals || []).forEach(function (p) {
        (p.risks || []).forEach(function (r) {
          // severity は大文字で来ることがある。取りこぼすと「重大 0 件」と誤って出る。
          var sev = String(r.severity || 'low').toLowerCase();
          counts.total += 1;
          if (sev === 'critical' || sev === 'high') { counts.high += 1; }
          else if (sev === 'medium') { counts.medium += 1; }
          else { counts.low += 1; }
        });
      });
    });
    return counts;
  }

  function riskCounts() {
    return state.riskCounts || { total: 0, high: 0, medium: 0, low: 0 };
  }

  // 該当箇所は畳まれた詳細行の中にある。開いてから送らないと空振りする。
  function revealFirstRisk() {
    var loop = $['hl-loop'];
    if (!loop) { return; }
    var target = loop.querySelector('.hl-risk-item.is-critical')
      || loop.querySelector('.hl-risk-item.is-high')
      || loop.querySelector('.hl-risk');
    if (!target) { return; }
    var row = target.closest ? target.closest('.hl-detail-row') : null;
    if (row && row.hidden) {
      row.hidden = false;
      var headRow = row.previousElementSibling;
      var toggle = headRow ? headRow.querySelector('[data-testid="hl-toggle-detail"]') : null;
      if (toggle) {
        toggle.setAttribute('aria-expanded', 'true');
        toggle.textContent = '詳細を閉じる';
      }
    }
    target.scrollIntoView({ block: 'center' });
  }

  function riskSummaryText(counts) {
    if (counts.total === 0) {
      return '機械的に検出できる兆候はありませんでした。';
    }
    var text = '⚠ 確認が必要な点が ' + counts.total + ' 件';
    if (counts.high > 0) { text += '（重大 ' + counts.high + ' 件）'; }
    return text + 'あります。差分を確認してください。';
  }

  function renderRiskSummary(run) {
    var badge = $['hl-status'];
    var head = badge && badge.closest ? badge.closest('.dashboard-section-head') : null;
    if (!head || !head.parentNode) { return; }
    var old = head.parentNode.querySelector('.hl-risk-summary');
    if (old && old.parentNode) { old.parentNode.removeChild(old); }
    if (!run) { state.riskCounts = null; return; }
    var counts = riskCounts();
    var level = counts.high > 0 ? 'high' : (counts.medium > 0 ? 'medium' : 'none');
    var btn = el('button', 'hl-risk-summary hl-risk-summary-' + level, riskSummaryText(counts));
    btn.type = 'button';
    btn.setAttribute('data-testid', 'hl-risk-summary');
    btn.addEventListener('click', revealFirstRisk);
    /* 判断ボタン群の直下・「判断のメモ」より前に置く。メモは label と input が
       1 組で意味を持つので、その間には絶対に割り込ませない（行ごと前に入れる）。 */
    var noteRow = head.parentNode.querySelector('.hl-decision-note-row');
    var anchor = (noteRow && noteRow.parentNode === head.parentNode) ? noteRow : head.nextSibling;
    head.parentNode.insertBefore(btn, anchor);
  }

  /* 実行が 1 件も選ばれていないのに「未選択」バッジと対象名を出すと、
     直下の空状態（まだ実行がありません）と矛盾する。見出しごと隠す。 */
  /* 実行が 1 件も選ばれていないと、空の黒い箱だけが 140px 居座る。見出しごと隠す。
     実行を選んだ／開始した時点で表示に戻し、実行中・実行後は常時表示のまま（折りたたまない）。 */
  function setLogSectionVisible(visible) {
    var logEl = $['hl-log'];
    var card = logEl && logEl.closest ? logEl.closest('.hl-log-card') : null;
    if (!card) { return; }
    card.hidden = !visible;
    // .card 側の display 指定に hidden が負けることがあるため、表示も明示で落とす。
    card.style.display = visible ? '' : 'none';
    var head = card.previousElementSibling;
    if (head && head.classList && head.classList.contains('dashboard-section-head')) {
      head.hidden = !visible;
      head.style.display = visible ? '' : 'none';
    }
  }

  function setRunSectionVisible(visible) {
    var badge = $['hl-status'];
    var head = badge && badge.closest ? badge.closest('.dashboard-section-head') : null;
    if (head) { head.hidden = !visible; }
    var noteRow = document.querySelector('.hl-decision-note-row');
    if (noteRow) { noteRow.hidden = !visible; }
    setLogSectionVisible(visible);
  }

  /* ---------------- 判断の文脈（共通部品 WS2D との対応） ----------------
     内部の状態名は変えず、表示のときだけ標準語（WS2D.status）へ対応付ける。
     WS2D が読み込めない場合は何も足さない（既存の表示だけで動く）。 */
  var WS_STATUS_MAP = {
    queued: ['preparing', '受付'], preparing: ['preparing', null], verifying: ['running', '検証中'],
    analyzing: ['running', '欠陥の切り出し中'], fixing: ['running', '修正中'],
    reverifying: ['running', '再検証中'], awaiting_human: ['waiting_approval', null],
    succeeded: ['done', null], no_defects: ['done', '不具合なし'], failed: ['failed', null],
    cancelled: ['cancelled', null]
  };
  var WS_REASONS = {
    queued: '実行の受付が済みました。まもなく準備に入ります。',
    preparing: '作業用のコピーを用意しています。',
    verifying: '現在のテストを実行して、不具合があるかを実測しています。',
    analyzing: 'テストの失敗から、修正する欠陥を切り出しています。',
    fixing: 'エージェントが修正案を作っています。まだリポジトリには反映されていません。',
    reverifying: '修正後のテストを実行して、直ったかを実測しています。',
    awaiting_human: '修正案と再検証の結果が揃いました。内容を読んで、承認・却下などを判断してください。',
    succeeded: 'この実行は完了しています。',
    no_defects: 'テストに失敗がなく、直す対象がありませんでした。',
    failed: '実行が途中で失敗しました。既存のリポジトリは変更していません。下の「次にすること」を確認してください。',
    cancelled: 'この実行は中止されました。'
  };
  function hasWS() { return !!(window.WS2D && window.WS2D.status && window.WS2D.reason); }

  /* 外部のリポジトリに副作用がある操作（PR 作成・承認・再検証）の確認。
     WS2D.confirm が無いときは window.confirm にして、確認なしでは実行しない。 */
  function askConfirm(opts) {
    if (window.WS2D && typeof window.WS2D.confirm === 'function') {
      return window.WS2D.confirm(opts);
    }
    return Promise.resolve(window.confirm(opts.title + '\n' + opts.message));
  }

  function proposalCounts(run) {
    var c = { failed: 0, unresolved: 0 };
    ((run && run.iterations) || []).forEach(function (iter) {
      (iter.proposals || []).forEach(function (p) {
        if (p.status === 'failed' || p.status === 'timeout') { c.failed += 1; }
        else if (p.status === 'proposed') { c.unresolved += 1; }
      });
    });
    return c;
  }

  /* 承認の前に残っている問題。失敗・未解決・未確認の件数と、高リスクの兆候を判断ボタンの直下に出す。
     件数 0 のときも「0 件」と出す（出ない＝問題なし、と読ませない）。 */
  function renderBlockers(run) {
    var box = $['hl-blockers'];
    if (!box) { return; }
    box.textContent = '';
    var map = actionAvailability(run);
    if (!run || !(map['hl-approve'] || map['hl-create-pr'])) { box.hidden = true; return; }
    var pc = proposalCounts(run);
    var unverified = (run.unverified || []).length;
    var high = riskCounts().high;
    var parts = [
      ['失敗', pc.failed, pc.failed > 0 ? 'is-err' : ''],
      ['未解決', pc.unresolved, pc.unresolved > 0 ? 'is-warn' : ''],
      ['未確認', unverified, unverified > 0 ? 'is-warn' : ''],
      ['高リスクの兆候', high, high > 0 ? 'is-err' : '']
    ];
    box.appendChild(el('span', 'hl-blockers-lead', '承認の前に確認:'));
    parts.forEach(function (p) {
      box.appendChild(el('span', 'hl-blocker ' + p[2], p[0] + ' ' + p[1] + ' 件'));
    });
    var total = pc.failed + pc.unresolved + unverified + high;
    box.appendChild(el('span', 'hl-blockers-note', total > 0
      ? '残っているものを読んでから判断してください。'
      : '機械的に分かる残りはありません。テストの通過は正しさの保証ではありません。'));
    box.hidden = false;
  }

  /* 接続先・実行・PR・報告書を 1 行に。どの実行に対する判断かを承認ボタンの上で見失わせない。 */
  function renderRunContext(run) {
    var box = $['hl-run-context'];
    if (!box) { return; }
    box.textContent = '';
    if (!run) { box.hidden = true; return; }
    function item(label, nodeOrText) {
      var s = el('span', 'c-context__item');
      s.appendChild(document.createTextNode(label + ': '));
      var b = el('b');
      if (typeof nodeOrText === 'string') { b.textContent = nodeOrText; } else { b.appendChild(nodeOrText); }
      s.appendChild(b);
      box.appendChild(s);
    }
    item('接続先', (run.project_name || '—') + (run.branch ? '（' + run.branch + '）' : ''));
    item('実行', String(run.run_id || '').slice(0, 12) || '—');
    var pr = run.pull_request && run.pull_request.number ? run.pull_request : null;
    if (pr && pr.url) {
      var a = el('a', null, '#' + pr.number);
      a.href = pr.url; a.target = '_blank'; a.rel = 'noopener';
      item('PR', a);
    } else {
      item('PR', pr ? '#' + pr.number : '未作成');
    }
    /* 承認しても状態は「人の判断待ち」のまま（PR・マージは別操作）。最後の判断をここに出さないと、
       承認済みかどうかが画面から読めず二重に承認してしまう。承認は PR の作成・マージを意味しない。 */
    var decs = run.decisions || [];
    var last = decs.length ? decs[decs.length - 1] : null;
    if (last) {
      var lastLabel = { approve: '承認済み', reject: '却下済み', merge: 'マージ済み' }[last.action] || last.action;
      item('最後の判断', lastLabel + '（' + fmtTime(last.at) + (last.actor ? '・' + last.actor : '') + '）' +
        (last.action === 'approve' && !pr ? '・PR は未作成' : ''));
    } else {
      item('最後の判断', 'まだありません');
    }
    var rep = el('a', null, '報告書の一覧');
    rep.href = '/healing';
    item('判断の記録', rep);
    box.hidden = false;
  }

  function renderWsStatus(run) {
    var host = $['hl-ws-status'];
    var reasonHost = $['hl-run-reason'];
    if (!hasWS() || !host || !reasonHost) { return; }
    if (!run) {
      host.innerHTML = window.WS2D.status.html('not_started', '実行なし');
      reasonHost.textContent = '';
      return;
    }
    var m = WS_STATUS_MAP[run.status] || ['unverified', run.status || '状態不明'];
    host.innerHTML = window.WS2D.status.html(m[0], m[1] || undefined);
    var kind = run.status === 'failed' ? 'error'
      : (run.status === 'awaiting_human' ? 'warning'
        : (run.status === 'succeeded' || run.status === 'no_defects' ? 'success' : 'info'));
    var decList = run.decisions || [];
    var lastDec = decList.length ? decList[decList.length - 1] : null;
    var reasonText = WS_REASONS[run.status] || '状態の理由を取得できませんでした。';
    if (run.status === 'awaiting_human' && lastDec && lastDec.action === 'approve') {
      reasonText = '承認済みです。次は「PR を作成」です。PR を作るまで外部のリポジトリは変わりません。やり直すときは「再検証」か「却下」を選びます。';
    }
    window.WS2D.reason(reasonHost, reasonText, kind);
  }

  function renderStatusBadge(run) {
    var badge = $['hl-status'];
    setRunSectionVisible(!!run);
    badge.className = 'hl-badge';
    if (!run) {
      badge.textContent = '未選択';
      renderRunError(null);
      return;
    }
    badge.classList.add(statusBadgeClass(run.status));
    /* 高リスクが 1 件でもあるなら、状態が何であれ危険でない実行と同じ見た目にしない。
       状態で絞ると「人の判断待ち（上限到達）」のように status が別名の実行で付かない。 */
    if (riskCounts().high > 0) {
      badge.classList.add('hl-badge-attention');
    }
    var label = STATUS_LABELS[run.status] || run.status || '';
    var step = run.step_label || '';
    // step_label は状態名で始まることが多い（status=fixing / step_label="修正（1周目・1件）"）。
    // そのまま連結すると二重になるため、細かい方が状態名を含むならそちらだけを出す。
    if (step && step.indexOf(label) === 0) {
      badge.textContent = step;
    } else {
      badge.textContent = label + (step ? '（' + step + '）' : '');
    }
    renderRunError(run);
  }

  // エラー文は括弧の入れ子をほどき、内部用語を言い換え、次にとる行動を 1 行添える。
  // box を作り直すので重複は起きない。「次にすること」は消さない——
  // 何が起きたかだけ伝えて、どうすればよいかを伝えないのは不親切（2026-09-05）。
  function renderRunError(run) {
    var box = $['hl-run-error'];
    box.textContent = '';
    var raw = run && run.error ? String(run.error) : '';
    if (!raw) { box.hidden = true; return; }
    box.hidden = false;
    var flat = flattenParens(raw);
    var msg = el('div', 'hl-run-error-msg');
    msg.textContent = humanizeError(flat);
    box.appendChild(msg);
    var next = nextActionFor(flat);
    if (next) {
      box.appendChild(el('div', 'hl-run-error-next', '次にすること: ' + next));
    }
  }

  // 押せない操作は disabled で並べず、表示から外す（選べないものを見せない）。
  function actionAvailability(run) {
    var map = {
      'hl-create-pr': false, 'hl-rerun': false, 'hl-approve': false,
      'hl-merge': false, 'hl-reject': false, 'hl-cancel': false
    };
    if (!run) { return map; }
    var hasPr = !!(run.pull_request && run.pull_request.number);
    var isTerminal = TERMINAL_STATUSES.indexOf(run.status) !== -1;
    var isAwaiting = run.status === 'awaiting_human';
    if (!isTerminal && !isAwaiting) {
      map['hl-cancel'] = true;
      return map;
    }
    map['hl-rerun'] = true;
    // 不具合なし（直す対象が無い）の実行には PR にする変更が無い。押せると「何かを直した」ように見える。
    map['hl-create-pr'] = !hasPr && run.status !== 'no_defects' && !(run.status === 'failed' && !(run.fixed_count > 0));
    map['hl-merge'] = hasPr;
    if (isAwaiting) {
      map['hl-approve'] = true;
      map['hl-reject'] = true;
    }
    return map;
  }

  /* 判断ボタンが全部同じ見た目だと、何を選べばよいかが画面から読み取れない。
     並びは「承認 / PR を作成 / 再検証 | 却下」。破壊的な却下だけを間隔で離す。 */
  var TOOLBAR_ORDER = ['hl-approve', 'hl-create-pr', 'hl-rerun', 'hl-merge'];
  var toolbarLaidOut = false;

  function setBtnWeight(btn, primary) {
    if (!btn) { return; }
    btn.classList.remove('btn-primary');
    btn.classList.remove('btn-outline-sm');
    btn.classList.add(primary ? 'btn-primary' : 'btn-outline-sm');
  }

  /* 並べ替えは 1 度だけ。ポーリングのたびに DOM を動かすとフォーカスが飛ぶ。 */
  function layoutToolbar() {
    if (toolbarLaidOut) { return; }
    var reject = $['hl-reject'];
    var bar = reject && reject.parentNode ? reject.parentNode : null;
    if (!bar) { toolbarLaidOut = true; return; }
    TOOLBAR_ORDER.forEach(function (id) { if ($[id]) { bar.appendChild($[id]); } });
    var spacer = bar.querySelector('.hl-toolbar-spacer') || el('span', 'hl-toolbar-spacer');
    bar.appendChild(spacer);
    bar.appendChild(reject);
    if ($['hl-cancel']) { bar.appendChild($['hl-cancel']); }
    toolbarLaidOut = true;
  }

  function updateActionButtons(run) {
    var map = actionAvailability(run);
    Object.keys(map).forEach(function (id) {
      var btn = $[id];
      if (!btn) { return; }
      btn.disabled = false;
      btn.hidden = !map[id];
    });
    layoutToolbar();

    // 高リスクが残るなら「承認」を塗って誘導しない。押すこと自体は妨げない（判断は人がする）。
    var risky = riskCounts().high > 0;
    setBtnWeight($['hl-approve'], !risky);
    // PR 作成・再検証は主動線ではない。常に輪郭のままにする。
    setBtnWeight($['hl-create-pr'], false);
    setBtnWeight($['hl-rerun'], false);
    // 却下は取り消せない。塗らずに文字色だけで破壊的だと示す。
    if ($['hl-reject']) {
      setBtnWeight($['hl-reject'], false);
      $['hl-reject'].classList.add('hl-btn-danger');
    }

    if (!$['hl-cancel'] || $['hl-cancel'].hidden) { setConfirmOpen($['hl-cancel-confirm'], false); }
    if (!$['hl-merge'] || $['hl-merge'].hidden) { setConfirmOpen($['hl-merge-confirm'], false); }
    if (!$['hl-reject'] || $['hl-reject'].hidden) { setConfirmOpen($['hl-reject-confirm'], false); }
  }

  /* ---------------- ループ表示 ---------------- */

  function allProposalsFailed(proposals) {
    var list = proposals || [];
    if (!list.length) { return false; }
    return list.every(function (p) { return p.status === 'failed' || p.status === 'timeout'; });
  }

  // 再検証は「走ったか」と「通ったか」が別。error だけで見ると、
  // 失敗したままの再検証・打ち切られた実行まで緑（完了）になる。
  function verifyFailed(v) {
    if (!v) { return false; }
    if (v.ok === false) { return true; }
    return typeof v.failed === 'number' && v.failed > 0;
  }

  /* 「走らなかった」を「落ちた」と描かない。上限到達で再検証していない実行まで
     赤（失敗）にすると、直っていないのか実行していないのかが判別できなくなる。 */
  function verifyRan(v) {
    return !!v && !v.error;
  }

  // 済み / 実行中 / 未実行 / 失敗 の 4 状態を返す。同じ色で並べると
  // 「終わったもの」と「これから」の区別が付かない。
  function stepStates(iter, isActive) {
    function next(prev, value, failed) {
      if (prev !== 'done') { return 'idle'; }
      if (!value) { return isActive ? 'active' : 'idle'; }
      return failed ? 'failed' : 'done';
    }
    var s1;
    if (!iter.verify_before) { s1 = isActive ? 'active' : 'idle'; }
    else { s1 = iter.verify_before.error ? 'failed' : 'done'; }
    var s2 = next(s1, iter.defects, false);
    var s3 = next(s2, iter.proposals, allProposalsFailed(iter.proposals));
    var s4 = next(s3, verifyRan(iter.verify_after) ? iter.verify_after : null, verifyFailed(iter.verify_after));
    return [s1, s2, s3, s4];
  }

  function renderStepper(states) {
    var labels = ['検証', '欠陥', '修正', '再検証'];
    var wrap = el('div', 'hl-stepper');
    states.forEach(function (st, i) {
      var legacy = st === 'done' ? ' is-done' : (st === 'active' ? ' is-current' : '');
      var cls = 'hl-step hl-step-' + st + legacy;
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
      if (v.command) { wrap.title = v.command; }
      return wrap;
    }
    var summary = '失敗 ' + (v.failed != null ? v.failed : '?') + ' / 全 ' + (v.total != null ? v.total : '?');
    if (typeof v.duration_sec === 'number') { summary += '（' + v.duration_sec.toFixed(1) + ' 秒）'; }
    wrap.appendChild(el('b', null, summary));
    // 検証コマンドはメタ情報に既に出ている。同じ値を 2 箇所に出さず title に残す。
    if (v.command) { wrap.title = v.command; }
    return wrap;
  }

  /* pytest の終了コードのうち意味が確定しているものだけを 1 行にする。
     知らないコードに勝手な意味を付けると、事実でない説明が画面に出る。 */
  var VERIFY_EXIT_NOTES = {
    2: 'テストを収集できませんでした（終了コード 2）。テストの読み込み自体が失敗しています。',
    5: '実行できるテストが 1 件もありませんでした（終了コード 5）。'
  };

  /* 収集できたテストの件数が前後で変われば、それ自体が異常の兆候。
     数字を並べるだけでは見落とされるので、文で出す。 */
  function totalShiftNote(before, after) {
    if (!before || !after) { return ''; }
    if (typeof before.total !== 'number' || typeof after.total !== 'number') { return ''; }
    if (before.total === after.total) { return ''; }
    var head = '収集できたテストが ' + before.total + ' 件 → ' + after.total + ' 件に';
    if (after.total < before.total) {
      return head + '減っています。テストが壊れている可能性があります。';
    }
    return head + '増えています。検証の対象が変わっている可能性があります。';
  }

  /* 再検証は「直ったのか」を利用者が知る唯一の場所。未実行・失敗・件数の変化を
     すべてここに出す。出さないと、修正を当てただけで直ったと読まれる。 */
  function renderReverifyResult(iter) {
    var wrap = el('div', 'hl-verify-after');
    var v = iter.verify_after;
    if (!v) {
      wrap.appendChild(el('div', 'hl-verify-result hl-muted', '再検証: 未実行'));
      return wrap;
    }
    if (v.error) {
      wrap.appendChild(renderVerifyResult(v));
      return wrap;
    }
    var failed = typeof v.failed === 'number' ? v.failed : null;
    var summary = '再検証: 失敗 ' + (failed != null ? failed : '?')
      + ' / 全 ' + (v.total != null ? v.total : '?');
    if (typeof v.duration_sec === 'number') { summary += '（' + v.duration_sec.toFixed(1) + ' 秒）'; }
    var passed = failed === 0 && v.ok !== false;
    var line = el('div', 'hl-verify-result');
    var badge = el('b', passed ? 'hl-verify-ok hl-badge-ok' : 'hl-verify-bad hl-badge-err', summary);
    if (v.command) { badge.title = v.command; }
    line.appendChild(badge);
    wrap.appendChild(line);
    var shift = totalShiftNote(iter.verify_before, v);
    if (shift) { wrap.appendChild(el('div', 'hl-verify-warn hl-note', shift)); }
    var note = VERIFY_EXIT_NOTES[v.exit_code];
    if (typeof note === 'string') { wrap.appendChild(el('div', 'hl-verify-note hl-muted', note)); }
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
    wrap.appendChild(el('div', 'hl-evidence-title', '該当箇所の根拠'));
    var list = (locations || []).slice();
    if (list.length === 0) {
      wrap.appendChild(el('p', 'hl-evidence-empty', '根拠を特定できませんでした。'));
      return wrap;
    }
    list.sort(function (a, b) { return (b.score || 0) - (a.score || 0); });
    // 入れ子テーブルは外側の表と列が揃わず破綻する。行の並び（定義リスト形式）にする。
    var strengthTip = '複数の根拠を重ねたスコア。100% が最も強い';
    var listEl = el('div', 'hl-evidence-list');
    // 1 件 = 3 カラム（ファイル / 根拠 / 確度）。列の割り付けは CSS 側が持つ。
    var head = el('div', 'hl-evidence-item hl-evidence-head');
    head.appendChild(el('span', 'hl-evidence-path', 'ファイル'));
    head.appendChild(el('span', 'hl-evidence-why', '根拠'));
    var headScore = el('span', 'hl-evidence-score', 'この根拠の強さ');
    headScore.title = strengthTip;
    head.appendChild(headScore);
    listEl.appendChild(head);
    list.forEach(function (loc) {
      var path = loc.path || '';
      var row = el('div', 'hl-evidence-item');
      var file = setTail(el('span', 'hl-evidence-path'), path, 46);
      if (loc.detail) { file.title = path + ' — ' + loc.detail; }
      row.appendChild(file);
      var badge = el('span', 'hl-evidence-why', REASON_LABELS[loc.reason] || loc.reason || '不明');
      if (loc.detail) { badge.title = loc.detail; }
      row.appendChild(badge);
      // score は 0〜1 で来る想定だが、0〜100 で来ても壊さない。
      var pct = null;
      if (typeof loc.score === 'number' && isFinite(loc.score)) {
        pct = loc.score <= 1 ? Math.round(loc.score * 100) : Math.round(loc.score);
        pct = Math.max(0, Math.min(100, pct));
      }
      var strength = el('span', 'hl-evidence-score');
      strength.title = strengthTip;
      var bar = el('span', 'hl-evidence-bar');
      var fill = el('span', 'hl-evidence-bar-fill');
      fill.style.width = (pct === null ? 0 : pct) + '%';
      bar.appendChild(fill);
      strength.appendChild(bar);
      strength.appendChild(el('span', 'hl-evidence-pct num', pct === null ? '—' : pct + '%'));
      row.appendChild(strength);
      listEl.appendChild(row);
    });
    wrap.appendChild(listEl);
    return wrap;
  }

  /* 確認が必要な点。risks が空でも黙らない（「兆候が無い＝正しい」ではないため）。 */
  function renderRisks(risks) {
    var wrap = el('div', 'hl-risk');
    wrap.appendChild(el('div', 'hl-subhead', '確認が必要な点'));
    var list = (risks || []).slice();
    if (list.length === 0) {
      wrap.appendChild(el('p', 'hl-risk-none',
        '機械的に検出できる兆候はありませんでした。テストの通過は正しさを保証しません。差分を確認してください。'));
      return wrap;
    }
    list.sort(function (a, b) { return severityRank(a.severity) - severityRank(b.severity); });
    var ul = el('ul', 'hl-risk-list');
    list.forEach(function (r) {
      var sev = r.severity || 'low';
      // 1 件 = バッジ・ラベル・詳細の 3 要素。入れ子の行ラッパは置かない。
      var li = el('li', 'hl-risk-item is-' + sev);
      li.appendChild(el('span', 'hl-risk-badge is-' + sev, SEVERITY_LABELS[sev] || sev));
      li.appendChild(el('span', 'hl-risk-label', r.label || r.code || ''));
      if (r.detail) { li.appendChild(el('div', 'hl-risk-detail', r.detail)); }
      ul.appendChild(li);
    });
    wrap.appendChild(ul);
    return wrap;
  }

  function pillEl(status) {
    var kind = PROPOSAL_STATUS_KIND[status] || 'mute';
    var pill = el('span', 'hl-pill hl-badge-' + kind + ' ' + (status || ''),
      PROPOSAL_STATUS_LABELS[status] || status || '不明');
    if (PROPOSAL_STATUS_TITLES[status]) { pill.title = PROPOSAL_STATUS_TITLES[status]; }
    return pill;
  }

  function renderProposalsTable(proposals) {
    if (!proposals || proposals.length === 0) {
      // 修正が無くても「確認が必要な点」は必ず出す（沈黙を「問題なし」と読ませない）。
      var empty = el('div', 'hl-proposals-empty');
      empty.appendChild(el('p', 'hl-hint', '修正はまだありません。'));
      empty.appendChild(renderRisks(null));
      return empty;
    }
    // 列幅は CSS で決める（「差分を見る」が 3 行に折れないだけの幅が要る）。
    var table = el('table', 'data dashboard-table hl-proposals-table');
    var thead = el('thead');
    var trh = el('tr');
    ['実行者', '状態', '何をどう直したか', '変更ファイル', '詳細'].forEach(function (t) { trh.appendChild(el('th', 'hl-th-nowrap', t)); });
    thead.appendChild(trh);
    table.appendChild(thead);
    var tbody = el('tbody');
    proposals.forEach(function (p) {
      var tr = el('tr');
      var tdAgent = el('td', null, agentDisplayName(p.agent) || '');
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

      var files = p.files_changed || [];
      var tdFiles = el('td', 'num');
      if (files.length === 1) {
        tdFiles.className = 'hl-kv';
        setTail(tdFiles, files[0], 28);
      } else {
        tdFiles.textContent = String(files.length);
        tdFiles.title = files.join('\n');
      }
      tr.appendChild(tdFiles);

      // 差分もバグレポートも同じ詳細行に入れる。行内の入口はトグル 1 つだけ。
      var tdDetail = el('td');
      tr.appendChild(tdDetail);
      tbody.appendChild(tr);

      var detailTr = el('tr', 'hl-detail-row');
      detailTr.hidden = true;
      var detailTd = el('td');
      detailTd.colSpan = 5;
      // 確認が必要な点は常に出す（空でも「兆候が無かった」と書く）。
      detailTd.appendChild(renderRisks(p.risks));
      if (p.diff) {
        detailTd.appendChild(el('div', 'hl-subhead', '差分'));
        detailTd.appendChild(buildDiffElement(p.diff));
      }
      if (p.report_md) {
        detailTd.appendChild(el('div', 'hl-subhead', 'バグレポート'));
        detailTd.appendChild(renderMarkdown(p.report_md));
      }
      detailTr.appendChild(detailTd);
      tbody.appendChild(detailTr);

      var toggle = el('button', 'btn-outline-sm hl-btn-ghost', '詳細を見る');
      toggle.type = 'button';
      toggle.setAttribute('data-testid', 'hl-toggle-detail');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.addEventListener('click', function () {
        detailTr.hidden = !detailTr.hidden;
        toggle.setAttribute('aria-expanded', detailTr.hidden ? 'false' : 'true');
        toggle.textContent = detailTr.hidden ? '詳細を見る' : '詳細を閉じる';
      });
      tdDetail.appendChild(toggle);
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
      // 再検証は「無い」ことも情報。ブロックごと消すと、直ったのか実行していないのかが分からない。
      block.appendChild(el('h4', 'hl-sub', '再検証結果'));
      block.appendChild(renderReverifyResult(iter));
      loopEl.appendChild(block);
    });
  }

  var LOG_TS_RE = /^\[(\d{2}):(\d{2}):(\d{2})\]\s?/;

  /* 時刻だけでは前後関係が読めないので、最初の行からの経過秒を並記する。 */
  function renderLogLines(lines, errorText) {
    var logEl = $['hl-log'];
    logEl.textContent = '';
    var list = lines || [];
    if (!list.length && !errorText) {
      // 空の黒い箱だけを置くと「壊れている」ように見える。何が入る場所かを書く。
      logEl.appendChild(el('div', 'hl-log-placeholder', 'ヒーリングを開始すると、ここに進行が 1 行ずつ出ます。'));
      return;
    }
    var base = null;
    list.forEach(function (line) {
      var raw = String(line);
      var m = LOG_TS_RE.exec(raw);
      var text = raw;
      if (m) {
        var sec = (Number(m[1]) * 3600) + (Number(m[2]) * 60) + Number(m[3]);
        if (base === null) { base = sec; }
        var diff = sec - base;
        if (diff < 0) { diff += 86400; }
        text = '[' + m[1] + ':' + m[2] + ':' + m[3] + ' +' + diff.toFixed(1) + 's] ' + raw.slice(m[0].length);
      }
      logEl.appendChild(el('div', 'hl-log-line', text));
    });
    // 失敗の理由はバナーだけでなくログの末尾にも残す（後から読み返す先はログのため）。
    if (errorText) {
      logEl.appendChild(el('div', 'hl-log-line hl-log-error', '失敗の理由: ' + humanizeError(flattenParens(errorText))));
    }
    logEl.scrollTop = logEl.scrollHeight;
  }

  /* ---- 他ファイルへ公開 ---- */
  HL.askConfirm = askConfirm;
  HL.clearRunView = clearRunView;
  HL.fetchAndRenderRun = fetchAndRenderRun;
  HL.hasWS = hasWS;
  HL.openRun = openRun;
  HL.renderEvidence = renderEvidence;
  HL.riskCounts = riskCounts;
  HL.selectProject = selectProject;
  HL.startRun = startRun;
})(window.HealingApp = window.HealingApp || {});
