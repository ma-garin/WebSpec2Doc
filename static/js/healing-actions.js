'use strict';

/* オートヒーリング設定画面（templates/healing.html）: 承認操作: PR 作成・中止・承認／差し戻し／却下（すべて確認を経由）・未確認の表示
   読み込み順: healing-core.js → healing-projects.js → healing-report.js → healing-run.js → healing-actions.js → healing-history.js → healing.js。
   ファイル間の共有は window.HealingApp（HL）だけ。他ファイルの関数は呼び出し時に HL から引く。 */
(function (HL) {
  /* ---- 他ファイルの宣言 ---- */
  var $ = HL.$;
  function apiFetch() { return HL.apiFetch.apply(this, arguments); }
  function askConfirm() { return HL.askConfirm.apply(this, arguments); }
  function clearError() { return HL.clearError.apply(this, arguments); }
  function el() { return HL.el.apply(this, arguments); }
  function fetchAndRenderRun() { return HL.fetchAndRenderRun.apply(this, arguments); }
  function flattenParens() { return HL.flattenParens.apply(this, arguments); }
  function fmtTime() { return HL.fmtTime.apply(this, arguments); }
  function getProject() { return HL.getProject.apply(this, arguments); }
  function humanizeError() { return HL.humanizeError.apply(this, arguments); }
  function showError() { return HL.showError.apply(this, arguments); }
  var state = HL.state;


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
    var p = getProject(state.selectedProjectId);
    askConfirm({
      title: 'PR を作成しますか？',
      message: '修正したブランチを接続先のリモートリポジトリへ push し、GitHub に PR を作成します。外部のリポジトリに記録が残り、push は取り消せません（PR は後から閉じられます）。',
      detail: p ? '接続先: ' + (p.name || '') : '',
      confirmLabel: 'push して PR を作成する'
    }).then(function (ok) { if (ok) { doCreatePullRequest(); } });
  }

  function doCreatePullRequest() {
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

  /* 承認・再検証は記録（監査ログ）と、再検証ではテスト実行を伴う。確認してから実行する。
     却下・マージは従来のインライン確認行が別にある。 */
  var DECISION_CONFIRM = {
    approve: {
      title: 'この実行を承認しますか？',
      message: '承認は判断として記録されます。承認しても PR はマージされません。マージは別の操作で、取り消せません。',
      confirmLabel: '承認する'
    },
    rerun: {
      title: '再検証を実行しますか？',
      message: 'この実行の作業用コピーで、検証コマンドをもう一度実行します。結果が出るまで他の操作は待ってください。',
      confirmLabel: '再検証する'
    }
  };

  function submitDecision(action) {
    if (!state.selectedRunId) { return; }
    var c = DECISION_CONFIRM[action];
    if (!c) { doSubmitDecision(action); return; }
    askConfirm(c).then(function (ok) { if (ok) { doSubmitDecision(action); } });
  }

  function doSubmitDecision(action) {
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
      // 過去の実行データには内部用語のままの文言が残っている。表示側でも言い換える。
      $['hl-unverified-list'].appendChild(
        el('li', null, humanizeError(flattenParens(String(item))))
      );
    });
  }

  /* ---- 他ファイルへ公開 ---- */
  HL.cancelRun = cancelRun;
  HL.createPullRequest = createPullRequest;
  HL.renderPrInfo = renderPrInfo;
  HL.renderUnverified = renderUnverified;
  HL.submitDecision = submitDecision;
})(window.HealingApp = window.HealingApp || {});
