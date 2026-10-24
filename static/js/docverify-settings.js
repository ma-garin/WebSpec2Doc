/* System 06 設定（/docverify#settings）。GET/PUT /api/docverify/settings（rev・409）、POST /api/docverify/settings/ai-check。 */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var SEV = [['critical', '重大'], ['major', '主要'], ['minor', '軽微']];
  var TYPES = ['矛盾', '欠落', '曖昧', '不整合ID', '重複', '用語揺れ'];
  var ROLES = [['author', '作成者', '文書を書き、指摘への対応を記入します。'], ['moderator', '進行役', '進め方と期限を決め、検討の場を回します。'],
    ['reviewer', 'レビュアー', '文書を読み、指摘を出します。'], ['approver', '承認者', '出口基準を満たしたかを判断し、承認します。']];
  var S = null, dirty = false, keyInput = '';
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
  function banner(kind, html) { var b = $('dvsBanner'); b.className = 'p1-banner b-' + kind; b.innerHTML = html; b.hidden = !html; }
  function src(key) {
    var u = S && S.sources && S.sources[key] === 'user';
    return '<span class="dvs-src' + (u ? ' is-user' : '') + '" title="' + (u ? '利用者が保存した値' : '既定値') + '">' + (u ? '利用者設定' : '既定値') + '</span>';
  }
  function setDirty(v) {
    dirty = v; $('dvsSave').disabled = !v;
    if (v) banner('unsaved', '<b>未保存の変更があります。</b><span>次の行動: 画面を離れる前に「保存」を押してください。</span>');
    else if ($('dvsBanner').className.indexOf('b-unsaved') >= 0) banner('ok', '');
  }
  function row(label, ctrl, key, hint) {
    return '<div class="dvs-row"><span class="dvs-k">' + label + '</span><span>' + ctrl + '</span>' + (key ? src(key) : '<span></span>') +
      (hint ? '<span class="dvs-hint">' + hint + '</span>' : '') + '</div>';
  }
  function render() {
    var v = S.values, ap = S.approval_policy || {}, us = S.users || { enabled: false, list: [] };
    var lim = SEV.map(function (s) {
      var val = v.exit.max_open[s[0]];
      return row('<label for="dvs-lim-' + s[0] + '">未対応の' + esc(v.labels[s[0]]) + 'の上限</label>',
        '<input type="number" min="0" max="999" step="1" id="dvs-lim-' + s[0] + '" data-k="lim" data-s="' + s[0] + '" value="' + (val == null ? '' : val) + '" placeholder="上限なし"> 件',
        'exit.max_open.' + s[0], '空欄は上限なし。採用・要確認・未判定の指摘を未対応に数えます。');
    }).join('');
    var labels = SEV.map(function (s) {
      return row('<label for="dvs-lab-' + s[0] + '">重大度（既定「' + s[1] + '」）</label>',
        '<input type="text" maxlength="8" id="dvs-lab-' + s[0] + '" data-k="lab" data-s="' + s[0] + '" value="' + esc(v.labels[s[0]]) + '"> <button type="button" class="p1-btn" data-reset="' + s[0] + '">既定に戻す</button>',
        'labels.' + s[0]);
    }).join('');
    var types = '<div class="dvs-types">' + TYPES.map(function (t) {
      return '<label><input type="checkbox" data-k="type" data-t="' + esc(t) + '"' + (v.types[t] !== false ? ' checked' : '') + '> ' + esc(t) + '</label>';
    }).join('') + '</div>';
    var opts = '<option value="">（未割当）</option>' + us.list.map(function (u) { return '<option value="' + esc(u.id) + '">' + esc(u.name) + '</option>'; }).join('');
    var roles = ROLES.map(function (r) {
      var ctrl = us.enabled ? '<select id="dvs-role-' + r[0] + '" data-k="role" data-r="' + r[0] + '">' + opts + '</select>'
        : '<span class="dvs-fixed">利用者名の記録なし（ログインが無効のため割り当てできません）</span>';
      return row('<label for="dvs-role-' + r[0] + '">' + r[1] + '</label>', ctrl, us.enabled ? 'roles.' + r[0] : '', esc(r[2]));
    }).join('');
    var pol = '<ul class="dvs-policy"><li>本人承認: ' + (ap.forbid_self_approval ? '禁止（起票者は自分のレビューを承認できません）' : '許可') + '</li>' +
      '<li>例外: ' + (ap.exception ? ('あり（担当 ' + esc(ap.max_members) + ' 名以下のテナント）。理由: ' + esc(ap.reason || '未記入')) : 'なし') + '</li>' +
      '<li>出典: ' + ({ s10: '管理の設定（' + esc(ap.updated_by || '') + '・' + esc(ap.updated_at || '') + '）', default: '既定値（管理の設定が未保存）', broken: '管理の設定を読み取れないため既定値' }[ap.source] || '既定値') + '</li></ul>' +
      '<p class="dvs-fixed">本人承認の規則と例外は管理の設定で変更します。 <a href="/admin#approval-policy">管理の設定を開く</a></p>';
    var ai = v.ai;
    var aiRows = row('<label for="dvs-ai-p">送信先</label>', '<select id="dvs-ai-p" data-k="ai" data-f="provider"><option value="none">使わない</option><option value="openai">OpenAI</option><option value="ollama">Ollama（手元のサーバ）</option></select>', 'ai.provider',
      '「使わない」を選ぶと文書は外部へ送られません。') +
      row('<label for="dvs-ai-e">接続先</label>', '<input type="url" id="dvs-ai-e" data-k="ai" data-f="endpoint" value="' + esc(ai.endpoint) + '" placeholder="空欄で標準の接続先">', 'ai.endpoint') +
      row('<label for="dvs-ai-m">モデル名</label>', '<input type="text" id="dvs-ai-m" data-k="ai" data-f="model" value="' + esc(ai.model) + '" placeholder="例: gpt-4o-mini">', 'ai.model') +
      row('<label for="dvs-ai-k">API キー</label>', '<input type="password" id="dvs-ai-k" data-k="key" value="" placeholder="' + (S.api_key_masked ? '保存済み ' + esc(S.api_key_masked) + '（変更時だけ入力）' : '未保存') + '">', '',
        'OpenAI のときだけ使います。保存後は末尾 4 文字だけ表示します。') +
      '<div class="dvs-row"><span></span><span><button type="button" class="p1-btn" id="dvsAiCheck">接続を確認</button></span><span></span><span class="dvs-hint" id="dvsAiResult" role="status" aria-live="polite"></span></div>';
    $('dvsForm').innerHTML =
      '<section class="dvs-sec" id="dvs-exit"><h3>出口基準</h3><p>レビューを合格にできる条件です。判定と記録の画面の「全体／今回の変更分」に反映されます。</p>' + lim +
      row('未検証の扱い', '<span class="dvs-fixed">未検証は合格に数えない（固定・変更できません）</span>', '') +
      row('<label for="dvs-chg">今回の変更分の合格条件</label>', '<select id="dvs-chg" data-k="chg"><option value="same">全体と同じ上限</option><option value="zero">変更分は未対応 0 件</option></select>', 'exit.changed_rule',
        '前版から変わった節に付いた指摘だけで判定します。') + '</section>' +
      '<section class="dvs-sec" id="dvs-vocab"><h3>重大度と種別</h3><p>画面と出力に使う言葉です。重大度は 3 段階で固定し、表示名だけ変えられます。</p>' + labels +
      row('指摘の種別', types, '', '無効にした種別の指摘は判定に数えません。1 つ以上は有効にしてください。') + '</section>' +
      '<section class="dvs-sec" id="dvs-roles"><h3>役割の割当</h3><p>レビューに関わる人の役割です。</p>' + roles +
      '<h3 style="margin-top:10px">承認の規則（読み取りのみ）</h3>' + pol + '</section>' +
      '<section class="dvs-sec" id="dvs-ai"><h3>AI 送信先</h3><p>指摘の候補づくりに使う AI です。</p>' + aiRows + '</section>';
    $('dvs-chg').value = v.exit.changed_rule; $('dvs-ai-p').value = ai.provider;
    if (us.enabled) ROLES.forEach(function (r) { $('dvs-role-' + r[0]).value = v.roles[r[0]] || ''; });
    $('dvsMeta').textContent = S.updated_at ? '最終更新 ' + new Date(S.updated_at).toLocaleString('ja-JP') + (S.updated_by && S.updated_by !== '_none' ? '・' + S.updated_by : '') : 'まだ保存されていません（すべて既定値）';
    keyInput = '';
  }
  function collect() {
    var f = $('dvsForm'), v = { exit: { max_open: {} }, labels: {}, types: {}, roles: {}, ai: {} }, err = '';
    f.querySelectorAll('[data-k=lim]').forEach(function (i) {
      var t = i.value.trim(); if (t !== '' && !/^\d{1,3}$/.test(t)) err = '上限は 0〜999 の整数か空欄で入力してください。';
      v.exit.max_open[i.dataset.s] = t === '' ? null : +t;
    });
    v.exit.changed_rule = $('dvs-chg').value;
    f.querySelectorAll('[data-k=lab]').forEach(function (i) { if (!i.value.trim()) err = '重大度の表示名を入力してください。'; v.labels[i.dataset.s] = i.value.trim(); });
    f.querySelectorAll('[data-k=type]').forEach(function (i) { v.types[i.dataset.t] = i.checked; });
    if (S.users.enabled) f.querySelectorAll('[data-k=role]').forEach(function (i) { v.roles[i.dataset.r] = i.value; });
    f.querySelectorAll('[data-k=ai]').forEach(function (i) { v.ai[i.dataset.f] = i.value.trim(); });
    return { v: v, err: err };
  }
  async function load() {
    banner('loading', '<b>読み込み中…</b>');
    try { S = (await req('/api/docverify/settings')).settings; render(); setDirty(false); banner('ok', ''); }
    catch (e) { $('dvsForm').innerHTML = ''; banner('error', '<b>設定を読み込めませんでした。</b><span>' + esc(e.message) + '</span><button type="button" class="p1-btn" data-act="reload">読み直す</button>'); }
  }
  async function save(rev) {
    var c = collect();
    if (c.err) { banner('error', '<b>保存できません。</b><span>次の行動: ' + esc(c.err) + '</span>'); return; }
    var body = { rev: rev == null ? S.rev : rev, values: c.v };
    if (keyInput) body.api_key = keyInput;
    var btn = $('dvsSave'); btn.disabled = true; btn.textContent = '保存中…';
    try {
      S = (await req('/api/docverify/settings', 'PUT', body)).settings; render(); setDirty(false); banner('ok', '');
      if (window.DV && DV.toast) DV.toast('設定を保存しました'); else banner('ok', '<b>設定を保存しました。</b>');
    } catch (e) {
      if (e.status === 409) {
        S._latestRev = e.data.latest && e.data.latest.rev; S._latest = e.data.latest;
        banner('conflict', '<b>' + esc((e.data.latest && e.data.latest.updated_by && e.data.latest.updated_by !== '_none') ? e.data.latest.updated_by + ' さん' : '別の人') + 'が先に設定を更新しました。</b><span>次の行動: どちらを残すか選んでください。</span>' +
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
    f.addEventListener('input', function (e) { if (e.target.dataset.k === 'key') keyInput = e.target.value.trim(); setDirty(true); });
    f.addEventListener('change', function () { setDirty(true); });
    f.addEventListener('submit', function (e) { e.preventDefault(); });
    f.addEventListener('click', function (e) {
      var r = e.target.closest('[data-reset]'); if (r) { $('dvs-lab-' + r.dataset.reset).value = S.defaults.labels[r.dataset.reset]; setDirty(true); }
      if (e.target.id === 'dvsAiCheck') aiCheck();
    });
    $('dvsSave').addEventListener('click', function () { save(); });
    $('dvsReload').addEventListener('click', function () { if (!dirty || confirm('保存していない変更は失われます。読み直しますか？')) load(); });
    $('dvsBanner').addEventListener('click', function (e) {
      var a = e.target.closest('[data-act]'); if (!a) return;
      if (a.dataset.act === 'reload') load(); else save(S._latestRev);
    });
    document.querySelector('.dvs-nav').addEventListener('click', function (e) {
      var a = e.target.closest('a[data-sec]'); if (!a) return; e.preventDefault();
      document.querySelectorAll('.dvs-nav a').forEach(function (x) { x.classList.toggle('is-on', x === a); });
      var t = $('dvs-' + a.dataset.sec); if (t) t.scrollIntoView({ block: 'start' });
    });
    window.addEventListener('beforeunload', function (e) { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
    var LEAVE = '保存していない設定の変更があります。破棄して移動しますか？';
    var onSettings = function () { return !document.querySelector('[data-view=settings]').hidden; };
    document.addEventListener('click', function (e) {
      var a = e.target.closest('[data-nav], [data-go]');
      if (!a || !dirty || !onSettings() || (a.dataset.nav || a.dataset.go) === 'settings') return;
      if (!confirm(LEAVE)) { e.preventDefault(); e.stopImmediatePropagation(); return; }
      setDirty(false);
    }, true);
    var back = function () {
      if (!dirty || location.hash === '#settings') return;
      if (!confirm(LEAVE)) { history.pushState(null, '', '#settings'); window.dispatchEvent(new PopStateEvent('popstate')); return; }
      setDirty(false);
    };
    window.addEventListener('hashchange', back);
    window.addEventListener('popstate', back);
  }
  if (!$('dvsForm')) return;
  bind();
  if (window.DV && DV.on) DV.on('settings', function () { if (!dirty) load(); });
  window.DVSettings = { load: load, isDirty: function () { return dirty; } };
})();
