// ====================== ウィザード ======================
let wizardStep = 1;
let discovered = [];
let discoverSkipped = [];
const urlInput = document.getElementById('url-input');
const crawlDiscoverySection = document.getElementById('crawl-discovery-section');
const targetPreview = document.getElementById('target-preview');
const targetPreviewList = document.getElementById('target-preview-list');

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
urlInput.addEventListener('input', () => { clearDiscovered(); updateTargetPreview(); validateUrlInput(); });


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
  if (!loginUrl) { statusEl.textContent = 'ログインURLが見つかりません。上級設定でURLを入力してください。'; statusEl.classList.add('input-field-message-error'); return; }
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

// ---- 上級ログイン（アコーディオン内）: フォームを取得ボタン ----
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
  if (loginRecordPid) {
    await fetch('/api/login/record/cancel', { method: 'POST', body: new URLSearchParams({ pid: String(loginRecordPid) }) });
    loginRecordPid = null;
  }
  setLoginRecordUI('closed');
  const el = loginRecordStatusEl();
  if (el) { el.textContent = 'キャンセルしました'; el.classList.remove('input-field-message-error'); }
});

document.getElementById('select-all-btn').addEventListener('click', () => setAllDiscovered(true));
document.getElementById('clear-all-btn').addEventListener('click', () => setAllDiscovered(false));

// ---- 画面分析 経過時間タイマー ----
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

// skipLoginSection=true のとき（ログイン後の再解析）はログインセクションを再展開しない
async function discoverUrls(skipLoginSection) {
  const url = urlInput.value.trim();
  if (!url) { setUrlMessage('URLを入力してから画面分析を実行してください', true); return; }
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
    const body = new URLSearchParams({ url, depth: '5', max_pages: '300', auth });
    const res = await fetch('/api/discover-stream', { method: 'POST', body });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || '画面リスト取得に失敗しました');
    }

    const reader = res.body.getReader();
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
        if (obj.page) {
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
        } else if (obj.done) {
          _markDone(lastRow);
          lastRow = null;
        } else if (obj.error) {
          throw new Error(obj.error);
        }
      }
    }

    discovered = discovered.filter(p => p && p.url);
    renderDiscovered();
    // ログインURLを上級設定フィールドに反映（参考表示）
    if (!skipLoginSection && discovered.some(p => p.login_required)) {
      const loginPage = discovered.find(p => p.login_required && p.login_url);
      if (loginPage) {
        const advUrl = document.getElementById('login-url');
        if (advUrl && !advUrl.value) advUrl.value = loginPage.login_url;
      }
    }
    const loginCount = discovered.filter(p => p.login_required).length;
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
      status.textContent = '';
      if (discoverSkipped.length) status.textContent = `${discoverSkipped.length}件はrobots.txtまたは安全制約により除外されました。`;
    } else {
      status.textContent = discoverSkipped.length
        ? `取得可能な画面は0件です。${discoverSkipped.length}件がrobots.txtまたは安全制約により除外されました。`
        : '画面が0件でした。URLを確認してください。';
    }
  } catch (e) {
    clearDiscovered(); status.textContent = e.message; status.classList.add('discover-status-error');
  } finally {
    const elapsed = _stopDiscoverTimer();
    loading.style.display = 'none'; btn.disabled = false; updateTargetPreview();
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
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <input type="text" class="disc-item-login-user url-input" placeholder="ID / メールアドレス" autocomplete="username" style="flex:1;min-width:140px;height:34px;margin:0" />
            <input type="password" class="disc-item-login-pass url-input" placeholder="パスワード" autocomplete="current-password" style="flex:1;min-width:140px;height:34px;margin:0" />
            <button type="button" class="btn-primary disc-item-login-btn" style="height:34px;padding:0 16px;font-size:13px;flex-shrink:0">ログイン</button>
          </div>
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
  list.querySelectorAll('.discovered-cb').forEach(cb => cb.addEventListener('change', updateTargetPreview));
}
function clearDiscovered() {
  discovered = [];
  discoverSkipped = [];
  document.getElementById('discovered-url-panel').style.display = 'none';
  document.getElementById('discovered-url-list').innerHTML = '';
  document.getElementById('discover-status').textContent = '';
}
function setAllDiscovered(v) { document.querySelectorAll('.discovered-cb').forEach(cb => { cb.checked = v; }); updateTargetPreview(); }
function selectedDiscovered() { return [...document.querySelectorAll('.discovered-cb:checked')].map(cb => cb.value); }

// ---- 対象URLの確定 ----
function buildTargetUrls() { return selectedDiscovered(); }
function updateTargetPreview() {
  const urls = buildTargetUrls();
  targetPreview.querySelector('strong').textContent = `チェック対象 ${urls.length}件`;
  if (!urls.length) {
    const msg = urlInput.value.trim() ? '画面リスト取得を実行してください' : 'URLを入力してください';
    targetPreviewList.innerHTML = `<li><span>未確定</span><code>${msg}</code></li>`;
    return;
  }
  targetPreviewList.innerHTML = urls.map((u, i) => `<li><span>${i === 0 ? 'メイン' : '対象 ' + (i + 1)}</span><code>${escHtml(u)}</code></li>`).join('');
}

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
