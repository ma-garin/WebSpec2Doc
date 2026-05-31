
const SETTINGS_KEY = 'webspec2doc.settings';
const VIEW_HEADER = {
  dashboard: { trail: ['ダッシュボード'], title: '監視対象サイト' },
  generate: { trail: ['ダッシュボード', 'サイトを追加'], title: 'サイトを追加 / 再クロール' },
  settings: { trail: ['ダッシュボード', '設定'], title: '設定' },
};
const escHtml = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// ---- ヘッダー（パンくず＋タイトル）----
function setHeader(trail, title) {
  const bc = document.getElementById('topbar-breadcrumb');
  bc.innerHTML = trail.map((t, i) => i === 0
    ? `<a data-bc-root="1">${escHtml(t)}</a>`
    : `<span class="sep">›</span><span>${escHtml(t)}</span>`).join('');
  const root = bc.querySelector('[data-bc-root]');
  if (root && trail.length > 1) root.addEventListener('click', () => switchView('dashboard'));
  document.getElementById('topbar-title').textContent = title;
  document.getElementById('topbar-actions').innerHTML = '';
}

// ---- ナビ切替 ----
document.querySelectorAll('.app-nav-item').forEach(btn => btn.addEventListener('click', () => switchView(btn.dataset.view)));
function switchView(name) {
  document.querySelectorAll('.app-nav-item').forEach(b => b.classList.toggle('is-active', b.dataset.view === name));
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('is-active', v.id === 'view-' + name));
  const h = VIEW_HEADER[name];
  if (h) setHeader(h.trail, h.title);
  if (name === 'dashboard') loadHistory();
}
// ---- ウィザード ステップ管理 ----
function showWizardStep(n) {
  const p1 = document.getElementById('wizard-p1');
  const p2 = document.getElementById('wizard-p2');
  const bar = document.getElementById('wizard-progress-bar');
  if (p1) p1.style.display = (n === 1) ? '' : 'none';
  if (p2) p2.style.display = (n === 2) ? '' : 'none';
  if (bar) bar.style.display = (n <= 2) ? '' : 'none';
  [1, 2, 3, 4].forEach(i => {
    const node = document.getElementById('ws-' + i);
    if (!node) return;
    node.classList.toggle('is-active', i === n);
    node.classList.toggle('is-done', i < n);
  });
  [1, 2, 3].forEach(i => {
    const line = document.getElementById('wl-' + i);
    if (line) line.classList.toggle('is-done', i < n);
  });
}

// 「+ サイトを追加」: 新規ウィザードを開く（P1から）
function openAddSite() {
  switchView('generate');
  executionView.classList.add('hidden'); resultPanel.classList.add('hidden');
  appContent.classList.remove('is-executing'); genPanel.style.display = '';
  document.getElementById('url-input').value = '';
  document.getElementById('p1-summary').style.display = 'none';
  clearDiscovered(); updateTargetPreview(); showWizardStep(1);
}
document.getElementById('add-site-btn').addEventListener('click', openAddSite);
document.getElementById('add-site-btn-2').addEventListener('click', openAddSite);

// P1 → P2: 「次へ」ボタン
document.getElementById('p1-next-btn').addEventListener('click', () => {
  showWizardStep(2);
  // 画面リストと必要なら認証パネルを表示
  if (discovered.length) {
    document.getElementById('discovered-url-panel').style.display = '';
    updateTargetPreview();
  }
});

// P2 → P1: 「解析に戻る」ボタン
document.getElementById('p2-back-btn').addEventListener('click', () => {
  showWizardStep(1);
});

// ---- 設定（localStorage）----
function getSettings() { try { return JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {}; } catch { return {}; } }
function applySettings() {
  const s = getSettings();
  // crawl-depth / max-pages は MAX 固定（hidden input）のため上書きしない
  if (s.auth) document.getElementById('auth-path').value = s.auth;
}
function loadSettingsForm() {
  const s = getSettings();
  document.getElementById('set-depth').value = s.depth || 2;
  document.getElementById('set-max').value = s.maxPages || 30;
  document.getElementById('set-auth').value = s.auth || '';
}
document.getElementById('save-settings').addEventListener('click', () => {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify({
    depth: document.getElementById('set-depth').value,
    maxPages: document.getElementById('set-max').value,
    auth: document.getElementById('set-auth').value.trim(),
  }));
  applySettings();
  const msg = document.getElementById('settings-msg'); msg.classList.add('show');
  setTimeout(() => msg.classList.remove('show'), 2000);
});

