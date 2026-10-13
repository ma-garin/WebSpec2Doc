/* バッチ・スクリプトのテスト（System 07）の画面。
 * いまは見本データ（SAMPLE）で 4 工程を表示するだけで、API にはつながっていない。
 * 取り込み・ケース生成・コード生成の API ができたら SAMPLE を応答に置き換える。 */
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var esc = function (v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };

  var STEPS = [
    { id: 'intake', name: '取り込み' },
    { id: 'cases', name: '観点とケース表' },
    { id: 'code', name: 'テストコード' },
    { id: 'export', name: '書き出し' }
  ];

  var C = function (id, obs, tech, pre, run, exp, src, ask) {
    return { id: id, obs: obs, tech: tech, pre: pre, run: run, exp: exp, src: src, ask: !!ask };
  };
  var SAMPLE = {
    jobs: [
      { name: '月次締めバッチ', file: 'monthly_close.bat', cases: 18, ask: 2, at: '2026-10-13 22:20', on: true },
      { name: '夜間の売上集計', file: 'nightly_sales.sh', cases: 24, ask: 0, at: '2026-10-11 18:02' },
      { name: '顧客マスタ取り込み', file: 'import_customers.ps1', cases: 0, ask: 0, at: '2026-10-10 09:41' }
    ],
    files: [
      ['monthly_close.bat', 'スクリプト', '4.2 KB'],
      ['月次締め仕様書.xlsx', '仕様書', '38 KB'],
      ['input_202609.csv', '入力サンプル', '12 KB'],
      ['expected_out_202609.csv', '期待出力', '3.1 KB']
    ],
    facts: [
      ['引数', [['対象年月', 'YYYYMM・必須'], ['--dry-run', '任意・書き込まない']]],
      ['終了コード', [['0', '正常'], ['1', '入力ファイルなし'], ['2', '引数・形式の誤り'], ['9', '想定外の失敗']]],
      ['入出力', [['data\\in\\input_{年月}.csv', '読む'], ['data\\out\\close_{年月}.csv', '書く'], ['logs\\close.log', '追記']]],
      ['環境変数・前提', [['CLOSE_HOME', '必須・基準フォルダ'], ['ロックファイル', 'close.lock で二重起動を防ぐ']]]
    ],
    cases: [
      C('B-01', '正常', '同値分割', 'input_202609.csv（100 行）', 'monthly_close.bat 202609', '終了コード 0／close_202609.csv が期待出力と一致', '仕様書 2.1'),
      C('B-02', '正常', '同値分割', 'input_202609.csv（1 行）', 'monthly_close.bat 202609', '終了コード 0／1 行出力', '仕様書 2.1'),
      C('B-03', '引数', '境界値', '対象年月 = 202601', 'monthly_close.bat 202601', '終了コード 0', '仕様書 2.3'),
      C('B-04', '引数', '境界値', '対象年月 = 202612', 'monthly_close.bat 202612', '終了コード 0', '仕様書 2.3'),
      C('B-05', '引数', '境界値', '対象年月 = 202613', 'monthly_close.bat 202613', '終了コード 2／「年月が不正です」を標準エラーへ', '仕様書 2.3'),
      C('B-06', '引数', '境界値', '対象年月 = 202600', 'monthly_close.bat 202600', '終了コード 2', '仕様書 2.3'),
      C('B-07', '引数', '同値分割', '引数なし', 'monthly_close.bat', '終了コード 2／使い方を表示', 'スクリプト 12 行'),
      C('B-08', '引数', '同値分割', '対象年月 = 2026-09', 'monthly_close.bat 2026-09', '終了コード 2', 'スクリプト 15 行'),
      C('B-09', '入力ファイル', '同値分割', '入力ファイルなし', 'monthly_close.bat 202609', '終了コード 1／出力ファイルを作らない', '仕様書 3.2'),
      C('B-10', '入力ファイル', '境界値', '見出し行のみ（0 件）', 'monthly_close.bat 202609', '仕様に記載なし', '—', true),
      C('B-11', '入力ファイル', '同値分割', '列数が足りない行を含む', 'monthly_close.bat 202609', '終了コード 2／行番号をログへ', '仕様書 3.4'),
      C('B-12', '出力', '同値分割', '出力先フォルダなし', 'monthly_close.bat 202609', '終了コード 9／ログに原因', 'スクリプト 41 行'),
      C('B-13', 'ログ', '同値分割', 'B-01 と同じ', 'monthly_close.bat 202609', 'close.log に開始・終了・件数を追記', '仕様書 5.1'),
      C('B-14', '環境変数', '同値分割', 'CLOSE_HOME 未設定', 'monthly_close.bat 202609', '終了コード 9', 'スクリプト 5 行'),
      C('B-15', '再実行', '状態遷移', 'B-01 の後にもう一度', 'monthly_close.bat 202609', '出力を上書き・件数が倍にならない', '仕様書 4.1'),
      C('B-16', '途中失敗', '状態遷移', '処理中に入力を消す', 'monthly_close.bat 202609', '途中の出力を残さない', '—', true),
      C('B-17', '二重起動', '状態遷移', 'close.lock が残っている', 'monthly_close.bat 202609', '終了コード 9／「実行中です」', 'スクリプト 8 行'),
      C('B-18', 'dry-run', '同値分割', 'input_202609.csv', 'monthly_close.bat 202609 --dry-run', '終了コード 0／出力ファイルを作らない', 'スクリプト 30 行')
    ],
    srcs: [
      { name: 'test_monthly_close.py', map: 'B-01〜B-18（18 件）', body:
'<span class="c"># 自動生成: 月次締めバッチ（monthly_close.bat）のテスト。ケース表 B-01〜B-18 と 1 対 1。</span>\n' +
'<span class="k">import</span> subprocess, filecmp, pytest\n\n' +
'<span class="k">def</span> run(env, *args):\n' +
'    <span class="k">return</span> subprocess.run([<span class="s">"cmd"</span>, <span class="s">"/c"</span>, <span class="s">"monthly_close.bat"</span>, *args],\n' +
'                          cwd=env.home, env=env.vars, capture_output=<span class="k">True</span>, text=<span class="k">True</span>, timeout=<span class="s">300</span>)\n\n' +
'<span class="k">def</span> test_B01_正常_100行(env):\n' +
'    env.put_input(<span class="s">"input_202609.csv"</span>)\n' +
'    r = run(env, <span class="s">"202609"</span>)\n' +
'    <span class="k">assert</span> r.returncode == 0\n' +
'    <span class="k">assert</span> filecmp.cmp(env.out(<span class="s">"close_202609.csv"</span>), env.expected(<span class="s">"expected_out_202609.csv"</span>))\n\n' +
'@pytest.mark.parametrize(<span class="s">"ym, code"</span>, [(<span class="s">"202601"</span>, 0), (<span class="s">"202612"</span>, 0), (<span class="s">"202613"</span>, 2), (<span class="s">"202600"</span>, 2)])\n' +
'<span class="k">def</span> test_B03_B06_年月の境界(env, ym, code):\n' +
'    env.put_input(<span class="s">"input_202609.csv"</span>, rename=f<span class="s">"input_{ym}.csv"</span>)\n' +
'    <span class="k">assert</span> run(env, ym).returncode == code\n\n' +
'<span class="k">def</span> test_B09_入力ファイルなし(env):\n' +
'    r = run(env, <span class="s">"202609"</span>)\n' +
'    <span class="k">assert</span> r.returncode == 1\n' +
'    <span class="k">assert not</span> env.out(<span class="s">"close_202609.csv"</span>).exists()\n\n' +
'@pytest.mark.skip(reason=<span class="s">"B-10: 仕様に記載なし（要確認）"</span>)\n' +
'<span class="k">def</span> test_B10_見出し行のみ(env): ...\n' },
      { name: 'conftest.py', map: '作業フォルダと環境変数の用意', body:
'<span class="c"># 各テストを空の作業フォルダで動かし、CLOSE_HOME をそこへ向ける。</span>\n' +
'<span class="k">import</span> os, shutil, pytest\n\n' +
'@pytest.fixture\n<span class="k">def</span> env(tmp_path):\n' +
'    shutil.copy(<span class="s">"monthly_close.bat"</span>, tmp_path)\n' +
'    (tmp_path / <span class="s">"data/in"</span>).mkdir(parents=<span class="k">True</span>); (tmp_path / <span class="s">"data/out"</span>).mkdir()\n' +
'    <span class="k">return</span> Env(tmp_path, {**os.environ, <span class="s">"CLOSE_HOME"</span>: str(tmp_path)})\n' },
      { name: 'fixtures/input_202609.csv', map: '取り込んだ入力サンプル', body: '<span class="c">（取り込んだ input_202609.csv をそのまま同梱）</span>' }
    ],
    outs: [
      ['ケース表', 'Excel（.xlsx）。ID・観点・技法・期待結果・根拠の列。テスト自動化のケース表と同じ形式です。', 'ケース表を書き出す'],
      ['テストコード一式', 'テストコード・準備用のファイル・入力サンプルをまとめた zip。展開して pytest を実行します。', 'zip を書き出す'],
      ['要確認の質問票', '仕様に書かれていない 2 件を質問にまとめます。ドキュメント検証の質問票へ送れます。', '質問票へ送る']
    ],
    checks: [
      '要確認が 2 件残っています（B-10・B-16）。仕様の回答を待つか、期待結果を書き込んでください。',
      'テストコードはこの画面では実行していません。お使いの Windows 環境で 1 回実行して確かめてください。',
      '入力サンプルに個人情報が含まれていないか確かめてから渡してください。'
    ]
  };

  var state = { step: 'intake', obs: '', src: 0 };

  function renderJobs() {
    var q = ($('#bt-q').value || '').trim();
    var jobs = SAMPLE.jobs.filter(function (j) { return !q || (j.name + j.file).indexOf(q) >= 0; });
    $('#bt-cnt').textContent = SAMPLE.jobs.length;
    $('#bt-jobs').innerHTML = jobs.length ? jobs.map(function (j) {
      var foot = j.cases ? j.cases + ' ケース' + (j.ask ? '・要確認 ' + j.ask : '') : 'ケース未作成';
      return '<div class="it' + (j.on ? ' on' : '') + '" role="listitem"><button type="button" class="it-main" aria-current="' + !!j.on + '">'
        + '<i class="' + (j.cases ? (j.ask ? 'i-flaky' : 'i-pass') : 'i-new') + '"></i>'
        + '<span class="grow"><b>' + esc(j.name) + '</b><small>' + esc(j.file) + '</small><small>' + esc(foot) + ' · ' + esc(j.at) + '</small></span></button></div>';
    }).join('') : '<div class="it empty">一致する案件はありません</div>';
  }

  function renderSteps() {
    var idx = STEPS.findIndex(function (s) { return s.id === state.step; });
    var notes = { intake: '4 ファイル', cases: '18 件', code: '3 ファイル', export: '' };
    $('#bt-steps').innerHTML = STEPS.map(function (s, i) {
      var cls = i === idx ? ' on' : (i < idx ? ' done' : '');
      return '<button type="button" class="bt-step' + cls + '" role="tab" aria-selected="' + (i === idx) + '" data-go="' + s.id + '">'
        + '<b>' + (i < idx ? '✓' : i + 1) + '</b><span>' + esc(s.name) + '</span><small>' + esc(notes[s.id]) + '</small></button>';
    }).join('');
    document.querySelectorAll('.rail [data-step]').forEach(function (b) { b.classList.toggle('on', b.dataset.step === state.step); });
    document.querySelectorAll('.bt-panel').forEach(function (p) { p.hidden = p.dataset.panel !== state.step; });
    $('#topbar-title').textContent = STEPS[idx].name;
  }

  function renderIntake() {
    $('#bt-files').innerHTML = SAMPLE.files.map(function (f) {
      return '<tr><td><code>' + esc(f[0]) + '</code></td><td><span class="pill p-new">' + esc(f[1]) + '</span></td><td>' + esc(f[2]) + '</td></tr>';
    }).join('');
    $('#bt-facts').innerHTML = SAMPLE.facts.map(function (g) {
      return '<div class="bt-fact"><h4>' + esc(g[0]) + '</h4><ul>' + g[1].map(function (x) {
        return '<li><code>' + esc(x[0]) + '</code><small>' + esc(x[1]) + '</small></li>';
      }).join('') + '</ul></div>';
    }).join('');
  }

  function renderCases() {
    var all = SAMPLE.cases, ask = all.filter(function (c) { return c.ask; }).length;
    var obsList = [];
    all.forEach(function (c) { if (obsList.indexOf(c.obs) < 0) obsList.push(c.obs); });
    var kpi = function (v, l, cls) { return '<div class="kpi' + (cls ? ' ' + cls : '') + '"><b>' + esc(v) + '</b><span>' + esc(l) + '</span></div>'; };
    $('#bt-kpis').innerHTML = kpi(all.length, 'ケース') + kpi(obsList.length, '観点') + kpi(ask, '要確認（仕様に記載なし）', ask ? 'wa' : '') + kpi(all.length - ask, '根拠つき', 'ok');
    $('#bt-obs').innerHTML = ['すべて'].concat(obsList).map(function (o) {
      var key = o === 'すべて' ? '' : o, n = key ? all.filter(function (c) { return c.obs === key; }).length : all.length;
      return '<span class="fchip' + (state.obs === key ? ' on' : '') + '" role="button" tabindex="0" aria-pressed="' + (state.obs === key) + '" data-obs="' + esc(key) + '">' + esc(o) + ' <em>' + n + '</em></span>';
    }).join('');
    var rows = all.filter(function (c) { return !state.obs || c.obs === state.obs; });
    $('#bt-shown').textContent = rows.length + ' / ' + all.length + ' 件';
    $('#bt-rows').innerHTML = rows.map(function (c) {
      return '<tr class="' + (c.ask ? 'ask' : '') + '"><td>' + esc(c.id) + '</td><td>' + esc(c.obs) + '</td><td>' + esc(c.tech) + '</td><td>' + esc(c.pre)
        + '</td><td><code>' + esc(c.run) + '</code></td><td>' + esc(c.exp) + '</td><td>' + esc(c.src) + '</td><td>'
        + (c.ask ? '<span class="pill p-flaky">要確認</span>' : '<span class="pill p-pass">根拠あり</span>') + '</td></tr>';
    }).join('');
    $('#bt-ask-note').textContent = ask ? '要確認の ' + ask + ' 件は、期待結果を推測で埋めていません。' : '';
    var bd = $('#bt-bd-ask'); bd.textContent = ask; bd.hidden = !ask;
  }

  function renderCode() {
    $('#bt-srcs').innerHTML = SAMPLE.srcs.map(function (s, i) {
      return '<div class="it' + (i === state.src ? ' on' : '') + '" role="listitem"><button type="button" class="it-main" data-src="' + i + '"><i class="i-pass"></i>'
        + '<span class="grow"><b>' + esc(s.name) + '</b><small>' + esc(s.map) + '</small></span></button></div>';
    }).join('');
    var s = SAMPLE.srcs[state.src];
    $('#bt-src-name').textContent = s.name;
    $('#bt-src-map').textContent = s.map;
    $('#bt-src').innerHTML = s.body; /* 見本の固定文字列。利用者の入力は含まない */
  }

  function renderExport() {
    $('#bt-outs').innerHTML = SAMPLE.outs.map(function (o) {
      return '<div class="bt-card bt-out"><h3>' + esc(o[0]) + '</h3><p>' + esc(o[1]) + '</p><button type="button" class="btn" data-todo="1">' + esc(o[2]) + '</button></div>';
    }).join('');
    $('#bt-checks').innerHTML = SAMPLE.checks.map(function (c) { return '<li>' + esc(c) + '</li>'; }).join('');
  }

  function toast(msg) {
    var t = $('#bt-toast'); t.textContent = msg; t.hidden = false;
    clearTimeout(toast.id); toast.id = setTimeout(function () { t.hidden = true; }, 3000);
  }

  function go(step) {
    if (!STEPS.some(function (s) { return s.id === step; })) step = 'intake';
    state.step = step;
    if (location.hash !== '#' + step) history.replaceState(null, '', '#' + step);
    renderSteps();
    $('#bt-content').scrollTop = 0;
  }

  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-go],[data-step],[data-obs],[data-src],[data-todo],#bt-new');
    if (!t) return;
    if (t.dataset.go || t.dataset.step) return go(t.dataset.go || t.dataset.step);
    if (t.hasAttribute('data-obs')) { state.obs = t.dataset.obs; return renderCases(); }
    if (t.dataset.src) { state.src = +t.dataset.src; return renderCode(); }
    toast('この操作はまだつながっていません。見本の画面です。');
  });
  document.addEventListener('keydown', function (e) {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('[data-obs]')) { e.preventDefault(); e.target.click(); }
  });
  $('#bt-q').addEventListener('input', renderJobs);
  window.addEventListener('hashchange', function () { go(location.hash.slice(1)); });

  renderJobs(); renderIntake(); renderCases(); renderCode(); renderExport();
  go(location.hash.slice(1));
})();
