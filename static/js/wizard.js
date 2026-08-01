// ====================== ウィザード ======================
let wizardStep = 1;
let discovered = [];
let discoverSkipped = [];
const urlInput = document.getElementById('url-input');
const crawlDiscoverySection = document.getElementById('crawl-discovery-section');

function showStep(n) { wizardStep = n; }

// ---- URL リアルタイムバリデーション（送信前エラー防止） ----
const URL_FORMAT_RE = /^https?:\/\/\S+\.\S+/i;
function validateUrlInput() {
  const v = urlInput.value.trim();
  if (!v) { urlInput.classList.remove('is-invalid'); setUrlMessage('', false); return false; }
  const ok = URL_FORMAT_RE.test(v);
  urlInput.classList.toggle('is-invalid', !ok);
  setUrlMessage(ok ? '' : 'URL は https://example.com の形式で入力してください', true);
  return ok;
}
urlInput.addEventListener('input', () => { clearDiscovered(); validateUrlInput(); });


function setUrlMessage(msg, isError) {
  const el = document.getElementById('url-input-message');
  el.textContent = msg; el.classList.toggle('input-field-message-error', !!(msg && isError));
}

// ---- 画面リスト取得（discover）----
document.getElementById('discover-btn').addEventListener('click', () => discoverUrls());

// ---- 自動ログイン（ADR-0002: GUIフォーム入力方式）----
function loginDomain() {
  const u = urlInput.value.trim();
  try { return new URL(u).hostname; } catch (e) { return ''; }
}
function setLoginStatus(msg, isError) {
  const el = document.getElementById('login-status');
  if (!el) return;
  el.textContent = msg; el.classList.toggle('input-field-message-error', !!(msg && isError));
}
function setLoginLoading(show, msg) {
  const el = document.getElementById('login-loading');
  if (!el) return;
  el.style.display = show ? 'flex' : 'none';
  if (msg) { const m = document.getElementById('login-loading-msg'); if (m) m.textContent = msg; }
}

// ---- 各「要ログイン」ページに埋め込んだログインボタン（イベント委譲）----
document.getElementById('discovered-url-list').addEventListener('click', async (e) => {
  const btn = e.target.closest('.disc-item-login-btn');
  if (!btn) return;
  const panel = btn.closest('.disc-item-login-panel');
  if (!panel) return;
  const loginUrl = panel.dataset.loginUrl || document.getElementById('login-url').value.trim();
  const username = panel.querySelector('.disc-item-login-user').value.trim();
  const password = panel.querySelector('.disc-item-login-pass').value;
  const statusEl = panel.querySelector('.disc-item-login-status');
  const loadingEl = panel.querySelector('.disc-item-login-loading');
  const domain = loginDomain();
  if (!loginUrl) { statusEl.textContent = 'ログインURLが見つかりません。上のログインURL欄に入力してください。'; statusEl.classList.add('input-field-message-error'); return; }
  btn.disabled = true; loadingEl.style.display = 'flex'; statusEl.textContent = '';
  try {
    const res = await fetch('/api/login/simple', { method: 'POST', body: new URLSearchParams({
      domain: domain || 'site', login_url: loginUrl, username, password,
    }) });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.error || 'ログインに失敗しました');
    document.getElementById('auth-path').value = data.auth_path || ('output/' + domain + '/auth.json');
    // パスワードを即破棄（セキュリティ）
    panel.querySelector('.disc-item-login-pass').value = '';
    statusEl.textContent = 'ログイン成功。認証後ページを再解析しています…';
    statusEl.classList.remove('input-field-message-error');
    await discoverUrls(true);
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.classList.add('input-field-message-error');
  } finally {
    btn.disabled = false; loadingEl.style.display = 'none';
  }
});

// ---- ログイン案内カード: フォームを取得ボタン ----
document.getElementById('login-scrape-btn').addEventListener('click', async () => {
  const url = document.getElementById('login-url').value.trim();
  const domain = loginDomain();
  if (!url) { setLoginStatus('ログインURLを入力してください', true); return; }
  setLoginStatus('', false);
  setLoginLoading(true, 'フォームを取得しています…');
  document.getElementById('login-scrape-btn').disabled = true;
  document.getElementById('login-fields-area').innerHTML = '';
  try {
    const res = await fetch('/api/login/scrape', { method: 'POST', body: new URLSearchParams({ url, domain: domain || 'site' }) });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'フォーム取得に失敗しました');
    renderLoginFields(data.fields || [], data.current_url);
  } catch (e) {
    setLoginStatus(e.message, true);
  } finally {
    setLoginLoading(false);
    document.getElementById('login-scrape-btn').disabled = false;
  }
});