// ---- 履歴 ----
async function loadHistory() {
  const body = document.getElementById('history-body');
  body.innerHTML = '<div class="empty">読み込み中...</div>';
  try {
    const res = await fetch('/api/history');
    const data = await res.json();
    if (!data.items.length) { body.innerHTML = '<div class="empty">まだ監視対象がありません。「+ サイトを追加」から最初のサイトをクロールしてください。</div>'; return; }
    let html = '<table class="data"><thead><tr><th>サイト</th><th class="num">画面数</th><th class="num">入力項目</th><th>形式</th><th>最終クロール</th><th>操作</th></tr></thead><tbody>';
    for (const it of data.items) {
      const badges = (it.formats || []).map(f => `<span class="fmt-badge">${escHtml(f)}</span>`).join('');
      html += `<tr><td><strong>${escHtml(it.domain)}</strong></td><td class="num">${it.screens}</td><td class="num">${it.fields}</td>` +
        `<td><div class="fmt-badges">${badges || '—'}</div></td><td>${escHtml(it.updated)}</td>` +
        `<td><div class="history-actions">` +
        `<button type="button" class="btn-outline-sm hist-recrawl" data-domain="${escHtml(it.domain)}">再クロール</button>` +
        `<button type="button" class="btn-primary hist-open" data-domain="${escHtml(it.domain)}" style="height:36px;padding:0 14px;font-size:13px">開く</button>` +
        `</div></td></tr>`;
    }
    html += '</tbody></table>';
    body.innerHTML = html;
    body.querySelectorAll('.hist-open').forEach(b => b.addEventListener('click', () => openResultsForDomain(b.dataset.domain)));
    body.querySelectorAll('.hist-recrawl').forEach(b => b.addEventListener('click', () => recrawlSite(b.dataset.domain)));
  } catch (e) { body.innerHTML = '<div class="empty">サイト一覧の読み込みに失敗しました。</div>'; }
}
document.getElementById('reload-history').addEventListener('click', loadHistory);

// ---- 再クロール（ドリフト検知）: 既知のサイトを同じ画面構成で取り直す ----

async function recrawlSite(domain) {
  let site = null, urls = [], auth = getSettings().auth || '';
  try { site = (await fetch('/api/site?domain=' + encodeURIComponent(domain)).then(r => r.json())).site; } catch (e) {}
  if (site) {
    urls = site.urls || [];
    auth = site.auth_path || auth;
  } else {
    try {
      const data = await fetch('/api/result?domain=' + encodeURIComponent(domain)).then(r => r.json());
      if (data.files && data.files.json) {
        const rj = await fetch('/preview?path=' + encodeURIComponent(data.files.json)).then(r => r.json());
        urls = (rj.screens || []).map(s => ({ url: s.url, title: s.title || s.url }));
      }
    } catch (e) {}
  }
  if (!urls.length) urls = [{ url: 'https://' + domain + '/', title: domain }];

  // P2へ遷移して前回設定を復元
  switchView('generate');
  executionView.classList.add('hidden'); resultPanel.classList.add('hidden');
  appContent.classList.remove('is-executing'); genPanel.style.display = '';

  document.getElementById('url-input').value = 'https://' + domain + '/';
  if (auth) document.getElementById('auth-path').value = auth;
  document.getElementById('compare').checked = true;
  document.getElementById('p1-summary').style.display = 'none';

  // 前回の画面リストを復元
  discovered = (Array.isArray(urls) ? urls : []).map(u =>
    typeof u === 'string'
      ? { url: u, title: u, login_required: false, login_reasons: [], login_url: '' }
      : { url: u.url, title: u.title || u.url, login_required: false, login_reasons: [], login_url: '' }
  );
  renderDiscovered();
  updateTargetPreview();
  showWizardStep(2);
}

