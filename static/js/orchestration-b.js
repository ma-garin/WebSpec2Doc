/* 指揮（案B・サイト一覧）。
 *
 * 主役は 1 表。1 行 = 1 サイト。起動時に 4 本だけ API を叩き、束ねるのはここで行う。
 * 表示テキストに内部用語（run / domain / project）を出さない。
 * DOM は createElement + textContent だけで組む（生 HTML の流し込みはしない）。
 */
(function () {
  'use strict';

  /** 案の記号は画面（body[data-variant]）を正とする。JS 側では持たない。 */
  function variantOf() {
    var body = typeof document === 'undefined' ? null : document.body;
    var name = body && body.dataset ? String(body.dataset.variant || '') : '';
    return name === 'b' || name === 'd' ? name : 'b';
  }

  var T0 = Date.now();
  var POLL_MS = 10000;
  var LIMIT = 200;

  /* ── 小道具 ───────────────────────────────────────── */

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined && text !== null && text !== '') { node.textContent = String(text); }
    return node;
  }

  function clear(node) {
    while (node && node.firstChild) { node.removeChild(node.firstChild); }
  }

  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  function clip(text, max) {
    var s = String(text === undefined || text === null ? '' : text);
    return s.length > max ? s.slice(0, max) : s;
  }

  /** ISO 文字列 → {hhmm, label, rel}。読めない値は空を返す（推測で埋めない）。 */
  function when(iso) {
    var t = Date.parse(String(iso || ''));
    if (!iso || isNaN(t)) { return { hhmm: '', label: '', rel: '' }; }
    var d = new Date(t);
    var now = new Date();
    var hhmm = pad2(d.getHours()) + ':' + pad2(d.getMinutes());
    var sameDay = d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth()
      && d.getDate() === now.getDate();
    var label = (sameDay ? '今日 ' : (d.getMonth() + 1) + '/' + d.getDate() + ' ') + hhmm;
    var diff = Math.max(0, Math.round((now.getTime() - t) / 60000));
    var rel = diff < 1 ? 'たった今'
      : diff < 60 ? diff + ' 分前'
        : diff < 60 * 24 ? Math.floor(diff / 60) + ' 時間前'
          : Math.floor(diff / 1440) + ' 日前';
    return { hhmm: hhmm, label: label, rel: rel };
  }

  /* ── 状態の判定（画面の心臓部。node からも読めるよう純関数にする）──── */

  var DEFAULT_STEP_LABELS = ['観測', 'テスト作成', '実行', '修正と報告書'];
  var DONE_STATES = { done: 1, ok: 1, succeeded: 1, success: 1, finished: 1, skipped: 1 };

  /** いま進んでいる段の名前（docs / tests / run / healing）。 */
  function currentStepName(run) {
    if (!run || !run.steps || !run.steps.length) { return ''; }
    var i = run.step_index;
    if (typeof i !== 'number' || i < 0 || i >= run.steps.length) { return ''; }
    return String(run.steps[i].name || '');
  }

  /** 承認画面の行き先。段ごとに担当システムが違う。 */
  function approvalHref(run, domain) {
    return currentStepName(run) === 'healing' ? '/healing' : '/autorun/report/' + domain;
  }

  /**
   * 1 サイトの状態・1 文・ボタンを決める。
   * ctx = { domain, run, awaiting: [{report_id}], monitor: {enabled, time} }
   */
  function decideRow(ctx) {
    var domain = String((ctx && ctx.domain) || '');
    var run = (ctx && ctx.run) || null;
    var awaiting = (ctx && ctx.awaiting) || [];
    var monitor = (ctx && ctx.monitor) || {};
    var stepLabel = (run && run.step_label) || '';

    if (awaiting.length >= 1) {
      var one = awaiting.length === 1 && awaiting[0] && awaiting[0].report_id;
      return {
        rank: 0, state: '要対応', stateClass: 'cb-s-act', quiet: false,
        text: '直した内容の報告書 ' + awaiting.length + ' 件が、あなたの承認を待っています。',
        button: { label: '報告書を見る', kind: 'act', href: one ? '/healing/reports/' + one : '/healing' }
      };
    }
    if (run && run.status === 'waiting_human') {
      return {
        rank: 1, state: '人待ち', stateClass: 'cb-s-wait', quiet: false,
        text: run.human_action || 'あなたの確認を待っています。',
        button: { label: '承認画面へ', kind: 'wait', href: approvalHref(run, domain) }
      };
    }
    if (run && run.status === 'failed') {
      var reason = clip(run.error || '', 60);
      return {
        rank: 0, state: '要対応', stateClass: 'cb-s-act', quiet: false,
        text: (stepLabel || '指揮') + ' が失敗しました' + (reason ? ': ' + reason : '。'),
        button: { label: 'もう一度', kind: 'act', action: 'daily' }
      };
    }
    if (run && (run.status === 'running' || run.status === 'queued')) {
      var started = when(run.started_at).hhmm;
      return {
        rank: 2, state: '実行中', stateClass: 'cb-s-wait', quiet: false,
        text: (stepLabel || '指揮') + 'を実行しています' + (started ? '（開始 ' + started + '）' : '。'),
        button: { label: 'やめる', kind: 'plain', action: 'cancel', runId: run.run_id }
      };
    }
    if (monitor.enabled) {
      var at = String(monitor.time || '').slice(0, 5);
      return {
        rank: 3, state: '見張り中', stateClass: 'cb-s-ok', quiet: true,
        text: '次は明日 ' + (at || '朝') + ' に自動で確認します。',
        button: null
      };
    }
    return {
      rank: 4, state: '未設定', stateClass: 'cb-s-idle', quiet: true,
      text: run ? '自動の見張りは止まっています。' : 'まだ指揮していません。',
      button: { label: '今すぐ回す', kind: 'plain', action: 'daily' }
    };
  }

  //: 状態タグの並び。サマリはこの順に出す（行のタグと同じ語をそのまま使う）。
  var STATE_ORDER = ['要対応', '人待ち', '実行中', '見張り中', '未設定'];

  /**
   * 状態タグごとの件数。行が使うのと同じ decideRow の結果だけを数えるため、
   * 合計は必ず行数と一致する（分岐を二重に書かない）。
   * items は decideRow へ渡す ctx でも、decision を持つ行でもよい。
   */
  function summarize(items) {
    var counts = {};
    STATE_ORDER.forEach(function (name) { counts[name] = 0; });
    var list = items || [];
    var total = 0;
    list.forEach(function (item) {
      var decision = (item && item.decision) || decideRow(item);
      var state = String(decision.state || '');
      if (counts[state] === undefined) { counts[state] = 0; }
      counts[state] += 1;
      total += 1;
    });
    return { total: total, counts: counts, order: STATE_ORDER.slice() };
  }

  /** 展開したときの 4 段。run が無ければ既定の 4 つを薄く出す。 */
  function trackSteps(run) {
    var steps = (run && run.steps && run.steps.length) ? run.steps : null;
    if (!steps) {
      return DEFAULT_STEP_LABELS.map(function (label) {
        return { label: label, done: false, now: false };
      });
    }
    var index = typeof run.step_index === 'number' ? run.step_index : -1;
    var live = run.status === 'running' || run.status === 'waiting_human';
    return steps.map(function (step, i) {
      return {
        label: String(step.label || step.name || ''),
        done: !!DONE_STATES[String(step.status || '')],
        now: live && i === index
      };
    });
  }

  /* ── ここから下はブラウザでしか動かない（node からは読み込むだけ）──── */

  if (typeof document === 'undefined') {
    if (typeof module === 'object' && module && module.exports) {
      module.exports = {
        decideRow: decideRow, summarize: summarize,
        trackSteps: trackSteps, approvalHref: approvalHref
      };
    }
    return;
  }

  var state = { sites: [], projects: [], runs: [], reports: [], open: '', busy: {} };
  var nodes = {};
  var timer = null;
  var firstActionSent = false;

  /* ── 計測（A/B）──────────────────────────────────── */

  function ab(event, target) {
    var ms = Math.max(0, Math.min(600000, Math.round(Date.now() - T0)));
    try {
      fetch('/api/orchestration/ab', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ variant: variantOf(), event: event, ms: ms, target: clip(target, 80) })
      }).catch(function () { /* 計測の失敗で画面を止めない */ });
    } catch (e) { /* 同上 */ }
  }

  function markFirstAction(target) {
    if (firstActionSent) { return; }
    firstActionSent = true;
    ab('first_action', target);
  }

  /* ── 通信 ─────────────────────────────────────────── */

  function fail(message) {
    if (!nodes.alert) { return; }
    nodes.alert.textContent = message;
    nodes.alert.hidden = false;
  }

  function clearFail() {
    if (nodes.alert) { nodes.alert.hidden = true; }
  }

  function getJSON(path) {
    return fetch(path, { credentials: 'same-origin' }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) { throw new Error((data && data.error) || 'うまく取得できませんでした。'); }
        return data;
      });
    });
  }

  function postJSON(path, body) {
    return fetch(path, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) { throw new Error((data && data.error) || 'うまく実行できませんでした。'); }
        return data;
      });
    });
  }

  /* ── 束ねる ───────────────────────────────────────── */

  function projectsByDomain() {
    var map = {};
    state.projects.forEach(function (p) {
      var d = String(p.domain || '');
      if (d && !map[d]) { map[d] = p; }
    });
    return map;
  }

  function latestRunByDomain() {
    var map = {};
    state.runs.forEach(function (r) {
      var d = String(r.domain || '');
      if (!d) { return; }
      var prev = map[d];
      if (!prev) { map[d] = r; return; }
      var a = Date.parse(String(r.started_at || '')) || 0;
      var b = Date.parse(String(prev.started_at || '')) || 0;
      if (a > b) { map[d] = r; }
    });
    return map;
  }

  function awaitingByDomain() {
    var byId = {};
    state.projects.forEach(function (p) { byId[String(p.project_id)] = String(p.domain || ''); });
    var map = {};
    state.reports.forEach(function (rep) {
      var d = byId[String(rep.project_id)] || '';
      if (!d) { return; }
      if (!map[d]) { map[d] = []; }
      map[d].push(rep);
    });
    return map;
  }

  function buildRows() {
    var projectMap = projectsByDomain();
    var runMap = latestRunByDomain();
    var awaitMap = awaitingByDomain();
    var rows = state.sites.map(function (site) {
      var domain = String(site.domain || '');
      var project = projectMap[domain] || {};
      var run = runMap[domain] || null;
      var decision = decideRow({
        domain: domain, run: run, awaiting: awaitMap[domain] || [],
        monitor: { enabled: !!project.monitor_enabled, time: project.monitor_time || '' }
      });
      var stamp = (run && (run.finished_at || run.started_at)) || site.updated_at || '';
      return { site: site, domain: domain, run: run, decision: decision, when: when(stamp) };
    });
    rows.sort(function (a, b) {
      if (a.decision.rank !== b.decision.rank) { return a.decision.rank - b.decision.rank; }
      return String(a.site.title || a.domain).localeCompare(String(b.site.title || b.domain), 'ja');
    });
    return rows;
  }

  /* ── 描画 ─────────────────────────────────────────── */

  function actionButton(row, spec, extraClass) {
    var cls = 'cb-do' + (spec.kind === 'act' ? ' cb-do-act' : spec.kind === 'wait' ? ' cb-do-wait' : '')
      + (extraClass ? ' ' + extraClass : '');
    if (spec.href) {
      var link = el('a', cls, spec.label);
      link.setAttribute('href', spec.href);
      link.addEventListener('click', function (ev) {
        ev.stopPropagation();
        markFirstAction(spec.label);
      });
      return link;
    }
    var button = el('button', cls, spec.label);
    button.type = 'button';
    if (state.busy[row.domain]) { button.disabled = true; }
    button.addEventListener('click', function (ev) {
      ev.stopPropagation();
      markFirstAction(spec.label);
      runAction(row, spec, button);
    });
    return button;
  }

  function siteCell(row, isOpen) {
    var wrap = el('span', 'cb-site');
    wrap.appendChild(el('span', 'cb-caret', isOpen ? '▾' : '▸'));
    var name = el('span', 'cb-site-name');
    name.appendChild(el('span', 'cb-t', row.site.title || row.domain));
    name.appendChild(el('span', 'cb-u', row.domain));
    wrap.appendChild(name);
    return wrap;
  }

  function panelFor(row) {
    var panel = el('div', 'cb-panel');
    var track = el('div', 'cb-track');
    trackSteps(row.run).forEach(function (step) {
      var cls = 'cb-dot' + (step.now ? ' is-now' : step.done ? ' is-done' : '');
      track.appendChild(el('span', cls, step.label));
    });
    panel.appendChild(track);

    var foot = el('div', 'cb-panel-foot');
    foot.appendChild(el('p', '', row.decision.text));
    if (row.decision.button) {
      foot.appendChild(actionButton(row, row.decision.button));
    }
    var link = el('a', '', 'これまでの記録を見る');
    link.setAttribute('href', '/orchestration/d?site=' + encodeURIComponent(row.domain));
    link.addEventListener('click', function (ev) {
      ev.stopPropagation();
      markFirstAction('これまでの記録を見る');
    });
    foot.appendChild(link);
    panel.appendChild(foot);
    return panel;
  }

  function toggle(domain) {
    state.open = state.open === domain ? '' : domain;
    markFirstAction('行を開く');
    render();
  }

  function rowNode(row) {
    var isOpen = state.open === row.domain;
    var node = el('div', 'cb-row cb-clickable' + (isOpen ? ' cb-open' : ''));
    node.setAttribute('role', 'button');
    node.setAttribute('tabindex', '0');
    node.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    node.setAttribute('aria-label', (row.site.title || row.domain) + ' の詳しい進みぐあいを開く');

    node.appendChild(siteCell(row, isOpen));
    node.appendChild(el('span', 'cb-state ' + row.decision.stateClass, row.decision.state));
    node.appendChild(el('p', row.decision.quiet ? 'cb-quiet' : '', row.decision.text));
    if (row.decision.button) {
      node.appendChild(actionButton(row, row.decision.button));
    } else {
      node.appendChild(el('span'));
    }
    var stamp = el('span', 'cb-when', row.when.label);
    if (row.when.rel) { stamp.appendChild(el('i', '', row.when.rel)); }
    node.appendChild(stamp);

    node.addEventListener('click', function () { toggle(row.domain); });
    node.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'Spacebar') {
        ev.preventDefault();
        toggle(row.domain);
      }
    });
    return node;
  }

  function renderHead(rows) {
    var summary = summarize(rows);
    nodes.count.textContent = '担当サイト ' + summary.total + ' 件';
    clear(nodes.lead);
    if (!summary.total) {
      nodes.lead.appendChild(document.createTextNode('まだ 1 件もありません。'));
      return;
    }
    summary.order.forEach(function (name, index) {
      if (index > 0) { nodes.lead.appendChild(document.createTextNode('・')); }
      var count = summary.counts[name] || 0;
      var hand = count > 0 && (name === '要対応' || name === '人待ち');
      nodes.lead.appendChild(el(hand ? 'b' : 'span', '', name + ' ' + count + ' 件'));
    });
  }

  function render() {
    var rows = buildRows();
    renderHead(rows);
    clear(nodes.rows);

    if (!rows.length) {
      var blank = el('div', 'cb-blank');
      blank.appendChild(el('p', '', '01 ドキュメント作成でサイトを観測すると、ここに並びます。'));
      var go = el('button', 'cb-add', 'サイトを保守下に置く');
      go.type = 'button';
      go.addEventListener('click', function () {
        markFirstAction('サイトを保守下に置く');
        openForm();
      });
      blank.appendChild(go);
      nodes.rows.appendChild(blank);
      schedulePoll(rows);
      return;
    }

    rows.forEach(function (row) {
      nodes.rows.appendChild(rowNode(row));
      if (state.open === row.domain) { nodes.rows.appendChild(panelFor(row)); }
    });
    schedulePoll(rows);
  }

  /* ── 走行中だけ 10 秒おきに実行の一覧だけ取り直す ──────────── */

  function schedulePoll(rows) {
    var running = rows.some(function (r) { return r.run && r.run.status === 'running'; });
    if (running && !timer) {
      timer = window.setInterval(refreshRuns, POLL_MS);
    } else if (!running && timer) {
      window.clearInterval(timer);
      timer = null;
    }
  }

  function refreshRuns() {
    getJSON('/api/orchestration/runs?limit=' + LIMIT).then(function (data) {
      state.runs = (data && data.runs) || [];
      clearFail();
      render();
    }).catch(function (err) {
      fail(err && err.message ? err.message : 'いまの状態を取得できませんでした。');
    });
  }

  /* ── 操作 ─────────────────────────────────────────── */

  function runAction(row, spec, button) {
    if (state.busy[row.domain]) { return; }
    state.busy[row.domain] = true;
    button.disabled = true;
    clearFail();
    var work = spec.action === 'cancel'
      ? postJSON('/api/orchestration/runs/' + spec.runId + '/cancel', {})
      : postJSON('/api/orchestration/runs', { domain: row.domain, goal: 'daily' });
    work.then(function () {
      state.busy[row.domain] = false;
      refreshRuns();
    }).catch(function (err) {
      state.busy[row.domain] = false;
      button.disabled = false;
      fail(err && err.message ? err.message : 'うまく実行できませんでした。');
    });
  }

  function openForm() {
    clear(nodes.formSite);
    state.sites.forEach(function (site) {
      var option = el('option', '', (site.title || site.domain) + '（' + site.domain + '）');
      option.value = String(site.domain || '');
      nodes.formSite.appendChild(option);
    });
    nodes.form.hidden = false;
    syncFormUrl();
    nodes.formSite.focus();
  }

  function syncFormUrl() {
    var domain = nodes.formSite.value;
    if (domain) { nodes.formUrl.value = 'http://' + domain + '/'; }
  }

  function submitForm(ev) {
    ev.preventDefault();
    var domain = nodes.formSite.value;
    if (!domain) { fail('サイトを選んでください。'); return; }
    clearFail();
    nodes.formGo.disabled = true;
    postJSON('/api/orchestration/runs', {
      domain: domain, goal: 'onboard', params: { url: nodes.formUrl.value }
    }).then(function () {
      nodes.formGo.disabled = false;
      nodes.form.hidden = true;
      refreshRuns();
    }).catch(function (err) {
      nodes.formGo.disabled = false;
      fail(err && err.message ? err.message : 'うまく始められませんでした。');
    });
  }

  /* ── 起動：API は 4 本だけ ─────────────────────────── */

  function boot() {
    nodes.count = document.getElementById('cb-count');
    nodes.lead = document.getElementById('cb-lead');
    nodes.alert = document.getElementById('cb-alert');
    nodes.rows = document.getElementById('cb-rows');
    nodes.add = document.getElementById('cb-add');
    nodes.form = document.getElementById('cb-form');
    nodes.formSite = document.getElementById('cb-form-site');
    nodes.formUrl = document.getElementById('cb-form-url');
    nodes.formGo = document.getElementById('cb-form-go');
    nodes.formCancel = document.getElementById('cb-form-cancel');
    if (!nodes.rows) { return; }

    nodes.add.addEventListener('click', function () {
      markFirstAction('サイトを保守下に置く');
      if (nodes.form.hidden) { openForm(); } else { nodes.form.hidden = true; }
    });
    nodes.formSite.addEventListener('change', syncFormUrl);
    nodes.formCancel.addEventListener('click', function () { nodes.form.hidden = true; });
    nodes.form.addEventListener('submit', submitForm);

    ab('view', '指揮');

    Promise.all([
      getJSON('/api/healing/sites'),
      getJSON('/api/healing/projects'),
      getJSON('/api/orchestration/runs?limit=' + LIMIT),
      getJSON('/api/healing/reports?status=awaiting&limit=' + LIMIT)
    ]).then(function (all) {
      state.sites = (all[0] && all[0].sites) || [];
      state.projects = (all[1] && all[1].projects) || [];
      state.runs = (all[2] && all[2].runs) || [];
      state.reports = (all[3] && all[3].reports) || [];
      clearFail();
      render();
    }).catch(function (err) {
      fail(err && err.message ? err.message : 'いまの状態を取得できませんでした。しばらくして開き直してください。');
      render();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  window.__orchestrationB = {
    decideRow: decideRow, summarize: summarize,
    trackSteps: trackSteps, approvalHref: approvalHref
  };
}());
