/* 指揮画面（ワークフロー型）。
 *
 * 中央に「今いる工程のカード 1 枚」だけを出す状態機械。中身はサーバから来る
 * current.action.kind で決まる（テンプレート担当が置く DOM に、ここから要素を
 * 追加していく形）。healing-reports.js とはヘルパーを共有しない（IIFE の中に
 * 閉じていて外から呼べないため、必要な分だけこちらにも作る）。
 *
 * 工程は 5 つ（解析 → テスト設計 → 実行 → 分析して直す → 判断）。setup は
 * 工程ではなく、サイト未登録のときだけ出す開始カードの状態（current.key）。
 *
 * HTML 文字列の直接組み込みは使わない。値は必ず textContent で入れ、要素は createElement で組む。
 */
(function () {
  'use strict';

  var IS_ADMIN = document.body.getAttribute('data-hl-admin') === 'true';

  var STEP_STATE_WORD = {
    done: '完了', active: '進行中', human: 'あなたの番', todo: '未着手',
    running: '実行中', cancelled: '中止', failed: '失敗'
  };
  /* 01（view-generate.html）の discover_presets と同じ depth/max_pages（案・T8）。
     既定は「この1画面だけ」——初回は速く1周させ、次に広げる（T2）。 */
  var SCOPE_PRESETS = [
    { id: 'single', label: 'この1画面だけ（目安 1時間・約 250 件）', depth: 1, max: 1, checked: true },
    { id: 'standard', label: '標準（深さ2・最大30画面・目安 半日以上）', depth: 2, max: 30 },
    { id: 'wide', label: '広め（目安 1日以上）', depth: 5, max: 300 }
  ];
  var STAGE_STATUS_WORD = { approved: '承認済み', skipped: '飛ばした', current: '確認待ち', pending: '未着手' };
  /* current.text_source / report.sources.* の出所ラベル。実測 > 入力 > AIの提案 > 前提 > 未確認。 */
  var SRC_LABEL = { measured: '実測', user: '入力', llm: 'AIの提案', assumed: '前提', unverified: '未確認' };
  var WATCH_TIMES = ['7:00', '8:00', '9:00', '12:00', '18:00'];

  /* ---------------- 小さなヘルパー ---------------- */

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text != null) { node.textContent = String(text); }
    return node;
  }

  function on(node, type, fn) {
    if (node) { node.addEventListener(type, fn); }
    return node;
  }

  function byId(id) { return document.getElementById(id); }

  function getJSON(path) {
    return fetch(path).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) { throw new Error((data && data.error) || '読み込みに失敗しました'); }
        return data;
      });
    });
  }

  function postJSON(path, body) {
    return fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          var err = new Error((data && data.error) || '処理に失敗しました');
          err.humanAction = data && data.human_action;
          throw err;
        }
        return data;
      });
    });
  }

  function fmtElapsed(sec) {
    sec = Math.max(0, Math.floor(sec || 0));
    var m = Math.floor(sec / 60), s = sec % 60;
    return m + '分' + (s < 10 ? '0' : '') + s + '秒';
  }

  /* action.items は「配列そのもの」と「{items:[...], count:N} でラップ」の
     両方に対応する（契約に「items の外か中かは両対応」とあるため）。 */
  function extractItems(action) {
    if (!action) { return []; }
    if (Array.isArray(action.items)) { return action.items; }
    if (action.items && Array.isArray(action.items.items)) { return action.items.items; }
    return [];
  }

  /* ---------------- DOM 契約チェック ---------------- */
  /* テンプレート担当が置くはずの要素。無ければ自分で作らず、console.error して止まる。 */

  var DOM = {};

  function checkDom() {
    DOM.card = byId('cw-card');
    DOM.title = byId('cw-card-title');
    DOM.text = byId('cw-card-text');
    DOM.body = byId('cw-card-body');
    DOM.error = byId('cw-card-error');
    DOM.actions = byId('cw-card-actions');
    DOM.stepper = byId('cw-stepper');
    DOM.toast = byId('cw-toast');

    var required = [DOM.card, DOM.title, DOM.text, DOM.body, DOM.error, DOM.actions, DOM.stepper, DOM.toast];
    for (var i = 0; i < required.length; i++) {
      if (!required[i]) {
        console.error('orchestration.js: DOM 契約の必須要素が見つかりません（テンプレート未実装）。');
        return false;
      }
    }
    if (!document.querySelectorAll('#cw-stepper > li.cw-step[data-key]').length) {
      console.error('orchestration.js: #cw-stepper > li.cw-step[data-key] が見つかりません。');
      return false;
    }

    /* 任意（無くても致命的ではない）要素 */
    DOM.src = byId('cw-card-src');
    DOM.site = byId('cw-site');
    DOM.rounds = byId('cw-rounds');
    DOM.restart = byId('cw-restart');
    return true;
  }

  /* ---------------- 状態 ---------------- */

  var state = {
    site: '',
    data: null,
    pollTimer: null,
    elapsedTimer: null,
    elapsedSec: 0,
    roundsCurrent: 0
  };

  function siteFromLocation() {
    var params = new URLSearchParams(window.location.search);
    return params.get('site') || document.body.getAttribute('data-site') || '';
  }

  function setSiteParam(site) {
    var url = new URL(window.location.href);
    if (site) { url.searchParams.set('site', site); } else { url.searchParams.delete('site'); }
    window.history.replaceState(null, '', url.toString());
  }

  function restartFlow() {
    setSiteParam('');
    load('');
  }

  /* ---------------- 取得・送信 ---------------- */

  function load(site) {
    var qs = site ? ('?site=' + encodeURIComponent(site)) : '';
    getJSON('/api/orchestration/workflow' + qs).then(function (data) {
      state.site = data.domain || site || '';
      state.data = data;
      render(data);
    }).catch(function (e) {
      renderLoadError(e.message);
    });
  }

  function renderLoadError(message) {
    stopPolling();
    stopElapsedTimer();
    if (DOM.title) { DOM.title.textContent = '読み込みに失敗しました'; }
    if (DOM.text) { DOM.text.textContent = ''; }
    if (DOM.body) { DOM.body.textContent = ''; }
    if (DOM.actions) { DOM.actions.textContent = ''; }
    showCardError(message);
  }

  function showCardError(message) {
    if (!DOM.error) { return; }
    DOM.error.textContent = message || '';
    DOM.error.hidden = !message;
  }
  function clearCardError() { showCardError(''); }

  function toast(message) {
    if (!DOM.toast) { return; }
    DOM.toast.textContent = message;
    DOM.toast.hidden = false;
    setTimeout(function () { DOM.toast.hidden = true; }, 3000);
  }

  function sendAction(kind, extra, button, successMessage) {
    clearCardError();
    if (button) { button.disabled = true; }
    var body = Object.assign({ site: state.site, kind: kind }, extra || {});
    return postJSON('/api/orchestration/workflow/actions', body).then(function (data) {
      state.data = data;
      if (data.domain && data.domain !== state.site) {
        state.site = data.domain;
        setSiteParam(data.domain);
      }
      render(data);
      if (successMessage) { toast(successMessage); }
      return data;
    }).catch(function (e) {
      if (button) { button.disabled = false; }
      showCardError((e.humanAction ? e.humanAction + '　' : '') + e.message);
      throw e;
    });
  }

  /* ---------------- 描画: ルート ---------------- */

  function render(data) {
    maybeToastRoundChange(data);
    renderSiteSwitcher(data);
    renderRounds(data);
    renderRestart(data);
    renderStepper(data);
    renderCard(data);
  }

  /* 周回（rounds.current）が前回描画より増えていたら、無言で経過が
     巻き戻ったように見えないよう一言添える。初回読み込み（roundsCurrent
     が未設定の 0）では出さない。 */
  function maybeToastRoundChange(data) {
    var r = data.rounds || {};
    var current = r.current || 1;
    if (state.roundsCurrent && current > state.roundsCurrent) {
      toast(current + ' 周目に入りました');
    }
    state.roundsCurrent = current;
  }

  function renderSiteSwitcher(data) {
    if (!DOM.site) { return; }
    var sites = data.sites || [];
    if (sites.length < 2) { DOM.site.hidden = true; return; }
    DOM.site.hidden = false;
    DOM.site.textContent = '';
    sites.forEach(function (s) {
      var opt = el('option', null, s.label || s.domain);
      opt.value = s.domain;
      if (s.domain === data.domain) { opt.selected = true; }
      DOM.site.appendChild(opt);
    });
  }

  function renderRounds(data) {
    if (!DOM.rounds) { return; }
    var r = data.rounds || { current: 1, total: 1 };
    DOM.rounds.textContent = (r.current || 1) + ' 周目 / ' + (r.total || 1);
  }

  /* 「最初から」は、まだ何も進んでいない（全工程 todo）ときは意味が無いので隠す。 */
  function renderRestart(data) {
    if (!DOM.restart) { return; }
    var steps = data.steps || [];
    var hasProgress = steps.some(function (s) { return s.state !== 'todo'; });
    DOM.restart.hidden = !hasProgress;
  }

  /* サイト未登録（current.key === 'setup'）のときは進める工程が無いので、
     ステッパーごと隠す（setup は工程ではなく開始カードの状態のため）。 */
  function renderStepper(data) {
    var current = data.current || {};
    var steps = data.steps || [];
    if (current.key === 'setup' || !steps.length) {
      DOM.stepper.hidden = true;
      return;
    }
    DOM.stepper.hidden = false;
    var byKey = {};
    steps.forEach(function (s) { byKey[s.key] = s; });
    var items = document.querySelectorAll('#cw-stepper > li.cw-step[data-key]');
    Array.prototype.forEach.call(items, function (li) {
      var key = li.getAttribute('data-key');
      var step = byKey[key];
      if (!step) { return; }
      li.setAttribute('data-state', step.state);
      var no = li.querySelector('.cw-step-no');
      if (no) { no.textContent = step.state === 'done' ? '✓' : String(step.no); }
      var stEl = li.querySelector('.cw-step-state');
      if (stEl) { stEl.textContent = STEP_STATE_WORD[step.state] || ''; }
    });
  }

  /* done の番号クリックで、結果 1 文を #cw-card-text の下にトグル表示する。 */
  function findStepLi(node) {
    while (node && node !== DOM.stepper) {
      if (node.tagName === 'LI' && node.classList && node.classList.contains('cw-step')) { return node; }
      node = node.parentNode;
    }
    return null;
  }

  function bindStepperDelegate() {
    on(DOM.stepper, 'click', function (ev) {
      var li = findStepLi(ev.target);
      if (!li || li.getAttribute('data-state') !== 'done') { return; }
      var key = li.getAttribute('data-key');
      var steps = (state.data && state.data.steps) || [];
      var step = steps.filter(function (s) { return s.key === key; })[0];
      if (!step) { return; }
      toggleStepSummary(step);
    });
  }

  function ensureStepSummaryEl() {
    var existing = byId('cw-step-summary');
    if (existing) { return existing; }
    var node = el('p', 'cw-step-summary-line');
    node.id = 'cw-step-summary';
    node.hidden = true;
    if (DOM.text && DOM.text.parentNode) {
      DOM.text.parentNode.insertBefore(node, DOM.text.nextSibling);
    }
    return node;
  }

  function toggleStepSummary(step) {
    var node = ensureStepSummaryEl();
    if (!node.hidden && node.getAttribute('data-step-key') === step.key) {
      node.hidden = true;
      return;
    }
    node.hidden = false;
    node.setAttribute('data-step-key', step.key);
    node.textContent = step.summary || '';
  }

  /* ---------------- 描画: カード ---------------- */

  /* カード本文の右上に出す出所（実測 / 入力 / AIの提案 / 前提 / 未確認）。
     current.text_source が無い・未知の値なら何も出さない（嘘の出所を作らない）。 */
  function renderSourceLabel(current) {
    if (!DOM.src) { return; }
    var label = SRC_LABEL[current.text_source] || '';
    DOM.src.textContent = label;
    DOM.src.hidden = !label;
  }

  function renderCard(data) {
    var current = data.current || {};
    clearCardError();
    DOM.title.textContent = current.headline || '';
    DOM.text.textContent = current.text || '';
    DOM.body.textContent = '';
    DOM.actions.textContent = '';
    renderSourceLabel(current);

    var isRetry = current.state === 'failed' || current.state === 'cancelled';
    if (isRetry) {
      showCardError(current.error || (current.state === 'cancelled' ? '中止しました。' : '失敗しました。'));
    }

    if (current.state === 'running') {
      renderRunningBody(current);
    } else {
      renderBody(current, data);
    }

    if (!IS_ADMIN) {
      DOM.actions.appendChild(el('p', 'cw-waiting', '操作は管理者が行います'));
    } else if (current.state === 'running') {
      renderRunningActions();
    } else {
      renderActions(current, data, isRetry);
    }

    manageElapsed(current);
    managePolling(current);
  }

  /* #cw-card-text に工程の 1 文が既に出ているため、ここでは経過だけを出す
     （同じ文を二重に表示しない）。 */
  function renderRunningBody(current) {
    var p = el('p', 'cw-waiting', '経過 ');
    var span = el('span', 'cw-elapsed', fmtElapsed(current.elapsed_sec || 0));
    p.appendChild(span);
    DOM.body.appendChild(p);
  }

  function renderRunningActions() {
    var btn = el('button', 'btn-outline-sm', 'やめる');
    btn.type = 'button';
    on(btn, 'click', function () { sendAction('cancel', {}, btn); });
    DOM.actions.appendChild(btn);
  }

  function renderBody(current, data) {
    var action = current.action || {};
    switch (action.kind) {
      case 'start': return renderStartBody(data);
      case 'login': return renderLoginBody();
      case 'approve_stage': return renderDesignBody(action);
      case 'connect': return renderConnectBody(action);
      case 'decide_report': return renderDecideReportBody(action);
      case 'decide_bundle': return renderDecideBundleBody(action);
      case 'monitor': return renderMonitorBody(action);
      default: return; /* another_round / none: 追加の本文は無い */
    }
  }

  function renderActions(current, data, isRetry) {
    var action = current.action || {};
    switch (action.kind) {
      case 'start': return renderStartActions(action);
      case 'login': return renderLoginActions(action);
      case 'approve_stage': return; /* 承認・差し戻しボタンは現在の段階の行の中 */
      case 'connect': return renderConnectActions(action);
      case 'decide_report': return; /* 判断ボタンは各 article.cw-report の中 */
      case 'decide_bundle': return; /* 判断ボタンは各 article.cw-report の中 */
      case 'another_round': return renderAnotherRoundActions(action, isRetry);
      case 'monitor': return renderMonitorActions(action);
      default:
        if (isRetry) { renderAnotherRoundActions(action, true); }
        return;
    }
  }

  /* ---- kind: start（サイトの URL を 1 本だけ聞く） ---- */

  function renderStartBody() {
    var form = el('form', 'cw-form');
    form.id = 'cw-start-form';

    var urlField = el('label', 'cw-field cw-wide');
    urlField.appendChild(el('span', 'cw-field-label', 'サイトの URL'));
    var urlInput = document.createElement('input');
    urlInput.type = 'url';
    urlInput.className = 'cw-input';
    urlInput.id = 'cw-f-url';
    urlInput.placeholder = 'https://example.jp/path';
    urlField.appendChild(urlInput);
    form.appendChild(urlField);

    var scopeField = el('div', 'cw-field cw-wide');
    scopeField.appendChild(el('span', 'cw-field-label', '解析する範囲'));
    var scopeGroup = el('div', 'cw-scope-group');
    SCOPE_PRESETS.forEach(function (preset, i) {
      var label = el('label', 'cw-scope-option');
      var input = document.createElement('input');
      input.type = 'radio';
      input.name = 'cw-scope';
      input.id = 'cw-f-scope-' + preset.id;
      input.value = preset.id;
      input.checked = !!preset.checked;
      input.setAttribute('data-depth', String(preset.depth));
      input.setAttribute('data-max', String(preset.max));
      label.appendChild(input);
      label.appendChild(document.createTextNode(' ' + preset.label));
      scopeGroup.appendChild(label);
    });
    scopeField.appendChild(scopeGroup);
    form.appendChild(scopeField);

    DOM.body.appendChild(form);
    DOM.body.appendChild(el('p', 'cw-hint',
      '解析 → テスト設計 → 実行 → 分析して直す → 判断 の順に進みます。必要な情報はその時に聞きます'));
  }

  function renderStartActions(action) {
    var btn = el('button', 'btn-primary', action.primary || '解析を始める');
    btn.type = 'button';
    on(btn, 'click', function () { submitStart(btn); });
    DOM.actions.appendChild(btn);
  }

  function submitStart(button) {
    var url = (byId('cw-f-url') || {}).value || '';
    if (!url.trim()) { showCardError('サイトの URL を入れてください。'); return; }
    /* 新規サイト登録なので site は必ず空で送る（切替コンボの現在値を使わない）。
       契約どおり body は {site, kind, url, depth, max_pages}。 */
    var body = { site: '', url: url.trim() };
    var scope = document.querySelector('input[name="cw-scope"]:checked');
    if (scope) {
      body.depth = parseInt(scope.getAttribute('data-depth'), 10);
      body.max_pages = parseInt(scope.getAttribute('data-max'), 10);
    }
    sendAction('start', body, button);
  }

  /* ---- kind: login（解析中・ログイン待ち） ---- */

  function renderLoginBody() {
    DOM.body.appendChild(el('p', 'cw-waiting', 'ログイン画面を開いてから、ログインしたボタンを押してください。'));
  }

  function renderLoginActions(action) {
    var items = extractItems(action);
    var loginUrl = (items[0] && items[0].login_url) || '';

    var openBtn = el('button', 'btn-outline-sm', 'ログイン画面を開く');
    openBtn.type = 'button';
    on(openBtn, 'click', function () {
      if (loginUrl) { window.open(loginUrl, '_blank', 'noopener'); }
    });
    DOM.actions.appendChild(openBtn);

    var doneBtn = el('button', 'btn-primary', action.primary || 'ログインした');
    doneBtn.type = 'button';
    on(doneBtn, 'click', function () { sendAction('login_done', {}, doneBtn); });
    DOM.actions.appendChild(doneBtn);
  }

  /* ---- kind: approve_stage（テスト設計・8 段階を要確認キュー越しに出す） ---- */

  function renderDesignBody(action) {
    var items = extractItems(action);
    var list = el('ol', 'cw-stage-list');
    items.forEach(function (stage) {
      list.appendChild(buildStageRow(stage));
    });
    DOM.body.appendChild(list);
  }

  /* 「自動で確認済み」: 段階そのものが要確認 0 件のまま承認された（＝人が
     個別に見る必要が無かった）ことを表す語。approved かつ review_count===0
     かつ auto_approved>0（自動承認の対象が実際にあった）のときだけ出す。 */
  function stageStateText(stage) {
    if (stage.status === 'approved' && !(stage.review_count || 0) && (stage.auto_approved || 0) > 0) {
      return '自動で確認済み';
    }
    return STAGE_STATUS_WORD[stage.status] || '';
  }

  function buildAutoApprovedLine(stage) {
    return el('p', 'cw-hint', '自動で確認済み ' + (stage.auto_approved || 0) + '件');
  }

  /* 要確認の項目だけを列挙する（理由は薄字: cw-hint を流用）。 */
  function buildReviewList(stage) {
    var box = el('div', 'cw-stage-review');
    (stage.review || []).forEach(function (item) {
      var line = el('p', 'cw-stage-review-item');
      line.appendChild(el('span', null, item.text));
      line.appendChild(el('span', 'cw-hint', '　' + item.reason));
      box.appendChild(line);
    });
    return box;
  }

  function buildStageRow(stage) {
    var li = el('li', 'cw-stage');
    li.setAttribute('data-status', stage.status);
    li.appendChild(el('span', 'cw-stage-no', stage.no));
    li.appendChild(el('span', 'cw-stage-name', stage.name));

    if (stage.status === 'current') {
      var count = (stage.approved_count || 0) + ' / ' + (stage.item_count || 0) + ' 件承認';
      li.appendChild(el('span', 'cw-stage-count', count));
      li.appendChild(buildAutoApprovedLine(stage));
      li.appendChild(buildReviewList(stage));
      li.appendChild(buildStageActions(stage));
    } else {
      li.appendChild(el('span', 'cw-stage-state', stageStateText(stage)));
    }
    return li;
  }

  function buildStageActions(stage) {
    var box = el('div', 'cw-stage-actions');

    var approveBtn = el('button', 'btn-primary', '確認して次へ');
    approveBtn.type = 'button';
    on(approveBtn, 'click', function () {
      sendAction('approve_stage', { stage_id: stage.stage_id }, approveBtn, '承認しました');
    });
    box.appendChild(approveBtn);

    var returnBtn = el('button', 'btn-outline-sm', '差し戻す（メモ）');
    returnBtn.type = 'button';
    var memoBox = buildMemoBox(function (note) {
      sendAction('return_stage', { stage_id: stage.stage_id, note: note }, returnBtn, '差し戻しました。作り直します');
    });
    memoBox.hidden = true;
    on(returnBtn, 'click', function () { memoBox.hidden = !memoBox.hidden; });
    box.appendChild(returnBtn);
    box.appendChild(memoBox);
    return box;
  }

  /* ---- kind: connect（分析して直す・コードの場所を聞く） ---- */

  function renderConnectBody(action) {
    var items = extractItems(action);
    var form = el('form', 'cw-form');
    form.id = 'cw-connect-form';

    var repoField = el('label', 'cw-field cw-wide');
    repoField.appendChild(el('span', 'cw-field-label', 'コードの場所'));
    var select = document.createElement('select');
    select.className = 'cw-input';
    select.id = 'cw-f-connect-repo';
    items.forEach(function (it) {
      var opt = el('option', null, it.label || it.path);
      opt.value = it.path;
      select.appendChild(opt);
    });
    repoField.appendChild(select);
    form.appendChild(repoField);

    var details = document.createElement('details');
    details.className = 'cw-details';
    var summary = document.createElement('summary');
    summary.textContent = '詳しい設定';
    details.appendChild(summary);
    var verifyField = el('label', 'cw-field');
    verifyField.appendChild(el('span', 'cw-field-label', '検証コマンド'));
    var verifyInput = document.createElement('input');
    verifyInput.type = 'text';
    verifyInput.className = 'cw-input';
    verifyInput.id = 'cw-f-connect-verify';
    verifyInput.value = (items[0] && items[0].verify_command) || '';
    verifyField.appendChild(verifyInput);
    details.appendChild(verifyField);
    form.appendChild(details);

    on(select, 'change', function () {
      var repo = items.filter(function (r) { return r.path === select.value; })[0];
      verifyInput.value = repo ? (repo.verify_command || '') : '';
    });

    DOM.body.appendChild(form);
  }

  function renderConnectActions(action) {
    var btn = el('button', 'btn-primary', action.primary || 'この場所を使う');
    btn.type = 'button';
    on(btn, 'click', function () { submitConnect(btn); });
    DOM.actions.appendChild(btn);
  }

  function submitConnect(button) {
    var select = byId('cw-f-connect-repo');
    var repo = select ? select.value : '';
    if (!repo) { showCardError('コードの場所を選んでください。'); return; }
    var verifyInput = byId('cw-f-connect-verify');
    sendAction('connect', {
      repo: repo,
      verify_command: verifyInput ? verifyInput.value : ''
    }, button).catch(function (e) {
      showDetailsErrorIfNeeded('cw-connect-form', (e && e.message) || '');
    });
  }

  /* 検証コマンドが決められなかった 400 のときは、「詳しい設定」を開いて
     その直下にも理由を出す（折りたたみの中にある必須項目のため）。 */
  function showDetailsErrorIfNeeded(formId, message) {
    if (message.indexOf('検証コマンド') === -1) { return; }
    var form = byId(formId);
    var details = form ? form.querySelector('.cw-details') : null;
    if (!details) { return; }
    details.open = true;
    var note = byId('cw-details-error');
    if (!note) {
      note = el('p', 'cw-field-error');
      note.id = 'cw-details-error';
      details.parentNode.insertBefore(note, details.nextSibling);
    }
    note.textContent = message;
    /* 同じ文をカード下の赤字と二重に出さない（通し検証で指摘） */
    if (DOM.error) { DOM.error.textContent = ''; DOM.error.hidden = true; }
  }

  /* ---- kind: decide_report（判断） ---- */

  function renderDecideReportBody(action) {
    var items = extractItems(action);
    items.forEach(function (report) {
      DOM.body.appendChild(buildReportArticle(report));
    });
  }

  function buildFactRow(dl, label, text, srcWord) {
    dl.appendChild(el('dt', null, label));
    var dd = el('dd');
    dd.appendChild(document.createTextNode(text || '—'));
    if (srcWord) {
      dd.appendChild(document.createTextNode(' '));
      dd.appendChild(el('span', 'cw-src', srcWord));
    }
    dl.appendChild(dd);
  }

  function buildReportArticle(report) {
    var sources = report.sources || {};
    var art = el('article', 'cw-report');
    art.setAttribute('data-report-id', report.report_id);
    art.appendChild(el('h3', 'cw-report-title', report.title || '（件名なし）'));

    var dl = el('dl', 'cw-report-facts');
    buildFactRow(dl, '事象', report.incident_text, SRC_LABEL[sources.incident]);
    buildFactRow(dl, '原因', report.cause_text, SRC_LABEL[sources.cause]);
    buildFactRow(dl, '対応', report.action_text, SRC_LABEL[sources.action]);
    art.appendChild(dl);

    var verifyP = el('p', 'cw-report-verify');
    verifyP.appendChild(document.createTextNode('検証　修正前 '));
    verifyP.appendChild(el('span', 'cw-badge-err', report.verify_before || '—'));
    verifyP.appendChild(document.createTextNode(' → 修正後 '));
    var afterCls = report.verify_after_ok === false ? 'cw-badge-err' : 'cw-badge-ok';
    verifyP.appendChild(el('span', afterCls, report.verify_after || '—'));
    var verifySrc = SRC_LABEL[sources.verify];
    if (verifySrc) {
      verifyP.appendChild(document.createTextNode(' '));
      verifyP.appendChild(el('span', 'cw-src', verifySrc));
    }
    art.appendChild(verifyP);

    if (report.fix_target === 'script') {
      art.appendChild(el('p', 'cw-report-note',
        'テストの探し方を直しました。サイトのコードは変更していません'));
    }

    art.appendChild(buildReportActions(report));
    return art;
  }

  function buildReportActions(report) {
    var box = el('div', 'cw-report-actions');

    var approveLabel = report.primary || (report.fix_target === 'script' ? '承認' : '承認して修正を送る');
    var approveBtn = el('button', 'btn-primary', approveLabel);
    approveBtn.type = 'button';
    on(approveBtn, 'click', function () {
      var msg = report.fix_target === 'script' ? '承認しました' : '承認しました。開発者に修正を送ります';
      sendAction('decide_report', { report_id: report.report_id, action: 'approve', note: '' }, approveBtn, msg);
    });
    box.appendChild(approveBtn);
    if (report.fix_target !== 'script') {
      box.appendChild(el('p', 'cw-hint', '開発者には PR として届きます'));
    }

    var returnBtn = el('button', 'btn-outline-sm', '差し戻す');
    returnBtn.type = 'button';
    var memoBox = buildMemoBox(function (note) {
      sendAction('decide_report', { report_id: report.report_id, action: 'return', note: note },
        returnBtn, '差し戻しました。作り直します');
    });
    memoBox.hidden = true;
    on(returnBtn, 'click', function () { memoBox.hidden = !memoBox.hidden; });
    box.appendChild(returnBtn);

    var rejectBtn = el('button', 'hl-btn-danger', '却下');
    rejectBtn.type = 'button';
    var confirmBox = buildConfirmBox('本当に却下しますか？', function () {
      sendAction('decide_report', { report_id: report.report_id, action: 'reject', note: '' },
        rejectBtn, '却下しました');
    });
    confirmBox.hidden = true;
    on(rejectBtn, 'click', function () { confirmBox.hidden = !confirmBox.hidden; });
    box.appendChild(rejectBtn);

    box.appendChild(memoBox);
    box.appendChild(confirmBox);
    return box;
  }

  /* ---- kind: decide_bundle（判断・画面 × 観点の束単位。案3） ---- */

  function renderDecideBundleBody(action) {
    var items = extractItems(action);
    items.forEach(function (bundle) {
      DOM.body.appendChild(buildBundleArticle(bundle));
    });
  }

  function buildBundleArticle(bundle) {
    var sources = bundle.sources || {};
    var art = el('article', 'cw-report');
    art.setAttribute('data-bundle-id', bundle.bundle_id);
    art.appendChild(el('h3', 'cw-report-title', bundle.title || '（画面不明）'));

    var dl = el('dl', 'cw-report-facts');
    buildFactRow(dl, '件数',
      (bundle.count || 0) + ' 件（うち承認待ち ' + (bundle.awaiting_count || 0) + '）', '');
    buildFactRow(dl, '理由', bundle.review_reason, SRC_LABEL[sources.cause]);
    buildFactRow(dl, '検証',
      (bundle.verify_after_ok_count || 0) + ' / ' + (bundle.count || 0) + ' 件が通過',
      SRC_LABEL[sources.verify]);
    art.appendChild(dl);

    var link = el('a', 'cw-link', '個票を見る');
    link.href = '/healing/bundles/' + encodeURIComponent(bundle.bundle_id);
    link.target = '_blank';
    link.rel = 'noopener';
    art.appendChild(link);

    art.appendChild(buildBundleActions(bundle));
    return art;
  }

  function buildBundleActions(bundle) {
    var box = el('div', 'cw-report-actions');
    var fixTargets = bundle.fix_targets || [];
    var scriptOnly = fixTargets.length > 0 && fixTargets.every(function (t) { return t === 'script'; });

    var approveLabel = bundle.primary || (scriptOnly ? '承認' : '承認して修正を送る');
    var approveBtn = el('button', 'btn-primary', approveLabel);
    approveBtn.type = 'button';
    on(approveBtn, 'click', function () {
      var msg = scriptOnly ? '承認しました' : '承認しました。開発者に修正を送ります';
      sendAction('decide_bundle', { bundle_id: bundle.bundle_id, action: 'approve', note: '' },
        approveBtn, msg);
    });
    box.appendChild(approveBtn);
    if (!scriptOnly) {
      box.appendChild(el('p', 'cw-hint', '開発者には PR として届きます'));
    }

    var returnBtn = el('button', 'btn-outline-sm', '差し戻す');
    returnBtn.type = 'button';
    var memoBox = buildMemoBox(function (note) {
      sendAction('decide_bundle', { bundle_id: bundle.bundle_id, action: 'return', note: note },
        returnBtn, '差し戻しました。作り直します');
    });
    memoBox.hidden = true;
    on(returnBtn, 'click', function () { memoBox.hidden = !memoBox.hidden; });
    box.appendChild(returnBtn);

    var rejectBtn = el('button', 'hl-btn-danger', '却下');
    rejectBtn.type = 'button';
    var confirmBox = buildConfirmBox('束の中の承認待ち個票をすべて却下しますか？', function () {
      sendAction('decide_bundle', { bundle_id: bundle.bundle_id, action: 'reject', note: '' },
        rejectBtn, '却下しました');
    });
    confirmBox.hidden = true;
    on(rejectBtn, 'click', function () { confirmBox.hidden = !confirmBox.hidden; });
    box.appendChild(rejectBtn);

    box.appendChild(memoBox);
    box.appendChild(confirmBox);
    return box;
  }

  /* 差し戻し共通: メモ欄＋確定ボタン。空なら送らない（通し検証で「無反応」と指摘された箇所）。 */
  function buildMemoBox(onSubmit) {
    var wrap = el('div', 'cw-memo-box');
    var ta = document.createElement('textarea');
    ta.className = 'cw-input';
    ta.placeholder = 'どう直してほしいかを書いてください';
    wrap.appendChild(ta);
    var confirmBtn = el('button', 'btn-outline-sm', 'この内容で差し戻す');
    confirmBtn.type = 'button';
    on(confirmBtn, 'click', function () {
      var note = ta.value.trim();
      if (!note) {
        showCardError('差し戻すときは、どう直してほしいかをメモに書いてください。');
        ta.focus();
        return;
      }
      onSubmit(note);
    });
    wrap.appendChild(confirmBtn);
    return wrap;
  }

  /* 却下共通: 2 段階確認。 */
  function buildConfirmBox(message, onYes) {
    var wrap = el('div', 'cw-confirm-box');
    wrap.appendChild(el('span', null, message));
    var yes = el('button', 'hl-btn-danger', '却下する');
    yes.type = 'button';
    on(yes, 'click', onYes);
    var no = el('button', 'btn-outline-sm', 'やめる');
    no.type = 'button';
    on(no, 'click', function () { wrap.hidden = true; });
    wrap.appendChild(yes);
    wrap.appendChild(no);
    return wrap;
  }

  /* ---- kind: another_round（回数を使い切った後の判断） ---- */

  function renderAnotherRoundActions(action, isRetry) {
    var label = action.primary || (isRetry ? 'もう一度' : 'もう1周する');
    var btn = el('button', 'btn-primary', label);
    btn.type = 'button';
    on(btn, 'click', function () { sendAction('another_round', {}, btn); });
    DOM.actions.appendChild(btn);

    if (action.secondary) {
      var link = el('button', 'cw-link', action.secondary);
      link.type = 'button';
      on(link, 'click', function () {
        /* 契約の action kind 一覧に「ここで終わる」に相当するものが無いため未実装。
           押しても API へは送らず、その旨だけ知らせる（未確認としてレポートに明記）。 */
        console.warn('orchestration.js: 「' + action.secondary + '」に対応する API kind が契約に無いため未実装です。');
        toast('この操作は現在対応していません。');
      });
      DOM.actions.appendChild(link);
    }
  }

  /* ---- kind: monitor（終わりました・見張り設定） ---- */

  function renderMonitorBody(action) {
    var items = extractItems(action);
    var cfg = items[0] || {};
    var wrap = el('div', 'cw-form');
    var label = el('label', 'cw-field');
    label.appendChild(el('span', 'cw-field-label', '見張りの時刻'));
    var select = document.createElement('select');
    select.className = 'cw-input';
    select.id = 'cw-f-watch';
    WATCH_TIMES.forEach(function (t) {
      var opt = el('option', null, t);
      opt.value = t;
      if (t === cfg.monitor_time) { opt.selected = true; }
      select.appendChild(opt);
    });
    label.appendChild(select);
    wrap.appendChild(label);
    DOM.body.appendChild(wrap);
  }

  function renderMonitorActions(action) {
    var btn = el('button', 'btn-primary', action.primary || '見張りの時刻を変える');
    btn.type = 'button';
    on(btn, 'click', function () {
      var select = byId('cw-f-watch');
      var value = select ? select.value : '';
      sendAction('monitor', { monitor_enabled: true, monitor_time: value }, btn, '見張りの時刻を変更しました');
    });
    DOM.actions.appendChild(btn);

    if (action.secondary) {
      var link = el('button', 'cw-link', action.secondary);
      link.type = 'button';
      on(link, 'click', restartFlow);
      DOM.actions.appendChild(link);
    }
  }

  /* ---------------- 経過時間・ポーリング ---------------- */

  function stopElapsedTimer() {
    if (state.elapsedTimer) { clearInterval(state.elapsedTimer); state.elapsedTimer = null; }
  }

  function manageElapsed(current) {
    stopElapsedTimer();
    if (current.state !== 'running') { return; }
    state.elapsedSec = current.elapsed_sec || 0;
    state.elapsedTimer = setInterval(function () {
      state.elapsedSec += 1;
      var span = document.querySelector('#cw-card-body .cw-elapsed');
      if (span) { span.textContent = fmtElapsed(state.elapsedSec); }
    }, 1000);
  }

  function stopPolling() {
    if (state.pollTimer) { clearTimeout(state.pollTimer); state.pollTimer = null; }
  }

  /* running のときだけ 5 秒毎に GET。タブが非表示の間は止め、
     visibilitychange で戻ってきたときに再開する。 */
  function managePolling(current) {
    stopPolling();
    if (current.state !== 'running') { return; }
    if (document.hidden) { return; }
    state.pollTimer = setTimeout(function () { load(state.site); }, 5000);
  }

  function onVisibilityChange() {
    if (!document.hidden && state.data && state.data.current &&
        state.data.current.state === 'running' && !state.pollTimer) {
      managePolling(state.data.current);
    }
  }

  /* ---------------- 起動 ---------------- */

  function init() {
    if (document.body.getAttribute('data-mode') === 'home') { return; }
    if (!checkDom()) { return; }
    bindStepperDelegate();
    on(DOM.site, 'change', function () {
      var v = DOM.site.value;
      setSiteParam(v);
      load(v);
    });
    on(DOM.restart, 'click', function (ev) {
      ev.preventDefault();
      restartFlow();
    });
    document.addEventListener('visibilitychange', onVisibilityChange);
    load(siteFromLocation());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  /* テスト用に描画関数を公開する（サーバ無しでの疎通確認用）。 */
  window.__cw = { render: render, checkDom: checkDom, state: state, load: load };
})();