async function openResultsForDomain(domain) {
  switchView('generate');
  genPanel.style.display = 'none';
  executionView.classList.add('hidden');
  appContent.classList.add('is-executing');
  resultPanel.classList.remove('hidden');
  resultHero.innerHTML = '<div class="hero-msg">読み込み中…</div>';
  await showResults(domain);
}


// ====================== ウィザード ======================
let wizardStep = 1;
let discovered = [];
const urlInput = document.getElementById('url-input');
const crawlDiscoverySection = document.getElementById('crawl-discovery-section');
const targetPreview = document.getElementById('target-preview');
const targetPreviewList = document.getElementById('target-preview-list');

function showStep(n) { wizardStep = n; }
urlInput.addEventListener('input', () => { clearDiscovered(); updateTargetPreview(); });


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

// ---- シンプルログイン（インラインパネル）----
document.getElementById('login-simple-btn').addEventListener('click', async () => {
  const domain = loginDomain();
  const loginUrl = document.getElementById('login-inline-url').value.trim()
    || document.getElementById('login-url').value.trim();
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  if (!loginUrl) { document.getElementById('login-simple-status').textContent = 'ログインURLが見つかりません。上級設定でURLを入力してください。'; return; }

  const btn = document.getElementById('login-simple-btn');
  const loading = document.getElementById('login-simple-loading');
  const status = document.getElementById('login-simple-status');
  btn.disabled = true; loading.style.display = 'flex'; status.textContent = '';
  try {
    const res = await fetch('/api/login/simple', { method: 'POST', body: new URLSearchParams({
      domain: domain || 'site', login_url: loginUrl, username, password,
    }) });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.error || 'ログインに失敗しました');
    document.getElementById('auth-path').value = data.auth_path || ('output/' + domain + '/auth.json');
    status.textContent = 'ログイン成功。認証後ページを再解析しています…';
    status.classList.remove('input-field-message-error');
    // パスワードフィールドをクリア（セキュリティ）
    document.getElementById('login-password').value = '';
    document.getElementById('login-inline-panel').style.display = 'none';
    await discoverUrls(true);
  } catch (e) {
    status.textContent = e.message;
    status.classList.add('input-field-message-error');
  } finally {
    btn.disabled = false; loading.style.display = 'none';
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
  const el = document.getElementById('discover-elapsed');
  if (el) el.textContent = '';
}

// skipLoginSection=true のとき（ログイン後の再解析）はログインセクションを再展開しない
async function discoverUrls(skipLoginSection) {
  const url = urlInput.value.trim();
  if (!url) { setUrlMessage('URLを入力してから画面分析を実行してください', true); return; }
  const loading = document.getElementById('discover-loading');
  const status = document.getElementById('discover-status');
  const btn = document.getElementById('discover-btn');
  loading.style.display = 'flex'; status.textContent = ''; status.classList.remove('discover-status-error');
  btn.disabled = true;
  _startDiscoverTimer();
  try {
    const auth = document.getElementById('auth-path').value.trim() || getSettings().auth || '';
    const body = new URLSearchParams({ url, depth: '5', max_pages: '300', auth });
    const res = await fetch('/api/discover', { method: 'POST', body });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || '画面リスト取得に失敗しました');
    discovered = (data.pages || []).filter(p => p && p.url);
    renderDiscovered();
    if (!skipLoginSection && discovered.some(p => p.login_required)) {
      // インラインログインパネルを表示
      const inlinePanel = document.getElementById('login-inline-panel');
      if (inlinePanel) {
        inlinePanel.style.display = '';
        // ログインURLを自動セット
        const loginPage = discovered.find(p => p.login_required && p.login_url);
        const detectedLoginUrl = loginPage ? loginPage.login_url : '';
        const hiddenUrl = document.getElementById('login-inline-url');
        if (hiddenUrl) hiddenUrl.value = detectedLoginUrl;
        // 上級設定のURLフィールドにも反映
        const advUrl = document.getElementById('login-url');
        if (advUrl && !advUrl.value && detectedLoginUrl) advUrl.value = detectedLoginUrl;
      }
    }
    const loginCount = discovered.filter(p => p.login_required).length;
    if (discovered.length) {
      const summary = document.getElementById('p1-summary');
      const countEl = document.getElementById('p1-count-text');
      const hintEl = document.getElementById('p1-login-hint');
      if (summary) {
        countEl.textContent = `${discovered.length}件の画面を検出しました`;
        hintEl.textContent = loginCount ? `うち${loginCount}件がログインを必要とします` : '';
        summary.style.display = '';
      }
      status.textContent = '';
    } else {
      status.textContent = '画面が0件でした。URLを確認してください。';
    }
  } catch (e) {
    clearDiscovered(); status.textContent = e.message; status.classList.add('discover-status-error');
  } finally {
    _stopDiscoverTimer();
    loading.style.display = 'none'; btn.disabled = false; updateTargetPreview();
  }
}
function renderDiscovered() {
  const panel = document.getElementById('discovered-url-panel');
  const list = document.getElementById('discovered-url-list');
  panel.style.display = discovered.length ? '' : 'none';
  list.innerHTML = discovered.map((it, i) => `
    <label class="discovered-url-item">
      <input type="checkbox" class="discovered-cb" value="${escHtml(it.url)}" checked />
      <span><strong>${escHtml(it.title || ('タイトル未取得 ' + (i + 1)))}</strong><code>${escHtml(it.url)}</code>${it.login_required ? `<span class="disc-login-badge" title="${escHtml('認証が必要な可能性があります（根拠: ' + ((it.login_reasons || []).join(', ') || '不明') + '）。不要ならチェックを外してスキップできます。')}">要ログイン</span>` : ''}</span>
    </label>`).join('');
  list.querySelectorAll('.discovered-cb').forEach(cb => cb.addEventListener('change', updateTargetPreview));
}
function clearDiscovered() {
  discovered = [];
  document.getElementById('discovered-url-panel').style.display = 'none';
  document.getElementById('discovered-url-list').innerHTML = '';
  document.getElementById('discover-status').textContent = '';
  document.getElementById('login-inline-panel').style.display = 'none';
  document.getElementById('login-simple-status').textContent = '';
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

// ====================== 実行 ======================
const genPanel = document.getElementById('gen-panel');
const executionView = document.getElementById('execution-view');
const appContent = document.getElementById('app-content');
const execTitle = document.getElementById('exec-title');
const execMessage = document.getElementById('exec-message');
const execElapsed = document.getElementById('exec-elapsed');
const execProgressBar = document.getElementById('exec-progress-bar');
const execTarget = document.getElementById('exec-target');
const execPhase = document.getElementById('exec-phase');
const execLog = document.getElementById('exec-log');
const execError = document.getElementById('exec-error');
const execActions = document.getElementById('exec-actions');
const execRunningActions = document.getElementById('exec-running-actions');
const previewImage = document.getElementById('exec-preview-image');
const previewPlaceholder = document.getElementById('exec-preview-placeholder');
const estep = [0,1,2,3].map(i => document.getElementById('estep-' + i));
let timer, startTime, previewTimer, activeDomain = '';
let runAbort = null, lastRun = null, activeRunId = '';

function domainOf(url) { try { return new URL(url).host; } catch { return ''; } }
function startTimer() { startTime = Date.now(); timer = setInterval(() => { const s = Math.floor((Date.now() - startTime) / 1000); execElapsed.textContent = String(Math.floor(s / 60)).padStart(2,'0') + ':' + String(s % 60).padStart(2,'0'); }, 500); }
function stopTimer() { clearInterval(timer); }
function setStep(idx) { estep.forEach((el, i) => { el.className = 'execution-step' + (i < idx ? ' is-complete' : i === idx ? ' is-active' : ''); }); execProgressBar.style.width = (8 + idx * 23) + '%'; }
function guessStep(line) {
  if (line.includes('解析') || line.includes('analyz')) return 2;
  if (line.includes('グラフ') || line.includes('graph') || line.includes('保存') || line.includes('出力') || line.includes('完了')) return 3;
  if (line.includes('クロール') || line.includes('crawl') || line.includes('ページ')) return 1;
  return -1;
}
function startPreviewPolling() {
  if (!activeDomain) return;
  const poll = () => {
    const img = new Image();
    img.onload = () => { previewImage.src = img.src; previewImage.classList.add('show'); previewPlaceholder.classList.add('hidden'); };
    img.src = `/api/live-screenshot?domain=${encodeURIComponent(activeDomain)}&t=${Date.now()}`;
  };
  poll(); previewTimer = setInterval(poll, 1500);
}
function stopPreviewPolling() { clearInterval(previewTimer); }

document.getElementById('form').addEventListener('submit', (e) => {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (!url) { setUrlMessage('URL を入力してください', true); return; }
  const urls = buildTargetUrls();
  if (!urls.length) {
    setUrlMessage(discovered.length ? 'ドキュメント化する画面を1件以上選択してください' : '先に「画面分析」を実行してください', true);
    return;
  }
  const body = new URLSearchParams({
    urls: urls.join(','),
    depth: document.getElementById('crawl-depth').value,
    max_pages: document.getElementById('max-pages').value,
    format: 'html,pdf,md,excel,json',
    compare: document.getElementById('compare').checked ? 'true' : 'false',
    auth: document.getElementById('auth-path').value.trim() || getSettings().auth || '',
    crawl_mode: 'crawl',
  });
  const label = urls.length > 1 ? `${urls[0]} ほか ${urls.length - 1}件` : urls[0];
  runWith(body.toString(), domainOf(urls[0]), label, urls.length);
});

async function runWith(bodyStr, domain, label, urlCount) {
  lastRun = { bodyStr, domain, label, urlCount };
  activeDomain = domain;
  runAbort = new AbortController();
  genPanel.style.display = 'none';
  resultPanel.classList.add('hidden');
  executionView.classList.remove('hidden');
  appContent.classList.add('is-executing');
  execError.classList.add('hidden'); execActions.classList.add('hidden');
  execRunningActions.classList.remove('hidden');
  const stopBtn = document.getElementById('exec-stop-btn');
  stopBtn.disabled = false; stopBtn.textContent = '停止';
  previewImage.classList.remove('show'); previewPlaceholder.classList.remove('hidden');
  execLog.textContent = '';
  execTarget.textContent = label;
  execTitle.textContent = 'クロール中…'; execMessage.textContent = `${urlCount}件の対象をクロールしてドキュメント化します。`;
  execPhase.textContent = '実行中'; setStep(0); startTimer(); startPreviewPolling();

  activeRunId = '';
  let reportPath = '', summary = null, ok = false, cur = 0, cancelled = false, sessionExpired = false;
  try {
    const res = await fetch('/run', { method: 'POST', body: bodyStr, headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, signal: runAbort.signal });
    const reader = res.body.getReader(); const dec = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      const chunk = dec.decode(value);
      const ri = chunk.match(/RUN_ID:(.*)/); if (ri) activeRunId = ri[1].trim();
      const rp = chunk.match(/REPORT_PATH:(.*)/); if (rp) { reportPath = rp[1].trim(); ok = true; }
      const sm = chunk.match(/SUMMARY:(.*)/); if (sm) { try { summary = JSON.parse(sm[1].trim()); ok = true; } catch {} }
      if (/(^|\\n)\\s*停止しました。/.test(chunk)) cancelled = true;
      if (/SESSION_EXPIRED/.test(chunk)) sessionExpired = true;
      const clean = chunk.replace(/(RUN_ID|REPORT_PATH|PDF_PATH|SUMMARY):.*\\n?/g, '');
      execLog.textContent += clean; execLog.scrollTop = execLog.scrollHeight;
      for (const line of clean.split('\\n')) { const st = guessStep(line); if (st >= 0 && st >= cur) { cur = st; setStep(st); } }
    }
  } catch (err) {
    if (err.name === 'AbortError') cancelled = true;
    else execLog.textContent += '\\n通信エラー: ' + err.message;
  }

  stopTimer(); stopPreviewPolling(); execRunningActions.classList.add('hidden');
  if (sessionExpired) {
    execActions.classList.remove('hidden');
    execTitle.textContent = 'セッションが失効しています'; execPhase.textContent = '要再ログイン';
    execMessage.textContent = '保存済みのログインセッションが失効していたため、ドリフト誤検知を防ぐためクロールを中断しました（前回の結果は保持されています）。入力に戻り「ログイン情報の設定」から再ログインしてください。';
  } else if (cancelled) {
    execActions.classList.remove('hidden');
    execTitle.textContent = '実行を停止しました'; execPhase.textContent = '停止';
    execMessage.textContent = '停止要求により処理を終了しました。必要に応じて入力に戻って再実行してください。';
  } else if (ok || reportPath) {
    setStep(4); execProgressBar.style.width = '100%';
    estep.forEach(el => el.className = 'execution-step is-complete');
    execTitle.textContent = '生成完了'; execPhase.textContent = '完了';
    execMessage.textContent = 'ドキュメントの生成が完了しました。';
    document.getElementById('btn-view-report').style.display = '';
    execActions.classList.remove('hidden');
    _showCompletionPopup(Math.floor((Date.now() - startTime) / 1000));
  } else {
    execActions.classList.remove('hidden');
    execTitle.textContent = 'エラー'; execPhase.textContent = 'エラー'; execError.classList.remove('hidden');
  }
}

