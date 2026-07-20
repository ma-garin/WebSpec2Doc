// AutoRun 段階承認パイプライン（仕様7〜14 / 画面上は1〜8）のUI。
//
// **1フェーズ＝1画面**。フェーズの一覧はサイドメニューに置き、
// 中央にはそのフェーズの内容だけを出す。
// 承認済みフェーズへは戻って修正できる。
(function () {
  'use strict';

  // editing: 修正エディタを開いている項目のキー（stageId:itemId）。開いている間に
  // 別フェーズ・別画面へ移動しようとすると、破棄してよいか確認する
  // （監査で発覚: 以前は警告なく黙って破棄されていた）。
  var state = { domain: '', pipeline: null, selected: '', busy: false, editing: null };

  function confirmDiscardEdit() {
    if (!state.editing) return true;
    var ok = window.confirm('編集中の内容がまだ保存されていません。破棄して移動しますか？');
    if (ok) state.editing = null;
    return ok;
  }

  function $(id) { return document.getElementById(id); }
  function root() { return $('autorun-stages'); }

  // 1フェーズ＝1画面。フェーズ表示中は受付を隠し、中央をそのフェーズだけにする。
  function show(visible) {
    var el = root();
    if (el) el.style.display = visible ? '' : 'none';
    var intake = $('autorun-idle-msg');
    if (intake) intake.style.display = visible ? 'none' : '';
    setNavVisible(!!state.pipeline);
  }

  function setNavVisible(visible) {
    var group = $('autorun-phase-group');
    var nav = $('autorun-phase-nav');
    if (group) group.style.display = visible ? '' : 'none';
    if (nav) nav.style.display = visible ? '' : 'none';
  }

  // サイドの「受付」に戻る。段階の状態は保持したまま画面だけ切り替える。
  function showIntake() {
    var el = root();
    if (el) el.style.display = 'none';
    var intake = $('autorun-idle-msg');
    if (intake) intake.style.display = '';
    state.selected = '';
    renderNav();
    setNavVisible(!!state.pipeline);
    if (window.autorunChat) {
      window.autorunChat.setPhase({ key: 'intake', label: '受付' });
    }
  }

  async function call(path, options) {
    var res = await fetch(path, options);
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(data.detail || data.error || '操作に失敗しました');
    return data;
  }

  function stages() { return (state.pipeline && state.pipeline.stages) || []; }

  function stageById(id) {
    return stages().filter(function (s) { return s.stage_id === id; })[0] || null;
  }

  function indexOf(id) {
    var list = stages();
    for (var i = 0; i < list.length; i++) if (list[i].stage_id === id) return i;
    return -1;
  }

  // 到達済み＝承認済み、または「次に進むべき段階」。未到達は薄く表示する。
  function isReachable(stage) {
    if (stage.status !== 'pending') return true;
    return stage.stage_id === state.pipeline.current_stage_id;
  }

  // ---------------------------------------------------------------- サイドメニュー

  function renderNav() {
    var nav = $('autorun-phase-nav');
    if (!nav || !state.pipeline) return;
    nav.replaceChildren();

    stages().forEach(function (stage) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'autorun-phase-item is-' + stage.status;
      if (stage.stage_id === state.selected) btn.classList.add('is-selected');
      if (!isReachable(stage)) btn.classList.add('is-locked');

      var no = document.createElement('span');
      no.className = 'autorun-phase-no';
      no.textContent = stage.status === 'approved' ? '✓'
        : stage.status === 'skipped' ? '—' : String(stage.step_no);
      btn.appendChild(no);

      var label = document.createElement('span');
      label.className = 'autorun-phase-label';
      label.textContent = stage.name;
      btn.appendChild(label);

      btn.addEventListener('click', function () {
        if (!confirmDiscardEdit()) return;
        state.selected = stage.stage_id;
        render();
      });
      nav.appendChild(btn);
    });
  }

  // ---------------------------------------------------------------- 項目

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
      head.appendChild(makeBadge('is-edited', '修正済'));
    }
    if (item.source === 'llm') {
      head.appendChild(makeBadge('is-llm', 'LLM提案'));
    }
    if (item.approved) {
      head.appendChild(makeBadge('is-ok', '承認済み'));
    }
    row.appendChild(head);

    var detail = document.createElement('p');
    detail.className = 'autorun-stage-item-detail';
    detail.textContent = item.detail;
    row.appendChild(detail);

    var actions = document.createElement('div');
    actions.className = 'autorun-stage-item-actions';

    if (stage.requires_item_approval) {
      actions.appendChild(button(item.approved ? '承認済み（取消）' : '承認', function () {
        updateItem(stage.stage_id, item.item_id, { approved: !item.approved });
      }));
    }
    actions.appendChild(button('修正', function () { startEdit(row, stage, item); }));
    actions.appendChild(button('アシスタントに相談', function () {
      askAssistant('次の項目について改善案を出してください:\n' + item.title + '\n' + item.detail);
    }));

    row.appendChild(actions);
    return row;
  }

  function makeBadge(cls, text) {
    var b = document.createElement('span');
    b.className = 'autorun-stage-badge ' + cls;
    b.textContent = text;
    return b;
  }

  function button(text, onClick, cls) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = cls || 'btn-outline-sm';
    b.textContent = text;
    b.addEventListener('click', onClick);
    return b;
  }

  function askAssistant(text) {
    var input = $('autorun-chat-input');
    if (!input) return;
    input.value = text;
    input.focus();
  }

  function startEdit(row, stage, item) {
    state.editing = stage.stage_id + ':' + item.item_id;

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

    var buttons = document.createElement('div');
    buttons.className = 'autorun-stage-editor-actions';
    buttons.appendChild(button('保存', function () {
      state.editing = null;
      updateItem(stage.stage_id, item.item_id, {
        title: titleInput.value, detail: detailInput.value,
      });
    }, 'btn-primary'));
    buttons.appendChild(button('やめる', function () {
      state.editing = null;
      render();
    }));

    editor.appendChild(titleInput);
    editor.appendChild(detailInput);
    editor.appendChild(buttons);
    row.replaceChildren(editor);
    titleInput.focus();
  }

  // ---------------------------------------------------------------- 本文

  function renderPanel() {
    var panel = $('autorun-stage-panel');
    if (!panel || !state.pipeline) return;
    panel.replaceChildren();

    var stage = stageById(state.selected);
    if (!stage) return;

    var head = document.createElement('header');
    head.className = 'autorun-stage-head';

    var kicker = document.createElement('div');
    kicker.className = 'section-kicker';
    kicker.textContent = 'STEP ' + stage.step_no + ' / ' + stages().length;
    head.appendChild(kicker);

    var title = document.createElement('h3');
    title.className = 'autorun-stage-title';
    title.textContent = stage.name;
    head.appendChild(title);

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
      panel.appendChild(message('この段階はスキップされました（2回目以降のため）。'));
    } else if (!stage.items.length) {
      panel.appendChild(message('まだ生成されていません。「内容を生成」を押してください。'));
    } else {
      var list = document.createElement('div');
      list.className = 'autorun-stage-items';
      stage.items.forEach(function (item) { list.appendChild(itemRow(stage, item)); });
      panel.appendChild(list);
    }

    panel.appendChild(renderActions(stage));
  }

  function message(text) {
    var p = document.createElement('p');
    p.className = 'autorun-stage-empty';
    p.textContent = text;
    return p;
  }

  function renderActions(stage) {
    var bar = document.createElement('div');
    bar.className = 'autorun-stage-actions';

    var idx = indexOf(stage.stage_id);
    var prev = button('← 前へ', function () {
      state.selected = stages()[idx - 1].stage_id;
      render();
    });
    prev.disabled = idx <= 0;
    bar.appendChild(prev);

    var gen = button(stage.items.length ? '作り直す' : '内容を生成', function () {
      generateStage(stage.stage_id);
    });
    gen.disabled = state.busy;
    bar.appendChild(gen);

    if (stage.items.length) {
      var suggest = button('抜けをLLMに聞く', function () { suggestFor(stage.stage_id); });
      suggest.disabled = state.busy;
      bar.appendChild(suggest);
    }

    if (stage.skippable_on_rerun && state.pipeline.is_rerun && stage.status !== 'skipped') {
      var skip = button('スキップ（2回目以降）', function () { skipStage(stage.stage_id); });
      skip.disabled = state.busy;
      bar.appendChild(skip);
    }

    var status = document.createElement('span');
    status.className = 'autorun-stage-actions-note';
    if (stage.status === 'approved') {
      status.textContent = 'この段階は承認済みです。修正すると再承認が必要です。';
    } else if (stage.requires_item_approval && !stage.can_approve && stage.items.length) {
      var pending = stage.items.filter(function (i) { return !i.approved; }).length;
      status.textContent = '未承認の項目が ' + pending + ' 件あります。全て承認すると次へ進めます。';
    }
    bar.appendChild(status);

    var approve = button('承認して次へ', function () { approveStage(stage.stage_id); }, 'btn-primary');
    approve.disabled = state.busy || !stage.can_approve || stage.status === 'approved';
    bar.appendChild(approve);

    return bar;
  }

  // ---------------------------------------------------------------- 進行

  function renderProceed() {
    var host = root();
    if (!host) return;
    var old = host.querySelector('.autorun-stages-proceed');
    if (old) old.remove();
    if (!state.pipeline) return;

    // 設計段階（1〜7）が揃った時点と、全段階が揃った時点で進める
    var designDone = stages().slice(0, 7).every(function (s) {
      return s.status === 'approved' || s.status === 'skipped';
    });
    var allDone = state.pipeline.all_approved;
    if (!designDone) return;

    var bar = document.createElement('div');
    bar.className = 'autorun-stages-proceed';

    var msg = document.createElement('span');
    msg.className = 'autorun-stages-proceed-msg';
    msg.textContent = allDone
      ? '全ての段階を承認しました。テストを実行できます。'
      : '設計段階（1〜7）を承認しました。Playwright 化へ進めます。';
    bar.appendChild(msg);

    var go = button(allDone ? '承認を確定して実行する' : '承認を確定して次へ進む', proceed, 'btn-primary');
    go.disabled = state.busy;
    bar.appendChild(go);

    host.appendChild(bar);
  }

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
        viewpoint_set_name: vpSelect
          ? ((vpSelect.options[vpSelect.selectedIndex] || {}).text || '') : '',
      }));
      state.selected = stageId;
    });
  }

  function approveStage(stageId) {
    return withBusy(async function () {
      state.pipeline = await call('/api/autorun/stages/approve', json({
        domain: state.domain, stage_id: stageId,
      }));
      // 承認したら次の未承認フェーズへ自動で進む
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

  function updateItem(stageId, itemId, changes) {
    return withBusy(async function () {
      var body = { domain: state.domain, stage_id: stageId, item_id: itemId };
      Object.keys(changes).forEach(function (k) { body[k] = changes[k]; });
      state.pipeline = await call('/api/autorun/stages/item', json(body));
    });
  }

  function proceed() {
    return withBusy(async function () {
      var jobId = (window._autoRunLastData && window._autoRunLastData.job_id) || '';
      var res = await call('/api/autorun/stages/proceed', json({
        domain: state.domain, job_id: jobId,
      }));
      state.pipeline = res;
      if (res.detail) {
        var host = root();
        if (host) {
          var note = document.createElement('div');
          note.className = 'autorun-stages-proceed-msg';
          note.textContent = res.detail;
          host.appendChild(note);
        }
      }
    });
  }

  // ---------------------------------------------------------------- LLM 提案

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
        var d = document.createElement('p');
        d.className = 'autorun-suggest-detail';
        d.textContent = s.detail;
        row.appendChild(d);
      }
      if (s.reason) {
        var r = document.createElement('p');
        r.className = 'autorun-suggest-reason';
        r.textContent = '理由: ' + s.reason;
        row.appendChild(r);
      }
      row.appendChild(button('項目として採用', function () {
        adoptSuggestion(stageId, s.title, s.detail);
      }));
      box.appendChild(row);
    });

    panel.appendChild(box);
  }

  function suggestFor(stageId) {
    return withBusy(async function () {
      var urlInput = $('autorun-url');
      var result = await call('/api/autorun/stages/suggest', json({
        domain: state.domain, stage_id: stageId,
        url: urlInput ? urlInput.value : '',
      }));
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

  // ---------------------------------------------------------------- 全体

  function render() {
    if (!state.pipeline) { show(false); return; }
    show(true);
    renderNav();
    renderPanel();
    renderProceed();
    notifyPhase();
  }

  // 右のアシスタントへ、現在のフェーズを伝える
  function notifyPhase() {
    var stage = stageById(state.selected);
    if (window.autorunChat && stage) {
      window.autorunChat.setPhase({
        key: stage.stage_id,
        label: 'STEP ' + stage.step_no + ' ' + stage.name,
      });
    }
  }

  async function load(domain, opts) {
    if (!domain) return;
    state.domain = domain;
    try {
      state.pipeline = await call('/api/autorun/stages?domain=' + encodeURIComponent(domain));
      var list = state.pipeline.stages || [];
      state.selected = state.pipeline.current_stage_id
        || (list.length ? list[list.length - 1].stage_id : '');
      // 読み込んだだけでは画面を奪わない。フェーズを開くのは利用者の操作か、
      // ジョブが承認待ちに入った時だけ。
      if (opts && opts.open) {
        render();
      } else {
        renderNav();
        setNavVisible(true);
      }
    } catch (e) {
      state.pipeline = null;
      setNavVisible(false);
    }
  }

  function boot() {
    // サイドの「受付」を押したら受付画面へ戻す
    var intakeNav = document.querySelector('.app-nav-item[data-view="auto-run"]');
    if (intakeNav) intakeNav.addEventListener('click', function (e) {
      if (!confirmDiscardEdit()) { e.preventDefault(); e.stopImmediatePropagation(); return; }
      showIntake();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  window.autorunStages = {
    load: load,
    render: render,
    showIntake: showIntake,
    hide: function () { show(false); },
  };
})();
