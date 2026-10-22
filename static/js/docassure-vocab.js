/* Document Assurance: 状態語と指標の正本（Vocabulary / Metric Dictionary）。画面はここだけから語と定義を引く。
   決定: 判断対象=判断待ち／判断済み、要件=判断待ちあり／判断済み／指摘なし／未評価、データ無し=未評価、統合先なし=未取り込み、
   バックエンドが返さない値=未提供。指摘なし≠問題なし。件数の唯一の元は buildModel() の open。 */
(function () {
  'use strict';
  var W = {
    open: '判断待ち', done: '判断済み', all: 'すべて',
    reqOpen: '判断待ちあり', reqDone: '判断済み', reqNone: '指摘なし', unknown: '未評価',
    notImported: '未取り込み', notProvided: '未提供', unavailable: '利用できません',
    accepted: '認めた', rejected: '却下', waived: '免除', adopted: '正とした', expired: '期限切れ。再度確認が必要',
    rejectBtn: '却下（指摘は誤り）', waiveBtn: '期限つきで免除', decideBtn: '判断を記録',
    aiNot: '未実施', aiRun: '実行中', aiDone: '完了', aiFail: '失敗', aiPartial: '一部のみ', candidate: '候補',
    traceMiss: '未達', traceIn: '追跡対象', traceOut: '対象外', inferred: '推定', gateMiss: '基準未達'
  };
  /* Readiness: API の 5 状態に 1 対 1。ピルはこの 5 語だけ（[語, CSS 修飾子, 色の意味]） */
  var READY = {
    BLOCKED: ['ブロック中', 'blocked', 'danger'],
    DRAFT: ['下書き', 'draft', 'neutral'],
    REVIEWABLE: ['確認可能', 'reviewable', 'warning'],
    CONDITIONALLY_READY: ['条件付き', 'conditional', 'warning'],
    READY: ['準備完了', 'ready', 'success']
  };
  var TEST = { CAN_TEST: 'テストできる', PARTIALLY_TESTABLE: '一部のみ', NOT_TESTABLE: 'テスト不可', UNKNOWN: W.unknown };
  var METRIC = {
    open: { label: '判断待ち', definition: '判断を記録していない指摘・矛盾と、文書を直すまで閉じないテスト不可の合計', numerator: 'buildModel() の open=true の件数（規則指摘＋矛盾＋テスト不可）', denominator: 'なし（件数）', scope: '1 回の検査の全文書' },
    openConflict: { label: '判断待ちの矛盾', definition: '判断待ちのうち種類が矛盾のもの', numerator: 'buildModel() の open=true かつ kind=c', denominator: 'なし（判断待ちの内数）', scope: '1 回の検査の全文書' },
    decided: { label: '判断済み', definition: '判断を記録した指摘・矛盾', numerator: 'buildModel() の open=false', denominator: '判断を記録できるもの（規則指摘＋矛盾。テスト不可を除く）', scope: '1 回の検査の全文書' },
    requirements: { label: '要件', definition: '抽出した要件（文書×ID の行）', numerator: 'requirements[] の件数（document_id:requirement_id）', denominator: 'なし（件数）', scope: '全文書（要件定義書＋基本設計書）' },
    reqOpen: { label: '判断待ちありの要件', definition: '判断待ちの指摘か矛盾が 1 件以上ある要件', numerator: 'reqModel() で判断待ちありの行', denominator: '要件（文書×ID）', scope: '全文書' },
    coverage: { label: '被覆', definition: '追跡対象の要件のうち次段へつながった割合', numerator: 'trace.coverage.*.count', denominator: '追跡対象の要件（trace.coverage.*.total）', scope: 'トレースの追跡対象（要件定義書のノード）' },
    score: { label: '観点の点数', definition: '品質観点ごとの点数（基準 60）', numerator: 'scores[観点].value', denominator: '評価できた要件（観点ごとに異なる）', scope: '全文書' }
  };
  /* 件数ラベルの組み立て（見出し横・サイドバー・ツールチップで同じ文を使う） */
  function n(v) { return (v == null ? 0 : v) + ' 件'; }
  var LABEL = {
    issues: function (v) { return W.open + ' ' + n(v); },
    conf: function (v) { return '判断待ちの矛盾 ' + n(v); },
    confOf: function (all, c) { return W.open + ' ' + n(all) + 'のうち矛盾 ' + n(c); },
    req: function (v, byDoc) { return '要件 ' + n(v) + (byDoc && byDoc.length ? '（' + byDoc.join('・') + '）' : ''); },
    reqOpen: function (v) { return W.reqOpen + 'の要件 ' + n(v); }
  };
  var prev = window.DAM || {};
  window.DAM = { WORD: W, READY: READY, TEST: TEST, METRIC: METRIC, LABEL: LABEL };
  Object.keys(prev).forEach(function (k) { if (!(k in window.DAM)) window.DAM[k] = prev[k]; });
})();