document.getElementById('exec-stop-btn').addEventListener('click', async () => {
  const stopBtn = document.getElementById('exec-stop-btn');
  stopBtn.disabled = true; stopBtn.textContent = '停止中…';
  execMessage.textContent = '停止要求を送信しています…';
  // サーバ側のクロールプロセスを確実に終了させてから、クライアントの受信を中断する
  if (activeRunId) {
    try { await fetch('/api/cancel', { method: 'POST', body: new URLSearchParams({ run_id: activeRunId }) }); } catch (e) {}
  }
  if (runAbort) runAbort.abort();
});

document.getElementById('exec-new-btn').addEventListener('click', () => {
  switchView('generate');
  executionView.classList.add('hidden'); resultPanel.classList.add('hidden');
  appContent.classList.remove('is-executing'); genPanel.style.display = '';
  showWizardStep(2);
});
document.getElementById('r-new-btn').addEventListener('click', () => switchView('dashboard'));
document.getElementById('btn-view-report').addEventListener('click', () => showResults(activeDomain));
document.getElementById('r-recrawl-btn').addEventListener('click', () => {
  const domain = document.getElementById('r-domain').textContent.trim();
  if (domain && domain !== '-') recrawlSite(domain);
});

// ====================== 結果ページ（QAビュー軸） ======================
const resultPanel = document.getElementById('result-panel');
const resultHero = document.getElementById('result-hero');
const EXPORT_DEFS = [
  { key: 'html', label: 'HTMLレポート', desc: 'テスト分析インプット文書（画面別カード＋テスト条件）' },
  { key: 'pdf', label: 'PDF', desc: '配布・印刷用（HTMLレポートのPDF版）' },
  { key: 'screens_md', label: 'Markdown（画面一覧）', desc: 'screens.md' },
  { key: 'forms_md', label: 'Markdown（フォーム）', desc: 'forms.md' },
  { key: 'excel', label: 'Excel', desc: 'spec.xlsx（表計算で編集）' },
  { key: 'json', label: 'JSON（機械可読）', desc: '自動化・連携用の構造化データ' },
  { key: 'diff', label: '差分レポート', desc: '前回スナップショットとの差分' },
];
let resultData = null, reportJson = null, activeResultTab = 'overview';

