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
  var state = { jobs: [], job: null, step: 'intake', obs: '', src: 0, editing: '' };

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
  function toast(msg) {
    var t = $('#bt-toast'); t.textContent = msg; t.hidden = false;
    clearTimeout(toast.id); toast.id = setTimeout(function () { t.hidden = true; }, 3000);
  }
  function busy(el, on) { if (el) { el.classList.toggle('bt-busy', on); el.disabled = on; } }
  function run(el, p, okMsg) {
    banner(''); busy(el, true);
    return p.then(function (d) { if (d.job) setJob(d.job); if (okMsg) toast(okMsg); return d; })
      .catch(function (e) { banner(e.message); })
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
  }

  function renderIntake() {
    var j = state.job;
    $('#bt-files').innerHTML = j.files.length ? j.files.map(function (f) {
      var opts = Object.keys(KINDS).map(function (k) {
        return '<option value="' + k + '"' + (k === f.kind ? ' selected' : '') + '>' + KINDS[k] + '</option>';
      }).join('');
      return '<tr><td><code>' + esc(f.name) + '</code></td><td><select data-kind="' + esc(f.name) + '" aria-label="' + esc(f.name) + ' の種類">' + opts + '</select></td><td>'
        + fmtSize(f.size) + '</td><td><button type="button" class="bt-x" data-delfile="' + esc(f.name) + '" aria-label="' + esc(f.name) + ' を外す" title="外す">✕</button></td></tr>';
    }).join('') : '<tr><td colspan="4" class="bt-none">まだ何も取り込んでいません。スクリプトを 1 本と、あれば仕様書・入出力のサンプルを取り込んでください。</td></tr>';
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

  function upload(files) {
    if (!files || !files.length || !state.job) return;
    var fd = new FormData();
    Array.prototype.forEach.call(files, function (f) { fd.append('files', f); });
    run($('#bt-drop'), api('POST', API + '/' + state.job.id + '/files', fd), files.length + ' ファイルを取り込みました');
  }

  /* ---- 操作 ---- */
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-go],[data-step],[data-obs],[data-src],[data-job],[data-deljob],[data-delfile],[data-edit],#bt-new,#bt-newcancel,#bt-analyze,#bt-make-cases,#bt-redesign,#bt-make-code,#bt-add-open,#bt-add-cancel');
    if (!t || t.disabled) return;
    var j = state.job;
    if (t.dataset.go || t.dataset.step) return go(t.dataset.go || t.dataset.step);
    if (t.hasAttribute('data-obs')) { state.obs = t.dataset.obs; return renderCases(); }
    if (t.dataset.src) { state.src = +t.dataset.src; return renderCode(); }
    if (t.dataset.job) return openJob(t.dataset.job);
    if (t.dataset.edit) { state.editing = t.dataset.edit; renderCases(); var i = document.querySelector('[data-editform] input'); if (i) i.focus(); return; }
    if (t.dataset.deljob) {
      if (t.dataset.armed !== '1') { t.dataset.armed = '1'; t.textContent = '削除'; toast('もう一度押すと削除します'); return; }
      return api('DELETE', API + '/' + t.dataset.deljob).then(function () {
        state.jobs = state.jobs.filter(function (x) { return x.id !== t.dataset.deljob; });
        if (j && j.id === t.dataset.deljob) { state.job = null; history.replaceState(null, '', location.pathname); }
        renderAll(); toast('案件を削除しました');
      }).catch(function (er) { banner(er.message); });
    }
    if (t.dataset.delfile) return run(t, api('DELETE', API + '/' + j.id + '/files/' + encodeURIComponent(t.dataset.delfile)), 'ファイルを外しました');
    switch (t.id) {
      case 'bt-new': $('#bt-newform').hidden = false; $('#bt-newname').focus(); return;
      case 'bt-newcancel': $('#bt-newform').hidden = true; return;
      case 'bt-analyze':
        return run(t, api('POST', API + '/' + j.id + '/analyze'), '読み取りました').then(function (d) {
          if (d && d.notes && d.notes.length) banner('仕様書の一部を読めませんでした: ' + d.notes.join(' / '));
        });
      case 'bt-make-cases': case 'bt-redesign':
        return run(t, api('POST', API + '/' + j.id + '/cases'), 'ケース表を作りました').then(function (d) { if (d && d.job) go('cases'); });
      case 'bt-make-code':
        return run(t, api('POST', API + '/' + j.id + '/code'), 'テストコードを生成しました').then(function (d) { if (d && d.job) go('code'); });
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