function renderLoginFields(fields, currentUrl) {
  const area = document.getElementById('login-fields-area');
  if (!fields.length) { setLoginStatus('フォームフィールドが見つかりませんでした。ログインURLを確認してください。', true); return; }
  area.innerHTML = fields.map(f => {
    const type = f.field_type === 'password' ? 'password' : (f.field_type === 'email' ? 'email' : 'text');
    const ac = f.field_type === 'password' ? 'current-password' : (f.field_type === 'email' || f.name.includes('mail') || f.name.includes('user') ? 'username' : 'off');
    return `<div class="field" style="margin-bottom:8px">
      <label>${escHtml(f.placeholder || f.name || f.field_type)}</label>
      <input type="${type}" class="url-input login-field-input" data-field-name="${escHtml(f.name || f.element_id)}" data-current-url="${escHtml(currentUrl)}" placeholder="${escHtml(f.placeholder)}" autocomplete="${ac}" />
    </div>`;
  }).join('') +
    '<button type="button" id="login-submit-btn" class="btn-primary" style="margin-top:8px;height:36px;padding:0 18px;font-size:13px">ログイン</button>';
  document.getElementById('login-submit-btn').addEventListener('click', submitLogin);
  setLoginStatus('', false);
}

async function submitLogin() {
  const domain = loginDomain();
  const inputs = document.querySelectorAll('.login-field-input');
  if (!inputs.length) { setLoginStatus('先にフォームを取得してください', true); return; }
  const currentUrl = inputs[0].dataset.currentUrl || document.getElementById('login-url').value.trim();
  const fieldValues = {};
  inputs.forEach(inp => { if (inp.dataset.fieldName) fieldValues[inp.dataset.fieldName] = inp.value; });

  setLoginLoading(true, 'ログインしています…');
  const btn = document.getElementById('login-submit-btn');
  if (btn) btn.disabled = true;
  setLoginStatus('', false);
  try {
    const res = await fetch('/api/login/submit', { method: 'POST', body: new URLSearchParams({
      domain: domain || 'site', current_url: currentUrl, fields_json: JSON.stringify(fieldValues),
    }) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'ログインに失敗しました');
    if (data.success) {
      document.getElementById('auth-path').value = data.auth_path || ('output/' + domain + '/auth.json');
      setLoginStatus('ログイン成功。認証後ページを再解析しています…', false);
      setLoginLoading(true, '認証後ページを再解析しています…');
      await discoverUrls(true);
    } else if (data.needs_more_fields) {
      setLoginStatus('追加認証（MFA等）が必要です。表示されたフィールドを入力してください。', false);
      renderLoginFields(data.fields || [], data.current_url || currentUrl);
    } else {
      throw new Error(data.error || 'ログインに失敗しました');
    }
  } catch (e) {
    setLoginStatus(e.message, true);
  } finally {
    setLoginLoading(false);
    const b = document.getElementById('login-submit-btn');
    if (b) b.disabled = false;
  }
}
// ---- 認証フローレコーダー（SPEC-3-2）: 見えるブラウザで人が普通にログインし、ボタン一つで保存する ----
let loginRecordPid = null;
let loginRecordTimer = null;

const LOGIN_RECORD_PHASE_TEXT = {
  waiting: 'ブラウザでログインしてください…',
  login_detected: 'ログインを検知しました。完了したら「ログイン完了」を押してください。',
  saved: '',
  timeout: '時間切れです。もう一度お試しください。',
  closed: 'ブラウザが閉じられました（保存されていません）',
  error: '',
};

function loginRecordStatusEl() { return document.getElementById('login-record-status'); }

function setLoginRecordUI(phase) {
  const startBtn = document.getElementById('login-record-start-btn');
  const completeBtn = document.getElementById('login-record-complete-btn');
  const cancelBtn = document.getElementById('login-record-cancel-btn');
  const running = phase === 'waiting' || phase === 'login_detected';
  if (startBtn) startBtn.disabled = running;
  if (completeBtn) completeBtn.style.display = running ? '' : 'none';
  if (cancelBtn) cancelBtn.style.display = running ? '' : 'none';
}

function stopLoginRecordPolling() {
  if (loginRecordTimer) { clearInterval(loginRecordTimer); loginRecordTimer = null; }
}

async function pollLoginRecordStatus(domain) {
  const el = loginRecordStatusEl();
  try {
    const res = await fetch('/api/login/record/status?domain=' + encodeURIComponent(domain));
    const data = await res.json();
    if (!data.success) return;
    let text = LOGIN_RECORD_PHASE_TEXT[data.phase] || '';
    if (data.phase === 'saved') {
      text = data.verified ? '保存しました（動作確認OK）' : '保存しました（動作確認は未確認）';
    } else if (data.phase === 'error') {
      text = data.detail || 'エラーが発生しました';
    }
    if (el) { el.textContent = text; el.classList.toggle('input-field-message-error', ['timeout', 'closed', 'error'].includes(data.phase)); }
    setLoginRecordUI(data.phase);
    if (data.phase === 'saved') {
      stopLoginRecordPolling();
      if (data.auth_path) document.getElementById('auth-path').value = data.auth_path;
    } else if (data.phase === 'timeout' || data.phase === 'closed' || data.phase === 'error') {
      stopLoginRecordPolling();
    }
  } catch (e) {
    // ポーリング失敗は次回に任せる（ネットワーク瞬断等）
  }
}

document.getElementById('login-record-start-btn').addEventListener('click', async () => {
  const loginUrl = document.getElementById('login-url').value.trim();
  const domain = loginDomain();
  const el = loginRecordStatusEl();
  if (!loginUrl) { el.textContent = 'ログインURLを入力してください。'; el.classList.add('input-field-message-error'); return; }
  el.classList.remove('input-field-message-error');
  el.textContent = 'ブラウザを起動しています…';
  try {
    const res = await fetch('/api/login/record/start', { method: 'POST', body: new URLSearchParams({
      domain: domain || 'site', login_url: loginUrl,
    }) });
    const data = await res.json();
    if (!data.success) { el.textContent = data.error || '起動に失敗しました'; el.classList.add('input-field-message-error'); return; }
    loginRecordPid = data.pid;
    setLoginRecordUI('waiting');
    el.textContent = LOGIN_RECORD_PHASE_TEXT.waiting;
    stopLoginRecordPolling();
    loginRecordTimer = setInterval(() => pollLoginRecordStatus(domain || 'site'), 1000);
  } catch (e) {
    el.textContent = '起動に失敗しました';
    el.classList.add('input-field-message-error');
  }
});

document.getElementById('login-record-complete-btn').addEventListener('click', async () => {
  const domain = loginDomain();
  await fetch('/api/login/record/complete', { method: 'POST', body: new URLSearchParams({ domain: domain || 'site' }) });
});

document.getElementById('login-record-cancel-btn').addEventListener('click', async () => {
  const domain = loginDomain();
  stopLoginRecordPolling();
  let cancelFailed = false;
  if (loginRecordPid) {
    try {
      await fetch('/api/login/record/cancel', { method: 'POST', body: new URLSearchParams({ pid: String(loginRecordPid) }) });
    } catch (e) {
      // 中断要求が届かなくても UI は必ず閉じる。閉じないと記録中のまま操作不能になる。
      cancelFailed = true;
    }
    loginRecordPid = null;
  }
  setLoginRecordUI('closed');
  const el = loginRecordStatusEl();
  if (el) {
    el.textContent = cancelFailed
      ? '中断要求を送信できませんでした。ブラウザ側は閉じましたが、サーバ側の処理が残っている可能性があります。'
      : 'キャンセルしました';
    el.classList.toggle('input-field-message-error', cancelFailed);
  }
});

document.getElementById('select-all-btn').addEventListener('click', () => setAllDiscovered(true));
document.getElementById('clear-all-btn').addEventListener('click', () => setAllDiscovered(false));

// ---- 画面解析 経過時間タイマー ----
let _discoverTimerInterval = null;
function _startDiscoverTimer() {
  const el = document.getElementById('discover-elapsed');
  if (!el) return;
  el.textContent = '0:00';
  const t0 = Date.now();
  _discoverTimerInterval = setInterval(() => {
    const s = Math.floor((Date.now() - t0) / 1000);
    el.textContent = Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
  }, 1000);
}
function _stopDiscoverTimer() {
  clearInterval(_discoverTimerInterval);
  _discoverTimerInterval = null;
  // 最終経過時間をサマリー用に返す（消去しない）
  const el = document.getElementById('discover-elapsed');
  const elapsed = el ? el.textContent : '';
  if (el) el.textContent = '';
  return elapsed;
}

// 画面解析の結果に応じてログイン案内カードを出し分ける。
//   detected: ログインが必要な画面を検知した / closed: 公開画面が0件＝閉じた環境の疑い
//   none: ログイン不要
function showLoginPrompt(kind) {
  const card = document.getElementById('login-required-card');
  if (!card) return;
  if (kind === 'none') { card.style.display = 'none'; return; }
  const title = document.getElementById('login-required-title');
  const desc = document.getElementById('login-required-desc');
  if (kind === 'closed') {
    if (title) title.textContent = '🔒 ログインが必要な環境の可能性があります';
    if (desc) desc.textContent = '公開されている画面が見つかりませんでした。閉じた環境の場合は、ここでログインしてから「画面解析」をもう一度実行してください。';
  } else {
    if (title) title.textContent = '🔒 このサイトはログインが必要です';
    if (desc) desc.textContent = '認証の内側にある画面も対象にするには、ログインしてください。ログイン後に「画面解析」を再実行すると、認証済みの画面が追加されます。';
  }
  card.style.display = '';
}

// skipLoginSection=true のとき（ログイン後の再解析）はログインセクションを再展開しない
// 画面解析（discover）フェーズの中断用状態。クロール実行フェーズには停止ボタンが
// あるのに画面解析フェーズには無い、というドッグフーディング要望への対応。
let _discoverRunId = null;
let _discoverReader = null;
let _discoverCancelledByUser = false;

document.getElementById('discover-cancel-btn')?.addEventListener('click', async () => {
  _discoverCancelledByUser = true;
  if (_discoverRunId) {
    try {
      await fetch('/api/cancel', { method: 'POST', body: new URLSearchParams({ run_id: _discoverRunId }) });
    } catch (e) {
      // 中断要求が届かなかった場合、サーバ側の解析はそのまま走り続ける。
      // 黙って握りつぶすと「止めたつもりで止まっていない」状態になるため必ず伝える。
      setUrlMessage('中断の要求を送れませんでした。解析が続いている可能性があります。', true);
    }
  }
  if (_discoverReader) {
    try {
      await _discoverReader.cancel();
    } catch (e) {
      // 受信の打ち切りに失敗した場合も、サーバ側の解析は動き続けている可能性がある。
      // /api/cancel と同じ理由で握りつぶさない（feature_contracts: discover は critical）。
      setUrlMessage('中断しきれませんでした。解析が続いている可能性があります。', true);
    }
  }
});

// ---- 解析する範囲（深さ・最大ページ）----
// 従来は depth=5 / max_pages=300 を固定で送っており、大規模サイトでは 300画面・15分規模の
// 解析になっても中断以外の手が無かった（Issue #15）。API 側は元から depth / max_pages を
// 受け付けているため、ここでは画面の選択値を渡すだけにする。
const DISCOVER_SEC_PER_PAGE = 2.4;  // P0-1 の実測（デモサイト 7画面 16.6秒）
// 受付範囲は web/config.py の MAX_DEPTH / MAX_PAGES_LIMIT に対応する。
// 画面側が API より広い範囲を許すと、送っても黙って丸められる。
const DISCOVER_LIMITS = {
  depth: { min: 1, max: 10, fallback: 2 },
  max_pages: { min: 1, max: 500, fallback: 30 },
};

function _clampInt(value, { min, max, fallback }) {
  const n = parseInt(value, 10);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(Math.max(n, min), max);
}

function _checkedDiscoverScope() {
  return document.querySelector('input[name="discover-scope"]:checked');
}

/** 選択中のプリセット（またはカスタム入力）から depth / max_pages を返す。 */
function discoverScope(sel = _checkedDiscoverScope()) {
  // プリセットは data 属性、カスタムは数値入力欄。違うのは読む場所だけ。
  const src = (sel && sel.value !== 'custom')
    ? { depth: sel.dataset.depth, max: sel.dataset.max }
    : {
      depth: document.getElementById('discover-depth')?.value,
      max: document.getElementById('discover-max-pages')?.value,
    };
  return {
    depth: _clampInt(src.depth, DISCOVER_LIMITS.depth),
    max_pages: _clampInt(src.max, DISCOVER_LIMITS.max_pages),
  };
}

// 選択に応じてカスタム入力の開閉と見込み時間の表示を更新する。
// 見込みは「最大ページ数 × 実測 2.4秒」の上限値。実際は発見数がこれを下回ることが多く、
// 対象サイトの応答速度や robots.txt の Crawl-Delay で延びるため、断定しない書き方にする。
// 丸めは execution.js の formatEta() に合わせる。画面ごとに粒度が違うと、
// 同じ待ち時間が別の精度で見え、見積もりが実際より正確そうに見えてしまう。
function _syncDiscoverScope() {
  const sel = _checkedDiscoverScope();
  const fields = document.getElementById('discover-scope-fields');
  if (fields) fields.style.display = (sel && sel.value === 'custom') ? 'flex' : 'none';
  const est = document.getElementById('discover-scope-est');
  if (!est) return;
  const scope = discoverScope(sel);
  est.textContent = scope.max_pages === 1
    ? '開始ページの1画面だけを解析します（リンクは辿りません）。'
    : `最大 ${scope.max_pages} 画面・${formatEta(scope.max_pages * DISCOVER_SEC_PER_PAGE)}の見込みです。`
      + '対象サイトの応答速度により延びることがあります。';
}

// formatEta は execution.js にあり、そちらは wizard.js より後に読み込まれる。
// トップレベルで初期化すると未定義になるため DOMContentLoaded まで待つ。
window.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('input[name="discover-scope"]').forEach(r => {
    r.addEventListener('change', _syncDiscoverScope);
  });
  ['discover-depth', 'discover-max-pages'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', _syncDiscoverScope);
  });
  _syncDiscoverScope();
});

