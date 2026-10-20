/* バッチ・スクリプトのテスト（System 07）の画面。API: /api/batch-test/*（web/routes/batch_test.py）。
 * 工程: 取り込み → 観点とケース表 → テストコード → 書き出し。選んだ案件は URL の ?job= に持つ。 */
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var esc = function (v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var API = '/api/batch-test/jobs';
  var STEPS = [
    { id: 'intake', name: '取り込み' }, { id: 'cases', name: '観点とケース表' },
    { id: 'code', name: 'テストコード' }, { id: 'export', name: '書き出し' }
  ];
  var KINDS = { script: 'スクリプト', spec: '仕様書', input: '入力サンプル', expected: '期待出力' };
  var W = window.WS2D || null;
  /* 取り込めるファイル（サーバは拡張子を見ないので、ここで非対応形式を先に止める） */
  var OK_EXT = ['.bat', '.cmd', '.sh', '.ps1', '.xlsx', '.docx', '.md', '.txt', '.pdf', '.csv'];
  var MAX_BYTES = 20 * 1048576;
  /* exported: 案件ごとの書き出し記録。サーバには残らないので、この画面の操作中だけ（リロードで消える） */
  var state = { jobs: [], job: null, step: 'intake', obs: '', src: 0, editing: '', exported: {}, notice: {} };

  function api(method, path, body) {
    var opt = { method: method, headers: {} };
    if (body instanceof FormData) opt.body = body;
    else if (body) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    return fetch(path, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) throw new Error(d.error || '処理できませんでした（' + r.status + '）。時間をおいてもう一度お試しください。');
        return d;
      });
    }, function () { throw new Error('サーバにつながりません。画面を再読み込みしてください。'); });
  }
  function banner(msg) { var b = $('#bt-banner'); b.textContent = msg || ''; b.hidden = !msg; }
  function toast(msg, kind) {
    if (W && W.toast) { W.toast(msg, kind || 'success'); return; }
    var t = $('#bt-toast'); t.textContent = msg; t.hidden = false;
    clearTimeout(toast.id); toast.id = setTimeout(function () { t.hidden = true; }, 3000);
  }
  function busy(el, on) { if (el) { el.classList.toggle('bt-busy', on); el.disabled = on; } }
  /* 状態の通知（WS2D.state）。host の id ごとに 1 つ持ち、次の成功操作で消す */
  function notice(id, opts) { state.notice[id] = opts; paintNotice(id); }
  function paintNotice(id, fallback) {
    var host = document.getElementById(id), o = state.notice[id] || fallback;
    if (!host) return;
    if (o && W) { host.hidden = false; W.state(host, o); } else { host.innerHTML = ''; host.hidden = true; }
  }
  var NOTICE_HOSTS = ['bt-intake-state', 'bt-cases-state', 'bt-code-state', 'bt-export-state'];
  function failHostFor(el) {
    var p = el && el.closest ? el.closest('[data-panel]') : null;
    return p ? ({ intake: 'bt-intake-state', cases: 'bt-cases-state', code: 'bt-code-state', export: 'bt-export-state' })[p.dataset.panel] : 'bt-intake-state';
  }
  function run(el, p, okMsg, failTitle, failNext) {
    banner(''); busy(el, true);
    var host = failHostFor(el);
    return p.then(function (d) {
      NOTICE_HOSTS.forEach(function (h) { delete state.notice[h]; });
      if (d.job) setJob(d.job); else renderAll();
      if (okMsg) toast(okMsg); return d;
    })
      .catch(function (e) {
        if (failTitle) notice(host, { kind: 'error', title: failTitle, message: e.message, retained: true, next: failNext || 'もう一度押してください。続かないときは入力を見直してください。' });
        else banner(e.message);
        renderReason();
      })
      .then(function (d) { busy(el, false); return d; });
  }
  function fmtSize(n) {
    return n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : n >= 1024 ? (n / 1024).toFixed(1) + ' KB' : n + ' B';
  }
  function fmtTime(t) {
    var d = t ? new Date(t) : null;
    return d && !isNaN(d) ? d.toLocaleString('ja-JP', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
  }

  /* ---- 案件一覧 ---- */
  function loadJobs() {
    return api('GET', API).then(function (d) { state.jobs = d.jobs; renderJobs(); })
      .catch(function (e) { banner(e.message); });
  }
  function renderJobs() {
    var q = ($('#bt-q').value || '').trim();
    var jobs = state.jobs.filter(function (j) {
      return !q || (j.name + ' ' + j.files.map(function (f) { return f.name; }).join(' ')).indexOf(q) >= 0;
    });
    $('#bt-cnt').textContent = state.jobs.length;
    var cur = state.job && state.job.id;
    $('#bt-jobs').innerHTML = jobs.length ? jobs.map(function (j) {
      var script = (j.files.filter(function (f) { return f.kind === 'script'; })[0] || {}).name || 'スクリプト未取り込み';
      var foot = j.case_count ? j.case_count + ' ケース（生成済み・未実行）' + (j.ask_count ? '・要確認 ' + j.ask_count : '') : 'ケース未作成';
      var on = j.id === cur;
      return '<div class="it' + (on ? ' on' : '') + '" role="listitem"><button type="button" class="it-main" data-job="' + esc(j.id) + '" aria-current="' + on + '">'
        + '<i class="' + (j.case_count ? (j.ask_count ? 'i-flaky' : 'i-new') : 'i-new') + '"></i>'
        + '<span class="grow"><b>' + esc(j.name) + '</b><small>' + esc(script) + '</small><small>' + esc(foot) + ' · ' + esc(fmtTime(j.updated_at)) + '</small></span></button>'
        + '<button type="button" class="del" data-deljob="' + esc(j.id) + '" title="「' + esc(j.name) + '」を削除" aria-label="「' + esc(j.name) + '」を削除">✕</button></div>';
    }).join('') : '<div class="it empty">' + (state.jobs.length ? '一致する案件はありません' : 'まだ案件がありません') + '</div>';
  }
  /* URL は ?job=<id>#<step>。案件を開く・段階を変えるのは pushState、起動時と戻る・進むの復元は積まない */
  function syncUrl(push) {
    var want = location.pathname + (state.job ? '?job=' + encodeURIComponent(state.job.id) : '') + '#' + state.step;
    if (location.pathname + location.search + location.hash === want) return;
    history[push ? 'pushState' : 'replaceState'](null, '', want);
  }
  function openJob(id, noPush) {
    banner('');
    return api('GET', API + '/' + id).then(function (d) {
      setJob(d.job);
      syncUrl(!noPush);
    }).catch(function (e) { banner(e.message); });
  }
  function setJob(job) {
    state.job = job;
    var i = state.jobs.findIndex(function (j) { return j.id === job.id; });
    var sum = Object.assign({}, job, {
      case_count: job.cases.length,
      ask_count: job.cases.filter(function (c) { return c.ask; }).length
    });
    if (i >= 0) state.jobs[i] = sum; else state.jobs.unshift(sum);
    if (state.src >= job.sources.length) state.src = 0;
    renderAll();
  }

  /* ---- 工程 ---- */
  function renderSteps() {
    var j = state.job, idx = STEPS.findIndex(function (s) { return s.id === state.step; });
    var done = j ? { intake: !!j.facts, cases: j.cases.length > 0, code: j.sources.length > 0, export: false } : {};
    var notes = j ? {
      intake: j.files.length + ' ファイル', cases: j.cases.length ? j.cases.length + ' 件' : '',
      code: j.sources.length ? j.sources.length + ' ファイル' : '', export: ''
    } : {};
    $('#bt-steps').innerHTML = STEPS.map(function (s, i) {
      var cls = i === idx ? ' on' : (done[s.id] ? ' done' : '');
      return '<button type="button" class="bt-step' + cls + '" role="tab" aria-selected="' + (i === idx) + '" data-go="' + s.id + '"' + (j ? '' : ' disabled') + '>'
        + '<b>' + (done[s.id] && i !== idx ? '✓' : i + 1) + '</b><span>' + esc(s.name) + '</span><small>' + esc(notes[s.id] || '') + '</small></button>';
    }).join('');
    document.querySelectorAll('.rail [data-step]').forEach(function (b) {
      b.classList.toggle('on', !!j && b.dataset.step === state.step); b.disabled = !j;
    });
    $('#bt-empty').hidden = !!j;
    document.querySelectorAll('.bt-panel').forEach(function (p) { p.hidden = !j || p.dataset.panel !== state.step; });
    $('#topbar-title').textContent = j ? j.name + ' · ' + STEPS[idx].name : '案件を選ぶ';
    renderHead();
  }

  /* ---- 4 段の状態: 生成済み / 書き出し済み / 実行済み / 確認済み（別々に持つ。前の段が次の段を意味しない） ---- */
  function exportedKinds(j) { return j ? Object.keys(state.exported[j.id] || {}) : []; }
  var EXPORT_NAME = { 'cases.xlsx': 'ケース表', 'code.zip': 'テストコード一式', 'questions.csv': '質問票' };
  function stages(j) {
    var gen = j && (j.cases.length > 0 || j.sources.length > 0);
    var ex = exportedKinds(j);
    var ran = !!(j && j.results && j.results.length);
    var ver = !!(j && j.verified_at);
    return [
      { key: 'generated', code: gen ? 'preparing' : 'not_started', label: gen ? '生成済み' : '未生成',
        note: gen ? 'ケース ' + j.cases.length + ' 件・コード ' + j.sources.length + ' ファイル（未実行）' : 'ケース表とテストコードを作ると変わります' },
      { key: 'exported', code: ex.length ? 'preparing' : 'unverified', label: ex.length ? '書き出し済み（未実行）' : '未確認',
        note: ex.length ? ex.map(function (k) { return EXPORT_NAME[k]; }).join('・') + '。この画面の操作中だけの記録（リロード後は未確認）' : '書き出しの記録はサーバにありません' },
      { key: 'executed', code: ran ? 'done' : 'not_started', label: ran ? '実行済み' : '未実行',
        note: ran ? j.results.length + ' 件の実行結果を取り込み済み' : 'この画面ではテストを実行しません。書き出したコードを手元の pytest で実行してください（結果の取り込みは未対応）' },
      { key: 'verified', code: ver ? 'done' : 'unverified', label: ver ? '確認済み' : '未確認',
        note: ver ? '人が結果を確認済み' : '実行結果を取り込めないため、この画面では確認済みになりません' }
    ];
  }
  function renderStages() {
    var host = $('#bt-stages'), j = state.job;
    host.hidden = !j;
    if (!j) { host.innerHTML = ''; return; }
    var names = ['Generated', 'Exported', 'Executed', 'Verified'];
    host.innerHTML = stages(j).map(function (g, i) {
      var badge = W ? W.status.html(g.code, g.label) : esc(g.label);
      return '<li class="bt-stage" data-stage="' + g.key + '"><small>' + names[i] + '</small>' + badge + '<span>' + esc(g.note) + '</span></li>';
    }).join('');
  }
  function headAction() {
    var j = state.job;
    if (!j) return { label: '＋ 新しい案件', fn: function () { $('#bt-new').click(); } };
    if (state.step === 'intake') {
      return j.facts ? { label: '観点とケース表を作る →', fn: function () { $('#bt-make-cases').click(); } }
        : { label: '読み取る', fn: function () { $('#bt-analyze').click(); }, off: !j.files.some(function (f) { return f.kind === 'script'; }) };
    }
    if (state.step === 'cases') return { label: 'テストコードを生成 →', fn: function () { $('#bt-make-code').click(); }, off: !j.cases.length };
    if (state.step === 'code') return { label: '書き出しへ →', fn: function () { go('export'); }, off: !j.sources.length };
    return { label: 'ケース表を書き出す', fn: function () { $('#bt-dl-cases').click(); }, off: !j.cases.length };
  }
  var headFn = null;
  function renderHead() {
    var j = state.job, a = headAction(), b = $('#bt-head-primary');
    b.textContent = a.label; b.disabled = !!a.off; headFn = a.fn;
    var st = $('#bt-head-state');
    if (!j) { st.innerHTML = W ? W.status.html('not_started', '案件を選んでいません') : ''; }
    else {
      var g = stages(j), cur = g[3].code === 'done' ? g[3] : g[2].code === 'done' ? g[2] : g[1].label.indexOf('書き出し済み') === 0 ? g[1] : g[0];
      st.innerHTML = W ? W.status.html(cur.code, cur.label) + ' <span class="bt-mut">' + esc(j.name) + '</span>' : esc(cur.label);
    }
    renderStages(); renderReason();
  }
  function renderReason() {
    var j = state.job, host = $('#bt-reason'), msg, kind;
    if (!j) { msg = '案件が選ばれていません。左の一覧から選ぶか、「＋ 新しい案件」で作ってください。'; }
    else if (!j.files.length) { msg = 'ファイルが取り込まれていません。スクリプトを 1 本取り込むと読み取れます。'; }
    else if (!j.facts) { msg = 'スクリプトを取り込みました。「読み取る」で引数・終了コード・入出力を取り出します。'; }
    else if (!j.cases.length) { msg = '読み取り済みです。「観点とケース表を作る」でケースを生成します。'; }
    else if (!j.sources.length) { msg = 'ケースを ' + j.cases.length + ' 件生成しました（未実行）。テストコードはまだありません。'; }
    else if (exportedKinds(j).length) { msg = '書き出し済み（未実行）です。この画面では実行していないので、実行済み・確認済みとは扱いません。'; kind = 'warning'; }
    else { msg = '生成済み（未実行）です。実行結果が無いため、合否は出していません。書き出して手元の環境で実行してください。'; }
    if (state.notice[failHostId()]) { msg = '直前の操作が失敗しました。既存の結果は保持しています。画面内の案内に従ってください。'; kind = 'error'; }
    if (W) W.reason(host, msg, kind); else host.textContent = msg;
  }
  function failHostId() { return ({ intake: 'bt-intake-state', cases: 'bt-cases-state', code: 'bt-code-state', export: 'bt-export-state' })[state.step]; }

  function renderIntake() {
    var j = state.job;
    $('#bt-files').innerHTML = j.files.length ? j.files.map(function (f) {
      var opts = Object.keys(KINDS).map(function (k) {
        return '<option value="' + k + '"' + (k === f.kind ? ' selected' : '') + '>' + KINDS[k] + '</option>';
      }).join('');
      return '<tr><td><code>' + esc(f.name) + '</code></td><td><select data-kind="' + esc(f.name) + '" aria-label="' + esc(f.name) + ' の種類">' + opts + '</select></td><td>'
        + fmtSize(f.size) + '</td><td><button type="button" class="bt-x" data-delfile="' + esc(f.name) + '" aria-label="' + esc(f.name) + ' を外す" title="外す">✕</button></td></tr>';
    }).join('') : '';
    $('#bt-files-tbl').hidden = !j.files.length;
    paintNotice('bt-intake-state', j.files.length ? null : {
      kind: 'empty', title: 'ファイルがまだ選ばれていません',
      message: 'スクリプトが 1 本あれば読み取れます。仕様書や入出力のサンプルがあれば、根拠の照合に使います。',
      next: '上の枠にファイルを落とすか、押して選んでください。', actionLabel: 'ファイルを選ぶ', onAction: function () { $('#bt-file').click(); }
    });
    $('#bt-env').value = j.settings.env; $('#bt-fw').value = j.settings.framework; $('#bt-cmd').value = j.settings.command;
    var f = j.facts;
    $('#bt-facts-pill').textContent = f ? '読み取り済み · ' + fmtTime(j.analyzed_at) : '未読み取り';
    $('#bt-facts-pill').className = 'pill p-new';
    $('#bt-analyze').textContent = f ? '読み取り直す' : '読み取る';
    if (!f) { $('#bt-facts').innerHTML = '<p class="bt-none">スクリプトを取り込んで「読み取る」を押すと、引数・終了コード・入出力・環境変数がここに並びます。</p>'; }
    else {
      var li = function (a, b) { return '<li><code>' + esc(a) + '</code><small>' + esc(b) + '</small></li>'; };
      var none = '<li><small>見つかりません</small></li>';
      var groups = [
        ['引数', f.args.map(function (a) { return li(a.name, (a.required ? '必須' : '任意') + (a.format ? '・' + a.format.toUpperCase() : '') + (a.line ? '・' + a.line + ' 行' : '')); })
          .concat(f.flags.map(function (x) { return li(x.name, 'フラグ・' + x.line + ' 行'); }))],
        ['終了コード', f.exit_codes.map(function (c) { return li(c.code, c.meanings.map(function (m) { return m.text || '（文言なし）'; }).join(' / ')); })],
        ['入出力', f.inputs.map(function (x) { return li(x.path, '読む・' + x.line + ' 行'); })
          .concat(f.outputs.map(function (x) { return li(x.path, '書く・' + x.line + ' 行'); }))
          .concat(f.logs.map(function (x) { return li(x.path, 'ログ・' + x.line + ' 行'); }))],
        ['環境変数・前提', f.env_vars.map(function (e) { return li(e.name, (e.required ? '必須' : '参照') + '・' + e.line + ' 行'); })
          .concat(f.lock ? [li(f.lock.path, '二重起動の防止・' + f.lock.line + ' 行')] : [])]
      ];
      $('#bt-facts').innerHTML = groups.map(function (g) {
        return '<div class="bt-fact"><h4>' + g[0] + '</h4><ul>' + (g[1].join('') || none) + '</ul></div>';
      }).join('');
    }
    var specN = j.spec.length;
    $('#bt-intake-note').textContent = f ? '仕様書から ' + specN + ' 文を読み取りました。根拠の照合に使います。' : '';
    $('#bt-make-cases').disabled = !f;
    $('#bt-analyze').disabled = !j.files.some(function (x) { return x.kind === 'script'; });
  }

  function renderCases() {
    var all = state.job.cases, ask = all.filter(function (c) { return c.ask; }).length;
    var obsList = [];
    all.forEach(function (c) { if (obsList.indexOf(c.obs) < 0) obsList.push(c.obs); });
    if (state.obs && obsList.indexOf(state.obs) < 0) state.obs = '';
    var kpi = function (v, l, cls) { return '<div class="kpi' + (cls ? ' ' + cls : '') + '"><b>' + esc(v) + '</b><span>' + esc(l) + '</span></div>'; };
    $('#bt-kpis').innerHTML = kpi(all.length, '生成したケース数') + kpi(obsList.length, '観点') + kpi(ask, '要確認（仕様に記載なし）', ask ? 'wa' : '') + kpi(all.length - ask, '根拠つき（生成済み）') + kpi('未実行', '合格／失敗（実行結果を取り込むと表示）', 'nr');
    $('#bt-obs').innerHTML = all.length ? ['すべて'].concat(obsList).map(function (o) {
      var key = o === 'すべて' ? '' : o, n = key ? all.filter(function (c) { return c.obs === key; }).length : all.length;
      return '<span class="fchip' + (state.obs === key ? ' on' : '') + '" role="button" tabindex="0" aria-pressed="' + (state.obs === key) + '" data-obs="' + esc(key) + '">' + esc(o) + ' <em>' + n + '</em></span>';
    }).join('') : '<span class="bt-none">ケースを作ると観点が並びます。</span>';
    var rows = all.filter(function (c) { return !state.obs || c.obs === state.obs; });
    $('#bt-shown').textContent = rows.length + ' / ' + all.length + ' 件';
    $('#bt-rows').innerHTML = rows.length ? rows.map(function (c) {
      var exp = esc(c.exp);
      if (c.ask) {
        exp += state.editing === c.id
          ? '<form class="bt-edit" data-editform="' + esc(c.id) + '"><input name="exp" maxlength="300" placeholder="期待結果" aria-label="' + esc(c.id) + ' の期待結果" required><input name="code" maxlength="3" inputmode="numeric" placeholder="終了コード" aria-label="' + esc(c.id) + ' の終了コード"><button type="submit" class="btn sm pri">決める</button></form>'
          : '<div><button type="button" class="btn sm ghost" data-edit="' + esc(c.id) + '">期待結果を書く</button></div>';
      }
      return '<tr class="' + (c.ask ? 'ask' : '') + '"><td>' + esc(c.id) + '</td><td>' + esc(c.obs) + '</td><td>' + esc(c.tech) + '</td><td>' + esc(c.pre)
        + '</td><td><code>' + esc(c.run) + '</code></td><td>' + exp + '</td><td>' + esc(c.src) + '</td><td>'
        + (c.ask ? '<span class="pill p-flaky">要確認</span>' : '<span class="pill p-new">' + (c.origin === 'manual' ? '追加' : '根拠あり') + '・未実行</span>') + '</td></tr>';
    }).join('') : '<tr><td colspan="8" class="bt-none">ケースはまだありません。「取り込み」で読み取ってから「観点とケース表を作る」を押してください。</td></tr>';
    $('#bt-ask-note').textContent = ask ? '要確認の ' + ask + ' 件は期待結果を推測で埋めていません。「期待結果を書く」で決めるか、質問票で確かめてください。' : '';
    var bd = $('#bt-bd-ask'); bd.textContent = ask; bd.hidden = !ask;
    $('#bt-make-code').disabled = !all.length;
    paintNotice('bt-cases-state', null);
  }

  function renderCode() {
    var srcs = state.job.sources;
    $('#bt-srcs').innerHTML = srcs.length ? srcs.map(function (s, i) {
      return '<div class="it' + (i === state.src ? ' on' : '') + '" role="listitem"><button type="button" class="it-main" data-src="' + i + '"><i class="i-new"></i>'
        + '<span class="grow"><b>' + esc(s.name) + '</b><small>生成済み（未実行）</small><small>' + esc(s.map) + '</small></span></button></div>';
    }).join('') : '<div class="it empty">まだ生成していません</div>';
    var s = srcs[state.src];
    $('#bt-src-name').textContent = s ? s.name : 'テストコード';
    $('#bt-src-map').textContent = s ? s.map : '';
    $('#bt-src').textContent = s ? s.body : 'ケース表で「テストコードを生成」を押すと、ここにコードが出ます。';
    $('#bt-code-wrap').hidden = !srcs.length;
    paintNotice('bt-code-state', srcs.length ? null : {
      kind: 'empty', title: 'テストコードはまだ生成していません',
      message: 'ケース表ができていれば、ケース 1 件につきテスト 1 つを生成します。',
      next: state.job.cases.length ? '「テストコードを生成」を押してください。' : '先に「取り込み」から観点とケース表を作ってください。',
      actionLabel: state.job.cases.length ? 'テストコードを生成' : '取り込みへ', onAction: function () { if (state.job.cases.length) $('#bt-make-code').click(); else go('intake'); }
    });
  }

  function renderExport() {
    var j = state.job, base = API + '/' + j.id + '/export/';
    var ask = j.cases.filter(function (c) { return c.ask; });
    var set = function (sel, href, ok) { var a = $(sel); a.href = ok ? href : '#'; a.setAttribute('aria-disabled', String(!ok)); };
    set('#bt-dl-cases', base + 'cases.xlsx', j.cases.length > 0);
    set('#bt-dl-code', base + 'code.zip', j.sources.length > 0);
    set('#bt-dl-q', base + 'questions.csv', ask.length > 0);
    var checks = [];
    checks.push(ask.length ? '要確認が ' + ask.length + ' 件残っています（' + ask.map(function (c) { return c.id; }).join('・') + '）。期待結果を書くか、質問票で確かめてください。' : '要確認のケースはありません。');
    checks.push(j.sources.length ? 'テストコードは生成済み（未実行）です。この画面では実行していません。お使いの環境で 1 回実行して確かめてください。' : 'テストコードがまだありません。「テストコード」で生成してください。');
    checks.push('入力サンプルに個人情報が含まれていないか確かめてから渡してください。');
    var ex = exportedKinds(j);
    if (ex.length) checks.push('書き出し済み（未実行）: ' + ex.map(function (k) { return EXPORT_NAME[k]; }).join('・') + '。書き出しただけで、実行・確認はしていません。この記録はこの画面の操作中だけで、リロード後は未確認に戻ります。');
    paintNotice('bt-export-state', !j.cases.length && !j.sources.length ? {
      kind: 'unavailable', title: '書き出せるものがありません', message: 'ケース表もテストコードもまだ生成していません。',
      next: '「取り込み」で読み取り、観点とケース表を作ってください。', actionLabel: '取り込みへ', onAction: function () { go('intake'); }
    } : ex.length ? {
      kind: 'unverified', title: '書き出し済み（未実行）',
      message: ex.map(function (k) { return EXPORT_NAME[k]; }).join('・') + ' を書き出しました。実行も確認もしていません。この記録はこの画面の操作中だけで、リロード後は未確認に戻ります。',
      next: 'お使いの環境でテストコードを 1 回実行し、結果を確かめてください。'
    } : null);
    $('#bt-checks').innerHTML = checks.map(function (c) { return '<li>' + esc(c) + '</li>'; }).join('');
  }

  function renderAll() {
    renderJobs(); renderSteps();
    if (!state.job) return;
    renderIntake(); renderCases(); renderCode(); renderExport();
  }

  function go(step, noPush) {
    if (!STEPS.some(function (s) { return s.id === step; })) step = 'intake';
    state.step = step;
    syncUrl(!noPush);
    renderSteps();
    $('#bt-content').scrollTop = 0;
  }

  /* 取り込み前の検査: 非対応形式・空・20MB 超はここで止め、取り込める分だけ送る */
  function upload(files) {
    if (!state.job) return;
    if (!files || !files.length) {
      notice('bt-intake-state', { kind: 'empty', title: 'ファイルが選ばれていません', message: 'ファイルが選ばれないまま閉じられました。',
        next: '枠を押してスクリプトを 1 本選んでください。', actionLabel: 'ファイルを選ぶ', onAction: function () { $('#bt-file').click(); } });
      renderReason(); return;
    }
    var okFiles = [], bad = [];
    Array.prototype.forEach.call(files, function (f) {
      var ext = (f.name.lastIndexOf('.') >= 0 ? f.name.slice(f.name.lastIndexOf('.')) : '').toLowerCase();
      if (OK_EXT.indexOf(ext) < 0) bad.push(f.name + '（' + (ext || '拡張子なし') + ' は非対応）');
      else if (!f.size) bad.push(f.name + '（空のファイル）');
      else if (f.size > MAX_BYTES) bad.push(f.name + '（20MB 超）');
      else okFiles.push(f);
    });
    if (bad.length) {
      notice('bt-intake-state', {
        kind: okFiles.length ? 'partial' : 'unavailable', title: okFiles.length ? '一部のファイルは取り込めません' : '取り込めない形式です',
        message: bad.join(' / '), retained: true,
        next: '取り込めるのは .bat .cmd .sh .ps1（スクリプト）、.xlsx .docx .md .txt .pdf（仕様書）、.csv .txt（サンプル）です。' + (okFiles.length ? '取り込める ' + okFiles.length + ' 件は続けて取り込みます。' : '対応形式のファイルを選び直してください。')
      });
      renderReason();
    }
    if (!okFiles.length) return;
    var fd = new FormData();
    okFiles.forEach(function (f) { fd.append('files', f); });
    var warn = bad.length ? state.notice['bt-intake-state'] : null;
    run($('#bt-drop'), api('POST', API + '/' + state.job.id + '/files', fd), okFiles.length + ' ファイルを取り込みました', 'ファイルを取り込めませんでした', '別のファイルで試すか、ファイルの中身を確かめてください。')
      .then(function () { if (warn) notice('bt-intake-state', warn); });
  }

  /* 書き出し: fetch で取得して成否を見てから保存する（失敗したのに「書き出し済み」にしない） */
  function exportFile(a) {
    var j = state.job, kind = a.id === 'bt-dl-cases' ? 'cases.xlsx' : a.id === 'bt-dl-code' ? 'code.zip' : 'questions.csv';
    if (!j || a.getAttribute('aria-disabled') === 'true') return;
    banner(''); a.classList.add('bt-busy');
    var fail = function (msg) {
      notice('bt-export-state', { kind: 'error', title: EXPORT_NAME[kind] + 'を書き出せませんでした', message: msg, retained: true,
        next: '内容は保持しています。もう一度押してください。続くときはケース表・テストコードを作り直してください。',
        actionLabel: '再試行', onAction: function () { a.click(); } });
      renderReason();
    };
    fetch(API + '/' + j.id + '/export/' + kind).then(function (r) {
      if (!r.ok) return r.json().catch(function () { return {}; }).then(function (d) { throw new Error(d.error || '書き出せませんでした（' + r.status + '）。'); });
      var m = /filename="?([^";]+)"?/.exec(r.headers.get('Content-Disposition') || '');
      return r.blob().then(function (b) { return { b: b, name: m ? m[1] : kind }; });
    }).then(function (x) {
      var u = URL.createObjectURL(x.b), l = document.createElement('a');
      l.href = u; l.download = x.name; document.body.appendChild(l); l.click(); l.remove();
      setTimeout(function () { URL.revokeObjectURL(u); }, 1000);
      delete state.notice['bt-export-state'];
      (state.exported[j.id] = state.exported[j.id] || {})[kind] = Date.now();
      renderExport(); renderHead();
      toast(EXPORT_NAME[kind] + 'を書き出しました（未実行）', 'success');
    }).catch(function (e) { fail(e instanceof TypeError ? 'サーバにつながりません。通信を確かめてください。' : e.message); })
      .then(function () { a.classList.remove('bt-busy'); });
  }

  /* ---- 操作 ---- */
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-go],[data-step],[data-obs],[data-src],[data-job],[data-deljob],[data-delfile],[data-edit],#bt-new,#bt-newcancel,#bt-analyze,#bt-make-cases,#bt-redesign,#bt-make-code,#bt-add-open,#bt-add-cancel,#bt-dl-cases,#bt-dl-code,#bt-dl-q');
    if (!t || t.disabled) return;
    var j = state.job;
    if (t.id && t.id.indexOf('bt-dl-') === 0) { e.preventDefault(); return exportFile(t); }
    if (t.dataset.go || t.dataset.step) return go(t.dataset.go || t.dataset.step);
    if (t.hasAttribute('data-obs')) { state.obs = t.dataset.obs; return renderCases(); }
    if (t.dataset.src) { state.src = +t.dataset.src; return renderCode(); }
    if (t.dataset.job) return openJob(t.dataset.job);
    if (t.dataset.edit) { state.editing = t.dataset.edit; renderCases(); var i = document.querySelector('[data-editform] input'); if (i) i.focus(); return; }
    if (t.dataset.deljob) {
      var delId = t.dataset.deljob, delJob = state.jobs.filter(function (x) { return x.id === delId; })[0] || {};
      var askDel = W && W.confirm ? W.confirm({
        title: '案件を削除しますか', message: '「' + (delJob.name || '') + '」を削除します。',
        detail: '取り込んだファイル・ケース表・生成したテストコードがすべて消え、元に戻せません。書き出し済みのファイルは影響を受けません。',
        confirmLabel: '削除する', danger: true
      }) : Promise.resolve(true);
      return askDel.then(function (ok) {
        if (!ok) return;
        return api('DELETE', API + '/' + delId).then(function () {
          state.jobs = state.jobs.filter(function (x) { return x.id !== delId; });
          delete state.exported[delId];
          if (j && j.id === delId) { state.job = null; history.replaceState(null, '', location.pathname); }
          renderAll(); toast('案件を削除しました');
        }).catch(function (er) { banner(er.message); });
      });
    }
    if (t.dataset.delfile) {
      var fname = t.dataset.delfile, dependent = j.facts || j.cases.length || j.sources.length;
      var ask = W && W.confirm ? W.confirm({
        title: 'ファイルを外しますか', message: '「' + fname + '」をこの案件から外します。',
        detail: '取り込んだファイルは案件から削除され、元に戻せません（必要なら取り込み直してください）。'
          + (dependent ? ' 読み取り済みの内容とケース・コードは残りますが、外したファイルとは一致しなくなります。' : ''),
        confirmLabel: '外す', danger: true
      }) : Promise.resolve(true);
      return ask.then(function (ok) {
        if (ok) return run(t, api('DELETE', API + '/' + j.id + '/files/' + encodeURIComponent(fname)), 'ファイルを外しました', 'ファイルを外せませんでした', '一覧を再読み込みしてからもう一度お試しください。');
        toast('ファイルは外していません', 'info');
      });
    }
    switch (t.id) {
      case 'bt-new': $('#bt-newform').hidden = false; $('#bt-newname').focus(); return;
      case 'bt-newcancel': $('#bt-newform').hidden = true; return;
      case 'bt-analyze':
        return run(t, api('POST', API + '/' + j.id + '/analyze'), '読み取りました', '読み取れませんでした', 'スクリプトの種類が「スクリプト」になっているか確かめてください。').then(function (d) {
          if (d && d.notes && d.notes.length) banner('仕様書の一部を読めませんでした: ' + d.notes.join(' / '));
        });
      case 'bt-make-cases': case 'bt-redesign':
        return run(t, api('POST', API + '/' + j.id + '/cases'), 'ケース表を作りました', 'ケース表を生成できませんでした', '先に「読み取る」を実行したか確かめ、もう一度押してください。').then(function (d) { if (d && d.job) go('cases'); });
      case 'bt-make-code':
        return run(t, api('POST', API + '/' + j.id + '/code'), 'テストコードを生成しました', 'テストコードを生成できませんでした', '実行環境とテストコードの種類の組み合わせを確かめ、もう一度押してください。').then(function (d) { if (d && d.job) go('code'); });
      case 'bt-add-open': $('#bt-addform').hidden = false; $('#bt-addform [name=pre]').focus(); return;
      case 'bt-add-cancel': $('#bt-addform').hidden = true; return;
    }
  });

  document.addEventListener('submit', function (e) {
    var f = e.target, j = state.job;
    e.preventDefault();
    if (f.id === 'bt-newform') {
      var name = $('#bt-newname').value.trim();
      if (!name) return;
      return run(f.querySelector('button'), api('POST', API, { name: name }), '案件を作りました').then(function (d) {
        if (d && d.job) { f.hidden = true; $('#bt-newname').value = ''; go('intake', true); state.job = d.job; syncUrl(true); }
      });
    }
    if (f.id === 'bt-addform') {
      var body = { obs: f.obs.value, pre: f.pre.value, args: f.args.value, exp: f.exp.value, code: f.code.value };
      return run(f.querySelector('[type=submit]'), api('POST', API + '/' + j.id + '/cases/add', body), 'ケースを追加しました').then(function (d) {
        if (d && d.job) { f.reset(); f.hidden = true; }
      });
    }
    if (f.dataset.editform) {
      return run(f.querySelector('button'), api('PATCH', API + '/' + j.id + '/cases/' + f.dataset.editform, { exp: f.exp.value, code: f.code.value }), '期待結果を決めました')
        .then(function (d) { if (d && d.job) { state.editing = ''; renderCases(); } });
    }
  });

  document.addEventListener('change', function (e) {
    var t = e.target, j = state.job;
    if (!j) return;
    if (t.id === 'bt-file') { upload(t.files); t.value = ''; return; }
    if (t.dataset.kind) return run(null, api('PATCH', API + '/' + j.id + '/files/' + encodeURIComponent(t.dataset.kind), { kind: t.value }), '種類を変えました');
    var key = { 'bt-env': 'env', 'bt-fw': 'framework', 'bt-cmd': 'command' }[t.id];
    if (key) { var b = {}; b[key] = t.value; run(null, api('PATCH', API + '/' + j.id, b), '保存しました'); }
  });
  document.addEventListener('keydown', function (e) {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('[data-obs]')) { e.preventDefault(); e.target.click(); }
  });
  /* 状態の語彙: 生成済み（未実行）／書き出し済み（未実行）／実行済み（結果あり）／確認済み。この画面は実行しない */
  (function () {
    var host = $('#bt-content');
    if (!host || $('#bt-truth')) return;
    var n = document.createElement('p');
    n.id = 'bt-truth'; n.className = 'bt-truth';
    n.textContent = 'この画面ではテストを実行しません。生成・書き出しまでです。実行結果は取り込むまで表示しません。';
    host.insertBefore(n, host.firstChild);
  })();
  var drop = $('#bt-drop');
  ['dragenter', 'dragover'].forEach(function (n) { drop.addEventListener(n, function (e) { e.preventDefault(); drop.classList.add('over'); }); });
  ['dragleave', 'drop'].forEach(function (n) { drop.addEventListener(n, function (e) { e.preventDefault(); drop.classList.remove('over'); }); });
  drop.addEventListener('drop', function (e) { upload(e.dataTransfer.files); });
  $('#bt-q').addEventListener('input', renderJobs);
  $('#bt-head-primary').addEventListener('click', function () { if (headFn) headFn(); });
  /* 戻る・進む・手入力のハッシュ変更。URL の案件と段階へ画面を合わせる */
  function restore() {
    var step = location.hash.slice(1);
    state.step = STEPS.some(function (s) { return s.id === step; }) ? step : 'intake';
    var id = new URLSearchParams(location.search).get('job');
    if (id && (!state.job || state.job.id !== id)) return openJob(id, true);
    if (!id && state.job) { state.job = null; renderAll(); }
    go(state.step, true);
  }
  window.addEventListener('popstate', restore);

  var h0 = location.hash.slice(1);
  state.step = STEPS.some(function (s) { return s.id === h0; }) ? h0 : 'intake';
  var jid = new URLSearchParams(location.search).get('job');
  loadJobs().then(function () {
    if (jid) return openJob(jid, true);
    renderAll();
  });
})();