async function showResults(domain) {
  let data;
  try {
    const res = await fetch('/api/result?domain=' + encodeURIComponent(domain));
    data = await res.json();
    if (!res.ok) throw new Error(data.error || '結果の取得に失敗しました');
  } catch (e) {
    // 実行ビューが隠れている（履歴から開いた）場合は結果領域にエラーを表示
    executionView.classList.add('hidden'); resultPanel.classList.remove('hidden');
    appContent.classList.add('is-executing');
    setHeader(['ダッシュボード', domain], domain);
    resultHero.innerHTML = `<div class="hero-msg"><p>結果の取得に失敗しました。</p><p style="font-size:13px;color:var(--text-muted)">${escHtml(e.message)}</p></div>`;
    return;
  }
  resultData = data;
  reportJson = null;
  if (data.files && data.files.json) {
    try { reportJson = await fetch('/preview?path=' + encodeURIComponent(data.files.json)).then(r => r.json()); } catch (e) {}
  }
  const s = data.summary || {};
  const required = reportJson ? countRequired(reportJson) : 0;
  const crawledAt = reportJson && reportJson.meta ? reportJson.meta.crawled_at : '';
  document.getElementById('r-crawled').textContent = crawledAt ? ('最終クロール: ' + crawledAt) : '';
  document.getElementById('r-domain').textContent = domain;
  document.getElementById('r-screens').textContent = s.screens || 0;
  document.getElementById('r-forms').textContent = s.forms || 0;
  document.getElementById('r-fields').textContent = s.fields || 0;
  document.getElementById('r-required').textContent = required;
  document.getElementById('r-buttons').textContent = s.buttons || 0;
  setHeader(['ダッシュボード', domain], domain);

  executionView.classList.add('hidden'); resultPanel.classList.remove('hidden');
  _buildExportDropdown(data);
  showWizardStep(4);
  selectResultTab('overview');
}

