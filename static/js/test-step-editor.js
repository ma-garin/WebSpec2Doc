// ステップ編集（ノーコード）。テスト活動支援 / 実装画面。
//
// 生成された .spec.ts を直接編集させない。編集の正本はステップ列で、
// コードは常にそこから生成する（生成物を直すと再生成のたびに消えるため）。
//
// 動作の語彙はサーバ（/api/test-steps/actions）から取る。画面側にも定義を持つと、
// 片方だけ増えたときに「選べるのに保存できない」が起きる。
(function () {
  'use strict';

  var state = { domain: '', doc: null, actions: [], dirty: false, jobId: '', pollTimer: null };

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function spec(action) {
    for (var i = 0; i < state.actions.length; i++) {
      if (state.actions[i].action === action) return state.actions[i];
    }
    return { action: action, label: action, needs_target: true, needs_value: true };
  }

  function message(text, ok) {
    var el = $('ns-message');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'ns-message ' + (text ? (ok ? 'ns-ok' : 'ns-ng') : '');
    el.hidden = !text;
  }

  function newId(prefix) {
    return prefix + Math.random().toString(36).slice(2, 8);
  }

  // ---- 描画 -------------------------------------------------------------
  function render() {
    var host = $('ns-tests');
    if (!host) return;
    var tests = (state.doc && state.doc.tests) || [];
    if (!tests.length) {
      host.innerHTML = '<p class="ns-empty">まだテストがありません。'
        + '「解析結果から取り込む」で叩き台を作るか、「＋ テストを追加」で始めてください。</p>';
      return;
    }
    host.innerHTML = tests.map(renderTest).join('');
  }

  function renderTest(test, ti) {
    var steps = test.steps || [];
    return '<div class="ns-test' + (test.enabled === false ? ' is-off' : '') + '" data-ti="' + ti + '">'
      + '<div class="ns-test-head">'
      + '<input class="ns-input ns-test-title" data-f="title" value="' + esc(test.title) + '" aria-label="テスト名">'
      + '<span class="ns-id">' + esc(test.test_id) + '</span>'
      + '<label class="ns-label"><input type="checkbox" data-f="enabled"'
      + (test.enabled === false ? '' : ' checked') + '> 有効</label>'
      + '<button type="button" class="ns-mini ns-mini-danger" data-op="del-test">テストを削除</button>'
      + '</div>'
      + '<div class="ns-steps-wrap"><table class="ns-steps"><thead><tr>'
      + '<th class="ns-col-n">#</th><th class="ns-col-act">動作</th><th>対象（複数可・改行区切り）</th>'
      + '<th>値</th><th>メモ</th><th class="ns-col-ops">操作</th>'
      + '</tr></thead><tbody>'
      + steps.map(function (s, si) { return renderStep(s, si, steps.length); }).join('')
      + '</tbody></table></div>'
      + '<div class="ns-foot"><button type="button" class="ns-mini" data-op="add-step">＋ ステップを追加</button></div>'
      + '</div>';
  }

  function renderStep(step, si, total) {
    var sp = spec(step.action);
    var options = state.actions.map(function (a) {
      return '<option value="' + esc(a.action) + '"' + (a.action === step.action ? ' selected' : '') + '>'
        + esc(a.label) + '</option>';
    }).join('');
    // 対象・値が要らない動作では入力欄を無効にする。押せるのに保存で弾かれるより、
    // 最初から入れられない方が分かる。
    return '<tr data-si="' + si + '">'
      + '<td class="ns-col-n">' + (si + 1) + '</td>'
      + '<td><select class="ns-select" data-f="action">' + options + '</select></td>'
      + '<td><textarea class="ns-input" rows="1" data-f="target"'
      + (sp.needs_target ? '' : ' disabled') + '>' + esc((step.target || []).join('\n')) + '</textarea></td>'
      + '<td><input class="ns-input" data-f="value" value="' + esc(step.value) + '"'
      + (sp.needs_value ? '' : ' disabled') + '></td>'
      + '<td><input class="ns-input" data-f="label" value="' + esc(step.label) + '"></td>'
      + '<td class="ns-col-ops">'
      + '<button type="button" class="ns-mini" data-op="up"' + (si === 0 ? ' disabled' : '') + '>↑</button> '
      + '<button type="button" class="ns-mini" data-op="down"' + (si === total - 1 ? ' disabled' : '') + '>↓</button> '
      + '<button type="button" class="ns-mini ns-mini-danger" data-op="del-step">削除</button>'
      + '</td></tr>';
  }

  // ---- 編集 -------------------------------------------------------------
  function testAt(el) {
    var box = el.closest('.ns-test');
    return box ? state.doc.tests[parseInt(box.dataset.ti, 10)] : null;
  }
  function stepAt(el) {
    var test = testAt(el);
    var row = el.closest('tr[data-si]');
    return test && row ? test.steps[parseInt(row.dataset.si, 10)] : null;
  }

  function onInput(ev) {
    var el = ev.target;
    var field = el.dataset.f;
    if (!field || !state.doc) return;
    var step = stepAt(el);
    if (step) {
      if (field === 'target') {
        step.target = el.value.split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
      } else {
        step[field] = el.value;
      }
      if (field === 'action') { state.dirty = true; render(); return; }
    } else {
      var test = testAt(el);
      if (!test) return;
      if (field === 'enabled') { test.enabled = el.checked; render(); }
      else test[field] = el.value;
    }
    state.dirty = true;
  }

  function onClick(ev) {
    var el = ev.target.closest('[data-op]');
    if (!el || !state.doc) return;
    var op = el.dataset.op;
    var test = testAt(el);
    var row = el.closest('tr[data-si]');
    var si = row ? parseInt(row.dataset.si, 10) : -1;

    if (op === 'add-step' && test) {
      test.steps.push({ id: newId('s'), action: 'click', target: [], value: '', label: '', note: '' });
    } else if (op === 'del-step' && test) {
      if (test.steps.length <= 1) { message('ステップは 1 つ以上必要です。', false); return; }
      test.steps.splice(si, 1);
    } else if (op === 'up' && test && si > 0) {
      test.steps.splice(si - 1, 0, test.steps.splice(si, 1)[0]);
    } else if (op === 'down' && test && si < test.steps.length - 1) {
      test.steps.splice(si + 1, 0, test.steps.splice(si, 1)[0]);
    } else if (op === 'del-test' && test) {
      state.doc.tests.splice(state.doc.tests.indexOf(test), 1);
    } else {
      return;
    }
    state.dirty = true;
    render();
  }

  // ---- サーバとのやり取り ------------------------------------------------
  async function loadActions() {
    try {
      var res = await fetch('/api/test-steps/actions');
      if (!res.ok) return;
      state.actions = (await res.json()).actions || [];
    } catch (e) { /* 語彙が取れなければ描画時に既定へ倒す */ }
  }

  async function loadDoc() {
    if (!state.domain) { state.doc = { version: 1, domain: '', tests: [] }; render(); return; }
    try {
      var res = await fetch('/api/test-steps/' + encodeURIComponent(state.domain));
      var data = await res.json();
      if (!res.ok) { message(data.error || '取得に失敗しました。', false); return; }
      state.doc = data.document;
      state.dirty = false;
      message(data.saved ? '' : 'このサイトのステップはまだ保存されていません。', true);
      render();
    } catch (e) {
      message('取得に失敗しました: ' + e.message, false);
    }
  }

  async function doImport() {
    if (!state.domain) return;
    if (state.dirty && !window.confirm('未保存の編集を取り込み結果で置き換えます。よろしいですか？')) return;
    try {
      var res = await fetch('/api/test-steps/' + encodeURIComponent(state.domain) + '/import', { method: 'POST' });
      var data = await res.json();
      if (!res.ok) { message(data.error || '取り込めませんでした。', false); return; }
      state.doc = data.document;
      state.dirty = true;
      render();
      message(data.tests + ' 件を取り込みました。内容を確認して保存してください（まだ保存されていません）。', true);
    } catch (e) {
      message('取り込みに失敗しました: ' + e.message, false);
    }
  }

  async function doSave() {
    if (!state.domain || !state.doc) return;
    try {
      var res = await fetch('/api/test-steps/' + encodeURIComponent(state.domain), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(state.doc)
      });
      var data = await res.json();
      if (!res.ok) { message('保存できません: ' + (data.error || res.status), false); return; }
      state.dirty = false;
      message('保存しました（' + data.tests + ' 件）。', true);
    } catch (e) {
      message('保存に失敗しました: ' + e.message, false);
    }
  }

  async function doGenerate() {
    if (!state.domain) return;
    if (state.dirty) { message('先に保存してください。生成は保存済みのステップから行います。', false); return; }
    try {
      var res = await fetch('/api/test-steps/' + encodeURIComponent(state.domain) + '/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ self_healing: true })
      });
      var data = await res.json();
      if (!res.ok) { message('生成できません: ' + (data.error || res.status), false); return; }
      $('ns-code').textContent = data.preview || '';
      $('ns-preview-meta').textContent = '（' + data.tests + ' 件・' + data.lines + ' 行'
        + (data.skipped ? '・無効 ' + data.skipped + ' 件は除外' : '') + '）';
      $('ns-preview').hidden = false;
      $('ns-preview').open = true;
      message('生成しました: ' + data.path, true);
    } catch (e) {
      message('生成に失敗しました: ' + e.message, false);
    }
  }

  // ---- 実行 -------------------------------------------------------------
  // 投入は 202（受け付けただけ）。結果は 1.5 秒間隔のポーリングで取る。
  // 終端（complete/failed/cancelled）でポーリングを止める。止め忘れると
  // 画面を開いたままのブラウザが延々と叩き続ける。
  var POLL_MS = 1500;

  function runBox(show) {
    var box = $('ns-run-status');
    if (box) box.hidden = !show;
  }

  function runView(stateText, detailText, opts) {
    opts = opts || {};
    var st = $('ns-run-state');
    var detail = $('ns-run-detail');
    var job = $('ns-run-job');
    var bar = $('ns-run-bar');
    var fill = $('ns-run-bar-fill');
    var cancel = $('ns-run-cancel');
    runBox(true);
    if (st) {
      st.textContent = stateText;
      st.className = 'ns-run-state' + (opts.tone ? ' is-' + opts.tone : '');
    }
    if (detail) detail.textContent = detailText || '';
    if (job) job.textContent = state.jobId ? 'job_id: ' + state.jobId : '';
    if (cancel) cancel.hidden = !opts.cancellable;
    if (bar && fill) {
      // 進捗が未計測（NDJSON がまだ無い）ならバー自体を出さない。
      // 0/0 を 0% のバーで描くと「1 件も通っていない」と読めてしまう。
      if (opts.ratio == null) {
        bar.hidden = true;
      } else {
        bar.hidden = false;
        fill.style.width = Math.max(0, Math.min(100, Math.round(opts.ratio * 100))) + '%';
      }
    }
  }

  function stopPolling() {
    if (state.pollTimer) { clearTimeout(state.pollTimer); state.pollTimer = null; }
  }

  async function doRun() {
    if (!state.domain) return;
    // 生成と同じ扱い。未保存のステップは実行対象にならない（実行は保存済みから生成する）。
    if (state.dirty) { message('先に保存してください。実行は保存済みのステップから行います。', false); return; }
    if (state.jobId) { message('すでに実行中です。完了か中止を待ってください。', false); return; }
    stopPolling();
    try {
      var res = await fetch('/api/test-steps/' + encodeURIComponent(state.domain) + '/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ self_healing: true })
      });
      var data = await res.json();
      if (res.status === 409) {
        state.jobId = '';
        runView('実行できません', '実行中のジョブがあります（job_id: '
          + (data.running_job_id || '不明') + '）。完了を待つか、そのジョブを中止してください。',
          { tone: 'ng' });
        return;
      }
      if (!res.ok) {
        state.jobId = '';
        runView('実行できません', data.error || ('HTTP ' + res.status), { tone: 'ng' });
        return;
      }
      state.jobId = data.job_id;
      message('', true);
      var pos = data.queued_position;
      runView(pos > 0 ? '待機中' : '実行を開始しました',
        data.tests + ' 件を実行します'
        + (data.environment ? '（環境: ' + data.environment + '）' : '')
        + (pos > 0 ? '。待ち順 ' + pos + ' 番目です。' : '。'),
        { cancellable: true });
      state.pollTimer = setTimeout(pollJob, POLL_MS);
    } catch (e) {
      state.jobId = '';
      runView('実行できません', '実行を要求できませんでした: ' + e.message, { tone: 'ng' });
    }
  }

  async function pollJob() {
    if (!state.jobId) return;
    try {
      var res = await fetch('/api/test-runs/jobs/' + encodeURIComponent(state.jobId));
      var data = await res.json();
      if (res.status === 404) {
        stopPolling();
        state.jobId = '';
        runView('状況を取得できません', 'ジョブが見つかりません（サーバ再起動などで失われた可能性があります）。実行履歴を確認してください。', { tone: 'ng' });
        return;
      }
      if (!res.ok) { state.pollTimer = setTimeout(pollJob, POLL_MS); return; }
      renderJob(data);
    } catch (e) {
      // 一時的な通信断でポーリングを止めない（次周期で回復する）
      state.pollTimer = setTimeout(pollJob, POLL_MS);
    }
  }

  function renderJob(job) {
    var status = job.status;
    if (status === 'queued') {
      runView('待機中', '順番待ちです（待ち順 ' + (job.queued_position >= 0 ? job.queued_position : '?') + ' 番目）。',
        { cancellable: true });
      state.pollTimer = setTimeout(pollJob, POLL_MS);
      return;
    }
    if (status === 'running') {
      var p = job.progress;
      if (!p) {
        // 進捗ファイルがまだ無い＝未計測。件数を 0 と書かない。
        runView('実行中', '起動中です（進捗は未計測）。経過 ' + (job.elapsed_sec || 0) + ' 秒。',
          { cancellable: true });
      } else {
        var ratio = p.total ? p.done / p.total : null;
        runView('実行中',
          p.done + ' / ' + (p.total ? p.total + ' 件' : '件数は未計測')
          + '・合格 ' + p.passed + '／失敗 ' + p.failed
          + '・経過 ' + (job.elapsed_sec || 0) + ' 秒',
          { cancellable: true, ratio: ratio });
      }
      state.pollTimer = setTimeout(pollJob, POLL_MS);
      return;
    }
    // ---- 終端 ----
    stopPolling();
    state.jobId = '';
    var r = job.result || {};
    var hasCounts = r.total != null || r.passed != null;
    var counts = hasCounts
      ? '合格 ' + (r.passed || 0) + '／失敗 ' + (r.failed || 0)
        + '／不安定 ' + (r.flaky || 0) + '（全 ' + (r.total || 0) + ' 件）'
      : '件数は未計測です';
    var tail = '。詳細は「実行履歴」画面で確認できます'
      + (job.run_id ? '（実行回 ' + job.run_id + '）' : '') + '。';
    if (status === 'complete') {
      runView('完了', counts + tail, { tone: 'ok' });
    } else if (status === 'cancelled') {
      runView('中止しました', counts + tail, { tone: 'ng' });
    } else {
      runView('失敗', counts + (job.error ? '・' + job.error : '') + tail, { tone: 'ng' });
    }
  }

  async function doCancel() {
    if (!state.jobId) return;
    var id = state.jobId;
    try {
      var res = await fetch('/api/test-runs/jobs/' + encodeURIComponent(id) + '/cancel', { method: 'POST' });
      var data = await res.json();
      if (res.status === 409) { runView('中止できません', 'このジョブはすでに終了しています。', { tone: 'ng' }); return; }
      if (res.status === 404) {
        stopPolling(); state.jobId = '';
        runView('中止できません', 'ジョブが見つかりません。', { tone: 'ng' });
        return;
      }
      if (!res.ok) { runView('中止できません', data.error || ('HTTP ' + res.status), { tone: 'ng' }); return; }
      runView('中止を要求しました', '停止を待っています…', { cancellable: false });
      // 終端の確定はポーリングに任せる（ここで完了扱いにすると、実際は
      // まだ止まっていないのに「中止済み」と表示してしまう）。
      stopPolling();
      state.jobId = id;
      state.pollTimer = setTimeout(pollJob, POLL_MS);
    } catch (e) {
      runView('中止できません', '中止を要求できませんでした: ' + e.message, { tone: 'ng' });
    }
  }

  async function loadDomains() {
    var sel = $('ns-domain');
    if (!sel) return;
    try {
      // 「解析済み」か「ステップ保存済み」のサイト。実行履歴とは別条件で、
      // まだ一度も実行していないサイトでも編集できるようにする。
      var res = await fetch('/api/test-steps/sites');
      var list = res.ok ? ((await res.json()).sites || []).map(function (s) { return s.domain; }) : [];
      sel.innerHTML = list.length
        ? list.map(function (d) { return '<option value="' + esc(d) + '">' + esc(d) + '</option>'; }).join('')
        : '<option value="">（対象サイトがありません）</option>';
      state.domain = list[0] || '';
      if (!list.length) {
        message('解析済みのサイトがありません。先に解析を実行すると、ここに候補が出ます。', false);
        render();
        return;
      }
      loadDoc();
    } catch (e) {
      sel.innerHTML = '<option value="">（サイト一覧を取得できません）</option>';
      message('サイト一覧を取得できませんでした: ' + e.message, false);
    }
  }

  function init() {
    if (!$('ns-panel')) return;
    $('ns-tests').addEventListener('input', onInput);
    $('ns-tests').addEventListener('change', onInput);
    $('ns-tests').addEventListener('click', onClick);
    $('ns-domain').addEventListener('change', function (e) {
      // サイトを切り替えたら、別サイトのジョブを見続けないようポーリングを止める。
      stopPolling();
      state.jobId = '';
      runBox(false);
      state.domain = e.target.value;
      loadDoc();
    });
    $('ns-import').addEventListener('click', doImport);
    $('ns-save').addEventListener('click', doSave);
    $('ns-generate').addEventListener('click', doGenerate);
    if ($('ns-run')) $('ns-run').addEventListener('click', doRun);
    if ($('ns-run-cancel')) $('ns-run-cancel').addEventListener('click', doCancel);
    $('ns-add-test').addEventListener('click', function () {
      if (!state.doc) state.doc = { version: 1, domain: state.domain, tests: [] };
      state.doc.tests.push({
        test_id: newId('t'), title: '新しいテスト', enabled: true, note: '',
        steps: [{ id: newId('s'), action: 'goto', target: [], value: 'https://', label: '', note: '' }]
      });
      state.dirty = true;
      render();
    });
    loadActions().then(loadDomains);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window.nsReload = loadDoc;
})();
