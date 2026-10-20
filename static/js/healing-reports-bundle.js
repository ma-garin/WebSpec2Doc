/* オートヒーリングの報告書（templates/healing_reports.html・healing_report.html）: 束の本文: 個票の表・まとめての承認／差し戻し／却下（確認を経由）
   読み込み順: healing-reports-core.js → healing-reports-list.js → healing-reports-doc.js → healing-reports-bundle.js → healing-reports.js。
   ファイル間の共有は window.HealingReports（HL）だけ。他ファイルの関数は呼び出し時に HL から引く。 */
(function (HL) {
  'use strict';

  /* ---- 他ファイルの宣言 ---- */
  var IS_ADMIN = HL.IS_ADMIN;
  var STATUS_LABELS = HL.STATUS_LABELS;
  var WS_REPORT_STATUS = HL.WS_REPORT_STATUS;
  function api() { return HL.api.apply(this, arguments); }
  function askConfirm() { return HL.askConfirm.apply(this, arguments); }
  function blockersBox() { return HL.blockersBox.apply(this, arguments); }
  function clearError() { return HL.clearError.apply(this, arguments); }
  function el() { return HL.el.apply(this, arguments); }
  function renderContext() { return HL.renderContext.apply(this, arguments); }
  function renderHead() { return HL.renderHead.apply(this, arguments); }
  function renderReportTable() { return HL.renderReportTable.apply(this, arguments); }
  function section() { return HL.section.apply(this, arguments); }
  function showError() { return HL.showError.apply(this, arguments); }
  function showState() { return HL.showState.apply(this, arguments); }
  var state = HL.state;
  function toast() { return HL.toast.apply(this, arguments); }


  /* ---------------- 束の本文 ---------------- */

  function renderBundleDoc(data) {
    var bundle = data.bundle;
    var reports = data.reports || [];
    var doc = document.getElementById('hl-doc');
    doc.textContent = '';
    doc.setAttribute('aria-busy', 'false');

    doc.appendChild(el('h1', 'hl-doc-title', bundle.title || '（画面不明）'));
    if (bundle.review_reason) { doc.appendChild(el('p', 'hl-doc-note', bundle.review_reason)); }
    var meta = el('p', 'hl-doc-meta');
    [
      '案件: ' + (bundle.project_name || '—'),
      bundle.target_url ? '対象: ' + bundle.target_url : '',
      '件数: ' + bundle.count + ' 件'
    ].filter(Boolean).forEach(function (t) { meta.appendChild(el('span', null, t)); });
    meta.appendChild(el('span', 'hl-badge is-ac', STATUS_LABELS[bundle.status] || bundle.status));
    doc.appendChild(meta);

    doc.appendChild(section('個票 ' + reports.length + ' 件（うち承認待ち ' + bundle.awaiting_count + '）'));
    doc.appendChild(renderReportTable(reports));

    var bstatus = bundle.awaiting_count > 0 ? ['waiting_approval', null]
      : (WS_REPORT_STATUS[bundle.status] || ['unverified', bundle.status || '状態不明']);
    renderHead({
      title: '束：' + (bundle.title || '（画面不明）'),
      desc: '同じ画面 × 観点の個票をまとめて読み、まとめて判断します。',
      statusCode: bstatus[0], statusLabel: bstatus[1],
      reason: bundle.awaiting_count > 0
        ? '承認待ちの個票が ' + bundle.awaiting_count + ' 件あります。個票を読んでから、まとめて判断してください。'
        : (bundle.review_reason || 'この束に承認待ちの個票はありません。'),
      reasonKind: bundle.awaiting_count > 0 ? 'warning' : 'info'
    });
    renderContext([
      { label: '案件', value: bundle.project_name },
      { label: '対象', value: bundle.target_url },
      { label: '件数', value: bundle.count + ' 件（承認待ち ' + (bundle.awaiting_count || 0) + '）' }
    ]);
    renderBundleActions(bundle);
  }

  function renderBundleActions(bundle) {
    var box = document.getElementById('hl-doc-actions');
    if (!box) { return; }
    box.textContent = '';
    var canDecide = IS_ADMIN && bundle.awaiting_count > 0;
    box.hidden = false;

    if (canDecide) {
      var note = el('textarea', 'hl-field');
      note.id = 'hl-bundle-note';
      note.rows = 3;
      note.placeholder = '承認のメモ（束の中の承認待ち個票すべてに残ります）';
      note.setAttribute('aria-label', '承認のメモ');
      box.appendChild(note);

      var fixTargets = bundle.fix_targets || [];
      // 送る修正（差分）が無い束は、テストだけの修正と同じく「承認」だけにする（PR は作られない）
      var scriptOnly = (fixTargets.length > 0 && fixTargets.every(function (t) { return t === 'script'; })) || bundle.has_diff === false;
      var approveLabel = scriptOnly ? '承認' : '承認して修正を送る';
      var bUnverified = Math.max(0, (bundle.count || 0) - (bundle.verify_after_ok_count || 0));
      var bTotal = (bundle.attention_high || 0) + bUnverified;
      box.appendChild(blockersBox([
        { n: bUnverified, label: '検証が通っていない個票（失敗・未確認を含む）', kind: 'is-err' },
        { n: bundle.attention_high || 0, label: '重大な確認事項', kind: 'is-err' }
      ], bTotal > 0 ? '残っているものを個票で読んでから判断してください。' : '機械的に分かる残りはありません。テストの通過は正しさの保証ではありません。'));
      var approve = el('button', 'hl-btn' + (bundle.attention_high > 0 ? '' : ' is-primary'), approveLabel);
      approve.type = 'button';
      approve.addEventListener('click', function () {
        askConfirm({
          title: 'この束の承認待ち ' + (bundle.awaiting_count || 0) + ' 件をまとめて承認しますか？',
          message: scriptOnly
            ? '承認は個票ごとに記録され、以後は書き直せません。' + (bundle.has_diff === false ? '送る修正（差分）が無いため、PR は作られません。' : 'サイトのコードは変更しません。')
            : '承認すると、修正が接続先の GitHub リポジトリへ PR として送られます。外部のリポジトリに記録が残り、承認は取り消せません（PR は後から閉じられます）。',
          detail: '案件: ' + (bundle.project_name || '—'),
          confirmLabel: scriptOnly ? 'まとめて承認する' : 'まとめて承認して PR を送る'
        }).then(function (ok) { if (ok) { decideBundle('approve', note.value, approve); } });
      });
      box.appendChild(approve);
      if (!scriptOnly) {
        box.appendChild(el('p', 'hl-doc-note', '開発者には PR として届きます'));
      }

      var back = el('button', 'hl-btn', '差し戻す');
      back.type = 'button';
      back.addEventListener('click', function () {
        if (!note.value.trim()) {
          showError('差し戻すときは、どう直してほしいかをメモに書いてください。');
          note.focus();
          return;
        }
        decideBundle('return', note.value, back);
      });
      box.appendChild(back);

      var reject = el('button', 'hl-btn is-danger', '却下');
      reject.type = 'button';
      var confirm = el('div', 'hl-confirm');
      confirm.hidden = true;
      confirm.setAttribute('inert', '');
      confirm.appendChild(el('span', null, '束の中の承認待ち個票をすべて却下しますか？'));
      var yes = el('button', 'hl-btn hl-btn-sm is-danger', '却下する');
      yes.type = 'button';
      yes.addEventListener('click', function () { decideBundle('reject', note.value, yes); });
      var no = el('button', 'hl-btn hl-btn-sm', 'やめる');
      no.type = 'button';
      // 確認は開いたら「やめる」へフォーカスを移し（誤って却下しない側）、Esc・やめるで閉じて「却下」へ戻す
      var closeConfirm = function () { confirm.hidden = true; confirm.setAttribute('inert', ''); reject.focus(); };
      no.addEventListener('click', closeConfirm);
      confirm.setAttribute('role', 'group');
      confirm.setAttribute('aria-label', '却下の確認');
      confirm.addEventListener('keydown', function (ev) {
        if (ev.key === 'Escape' || ev.key === 'Esc') { ev.preventDefault(); ev.stopPropagation(); closeConfirm(); }
      });
      confirm.appendChild(yes); confirm.appendChild(no);
      reject.addEventListener('click', function () { confirm.hidden = false; confirm.removeAttribute('inert'); no.focus(); });
      box.appendChild(reject);
      box.appendChild(confirm);

      if (bundle.attention_high > 0) {
        box.appendChild(el('p', 'hl-doc-note', '確認が必要な点が残っているため、承認は強調していません。'));
      }
    } else if (!IS_ADMIN) {
      box.appendChild(el('p', 'hl-doc-note', '判断するには管理者権限が必要です。'));
    } else {
      box.appendChild(el('p', 'hl-doc-note', 'この束に承認待ちの個票はありません。'));
    }
  }

  function decideBundle(action, note, button) {
    clearError();
    if (button) { button.disabled = true; }
    api('/api/healing/bundles/' + encodeURIComponent(state.bundleId) + '/decision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action, note: note || '', actor: '' })
    }).then(function (data) {
      var n = data.decided || 0;
      var msg = action === 'approve'
        ? (data.pr_number ? '承認しました（' + n + ' 件）。PR #' + data.pr_number + ' を作成しました'
                          : '承認しました（' + n + ' 件）')
        : action === 'return' ? '差し戻しました（' + n + ' 件）。修正をやり直します'
                               : '却下しました（' + n + ' 件）';
      toast(msg);
      setTimeout(function () { window.location.href = '/healing'; }, 2000);
    }).catch(function (e) {
      if (button) { button.disabled = false; }
      showError(e.message);
    });
  }

  function loadBundleDoc() {
    api('/api/healing/bundles/' + encodeURIComponent(state.bundleId))
      .then(renderBundleDoc)
      .catch(function (e) {
        var doc = document.getElementById('hl-doc');
        if (doc) {
          doc.setAttribute('aria-busy', 'false');
          showState(doc, {
            kind: 'error', title: '束を読み込めませんでした', message: e.message,
            next: '一覧に戻って開き直すか、通信を確認してください。',
            actionLabel: '再読み込み', onAction: loadBundleDoc
          }, '束を読み込めませんでした。');
        }
        showError(e.message);
      });
  }

  /* ---- 他ファイルへ公開 ---- */
  HL.loadBundleDoc = loadBundleDoc;
})(window.HealingReports = window.HealingReports || {});