async function discoverUrls(skipLoginSection) {
  const url = urlInput.value.trim();
  if (!url) { setUrlMessage('URLを入力してから画面解析を実行してください', true); return; }
  if (!validateUrlInput()) return;
  const loading = document.getElementById('discover-loading');
  const status = document.getElementById('discover-status');
  const btn = document.getElementById('discover-btn');
  const feed = document.getElementById('discover-live-feed');
  const countLabel = document.getElementById('discover-count-label');

  loading.style.display = '';
  status.textContent = '';
  status.classList.remove('discover-status-error');
  btn.disabled = true;
  if (feed) feed.innerHTML = '';
  if (countLabel) countLabel.textContent = '0画面を発見';
  discovered = [];
  discoverSkipped = [];
  _discoverRunId = null;
  _discoverReader = null;
  _discoverCancelledByUser = false;
  _startDiscoverTimer();

  let lastRow = null;

  function _addRow(page, active) {
    if (!feed) return null;
    const div = document.createElement('div');
    div.className = 'discover-feed-row ' + (active ? 'discover-feed-row--active' : 'discover-feed-row--done');
    let path = page.url;
    try { path = new URL(page.url).pathname; } catch (e) {}
    div.innerHTML =
      `<span class="discover-feed-icon">${active ? '⟳' : '✓'}</span>` +
      `<span class="discover-feed-title">${escHtml(page.title || path)}</span>` +
      `<span class="discover-feed-path">${escHtml(path)}</span>`;
    feed.appendChild(div);
    feed.scrollTop = feed.scrollHeight;
    return div;
  }

  function _markDone(row) {
    if (!row) return;
    row.classList.replace('discover-feed-row--active', 'discover-feed-row--done');
    const icon = row.querySelector('.discover-feed-icon');
    if (icon) icon.textContent = '✓';
  }

  try {
    const auth = document.getElementById('auth-path').value.trim() || getSettings().auth || '';
    const scope = discoverScope();
    const body = new URLSearchParams({
      url, depth: String(scope.depth), max_pages: String(scope.max_pages), auth,
    });
    const res = await fetch('/api/discover-stream', { method: 'POST', body });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || '画面リスト取得に失敗しました');
    }

    const reader = res.body.getReader();
    _discoverReader = reader;
    const decoder = new TextDecoder();
    let buf = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const chunks = buf.split('\n\n');
      buf = chunks.pop() ?? '';
      for (const chunk of chunks) {
        const line = chunk.replace(/^data:\s?/, '').trim();
        if (!line) continue;
        let obj;
        try { obj = JSON.parse(line); } catch (e) { continue; }
        if (obj.run_id) {
          _discoverRunId = obj.run_id;
        } else if (obj.page) {
          _markDone(lastRow);
          discovered.push(obj.page);
          if (countLabel) countLabel.textContent = `${discovered.length}画面を発見`;
          lastRow = _addRow(obj.page, true);
        } else if (obj.crawl_event?.event === 'page_skipped') {
          discoverSkipped.push(obj.crawl_event);
          const skipped = obj.crawl_event;
          const reason = skipped.reason === 'robots' ? 'robots.txtにより除外' : '安全制約により除外';
          _markDone(lastRow); lastRow = null;
          _addRow({ url: skipped.url || '', title: reason }, false);
          if (countLabel) countLabel.textContent = `${discovered.length}画面 / ${discoverSkipped.length}件除外`;
        } else if (obj.done || obj.cancelled) {
          _markDone(lastRow);
          lastRow = null;
        } else if (obj.error) {
          throw new Error(obj.error);
        }
      }
    }
    // ユーザーが中断ボタンで停止した場合も、それまでに見つかった画面は捨てずに使う
    // （途中結果を保存するクロール実行フェーズの挙動と揃える）。
    discovered = discovered.filter(p => p && p.url);
    renderDiscovered();
    const loginCount = discovered.filter(p => p.login_required).length;
    // ログイン壁を検知したら、その場でログインを促す（旧「上級設定」は廃止）
    if (!skipLoginSection) {
      const loginPage = discovered.find(p => p.login_required && p.login_url);
      if (loginPage) {
        const urlInput = document.getElementById('login-url');
        if (urlInput && !urlInput.value) urlInput.value = loginPage.login_url;
      }
      if (loginCount) showLoginPrompt('detected');
      else if (!discovered.length && !_discoverCancelledByUser) showLoginPrompt('closed');
      else showLoginPrompt('none');
    }
    if (discovered.length) {
      const summary = document.getElementById('p1-summary');
      if (summary) {
        const screensNum = document.getElementById('p1-screens-num');
        if (screensNum) screensNum.textContent = discovered.length;
        const loginCard = document.getElementById('p1-login-card');
        const loginNum = document.getElementById('p1-login-num');
        if (loginCard) loginCard.style.display = loginCount ? '' : 'none';
        if (loginNum) loginNum.textContent = loginCount;
        summary.style.display = '';
      }
      if (_discoverCancelledByUser) {
        status.textContent = `中断しました（${discovered.length}画面を取得済み）。このまま条件設定に進むか、再実行してください。`;
      } else {
        status.textContent = '';
        if (discoverSkipped.length) status.textContent = `${discoverSkipped.length}件はrobots.txtまたは安全制約により除外されました。`;
      }
    } else if (_discoverCancelledByUser) {
      status.textContent = '中断しました（画面が見つかる前に停止しました）。';
    } else {
      status.textContent = discoverSkipped.length
        ? `取得可能な画面は0件です。${discoverSkipped.length}件がrobots.txtまたは安全制約により除外されました。`
        : '画面が0件でした。URLを確認してください。';
    }
  } catch (e) {
    if (_discoverCancelledByUser) {
      // 中断操作によって reader.cancel() が例外化する実装もあるため、その場合も
      // エラー扱いにせず静かに終了する（discovered は既に保持済み）。
      return;
    }
    clearDiscovered(); status.textContent = e.message; status.classList.add('discover-status-error');
  } finally {
    const elapsed = _stopDiscoverTimer();
    loading.style.display = 'none'; btn.disabled = false;
    if (elapsed) {
      const timeCard = document.getElementById('p1-time-card');
      const elapsedNum = document.getElementById('p1-elapsed-num');
      if (timeCard) timeCard.style.display = '';
      if (elapsedNum) elapsedNum.textContent = elapsed;
    }
  }
}
function renderDiscovered() {
  const panel = document.getElementById('discovered-url-panel');
  const list = document.getElementById('discovered-url-list');
  panel.style.display = (discovered.length || discoverSkipped.length) ? '' : 'none';

  const makeNormalItem = (it) => `
    <label class="discovered-url-item">
      <input type="checkbox" class="discovered-cb" value="${escHtml(it.url)}" checked />
      <span><strong>${escHtml(it.title || 'タイトル未取得')}</strong><code>${escHtml(it.url)}</code></span>
    </label>`;

  const makeLoginItem = (it) => {
    const loginUrl = it.login_url || '';
    const loginUrlDisplay = loginUrl ? (() => { try { return new URL(loginUrl).pathname; } catch (e) { return loginUrl; } })() : '（検出中）';
    return `
    <div class="disc-login-item-wrap">
      <label class="discovered-url-item">
        <input type="checkbox" class="discovered-cb" value="${escHtml(it.url)}" checked />
        <span>
          <strong>${escHtml(it.title || 'タイトル未取得')}</strong>
          <code>${escHtml(it.url)}</code>
          <span class="disc-login-badge">要ログイン</span>
        </span>
      </label>
      <div class="disc-item-login-panel" data-login-url="${escHtml(loginUrl)}">
        <div class="disc-item-login-header">🔒 この画面へのアクセスに認証が必要です <span class="disc-item-login-urlpath">ログインURL: ${escHtml(loginUrlDisplay)}</span></div>
        <div class="disc-item-login-body">
          <!-- パスワード欄が form の外にあるとブラウザが警告を出し、パスワード管理も
               効かないため form で包む。送信は JS が行うので既定の送信は抑止する。 -->
          <form class="disc-item-login-form" autocomplete="on" onsubmit="return false">
            <div class="disc-item-login-row">
              <input type="text" class="disc-item-login-user url-input disc-item-login-input" placeholder="ID / メールアドレス" autocomplete="username" />
              <input type="password" class="disc-item-login-pass url-input disc-item-login-input" placeholder="パスワード" autocomplete="current-password" />
              <button type="button" class="btn-primary disc-item-login-btn">ログイン</button>
            </div>
          </form>
          <div class="disc-item-login-loading discover-loading" style="display:none;margin-top:6px"><span class="spinner"></span><span>ログインしています…</span></div>
          <div class="disc-item-login-status input-field-message" style="margin-top:4px"></div>
        </div>
      </div>
    </div>`;
  };

  // evidence-only: 1件の描画失敗が全体を空白にしてはならない（過去に再発した障害クラス）。
  // banner（件数表示）は実データから生成される一方、各項目の HTML 生成は個別に
  // try/catch で保護し、失敗した項目だけを可視のフォールバック表示に落とす。
  const safeMap = (items, fn, fallbackLabel) => items.map((it) => {
    try {
      return fn(it);
    } catch (e) {
      console.error(`${fallbackLabel}の表示に失敗しました:`, it, e);
      return `<div class="discovered-url-item" style="opacity:.72"><span aria-hidden="true"></span><span><strong class="input-field-message-error">⚠ ${escHtml(fallbackLabel)}の表示に失敗しました（詳細はコンソール参照）</strong><code>${escHtml(String(it && it.url || ''))}</code></span></div>`;
    }
  });

  const normalPages = discovered.filter(p => !p.login_required);
  const loginPages = discovered.filter(p => p.login_required);

  let html = safeMap(normalPages, makeNormalItem, '画面').join('');
  if (loginPages.length) {
    html += `<div class="disc-login-group-separator"><span>🔒 認証が必要なページ（${loginPages.length}件）— 各画面の認証情報を入力してください</span></div>`;
    html += safeMap(loginPages, makeLoginItem, '認証必須画面').join('');
  }
  if (discoverSkipped.length) {
    html += `<div class="disc-login-group-separator"><span>取得対象外（${discoverSkipped.length}件）</span></div>`;
    html += safeMap(discoverSkipped, (item) => {
      const reason = item.reason === 'robots' ? 'robots.txt' : '安全制約';
      return `<div class="discovered-url-item" style="opacity:.72;cursor:default"><span aria-hidden="true"></span><span><strong>${escHtml(reason)}により除外</strong><code>${escHtml(item.url || '')}</code></span></div>`;
    }, '除外画面').join('');
  }
  list.innerHTML = html;
}
function clearDiscovered() {
  discovered = [];
  discoverSkipped = [];
  document.getElementById('discovered-url-panel').style.display = 'none';
  document.getElementById('discovered-url-list').innerHTML = '';
  document.getElementById('discover-status').textContent = '';
  setCrawlTargetMode('selected');
}
function setAllDiscovered(v) { document.querySelectorAll('.discovered-cb').forEach(cb => { cb.checked = v; }); }
function selectedDiscovered() { return [...document.querySelectorAll('.discovered-cb:checked')].map(cb => cb.value); }