function _buildExportDropdown(data) {
  const menu = document.getElementById('export-dropdown-menu');
  if (!menu) return;
  const files = (data && data.files) || {};
  const domain = (document.getElementById('r-domain') || {}).textContent || '';
  const defs = [
    { key: 'html', label: 'HTMLレポート' },
    { key: 'pdf', label: 'PDF' },
    { key: 'json', label: 'JSON' },
    { key: 'excel', label: 'Excel' },
    { key: 'screens_md', label: 'Markdown（画面一覧）' },
    { key: 'transition_mmd', label: '遷移図（Mermaid）' },
    { key: 'diff', label: '差分レポート' },
  ];
  const zipRow = `<div class="export-dropdown-item is-zip"><span>すべてZIPでダウンロード</span><a href="/download-zip?domain=${encodeURIComponent(domain)}" class="btn-primary" style="height:28px;padding:0 10px;font-size:12px">DL</a></div>`;
  const fileRows = defs.map(d => {
    if (files[d.key]) {
      return `<div class="export-dropdown-item"><span>${escHtml(d.label)}</span><div style="display:flex;gap:4px"><a href="/preview?path=${encodeURIComponent(files[d.key])}" target="_blank" class="btn-outline-sm" style="height:28px;padding:0 8px;font-size:12px">開く</a><a href="/download?path=${encodeURIComponent(files[d.key])}" class="btn-outline-sm" style="height:28px;padding:0 8px;font-size:12px" download>DL</a></div></div>`;
    }
    return `<div class="export-dropdown-item is-missing"><span>${escHtml(d.label)}（未生成）</span></div>`;
  }).join('');
  menu.innerHTML = zipRow + fileRows;
}

