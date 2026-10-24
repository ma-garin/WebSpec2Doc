/* ---------------------------------------------------------------------------
 * 現在地バー（製品名・パンくず・作業名・1 行説明）
 *
 * レールはアイコンとツールチップだけなので、何のツールの、どの作業をして
 * いるのかが画面から読めない。ここで常に言葉にする。
 * ------------------------------------------------------------------------- */
(function () {
  'use strict';
  var T = window.TA2;
  if (!T) return;
  var S = T.state;

  /* 作業名と、その画面で何ができるかの 1 行。利用者の言葉で書く。 */
  var TASK = {
    home:     ['ホーム',     'URL を入れると、画面仕様・テスト条件・テストケースまで自動で作ります'],
    spec:     ['分析・設計', '解析した画面の仕様と、そこから設計したテストケースを見る・直す'],
    site:     ['分析・設計', 'サイトの地図。画面ごとの網羅状況と、まだテストしていない箇所'],
    test:     ['自動化',     '設計したケースを実行できるコードにして、走らせて結果を見る'],
    run:      ['自動化',     '実行の結果と証跡。失敗は理由・停止したステップ・修正案まで'],
    drift:    ['変更',       'サイトが変わった箇所と、影響するテスト。壊れる前に直す'],
    schedule: ['定期実行',   '決めた時刻に解析し、変化があったら知らせる'],
    report:   ['報告',       'このツールが無くても開ける 1 枚の HTML にまとめる'],
    team:     ['チーム',     '同じサイトを一緒に見るメンバーと、CI 用のトークン']
  };

  /* パンくずの中段。作業のまとまりを示す（レールの並びと合わせる） */
  var GROUP = {
    spec: '分析・設計', site: '分析・設計',
    test: '自動化', run: '自動化',
    drift: '変更', schedule: '定期実行', report: '報告', team: 'チーム'
  };

  function esc(v) { return T.esc ? T.esc(v) : String(v == null ? '' : v); }

  function render() {
    var v = S.view || 'home';
    var task = TASK[v] || ['', ''];
    var crumb = document.getElementById('ws-crumb');
    var title = document.getElementById('ws-task');
    var lead = document.getElementById('ws-lead');
    if (title) title.textContent = task[0];
    // 共通ヘッダーの見出しも作業名に合わせる（どの System のどの作業かを上端で読めるように）
    var top = document.getElementById('topbar-title');
    if (top && v !== 'home' && task[0]) top.textContent = v === 'run' ? task[0] + ' · 実行と結果' : task[0];
    if (lead) { lead.textContent = task[1]; lead.hidden = v === 'home' || !task[1]; }
    var head = document.getElementById('ws-page-head');
    if (head) head.hidden = v !== 'home';
    renderContext(v);
    if (!crumb) return;

    var parts = [];
    if (v === 'home') {
      parts.push('<span class="cur">サイト一覧</span>');
    } else if (!S.domain) {
      parts.push('<a href="/">サイト一覧</a>');
      parts.push('<span class="cur">' + esc(task[0]) + '</span>');
    } else {
      parts.push('<a href="/">サイト一覧</a>');
      parts.push('<a href="/sites/' + encodeURIComponent(S.domain) + '/spec">' + esc(S.domain) + '</a>');
      parts.push('<span class="cur">' + esc(GROUP[v] || task[0]) + '</span>');
    }
    crumb.innerHTML = parts.join('<span aria-hidden="true">/</span>');
  }

  /* 対象サイトの表示（c-context）と、サイト内の作業の切替（c-tabs）。ホームでは出さない */
  var GROUP_TABS = [['spec', '仕様', 'spec'], ['test', '自動化', 'tests'], ['drift', '変更', 'changes'], ['report', '報告', 'report']];
  function renderContext(v) {
    var box = document.getElementById('ws-context');
    var tabs = document.getElementById('ws-tabs');
    var show = v !== 'home' && !!S.domain;
    if (box) box.hidden = !show;
    if (tabs) tabs.hidden = !show;
    if (!show) return;
    var it = T.historyItem ? T.historyItem(S.domain) : null;
    var fails = 0;
    (S.tests || []).forEach(function (t) { if (t.status === 'fail') fails++; });
    var st = !it ? '解析結果を読み込んでいます'
      : (Number(it.screens) > 0 ? (fails ? '失敗 ' + fails + ' 件' : '解析済み') : '画面 0（解析できていません）');
    if (box) {
      box.innerHTML = '<span class="c-context__item">対象サイト <b>' + esc(S.domain) + '</b></span>'
        + '<span class="c-context__item">最終解析 <b>' + esc((it && it.updated) || '—') + '</b></span>'
        + '<span class="c-context__item">状態 <b>' + esc(st) + '</b></span>';
    }
    if (tabs) {
      var d = encodeURIComponent(S.domain);
      tabs.innerHTML = GROUP_TABS.map(function (g) {
        var cur = v === g[0] || (g[0] === 'test' && v === 'run') || (g[0] === 'spec' && v === 'site');
        return '<a role="tab" href="/sites/' + d + '/' + g[2] + '" aria-selected="' + (cur ? 'true' : 'false') + '">' + g[1] + '</a>';
      }).join('');
    }
  }

  T.on('history', render);
  T.on('tests', render);
  T.on('view', render);
  T.on('boot', render);
  T.on('render', render);
  if (document.readyState !== 'loading') render();
  else document.addEventListener('DOMContentLoaded', render);
})();
