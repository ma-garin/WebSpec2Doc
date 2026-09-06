/* 指揮画面（ワークフロー型）。
 *
 * 中央に「今いる工程のカード 1 枚」だけを出す状態機械。中身はサーバから来る
 * current.action.kind で決まる（テンプレート担当が置く DOM に、ここから要素を
 * 追加していく形）。healing-reports.js とはヘルパーを共有しない（IIFE の中に
 * 閉じていて外から呼べないため、必要な分だけこちらにも作る）。
 *
 * HTML 文字列の直接組み込みは使わない。値は必ず textContent で入れ、要素は createElement で組む。
 */
(function () {
  'use strict';

  var IS_ADMIN = document.body.getAttribute('data-hl-admin') === 'true';

  var STEP_STATE_WORD = { done: '完了', active: '進行中', human: 'あなたの番', todo: '未着手' };
  var WATCH_TIMES = ['7:00', '8:00', '9:00', '12:00', '18:00'];
  var ROUND_OPTIONS = [1, 2, 3, 4, 5];

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
    DOM.site = byId('cw-site');
    DOM.rounds = byId('cw-rounds');
    DOM.restart = byId('cw-restart');
    DOM.navWaiting = byId('cw-nav-waiting');
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
    renderNavWaiting(data);
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

  function renderStepper(data) {
    var steps = data.steps || [];
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

  /* サイドバーの確認待ちバッジ。GET は現在のサイトしか詳細を返さないため、
     分かる範囲＝現在のサイトが human なら 1 とする（複数サイトの集計は未対応）。 */
  function renderNavWaiting(data) {
    if (!DOM.navWaiting) { return; }
    var current = data.current || {};
    var n = current.state === 'human' ? 1 : 0;
    DOM.navWaiting.textContent = n > 0 ? String(n) : '';
    DOM.navWaiting.hidden = n === 0;
  }

  /* ---------------- 描画: カード ---------------- */

  function renderCard(data) {
    var current = data.current || {};
    clearCardError();
    DOM.title.textContent = current.headline || '';
    DOM.text.textContent = current.text || '';
    DOM.body.textContent = '';
    DOM.actions.textContent = '';

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
      case 'approve_viewpoints': return renderApproveViewpointsBody(action);
      case 'decide_report': return renderDecideReportBody(action);
      default: return; /* another_round / monitor(本体は無し) / none: 追加の本文は無い */
    }
  }

  function renderMonitorBodyIfNeeded(current, data) {
    if ((current.action || {}).kind === 'monitor') { renderMonitorBody(current.action); }
  }

  function renderActions(current, data, isRetry) {
    var action = current.action || {};
    switch (action.kind) {
      case 'start': return renderStartActions(action);
      case 'login': return renderLoginActions(action);
      case 'approve_viewpoints': return renderApproveViewpointsActions(action);
      case 'decide_report': return; /* 判断ボタンは各 article.cw-report の中 */
      case 'another_round': return renderAnotherRoundActions(action, isRetry);
      case 'monitor':
        renderMonitorBody(action);
        return renderMonitorActions(action);
      default:
        if (isRetry) { renderAnotherRoundActions(action, true); }
        return;
    }
  }

  /* ---- kind: start（① 場所を指定） ---- */

  function renderStartBody(data) {
    var repos = data.repos || [];
    var form = el('form', 'cw-form');
    form.id = 'cw-start-form';

    var urlField = el('label', 'cw-field');
    urlField.appendChild(el('span', 'cw-field-label', 'サイトの URL'));
    var urlInput = document.createElement('input');
    urlInput.type = 'url';
    urlInput.className = 'cw-input';
    urlInput.id = 'cw-f-url';
    urlInput.placeholder = 'https://example.jp/path';
    urlField.appendChild(urlInput);
    form.appendChild(urlField);

    var repoField = el('label', 'cw-field');
    repoField.appendChild(el('span', 'cw-field-label', 'コードの場所'));
    var repoSelect = document.createElement('select');
    repoSelect.className = 'cw-input';
    repoSelect.id = 'cw-f-repo';
    repos.forEach(function (r) {
      var opt = el('option', null, r.label || r.path);
      opt.value = r.path;
      repoSelect.appendChild(opt);
    });
    var ghOpt = el('option', null, 'GitHub のリンクを貼る');
    ghOpt.value = 'gh';
    repoSelect.appendChild(ghOpt);
    repoField.appendChild(repoSelect);
    form.appendChild(repoField);

    var ghField = el('label', 'cw-field');
    ghField.id = 'cw-f-gh-row';
    ghField.hidden = true;
    ghField.appendChild(el('span', 'cw-field-label', 'GitHub のリンク'));
    var ghInput = document.createElement('input');
    ghInput.type = 'text';
    ghInput.className = 'cw-input';
    ghInput.id = 'cw-f-gh';
    ghInput.placeholder = 'https://github.com/example/repo';
    ghField.appendChild(ghInput);
    form.appendChild(ghField);

    var roundsField = el('label', 'cw-field');
    roundsField.appendChild(el('span', 'cw-field-label', '回数'));
    var roundsSelect = document.createElement('select');
    roundsSelect.className = 'cw-input';
    roundsSelect.id = 'cw-f-rounds';
    ROUND_OPTIONS.forEach(function (n) {
      var opt = el('option', null, String(n));
      opt.value = String(n);
      if (n === 1) { opt.selected = true; }
      roundsSelect.appendChild(opt);
    });
    roundsField.appendChild(roundsSelect);
    form.appendChild(roundsField);

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
    verifyInput.id = 'cw-f-verify';
    verifyInput.value = (repos[0] && repos[0].verify_command) || '';
    verifyField.appendChild(verifyInput);
    details.appendChild(verifyField);
    form.appendChild(details);

    on(repoSelect, 'change', function () {
      ghField.hidden = repoSelect.value !== 'gh';
      var repo = repos.filter(function (r) { return r.path === repoSelect.value; })[0];
      verifyInput.value = repo ? (repo.verify_command || '') : '';
    });

    DOM.body.appendChild(form);
  }

  function renderStartActions(action) {
    var btn = el('button', 'btn-primary', action.primary || '始める');
    btn.type = 'button';
    on(btn, 'click', function () { submitStart(btn); });
    DOM.actions.appendChild(btn);
  }

  function submitStart(button) {
    var url = (byId('cw-f-url') || {}).value || '';
    if (!url.trim()) { showCardError('サイトの URL を入れてください。'); return; }
    var repoSelect = byId('cw-f-repo');
    var repo = repoSelect ? repoSelect.value : '';
    if (repo === 'gh') {
      var gh = byId('cw-f-gh');
      if (!gh || !gh.value.trim()) { showCardError('GitHub のリンクを入れてください。'); return; }
      repo = gh.value.trim();
    }
    var roundsSelect = byId('cw-f-rounds');
    var rounds = parseInt(roundsSelect ? roundsSelect.value : '1', 10) || 1;
    var verifyInput = byId('cw-f-verify');
    /* 新規サイト登録なので site は必ず空で送る（切替コンボの現在値を使わない）。 */
    sendAction('start', {
      site: '',
      url: url.trim(),
      repo: repo,
      verify_command: verifyInput ? verifyInput.value : '',
      rounds: rounds
    }, button).catch(function (e) {
      showVerifyCommandErrorIfNeeded((e && e.message) || '');
    });
  }

  /* 検証コマンドが決められなかった 400 のときは、「詳しい設定」を開いて
     その直下にも理由を出す（折りたたみの中にある必須項目のため）。 */
  function showVerifyCommandErrorIfNeeded(message) {
    if (message.indexOf('検証コマンド') === -1) { return; }
    var form = byId('cw-start-form');
    var details = form ? form.querySelector('.cw-details') : null;
    if (!details) { return; }
    details.open = true;
    var note = byId('cw-verify-error');
    if (!note) {
      note = el('p', 'cw-field-error');
      note.id = 'cw-verify-error';
      details.parentNode.insertBefore(note, details.nextSibling);
    }
    note.textContent = message;
  }

  /* ---- kind: login（② 観測・ログイン待ち） ---- */

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

  /* ---- kind: approve_viewpoints（③ テストを作る） ---- */

  function renderApproveViewpointsBody(action) {
    var items = extractItems(action);
    var ul = el('ul', 'cw-list');
    items.slice(0, 3).forEach(function (it) {
      ul.appendChild(el('li', null, it.text));
    });
    DOM.body.appendChild(ul);
  }

  function renderApproveViewpointsActions(action) {
    var approveBtn = el('button', 'btn-primary', action.primary || '承認して続ける');
    approveBtn.type = 'button';
    on(approveBtn, 'click', function () {
      sendAction('approve_viewpoints', {}, approveBtn, '観点を承認しました');
    });
    DOM.actions.appendChild(approveBtn);

    var returnBtn = el('button', 'btn-outline-sm', action.secondary || '差し戻す');
    returnBtn.type = 'button';
    var memoBox = buildMemoBox(function (note) {
      sendAction('return_viewpoints', { note: note }, returnBtn, '差し戻しました。作り直します');
    });
    memoBox.hidden = true;
    on(returnBtn, 'click', function () { memoBox.hidden = !memoBox.hidden; });
    DOM.actions.appendChild(returnBtn);
    DOM.actions.appendChild(memoBox);
  }

  /* ---- kind: decide_report（⑥ 判断） ---- */

  function renderDecideReportBody(action) {
    var items = extractItems(action);
    items.forEach(function (report) {
      DOM.body.appendChild(buildReportArticle(report));
    });
  }

  function buildReportArticle(report) {
    var art = el('article', 'cw-report');
    art.setAttribute('data-report-id', report.report_id);
    art.appendChild(el('h3', 'cw-report-title', report.title || '（件名なし）'));

    var dl = el('dl', 'cw-report-facts');
    dl.appendChild(el('dt', null, '事象'));
    dl.appendChild(el('dd', null, report.incident_text || '—'));
    dl.appendChild(el('dt', null, '原因'));
    dl.appendChild(el('dd', null, report.cause_text || '—'));
    dl.appendChild(el('dt', null, '対応'));
    dl.appendChild(el('dd', null, report.action_text || '—'));
    art.appendChild(dl);

    var verifyP = el('p', 'cw-report-verify');
    verifyP.appendChild(document.createTextNode('検証　修正前 '));
    verifyP.appendChild(el('span', 'cw-badge-err', report.verify_before || '—'));
    verifyP.appendChild(document.createTextNode(' → 修正後 '));
    var afterCls = report.verify_after_ok === false ? 'cw-badge-err' : 'cw-badge-ok';
    verifyP.appendChild(el('span', afterCls, report.verify_after || '—'));
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

    var approveLabel = report.primary || (report.fix_target === 'script' ? '承認' : '承認して PR を作る');
    var approveBtn = el('button', 'btn-primary', approveLabel);
    approveBtn.type = 'button';
    on(approveBtn, 'click', function () {
      var msg = report.fix_target === 'script' ? '承認しました' : '承認しました。PR を作成します';
      sendAction('decide_report', { report_id: report.report_id, action: 'approve', note: '' }, approveBtn, msg);
    });
    box.appendChild(approveBtn);

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

  /* 差し戻し共通: メモ欄＋確定ボタン。空なら送らない。 */
  function buildMemoBox(onSubmit) {
    var wrap = el('div', 'cw-memo-box');
    var ta = document.createElement('textarea');
    ta.className = 'cw-input';
    ta.placeholder = 'どこを直してほしいかを書いてください';
    wrap.appendChild(ta);
    var confirmBtn = el('button', 'btn-outline-sm', 'この内容で差し戻す');
    confirmBtn.type = 'button';
    on(confirmBtn, 'click', function () {
      var note = ta.value.trim();
      if (!note) { showCardError('差し戻す理由を書いてください。'); ta.focus(); return; }
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
