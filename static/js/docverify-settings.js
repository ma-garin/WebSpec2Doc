/* System 06 設定（/docverify#settings）第 2 周。
   GET/PUT /api/docverify/settings（rev・409・理由必須・history）、POST /api/docverify/settings/preview（保存前の影響）、POST /api/docverify/settings/ai-check。 */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var SEV = [['critical', '重大'], ['major', '警告'], ['minor', '提案']];
  var TYPES = ['矛盾', '欠落', '曖昧', '不整合ID', '重複', '用語揺れ'];
  var ROLES = [['author', '作成者', '文書を書き、指摘への対応を記入します。'], ['moderator', '進行役', '進め方と期限を決め、検討の場を回します。'],
    ['reviewer', 'レビュアー', '文書を読み、指摘を出します。'], ['approver', '承認者', '出口基準を満たしたかを判断し、承認します。本人承認は禁止（既定）: 起票者は自分のレビューを承認できません。']];
  var PRESETS = [['strict', '厳格', '重大 0・警告 0・要確認 0', { critical: 0, major: 0, minor: null }],
    ['standard', '標準', '重大 0・警告 5 まで', { critical: 0, major: 5, minor: null }],
    ['loose', '緩め', '重大 0 のみ', { critical: 0, major: null, minor: null }]];
  var STATE = { pass: '合格', fail: '不合格', unknown: '判定不能' };
  var S = null, dirty = false, keyInput = '', pvTimer = 0, pvSeq = 0;
  async function req(path, method, body) {
    var init = { method: method || 'GET', headers: {} };
    if (body !== undefined) { init.body = JSON.stringify(body); init.headers['Content-Type'] = 'application/json'; }
    var res;
    try { res = await fetch(path, init); } catch (e) { throw Object.assign(new Error('サーバに接続できませんでした。通信を確かめてから「読み直す」を押してください。'), { status: 0 }); }
    var data = await res.json().catch(function () { return null; });
    if (!res.ok) throw Object.assign(new Error((data && data.error) || '処理に失敗しました。時間をおいて「読み直す」を押してください。'), { status: res.status, data: data || {} });
    if (!data) throw Object.assign(new Error('応答を読み取れませんでした。「読み直す」を押してください。'), { status: 500 });
    return data;
  }
  function banner(kind, html) { var b = $('dvsBanner'); b.className = 'p1-banner b-' + kind; b.innerHTML = html; b.hidden = !html; requestAnimationFrame(fit); }
  function who(u) { return !u || u === '_none' ? 'ログインなし' : u; }
  function when(t) { return t ? new Date(t).toLocaleString('ja-JP', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''; }
  function userName(id) { var u = (S.users.list || []).filter(function (x) { return x.id === id; })[0]; return u ? u.name : id; }
  function flat(v) {
    var o = {};
    SEV.forEach(function (s) { o['exit.max_open.' + s[0]] = v.exit.max_open[s[0]] == null ? null : v.exit.max_open[s[0]]; });
    o['exit.changed_rule'] = v.exit.changed_rule;
    TYPES.forEach(function (t) { o['types.' + t] = v.types[t] !== false; });
    if (S.users.enabled) ROLES.forEach(function (r) { o['roles.' + r[0]] = v.roles[r[0]] || ''; });
    ['provider', 'endpoint', 'model'].forEach(function (k) { o['ai.' + k] = v.ai[k] || ''; });
    return o;
  }
  function fmt(k, v) {
    if (k.indexOf('exit.max_open.') === 0) return v == null ? '上限なし' : String(v);
    if (k === 'exit.changed_rule') return v === 'zero' ? '変更分 0 件' : '全体と同じ';
    if (k.indexOf('types.') === 0) return v ? '有効' : '無効';
    if (k.indexOf('roles.') === 0) return v ? userName(v) : '未割当';
    if (k === 'ai.provider') return { none: '使わない', openai: 'OpenAI', ollama: 'Ollama' }[v] || v;
    return v || '（なし）';
  }
  function src(key) {
    var u = S.sources && S.sources[key] === 'user';
    return '<span class="dvs-src' + (u ? ' is-user' : '') + '" title="' + (u ? '利用者が保存した値' : '既定値') + '">' + (u ? '利用者設定' : '既定値') + '</span>';
  }
  function row(label, ctrl, key, hint) {
    return '<div class="dvs-row"><span class="dvs-k">' + label + '</span><span>' + ctrl + '</span><span class="dvs-side">' +
      (key ? '<span class="dvs-delta" data-delta="' + esc(key) + '" hidden></span>' + (S.sources[key] ? src(key) : '') : '') + '</span>' +
      (hint ? '<span class="dvs-hint">' + hint + '</span>' : '') + '</div>';
  }
  function render() {
    var v = S.values, ap = S.approval_policy || {}, us = S.users || { enabled: false, list: [] };
    var presets = '<div class="dvs-presets" role="group" aria-label="プリセット">' + PRESETS.map(function (p) {
      return '<button type="button" class="dvs-preset" data-preset="' + p[0] + '">' + p[1] + '<small>' + p[2] + '</small></button>';
    }).join('') + '</div>';
    var lim = SEV.map(function (s) {
      var val = v.exit.max_open[s[0]];
      return row('<label for="dvs-lim-' + s[0] + '">未対応の' + s[1] + 'の上限</label>',
        '<input type="number" min="0" max="999" step="1" id="dvs-lim-' + s[0] + '" data-k="lim" data-s="' + s[0] + '" value="' + (val == null ? '' : val) + '" placeholder="上限なし"> 件',
        'exit.max_open.' + s[0]);
    }).join('');
    var types = '<div class="dvs-types">' + TYPES.map(function (t) {
      return '<label><input type="checkbox" data-k="type" data-t="' + esc(t) + '"' + (v.types[t] !== false ? ' checked' : '') + '> ' + esc(t) + '</label>';
    }).join('') + '</div>';
    var opts = '<option value="">（未割当）</option>' + us.list.map(function (u) { return '<option value="' + esc(u.id) + '">' + esc(u.name) + '</option>'; }).join('');
    var roles = ROLES.map(function (r) {
      var ctrl = us.enabled ? '<select id="dvs-role-' + r[0] + '" data-k="role" data-r="' + r[0] + '">' + opts + '</select>'
        : '<span class="dvs-off">ログインすると割り当てられます</span>';
      return row(us.enabled ? '<label for="dvs-role-' + r[0] + '">' + r[1] + '</label>' : r[1], ctrl, us.enabled ? 'roles.' + r[0] : '', esc(r[2]));
    }).join('');
    var pol = '<ul class="dvs-policy"><li>本人承認: ' + (ap.forbid_self_approval !== false ? '禁止（既定。起票者は自分のレビューを承認できません）' : '許可') + '</li>' +
      '<li>例外: ' + (ap.exception ? ('あり（担当 ' + esc(ap.max_members) + ' 名以下のテナント）。理由: ' + esc(ap.reason || '未記入')) : 'なし') + '</li></ul>' +
      '<p class="dvs-fixed">本人承認の規則と例外は監査の設定で変更します。 <a href="/settings/audit">承認規則を開く</a></p>';
    var ai = v.ai;
    var aiRows = row('<label for="dvs-ai-p">送信先</label>', '<select id="dvs-ai-p" data-k="ai" data-f="provider"><option value="none">使わない</option><option value="openai">OpenAI</option><option value="ollama">Ollama（手元のサーバ）</option></select>', 'ai.provider',
      '「使わない」を選ぶと文書は外部へ送られません。') +
      row('<label for="dvs-ai-e">接続先</label>', '<input type="url" id="dvs-ai-e" data-k="ai" data-f="endpoint" value="' + esc(ai.endpoint) + '" placeholder="空欄で標準の接続先">', 'ai.endpoint') +
      row('<label for="dvs-ai-m">モデル名</label>', '<input type="text" id="dvs-ai-m" data-k="ai" data-f="model" value="' + esc(ai.model) + '" placeholder="例: gpt-4o-mini">', 'ai.model') +
      row('<label for="dvs-ai-k">API キー</label>', '<input type="password" id="dvs-ai-k" data-k="key" value="" placeholder="' + (S.api_key_masked ? '保存済み ' + esc(S.api_key_masked) + '（変更時だけ入力）' : '未保存') + '">', '',
        'OpenAI のときだけ使います。保存後は末尾 4 文字だけ表示します。') +
      '<div class="dvs-row"><span></span><span><button type="button" class="p1-btn" id="dvsAiCheck">接続を確認</button> <span id="dvsAiResult" class="dvs-fixed" role="status" aria-live="polite"></span></span><span></span></div>';
    $('dvsForm').innerHTML =
      '<section class="dvs-sec" id="dvs-exit"><h3>出口基準</h3><p>レビューを合格にできる条件です。変えると上の帯に、現在のレビューの判定がどう変わるかを表示します。</p>' + presets + lim +
      row('要確認・未検証', '<span class="dvs-fixed">要確認が 1 件でもあれば不合格。未検証は解消に数えない（固定）</span>', '') +
      row('<label for="dvs-chg">今回の変更分</label>', '<select id="dvs-chg" data-k="chg"><option value="same">全体と同じ上限</option><option value="zero">変更分は未対応 0 件</option></select>', 'exit.changed_rule',
        '前版から変わった節に付いた指摘だけで判定します。') + '</section>' +
      '<section class="dvs-sec" id="dvs-vocab"><h3>重大度と種別</h3><p>重大度の名前は、対検査画面・判定・指摘書と同じ 3 段階です（変更できません）。</p>' +
      row('重大度', '<span class="dvs-sevs">' + SEV.map(function (s) { return '<span class="dvs-sev">' + s[1] + '</span>'; }).join('') + '</span>', '') +
      row('判定に数える種別', types, '', '外した種別の指摘は判定に数えません。1 つ以上は残してください。') + '</section>' +
      '<section class="dvs-sec" id="dvs-roles"><h3>役割の割当</h3><p>レビューに関わる人の役割です。' + (us.enabled ? '利用者一覧から選びます。' : '') + '</p>' + roles +
      '<h3 style="margin-top:10px">承認の規則（読み取りのみ）</h3>' + pol + '</section>' +
      '<section class="dvs-sec" id="dvs-ai"><h3>AI 送信先</h3><p>指摘の候補づくりに使う AI です。</p>' + aiRows + '</section>';
    $('dvs-chg').value = v.exit.changed_rule; $('dvs-ai-p').value = ai.provider;
    if (us.enabled) ROLES.forEach(function (r) { $('dvs-role-' + r[0]).value = v.roles[r[0]] || ''; });
    $('dvsMeta').textContent = S.updated_at ? '最終保存 ' + who(S.updated_by) + '・' + when(S.updated_at) : 'まだ保存されていません（すべて既定値）';
    keyInput = '';
    renderHist();
    requestAnimationFrame(fit);
  }
  function fit() {  // 区分ナビ・フォーム・履歴を画面の高さに収め、保存帯を常に画面下端に見せる（内側だけスクロール）
    var b = document.querySelector('.dvs-body'), bar = document.querySelector('.dvs-savebar');
    if (!b || !bar || !b.offsetParent) return;
    var top = b.getBoundingClientRect().top + (document.scrollingElement || document.documentElement).scrollTop;
    b.style.setProperty('--dvs-body-h', Math.max(260, window.innerHeight - top - bar.offsetHeight - 20) + 'px');
  }
  function renderHist() {
    var h = S.history || [];
    $('dvsHist').innerHTML = h.length ? h.map(function (e) {
      return '<li><div class="h-who">' + esc(who(e.by)) + '・' + esc(when(e.at)) + '</div><div class="h-why">理由: ' + esc(e.reason) + '</div><ul>' +
        (e.changes || []).map(function (c) { return '<li>' + esc(c.label) + ': ' + esc(c.before) + ' → ' + esc(c.after) + '</li>'; }).join('') + '</ul></li>';
    }).join('') : '<li class="mut">まだ変更はありません。保存すると、誰が・いつ・何を・なぜ変えたかがここに残ります。</li>';
  }
  function collect() {
    var f = $('dvsForm'), v = { exit: { max_open: {} }, types: {}, roles: {}, ai: {} }, err = '';
    f.querySelectorAll('[data-k=lim]').forEach(function (i) {
      var t = i.value.trim(); if (t !== '' && !/^\d{1,3}$/.test(t)) err = '上限は 0〜999 の整数か空欄で入力してください。';
      v.exit.max_open[i.dataset.s] = t === '' ? null : +t;
    });
    v.exit.changed_rule = $('dvs-chg').value;
    f.querySelectorAll('[data-k=type]').forEach(function (i) { v.types[i.dataset.t] = i.checked; });
    if (S.users.enabled) f.querySelectorAll('[data-k=role]').forEach(function (i) { v.roles[i.dataset.r] = i.value; });
    f.querySelectorAll('[data-k=ai]').forEach(function (i) { v.ai[i.dataset.f] = i.value.trim(); });
    return { v: v, err: err };
  }
  function refresh() {
    var c = collect(), a = flat(S.values), b = flat(c.v), n = 0;
    Object.keys(a).forEach(function (k) {
      var d = document.querySelector('[data-delta="' + k + '"]'), ch = a[k] !== b[k];
      if (ch) n++;
      if (d) { d.hidden = !ch; d.textContent = ch ? fmt(k, a[k]) + ' → ' + fmt(k, b[k]) : ''; }
    });
    if (keyInput) n++;
    var mo = c.v.exit.max_open;
    document.querySelectorAll('.dvs-preset').forEach(function (p) {
      var x = PRESETS.filter(function (q) { return q[0] === p.dataset.preset; })[0][3];
      p.classList.toggle('is-on', SEV.every(function (s) { return x[s[0]] === mo[s[0]]; }));
    });
    dirty = n > 0; $('dvsSave').disabled = !dirty;
    var cnt = $('dvsCount'); cnt.textContent = dirty ? '未保存の変更 ' + n + ' 項目' : '未保存の変更はありません'; cnt.classList.toggle('is-dirty', dirty);
    clearTimeout(pvTimer); pvTimer = setTimeout(function () { preview(c); }, 250);
  }
  async function preview(c) {
    var box = $('dvsImpact'), seq = ++pvSeq;
    if (c.err) { box.className = 'dvs-impact is-error'; box.innerHTML = '<b>影響プレビュー</b><span>' + esc(c.err) + '</span>'; return; }
    try {
      var r = await req('/api/docverify/settings/preview', 'POST', { values: c.v });
      if (seq !== pvSeq) return;
      var cnt = function (o) { return '合格 <span class="n-pass">' + o.pass + '</span>／不合格 <span class="n-fail">' + o.fail + '</span>／判定不能 <span class="n-unk">' + o.unknown + '</span>'; };
      box.className = 'dvs-impact' + (r.changed_count ? ' is-changed' : '');
      box.innerHTML = r.total ? '<b>' + (dirty ? 'この基準なら' : '現在の基準で') + '、現在のレビュー ' + r.total + ' 件の判定は</b><span>' + cnt(r.new) + '</span>' +
        (dirty ? '<span class="dvs-was">保存済みの基準では ' + cnt(r.now) + '</span>' : '') +
        (r.changed_count ? '<span>判定が変わるレビュー ' + r.changed_count + ' 件' + (r.changed_count > 5 ? '（先頭 5 件）' : '') + '</span><ul>' + r.changed.map(function (x) {
          return '<li>' + esc(x.name) + ': ' + STATE[x.now] + ' → <b>' + STATE[x.new] + '</b></li>'; }).join('') + '</ul>' : (dirty ? '<span>判定が変わるレビューはありません。</span>' : ''))
        : '<b>影響プレビュー</b><span>レビューがまだありません。基準を変えても判定に影響するものはありません。</span>';
      requestAnimationFrame(fit);
    } catch (e) { if (seq === pvSeq) { box.className = 'dvs-impact is-error'; box.innerHTML = '<b>影響を計算できませんでした。</b><span>' + esc(e.message) + '</span>'; } }
  }
  async function load() {
    banner('loading', '<b>読み込み中…</b>');
    try { S = (await req('/api/docverify/settings')).settings; render(); refresh(); banner('ok', ''); }
    catch (e) { $('dvsForm').innerHTML = ''; banner('error', '<b>設定を読み込めませんでした。</b><span>' + esc(e.message) + '</span><button type="button" class="p1-btn" data-act="reload">読み直す</button>'); }
  }
  async function save(rev) {
    var c = collect(), rs = $('dvsReason'), reason = rs.value.trim();
    if (c.err) { banner('error', '<b>保存できません。</b><span>次の行動: ' + esc(c.err) + '</span>'); return; }
    if (!reason) { rs.setAttribute('aria-invalid', 'true'); rs.focus(); banner('error', '<b>変更の理由が未入力です。</b><span>次の行動: 下の「変更の理由」に、なぜ変えるかを書いてから保存してください。</span>'); return; }
    rs.removeAttribute('aria-invalid');
    var body = { rev: rev == null ? S.rev : rev, values: c.v, reason: reason };
    if (keyInput) body.api_key = keyInput;
    var btn = $('dvsSave'); btn.disabled = true; btn.textContent = '保存中…';
    try {
      S = (await req('/api/docverify/settings', 'PUT', body)).settings; rs.value = ''; render(); refresh();
      banner('ok', '<b>設定を保存しました。</b><span>変更履歴に記録しました。判定の画面は次に開いたときに新しい基準で表示します。</span>');
    } catch (e) {
      if (e.status === 409) {
        S._latestRev = e.data.latest && e.data.latest.rev;
        banner('conflict', '<b>' + esc(e.data.latest ? who(e.data.latest.updated_by) : '別の人') + ' が先に設定を更新しました。</b><span>次の行動: どちらを残すか選んでください。</span>' +
          '<button type="button" class="p1-btn" data-act="reload">最新を読み直す</button><button type="button" class="p1-btn is-primary" data-act="keep">自分の変更を保持して保存</button>');
      } else banner('error', '<b>保存できませんでした。</b><span>次の行動: ' + esc(e.message) + '</span>');
      $('dvsSave').disabled = !dirty;
    } finally { btn.textContent = '保存'; }
  }
  async function aiCheck() {
    var c = collect(), out = $('dvsAiResult'), b = $('dvsAiCheck');
    b.disabled = true; b.textContent = '確認中…'; out.textContent = '';
    try {
      var r = await req('/api/docverify/settings/ai-check', 'POST', Object.assign({}, c.v.ai, keyInput ? { api_key: keyInput } : {}));
      banner(r.ok ? 'ok' : 'error', '<b>' + esc(r.message) + '</b>' + (r.next ? '<span>次の行動: ' + esc(r.next) + '</span>' : ''));
      out.textContent = r.ok ? '接続できました' : '接続できませんでした';
    } catch (e) { banner('error', '<b>接続を確認できませんでした。</b><span>次の行動: ' + esc(e.message) + '</span>'); }
    finally { b.disabled = false; b.textContent = '接続を確認'; }
  }
  function bind() {
    var f = $('dvsForm');
    f.addEventListener('input', function (e) { if (e.target.dataset.k === 'key') keyInput = e.target.value.trim(); refresh(); });
    f.addEventListener('change', refresh);
    f.addEventListener('submit', function (e) { e.preventDefault(); });
    f.addEventListener('click', function (e) {
      var p = e.target.closest('[data-preset]');
      if (p) {
        var x = PRESETS.filter(function (q) { return q[0] === p.dataset.preset; })[0][3];
        SEV.forEach(function (s) { $('dvs-lim-' + s[0]).value = x[s[0]] == null ? '' : x[s[0]]; });
        refresh();
      }
      if (e.target.id === 'dvsAiCheck') aiCheck();
    });
    $('dvsReason').addEventListener('input', function () { this.removeAttribute('aria-invalid'); });
    $('dvsSave').addEventListener('click', function () { save(); });
    $('dvsReload').addEventListener('click', function () { if (!dirty || confirm('保存していない変更は失われます。読み直しますか？')) load(); });
    $('dvsBanner').addEventListener('click', function (e) {
      var a = e.target.closest('[data-act]'); if (!a) return;
      if (a.dataset.act === 'reload') load(); else save(S._latestRev);
    });
    document.querySelector('.dvs-nav').addEventListener('click', function (e) {
      var a = e.target.closest('a[data-sec]'); if (!a) return; e.preventDefault();
      document.querySelectorAll('.dvs-nav a').forEach(function (x) { x.classList.toggle('is-on', x === a); });
      var t = $('dvs-' + a.dataset.sec); if (t) f.scrollTo({ top: t.offsetTop, behavior: 'smooth' });  // 外側のページは動かさない
    });
    window.addEventListener('resize', fit);
    window.addEventListener('beforeunload', function (e) { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
    var LEAVE = '保存していない設定の変更があります。破棄して移動しますか？';
    var onSettings = function () { return !document.querySelector('[data-view=settings]').hidden; };
    document.addEventListener('click', function (e) {
      var a = e.target.closest('[data-nav], [data-go]');
      if (!a || !dirty || !onSettings() || (a.dataset.nav || a.dataset.go) === 'settings') return;
      if (!confirm(LEAVE)) { e.preventDefault(); e.stopImmediatePropagation(); return; }
      dirty = false;
    }, true);
    var back = function () {
      if (!dirty || location.hash === '#settings') return;
      if (!confirm(LEAVE)) { history.pushState(null, '', '#settings'); window.dispatchEvent(new PopStateEvent('popstate')); return; }
      dirty = false;
    };
    window.addEventListener('hashchange', back);
    window.addEventListener('popstate', back);
  }
  if (!$('dvsForm')) return;
  bind();
  if (window.DV && DV.on) DV.on('settings', function () { if (!dirty) load(); });
  window.DVSettings = { load: load, isDirty: function () { return dirty; } };
})();
