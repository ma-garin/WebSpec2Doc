
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
// 「+ サイトを追加」: 新規ウィザードを開く
function openAddSite() {
  switchView('generate');
  executionView.classList.add('hidden'); resultPanel.classList.add('hidden');
  appContent.classList.remove('is-executing'); genPanel.style.display = '';
  document.getElementById('url-input').value = '';
  clearDiscovered(); updateTargetPreview(); showStep(1);
}
document.getElementById('add-site-btn').addEventListener('click', openAddSite);
document.getElementById('add-site-btn-2').addEventListener('click', openAddSite);

// ---- 設定（localStorage）----
function getSettings() { try { return JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {}; } catch { return {}; } }
function applySettings() {
  const s = getSettings();
  if (s.depth) document.getElementById('crawl-depth').value = s.depth;
  if (s.maxPages) document.getElementById('max-pages').value = s.maxPages;
  if (Array.isArray(s.formats)) document.querySelectorAll('input[name=fmt]').forEach(c => { c.checked = s.formats.includes(c.value); });
  if (s.auth) document.getElementById('auth-path').value = s.auth;
}
function loadSettingsForm() {
  const s = getSettings();
  document.getElementById('set-depth').value = s.depth || 2;
  document.getElementById('set-max').value = s.maxPages || 30;
  const fmts = Array.isArray(s.formats) ? s.formats : ['html','md'];
  document.querySelectorAll('input[name=set-fmt]').forEach(c => { c.checked = fmts.includes(c.value); });
  document.getElementById('set-auth').value = s.auth || '';
}
document.getElementById('save-settings').addEventListener('click', () => {
  const formats = [...document.querySelectorAll('input[name=set-fmt]:checked')].map(c => c.value);
  localStorage.setItem(SETTINGS_KEY, JSON.stringify({
    depth: document.getElementById('set-depth').value,
    maxPages: document.getElementById('set-max').value,
    formats,
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
const FILE_TO_FMT = { html: 'html', pdf: 'pdf', excel: 'excel', screens_md: 'md', json: 'json' };
async function recrawlSite(domain) {
  // 保存済み site.json があれば前回設定を忠実に再現。無ければ旧データ用フォールバック。
  let site = null;
  try { site = (await fetch('/api/site?domain=' + encodeURIComponent(domain)).then(r => r.json())).site; } catch (e) {}
  let urls = [], depth = '2', maxPages = '300', fmts = [], auth = getSettings().auth || '';
  if (site) {
    urls = site.urls || [];
    depth = String(site.depth || 2);
    maxPages = String(site.max_pages || 300);
    fmts = site.formats || [];
    auth = site.auth_path || auth;
  } else {
    try {
      const data = await fetch('/api/result?domain=' + encodeURIComponent(domain)).then(r => r.json());
      fmts = Object.keys(FILE_TO_FMT).filter(k => (data.files || {})[k]).map(k => FILE_TO_FMT[k]);
      if (data.files && data.files.json) {
        const rj = await fetch('/preview?path=' + encodeURIComponent(data.files.json)).then(r => r.json());
        urls = (rj.screens || []).map(s => s.url).filter(Boolean);
      }
    } catch (e) {}
  }
  if (!urls.length) urls = ['https://' + domain + '/'];
  if (!fmts.length) fmts = ['html', 'md'];
  if (!fmts.includes('json')) fmts.push('json');
  const body = new URLSearchParams({
    urls: urls.join(','), depth: depth, max_pages: maxPages,
    format: fmts.join(','), compare: 'true', auth: auth,
  });
  switchView('generate');
  runWith(body.toString(), domain, domain, urls.length);
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

// ====================== 出力形式セレクター ======================
const FORMAT_DEFS = [
  {
    key: 'html', label: 'HTML レポート', defaultOn: true,
    desc: 'ブラウザで読むテストベース文書',
    includes: ['画面一覧（サイドバー）', '入力項目・テスト条件', 'ロケータ候補', 'スクリーンショット'],
    mock: '<div class="fmt-mock-html"><div class="fmt-mock-sidebar"><div class="fmt-mock-bar"></div><div class="fmt-mock-bar short"></div><div class="fmt-mock-bar short"></div></div><div class="fmt-mock-body"><div class="fmt-mock-heading"></div><div class="fmt-mock-line"></div><div class="fmt-mock-line short"></div><div class="fmt-mock-table"><div class="fmt-mock-row"></div><div class="fmt-mock-row"></div></div></div></div>',
  },
  {
    key: 'pdf', label: 'PDF', defaultOn: false,
    desc: '配布・印刷用ドキュメント',
    includes: ['HTMLレポートと同等の内容', '印刷・共有に最適化'],
    mock: '<div class="fmt-mock-pdf"><div class="fmt-mock-pdf-title"></div><div class="fmt-mock-line"></div><div class="fmt-mock-line short"></div><div class="fmt-mock-line"></div><div class="fmt-mock-line short"></div></div>',
  },
  {
    key: 'md', label: 'Markdown', defaultOn: true,
    desc: '軽量テキスト形式',
    includes: ['画面一覧', 'フォーム一覧', '遷移図（Mermaid）'],
    mock: '<div class="fmt-mock-md"><div class="fmt-mock-md-h1"></div><div class="fmt-mock-md-h2"></div><div class="fmt-mock-line"></div><div class="fmt-mock-line short"></div><div class="fmt-mock-md-h2"></div><div class="fmt-mock-line"></div></div>',
  },
  {
    key: 'excel', label: 'Excel', defaultOn: false,
    desc: '表計算ソフトで編集可能',
    includes: ['入力項目一覧（シート）', 'テスト条件一覧（シート）'],
    mock: '<div class="fmt-mock-excel"><div class="fmt-mock-excel-header"><div></div><div></div><div></div><div></div></div><div class="fmt-mock-excel-row"><div></div><div></div><div></div><div></div></div><div class="fmt-mock-excel-row alt"><div></div><div></div><div></div><div></div></div><div class="fmt-mock-excel-row"><div></div><div></div><div></div><div></div></div></div>',
  },
  {
    key: 'json', label: 'JSON', defaultOn: false,
    desc: '自動化・CI連携用の構造化データ',
    includes: ['全画面・フォーム・フィールド', 'テスト条件', 'ロケータ候補'],
    mock: '<div class="fmt-mock-json"><span class="fmt-mock-brace">{</span><div class="fmt-mock-json-line"><span class="fmt-mock-key">"screens"</span>: [<span class="fmt-mock-brace">…</span>]</div><div class="fmt-mock-json-line"><span class="fmt-mock-key">"summary"</span>: {<span class="fmt-mock-brace">…</span>}</div><span class="fmt-mock-brace">}</span></div>',
  },
];

(function initFormatCards() {
  const container = document.getElementById('fmt-cards');
  const preview = document.getElementById('fmt-preview');
  if (!container) return;

  FORMAT_DEFS.forEach(def => {
    const card = document.createElement('label');
    card.className = 'fmt-card' + (def.defaultOn ? ' is-selected' : '');
    card.dataset.key = def.key;
    card.innerHTML = `<input type="checkbox" name="fmt" value="${escHtml(def.key)}"${def.defaultOn ? ' checked' : ''} style="display:none"><span class="fmt-card-label">${escHtml(def.label)}</span>`;
    card.addEventListener('click', (e) => {
      e.preventDefault();
      const cb = card.querySelector('input[type=checkbox]');
      cb.checked = !cb.checked;
      card.classList.toggle('is-selected', cb.checked);
      showFormatPreview(def);
    });
    card.addEventListener('mouseenter', () => showFormatPreview(def));
    container.appendChild(card);
  });

  function showFormatPreview(def) {
    preview.style.display = '';
    preview.innerHTML = `<div class="fmt-preview-mock">${def.mock}</div><div class="fmt-preview-info"><p class="fmt-preview-desc">${escHtml(def.desc)}</p><ul class="fmt-preview-includes">${def.includes.map(i => `<li>${escHtml(i)}</li>`).join('')}</ul></div>`;
  }
})();

// ====================== ウィザード ======================
let wizardStep = 1;
let discovered = [];
const urlInput = document.getElementById('url-input');
const crawlDiscoverySection = document.getElementById('crawl-discovery-section');
const targetPreview = document.getElementById('target-preview');
const targetPreviewList = document.getElementById('target-preview-list');

function showStep(n) {
  for (let i = 1; i <= 2; i++) {
    document.getElementById('wpage-' + i).classList.toggle('is-active', i === n);
    const node = document.getElementById('wnode-' + i);
    node.classList.toggle('is-active', i === n);
    node.classList.toggle('is-done', i < n);
  }
  document.getElementById('wline-12').classList.toggle('is-done', n > 1);
  wizardStep = n;
}
urlInput.addEventListener('input', () => { clearDiscovered(); updateTargetPreview(); });

document.getElementById('wnext-1').addEventListener('click', () => {
  const url = urlInput.value.trim();
  if (!url) { setUrlMessage('URL を入力してください', true); return; }
  if (!selectedDiscovered().length) {
    setUrlMessage(discovered.length ? 'ドキュメント化する画面を1件以上選択してください' : '先に「画面リスト取得」を実行してください', true);
    return;
  }
  setUrlMessage(''); showStep(2);
});
document.getElementById('wback-2').addEventListener('click', () => showStep(1));

function setUrlMessage(msg, isError) {
  const el = document.getElementById('url-input-message');
  el.textContent = msg; el.classList.toggle('input-field-message-error', !!(msg && isError));
}

// ---- 画面リスト取得（discover）----
document.getElementById('discover-btn').addEventListener('click', discoverUrls);

// ---- 手渡しログイン（ADR-0001: サブプロセス＋シグナル）----
function loginDomain() {
  const u = urlInput.value.trim();
  try { return new URL(u).hostname; } catch (e) { return ''; }
}
function setLoginStatus(msg, isError) {
  const el = document.getElementById('login-status');
  el.textContent = msg; el.classList.toggle('input-field-message-error', !!(msg && isError));
}
document.getElementById('login-start-btn').addEventListener('click', async () => {
  const domain = loginDomain();
  if (!domain) { setLoginStatus('先に有効なURLを入力してください', true); return; }
  const startBtn = document.getElementById('login-start-btn');
  const finishBtn = document.getElementById('login-finish-btn');
  startBtn.disabled = true;
  setLoginStatus('ログイン用ブラウザを起動しています…', false);
  try {
    const res = await fetch('/api/login/start', { method: 'POST', body: new URLSearchParams({ url: urlInput.value.trim(), domain }) });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'ログイン開始に失敗しました');
    setLoginStatus('ブラウザでログインを完了したら「ログイン完了」を押してください。', false);
    finishBtn.disabled = false;
  } catch (e) {
    setLoginStatus(e.message, true); startBtn.disabled = false;
  }
});
document.getElementById('login-finish-btn').addEventListener('click', async () => {
  const domain = loginDomain();
  const startBtn = document.getElementById('login-start-btn');
  const finishBtn = document.getElementById('login-finish-btn');
  finishBtn.disabled = true;
  setLoginStatus('セッションを保存しています…', false);
  try {
    const res = await fetch('/api/login/finish', { method: 'POST', body: new URLSearchParams({ domain }) });
    const data = await res.json();
    if (!res.ok || !data.session_saved) throw new Error(data.error || 'セッション保存に失敗しました');
    setLoginStatus('ログインセッションを保存しました。認証後ページを取得できます。', false);
    document.getElementById('auth-path').value = 'output/' + domain + '/auth.json';
  } catch (e) {
    setLoginStatus(e.message, true); finishBtn.disabled = false;
  } finally {
    startBtn.disabled = false;
  }
});
document.getElementById('select-all-btn').addEventListener('click', () => setAllDiscovered(true));
document.getElementById('clear-all-btn').addEventListener('click', () => setAllDiscovered(false));
async function discoverUrls() {
  const url = urlInput.value.trim();
  if (!url) { setUrlMessage('URLを入力してから画面リスト取得を実行してください', true); return; }
  const loading = document.getElementById('discover-loading');
  const status = document.getElementById('discover-status');
  const btn = document.getElementById('discover-btn');
  loading.style.display = 'flex'; status.textContent = ''; status.classList.remove('discover-status-error'); btn.disabled = true;
  try {
    const body = new URLSearchParams({
      url, depth: document.getElementById('crawl-depth').value,
      max_pages: document.getElementById('max-pages').value, auth: getSettings().auth || document.getElementById('auth-path').value.trim() || '',
    });
    const res = await fetch('/api/discover', { method: 'POST', body });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || '画面リスト取得に失敗しました');
    discovered = (data.pages || []).filter(p => p && p.url);
    renderDiscovered();
    status.textContent = discovered.length ? `${discovered.length}件の画面を取得しました。対象を選択してください。` : '画面リストは0件でした。URLや階層数を確認してください。';
  } catch (e) {
    clearDiscovered(); status.textContent = e.message; status.classList.add('discover-status-error');
  } finally {
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
  const urls = buildTargetUrls();
  if (!urls.length) { showStep(1); setUrlMessage('対象URLが確定していません', true); return; }
  const fmts = [...document.querySelectorAll('input[name=fmt]:checked')].map(c => c.value);
  if (!fmts.length) { showStep(2); return; }
  const body = new URLSearchParams({
    urls: urls.join(','),
    depth: document.getElementById('crawl-depth').value,
    max_pages: document.getElementById('max-pages').value,
    format: fmts.join(','),
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
    execMessage.textContent = '保存済みのログインセッションが失効していたため、ドリフト誤検知を防ぐためクロールを中断しました（前回の結果は保持されています）。入力に戻り「ログイン用ブラウザを開く」から再ログインしてください。';
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

document.getElementById('exec-new-btn').addEventListener('click', () => switchView('dashboard'));
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
  selectResultTab('overview');
}

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
  else if (tab === 'history') renderTimeline();
  else if (tab === 'export') renderExport();
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

function allFields(rj) {
  const rows = [];
  for (const sc of (rj.screens || [])) {
    for (const fm of (sc.forms || [])) {
      for (const fld of (fm.fields || [])) rows.push({ screen: sc.page_id, title: sc.title || '', field: fld });
    }
  }
  return rows;
}
function countRequired(rj) { return allFields(rj).filter(r => r.field.required).length; }
function constraintText(f) {
  const p = [];
  if (f.maxlength != null) p.push('最大' + f.maxlength + '文字');
  if (f.minlength != null) p.push('最小' + f.minlength + '文字');
  if (f.min_value) p.push('min=' + f.min_value);
  if (f.max_value) p.push('max=' + f.max_value);
  if (f.pattern) p.push('pattern=' + f.pattern);
  if (f.placeholder) p.push('例: ' + f.placeholder);
  return p.join(' / ');
}
function defaultOptionsText(f) {
  if (f.options && f.options.length) return f.options.filter(Boolean).join(', ').slice(0, 120);
  return f.default || '';
}

// ---- 概要 ----
function renderOverview() {
  if (!reportJson) {
    const shots = (resultData.screenshots || []).map(p =>
      `<a href="/preview?path=${encodeURIComponent(p)}" target="_blank"><figure><img src="/preview?path=${encodeURIComponent(p)}" loading="lazy" alt="${escHtml(p.split('/').pop())}"><figcaption>${escHtml(p.split('/').pop())}</figcaption></figure></a>`).join('');
    resultHero.innerHTML = '<div class="hero-pad">' +
      '<p style="color:var(--text-muted);font-size:13px;margin-bottom:12px">このサイトは旧バージョンで生成されたため画面別の構造化データがありません。「<strong>再クロール</strong>」で最新のテスト条件マトリクスを生成できます。詳細は「画面別仕様」タブを参照してください。</p>' +
      (shots ? '<div class="hero-section-title">スクリーンショット</div><div class="r-shots">' + shots + '</div>' : '') +
      '</div>';
    return;
  }
  const screens = reportJson.screens || [];
  const meta = reportJson.meta || {};
  const rows = screens.map(sc => {
    const fields = (sc.forms || []).reduce((n, fm) => n + (fm.fields || []).length, 0);
    const to = (sc.transitions && sc.transitions.to || []).join(', ') || '—';
    return `<tr><td class="c-screen">${escHtml(sc.page_id)}</td><td>${escHtml(sc.title || '')}</td>` +
      `<td><code style="font-size:.78rem;color:var(--text-muted)">${escHtml(sc.url || '')}</code></td>` +
      `<td class="num">${(sc.forms || []).length}</td><td class="num">${fields}</td><td>${escHtml(to)}</td></tr>`;
  }).join('');
  // 現在のクロールに含まれる画面IDのスクショだけ表示（過去の残骸を除外）
  const pageIds = new Set(screens.map(sc => sc.page_id));
  const shots = (resultData.screenshots || []).filter(p => pageIds.has(p.split('/').pop().replace(/\\.png$/, ''))).map(p =>
    `<a href="/preview?path=${encodeURIComponent(p)}" target="_blank"><figure><img src="/preview?path=${encodeURIComponent(p)}" loading="lazy" alt="${escHtml(p.split('/').pop())}"><figcaption>${escHtml(p.split('/').pop())}</figcaption></figure></a>`).join('');
  resultHero.innerHTML = '<div class="hero-pad">' +
    `<p style="color:var(--text-muted);font-size:13px;margin-bottom:12px">対象 ${escHtml(meta.target_url || '')} ／ クロール: 深さ${meta.crawl_depth ?? '-'} ・最大${meta.max_pages ?? '-'}ページ ／ ${escHtml(meta.crawled_at || '')}</p>` +
    '<div class="hero-section-title">画面インベントリ</div>' +
    '<table class="ov-screens"><thead><tr><th>画面ID</th><th>タイトル</th><th>URL</th><th>フォーム</th><th>入力項目</th><th>遷移先</th></tr></thead><tbody>' +
    (rows || '<tr><td colspan="6" style="color:var(--text-muted)">画面がありません</td></tr>') + '</tbody></table>' +
    (shots ? '<div class="hero-section-title" style="margin-top:18px">スクリーンショット</div><div class="r-shots">' + shots + '</div>' : '') +
    '</div>';
}

// ---- 入力項目・テスト条件マトリクス ----
function renderMatrix() {
  if (!reportJson) { resultHero.innerHTML = '<div class="hero-msg">マトリクスデータ（report.json）を読み込めませんでした。</div>'; return; }
  const screens = (reportJson.screens || []).map(s => s.page_id);
  resultHero.innerHTML =
    '<div class="matrix-toolbar">' +
    '<select id="mx-screen"><option value="">全画面</option>' + screens.map(s => `<option value="${escHtml(s)}">${escHtml(s)}</option>`).join('') + '</select>' +
    '<input type="search" id="mx-search" placeholder="項目名・条件で検索" />' +
    '<label><input type="checkbox" id="mx-required"> 必須のみ</label>' +
    '<button type="button" class="btn-outline-sm" id="mx-csv">CSVで書き出し</button>' +
    '<span class="matrix-count" id="mx-count"></span>' +
    '<span class="cond-legend">種別:' +
    '<span class="cond-pill cc-req">必須</span>' +
    '<span class="cond-pill cc-bound">境界値</span>' +
    '<span class="cond-pill cc-format">形式</span>' +
    '<span class="cond-pill cc-opt">選択肢</span>' +
    '<span class="cond-pill cc-other">その他</span>' +
    '</span>' +
    '</div><div id="mx-table-wrap"></div>';
  let t = null;
  const debounced = () => { clearTimeout(t); t = setTimeout(drawMatrix, 150); };
  document.getElementById('mx-screen').addEventListener('change', drawMatrix);
  document.getElementById('mx-search').addEventListener('input', debounced);
  document.getElementById('mx-required').addEventListener('change', drawMatrix);
  document.getElementById('mx-csv').addEventListener('click', exportMatrixCsv);
  drawMatrix();
}
function condClass(c) {
  if (c.includes('必須')) return 'cc-req';
  if (c.includes('最大長') || c.includes('最小長') || c.includes('範囲') || c.includes('境界')) return 'cc-bound';
  if (c.includes('形式') || c.includes('メール') || c.includes('パターン') || c.includes('日付') || c.includes('電話') || c.includes('数値') || c.includes('パスワード')) return 'cc-format';
  if (c.includes('選択肢') || c.includes('ON / OFF') || c.includes('未選択')) return 'cc-opt';
  return 'cc-other';
}
function matrixRows() {
  const scFilter = (document.getElementById('mx-screen') || {}).value || '';
  const q = ((document.getElementById('mx-search') || {}).value || '').toLowerCase();
  const reqOnly = (document.getElementById('mx-required') || {}).checked;
  return allFields(reportJson).filter(r => {
    if (scFilter && r.screen !== scFilter) return false;
    if (reqOnly && !r.field.required) return false;
    if (q) {
      const hay = (r.field.name + ' ' + (r.field.test_conditions || []).join(' ') + ' ' + constraintText(r.field)).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}
function drawMatrix() {
  const rows = matrixRows();
  document.getElementById('mx-count').textContent = rows.length + ' 項目';
  const body = rows.map(r => {
    const f = r.field;
    return '<tr>' +
      `<td class="c-screen">${escHtml(r.screen)}</td>` +
      `<td>${escHtml(f.name || '(無名)')}</td>` +
      `<td>${escHtml(f.field_type || '')}</td>` +
      `<td>${f.required ? '<span class="c-req">必須</span>' : '-'}</td>` +
      `<td>${escHtml(constraintText(f)) || '-'}</td>` +
      `<td>${escHtml(defaultOptionsText(f)) || '-'}</td>` +
      `<td class="c-loc">${escHtml((f.locators || []).join(' / ')) || '-'}</td>` +
      `<td class="c-cond">${(f.test_conditions || []).map(c => `<span class="cond-pill ${condClass(c)}">${escHtml(c)}</span>`).join('') || '-'}</td>` +
    '</tr>';
  }).join('');
  document.getElementById('mx-table-wrap').innerHTML =
    '<table class="matrix"><thead><tr><th>画面</th><th>項目名</th><th>型</th><th>必須</th><th>制約</th><th>既定/選択肢</th><th>ロケータ候補</th><th>導出テスト条件</th></tr></thead><tbody>' +
    (body || '<tr><td colspan="8" style="padding:16px;color:var(--text-muted)">該当する入力項目がありません</td></tr>') + '</tbody></table>';
}
function exportMatrixCsv() {
  const head = ['画面', '項目名', '型', '必須', '制約', '既定/選択肢', 'ロケータ候補', '導出テスト条件'];
  const esc = v => '"' + String(v).replace(/"/g, '""') + '"';
  const lines = [head.map(esc).join(',')];
  for (const r of matrixRows()) {
    const f = r.field;
    lines.push([r.screen, f.name || '(無名)', f.field_type || '', f.required ? '必須' : '', constraintText(f), defaultOptionsText(f), (f.locators || []).join(' / '), (f.test_conditions || []).join(' / ')].map(esc).join(','));
  }
  const blob = new Blob(['\\uFEFF' + lines.join('\\r\\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'test_conditions.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
}

// ---- 画面別仕様（HTMLレポート埋め込み）----
function renderReport() {
  if (!reportJson || !(reportJson.screens || []).length) {
    resultHero.innerHTML = '<div class="hero-msg"><p>画面別仕様データ（report.json）がありません。</p><p style="font-size:13px">出力形式で「HTML」または「JSON」を選んで再クロールすると表示されます。</p></div>';
    return;
  }
  const screens = reportJson.screens;
  const pageIds = new Set(screens.map(s => s.page_id));
  const allShots = (resultData.screenshots || []).filter(p => pageIds.has(p.split('/').pop().replace(/\.png$/, '')));

  resultHero.innerHTML =
    '<div class="rpt-pane-wrap">' +
    '<div class="rpt-list" id="rpt-list"></div>' +
    '<div class="rpt-detail" id="rpt-detail"><p class="hero-msg" style="padding:24px">左の一覧から画面を選択してください。</p></div>' +
    '</div>';

  const list = document.getElementById('rpt-list');
  screens.forEach((sc, idx) => {
    const item = document.createElement('div');
    item.className = 'rpt-list-item' + (idx === 0 ? ' is-active' : '');
    item.dataset.pid = sc.page_id;
    item.innerHTML = `<strong>${escHtml(sc.page_id)}</strong><span>${escHtml(sc.title || '')}</span>`;
    item.addEventListener('click', () => {
      list.querySelectorAll('.rpt-list-item').forEach(el => el.classList.remove('is-active'));
      item.classList.add('is-active');
      renderReportDetail(sc, allShots);
    });
    list.appendChild(item);
  });
  renderReportDetail(screens[0], allShots);
}

function renderReportDetail(sc, allShots) {
  const detail = document.getElementById('rpt-detail');
  if (!detail) return;
  const shotPath = allShots.find(p => p.split('/').pop().replace(/\.png$/, '') === sc.page_id);
  const shotHtml = shotPath
    ? `<div class="rpt-shots"><img src="/preview?path=${encodeURIComponent(shotPath)}" class="rpt-thumb" loading="lazy" alt="${escHtml(sc.page_id)}" onclick="openLightbox('${escHtml('/preview?path=' + encodeURIComponent(shotPath))}')" /></div>`
    : '';
  let fieldRows = '';
  for (const fm of (sc.forms || [])) {
    for (const f of (fm.fields || [])) {
      const conds = (f.test_conditions || []).map(c => `<span class="cond-pill ${condClass(c)}">${escHtml(c)}</span>`).join('');
      fieldRows +=
        `<tr><td>${escHtml(f.name || '')}</td>` +
        `<td>${escHtml(f.field_type || '')}</td>` +
        `<td>${f.required ? '●' : ''}</td>` +
        `<td>${escHtml(constraintText(f))}</td>` +
        `<td>${escHtml(defaultOptionsText(f))}</td>` +
        `<td><code class="loc-hint">${escHtml((f.locators || [])[0] || '')}</code></td>` +
        `<td class="cond-cell">${conds || '—'}</td></tr>`;
    }
  }
  const tableHtml = fieldRows
    ? '<table class="rpt-field-table"><thead><tr><th>項目名</th><th>型</th><th>必須</th><th>制約</th><th>既定・選択肢</th><th>ロケータ候補</th><th>テスト条件</th></tr></thead><tbody>' + fieldRows + '</tbody></table>'
    : '<p style="color:var(--text-muted);font-size:13px">この画面には入力フォームがありません。</p>';
  detail.innerHTML =
    `<div class="rpt-detail-header"><h3>${escHtml(sc.title || sc.page_id)}</h3><code class="rpt-url">${escHtml(sc.url || '')}</code></div>` +
    shotHtml + tableHtml;
}

// ---- エクスポート ----
function renderExport() {
  const files = resultData.files || {};
  const rows = EXPORT_DEFS.map(d => {
    const path = files[d.key];
    if (path) {
      return `<div class="export-row"><div class="export-main"><strong>${escHtml(d.label)}</strong><span class="export-desc">${escHtml(d.desc)}</span></div>` +
        `<a class="btn-outline-sm" href="/preview?path=${encodeURIComponent(path)}" target="_blank">開く</a>` +
        `<a class="btn-primary" style="height:36px;padding:0 16px;font-size:13px;display:inline-flex;align-items:center" href="/download?path=${encodeURIComponent(path)}" download>DL</a></div>`;
    }
    return `<div class="export-row export-missing"><div class="export-main"><strong>${escHtml(d.label)}</strong><span class="export-desc">未生成（出力形式で選択すると生成されます）</span></div></div>`;
  }).join('');
  resultHero.innerHTML = '<div class="hero-pad"><div class="export-grid">' +
    `<div class="export-row" style="background:var(--info-bg);border-color:var(--info-border)"><div class="export-main"><strong>すべてまとめてダウンロード</strong><span class="export-desc">生成物一式を ZIP で取得</span></div>` +
    `<a class="btn-primary" style="height:36px;padding:0 16px;font-size:13px;display:inline-flex;align-items:center" href="/download-zip?domain=${encodeURIComponent(resultData_domain())}">ZIP DL</a></div>` +
    rows + '</div></div>';
}
function resultData_domain() { return document.getElementById('r-domain').textContent || ''; }

// ---- 設定サブタブ ----
document.querySelectorAll('.set-tab').forEach(t => t.addEventListener('click', () => {
  document.querySelectorAll('.set-tab').forEach(x => x.classList.toggle('is-active', x === t));
  document.querySelectorAll('.set-panel').forEach(p => p.classList.toggle('is-active', p.id === 'set-panel-' + t.dataset.tab));
}));

// ---- API設定（.env にサーバ保存）----
function flash(id) { const m = document.getElementById(id); m.classList.add('show'); setTimeout(() => m.classList.remove('show'), 2000); }
async function loadApiSettings() {
  try {
    const res = await fetch('/api/settings'); const s = await res.json();
    document.getElementById('api-model').value = s.openai_model || 'gpt-5.4-mini';
    document.getElementById('api-org').value = s.openai_org_id || '';
    document.getElementById('api-project').value = s.openai_project_id || '';
    document.getElementById('api-key-current').textContent = s.openai_key_set ? s.openai_key_masked : '未設定';
  } catch (e) {}
}
document.getElementById('save-api').addEventListener('click', async () => {
  await fetch('/api/settings', { method: 'POST', body: new URLSearchParams({
    api_key: document.getElementById('api-key').value,
    org_id: document.getElementById('api-org').value,
    project_id: document.getElementById('api-project').value,
  }) });
  document.getElementById('api-key').value = ''; flash('api-msg'); loadApiSettings();
});
document.getElementById('save-model').addEventListener('click', async () => {
  await fetch('/api/settings', { method: 'POST', body: new URLSearchParams({ model: document.getElementById('api-model').value }) });
  flash('model-msg'); loadApiSettings();
});

// ---- URL履歴 datalist ----
async function loadUrlHistory() {
  try {
    const res = await fetch('/api/history'); const data = await res.json();
    const dl = document.getElementById('url-history-list');
    dl.innerHTML = (data.items || []).map(it => `<option value="https://${escHtml(it.domain)}/">`).join('');
  } catch (e) {}
}

// 初期化
applySettings(); loadSettingsForm(); loadApiSettings(); loadUrlHistory(); updateTargetPreview(); switchView('dashboard');
