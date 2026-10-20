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
    if (lead) lead.textContent = task[1];
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

  T.on('view', render);
  T.on('boot', render);
  T.on('render', render);
  if (document.readyState !== 'loading') render();
  else document.addEventListener('DOMContentLoaded', render);
})();