// ---- 解析方法（自動解析／選択したURLのみ）----
// 「画面解析で見つけたURLだけをクロールするか、そこからリンクを辿って
// 自動的にクロール範囲を広げるかを選びたい」というドッグフーディング要望への対応。
function crawlTargetMode() {
  return document.querySelector('input[name="crawl-target-mode"]:checked')?.value || 'selected';
}
function setCrawlTargetMode(mode) {
  const radio = document.getElementById(mode === 'auto' ? 'crawl-mode-auto' : 'crawl-mode-selected');
  if (radio) radio.checked = true;
  _syncCrawlModeFields();
}
function _syncCrawlModeFields() {
  const isAuto = crawlTargetMode() === 'auto';
  const autoFields = document.getElementById('crawl-mode-auto-fields');
  const discoveredPanel = document.getElementById('discovered-url-panel');
  if (autoFields) autoFields.style.display = isAuto ? 'flex' : 'none';
  if (discoveredPanel) discoveredPanel.style.display = (isAuto || !discovered.length) ? 'none' : '';
}
document.querySelectorAll('input[name="crawl-target-mode"]').forEach(radio =>
  radio.addEventListener('change', _syncCrawlModeFields));

// ---- 対象URLの確定 ----
function buildTargetUrls() {
  if (crawlTargetMode() === 'auto') {
    const u = urlInput.value.trim();
    return u ? [u] : [];
  }
  return selectedDiscovered();
}
// 「チェック対象 N件」の確認ブロックは廃止した。直上の「取得対象の画面」リストと
// 同じ内容を二重に見せていただけで、選択結果の確認はリスト側で足りる。