// エクスポートドロップダウンの開閉
document.getElementById('export-dropdown-btn').addEventListener('click', (e) => {
  e.stopPropagation();
  document.getElementById('export-dropdown').classList.toggle('is-open');
});
document.addEventListener('click', () => {
  const dd = document.getElementById('export-dropdown');
  if (dd) dd.classList.remove('is-open');
});

document.querySelectorAll('.result-tab').forEach(t => {
  t.addEventListener('click', () => selectResultTab(t.dataset.tab));
  t.addEventListener('keydown', e => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const tabs = [...document.querySelectorAll('.result-tab')].filter(x => x.offsetParent !== null);
    const i = tabs.indexOf(t);
    const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    if (next) { selectResultTab(next.dataset.tab); next.focus(); }
  });
});
function selectResultTab(tab) {
  activeResultTab = tab;
  document.querySelectorAll('.result-tab').forEach(t => {
    const on = t.dataset.tab === tab;
    t.classList.toggle('is-active', on);
    t.setAttribute('aria-selected', on ? 'true' : 'false');
    t.tabIndex = on ? 0 : -1;
  });
  if (tab === 'overview') renderOverview();
  else if (tab === 'matrix') renderMatrix();
  else if (tab === 'report') renderReport();
  else if (tab === 'design') renderDesign();
  else if (tab === 'transition') renderTransition();
  else if (tab === 'transition-table') renderTransitionTable();
  else if (tab === 'history') renderTimeline();
}

