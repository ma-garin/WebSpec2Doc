// ====================== ウィザード ======================
let wizardStep = 1;
let discovered = [];
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
    } else {
      status.textContent = '画面が0件でした。URLを確認してください。';
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
  panel.style.display = discovered.length ? '' : 'none';

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

  const normalPages = discovered.filter(p => !p.login_required);
  const loginPages = discovered.filter(p => p.login_required);

  let html = normalPages.map(makeNormalItem).join('');
  if (loginPages.length) {
    html += `<div class="disc-login-group-separator"><span>🔒 認証が必要なページ（${loginPages.length}件）— 各画面の認証情報を入力してください</span></div>`;
    html += loginPages.map(makeLoginItem).join('');
  }
  list.innerHTML = html;
  list.querySelectorAll('.discovered-cb').forEach(cb => cb.addEventListener('change', updateTargetPreview));
}
function clearDiscovered() {
  discovered = [];
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

