'use strict';

/* オートヒーリング設定画面（templates/healing.html）: 入口: 初期化とイベントの結び付け（最後に読む）
   読み込み順: healing-core.js → healing-projects.js → healing-report.js → healing-run.js → healing-actions.js → healing-history.js → healing.js。
   ファイル間の共有は window.HealingApp（HL）だけ。他ファイルの関数は呼び出し時に HL から引く。 */
(function (HL) {
  /* ---- 他ファイルの宣言 ---- */
  var $ = HL.$;
  var VIEW_NAMES = HL.VIEW_NAMES;
  function apiFetch() { return HL.apiFetch.apply(this, arguments); }
  function asObj() { return HL.asObj.apply(this, arguments); }
  function cacheDom() { return HL.cacheDom.apply(this, arguments); }
  function cancelRun() { return HL.cancelRun.apply(this, arguments); }
  function clearRunView() { return HL.clearRunView.apply(this, arguments); }
  function closeRowMenu() { return HL.closeRowMenu.apply(this, arguments); }
  function closeRowMenuOnOutsideClick() { return HL.closeRowMenuOnOutsideClick.apply(this, arguments); }
  function createPullRequest() { return HL.createPullRequest.apply(this, arguments); }
  function hideConnectForm() { return HL.hideConnectForm.apply(this, arguments); }
  function loadAgentOptions() { return HL.loadAgentOptions.apply(this, arguments); }
  function loadHistory() { return HL.loadHistory.apply(this, arguments); }
  function loadProjects() { return HL.loadProjects.apply(this, arguments); }
  function loadStats() { return HL.loadStats.apply(this, arguments); }
  function on() { return HL.on.apply(this, arguments); }
  function openConfirm() { return HL.openConfirm.apply(this, arguments); }
  function openRun() { return HL.openRun.apply(this, arguments); }
  function parseHash() { return HL.parseHash.apply(this, arguments); }
  function runCheck() { return HL.runCheck.apply(this, arguments); }
  function selectProject() { return HL.selectProject.apply(this, arguments); }
  function selectedProjectName() { return HL.selectedProjectName.apply(this, arguments); }
  function setAdminFlag() { return HL.setAdminFlag.apply(this, arguments); }
  function setConfirmOpen() { return HL.setConfirmOpen.apply(this, arguments); }
  function showConnectForm() { return HL.showConnectForm.apply(this, arguments); }
  function startRun() { return HL.startRun.apply(this, arguments); }
  var state = HL.state;
  function submitConnectForm() { return HL.submitConnectForm.apply(this, arguments); }
  function submitDecision() { return HL.submitDecision.apply(this, arguments); }
  function switchView() { return HL.switchView.apply(this, arguments); }
  function watchTableLabels() { return HL.watchTableLabels.apply(this, arguments); }


  function init() {
    cacheDom();
    watchTableLabels($['hl-projects']);
    watchTableLabels($['hl-runs']);
    state.focusRunId = document.body.getAttribute('data-focus-run-id') || '';
    setAdminFlag(document.body.getAttribute('data-hl-admin') === 'true');

    on('hl-nav-run', 'click', function () { switchView('run'); });
    on('hl-nav-projects', 'click', function () { switchView('projects'); });
    on('hl-nav-history', 'click', function () { switchView('history'); });
    // 実行ビューから接続先の一覧へ戻る導線。サイドバーに切替が無いので、
    // これが無いと「対象にする」で実行へ移った後、登録フォームへ戻れない。
    on('hl-back-to-projects', 'click', function () { switchView('projects'); });
    // 接続先ビューの右上が正規の入口。空状態にも同じ入口を置く。
    var addOnList = document.getElementById('hl-add-project-2');
    if (addOnList) { addOnList.addEventListener('click', function () { showConnectForm(null); }); }
    // #hl-add-project-2 / #hl-projects-empty-add は Jinja 側（hl_admin）が出し分ける。
    // ここで IS_ADMIN を再判定すると二重管理になるため、存在確認だけで結び付ける。
    var addOnEmpty = document.getElementById('hl-projects-empty-add');
    if (addOnEmpty) { addOnEmpty.addEventListener('click', function () { showConnectForm(null); }); }

    document.addEventListener('click', closeRowMenuOnOutsideClick);
    // body 直下・position: fixed で開くため、スクロールやリサイズで座標がずれる。追従させず閉じる。
    window.addEventListener('scroll', function () { closeRowMenu(); }, true);
    window.addEventListener('resize', function () { closeRowMenu(); });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' || ev.key === 'Esc') { closeRowMenu(); }
    });

    on('hl-project-select', 'change', function () { selectProject(this.value); });

    on('hl-connect-submit', 'click', submitConnectForm);
    on('hl-connect-cancel', 'click', hideConnectForm);

    on('hl-check-btn', 'click', runCheck);

    on('hl-start', 'click', function () {
      var target = document.getElementById('hl-confirm-target');
      if (target) { target.textContent = selectedProjectName(); }
      openConfirm($['hl-start-confirm']);
    });
    on('hl-start-yes', 'click', function () { setConfirmOpen($['hl-start-confirm'], false); startRun(); });
    on('hl-start-no', 'click', function () { setConfirmOpen($['hl-start-confirm'], false); });

    on('hl-cancel', 'click', function () { openConfirm($['hl-cancel-confirm']); });
    on('hl-cancel-yes', 'click', function () { setConfirmOpen($['hl-cancel-confirm'], false); cancelRun(); });
    on('hl-cancel-no', 'click', function () { setConfirmOpen($['hl-cancel-confirm'], false); });

    on('hl-merge', 'click', function () { openConfirm($['hl-merge-confirm']); });
    on('hl-merge-yes', 'click', function () { setConfirmOpen($['hl-merge-confirm'], false); submitDecision('merge'); });
    on('hl-merge-no', 'click', function () { setConfirmOpen($['hl-merge-confirm'], false); });

    on('hl-reject', 'click', function () { openConfirm($['hl-reject-confirm']); });
    on('hl-reject-yes', 'click', function () { setConfirmOpen($['hl-reject-confirm'], false); submitDecision('reject'); });
    on('hl-reject-no', 'click', function () { setConfirmOpen($['hl-reject-confirm'], false); });

    on('hl-approve', 'click', function () { submitDecision('approve'); });
    on('hl-create-pr', 'click', createPullRequest);
    on('hl-rerun', 'click', function () { submitDecision('rerun'); });

    on('hl-runs-more', 'click', function () {
      loadHistory((state.historyLimit || 20) + 20);
    });

    loadAgentOptions();
    // 起動時にどのビューを開くかはサーバが決める（body の data-default-view）。
    // 設定画面は接続先の一覧、実行の直リンクは実行ビュー。属性が無い / 未知の値なら
    // 従来どおり実行ビューにする。
    var defaultView = (document.body.dataset && document.body.dataset.defaultView) || '';
    // URL ハッシュ（リロード・ブックマーク・戻る）を優先。無い・不正なら従来の既定画面
    var h = parseHash();
    if (h) {
      defaultView = h.view;
      if (h.runId && !state.focusRunId) { state.focusRunId = h.runId; }
    }
    switchView(VIEW_NAMES.indexOf(defaultView) >= 0 ? defaultView : 'run', { replace: true });
    window.addEventListener('popstate', function () {
      var p = parseHash();
      var v = p ? p.view : 'run';
      switchView(v, { noUrl: true });
      if (p && p.view === 'run' && p.runId && p.runId !== state.selectedRunId) { openRun(p.runId); }
    });

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
})(window.HealingApp = window.HealingApp || {});
