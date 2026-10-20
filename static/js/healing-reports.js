/* 報告書の一覧と本文。
 *
 * healing.js とはヘルパーを共有しない。あちらは IIFE の中に閉じていて
 * window に何も出していないため、外から呼べない。ここでは必要な分だけ
 * 作り直している（重複より、片方を直したときにもう片方が壊れる方が高くつく）。
 *
 * innerHTML は使わない。値は必ず textContent で入れる。
 *
 * 一覧の既定表示は束（画面 × 観点）。個票（1 欠陥 = 1 報告書）は束の行を
 * 開いたときに現れる折りたたみと、束の本文ページの表にだけ出る。
 */
/* オートヒーリングの報告書（templates/healing_reports.html・healing_report.html）: 入口: どのページかを見て初期化する（最後に読む）
   読み込み順: healing-reports-core.js → healing-reports-list.js → healing-reports-doc.js → healing-reports-bundle.js → healing-reports.js。
   ファイル間の共有は window.HealingReports（HL）だけ。他ファイルの関数は呼び出し時に HL から引く。 */
(function (HL) {
  'use strict';

  /* ---- 他ファイルの宣言 ---- */
  function applySite() { return HL.applySite.apply(this, arguments); }
  function loadBundleDoc() { return HL.loadBundleDoc.apply(this, arguments); }
  function loadBundleList() { return HL.loadBundleList.apply(this, arguments); }
  function loadCount() { return HL.loadCount.apply(this, arguments); }
  function loadDoc() { return HL.loadDoc.apply(this, arguments); }
  function loadProjects() { return HL.loadProjects.apply(this, arguments); }
  function on() { return HL.on.apply(this, arguments); }
  function siteParam() { return HL.siteParam.apply(this, arguments); }
  var state = HL.state;


  function init() {
    var bundleId = document.body.getAttribute('data-bundle-id');
    if (bundleId) {
      state.bundleId = bundleId;
      loadCount();
      loadBundleDoc();
      return;
    }
    var reportId = document.body.getAttribute('data-report-id');
    if (reportId) {
      state.reportId = reportId;
      loadCount();
      loadDoc();
      return;
    }
    if (!document.getElementById('hl-reports-table')) { return; }
    on('hl-project-filter', 'change', function (ev) {
      state.projectId = ev.target.value || '';
      loadBundleList();
    });
    var site = siteParam();
    if (site) {
      loadProjects().then(function (projects) { applySite(site, projects); loadBundleList(); });
    } else {
      loadProjects();
      loadBundleList();
    }
    loadCount();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window.HealingReports = window.HealingReports || {});