// ---- 履歴・差分（クロール履歴タイムライン＋任意2点の仕様ドリフト比較）----
let timelineDomain = '';
async function renderTimeline() {
  const domain = document.getElementById('r-domain').textContent.trim();
  timelineDomain = domain;
  resultHero.innerHTML = '<div class="hero-msg">クロール履歴を読み込み中…</div>';
  let snaps = [];
  try {
    const data = await fetch('/api/snapshots?domain=' + encodeURIComponent(domain)).then(r => r.json());
    snaps = data.snapshots || [];
  } catch (e) {}
  if (snaps.length < 2) {
    resultHero.innerHTML = '<div class="hero-pad"><div class="hero-section-title">クロール履歴</div>' +
      '<p style="color:var(--text-muted);font-size:13px">履歴が' + snaps.length + '件です。<strong>再クロール</strong>すると、前回との仕様ドリフト（追加/削除された画面・変更されたフォーム）を時系列で比較できます。</p></div>';
    return;
  }
  // 既定: to=最新(0), from=ひとつ前(1)
  const rows = snaps.map((s, i) => `
    <tr>
      <td style="text-align:center"><input type="radio" name="snap-from" value="${escHtml(s.id)}" ${i === 1 ? 'checked' : ''}></td>
      <td style="text-align:center"><input type="radio" name="snap-to" value="${escHtml(s.id)}" ${i === 0 ? 'checked' : ''}></td>
      <td>${escHtml(s.label)}${i === 0 ? ' <span class="tl-latest">最新</span>' : ''}</td>
      <td class="num">${s.screens}</td><td class="num">${s.forms}</td><td class="num">${s.fields}</td>
    </tr>`).join('');
  resultHero.innerHTML = '<div class="hero-pad">' +
    '<div class="hero-section-title">クロール履歴（' + snaps.length + '件）</div>' +
    '<p style="color:var(--text-muted);font-size:13px;margin-bottom:10px">比較する2時点を選び、仕様ドリフトを確認します（比較元＝古い／比較先＝新しい）。</p>' +
    '<table class="ov-screens tl-table"><thead><tr><th>比較元</th><th>比較先</th><th>クロール日時</th><th>画面</th><th>フォーム</th><th>入力項目</th></tr></thead><tbody>' +
    rows + '</tbody></table>' +
    '<div style="margin:12px 0"><button type="button" class="btn-primary" id="tl-diff-btn">この2時点の差分を表示</button></div>' +
    '<div class="tl-diff-frame" id="tl-diff"></div></div>';
  document.getElementById('tl-diff-btn').addEventListener('click', showTimelineDiff);
  showTimelineDiff();
}
function showTimelineDiff() {
  const from = (document.querySelector('input[name=snap-from]:checked') || {}).value;
  const to = (document.querySelector('input[name=snap-to]:checked') || {}).value;
  const box = document.getElementById('tl-diff');
  if (!from || !to) { box.innerHTML = '<div class="hero-msg">2時点を選択してください。</div>'; return; }
  if (from === to) { box.innerHTML = '<div class="hero-msg">異なる2時点を選択してください。</div>'; return; }
  box.innerHTML = `<iframe src="/api/snapshot-diff?domain=${encodeURIComponent(timelineDomain)}&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}" title="仕様ドリフト差分"></iframe>`;
}

// ====================== 完了ポップアップ ======================
function _showCompletionPopup(elapsedSec) {
  const overlay = document.getElementById('completion-overlay');
  const elapsedEl = document.getElementById('popup-elapsed');
  if (!overlay) return;
  const m = Math.floor(elapsedSec / 60);
  const s = elapsedSec % 60;
  elapsedEl.textContent = `${m}:${String(s).padStart(2, '0')}`;
  overlay.classList.remove('hidden');
}

document.getElementById('popup-close-btn').addEventListener('click', () => {
  document.getElementById('completion-overlay').classList.add('hidden');
});
document.getElementById('popup-view-report-btn').addEventListener('click', () => {
  document.getElementById('completion-overlay').classList.add('hidden');
  showResults(activeDomain);
});
document.getElementById('completion-overlay').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) document.getElementById('completion-overlay').classList.add('hidden');
});

