// AutoRun「静的候補の探索」: GET で到達未確認の Route を開いて確かめる。
// API: GET/POST /api/sites/<domain>/static-routes/probe
(function () {
  'use strict';

  var root = document.getElementById('autorun-static-routes');
  if (!root) return;

  var state = { domain: '', data: null, running: false, notice: null, loadError: '', filter: 'all', posting: false };
  var pollTimer = null;
  var els = {};

  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function api(domain) { return '/api/sites/' + encodeURIComponent(domain) + '/static-routes/probe'; }
  function num(v) { return v == null ? '-' : String(v); }

  function fmtTime(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    return isNaN(d.getTime()) ? String(iso) : d.toLocaleString('ja-JP');
  }

  async function readJson(res) {
    try { return await res.json(); } catch (e) { return null; }
  }

  async function fetchState() {
    if (!state.domain) { state.data = null; render(); return; }
    var domain = state.domain;
    try {
      var res = await fetch(api(domain), { cache: 'no-store' });
      var body = await readJson(res);
      if (domain !== state.domain) return;
      if (!body) throw new Error('応答を読み取れませんでした');
      state.data = body;
      state.loadError = '';
      state.running = !!body.running;
    } catch (e) {
      state.loadError = '探索の状態を取得できませんでした。再読み込みしてください。';
    }
    render();
    // 別タブ・再読み込みで実行中の探索を開いたときは、完了まで 2 秒ごとに状態を取り直す（「実行中」のまま止めない）
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
    if (state.running && !state.posting && !state.loadError) pollTimer = setTimeout(fetchState, 2000);
  }

  async function run() {
    if (state.running || !state.domain) return;
    state.running = true;
    state.posting = true;
    state.notice = null;
    render();
    var notice;
    try {
      var res = await fetch(api(state.domain), { method: 'POST' });
      var body = await readJson(res);
      if (!body) {
        notice = { ok: false, message: '探索の結果を読み取れませんでした。', next: '再読み込みして状態を確認してください。' };
      } else {
        notice = { ok: body.result === 'success', message: body.message || '', next: body.next_action || '' };
      }
    } catch (e) {
      notice = { ok: false, message: '探索を開始できませんでした。', next: '通信状態を確認して再実行してください。' };
    }
    state.running = false;
    state.posting = false;
    state.notice = notice;
    await fetchState();
  }

  // ---- 表示語彙（WS2D.evidence の code へ対応付け。URL 到達 = 機能正常 にしない） ----
  var UNCONFIRMED = ['auth_required', 'ambiguous', 'unreached', 'failed'];
  var FILTERS = {
    all: { label: 'すべて', test: function () { return true; } },
    unauth: { label: '未認証で実測', test: function (it) { return it.status === 'observed' && it.authenticated !== true; } },
    auth: { label: '認証済みで実測', test: function (it) { return it.status === 'observed' && it.authenticated === true; } },
    unconfirmed: { label: '未確認・曖昧', test: function (it) { return UNCONFIRMED.indexOf(it.status) >= 0; } }
  };
  var STATUS_TEXT = { auth_required: '認証等で未確認', ambiguous: '曖昧（値が必要）', unreached: '未到達', failed: '確認失敗' };

  function evCode(it) {
    if (it.status === 'observed') return it.authenticated === true ? 'observed_auth' : 'observed';
    if (it.status === 'ambiguous') return 'ambiguous';
    return 'unverified';
  }
  function evLabel(it) {
    if (it.status === 'observed') return it.authenticated === true ? '認証済み実測' : '実測';
    if (it.status === 'auth_required' && it.auth_attempted === true) return '保存済みの認証状態でも未確認';
    return STATUS_TEXT[it.status] || it.status_label || String(it.status || '未確認');
  }
  function evBadge(it) { return WS2D.evidence.html(evCode(it), evLabel(it)); }

  function authStateText(d) {
    var v = d && d.after ? d.after.auth_state_available : null;
    return v === true ? 'System01 で保存済み' : (v === false ? 'なし' : '不明');
  }
  function count(items, key) { return items.filter(FILTERS[key].test).length; }
  function visibleItems(d) {
    var f = FILTERS[state.filter] || FILTERS.all;
    return (d.items || []).filter(f.test);
  }

  function renderHead(d) {
    var hasResult = d && d.state === 'ok';
    var busy = state.running || (d && d.running);
    var canRun = !(d && d.can_run === false) && !!state.domain && !busy;
    var last = d && d.finished_at ? fmtTime(d.finished_at) + (d.seconds != null ? '（' + d.seconds + '秒）' : '') : '未実行';
    var stCode = busy ? 'running' : (hasResult ? 'done' : (d && d.state === 'error' ? 'failed' : (d && d.state === 'no_rea' ? 'unavailable' : 'not_started')));
    var site = state.domain
      ? '<strong>' + esc(state.domain) + '</strong>'
      : '<input type="text" class="asr-domain-input" id="asr-domain-input" placeholder="例: example.com" aria-label="対象サイトのドメイン">' +
        ' <button type="button" class="c-btn c-btn--secondary c-btn--sm asr-set" id="asr-set">対象サイトに指定</button>';
    return '<header class="c-page-head asr-head"><div class="c-page-head__main">' +
      '<h3 class="c-page-head__title asr-title">静的候補の探索</h3>' +
      '<p class="c-page-head__desc">リバース解析で見つけた到達未確認の画面ルートを、閲覧（GET）だけで開いて到達を確かめます。送信・入力・削除は行いません。</p>' +
      '<div class="c-page-head__state">' + WS2D.status.html(stCode) + '</div></div>' +
      '<div class="c-page-head__actions"><button type="button" class="c-btn c-btn--primary asr-run" id="asr-run"' + (canRun ? '' : ' disabled') + '>' +
      (busy ? '探索中…' : (hasResult ? '再実行' : '探索を実行')) + '</button></div></header>' +
      '<div class="asr-context"><span><span class="asr-label">対象サイト</span>' + site + '</span>' +
      '<span><span class="asr-label">最終実行</span>' + esc(last) + '</span>' +
      '<span><span class="asr-label">認証状態</span>' + esc(authStateText(d)) + '</span></div>' +
      '<p class="asr-caveat" role="note"><strong>探索完了は機能が正しいことの証明ではありません</strong>（URL への到達のみ）。</p>' +
      (d && d.can_run === false && d.cannot_run_reason ? '<p class="asr-reason">' + esc(d.cannot_run_reason) + '</p>' : '') +
      '<div id="asr-reason-host"></div>' +
      '<p class="asr-live" role="status" aria-live="polite">' + (busy ? '探索しています（数十秒かかることがあります）。' + (hasResult ? '完了するまで下は前回の結果です。' : '') : '') + '</p>';
  }

  function renderNotice() {
    var n = state.notice;
    if (!n) return '';
    return '<div class="asr-notice ' + (n.ok ? 'is-ok' : 'is-ng') + '" role="status">' +
      '<strong>' + (n.ok ? '完了：' : '成功していません：') + '</strong>' + esc(n.message) +
      (n.next ? '<div>' + esc(n.next) + '</div>' : '') + '</div>';
  }

  // 流れ図の数（純関数・tests/js で検証）。0 と「未実施」を分ける: 認証状態が無いときの認証済み実測は null
  function flowModel(d) {
    var items = (d && d.items) || [];
    var a = (d && d.after) || {};
    var before = d && d.before && d.before.static_routes != null ? d.before.static_routes : items.length;
    var by = function (st) { return items.filter(function (it) { return it.status === st; }).length; };
    var auth = items.filter(function (it) { return it.status === 'observed' && it.authenticated === true; }).length;
    return {
      before: before,
      probed: items.length,
      notProbed: Math.max(0, before - items.length),
      unauth: items.filter(function (it) { return it.status === 'observed' && it.authenticated !== true; }).length,
      auth: (a.auth_state_available === false && !auth) ? null : auth,
      ambiguous: by('ambiguous'), unreached: by('unreached'), authRequired: by('auth_required'), failed: by('failed'),
      unconfirmed: items.filter(function (it) { return UNCONFIRMED.indexOf(it.status) >= 0; }).length,
      runnable: a.system02_runnable == null ? null : a.system02_runnable
    };
  }

  function stageBtn(key, label, n, ev, sub) {
    var on = state.filter === key;
    return '<button type="button" class="asr-stage' + (on ? ' is-on' : '') + '" data-filter="' + key + '" aria-pressed="' + (on ? 'true' : 'false') + '"' +
      ' aria-label="' + esc(label + ' ' + (n == null ? '未実施' : n + ' 件') + (on ? '（絞り込み中）' : '')) + '">' +
      '<span class="asr-stage-n">' + esc(n == null ? '—' : String(n)) + '</span>' +
      (ev ? '<span class="asr-stage-ev">' + ev + '</span>' : '') +
      (sub ? '<span class="asr-stage-sub">' + esc(sub) + '</span>' : '') + '</button>';
  }

  function node(no, title, body, cls) {
    return '<li class="asr-node' + (cls ? ' ' + cls : '') + '"><span class="asr-flow-t"><span class="asr-no" aria-hidden="true">' + no + '</span>' +
      esc(title) + '</span>' + body + '</li>';
  }

  // 静的候補 → 探索 → 未認証実測 → 認証済み実測 → 未確認・曖昧 → System02/09。番号で順序を示す（矢印は広い幅だけ）
  function renderFlow(d) {
    var m = flowModel(d);
    var q = encodeURIComponent(state.domain);
    var E = WS2D.evidence;
    var authOff = d.after && d.after.auth_state_available === false;
    var unconfSub = '曖昧 ' + m.ambiguous + '・未到達 ' + m.unreached + '・ログイン必要 ' + m.authRequired + '・確認失敗 ' + m.failed;
    return '<ol class="asr-flow" aria-label="静的候補から System02・System09 までの流れ（6 段）">' +
      node(1, '静的候補', stageBtn('all', 'リバース解析の静的候補', m.before, E.html('static', '静的'), '到達は未確認')) +
      node(2, '探索（GET のみ）', '<span class="asr-flow-note"><strong>' + m.probed + '</strong> 件を開いた' +
        (d.seconds != null ? '（' + esc(d.seconds) + ' 秒）' : '') + '</span>' +
        (m.notProbed ? '<span class="asr-flow-warn">未探索 ' + m.notProbed + ' 件（候補が増えています。再実行で確かめます）</span>' : '<span class="asr-flow-note">送信・入力・削除はしない</span>')) +
      node(3, '未認証実測', stageBtn('unauth', '未認証で実測', m.unauth, E.html('observed', '未認証実測'), 'URL への到達のみ')) +
      node(4, '認証済み実測', stageBtn('auth', '認証済みで実測', m.auth, E.html('observed_auth', '認証済み実測'),
        authOff && m.auth == null ? '保存済みの認証状態なし（未実施）' : 'ログイン必要な Route を再探索')) +
      node(5, '未確認・曖昧', stageBtn('unconfirmed', '未確認・曖昧', m.unconfirmed, E.html('unverified', '未確認') + ' ' + E.html('ambiguous', '曖昧'), unconfSub),
        m.unconfirmed ? 'is-warn' : '') +
      node(6, '次の工程', '<span class="asr-flow-group">' +
        '<a class="asr-next" href="/sites/' + q + '/tests#/run">System02 実行対象 <strong>' + esc(num(m.runnable)) + '</strong> 件<span class="asr-next-sub">実行済みとは別</span></a>' +
        '<a class="asr-next" href="/impact?tab=rea">System09 影響を見る</a></span>') +
      '</ol>';
  }

  function renderRow(it, i) {
    var vps = it.system02_viewpoints || [];
    var finalUrl = it.final_url && it.final_url !== it.url ? '<div class="asr-sub-url">遷移後: ' + esc(it.final_url) + '</div>' : '';
    return '<tr tabindex="0" data-i="' + i + '" aria-label="' + esc(it.route) + 'の根拠を開く">' +
      '<td data-label="Route"><code>' + esc(it.route) + '</code></td>' +
      '<td data-label="状態">' + evBadge(it) + '</td>' +
      '<td data-label="認証">' + esc(it.status === 'observed' ? (it.authenticated === true ? '認証済み' : '未認証') : '-') + '</td>' +
      '<td data-label="開いた URL"><div class="asr-url">' + esc(it.url || '-') + '</div>' + finalUrl + '</td>' +
      '<td data-label="静的根拠の位置">' + esc(it.location || '-') + '</td>' +
      '<td data-label="観点数" class="is-num">' + vps.length + '</td></tr>';
  }

  function renderList(d) {
    var items = d.items || [];
    if (!items.length) return '';
    var shown = visibleItems(d);
    var f = FILTERS[state.filter] || FILTERS.all;
    return '<div class="c-filter asr-filter"><span role="status">表示中: <strong>' + esc(f.label) + '</strong>（' + shown.length + ' / ' + items.length + ' 件）</span>' +
      (state.filter !== 'all' ? '<button type="button" class="c-btn c-btn--ghost c-btn--sm" id="asr-clear-filter">絞り込みを解除</button>' : '') + '</div>' +
      (shown.length
        ? '<div class="c-table-wrap"><table class="c-table"><thead><tr>' +
          '<th scope="col">Route</th><th scope="col">状態</th><th scope="col">認証</th>' +
          '<th scope="col">開いた URL / 遷移後 URL</th><th scope="col">静的根拠の位置</th><th scope="col" class="is-num">観点数</th>' +
          '</tr></thead><tbody>' + shown.map(renderRow).join('') + '</tbody></table></div>'
        : '<div id="asr-list-empty"></div>') +
      '<ul class="asr-notes"><li>「実測」は GET の遷移でその URL に留まったことだけを示します（画面が正しいことの証明ではありません）。</li>' +
      '<li>認証済みで実測した場合も、その URL へ到達したことだけを示します。画面内容・機能の正しさは別途確認が必要です。</li>' +
      '<li>曖昧（値が必要）な Route は、値を推測せず開いていません。行を選ぶと根拠が開きます。</li></ul>';
  }

  function renderBody(d) {
    if (state.loadError || !state.domain || !d || d.state !== 'ok') return '<div id="asr-state-host"></div>';
    return renderFlow(d) + renderList(d);
  }

  // 状態表示（loading / error / empty / unverified / unavailable）は WS2D.state に集約
  function fillState(d) {
    var host = root.querySelector('#asr-state-host');
    if (!host) return;
    var busy = state.running || (d && d.running);
    if (state.loadError) {
      WS2D.state(host, { kind: 'error', title: '探索の状態を取得できませんでした', message: state.loadError, retained: !!d,
        next: '再読み込みしてください。', actionLabel: '再読み込み', onAction: fetchState });
    } else if (!state.domain) {
      WS2D.state(host, { kind: 'empty', title: '対象サイトが未選択です', message: '対象サイトを選ぶと探索できます。', next: '上の入力欄にドメインを入れて「対象サイトに指定」を押します。' });
    } else if (!d) {
      WS2D.state(host, { kind: 'loading', message: '探索の状態を読み込んでいます。' });
    } else if (busy) {
      WS2D.state(host, { kind: 'loading', title: '探索しています', message: '静的候補を GET で開いています。数十秒かかることがあります。', retained: d.state === 'ok' });
    } else if (d.state === 'error') {
      WS2D.state(host, { kind: 'error', title: '探索の状態を取得できませんでした', message: d.message || '状態を取得できませんでした。', retained: false,
        next: d.next_action || '再読み込みしてください。', actionLabel: '再読み込み', onAction: fetchState });
    } else if (d.state === 'no_rea') {
      WS2D.state(host, { kind: 'empty', title: '静的候補がありません', message: 'リバース解析の結果がまだありません。', next: 'System01 でリバース解析を実行すると候補が入ります。' });
    } else if (d.state === 'not_run') {
      var can = !(d.can_run === false);
      WS2D.state(host, { kind: 'unverified', title: '未探索です', message: '静的候補はまだ URL への到達を確かめていません（静的のまま）。',
        next: can ? '「探索を実行」で GET だけで開いて確かめます。' : (d.cannot_run_reason || '実行できない理由を確認してください。'),
        actionLabel: '探索を実行', onAction: can ? run : null });
    }
  }

  function fillReason(d) {
    var host = root.querySelector('#asr-reason-host');
    if (!host) return;
    if (!d || d.state !== 'ok') { host.parentNode.removeChild(host); return; }
    var items = d.items || [];
    var obs = count(items, 'unauth') + count(items, 'auth');
    var un = count(items, 'unconfirmed');
    var m = flowModel(d);
    WS2D.reason(host, '探索した ' + items.length + ' 件のうち ' + obs + ' 件は URL への到達を実測、' + un + ' 件は未確認・曖昧・未到達・確認失敗のままです。' +
      (m.notProbed ? '静的候補 ' + m.before + ' 件のうち ' + m.notProbed + ' 件は未探索です（静的のまま）。' : ''),
      (un || m.notProbed) ? 'warning' : 'info');
  }

  function openDrawer(it, d, row) {
    var vps = it.system02_viewpoints || [];
    var observed = it.status === 'observed';
    var facts = [{ label: '結果', value: evLabel(it) }];
    if (observed) {
      facts.push({ label: '開いた URL（GET）', value: it.url || '-' });
      facts.push({ label: '最終 URL', value: it.final_url || it.url || '-' });
      facts.push({ label: '認証', value: it.authenticated === true ? '認証済み（保存済みの認証状態で到達）' : '未認証' });
      facts.push({ label: 'HTTP ステータス', value: it.http_status == null ? '-' : String(it.http_status) });
      facts.push({ label: '確認日時', value: fmtTime(it.observed_at) || '-' });
    } else {
      facts.push({ label: '実測', value: 'この Route への到達は実測できていません。' });
      if (it.auth_attempted) facts.push({ label: '認証', value: '保存済みの認証状態で再試行しましたが確認できませんでした' });
      if (it.http_status != null) facts.push({ label: 'HTTP ステータス', value: String(it.http_status) });
    }
    if (it.evidence) facts.push({ label: '観測（探索）', value: it.evidence });
    if (it.reason) facts.push({ label: '判定の理由', value: it.reason });
    var inf = [];
    if (it.status !== 'observed') inf.push('静的解析は Route「' + it.route + '」の宣言を示していますが、到達は実測できていません。');
    inf.push('System02 テスト観点: ' + (vps.length ? vps.join(' / ') : 'なし') + '（実行対象であっても実行済みではありません）');
    var lim = ['URL への到達のみを示します。画面の内容・機能が正しいことは確認していません。'];
    if (it.limitation) lim.push(it.limitation);
    WS2D.drawer.open({
      title: it.route, state: evCode(it), stateReason: it.reason || '',
      claim: 'リバース解析の静的解析が、Route「' + it.route + '」が宣言されていると示しています（静的候補）。',
      facts: facts, inferences: inf, limitations: lim,
      sources: [{ label: '位置', value: it.location || '-' },
        { label: 'provider', value: it.provider || (d && d.provider) || '静的解析（リバース解析）' }],
      returnFocus: row
    });
  }

  function bind(d) {
    var runBtn = root.querySelector('#asr-run');
    if (runBtn) runBtn.addEventListener('click', run);
    var reload = root.querySelector('#asr-reload');
    if (reload) reload.addEventListener('click', fetchState);
    var set = root.querySelector('#asr-set');
    if (set) {
      var apply = function () {
        var v = (root.querySelector('#asr-domain-input').value || '').trim();
        if (v) setDomain(v);
      };
      set.addEventListener('click', apply);
      root.querySelector('#asr-domain-input').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') apply();
      });
    }
    Array.prototype.forEach.call(root.querySelectorAll('[data-filter]'), function (b) {
      b.addEventListener('click', function () {
        var k = b.getAttribute('data-filter');
        state.filter = (state.filter === k && k !== 'all') ? 'all' : k;
        render();
        var again = root.querySelector('[data-filter="' + state.filter + '"]') || root.querySelector('[data-filter="' + k + '"]');
        if (again) again.focus();
      });
    });
    var clr = root.querySelector('#asr-clear-filter');
    if (clr) clr.addEventListener('click', function () { state.filter = 'all'; render(); });
    var empty = root.querySelector('#asr-list-empty');
    if (empty) WS2D.state(empty, { kind: 'empty', title: 'この区分に該当する Route はありません', message: '「' + (FILTERS[state.filter] || FILTERS.all).label + '」は 0 件です。', next: '絞り込みを解除して全体を確認します。' });
    if (d && d.state === 'ok') {
      var shown = visibleItems(d);
      Array.prototype.forEach.call(root.querySelectorAll('tr[data-i]'), function (tr) {
        var it = shown[Number(tr.getAttribute('data-i'))];
        if (!it) return;
        tr.addEventListener('click', function () { openDrawer(it, d, tr); });
        tr.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openDrawer(it, d, tr); }
        });
      });
    }
  }

  function render() {
    var d = state.data;
    var running = state.running || (d && d.running);
    root.innerHTML = renderHead(d) + renderNotice() + renderBody(d);
    root.setAttribute('aria-busy', running ? 'true' : 'false');
    fillState(d);
    fillReason(d);
    bind(d);
  }

  function setDomain(domain) {
    domain = domain || '';
    if (domain === state.domain && state.data) return;
    state.domain = domain;
    state.data = null;
    state.notice = null;
    state.loadError = '';
    state.filter = 'all';
    fetchState();
  }

  // 段階承認パイプラインが対象サイトを読み込むタイミングに合わせる
  function hook() {
    var st = window.autorunStages;
    if (!st || st.__asrHooked || typeof st.load !== 'function') return false;
    var orig = st.load;
    st.load = function (domain) {
      if (domain) setDomain(domain);
      return orig.apply(this, arguments);
    };
    st.__asrHooked = true;
    return true;
  }
  hook();

  window.autorunStaticRoutes = { load: setDomain };
  render();
})();
