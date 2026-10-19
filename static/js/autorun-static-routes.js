// AutoRun「静的候補の探索」: GET で到達未確認の Route を開いて確かめる。
// API: GET/POST /api/sites/<domain>/static-routes/probe
(function () {
  'use strict';

  var root = document.getElementById('autorun-static-routes');
  if (!root) return;

  var state = { domain: '', data: null, running: false, notice: null, loadError: '' };
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
  }

  async function run() {
    if (state.running || !state.domain) return;
    state.running = true;
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
    state.notice = notice;
    await fetchState();
  }

  function badgeClass(status) {
    return { observed: 'is-ok', unreached: 'is-miss', auth_required: 'is-auth', ambiguous: 'is-amb', failed: 'is-fail' }[status] || '';
  }

  function reachLabel(it) {
    if (it.status === 'observed') return it.authenticated === true ? '認証済みで実測' : '未認証で実測';
    if (it.status === 'auth_required' && it.auth_attempted === true) return '保存済みの認証状態でも未確認';
    return it.status_label || it.status;
  }

  function authStateText(d) {
    var v = d && d.after ? d.after.auth_state_available : null;
    return v === true ? 'System01 で保存済み' : (v === false ? 'なし' : '不明');
  }

  function renderBar(d) {
    var hasResult = d && d.state === 'ok';
    var canRun = !(d && d.can_run === false) && !!state.domain && !state.running && !(d && d.running);
    var last = '';
    if (d && d.finished_at) {
      last = fmtTime(d.finished_at) + (d.seconds != null ? '（' + d.seconds + '秒）' : '');
    } else {
      last = '未実行';
    }
    var reason = '';
    if (d && d.can_run === false && d.cannot_run_reason) reason = d.cannot_run_reason;
    var site = state.domain
      ? '<strong>' + esc(state.domain) + '</strong>'
      : '<input type="text" class="asr-domain-input" id="asr-domain-input" placeholder="例: example.com" aria-label="対象サイトのドメイン">' +
        ' <button type="button" class="btn btn-secondary asr-set" id="asr-set">設定</button>';
    return '<div class="asr-bar">' +
      '<div class="asr-bar-item"><span class="asr-label">対象サイト</span>' + site + '</div>' +
      '<div class="asr-bar-item"><span class="asr-label">最終実行</span><span>' + esc(last) + '</span></div>' +
      '<div class="asr-bar-item"><span class="asr-label">認証状態</span><span>' + esc(authStateText(d)) + '</span></div>' +
      '<button type="button" class="btn btn-primary asr-run" id="asr-run"' + (canRun ? '' : ' disabled') + '>' +
        (state.running || (d && d.running) ? '探索中…' : (hasResult ? '再実行' : '探索を実行')) + '</button>' +
      '</div>' +
      (reason ? '<p class="asr-reason">' + esc(reason) + '</p>' : '') +
      '<p class="asr-live" role="status" aria-live="polite">' +
        (state.running || (d && d.running) ? '探索しています（数十秒かかることがあります）' : '') + '</p>';
  }

  function renderNotice() {
    var n = state.notice;
    if (!n) return '';
    return '<div class="asr-notice ' + (n.ok ? 'is-ok' : 'is-ng') + '" role="status">' +
      '<strong>' + (n.ok ? '完了：' : '成功していません：') + '</strong>' + esc(n.message) +
      (n.next ? '<div>' + esc(n.next) + '</div>' : '') + '</div>';
  }

  function renderBand(d) {
    var a = d.after;
    if (!a) return '';
    var before = d.before ? d.before.static_routes : null;
    var obs = Number(a.observed) || 0;
    var authN = Number(a.observed_authenticated);
    if (isNaN(authN)) authN = (d.items || []).filter(function (x) { return x.status === 'observed' && x.authenticated === true; }).length;
    return '<div class="asr-band" aria-label="探索の前後">' +
      '<div class="asr-band-before"><span class="asr-label">探索前</span>静的 Route 候補 <strong>' + esc(num(before)) + '</strong></div>' +
      '<div class="asr-arrow" aria-hidden="true">→</div>' +
      '<div class="asr-band-after"><span class="asr-label">探索後</span><ul>' +
        '<li>実測で到達 <strong>' + esc(num(a.observed)) + '</strong>' +
          '<div class="asr-sub-auth">うち認証済み ' + esc(num(authN)) + ' ／ 未認証 ' + esc(num(Math.max(obs - authN, 0))) + '</div></li>' +
        '<li>未到達 <strong>' + esc(num(a.unreached)) + '</strong></li>' +
        '<li>認証等で未確認 <strong>' + esc(num(a.auth_required)) + '</strong></li>' +
        '<li>曖昧（値が必要） <strong>' + esc(num(a.ambiguous)) + '</strong></li>' +
        '<li>確認失敗 <strong>' + esc(num(a.failed)) + '</strong></li></ul></div>' +
      '</div>' +
      '<div class="asr-sub">実測へ昇格 <strong>' + esc(num(a.promoted)) + '</strong> 件 ／ ' +
        'System02 で実行対象になったテスト観点 <strong>' + esc(num(a.system02_runnable)) + '</strong> 件 ／ ' +
        '追加時間 <strong>' + esc(d.seconds != null ? d.seconds : '-') + '</strong> 秒</div>';
  }

  function renderRow(it) {
    var vps = it.system02_viewpoints || [];
    var finalUrl = it.final_url && it.final_url !== it.url ? '<div class="asr-sub-url">遷移後: ' + esc(it.final_url) + '</div>' : '';
    var details =
      '<dl class="asr-dl">' +
      '<dt>理由</dt><dd>' + esc(it.reason || '-') + '</dd>' +
      '<dt>認証</dt><dd>' + esc(it.authenticated === true ? '認証済み' : '未認証') + (it.auth_attempted ? '（保存済みの認証状態を試行）' : '') + '</dd>' +
      '<dt>証跡</dt><dd>' + esc(it.evidence || '-') + '</dd>' +
      '<dt>限界</dt><dd>' + esc(it.limitation || '-') + '</dd>' +
      '<dt>HTTP ステータス</dt><dd>' + esc(it.http_status == null ? '-' : it.http_status) + '</dd>' +
      '<dt>確認日時</dt><dd>' + esc(fmtTime(it.observed_at) || '-') + '</dd>' +
      '<dt>System02 テスト観点</dt><dd>' + (vps.length
        ? '<ul>' + vps.map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('') + '</ul>' : 'なし') + '</dd>' +
      '</dl>';
    return '<tr class="asr-row">' +
      '<td data-label="Route"><code>' + esc(it.route) + '</code></td>' +
      '<td data-label="状態"><span class="asr-badge ' + badgeClass(it.status) + '">' + esc(reachLabel(it)) + '</span></td>' +
      '<td data-label="理由">' + esc(it.reason || '') + '</td>' +
      '<td data-label="開いた URL"><div class="asr-url">' + esc(it.url || '-') + '</div>' + finalUrl + '</td>' +
      '<td data-label="静的根拠の位置">' + esc(it.location || '-') + '</td>' +
      '<td data-label="観点数">' + vps.length + '</td></tr>' +
      '<tr class="asr-detail-row"><td colspan="6"><details><summary>詳細（理由・HTTP・確認日時・観点）</summary>' + details + '</details></td></tr>';
  }

  function renderList(d) {
    var items = d.items || [];
    if (!items.length) return '';
    return '<div class="asr-table-wrap"><table class="asr-table"><thead><tr>' +
      '<th scope="col">Route</th><th scope="col">状態</th><th scope="col">理由</th>' +
      '<th scope="col">開いた URL / 遷移後 URL</th><th scope="col">静的根拠の位置</th><th scope="col">観点数</th>' +
      '</tr></thead><tbody>' + items.map(renderRow).join('') + '</tbody></table></div>' +
      '<ul class="asr-notes"><li>「実測で到達」は GET の遷移でその URL に留まったことだけを示します（画面が正しいことの証明ではありません）。</li>' +
      '<li>認証済みで実測した場合も、その URL へ到達したことだけを示します。画面内容・機能の正しさは別途確認が必要です。</li>' +
      '<li>曖昧（値が必要）な Route は、値を推測せず開いていません。</li></ul>';
  }

  function renderBody(d) {
    if (state.loadError) {
      return '<div class="asr-notice is-ng" role="alert">' + esc(state.loadError) +
        '<div><button type="button" class="btn btn-secondary" id="asr-reload">再読み込み</button></div></div>';
    }
    if (!state.domain) return '<p class="asr-empty">対象サイトを選ぶと探索できます。</p>';
    if (!d) return '<p class="asr-empty">読み込み中です。</p>';
    if (d.state === 'error') {
      return '<div class="asr-notice is-ng" role="alert"><strong>注意：</strong>' + esc(d.message || '状態を取得できませんでした。') +
        (d.next_action ? '<div>' + esc(d.next_action) + '</div>' : '') +
        '<div><button type="button" class="btn btn-secondary" id="asr-reload">再読み込み</button></div></div>';
    }
    if (d.state === 'no_rea') {
      return '<p class="asr-empty">System01 でリバース解析を実行すると候補が入ります。</p>';
    }
    if (d.state === 'not_run') {
      return '<p class="asr-empty">まだ探索していません。</p>';
    }
    return renderBand(d) + renderList(d);
  }

  function render() {
    var d = state.data;
    var running = state.running || (d && d.running);
    var html =
      '<h3 class="asr-title">静的候補の探索</h3>' +
      '<p class="asr-lead">リバース解析で見つけた到達未確認の画面ルートを、閲覧（GET）だけで開いて到達を確かめます。送信・入力・削除は行いません。</p>' +
      renderBar(d) + renderNotice() + renderBody(d);
    root.innerHTML = html;
    root.setAttribute('aria-busy', running ? 'true' : 'false');
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
  }

  function setDomain(domain) {
    domain = domain || '';
    if (domain === state.domain && state.data) return;
    state.domain = domain;
    state.data = null;
    state.notice = null;
    state.loadError = '';
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