/* 指揮ホーム（日常運用）。全サイトの状態を /api/home/summary 1 本で出す。
 * 部品は window.WS2D（c-hybrid.js）。文字は textContent で入れる。 */
(function () {
  'use strict';
  if (document.body.getAttribute('data-mode') !== 'home') { return; }
  var W = window.WS2D;
  var VIEWS = [
    { key: 'all', label: 'すべて' }, { key: 'human', label: '人の対応待ち' },
    { key: 'failed', label: '失敗' }, { key: 'unverified', label: '未確認' }
  ];
  var SOURCE_NAME = {
    sites: 'サイト一覧', runs: '実行記録', projects: '保守プロジェクト', reports: '報告書',
    failures: '失敗テスト', evidence: '根拠（リバース解析）'
  };
  var STAGE_NONE = '—';
  var data = null;
  var view = 'all';

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text !== undefined && text !== null) { n.textContent = text; }
    return n;
  }
  function clear(n) { while (n.firstChild) { n.removeChild(n.firstChild); } }
  function viewFromLocation() {
    var v = new URLSearchParams(window.location.search).get('view') || 'all';
    return VIEWS.some(function (x) { return x.key === v; }) ? v : 'all';
  }
  function fmtAt(ts) {
    if (!ts) { return '—'; }
    var m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(ts);
    return m ? (m[2] + '/' + m[3] + ' ' + m[4] + ':' + m[5]) : ts;
  }

  /* サーバの filter_sites と同じ条件（絞り込みはクライアントで行う）。 */
  function filterSites(sites, v) {
    return sites.filter(function (s) {
      if (v === 'human') { return !!s.human_action; }
      if (v === 'failed') { return s.status === 'failed' || !!s.latest_failure; }
      if (v === 'unverified') {
        return s.status === 'unverified' || !!(s.evidence && s.evidence.unverified > 0);
      }
      return true;
    });
  }

  function setView(v, push) {
    view = v;
    var url = new URL(window.location.href);
    if (v === 'all') { url.searchParams.delete('view'); } else { url.searchParams.set('view', v); }
    if (push) { window.history.pushState({ view: v }, '', url.toString()); }
    renderTabs();
    renderList();
  }

  /* ---------- 帯・KPI ---------- */

  function renderSplit() {
    var host = $('ch-split');
    clear(host);
    var sum = { fact: 0, inference: 0, unverified: 0 };
    var any = false;
    (data.sites || []).forEach(function (s) {
      if (s.evidence) {
        any = true;
        sum.fact += s.evidence.fact; sum.inference += s.evidence.inference; sum.unverified += s.evidence.unverified;
      }
    });
    [['fact', '事実（実測・記録）'], ['inference', '推論（静的・推論・曖昧）'], ['unverified', '未確認']].forEach(function (c) {
      var cell = el('div', 'c-split__cell c-split__cell--' + c[0]);
      cell.appendChild(el('span', 'c-split__label', c[1]));
      cell.appendChild(el('span', 'c-split__value', any ? String(sum[c[0]]) : '未計測'));
      host.appendChild(cell);
    });
  }

  function renderKpis() {
    var c = data.counts || {};
    function go(v) { return function () { setView(v, true); var b = $('ch-body'); if (b) { b.focus(); } }; }
    var items = [
      { label: '全サイト', value: c.sites, onClick: go('all') },
      { label: '正常', value: c.ok, sub: '完了のみ。一部完了は含めない', onClick: go('all') },
      { label: '実行中', value: c.running, onClick: go('all') },
      { label: '失敗', value: c.failed, onClick: go('failed') },
      { label: '人の対応待ち', value: c.human_action, onClick: go('human') },
      { label: '承認待ち', value: c.awaiting_approval, sub: '修正案の報告書', onClick: go('human') },
      { label: '未確認', value: c.unverified, sub: '解析結果があるサイトのみ', category: 'unverified', onClick: go('unverified') },
      { label: '今日の変更', value: c.changes_today, sub: '集計元なし' },
      { label: '今日のテスト', value: c.tests_today, sub: '実行の回数' },
      { label: '今日の修正', value: c.fixes_today, sub: '直す工程の回数' },
      { label: '今日の報告', value: c.reports_today }
    ];
    W.kpis($('ch-kpis'), items);
  }

  function renderReason() {
    var c = data.counts || {};
    var text;
    if (c.sites === null || c.sites === undefined) {
      text = 'サイト一覧を取得できていません。数字は未計測です。';
    } else if (c.sites === 0) {
      text = 'サイトがまだありません。追加すると、ここに状態が並びます。';
    } else {
      var parts = [c.sites + ' サイト'];
      if (c.failed) { parts.push('失敗 ' + c.failed); }
      if (c.human_action) { parts.push('人の対応待ち ' + c.human_action); }
      if (!c.failed && !c.human_action) { parts.push('失敗・対応待ちはありません'); }
      text = parts.join(' ／ ') + '（' + fmtAt(data.updated_at) + ' 時点）';
    }
    W.reason($('ch-reason'), text, (data.partial_errors || []).length ? 'warning' : undefined);
  }

  function renderBanner(errorInfo) {
    var host = $('ch-banner');
    clear(host);
    if (errorInfo) {
      W.state(host, { kind: 'error', title: '最新の状態を取得できませんでした', message: errorInfo,
        retained: !!data, next: '再読み込みを押してください。', actionLabel: '再読み込み', onAction: load });
      return;
    }
    var errs = (data && data.partial_errors) || [];
    if (errs.length) {
      var names = errs.map(function (e) { return SOURCE_NAME[e] || e; }).join('・');
      W.state(host, { kind: 'partial', message: '取得できなかった情報: ' + names + '。該当する数字は「未計測」と表示しています。',
        next: '時間をおいて再読み込みしてください。', actionLabel: '再読み込み', onAction: load });
    }
  }

  /* ---------- タブ・表 ---------- */

  function renderTabs() {
    var host = $('ch-tabs');
    clear(host);
    VIEWS.forEach(function (v, i) {
      var b = el('button', null, v.label);
      b.type = 'button';
      b.setAttribute('role', 'tab');
      b.id = 'ch-tab-' + v.key;
      b.setAttribute('aria-selected', v.key === view ? 'true' : 'false');
      b.setAttribute('aria-controls', 'ch-body');
      b.tabIndex = v.key === view ? 0 : -1;
      if (data) {
        b.appendChild(el('span', 'ch-tab-n', ' ' + filterSites(data.sites || [], v.key).length));
      }
      b.addEventListener('click', function () { setView(v.key, true); });
      b.addEventListener('keydown', function (ev) {
        var d = ev.key === 'ArrowRight' ? 1 : (ev.key === 'ArrowLeft' ? -1 : 0);
        if (!d) { return; }
        ev.preventDefault();
        var next = VIEWS[(i + d + VIEWS.length) % VIEWS.length];
        setView(next.key, true);
        var t = $('ch-tab-' + next.key);
        if (t) { t.focus(); }
      });
      host.appendChild(b);
    });
    $('ch-body').setAttribute('aria-labelledby', 'ch-tab-' + view);
  }

  function cell(tr, label, node) {
    var td = el('td');
    td.setAttribute('data-label', label);
    if (typeof node === 'string') { td.textContent = node; } else if (node) { td.appendChild(node); }
    tr.appendChild(td);
    return td;
  }
  function badge(html) { var s = el('span'); s.innerHTML = html; return s; }

  function evidenceCell(ev) {
    var box = el('span', 'ch-ev');
    if (!ev) { box.appendChild(badge(W.evidence.html('unverified', '未確認（解析結果なし）'))); return box; }
    box.appendChild(badge(W.evidence.html('observed', '事実 ' + ev.fact)));
    box.appendChild(badge(W.evidence.html('inferred', '推論 ' + ev.inference)));
    box.appendChild(badge(W.evidence.html('unverified', '未確認 ' + ev.unverified)));
    return box;
  }

  function linkCell(site) {
    var box = el('span', 'ch-links');
    [['s01', '01'], ['s02', '02'], ['s03', '03'], ['s09', '09'], ['s05', '05']].forEach(function (p) {
      var href = site.links && site.links[p[0]];
      if (href) {
        var a = el('a', null, p[1]);
        a.href = href;
        a.setAttribute('aria-label', 'System ' + p[1] + ' を開く（' + site.domain + '）');
        box.appendChild(a);
      } else {
        var m = el('span', 'ch-link-off', p[1]);
        m.title = '解析結果が無いため開けません';
        box.appendChild(m);
      }
    });
    var d = el('a', 'ch-detail', '詳細');
    d.href = '/orchestration?site=' + encodeURIComponent(site.domain);
    d.setAttribute('aria-label', '個別実行詳細を開く（' + site.domain + '）');
    box.appendChild(d);
    return box;
  }

  function textOrNone(item) {
    if (!item) { return '—'; }
    var box = el('span');
    var t = item.text || '';
    if (item.href) {
      var a = el('a', null, t);
      a.href = item.href;
      box.appendChild(a);
    } else { box.textContent = t; }
    return box;
  }

  function renderList() {
    var host = $('ch-body');
    clear(host);
    var c = data.counts || {};
    if (c.sites === 0 && !(data.partial_errors || []).length) {
      W.state(host, { kind: 'empty', title: 'サイトがまだありません', message: '見張りたいサイトを追加すると、状態がここに並びます。',
        next: '「サイトを追加」から URL を入れてください。', actionLabel: 'サイトを追加',
        onAction: function () { window.location.href = '/orchestration?mode=detail'; } });
      return;
    }
    var rows = filterSites(data.sites || [], view);
    if (!rows.length) {
      W.state(host, { kind: 'empty', title: 'この条件に当てはまるサイトはありません',
        message: (data.sites || []).length ? '' : 'サイト一覧を取得できていません。',
        next: view === 'all' ? '再読み込みしてください。' : '「すべて」のタブで全サイトを確認できます。',
        actionLabel: view === 'all' ? '再読み込み' : 'すべてを見る',
        onAction: function () { if (view === 'all') { load(); } else { setView('all', true); } } });
      return;
    }
    var wrap = el('div', 'c-table-wrap');
    var table = el('table', 'c-table');
    var cap = el('caption', 'ch-sr', 'サイトごとの状態');
    table.appendChild(cap);
    var head = el('tr');
    ['サイト', '現在の状態', '現在の工程', '最終実行', '根拠の健全性', '人の対応待ち', '最新の変更', '最新の失敗', '開く'].forEach(function (h) {
      var th = el('th', null, h); th.scope = 'col'; head.appendChild(th);
    });
    var thead = el('thead'); thead.appendChild(head); table.appendChild(thead);
    var tbody = el('tbody');
    rows.forEach(function (s) {
      var tr = el('tr');
      cell(tr, 'サイト', el('strong', null, s.label || s.domain));
      cell(tr, '現在の状態', badge(W.status.html(s.status)));
      cell(tr, '現在の工程', s.stage ? s.stage.label : STAGE_NONE);
      cell(tr, '最終実行', s.last_run ? fmtAt(s.last_run.at) : '実行なし');
      cell(tr, '根拠の健全性', evidenceCell(s.evidence));
      cell(tr, '人の対応待ち', textOrNone(s.human_action));
      cell(tr, '最新の変更', textOrNone(s.latest_change));
      cell(tr, '最新の失敗', textOrNone(s.latest_failure));
      cell(tr, '開く', linkCell(s));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    host.appendChild(wrap);
  }

  /* ---------- 取得 ---------- */

  function render() {
    renderReason(); renderBanner(null); renderSplit(); renderKpis(); renderTabs(); renderList();
  }

  function load() {
    if (!data) { W.state($('ch-body'), { kind: 'loading', message: '全サイトの状態を集めています。' }); }
    fetch('/api/home/summary', { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          if (!res.ok || !body || !body.counts) { throw new Error((body && body.error) || ('HTTP ' + res.status)); }
          return body;
        });
      })
      .then(function (body) { data = body; render(); })
      .catch(function (err) {
        if (data) { renderBanner(String(err.message || err)); return; }
        W.reason($('ch-reason'), '状態を取得できていません。数字は未計測です。', 'warning');
        W.state($('ch-body'), { kind: 'error', message: String(err.message || err),
          next: '再読み込みを押してください。', actionLabel: '再読み込み', onAction: load });
      });
  }

  function init() {
    if (!W || !$('ch-body')) { return; }
    view = viewFromLocation();
    renderTabs();
    $('ch-reload').addEventListener('click', load);
    window.addEventListener('popstate', function () {
      view = viewFromLocation();
      if (data) { renderTabs(); renderList(); }
    });
    load();
  }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }
  window.__chHome = { filterSites: filterSites, setView: setView };
})();