// ---- 参考文書アップロード（Doc Fusion）----
let referenceDocPaths = [];

function setReferenceDocStatus(msg, isError) {
  const el = document.getElementById('reference-doc-status');
  el.textContent = msg;
  el.classList.toggle('input-field-message-error', !!(msg && isError));
}

function renderReferenceDocList() {
  const list = document.getElementById('reference-doc-list');
  list.innerHTML = referenceDocPaths.map((doc, i) =>
    `<li><span>${escHtml(doc.name)}</span> <button type="button" class="btn-outline-sm reference-doc-remove-btn" data-idx="${i}">削除</button></li>`
  ).join('');
  list.querySelectorAll('.reference-doc-remove-btn').forEach(btn => btn.addEventListener('click', () => {
    referenceDocPaths.splice(Number(btn.dataset.idx), 1);
    renderReferenceDocList();
  }));
}

document.getElementById('reference-doc-input').addEventListener('change', async (e) => {
  const files = [...e.target.files];
  e.target.value = '';
  if (!files.length) return;
  const domain = domainOf(urlInput.value.trim());
  if (!domain) {
    setReferenceDocStatus('先に対象URLを入力してください', true);
    return;
  }
  const formData = new FormData();
  formData.append('domain', domain);
  files.forEach(f => formData.append('files', f));
  setReferenceDocStatus('アップロード中…', false);
  try {
    const res = await fetch('/api/reference-docs', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'アップロードに失敗しました');
    referenceDocPaths.push(...data.saved);
    renderReferenceDocList();
    setReferenceDocStatus('', false);
  } catch (err) {
    setReferenceDocStatus(err.message, true);
  }
});
