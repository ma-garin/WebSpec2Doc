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
  // lastRendered: 直前に表示していたフェーズ。切り替え方向（進む/戻る）を
  // 判定してスライドアニメーションの向きを決めるために保持する。
  var state = {
    domain: '', pipeline: null, selected: '', busy: false, editing: null,
    lastRendered: '', showActivity: false,
  };

  // フェーズごとの代表 HTML 成果物（ジョブの outputs キー）。JSON は削除せず
  // LLM 入力・アクティビティログとして保持し、画面では HTML 版を見せる。
  var STAGE_ARTIFACT_KEYS = {
    test_objective: ['report_html'],
    test_plan: ['test_plan'],
    features: ['report_html'],
    viewpoints: ['test_analysis'],
    basic_design: ['test_design'],
    detail_design: ['test_design'],
    test_cases: ['test_cases'],
    playwright_automation: ['playwright_candidates_html'],
  };

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
    state.showActivity = false;
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
        state.showActivity = false;
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

  // フェーズ切替時に、進む/戻るの向きに応じたスライドで新しい画面を入れる。
  // prefers-reduced-motion はCSS側で無効化される。
  function applySlide(panel, fromId, toId) {
    if (!fromId || fromId === toId) return;
    var direction = indexOf(toId) >= indexOf(fromId) ? 'fwd' : 'back';
    var cls = 'is-slide-' + direction;
    panel.classList.remove('is-slide-fwd', 'is-slide-back');
    // 再スタイル計算を挟んで同じクラスの付け直しでもアニメーションを再生させる
    void panel.offsetWidth;
    panel.classList.add(cls);
    panel.addEventListener('animationend', function handler() {
      panel.classList.remove(cls);
      panel.removeEventListener('animationend', handler);
    });
  }

  // フェーズに対応する HTML 中間成果物をインラインで表示する。
  // これまで成果物はプレビューボタンの先にしか無く、JSON/HTML のファイル名の
  // 羅列では価値が伝わりにくかった。1フェーズ＝1画面の中に成果物そのものを出す。
  function renderArtifact(stage) {
    var outputs = (window._autoRunLastData && window._autoRunLastData.outputs) || {};
    var keys = STAGE_ARTIFACT_KEYS[stage.stage_id] || [];
    var path = '';
    var key = '';
    for (var i = 0; i < keys.length; i++) {
      if (outputs[keys[i]]) { key = keys[i]; path = outputs[keys[i]]; break; }
    }
    if (!path || !/\.html?$/i.test(path)) return null;

    var box = document.createElement('section');
    box.className = 'autorun-stage-artifact';

    var head = document.createElement('div');
    head.className = 'autorun-stage-artifact-head';

    var label = document.createElement('span');
    label.className = 'autorun-stage-artifact-label';
    label.textContent = 'この段階の成果物プレビュー';
    head.appendChild(label);

    var open = document.createElement('button');
    open.type = 'button';
    open.className = 'btn-outline-sm qa-preview-btn';
    open.dataset.path = path;
    open.dataset.label = stage.name + ' の成果物';
    open.textContent = '拡大して開く';
    head.appendChild(open);
    box.appendChild(head);

    var frame = document.createElement('iframe');
    frame.className = 'autorun-stage-artifact-frame';
    frame.src = '/preview?path=' + encodeURIComponent(path);
    frame.title = stage.name + ' の成果物プレビュー';
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin');
    frame.setAttribute('loading', 'lazy');
    box.appendChild(frame);
    return box;
  }

  // 段階の状態タグ（縦タイムライン証跡フィード＝案A）。状態は実データの status 由来。
  var _STATUS_CHIP = {
    approved: ['is-ok', '承認済み'],
    generated: ['is-active', '生成済み'],
    skipped: ['is-skip', 'スキップ'],
    pending: ['is-pending', '未着手'],
  };
  function statusChip(stage) {
    var meta = _STATUS_CHIP[stage.status] || _STATUS_CHIP.pending;
    var s = document.createElement('span');
    s.className = 'autorun-stage-statuschip ' + meta[0];
    s.textContent = meta[1];
    return s;
  }

  // 証跡チップ（案A: 「リンクの塊」を件数で価値の分かる情報へ）。すべて実データ由来。
  function evidenceChips(stage) {
    var wrap = document.createElement('div');
    wrap.className = 'autorun-stage-evidence';
    var total = stage.items.length;
    if (!total) return wrap;
    function chip(label, value) {
      var c = document.createElement('span');
      c.className = 'autorun-ev-chip';
      var b = document.createElement('b');
      b.textContent = String(value);
      c.append(document.createTextNode(label + ' '), b);
      return c;
    }
    wrap.appendChild(chip('項目', total));
    if (stage.requires_item_approval) {
      var approved = stage.items.filter(function (i) { return i.approved; }).length;
      wrap.appendChild(chip('承認', approved + '/' + total));
    }
    var llm = stage.items.filter(function (i) { return i.source === 'llm'; }).length;
    if (llm) wrap.appendChild(chip('LLM提案', llm));
    return wrap;
  }

  // 段階の証跡サマリ文字列（タイムラインカードの折り畳み時に一目で分かる指標）。
  function evidenceSummary(stage) {
    var total = stage.items.length;
    if (!total) return '';
    var parts = ['項目 ' + total];
    if (stage.requires_item_approval) {
      var ap = stage.items.filter(function (i) { return i.approved; }).length;
      parts.push('承認 ' + ap + '/' + total);
    }
    var llm = stage.items.filter(function (i) { return i.source === 'llm'; }).length;
    if (llm) parts.push('LLM ' + llm);
    return parts.join(' · ');
  }

  var _SOURCE_BADGE = { llm: ['is-llm', 'LLM提案'], user: ['is-edited', '修正済'] };

  // 右カラムの成果物キャンバス（案B: 決定は左・成果物は右で常に画面に在り続ける）。
  // 実 HTML 成果物があれば iframe、無ければ段階データから読み取り用の文書を生成する。
  function renderCanvas(stage) {
    var canvas = document.createElement('aside');
    canvas.className = 'autorun-stage-canvas';
    var artifact = renderArtifact(stage);
    if (artifact) {
      canvas.appendChild(artifact);
      return canvas;
    }
    canvas.appendChild(renderDocView(stage));
    return canvas;
  }

  // 段階データから「成果物文書」を組み立てて右キャンバスに描画する（実データ由来）。
  function renderDocView(stage) {
    var doc = document.createElement('section');
    doc.className = 'autorun-doc';

    var bar = document.createElement('div');
    bar.className = 'autorun-doc-bar';
    var label = document.createElement('span');
    label.className = 'autorun-doc-label';
    label.textContent = '成果物プレビュー';
    bar.appendChild(label);
    doc.appendChild(bar);

    var sheet = document.createElement('article');
    sheet.className = 'autorun-doc-sheet';

    var h = document.createElement('h4');
    h.className = 'autorun-doc-title';
    h.textContent = stage.name;
    sheet.appendChild(h);

    var meta = document.createElement('div');
    meta.className = 'autorun-doc-meta';
    var sum = evidenceSummary(stage);
    meta.textContent = 'STEP ' + stage.step_no + ' / ' + stages().length + (sum ? ' · ' + sum : '');
    sheet.appendChild(meta);

    var lead = document.createElement('p');
    lead.className = 'autorun-doc-lead';
    lead.textContent = stage.purpose;
    sheet.appendChild(lead);

    if (!stage.items.length) {
      var empty = document.createElement('div');
      empty.className = 'autorun-stage-canvas-empty';
      empty.textContent = '左で「内容を生成」すると、ここに成果物の文書が表示されます。';
      sheet.appendChild(empty);
    } else {
      var table = document.createElement('table');
      table.className = 'autorun-doc-table';
      table.innerHTML =
        '<thead><tr><th class="c-no">#</th><th>内容</th>'
        + '<th class="c-src">種別</th></tr></thead>';
      var tbody = document.createElement('tbody');
      stage.items.forEach(function (item, i) {
        var tr = document.createElement('tr');
        var td0 = document.createElement('td');
        td0.className = 'c-no';
        td0.textContent = String(i + 1);
        var td1 = document.createElement('td');
        var t = document.createElement('div');
        t.className = 'autorun-doc-itemtitle';
        t.textContent = item.title;
        td1.appendChild(t);
        if (item.detail) {
          var d = document.createElement('div');
          d.className = 'autorun-doc-itemdetail';
          d.textContent = item.detail;
          td1.appendChild(d);
        }
        var td2 = document.createElement('td');
        td2.className = 'c-src';
        var badge = _SOURCE_BADGE[item.source];
        if (item.assumed) td2.appendChild(makeBadge('is-assumed', '前提'));
        if (badge) td2.appendChild(makeBadge(badge[0], badge[1]));
        if (item.approved) td2.appendChild(makeBadge('is-ok', '承認'));
        tr.append(td0, td1, td2);
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      var scroll = document.createElement('div');
      scroll.className = 'autorun-doc-scroll';
      scroll.appendChild(table);
      sheet.appendChild(scroll);
    }
    doc.appendChild(sheet);
    return doc;
  }

  // 中央の縦タイムライン（案A）。全段階を連結線付きカードで並べ、選択段階を展開する。
  function renderTimeline() {
    var tl = document.createElement('div');
    tl.className = 'autorun-timeline';
    stages().forEach(function (stage) {
      var selected = stage.stage_id === state.selected;
      var node = document.createElement('div');
      node.className = 'artl-node is-' + stage.status + (selected ? ' is-selected' : '');
      if (!isReachable(stage)) node.classList.add('is-locked');

      var dot = document.createElement('span');
      dot.className = 'artl-dot';
      dot.textContent = stage.status === 'approved' ? '✓'
        : stage.status === 'skipped' ? '—' : String(stage.step_no);
      node.appendChild(dot);

      var card = document.createElement('div');
      card.className = 'artl-card';

      var head = document.createElement('button');
      head.type = 'button';
      head.className = 'artl-card-head';
      var name = document.createElement('span');
      name.className = 'artl-card-name';
      name.textContent = stage.name;
      head.appendChild(name);
      head.appendChild(statusChip(stage));
      var sum = evidenceSummary(stage);
      if (sum) {
        var s = document.createElement('span');
        s.className = 'artl-card-ev';
        s.textContent = sum;
        head.appendChild(s);
      }
      head.addEventListener('click', function () {
        if (!confirmDiscardEdit()) return;
        state.selected = stage.stage_id;
        render();
      });
      card.appendChild(head);

      if (selected) {
        var body = document.createElement('div');
        body.className = 'artl-card-body';
        if (stage.note) {
          var note = document.createElement('div');
          note.className = 'autorun-stage-note';
          note.textContent = stage.note;
          body.appendChild(note);
        }
        if (stage.status === 'skipped') {
          body.appendChild(message('この段階はスキップされました（2回目以降のため）。'));
        } else if (!stage.items.length) {
          body.appendChild(message('まだ生成されていません。「内容を生成」を押してください。'));
        } else {
          var list = document.createElement('div');
          list.className = 'autorun-stage-items';
          stage.items.forEach(function (item) { list.appendChild(itemRow(stage, item)); });
          body.appendChild(list);
        }
        card.appendChild(body);
      }
      node.appendChild(card);
      tl.appendChild(node);
    });
    return tl;
  }

  // アクティビティログ（案A: JSON を型付きイベントのタイムラインで見せる）。
  // 監査は state.pipeline.audit（実データ）。生成AIの記録は llm_activity.jsonl に別途保存。
  var _ACTION_LABEL = {
    generate: '生成', approve: '承認', skip: 'スキップ', proceed: '確定して進む',
    item_approve: '項目を承認', item_unapprove: '承認取消', item_edit: '項目を修正',
    adopt_llm: 'LLM提案を採用',
  };
  function renderActivityLog() {
    var panel = $('autorun-stage-panel');
    if (!panel || !state.pipeline) return;
    panel.replaceChildren();

    var head = document.createElement('header');
    head.className = 'autorun-stage-head autorun-stage-head-row';
    var title = document.createElement('h3');
    title.className = 'autorun-stage-title';
    title.textContent = 'アクティビティログ';
    head.appendChild(title);
    head.appendChild(button('← 段階へ戻る', function () {
      state.showActivity = false;
      render();
    }));
    panel.appendChild(head);

    var audit = (state.pipeline.audit || []).slice().reverse();
    if (!audit.length) {
      panel.appendChild(message('まだ記録がありません。生成・承認を行うとここに残ります。'));
    } else {
      var feed = document.createElement('div');
      feed.className = 'autorun-activity';
      audit.forEach(function (e) {
        var row = document.createElement('div');
        row.className = 'autorun-activity-row';
        var when = document.createElement('span');
        when.className = 'autorun-activity-when';
        when.textContent = (e.at || '').replace('T', ' ').slice(0, 19);
        var body = document.createElement('span');
        body.className = 'autorun-activity-body';
        var act = document.createElement('b');
        act.textContent = _ACTION_LABEL[e.action] || e.action;
        body.appendChild(act);
        var stageName = (stageById(e.stage_id) || {}).name || e.stage_id;
        if (stageName) {
          var sp = document.createElement('span');
          sp.className = 'autorun-activity-stage';
          sp.textContent = stageName;
          body.appendChild(sp);
        }
        if (e.action === 'adopt_llm') {
          body.appendChild(makeBadge('is-llm', 'LLM'));
        }
        if (e.detail) {
          var d = document.createElement('span');
          d.className = 'autorun-activity-detail';
          d.textContent = e.detail;
          body.appendChild(d);
        }
        row.append(when, body);
        if (e.actor) {
          var who = document.createElement('span');
          who.className = 'autorun-activity-actor';
          who.textContent = e.actor;
          row.appendChild(who);
        }
        feed.appendChild(row);
      });
      panel.appendChild(feed);
    }

    var foot = document.createElement('p');
    foot.className = 'autorun-activity-note';
    foot.textContent =
      'JSON は削除せず保持しています（LLM 入力・監査証跡）。生成 AI の呼び出しは'
      + '成功・退避・失敗を問わず llm_activity.jsonl に記録されます。';
    panel.appendChild(foot);
  }

  // 進行の全体サマリ（承認済み数 / 総数）。タイムライン上部の一目インジケータ。
  function progressHeader() {
    var head = document.createElement('div');
    head.className = 'autorun-progress-head';
    var lhs = document.createElement('div');
    lhs.className = 'autorun-progress-lhs';
    var t = document.createElement('span');
    t.className = 'autorun-progress-title';
    t.textContent = '実行の進行';
    lhs.appendChild(t);
    var approved = stages().filter(function (s) {
      return s.status === 'approved' || s.status === 'skipped';
    }).length;
    var chip = document.createElement('span');
    chip.className = 'autorun-ev-chip';
    var b = document.createElement('b');
    b.textContent = approved + '/' + stages().length;
    chip.append(b, document.createTextNode(' 完了'));
    lhs.appendChild(chip);
    head.appendChild(lhs);
    var logBtn = button('アクティビティログ', function () {
      state.showActivity = true;
      render();
    });
    logBtn.classList.add('autorun-stage-logbtn');
    head.appendChild(logBtn);
    return head;
  }

  function renderPanel() {
    if (state.showActivity) { renderActivityLog(); return; }
    var panel = $('autorun-stage-panel');
    if (!panel || !state.pipeline) return;
    panel.replaceChildren();

    var stage = stageById(state.selected);
    if (!stage) return;
    applySlide(panel, state.lastRendered, stage.stage_id);
    state.lastRendered = stage.stage_id;

    panel.appendChild(progressHeader());

    // 案A（中央の縦タイムライン）＋ 案B（右の成果物キャンバス）。狭幅では縦積み。
    var split = document.createElement('div');
    split.className = 'autorun-stage-split';
    split.appendChild(renderTimeline());
    split.appendChild(renderCanvas(stage));
    panel.appendChild(split);

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

    // 仕様12-13: テストケースは QualityForward と連携できるようにする。
    // API は QF のカラム構成で CSV を返すので、そのまま取り込める形で渡す。
    if (stage.items.length &&
        (stage.stage_id === 'test_cases' || stage.stage_id === 'detail_design')) {
      var qf = button('QualityForward用CSVを取得', function () {
        window.location.href =
          '/api/autorun/stages/testcases?format=csv&domain=' + encodeURIComponent(state.domain);
      });
      qf.disabled = state.busy;
      bar.appendChild(qf);
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
