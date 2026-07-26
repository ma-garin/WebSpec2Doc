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
    lastRendered: '', error: '', artifactKey: '', showContents: false,
  };

  // フェーズごとの代表 HTML 成果物（ジョブの outputs キー）。JSON は削除せず
  // LLM 入力・アクティビティログとして保持し、画面では HTML 版を見せる。
  // 段階と無関係な成果物は出さない。テスト目的を見ている人に
  // テストケースやPlaywright候補を並べても判断の助けにならない（利用者の指摘）。
  var STAGE_ARTIFACT_KEYS = {
    test_objective: ['report_html', 'cross_review'],
    test_plan: ['test_plan', 'viewpoint_snapshot'],
    features: ['report_html', 'model_graph'],
    viewpoints: ['test_analysis', 'viewpoint_snapshot'],
    basic_design: ['test_design', 'model_graph'],
    detail_design: ['test_design', 'test_cases'],
    test_cases: ['test_cases', 'test_design'],
    playwright_automation: ['playwright_candidates_html', 'test_cases'],
  };

  var ARTIFACT_LABELS = {
    report_html: '仕様書',
    cross_review: '横断レビュー',
    test_plan: 'テスト計画',
    viewpoint_snapshot: '観点スナップショット',
    model_graph: 'モデルグラフ',
    test_analysis: 'テスト分析',
    test_design: 'テスト設計',
    test_cases: 'テストケース',
    playwright_candidates_html: 'Playwright候補',
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
    // 段階承認中は右レール（成果物一覧）を出さない。段階と無関係な成果物を
    // 並べず、その段階の成果物だけをパネル内のタブで見せる。
    var ws = document.querySelector('.autorun-workspace');
    if (ws) ws.classList.toggle('is-staging', !!visible);
    var intake = $('autorun-idle-msg');
    if (intake) intake.style.display = visible ? 'none' : '';
    setNavVisible(!!state.pipeline);
  }

  // 段階リストは出さない。生成済みのものを順番に承認させる導線を作らないため
  // （利用者の指摘: 「いちいち順番にやるのはいやです」）。
  function setNavVisible() {
    var group = $('autorun-phase-group');
    var nav = $('autorun-phase-nav');
    if (group) group.style.display = 'none';
    if (nav) nav.style.display = 'none';
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

  // 段階ナビは廃止した。段階ごとに順番へ承認させる導線を作らない方針の下で
  // 常時非表示にされ、段階詳細を描く関数も既に無いため到達できなかった。
  // 非表示のまま DOM に残すと、旧承認モーダルと同じ「押せない・見えないのに
  // セレクタだけ生きている」状態になるため、描画そのものを行わない。
  // 実行の中止。確認ダイアログと後始末は autorun.js 側に一本化する。
  function cancelRun() {
    if (typeof window.autorunCancel === 'function') window.autorunCancel();
  }

  function renderNav() {}

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
      askAssistant(
        '次の項目について改善案を出してください:\n' + item.title + '\n' + item.detail,
        { title: item.title, detail: item.detail }
      );
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

  function askAssistant(text, target) {
    // アシスタントは常駐しないので、相談対象を渡して開く
    if (window.autorunChat && window.autorunChat.open) {
      window.autorunChat.open(target || null);
    }
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
    // この段階に対応する成果物だけを候補にする
    var available = keys.filter(function (k) {
      return outputs[k] && /\.html?$/i.test(outputs[k]);
    });
    if (!available.length) return null;

    var selected = available.indexOf(state.artifactKey) >= 0 ? state.artifactKey : available[0];
    var path = outputs[selected];

    var box = document.createElement('section');
    box.className = 'autorun-stage-artifact';

    var head = document.createElement('div');
    head.className = 'autorun-stage-artifact-head';

    var label = document.createElement('span');
    label.className = 'autorun-stage-artifact-label';
    label.textContent = '成果物';
    head.appendChild(label);

    // 複数ある場合だけタブを出す。1件のときにタブを見せても選ぶものが無い。
    if (available.length > 1) {
      var tabs = document.createElement('div');
      tabs.className = 'autorun-artifact-tabs';
      available.forEach(function (k) {
        var tab = document.createElement('button');
        tab.type = 'button';
        tab.className = 'autorun-artifact-tab' + (k === selected ? ' is-on' : '');
        tab.textContent = ARTIFACT_LABELS[k] || k;
        tab.addEventListener('click', function () {
          state.artifactKey = k;
          renderPanel();
        });
        tabs.appendChild(tab);
      });
      head.appendChild(tabs);
    }

    var open = document.createElement('button');
    open.type = 'button';
    open.className = 'btn-outline-sm qa-preview-btn';
    open.dataset.path = path;
    open.dataset.label = (ARTIFACT_LABELS[selected] || stage.name) + ' の成果物';
    open.textContent = '拡大して開く';
    head.appendChild(open);
    box.appendChild(head);

    var frame = document.createElement('iframe');
    frame.className = 'autorun-stage-artifact-frame';
    frame.src = '/preview?path=' + encodeURIComponent(path);
    frame.title = (ARTIFACT_LABELS[selected] || stage.name) + ' のプレビュー';
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin');
    frame.setAttribute('loading', 'lazy');
    box.appendChild(frame);
    return box;
  }

  // 段階ごとの画面をやめ、1枚の成果物ビューにする。
  // 生成物はすべて出来上がっているので、見たいものをタブで選んで読む。
  function renderArtifactView() {
    var outputs = (window._autoRunLastData && window._autoRunLastData.outputs) || {};
    var keys = Object.keys(ARTIFACT_LABELS).filter(function (k) {
      return outputs[k] && /\.html?$/i.test(outputs[k]);
    });
    if (!keys.length) return null;

    var selected = keys.indexOf(state.artifactKey) >= 0 ? state.artifactKey : keys[0];
    var path = outputs[selected];

    var box = document.createElement('section');
    box.className = 'autorun-stage-artifact';

    var head = document.createElement('div');
    head.className = 'autorun-stage-artifact-head';

    var tabs = document.createElement('div');
    tabs.className = 'autorun-artifact-tabs';
    keys.forEach(function (k) {
      var tab = document.createElement('button');
      tab.type = 'button';
      tab.className = 'autorun-artifact-tab' + (k === selected ? ' is-on' : '');
      tab.textContent = ARTIFACT_LABELS[k] || k;
      tab.addEventListener('click', function () {
        state.artifactKey = k;
        renderPanel();
      });
      tabs.appendChild(tab);
    });
    head.appendChild(tabs);

    var open = document.createElement('button');
    open.type = 'button';
    open.className = 'btn-outline-sm qa-preview-btn';
    open.dataset.path = path;
    open.dataset.label = ARTIFACT_LABELS[selected] || selected;
    open.textContent = '拡大して開く';
    head.appendChild(open);
    box.appendChild(head);

    var frame = document.createElement('iframe');
    frame.className = 'autorun-stage-artifact-frame';
    frame.src = '/preview?path=' + encodeURIComponent(path);
    frame.title = (ARTIFACT_LABELS[selected] || selected) + ' のプレビュー';
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin');
    frame.setAttribute('loading', 'lazy');
    box.appendChild(frame);
    return box;
  }

  function renderPanel() {
    var panel = $('autorun-stage-panel');
    if (!panel || !state.pipeline) return;
    panel.replaceChildren();

    var head = document.createElement('header');
    head.className = 'autorun-stage-head';

    var kicker = document.createElement('div');
    kicker.className = 'section-kicker';
    kicker.textContent = '生成が完了しました';
    head.appendChild(kicker);

    var title = document.createElement('h3');
    title.className = 'autorun-stage-title';
    title.textContent = '成果物';
    head.appendChild(title);

    var purpose = document.createElement('p');
    purpose.className = 'autorun-stage-purpose';
    purpose.textContent =
      'テスト計画からテストケースまで生成済みです。内容を確認したうえで実行してください。';
    head.appendChild(purpose);
    panel.appendChild(head);

    var artifact = renderArtifactView();
    if (artifact) {
      panel.appendChild(artifact);
    } else {
      panel.appendChild(message('プレビューできる成果物がまだありません。'));
    }

    panel.appendChild(renderGeneratedContents());
  }

  // 生成された内容は既定で畳む。読みたい人だけ開けばよい。
  function renderGeneratedContents() {
    var box = document.createElement('section');
    box.className = 'autorun-generated';

    var total = 0;
    stages().forEach(function (s) { total += (s.items || []).length; });

    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'autorun-generated-toggle';
    toggle.textContent =
      (state.showContents ? '▾ ' : '▸ ') + '生成された内容 ' + total + '件';
    toggle.addEventListener('click', function () {
      state.showContents = !state.showContents;
      renderPanel();
    });
    box.appendChild(toggle);

    if (!state.showContents) return box;

    stages().forEach(function (stage) {
      if (!stage.items || !stage.items.length) return;
      var group = document.createElement('div');
      group.className = 'autorun-generated-group';

      var name = document.createElement('div');
      name.className = 'autorun-generated-name';
      name.textContent = stage.name + '（' + stage.items.length + '件）';
      group.appendChild(name);

      var list = document.createElement('div');
      list.className = 'autorun-stage-items';
      stage.items.forEach(function (item) { list.appendChild(itemRow(stage, item)); });
      group.appendChild(list);
      box.appendChild(group);
    });
    return box;
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

    // 承認操作は主導線バー（最上部固定）に一本化する。ここに置くと
    // 同じボタンが2箇所に出て、どちらを押すか迷わせる。
    return bar;
  }

  // ---------------------------------------------------------------- 進行

  // 進行操作は主導線バー（最上部固定）に一本化する。
  // 以前は一覧の最下部に置いていたため、自動承認が3桁になると画面外へ出て
  // 「先に進めない」状態になっていた（利用者の操作で発覚）。
  // 進行操作は主導線バーに一本化し、承認は段階ごとに行わせない。
  // 生成済みのものを7回に分けて承認させる理由がないため、実行条件を
  // まとめて確定するダイアログ（案C）へ集約する。
  function renderProceed() {
    var host = root();
    if (host) {
      var old = host.querySelector('.autorun-stages-proceed');
      if (old) old.remove();
    }
    var leadBar = window.autorunLeadBar;
    if (!leadBar) return;
    if (!state.pipeline) { leadBar.hide(); return; }

    if (state.pipeline.all_approved) {
      leadBar.set({
        tone: state.error ? 'blocked' : 'ready',
        title: '実行条件は確定済みです',
        meta: 'テストを実行できます',
        reason: state.error || '',
        // 実行前でも中止できるようにする（確認の途中で止めたい人の出口）。
        actions: [
          { label: 'テストを実行する', onClick: proceed, disabled: state.busy },
          { label: '中止する', kind: 'danger', onClick: cancelRun, disabled: state.busy },
        ],
      });
      return;
    }

    var counts = itemCounts();
    leadBar.set({
      tone: state.error ? 'blocked' : 'ready',
      title: '生成が完了しました',
      meta: counts.total + '件の内容を確認できます',
      reason: state.error || '',
      actions: [
        { label: '実行する', onClick: openDecisions, disabled: state.busy },
        { label: '中止する', kind: 'danger', onClick: cancelRun, disabled: state.busy },
      ],
    });
  }

  function itemCounts() {
    var total = 0;
    stages().forEach(function (s) { total += (s.items || []).length; });
    return { total: total };
  }

  // 実行条件の確定ダイアログを開く。ここで初めて人に判断を求める。
  function openDecisions() {
    if (!window.autorunDecisions || !window.autorunDecisions.open) return;
    var jobId = (window._autoRunLastData && window._autoRunLastData.job_id) || '';
    window.autorunDecisions.open(state.domain, jobId);
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
    // 失敗の理由は state に持たせる。DOM へ直接足すと、直後の render() で
    // 消えてしまい「押しても何も起きない」ように見えていた（実測で発覚）。
    state.error = '';
    render();
    try {
      await fn();
    } catch (e) {
      state.error = (e && e.message) ? e.message : '操作に失敗しました';
    } finally {
      state.busy = false;
      render();
      focusError();
    }
  }

  // 失敗理由は操作した場所の近くに出し、画面外なら自分で見える位置へ運ぶ。
  function focusError() {
    if (!state.error) return;
    var node = document.querySelector('.autorun-stage-error');
    if (node && node.scrollIntoView) {
      node.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }

  function errorNode() {
    if (!state.error) return null;
    var err = document.createElement('div');
    err.className = 'autorun-stage-error';
    err.setAttribute('role', 'alert');
    err.textContent = state.error;
    return err;
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
    // 進行バーが出ない段階（設計未完了時）でも失敗理由を必ず見せる。
    if (state.error && !document.querySelector('.autorun-stage-error')) {
      var panel = $('autorun-stage-panel');
      var node = errorNode();
      if (panel && node) panel.insertBefore(node, panel.firstChild);
    }
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
