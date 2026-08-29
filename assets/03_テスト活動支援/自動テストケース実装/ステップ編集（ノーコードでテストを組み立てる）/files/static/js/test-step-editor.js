// ステップ編集（ノーコード）。テスト活動支援 / 実装画面。
//
// 生成された .spec.ts を直接編集させない。編集の正本はステップ列で、
// コードは常にそこから生成する（生成物を直すと再生成のたびに消えるため）。
//
// 動作の語彙はサーバ（/api/test-steps/actions）から取る。画面側にも定義を持つと、
// 片方だけ増えたときに「選べるのに保存できない」が起きる。
(function () {
  'use strict';

  var state = { domain: '', doc: null, actions: [], dirty: false };

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
    $('ns-domain').addEventListener('change', function (e) { state.domain = e.target.value; loadDoc(); });
    $('ns-import').addEventListener('click', doImport);
    $('ns-save').addEventListener('click', doSave);
    $('ns-generate').addEventListener('click', doGenerate);
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
