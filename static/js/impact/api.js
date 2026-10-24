/* System 09 影響度分析 — API 呼び出し（DD-006。接頭辞 /api/impact/v2）。
   応答は JSON、エラーは {error} をそのまま利用者に見せる。旧 API（/api/impact/jobs…）は使わない。 */
(function () {
  'use strict';
  var BASE = '/api/impact/v2';
  var FALLBACK = {
    400: '入力に誤りがあります。内容を見直してもう一度実行してください。',
    403: 'この操作を行う権限がありません。対象システムの管理者に役割の付与を依頼してください。',
    404: '対象が見つかりません。一覧から開き直してください。',
    409: 'ほかの操作と重なりました。画面を再読み込みしてからもう一度実行してください。',
    500: 'サーバーで問題が起きました。時間をおいてもう一度実行してください。'
  };

  function ApiError(message, status) {
    var e = new Error(message);
    e.status = status;
    return e;
  }

  function enc(v) { return encodeURIComponent(v); }

  function query(params) {
    var parts = Object.keys(params || {}).filter(function (k) {
      return params[k] !== undefined && params[k] !== null && params[k] !== '';
    }).map(function (k) { return enc(k) + '=' + enc(params[k]); });
    return parts.length ? '?' + parts.join('&') : '';
  }

  function parse(r) {
    return r.text().then(function (t) {
      var data = null;
      try { data = t ? JSON.parse(t) : {}; } catch (_) { data = null; }
      if (r.ok) return data || {};
      var msg = (data && data.error) || FALLBACK[r.status] || FALLBACK[500];
      throw ApiError(msg, r.status);
    });
  }

  function request(method, path, body) {
    var opt = { method: method, headers: { 'Accept': 'application/json' }, credentials: 'same-origin' };
    if (body instanceof FormData) opt.body = body;
    else if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    return fetch(BASE + path, opt).then(parse, function () {
      throw ApiError('サーバーに接続できません。通信状態を確認してもう一度実行してください。', 0);
    });
  }

  var get = function (p, q) { return request('GET', p + query(q)); };
  var post = function (p, b) { return request('POST', p, b === undefined ? {} : b); };
  var patch = function (p, b) { return request('PATCH', p, b); };
  var put = function (p, b) { return request('PUT', p, b); };
  var del = function (p) { return request('DELETE', p); };

  function S(sid) { return '/systems/' + enc(sid); }
  function C(sid, code) { return S(sid) + '/crs/' + enc(code); }

  /* 応答の包み（{systems:[…]} か […] か）に依存しないための取り出し */
  function list(d, key) {
    if (Array.isArray(d)) return d;
    if (d && Array.isArray(d[key])) return d[key];
    if (d && Array.isArray(d.items)) return d.items;
    return [];
  }
  function obj(d, key) { return (d && d[key] && typeof d[key] === 'object') ? d[key] : (d || {}); }

  window.IM = window.IM || {};
  window.IM.api = {
    list: list, obj: obj, query: query, base: BASE,
    systems: function () { return get('/systems'); },
    createSystem: function (b) { return post('/systems', b); },
    system: function (sid) { return get(S(sid)); },
    updateSystem: function (sid, b) { return patch(S(sid), b); },
    deleteSystem: function (sid) { return del(S(sid)); },
    members: function (sid) { return get(S(sid) + '/members'); },
    setMember: function (sid, actor, role) { return put(S(sid) + '/members/' + enc(actor), { role: role }); },
    removeMember: function (sid, actor) { return del(S(sid) + '/members/' + enc(actor)); },
    documents: function (sid) { return get(S(sid) + '/documents'); },
    uploadDocument: function (sid, file) {
      var fd = new FormData(); fd.append('file', file, file.name);
      return post(S(sid) + '/documents', fd);
    },
    setDocKind: function (sid, id, kind) { return patch(S(sid) + '/documents/' + enc(id), { kind: kind }); },
    deleteDocument: function (sid, id) { return del(S(sid) + '/documents/' + enc(id)); },
    items: function (sid, q) { return get(S(sid) + '/items', q); },
    baselines: function (sid) { return get(S(sid) + '/baselines'); },
    createBaseline: function (sid, b) { return post(S(sid) + '/baselines', b); },
    baselineDiff: function (sid, oldId, newId) { return get(S(sid) + '/baselines/diff', { old: oldId, 'new': newId }); },
    links: function (sid) { return get(S(sid) + '/links'); },
    addLink: function (sid, a, b) { return post(S(sid) + '/links', { a_item: a, b_item: b }); },
    deleteLink: function (sid, id) { return del(S(sid) + '/links/' + enc(id)); },
    suggest: function (sid) { return post(S(sid) + '/links/suggest'); },
    suggestions: function (sid) { return get(S(sid) + '/links/suggestions'); },
    decide: function (sid, id, accept) { return post(S(sid) + '/links/suggestions/' + enc(id), { accept: accept }); },
    crs: function (sid, status) { return get(S(sid) + '/crs', { status: status }); },
    createCr: function (sid, b) { return post(S(sid) + '/crs', b); },
    cr: function (sid, code) { return get(C(sid, code)); },
    updateCr: function (sid, code, b) { return patch(C(sid, code), b); },
    transition: function (sid, code, to, reason) { return post(C(sid, code) + '/transition', { to: to, reason: reason || '' }); },
    estimate: function (sid, code) { return post(C(sid, code) + '/estimate'); },
    analyze: function (sid, code, confirmSend) { return post(C(sid, code) + '/analyze', { confirm_send: !!confirmSend }); },
    job: function (id) { return get('/jobs/' + enc(id)); },
    cancelJob: function (id) { return post('/jobs/' + enc(id) + '/cancel'); },
    decision: function (sid, code) { return get(C(sid, code) + '/decision'); },
    impacts: function (sid, code, q) { return get(C(sid, code) + '/impacts', q); },
    impact: function (id) { return get('/impacts/' + enc(id)); },
    resolve: function (id, state, reason) { return post('/impacts/' + enc(id) + '/resolve', { state: state, reason: reason }); },
    override: function (id, lv, lk, reason) {
      return post('/impacts/' + enc(id) + '/override', { impact_level: lv, likelihood: lk, reason: reason });
    },
    graph: function (sid, code) { return get(C(sid, code) + '/graph'); },
    approval: function (sid, code, decision, reason) { return post(C(sid, code) + '/approval', { decision: decision, reason: reason || '' }); },
    actuals: function (sid, code) { return get(C(sid, code) + '/actuals'); },
    addActual: function (sid, code, b) { return post(C(sid, code) + '/actuals', b); },
    review: function (sid, code) { return get(C(sid, code) + '/review'); },
    reportUrl: function (sid, code) { return BASE + C(sid, code) + '/report.xlsx'; },
    audit: function (sid, q) { return get(S(sid) + '/audit', q); },
    auditCsvUrl: function (sid, q) { return BASE + S(sid) + '/audit.csv' + query(q); },
    trend: function (sid) { return get('/systems/' + encodeURIComponent(sid) + '/trend'); },
    sample: function () { return post('/sample'); }
  };
})();
