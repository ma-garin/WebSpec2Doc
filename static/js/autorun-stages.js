// AutoRun 段階承認パイプライン（仕様7〜13）のUI。
//
// 提示 → 項目単位の修正/承認 → 段階の承認、で進む。
// フィーチャー分析は全項目の承認が必要（仕様9）。
// テスト計画は同一URLの2回目以降のみスキップできる（仕様8）。
(function () {
  'use strict';

  var state = { domain: '', pipeline: null, selected: '', busy: false };

  function $(id) { return document.getElementById(id); }
  function root() { return $('autorun-stages'); }

  function show(visible) {
    var el = root();
    if (el) el.style.display = visible ? '' : 'none';
  }

  async function call(path, options) {
    var res = await fetch(path, options);
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(data.detail || data.error || '操作に失敗しました');
    return data;
  }

  function stageById(id) {
    if (!state.pipeline) return null;
    return state.pipeline.stages.filter(function (s) { return s.stage_id === id; })[0] || null;
  }

  // ---------------------------------------------------------------- 描画

  function renderRail() {
    var rail = $('autorun-stages-rail');
    if (!rail || !state.pipeline) return;
    rail.replaceChildren();

    state.pipeline.stages.forEach(function (stage) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'autorun-stage-tab is-' + stage.status;
      if (stage.stage_id === state.selected) btn.classList.add('is-selected');

      var no = document.createElement('span');
      no.className = 'autorun-stage-no';
      no.textContent = String(stage.step_no);
      btn.appendChild(no);

      var name = document.createElement('span');
      name.className = 'autorun-stage-name';
      name.textContent = stage.name;
      btn.appendChild(name);

      var mark = document.createElement('span');
      mark.className = 'autorun-stage-mark';
      mark.textContent =
        stage.status === 'approved' ? '✓' : stage.status === 'skipped' ? '—' : '';
      btn.appendChild(mark);

      btn.addEventListener('click', function () {
        state.selected = stage.stage_id;
        render();
      });
      rail.appendChild(btn);
    });
  }

  function itemRow(stage, item) {
    var row = document.createElement('div');
    row.className = 'autorun-stage-item' + (item.approved ? ' is-approved' : '');

    var head = document.createElement('div');
    head.className = 'autorun-stage-item-head';

    var title = document.createElement('span');
    title.className = 'autorun-stage-item-title';
    title.textContent = item.title;
    head.appendChild(title);

    if (item.assumed) {
      var badge = document.createElement('span');
      badge.className = 'autorun-stage-badge is-assumed';
      badge.textContent = '前提';
      badge.title = '観測では決められないため前提を置いています。実行は止めません。';
      head.appendChild(badge);
    }
    if (item.source === 'user') {
      var edited = document.createElement('span');
      edited.className = 'autorun-stage-badge is-edited';
      edited.textContent = '修正済';
      head.appendChild(edited);
    }
    row.appendChild(head);

    var detail = document.createElement('p');
    detail.className = 'autorun-stage-item-detail';
    detail.textContent = item.detail;
    row.appendChild(detail);

    var actions = document.createElement('div');
    actions.className = 'autorun-stage-item-actions';

    if (stage.requires_item_approval) {
      var approve = document.createElement('button');
      approve.type = 'button';
      approve.className = 'btn-outline-sm';
      approve.textContent = item.approved ? '承認済み（取消）' : '承認';
      approve.addEventListener('click', function () {
        updateItem(stage.stage_id, item.item_id, { approved: !item.approved });
      });
      actions.appendChild(approve);
    }

    var edit = document.createElement('button');
    edit.type = 'button';
    edit.className = 'btn-outline-sm';
    edit.textContent = '修正';
    edit.addEventListener('click', function () {
      startEdit(row, stage, item);
    });
    actions.appendChild(edit);

    var ask = document.createElement('button');
    ask.type = 'button';
    ask.className = 'btn-outline-sm';
    ask.textContent = 'アシスタントに相談';
    ask.addEventListener('click', function () {
      var input = $('autorun-chat-input');
      if (!input) return;
      input.value = '次の項目について改善案を出してください:\n' + item.title + '\n' + item.detail;
      input.focus();
    });
    actions.appendChild(ask);

    row.appendChild(actions);
    return row;
  }

  function startEdit(row, stage, item) {
    var editor = document.createElement('div');
    editor.className = 'autorun-stage-editor';

    var titleInput = document.createElement('input');
    titleInput.type = 'text';
    titleInput.className = 'url-input input-compact';
    titleInput.value = item.title;

    var detailInput = document.createElement('textarea');
    detailInput.className = 'autorun-stage-editor-detail';
    detailInput.rows = 4;
    detailInput.value = item.detail;

    var save = document.createElement('button');
    save.type = 'button';
    save.className = 'btn-primary';
    save.textContent = '保存';
    save.addEventListener('click', function () {
      updateItem(stage.stage_id, item.item_id, {
        title: titleInput.value,
        detail: detailInput.value,
      });
    });

    var cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'btn-outline-sm';
    cancel.textContent = 'やめる';
    cancel.addEventListener('click', render);

    var buttons = document.createElement('div');
    buttons.className = 'autorun-stage-editor-actions';
    buttons.appendChild(save);
    buttons.appendChild(cancel);

    editor.appendChild(titleInput);
    editor.appendChild(detailInput);
    editor.appendChild(buttons);
    row.replaceChildren(editor);
    titleInput.focus();
  }

  function renderPanel() {
    var panel = $('autorun-stage-panel');
    if (!panel || !state.pipeline) return;
    panel.replaceChildren();

    var stage = stageById(state.selected) || stageById(state.pipeline.current_stage_id);
    if (!stage) return;
    state.selected = stage.stage_id;

    var head = document.createElement('header');
    head.className = 'autorun-stage-head';

    var kicker = document.createElement('div');
    kicker.className = 'section-kicker';
    kicker.textContent = 'STEP ' + stage.step_no + ' / ' + stage.name;
    head.appendChild(kicker);

    var purpose = document.createElement('p');
    purpose.className = 'autorun-stage-purpose';
    purpose.textContent = stage.purpose;
    head.appendChild(purpose);
    panel.appendChild(head);

    if (stage.note) {
      var note = document.createElement('div');
      note.className = 'autorun-stage-note';
      note.textContent = stage.note;
      panel.appendChild(note);
    }

    if (stage.status === 'skipped') {
      var skipped = document.createElement('p');
      skipped.className = 'autorun-stage-empty';
      skipped.textContent = 'この段階はスキップされました（2回目以降のため）。';
      panel.appendChild(skipped);
    } else if (!stage.items.length) {
      var empty = document.createElement('p');
      empty.className = 'autorun-stage-empty';
      empty.textContent = 'まだ生成されていません。「内容を生成」を押してください。';
      panel.appendChild(empty);
    } else {
      var list = document.createElement('div');
      list.className = 'autorun-stage-items';
      stage.items.forEach(function (item) {
        list.appendChild(itemRow(stage, item));
      });
      panel.appendChild(list);
    }

    panel.appendChild(renderActions(stage));
  }

  function renderActions(stage) {
    var bar = document.createElement('div');
    bar.className = 'autorun-stage-actions';

    var generate = document.createElement('button');
    generate.type = 'button';
    generate.className = 'btn-outline-sm';
    generate.textContent = stage.items.length ? '作り直す' : '内容を生成';
    generate.disabled = state.busy;
    generate.addEventListener('click', function () { generateStage(stage.stage_id); });
    bar.appendChild(generate);

    if (stage.items.length) {
      var suggest = document.createElement('button');
      suggest.type = 'button';
      suggest.className = 'btn-outline-sm';
      suggest.textContent = '抜けをLLMに聞く';
      suggest.disabled = state.busy;
      suggest.addEventListener('click', function () { suggestFor(stage.stage_id); });
      bar.appendChild(suggest);
    }

    if (stage.skippable_on_rerun && state.pipeline.is_rerun && stage.status !== 'skipped') {
      var skip = document.createElement('button');
      skip.type = 'button';
      skip.className = 'btn-outline-sm';
      skip.textContent = 'スキップ（2回目以降）';
      skip.disabled = state.busy;
      skip.addEventListener('click', function () { skipStage(stage.stage_id); });
      bar.appendChild(skip);
    }

    var status = document.createElement('span');
    status.className = 'autorun-stage-actions-note';
    if (stage.status === 'approved') {
      status.textContent = 'この段階は承認済みです。';
    } else if (stage.requires_item_approval && !stage.can_approve) {
      var pending = stage.items.filter(function (i) { return !i.approved; }).length;
      status.textContent = stage.items.length
        ? '未承認の項目が ' + pending + ' 件あります。全て承認すると次へ進めます。'
        : '';
    }
    bar.appendChild(status);

    var approve = document.createElement('button');
    approve.type = 'button';
    approve.className = 'btn-primary';
    approve.textContent = '承認して次へ';
    approve.disabled = state.busy || !stage.can_approve || stage.status === 'approved';
    approve.addEventListener('click', function () { approveStage(stage.stage_id); });
    bar.appendChild(approve);

    return bar;
  }

  function renderProceed() {
    var host = $('autorun-stages');
    if (!host) return;
    var old = host.querySelector('.autorun-stages-proceed');
    if (old) old.remove();
    if (!state.pipeline || !state.pipeline.all_approved) return;

    var bar = document.createElement('div');
    bar.className = 'autorun-stages-proceed';

    var msg = document.createElement('span');
    msg.className = 'autorun-stages-proceed-msg';
    msg.textContent = '全ての段階を承認しました。Playwright 化へ進めます。';
    bar.appendChild(msg);

    var go = document.createElement('button');
    go.type = 'button';
    go.className = 'btn-primary';
    go.textContent = '承認を確定して次へ進む';
    go.disabled = state.busy;
    go.addEventListener('click', proceed);
    bar.appendChild(go);

    host.appendChild(bar);
  }

  function proceed() {
    return withBusy(async function () {
      var jobId = (window._autoRunLastData && window._autoRunLastData.job_id) || '';
      var res = await call('/api/autorun/stages/proceed', json({
        domain: state.domain, job_id: jobId,
      }));
      state.pipeline = res;
      var host = $('autorun-stages');
      if (host && res.detail) {
        var note = document.createElement('div');
        note.className = 'autorun-stages-proceed-msg';
        note.textContent = res.detail;
        host.appendChild(note);
      }
    });
  }

  function render() {
    if (!state.pipeline) { show(false); return; }
    show(true);
    renderRail();
    renderPanel();
    renderProceed();
  }

  // ---------------------------------------------------------------- 操作

  function json(body) {
    return {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    };
  }

  async function withBusy(fn) {
    if (state.busy) return;
    state.busy = true;
    render();
    try {
      await fn();
    } catch (e) {
      var panel = $('autorun-stage-panel');
      if (panel) {
        var err = document.createElement('div');
        err.className = 'autorun-stage-error';
        err.textContent = e && e.message ? e.message : '操作に失敗しました';
        panel.appendChild(err);
      }
    } finally {
      state.busy = false;
      render();
    }
  }

  function generateStage(stageId) {
    return withBusy(async function () {
      var urlInput = $('autorun-url');
      var vpSelect = $('autorun-viewpoint-set');
      var modeDoc = $('autorun-mode-document');
      state.pipeline = await call('/api/autorun/stages/generate', json({
        domain: state.domain,
        stage_id: stageId,
        url: urlInput ? urlInput.value : '',
        document_driven: !!(modeDoc && modeDoc.checked),
        viewpoint_set_name: vpSelect ? (vpSelect.options[vpSelect.selectedIndex] || {}).text || '' : '',
      }));
      state.selected = stageId;
    });
  }

  function approveStage(stageId) {
    return withBusy(async function () {
      state.pipeline = await call('/api/autorun/stages/approve', json({
        domain: state.domain, stage_id: stageId,
      }));
      state.selected = state.pipeline.current_stage_id || stageId;
    });
  }

  function skipStage(stageId) {
    return withBusy(async function () {
      state.pipeline = await call('/api/autorun/stages/skip', json({
        domain: state.domain, stage_id: stageId,
      }));
      state.selected = state.pipeline.current_stage_id || stageId;
    });
  }

  function renderSuggestions(stageId, result) {
    var panel = $('autorun-stage-panel');
    if (!panel) return;

    var box = document.createElement('div');
    box.className = 'autorun-suggest';

    var head = document.createElement('div');
    head.className = 'autorun-suggest-head';
    head.textContent = result.available
      ? 'LLM からの追加候補（採用は人が判断します）'
      : 'LLM の提案は利用できません';
    box.appendChild(head);

    if (result.message) {
      var msg = document.createElement('p');
      msg.className = 'autorun-suggest-msg';
      msg.textContent = result.message;
      box.appendChild(msg);
    }

    (result.suggestions || []).forEach(function (s) {
      var row = document.createElement('div');
      row.className = 'autorun-suggest-item';

      var title = document.createElement('div');
      title.className = 'autorun-suggest-title';
      title.textContent = s.title;
      row.appendChild(title);

      if (s.detail) {
        var detail = document.createElement('p');
        detail.className = 'autorun-suggest-detail';
        detail.textContent = s.detail;
        row.appendChild(detail);
      }
      if (s.reason) {
        var reason = document.createElement('p');
        reason.className = 'autorun-suggest-reason';
        reason.textContent = '理由: ' + s.reason;
        row.appendChild(reason);
      }

      var adopt = document.createElement('button');
      adopt.type = 'button';
      adopt.className = 'btn-outline-sm';
      adopt.textContent = '項目として採用';
      adopt.addEventListener('click', function () {
        adoptSuggestion(stageId, s.title, s.detail);
      });
      row.appendChild(adopt);
      box.appendChild(row);
    });

    panel.appendChild(box);
  }

  function suggestFor(stageId) {
    return withBusy(async function () {
      var urlInput = $('autorun-url');
      var result = await call('/api/autorun/stages/suggest', json({
        domain: state.domain,
        stage_id: stageId,
        url: urlInput ? urlInput.value : '',
      }));
      // render() で消えないよう、描画後に追記する
      setTimeout(function () { renderSuggestions(stageId, result); }, 0);
    });
  }

  function adoptSuggestion(stageId, title, detail) {
    return withBusy(async function () {
      state.pipeline = await call('/api/autorun/stages/adopt', json({
        domain: state.domain, stage_id: stageId, title: title, detail: detail,
      }));
    });
  }

  function updateItem(stageId, itemId, changes) {
    return withBusy(async function () {
      var body = { domain: state.domain, stage_id: stageId, item_id: itemId };
      Object.keys(changes).forEach(function (k) { body[k] = changes[k]; });
      state.pipeline = await call('/api/autorun/stages/item', json(body));
    });
  }

  async function load(domain) {
    if (!domain) return;
    state.domain = domain;
    try {
      state.pipeline = await call('/api/autorun/stages?domain=' + encodeURIComponent(domain));
      state.selected = state.pipeline.current_stage_id || '';
      render();
    } catch (e) {
      show(false);
    }
  }

  // 外部（autorun.js のジョブ進行）から呼べるようにする
  window.autorunStages = { load: load, render: render, hide: function () { show(false); } };
})();
