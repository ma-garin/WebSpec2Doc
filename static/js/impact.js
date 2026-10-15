/* 影響度分析（System 08）の画面。いまは見本データのみで、API はまだ無い。
 * 工程: 入力（入力受付・文書確認）→ 変更点と検索（クエリ生成・文書検索・統合）→ 影響と優先度（影響度・優先度の判定）。 */
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var esc = function (v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var STEPS = [{ id: 'intake', name: '入力' }, { id: 'search', name: '変更点と検索' }, { id: 'impact', name: '影響と優先度' }];
  var LV = { 4: '致命', 3: '大', 2: '中', 1: '小' };

  var SAMPLE = {
    jobs: [{ name: '会員登録: 電話番号を必須に', at: '10/15 10:20' }, { name: '注文確定: クーポン併用の上限', at: '10/14 17:05' }],
    order: '会員登録画面で電話番号を任意から必須に変える。あわせて桁数チェックを 10〜11 桁に変更する。',
    docs: [
      { name: '画面仕様書_会員登録.xlsx', ver: 'v2.3 → v2.4', kind: '画面仕様書' },
      { name: '基本設計書_会員管理.docx', ver: 'v1.8', kind: '設計書' }
    ],
    stores: [
      { name: '設計書', n: 42, at: '10/15 09:00', ok: true },
      { name: '画面仕様書', n: 118, at: '10/15 09:00', ok: true },
      { name: 'テストケース（既存）', n: 1260, at: '10/10 18:30', ok: false }
    ],
    diffs: [
      { id: 'C1', where: '会員登録 / 電話番号', before: '任意', after: '必須' },
      { id: 'C2', where: '会員登録 / 電話番号', before: '桁数 10〜13', after: '桁数 10〜11' }
    ],
    queries: [
      { id: 'Q1', from: 'C1', q: '電話番号 AND (必須 OR 任意 OR 未入力)', store: '設計書・画面仕様書', hit: 9, merged: 5 },
      { id: 'Q2', from: 'C1', q: 'member.tel を参照する処理', store: '設計書', hit: 6, merged: 3 },
      { id: 'Q3', from: 'C2', q: '電話番号 AND (桁数 OR 文字数 OR 13桁)', store: '設計書・画面仕様書', hit: 4, merged: 2 },
      { id: 'Q4', from: 'C1, C2', q: '電話番号 入力チェック', store: 'テストケース（既存）', hit: 14, merged: 4 }
    ],
    rows: [
      { p: 1, lv: 4, where: '既存会員のログイン後プロフィール更新', why: '電話番号が空の既存会員は、更新時に必須チェックで保存できなくなる。', doc: '基本設計書_会員管理.docx §4.2 会員情報の更新', quote: '更新時は登録時と同じ入力チェックを行う。', test: '電話番号が未登録の既存会員で、他の項目だけを更新する' },
      { p: 1, lv: 4, where: 'CSV 一括会員取込（管理画面）', why: '取込データの電話番号は空欄を許していた。必須化で取込全体が失敗する恐れ。', doc: '基本設計書_会員管理.docx §6.1 一括取込', quote: '項目チェックは画面登録と共通の検証部品を用いる。', test: '電話番号が空の行を含む CSV を取り込む' },
      { p: 2, lv: 3, where: '会員登録 確認画面', why: '電話番号の表示欄が「未入力」表記を持つ。必須化で表記が不要になる。', doc: '画面仕様書_会員登録.xlsx 確認画面 No.12', quote: '未入力の場合は「（未入力）」と表示する。', test: '確認画面で電話番号の表示と戻る操作を確かめる' },
      { p: 2, lv: 3, where: '12 桁・13 桁の番号で登録済みの会員', why: '桁数の上限が 13 → 11 に下がる。既存データが新しいチェックに通らない。', doc: '画面仕様書_会員登録.xlsx 入力項目 No.7', quote: '電話番号: 半角数字 10〜13 桁', test: '12 桁の電話番号を持つ会員で、情報を更新する' },
      { p: 3, lv: 2, where: '会員登録 入力画面のエラー文言', why: '必須と桁数のエラー文言が変わる。', doc: '画面仕様書_会員登録.xlsx メッセージ一覧 M-021', quote: '電話番号は 10〜13 桁で入力してください。', test: '未入力・9 桁・12 桁でエラー文言を確かめる' },
      { p: 3, lv: 1, where: '既存テストケース TC-REG-031〜034', why: '旧仕様（任意・13 桁まで）を期待値にしている。期待値の書き換えが要る。', doc: 'テストケース（既存） TC-REG-031', quote: '電話番号を空欄で登録できること', test: '該当ケースの期待値を新仕様に直してから再実行する' }
    ]
  };
  var state = { step: 'intake', pri: 0 };

  function renderSteps() {
    var at = STEPS.findIndex(function (s) { return s.id === state.step; });
    $('#im-steps').innerHTML = STEPS.map(function (s, i) {
      var cls = i === at ? 'on' : i < at ? 'done' : '';
      return '<button type="button" role="tab" class="bt-step ' + cls + '" data-go="' + s.id + '" aria-selected="' + (i === at) + '"><b>' + (i + 1) + '</b><span>' + s.name + '</span></button>';
    }).join('');
    document.querySelectorAll('.app-nav-item[data-step]').forEach(function (b) { b.classList.toggle('on', b.dataset.step === state.step); });
    document.querySelectorAll('[data-panel]').forEach(function (p) { p.hidden = p.dataset.panel !== state.step; });
    var t = $('#topbar-title');
    if (t) t.textContent = STEPS[at].name;
  }

  function renderStatic() {
    $('#im-cnt').textContent = SAMPLE.jobs.length;
    $('#im-jobs').innerHTML = SAMPLE.jobs.map(function (j, i) {
      return '<div class="it' + (i === 0 ? ' on' : '') + '" role="listitem"><button type="button" class="it-main" aria-current="' + (i === 0) + '"><span class="grow"><b>' + esc(j.name) + '</b><small>' + esc(j.at) + '</small></span></button></div>';
    }).join('');
    $('#im-order').value = SAMPLE.order;
    $('#im-docs').innerHTML = SAMPLE.docs.map(function (d) {
      return '<tr><td>' + esc(d.name) + '</td><td>' + esc(d.ver) + '</td><td>' + esc(d.kind) + '</td></tr>';
    }).join('');
    $('#im-stores').innerHTML = SAMPLE.stores.map(function (s) {
      return '<li><b>' + esc(s.name) + '</b><small>' + s.n + ' 件 ・ 索引 ' + esc(s.at) + '</small>' +
        '<span class="pill ' + (s.ok ? 'p-pass' : 'p-flaky') + '">' + (s.ok ? '最新' : '5 日前') + '</span></li>';
    }).join('');
    $('#im-diffs').innerHTML = SAMPLE.diffs.map(function (d) {
      return '<div class="im-diff"><code>' + d.id + '</code><span>' + esc(d.where) + '</span><span><del>' + esc(d.before) + '</del></span><span><ins>' + esc(d.after) + '</ins></span></div>';
    }).join('');
    var hit = 0, merged = 0;
    $('#im-queries').innerHTML = SAMPLE.queries.map(function (q) {
      hit += q.hit; merged += q.merged;
      return '<tr><td><code>' + q.id + '</code></td><td>' + esc(q.from) + '</td><td><code>' + esc(q.q) + '</code></td><td>' + esc(q.store) + '</td><td>' + q.hit + '</td><td>' + q.merged + '</td></tr>';
    }).join('');
    $('#im-qsum').textContent = 'ヒット ' + hit + ' 件 → 統合後 ' + merged + ' 件';
  }

  function renderImpact() {
    var cnt = [0, 0, 0, 0, 0];
    SAMPLE.rows.forEach(function (r) { cnt[r.lv] += 1; });
    $('#im-kpis').innerHTML = [4, 3, 2, 1].map(function (lv) {
      return '<div class="kpi"><b>' + cnt[lv] + '</b><span>影響度 ' + LV[lv] + '</span></div>';
    }).join('');
    $('#im-filter').innerHTML = [0, 1, 2, 3].map(function (p) {
      return '<button type="button" class="fchip' + (state.pri === p ? ' on' : '') + '" data-pri="' + p + '">' + (p ? 'P' + p : 'すべて') + '</button>';
    }).join('');
    var rows = SAMPLE.rows.filter(function (r) { return !state.pri || r.p === state.pri; });
    $('#im-shown').textContent = rows.length + ' 件';
    $('#im-rows').innerHTML = rows.map(function (r) {
      return '<tr><td><span class="im-pri p' + r.p + '">P' + r.p + '</span></td><td>' + esc(r.where) + '</td>' +
        '<td><span class="im-lv l' + r.lv + '">' + LV[r.lv] + '</span></td><td>' + esc(r.why) + '</td>' +
        '<td>' + esc(r.doc) + '<q>' + esc(r.quote) + '</q></td><td>' + esc(r.test) + '</td></tr>';
    }).join('');
  }

  document.addEventListener('click', function (e) {
    var go = e.target.closest('[data-go],[data-step]');
    if (go) { state.step = go.dataset.go || go.dataset.step; renderSteps(); return; }
    var f = e.target.closest('[data-pri]');
    if (f) { state.pri = Number(f.dataset.pri); renderImpact(); }
  });

  renderStatic();
  renderImpact();
  renderSteps();
})();
