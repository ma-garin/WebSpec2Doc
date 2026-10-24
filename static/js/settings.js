// ---- 設定タブ切替（APIキー・モデル/クロール既定値/通知）----
// 従来 .set-tab ボタンに click ハンドラが未実装で「タブ操作ができない」不具合があったため追加。
// タブは URL（/settings/<tab>）にも反映する。従来は class を切り替えるだけで
// URL が変わらず、共有・ブックマーク・ブラウザの戻るがいずれも効かなかった。
// URL の形（/settings/<tab>）の解釈は core.js の _subPathOf() に一本化している。
const SETTINGS_TAB_DEFAULT = 'api';

function selectSettingsTab(tab, opts = {}) {
  const tabs = [...document.querySelectorAll('.set-tabs .set-tab')];
  if (!tabs.some(t => t.dataset.tab === tab)) return false;
  tabs.forEach(t => {
    const on = t.dataset.tab === tab;
    t.classList.toggle('is-active', on);
    t.setAttribute('aria-selected', on ? 'true' : 'false');
    t.tabIndex = on ? 0 : -1;
  });
  document.querySelectorAll('.set-panel').forEach(p => {
    p.classList.toggle('is-active', p.id === 'set-panel-' + tab);
  });
  if (!opts.skipHistory && location.pathname !== '/settings/' + tab) {
    try { history.pushState({ view: 'settings', tab }, '', '/settings/' + tab); } catch (e) {}
  }
  return true;
}

// URL からタブを復元する。core.js の switchView('settings') と popstate から呼ばれる。
// データ管理・監査ログは権限が無いとタブ自体が描画されないため、直接開かれた場合は
// 既定タブへ落とし、URL も置き換える（開けない画面を指す URL を残さないため）。
function syncSettingsTabFromPath() {
  const wanted = _subPathOf(location.pathname) || SETTINGS_TAB_DEFAULT;
  const applied = selectSettingsTab(wanted, { skipHistory: true }) ? wanted : SETTINGS_TAB_DEFAULT;
  if (applied !== wanted) {
    selectSettingsTab(applied, { skipHistory: true });
    try {
      history.replaceState({ view: 'settings', tab: applied }, '', '/settings/' + applied);
    } catch (e) {}
  }
  loadSettingsTabData(applied);
}

// タブを URL に載せたことで、戻る/進むのたびにここが走るようになった。
// 毎回読み直すと同じ API を叩き続けるため、一度読んだタブは飛ばす。
// 各ローダーは自前で例外を捕まえるので、失敗しても「読んだ」扱いになる。
// 明示的な再取得は各タブの更新ボタン（data-refresh / audit-refresh）が担う。
const _settingsTabLoaded = new Set();
const SETTINGS_TAB_LOADERS = {
  operations: () => loadOperationalSites(),
  integrations: () => loadIntegrations(),
  data: () => loadDataManagement(),
  audit: () => { loadApprovalPolicy(); loadAdminAudit(); },
};

async function loadSettingsTabData(tab) {
  const loader = SETTINGS_TAB_LOADERS[tab];
  if (!loader || _settingsTabLoaded.has(tab)) return;
  _settingsTabLoaded.add(tab);
  await loader();
}
document.querySelectorAll('.set-tabs .set-tab').forEach(t => {
  t.addEventListener('click', () => {
    selectSettingsTab(t.dataset.tab);
    loadSettingsTabData(t.dataset.tab);
  });
  t.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const tabs = [...document.querySelectorAll('.set-tabs .set-tab')];
    const i = tabs.indexOf(t);
    const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    if (next) { selectSettingsTab(next.dataset.tab); loadSettingsTabData(next.dataset.tab); next.focus(); }
  });
});

// ---- 設定（localStorage）----
function getSettings() { try { return JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {}; } catch { return {}; } }
function applySettings() {
  const s = getSettings();
  // crawl-depth / max-pages はウィザードの自動解析モードでのみ使う値のため
  // ここでは上書きしない（既定値のまま）。
  if (s.auth) document.getElementById('auth-path').value = s.auth;
  // 並列数はウィザードの条件設定にあり、既定値をここで反映する。
  const par = document.getElementById('crawl-parallelism');
  if (par && s.parallelism) par.value = String(s.parallelism);
}
function loadSettingsForm() {
  const s = getSettings();
  document.getElementById('set-depth').value = s.depth || 2;
  document.getElementById('set-max').value = s.maxPages || 30;
  document.getElementById('set-auth').value = s.auth || '';
  const parEl = document.getElementById('set-parallelism');
  if (parEl) parEl.value = String(s.parallelism || 4);
  const caseEl = document.getElementById('set-case-minutes');
  if (caseEl) caseEl.value = s.caseMinutes || 10;
  const urlHistEl = document.getElementById('set-url-history-limit');
  if (urlHistEl) urlHistEl.value = String(s.urlHistoryLimit ?? 10);
}
document.getElementById('save-settings').addEventListener('click', () => {
  const caseEl = document.getElementById('set-case-minutes');
  const urlHistEl = document.getElementById('set-url-history-limit');
  const urlHistoryLimit = urlHistEl ? (Number(urlHistEl.value) || 0) : 10;
  const parEl = document.getElementById('set-parallelism');
  localStorage.setItem(SETTINGS_KEY, JSON.stringify({
    depth: document.getElementById('set-depth').value,
    maxPages: document.getElementById('set-max').value,
    parallelism: parEl ? (Number(parEl.value) || 4) : 4,
    auth: document.getElementById('set-auth').value.trim(),
    caseMinutes: caseEl ? (Number(caseEl.value) || 10) : 10,
    urlHistoryLimit,
  }));
  if (urlHistEl && urlHistoryLimit === 0) {
    try { localStorage.removeItem('wsd_url_history'); } catch (_) {}
  }
  applySettings();
  const msg = document.getElementById('settings-msg'); msg.classList.add('show');
  setTimeout(() => msg.classList.remove('show'), 2000);
});

// ---- サーバー設定（API Key / Slack Webhook）の読み込みと保存 ----
async function loadServerSettings() {
  try {
    const data = await fetch('/api/settings').then(r => r.json());
    const keyEl = document.getElementById('api-key-current');
    if (keyEl) {
      if (data.openai_key_set) {
        keyEl.innerHTML = `<span class="badge-ok" style="display:inline-block;padding:2px 10px;border-radius:12px;background:var(--ok-bg);color:var(--ok);font-size:12px;font-weight:700">AI機能：有効</span> ${escHtml(data.openai_key_masked)}`;
      } else {
        keyEl.innerHTML = `<span class="badge-info" style="display:inline-block;padding:2px 10px;border-radius:12px;background:var(--info-bg);color:var(--primary-dark);font-size:12px;font-weight:700">AI機能：APIキー未設定</span> <span style="color:var(--text-muted);font-size:12px">設定するとテストケース自動生成が有効になります</span>`;
      }
    }
    const slackEl = document.getElementById('slack-webhook-current');
    if (slackEl) {
      slackEl.textContent = data.slack_webhook_set
        ? `設定済み (${data.slack_webhook_masked})`
        : '未設定（設定するとドリフト検知時にSlack通知が届きます）';
    }
    if (data.openai_model) {
      const modelEl = document.getElementById('api-model');
      if (modelEl) modelEl.value = data.openai_model;
    }
    const baseUrlEl = document.getElementById('llm-base-url');
    if (baseUrlEl) baseUrlEl.value = data.llm_base_url || OLLAMA_DEFAULT_BASE_URL;
    const llmModelEl = document.getElementById('llm-model');
    if (llmModelEl) llmModelEl.dataset.selected = data.llm_model || '';
    setLlmProvider(data.llm_provider || 'openai');
    await loadAllowLocalToggle();
  } catch (e) { /* 設定読み込み失敗は無視 */ }
}

async function saveApiKey() {
  const provider = currentLlmProvider();
  const form = new FormData();
  form.append('llm_provider', provider);
  if (provider === 'ollama') {
    form.append('llm_base_url', document.getElementById('llm-base-url')?.value?.trim() || OLLAMA_DEFAULT_BASE_URL);
    form.append('llm_model', document.getElementById('llm-model')?.value || OLLAMA_DEFAULT_MODEL);
  } else {
    const key = document.getElementById('api-key')?.value?.trim() || '';
    const org = document.getElementById('api-org')?.value?.trim() || '';
    const proj = document.getElementById('api-project')?.value?.trim() || '';
    if (key) form.append('api_key', key);
    if (org) form.append('org_id', org);
    if (proj) form.append('project_id', proj);
    form.append('model', document.getElementById('api-model')?.value || '');
  }
  try {
    const res = await fetch('/api/settings', { method: 'POST', body: form });
    const data = await res.json();
    if (data.ok) {
      const msg = document.getElementById('api-msg'); msg.classList.add('show');
      setTimeout(() => msg.classList.remove('show'), 2500);
      await loadServerSettings();
    }
  } catch (e) { showToast('設定の保存に失敗しました', 'error'); }
}

const OLLAMA_DEFAULT_BASE_URL = 'http://127.0.0.1:11434/v1';
const OLLAMA_DEFAULT_MODEL = 'qwen2.5:3b';

// セグメントで選択中のプロバイダ
function currentLlmProvider() {
  return document.querySelector('#llm-seg [role="tab"][aria-selected="true"]')?.dataset.provider || 'openai';
}

// 選択したプロバイダの設定だけを表示する（OpenAI と Ollama は同時に出さない）
function setLlmProvider(provider) {
  document.querySelectorAll('#llm-seg [role="tab"]').forEach(tab => {
    tab.setAttribute('aria-selected', String(tab.dataset.provider === provider));
  });
  document.querySelectorAll('[data-llm-panel]').forEach(panel => {
    panel.style.display = panel.dataset.llmPanel === provider ? '' : 'none';
  });
  const reloadBtn = document.getElementById('reload-ollama-models');
  if (reloadBtn) reloadBtn.style.display = provider === 'ollama' ? '' : 'none';
  // OpenAI 固有の操作（APIキー削除）は Ollama 選択時に隠す
  document.querySelectorAll('[data-llm-only]').forEach(el => {
    el.style.display = el.dataset.llmOnly === provider ? '' : 'none';
  });
  if (provider === 'ollama') loadOllamaModels();
}

// Ollama が実際に保持しているモデルを取得してプルダウンへ流し込む
async function loadOllamaModels() {
  const select = document.getElementById('llm-model');
  const status = document.getElementById('ollama-status');
  if (!select) return;
  const baseUrl = document.getElementById('llm-base-url')?.value?.trim() || OLLAMA_DEFAULT_BASE_URL;
  const wanted = select.dataset.selected || select.value || '';
  select.innerHTML = '<option value="">読み込み中…</option>';
  try {
    const url = '/api/settings/llm-models?base_url=' + encodeURIComponent(baseUrl);
    const data = await fetch(url).then(r => r.json());
    if (data.ok && data.models.length) {
      // モデル名は外部プロセス由来のため innerHTML を使わず DOM API で組む
      select.replaceChildren(...data.models.map(m => {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m;
        return opt;
      }));
      if (wanted && data.models.includes(wanted)) select.value = wanted;
      if (status) status.textContent = `${data.models.length} 件のモデルを検出しました。API キーは不要です。`;
    } else {
      select.innerHTML = '<option value="">（取得できませんでした）</option>';
      if (status) status.textContent = 'Ollama に接続できませんでした。起動しているか、ベース URL が正しいか確認してください。';
    }
  } catch (e) {
    select.innerHTML = '<option value="">（取得できませんでした）</option>';
    if (status) status.textContent = 'モデル一覧の取得に失敗しました。';
  }
}

document.querySelectorAll('#llm-seg [role="tab"]').forEach(tab => {
  tab.addEventListener('click', () => setLlmProvider(tab.dataset.provider));
});
document.getElementById('reload-ollama-models')?.addEventListener('click', loadOllamaModels);
document.getElementById('llm-base-url')?.addEventListener('change', loadOllamaModels);

async function testConnection() {
  const btn = document.getElementById('test-connection');
  const msg = document.getElementById('test-connection-msg');
  if (!msg) return;
  if (btn) { btn.disabled = true; btn.textContent = '疎通確認中…'; }
  msg.classList.remove('show', 'is-error');
  try {
    const res = await fetch('/api/settings/test-connection', { method: 'POST' });
    const data = await res.json();
    msg.textContent = data.message || (data.ok ? '接続に成功しました。' : '接続に失敗しました。');
    msg.classList.toggle('is-error', !data.ok);
    msg.classList.add('show');
  } catch (e) {
    msg.textContent = '疎通確認リクエストに失敗しました。';
    msg.classList.add('show', 'is-error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '疎通確認'; }
  }
}

// 保存済みの OpenAI API キーを明示的に削除する。
// 空欄保存では既存キーを保持するため、消す操作を別に用意している。
async function clearApiKey() {
  const btn = document.getElementById('clear-api-key');
  const msg = document.getElementById('api-status-msg');
  if (!confirm('保存済みの API キーを削除します。よろしいですか？')) return;
  if (btn) { btn.disabled = true; btn.textContent = '削除中…'; }
  try {
    const res = await fetch('/api/settings/clear-key', { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      const keyInput = document.getElementById('api-key');
      if (keyInput) keyInput.value = '';
      await loadServerSettings();  // 「現在のキー」表示を最新化
      if (msg) { msg.textContent = 'API キーを削除しました。'; msg.classList.remove('is-error'); msg.classList.add('show'); }
    } else if (msg) {
      msg.textContent = '削除に失敗しました。'; msg.classList.add('show', 'is-error');
    }
  } catch (e) {
    if (msg) { msg.textContent = '削除リクエストに失敗しました。'; msg.classList.add('show', 'is-error'); }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'API キーを削除'; }
  }
}

async function saveSlackWebhook() {
  const url = document.getElementById('slack-webhook-url')?.value?.trim() || '';
  const form = new FormData();
  form.append('slack_webhook_url', url);
  try {
    const res = await fetch('/api/settings', { method: 'POST', body: form });
    const data = await res.json();
    if (data.ok) {
      const msg = document.getElementById('slack-msg'); msg.classList.add('show');
      setTimeout(() => msg.classList.remove('show'), 2500);
      await loadServerSettings();
    }
  } catch (e) { showToast('Slack設定の保存に失敗しました', 'error'); }
}

// 保存済みの Webhook へ実際に送ってみる。保存成功と到達可否は別物なので、
// 結果は必ず slack-msg に文言で返す（成功も失敗も無反応にしない）。
async function testSlackWebhook() {
  const btn = document.getElementById('test-slack');
  const msg = document.getElementById('slack-msg');
  const prev = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = '送信中…'; }
  try {
    const res = await fetch('/api/integrations/slack/test', { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    const ok = res.ok && data.ok === true;
    if (msg) {
      msg.textContent = data.message || (ok ? '送信しました。' : '送信に失敗しました。');
      msg.classList.toggle('is-error', !ok);
      msg.classList.add('show');
    }
  } catch (e) {
    if (msg) {
      msg.textContent = 'テスト送信に失敗しました: ' + String(e && e.message ? e.message : e);
      msg.classList.add('is-error');
      msg.classList.add('show');
    }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = prev || 'テスト送信'; }
  }
}

// ---- 外部サービス連携（Jira / CI / 汎用 Webhook）----
// 通信は必ず try/catch し、失敗時も settings-msg に理由を出す（無反応を作らない）。
function _integrationsMessage(id, text, isError = false) {
  const msg = document.getElementById(id);
  if (!msg) return;
  msg.textContent = text;
  msg.classList.toggle('is-error', isError);
  msg.classList.add('show');
}

// GET /api/integrations の内容をフォームへ反映する。
// API トークンは値を戻さず、jira-current にマスク表示だけを出す。
async function loadIntegrations() {
  if (!document.getElementById('set-panel-integrations')) return;
  try {
    const res = await fetch('/api/integrations');
    if (!res.ok) throw new Error('連携設定を取得できませんでした。');
    const data = await res.json();
    const jira = data.jira || {};
    const setValue = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.value = value || '';
    };
    setValue('jira-base-url', jira.base_url);
    setValue('jira-email', jira.email);
    setValue('jira-project-key', jira.project_key);
    setValue('jira-issue-type', jira.issue_type);
    const token = document.getElementById('jira-api-token');
    if (token) token.value = '';
    const current = document.getElementById('jira-current');
    if (current) {
      current.textContent = jira.configured
        ? `設定済み（${jira.base_url || '—'} / トークン ${jira.token_masked || '****'}）`
        : '未設定';
    }
    const webhook = data.webhook || {};
    const webhookInput = document.getElementById('generic-webhook-url');
    if (webhookInput) webhookInput.value = '';
    if (webhook.configured) {
      _integrationsMessage('webhook-msg', `設定済み: ${webhook.url_masked || '****'}`);
    }
    // Teams / Notion / Confluence。トークンは入力欄へ戻さず xxx-current にマスク表示のみ出す。
    const clearValue = (id) => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    };
    const setCurrent = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    };
    const teams = data.teams || {};
    clearValue('teams-webhook-url');
    setCurrent('teams-current', teams.configured ? `設定済み（${teams.url_masked || '****'}）` : '未設定');
    const notion = data.notion || {};
    clearValue('notion-api-token');
    setValue('notion-database-id', notion.database_id);
    setCurrent('notion-current', notion.configured
      ? `設定済み（DB ${notion.database_id || '—'} / トークン ${notion.token_masked || '****'}）`
      : '未設定');
    const confluence = data.confluence || {};
    clearValue('confluence-api-token');
    setValue('confluence-base-url', confluence.base_url);
    setValue('confluence-email', confluence.email);
    setValue('confluence-space-key', confluence.space_key);
    setCurrent('confluence-current', confluence.configured
      ? `設定済み（${confluence.base_url || '—'} / スペース ${confluence.space_key || '—'} / トークン ${confluence.token_masked || '****'}）`
      : '未設定');
    // QualityForward は API キー 1 項目のみ。キーは入力欄へ戻さずマスク表示だけ出す。
    const qualityforward = data.qualityforward || {};
    clearValue('qf-api-key');
    setCurrent('qf-current', qualityforward.configured
      ? `設定済み（API キー ${qualityforward.key_masked || '****'}）`
      : '未設定');
  } catch (e) {
    _integrationsMessage('jira-msg', e.message || '連携設定を取得できませんでした。', true);
  }
}

async function saveJiraIntegration() {
  const form = new FormData();
  form.append('jira_base_url', document.getElementById('jira-base-url')?.value?.trim() || '');
  form.append('jira_email', document.getElementById('jira-email')?.value?.trim() || '');
  form.append('jira_api_token', document.getElementById('jira-api-token')?.value || '');
  form.append('jira_project_key', document.getElementById('jira-project-key')?.value?.trim() || '');
  form.append('jira_issue_type', document.getElementById('jira-issue-type')?.value?.trim() || '');
  try {
    const res = await fetch('/api/integrations/jira', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'Jira 設定を保存できませんでした。');
    _integrationsMessage('jira-msg', 'Jira 設定を保存しました。');
    await loadIntegrations();
  } catch (e) {
    _integrationsMessage('jira-msg', e.message || 'Jira 設定の保存に失敗しました。', true);
  }
}

async function testJiraIntegration() {
  _integrationsMessage('jira-msg', '接続を確認しています…');
  try {
    const res = await fetch('/api/integrations/jira/test', { method: 'POST' });
    const data = await res.json();
    _integrationsMessage('jira-msg', data.message || (data.ok ? '接続できました。' : '接続できませんでした。'), !data.ok);
  } catch (e) {
    _integrationsMessage('jira-msg', e.message || '接続確認のリクエストに失敗しました。', true);
  }
}

async function saveGenericWebhook() {
  const form = new FormData();
  form.append('webhook_url', document.getElementById('generic-webhook-url')?.value?.trim() || '');
  try {
    const res = await fetch('/api/integrations/webhook', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'Webhook URL を保存できませんでした。');
    _integrationsMessage('webhook-msg', 'Webhook URL を保存しました。');
    await loadIntegrations();
  } catch (e) {
    _integrationsMessage('webhook-msg', e.message || 'Webhook URL の保存に失敗しました。', true);
  }
}

// 接続テストの共通処理。実行中はボタンを disabled にし、finally で必ず元へ戻す。
async function _testIntegration(path, msgId, btnId, busyLabel) {
  const btn = document.getElementById(btnId);
  const prev = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = busyLabel; }
  _integrationsMessage(msgId, busyLabel);
  try {
    const res = await fetch(path, { method: 'POST' });
    const data = await res.json();
    _integrationsMessage(msgId, data.message || (data.ok ? '成功しました。' : '失敗しました。'), !data.ok);
  } catch (e) {
    _integrationsMessage(msgId, e.message || 'リクエストに失敗しました。', true);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = prev; }
  }
}

async function saveTeamsIntegration() {
  const form = new FormData();
  form.append('teams_webhook_url', document.getElementById('teams-webhook-url')?.value?.trim() || '');
  try {
    const res = await fetch('/api/integrations/teams', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'Teams 設定を保存できませんでした。');
    _integrationsMessage('teams-msg', 'Teams 設定を保存しました。');
    await loadIntegrations();
  } catch (e) {
    _integrationsMessage('teams-msg', e.message || 'Teams 設定の保存に失敗しました。', true);
  }
}

async function testTeamsIntegration() {
  await _testIntegration('/api/integrations/teams/test', 'teams-msg', 'test-teams', '送信中…');
}

async function saveNotionIntegration() {
  const form = new FormData();
  form.append('notion_api_token', document.getElementById('notion-api-token')?.value || '');
  form.append('notion_database_id', document.getElementById('notion-database-id')?.value?.trim() || '');
  try {
    const res = await fetch('/api/integrations/notion', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'Notion 設定を保存できませんでした。');
    _integrationsMessage('notion-msg', 'Notion 設定を保存しました。');
    await loadIntegrations();
  } catch (e) {
    _integrationsMessage('notion-msg', e.message || 'Notion 設定の保存に失敗しました。', true);
  }
}

async function testNotionIntegration() {
  await _testIntegration('/api/integrations/notion/test', 'notion-msg', 'test-notion', '確認中…');
}

async function saveConfluenceIntegration() {
  const form = new FormData();
  form.append('confluence_base_url', document.getElementById('confluence-base-url')?.value?.trim() || '');
  form.append('confluence_email', document.getElementById('confluence-email')?.value?.trim() || '');
  form.append('confluence_api_token', document.getElementById('confluence-api-token')?.value || '');
  form.append('confluence_space_key', document.getElementById('confluence-space-key')?.value?.trim() || '');
  try {
    const res = await fetch('/api/integrations/confluence', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'Confluence 設定を保存できませんでした。');
    _integrationsMessage('confluence-msg', 'Confluence 設定を保存しました。');
    await loadIntegrations();
  } catch (e) {
    _integrationsMessage('confluence-msg', e.message || 'Confluence 設定の保存に失敗しました。', true);
  }
}

async function testConfluenceIntegration() {
  await _testIntegration('/api/integrations/confluence/test', 'confluence-msg', 'test-confluence', '確認中…');
}

async function saveQualityForwardIntegration() {
  const form = new FormData();
  form.append('qualityforward_api_key', document.getElementById('qf-api-key')?.value || '');
  try {
    const res = await fetch('/api/integrations/qualityforward', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'QualityForward 設定を保存できませんでした。');
    _integrationsMessage('qf-msg', 'QualityForward 設定を保存しました。');
    await loadIntegrations();
  } catch (e) {
    _integrationsMessage('qf-msg', e.message || 'QualityForward 設定の保存に失敗しました。', true);
  }
}

async function testQualityForwardIntegration() {
  await _testIntegration('/api/integrations/qualityforward/test', 'qf-msg', 'test-qf', '確認中…');
}

async function loadAllowLocalToggle() {
  try {
    const data = await fetch('/api/settings/allow-local').then(r => r.json());
    const el = document.getElementById('allow-local-toggle');
    if (el) el.checked = !!data.allow_local;
  } catch (e) { /* トグル読み込み失敗は無視 */ }
}

async function saveAllowLocal() {
  const enabled = document.getElementById('allow-local-toggle')?.checked ?? false;
  try {
    const res = await fetch('/api/settings/allow-local', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    });
    const data = await res.json();
    if (data.ok) {
      const msg = document.getElementById('allow-local-msg');
      if (msg) { msg.classList.add('show'); setTimeout(() => msg.classList.remove('show'), 2000); }
    }
  } catch (e) { showToast('ローカルクロール設定の保存に失敗しました', 'error'); }
}

// ---- テスト設計（MBT）設定タブ ----
async function loadTestDesignSettings() {
  try {
    const d = await fetch('/api/settings/test-design').then(r => r.json());
    const techs = Array.isArray(d.enabled_techniques) ? d.enabled_techniques : ['bva', 'dt', 'pw', 'st'];
    ['bva', 'dt', 'pw', 'st'].forEach(k => {
      const el = document.getElementById('td-tech-' + k);
      if (el) el.checked = techs.includes(k);
    });
    const setVal = (id, v) => { const el = document.getElementById(id); if (el && v != null) el.value = v; };
    setVal('td-bva-offset', d.bva_offset ?? 1);
    setVal('td-pw-strength', String(d.pairwise_strength ?? 2));
    setVal('td-n-switch', String(d.n_switch ?? 0));
    setVal('td-max-dt', d.max_dt_conditions ?? 4);
    const ta = document.getElementById('td-value-catalog');
    if (ta) ta.value = JSON.stringify(d.value_catalog || {}, null, 2);
  } catch (e) { /* 読み込み失敗は既定値のまま */ }
}

async function saveTestDesignSettings() {
  const msg = document.getElementById('test-design-msg');
  const show = (text, isErr) => {
    if (!msg) return;
    msg.textContent = text; msg.style.display = 'block';
    msg.classList.toggle('is-error', !!isErr); msg.classList.add('show');
  };
  let valueCatalog;
  try {
    valueCatalog = JSON.parse(document.getElementById('td-value-catalog')?.value || '{}');
  } catch (e) {
    show('値カタログのJSONが不正です: ' + e.message, true);
    return;
  }
  const techs = ['bva', 'dt', 'pw', 'st'].filter(k => document.getElementById('td-tech-' + k)?.checked);
  const payload = {
    enabled_techniques: techs,
    bva_offset: parseInt(document.getElementById('td-bva-offset')?.value || '1', 10),
    pairwise_strength: parseInt(document.getElementById('td-pw-strength')?.value || '2', 10),
    n_switch: parseInt(document.getElementById('td-n-switch')?.value || '0', 10),
    max_dt_conditions: parseInt(document.getElementById('td-max-dt')?.value || '4', 10),
    value_catalog: valueCatalog,
  };
  try {
    const res = await fetch('/api/settings/test-design', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    show('テスト設計設定を保存しました。', false);
    setTimeout(() => msg && msg.classList.remove('show'), 2500);
  } catch (e) {
    show('保存に失敗しました: ' + e.message, true);
  }
}

// ---- 運用監視（スケジュール・通知）----
let _operationsSitesLoaded = false;
const _operationsSiteUrls = new Map();

function _opsMessage(text, isError = false) {
  const msg = document.getElementById('ops-msg');
  if (!msg) return;
  msg.textContent = text;
  msg.classList.toggle('is-error', isError);
  msg.classList.add('show');
}

async function loadOperationalSites(force = false) {
  if (_operationsSitesLoaded && !force) return;
  const select = document.getElementById('ops-site');
  if (!select) return;
  const previous = select.value;
  try {
    const res = await fetch('/api/history');
    const data = await res.json();
    const items = data.items || [];
    _operationsSiteUrls.clear();
    items.forEach(item => _operationsSiteUrls.set(item.domain, item.site_url || ''));
    select.innerHTML = items.length
      ? items.map(item => `<option value="${escHtml(item.domain)}">${escHtml(item.domain)}</option>`).join('')
      : '<option value="">解析済みサイトがありません</option>';
    if (items.some(item => item.domain === previous)) select.value = previous;
    _operationsSitesLoaded = true;
    if (select.value) await loadOperationalConfig(select.value);
  } catch (e) {
    _opsMessage('サイト一覧を取得できませんでした。', true);
  }
}

async function loadOperationalConfig(domain) {
  if (!domain) return;
  try {
    const res = await fetch(`/schedule/config?domain=${encodeURIComponent(domain)}`);
    const config = await res.json();
    if (!res.ok) throw new Error(config.error || '設定を取得できませんでした');
    const set = (id, value) => { const el = document.getElementById(id); if (el) el.value = value ?? ''; };
    set('ops-site-url', config.site_url || _operationsSiteUrls.get(domain) || '');
    set('ops-interval', config.interval || 'disabled');
    set('ops-timezone', config.timezone || 'Asia/Tokyo');
    set('ops-window-start', config.window_start || '');
    set('ops-window-end', config.window_end || '');
    set('ops-retry-max', config.retry_max ?? 2);
    set('ops-backoff', config.retry_backoff_seconds ?? 60);
    set('ops-notify-type', config.notify_type || 'none');
    set('ops-summary-limit', config.diff_summary_limit ?? 5);
    set('ops-endpoint', '');
    const endpoint = document.getElementById('ops-endpoint');
    if (endpoint) endpoint.placeholder = config.notify_endpoint_set
      ? '設定済み（変更時のみ入力）'
      : 'https://...';
    set('ops-template', config.notify_template || '');
    const selectedDays = new Set(config.weekdays || []);
    document.querySelectorAll('.ops-weekdays input[type="checkbox"]').forEach(input => {
      input.checked = selectedDays.has(Number(input.value));
    });
    await loadOperationalHistory(domain);
  } catch (e) {
    _opsMessage(e.message || '運用設定を取得できませんでした。', true);
  }
}

function _operationalPayload() {
  const domain = document.getElementById('ops-site')?.value || '';
  return {
    domain,
    site_url: document.getElementById('ops-site-url')?.value?.trim() || '',
    interval: document.getElementById('ops-interval')?.value || 'disabled',
    timezone: document.getElementById('ops-timezone')?.value || 'Asia/Tokyo',
    weekdays: [...document.querySelectorAll('.ops-weekdays input:checked')].map(el => Number(el.value)),
    window_start: document.getElementById('ops-window-start')?.value || '',
    window_end: document.getElementById('ops-window-end')?.value || '',
    retry_max: Number(document.getElementById('ops-retry-max')?.value || 0),
    retry_backoff_seconds: Number(document.getElementById('ops-backoff')?.value || 60),
    notify_type: document.getElementById('ops-notify-type')?.value || 'none',
    notify_endpoint: document.getElementById('ops-endpoint')?.value?.trim() || '',
    notify_template: document.getElementById('ops-template')?.value || '',
    diff_summary_limit: Number(document.getElementById('ops-summary-limit')?.value || 5),
    severity_filter: 'all',
  };
}

async function saveOperationalConfig() {
  const payload = _operationalPayload();
  if (!payload.domain) { _opsMessage('対象サイトを選択してください。', true); return; }
  try {
    const res = await fetch('/schedule/config', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '保存できませんでした');
    _opsMessage(`運用設定を保存しました。次回: ${data.next_run_at || '無効'}`);
    await loadOperationalConfig(payload.domain);
  } catch (e) {
    _opsMessage(e.message || '運用設定を保存できませんでした。', true);
  }
}

async function testOperationalNotification() {
  const payload = _operationalPayload();
  const button = document.getElementById('ops-test-notify');
  if (button) button.disabled = true;
  try {
    const res = await fetch('/schedule/notify/test', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '送信できませんでした');
    _opsMessage(data.message || 'テスト通知を送信しました。');
  } catch (e) {
    _opsMessage(e.message || 'テスト通知を送信できませんでした。', true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function loadOperationalHistory(domain) {
  const container = document.getElementById('ops-history');
  if (!container || !domain) return;
  container.innerHTML = '<p class="input-hint">読み込み中...</p>';
  try {
    const res = await fetch(`/schedule/history?domain=${encodeURIComponent(domain)}&limit=5`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '履歴を取得できませんでした');
    const items = data.items || [];
    if (!items.length) { container.innerHTML = '<p class="input-hint">実行履歴はまだありません。</p>'; return; }
    container.innerHTML = `<table class="ops-history-table"><thead><tr><th>開始</th><th>状態</th><th>試行</th><th>所要時間</th></tr></thead><tbody>${items.map(item => `<tr><td>${escHtml(item.started_at || '')}</td><td><span class="rh-status-badge ${item.status === 'complete' ? 'rh-status-complete' : 'rh-status-failed'}">${item.status === 'complete' ? '完了' : '失敗'}</span></td><td>${Number(item.attempts || 0)}回</td><td>${Number(item.duration_sec || 0).toFixed(1)}秒</td></tr>`).join('')}</tbody></table>`;
  } catch (e) {
    container.innerHTML = `<p class="input-hint">${escHtml(e.message || '履歴を取得できませんでした。')}</p>`;
  }
}

// ---- データ管理（容量・保持）----
function _formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let size = bytes / 1024;
  let unit = units[0];
  for (let i = 1; i < units.length && size >= 1024; i += 1) {
    size /= 1024;
    unit = units[i];
  }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${unit}`;
}

function _adminMessage(id, text, isError = false) {
  const message = document.getElementById(id);
  if (!message) return;
  message.textContent = text;
  message.classList.toggle('is-error', isError);
  message.classList.add('show');
}

async function _adminRequest(url, options) {
  const response = await fetch(url, options);
  let data = {};
  try { data = await response.json(); } catch (_) { data = {}; }
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function updateRetentionFields() {
  const mode = document.getElementById('retention-mode')?.value || 'unlimited';
  const generations = document.getElementById('retention-generations-field');
  const days = document.getElementById('retention-days-field');
  if (generations) generations.hidden = mode !== 'generations';
  if (days) days.hidden = mode !== 'days';
}

async function loadDataManagement() {
  if (!document.getElementById('set-panel-data')) return;
  try {
    const [storageData, retentionData] = await Promise.all([
      _adminRequest('/api/admin/storage'),
      _adminRequest('/api/admin/retention'),
    ]);
    const storage = storageData.storage || {};
    const value = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
    value('storage-output', _formatBytes(storage.output_bytes));
    value('storage-instance', _formatBytes(storage.instance_bytes));
    value('storage-total', _formatBytes(storage.total_bytes));
    const sites = Array.isArray(storage.sites) ? storage.sites : [];
    const body = document.getElementById('storage-sites');
    if (body) {
      body.innerHTML = sites.length ? sites.map(site => `<tr>
        <td>${escHtml(site.domain || '')}</td>
        <td>${Number(site.snapshot_count || 0).toLocaleString('ja-JP')}件</td>
        <td>${_formatBytes(site.snapshot_bytes)}</td>
        <td>${_formatBytes(site.total_bytes)}</td>
        <td>${escHtml(site.updated_at || '—')}</td>
      </tr>`).join('') : '<tr><td colspan="5">保存済みサイトはありません。</td></tr>';
    }
    const policy = retentionData.policy || {};
    const mode = document.getElementById('retention-mode');
    if (mode) mode.value = policy.mode || 'unlimited';
    const generations = document.getElementById('retention-generations');
    if (generations && policy.generations != null) generations.value = policy.generations;
    const days = document.getElementById('retention-days');
    if (days && policy.days != null) days.value = policy.days;
    updateRetentionFields();
  } catch (error) {
    _adminMessage('retention-msg', error.message || 'データ管理情報を取得できませんでした。', true);
  }
}

async function saveRetentionPolicy() {
  const mode = document.getElementById('retention-mode')?.value || 'unlimited';
  const payload = { mode };
  if (mode === 'generations') payload.generations = Number(document.getElementById('retention-generations')?.value || 0);
  if (mode === 'days') payload.days = Number(document.getElementById('retention-days')?.value || 0);
  try {
    await _adminRequest('/api/admin/retention', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    _adminMessage('retention-msg', '保持設定を保存しました。');
    await loadDataManagement();
  } catch (error) {
    _adminMessage('retention-msg', error.message || '保持設定を保存できませんでした。', true);
  }
}

// ---- 管理操作の監査ログ ----
const _auditActionLabels = {
  'user.login': 'ログイン',
  'user.created': 'メンバー追加',
  'user.updated': 'メンバー変更',
  'schedule.settings_updated': 'スケジュール・通知設定',
  'settings.updated': 'システム設定',
  'notification.tested': '通知テスト',
  'retention.settings_updated': '保持設定',
  'retention.snapshots_pruned': '保持GC',
  'report.exported': 'レポート出力',
  'review.exported': 'レビュー出力',
  'viewpoint.exported': '観点出力',
};
let _auditNextOffset = null;
Object.assign(_auditActionLabels, {
  'decision.draft': '判断の起票',
  'decision.approve': '判断の承認',
  'decision.revoke': '判断の取消',
  'review.adopt': '採用',
  'review.reject': '却下',
  'review.hold': '保留',
  'policy.approval_updated': '承認規則の変更',
  'audit.exported': '監査ログの出力',
  'settings.key_cleared': 'APIキーの削除',
});
const _AUDIT_FIELD_LABELS = {
  forbid_self_approval: '職務分離', small_tenant_exception: '少人数の例外',
  small_tenant_max_members: '例外の人数上限', exception_reason: '例外の理由',
};
const _AUDIT_FILTER_IDS = { action: 'audit-action', outcome: 'audit-outcome', actor: 'audit-actor',
  since: 'audit-since', until: 'audit-until', case: 'audit-case', query: 'audit-query' };

function _auditParams() {
  const params = new URLSearchParams();
  Object.entries(_AUDIT_FILTER_IDS).forEach(([key, id]) => {
    const value = document.getElementById(id)?.value?.trim() || '';
    if (value) params.set(key, key === 'until' ? `${value}T23:59:59` : value);
  });
  return params;
}

function _auditDetailText(event) {
  const detail = { ...(event.detail || {}) };
  const parts = [];
  delete detail.reason; delete detail.case;
  if ('rev_before' in detail || 'rev_after' in detail) { parts.push(`版 ${detail.rev_before}→${detail.rev_after}`); delete detail.rev_before; delete detail.rev_after; }
  if (event.reason) parts.push(`理由: ${event.reason}`);
  if (Array.isArray(detail.changed_fields)) { parts.push(`変更: ${detail.changed_fields.map(f => _AUDIT_FIELD_LABELS[f] || f).join('・') || 'なし'}`); delete detail.changed_fields; }
  if (Object.keys(detail).length) parts.push(JSON.stringify(detail));
  return parts.join(' / ') || '—';
}

async function loadAdminAudit({append = false} = {}) {
  const body = document.getElementById('admin-audit-events');
  if (!body) return;
  const params = _auditParams();
  const filtered = [...params.keys()].length > 0;
  params.set('limit', '100');
  if (append && _auditNextOffset != null) params.set('offset', String(_auditNextOffset));
  if (!append) { body.dataset.state = 'loading'; body.innerHTML = '<tr><td colspan="7">読み込み中です。</td></tr>'; }
  const auditMsg = document.getElementById('audit-msg');
  if (auditMsg) { auditMsg.textContent = ''; auditMsg.className = 'settings-msg'; }
  try {
    const data = await _adminRequest(`/api/admin/audit?${params.toString()}`);
    const events = Array.isArray(data.events) ? data.events : [];
    const rows = events.map(event => {
      const target = [event.target_type, event.target_id].filter(Boolean).join(': ') || '—';
      const success = event.outcome === 'success';
      return `<tr>
        <td>${escHtml(event.at || '')}</td>
        <td>${escHtml(event.actor_email || event.actor_id || 'システム')}</td>
        <td>${escHtml(_auditActionLabels[event.action] || event.action || '')}</td>
        <td>${escHtml(event.case || '—')}</td>
        <td>${escHtml(target)}</td>
        <td><span class="audit-outcome ${success ? 'is-success' : 'is-failure'}">${success ? '成功' : '失敗'}</span></td>
        <td class="audit-detail">${escHtml(_auditDetailText(event))}</td>
      </tr>`;
    }).join('');
    if (append && rows) body.insertAdjacentHTML('beforeend', rows);
    else if (rows) { body.innerHTML = rows; body.dataset.state = 'normal'; }
    else if (filtered) {
      body.dataset.state = 'no-match';
      body.innerHTML = '<tr><td colspan="7">条件に一致する記録はありません。「条件を解除」で全件に戻せます。</td></tr>';
    } else {
      body.dataset.state = 'empty';
      body.innerHTML = '<tr><td colspan="7">まだ記録がありません。設定の変更や承認を行うとここに残ります。</td></tr>';
    }
    _auditNextOffset = data.has_more && Number.isInteger(data.next_offset) ? data.next_offset : null;
    const more = document.getElementById('audit-load-more');
    if (more) more.hidden = _auditNextOffset == null;
  } catch (error) {
    const forbidden = /403|権限/.test(error.message || '');
    body.dataset.state = forbidden ? 'forbidden' : 'error';
    body.innerHTML = `<tr><td colspan="7">${forbidden
      ? '監査ログを見るには管理者の役割が必要です。管理者に依頼してください。'
      : '監査ログを取得できませんでした。「再読み込み」を押してください。'}</td></tr>`;
    _adminMessage('audit-msg', error.message || '監査ログを取得できませんでした。', true);
  }
}

// ---- 承認規則（職務分離） ----
let _apSaved = null;

function _apForm() {
  return {
    forbid_self_approval: document.querySelector('input[name="ap-self"]:checked')?.value !== 'allow',
    small_tenant_exception: !!document.getElementById('ap-exception')?.checked,
    small_tenant_max_members: Number.parseInt(document.getElementById('ap-members')?.value || '', 10),
    exception_reason: (document.getElementById('ap-reason')?.value || '').trim(),
  };
}

function _apSetState(state, text) {
  const form = document.getElementById('approval-policy');
  if (!form) return;
  form.dataset.state = state;
  const label = document.getElementById('ap-state');
  if (label) label.textContent = text;
  const busy = state === 'loading' || state === 'saving';
  const dirty = state === 'dirty' || state === 'invalid';
  document.getElementById('ap-save').disabled = busy || !dirty || state === 'forbidden';
  document.getElementById('ap-cancel').disabled = busy || !dirty;
}

function _apFieldError(field, message) {
  ['ap-members-err', 'ap-reason-err'].forEach(id => { const el = document.getElementById(id); if (el) { el.hidden = true; el.textContent = ''; } });
  const id = field === 'small_tenant_max_members' ? 'ap-members-err' : field === 'exception_reason' ? 'ap-reason-err' : '';
  const el = id && document.getElementById(id);
  if (el && message) { el.hidden = false; el.textContent = message; }
}

function _apValidate(values) {
  if (!values.forbid_self_approval && values.small_tenant_exception) {
    return ['small_tenant_exception', '同一を許可している場合、少人数の例外は不要です。どちらかを選び直してください。'];
  }
  if (values.small_tenant_exception) {
    if (!Number.isInteger(values.small_tenant_max_members) || values.small_tenant_max_members < 1 || values.small_tenant_max_members > 5) {
      return ['small_tenant_max_members', '人数は 1〜5 人の整数で入力してください。'];
    }
    if (values.exception_reason.length < 10) {
      return ['exception_reason', '例外を有効にするには理由を 10 文字以上で入力してください。'];
    }
  }
  return null;
}

function _apRender(policy) {
  _apSaved = policy;
  document.querySelectorAll('input[name="ap-self"]').forEach(input => {
    input.checked = (input.value === 'forbid') === !!policy.forbid_self_approval;
  });
  document.getElementById('ap-exception').checked = !!policy.small_tenant_exception;
  document.getElementById('ap-members').value = String(policy.small_tenant_max_members || 2);
  document.getElementById('ap-reason').value = policy.exception_reason || '';
  document.getElementById('ap-exception-body').hidden = !policy.small_tenant_exception;
  document.getElementById('ap-exception-field').hidden = !policy.forbid_self_approval;
  document.getElementById('ap-conflict').hidden = true;
  _apFieldError('', '');
  const meta = document.getElementById('ap-meta');
  if (meta) meta.textContent = policy.updated_at
    ? `最終保存: ${policy.updated_at}（${policy.updated_by || '—'}）・版 ${policy.rev}`
    : '未保存の既定値です（起票者と承認者の同一を禁止）。';
}

function _apOnInput() {
  if (!_apSaved) return;
  const exceptionBox = document.getElementById('ap-exception');
  if (document.querySelector('input[name="ap-self"]:checked')?.value === 'allow' && exceptionBox) exceptionBox.checked = false;
  const values = _apForm();
  document.getElementById('ap-exception-body').hidden = !values.small_tenant_exception;
  document.getElementById('ap-exception-field').hidden = !values.forbid_self_approval;
  const changed = values.forbid_self_approval !== _apSaved.forbid_self_approval
    || values.small_tenant_exception !== _apSaved.small_tenant_exception
    || (values.small_tenant_exception && (values.small_tenant_max_members !== _apSaved.small_tenant_max_members
      || values.exception_reason !== (_apSaved.exception_reason || '')));
  const problem = changed ? _apValidate(values) : null;
  _apFieldError(problem?.[0] || '', problem?.[1] || '');
  if (!changed) _apSetState('normal', '保存済みの値です。');
  else if (problem) _apSetState('invalid', '入力を直すと保存できます。');
  else _apSetState('dirty', '未保存の変更があります。');
}

async function loadApprovalPolicy({restored = false} = {}) {
  if (!document.getElementById('approval-policy')) return;
  _apSetState('loading', '読み込み中です。');
  try {
    const data = await _adminRequest('/api/admin/approval-policy');
    _apRender(data.policy || {});
    _apSetState(restored ? 'restored' : 'normal', restored ? '最新の値を読み込みました。必要なら変更し直してください。' : '保存済みの値です。');
  } catch (error) {
    const forbidden = /403|権限/.test(error.message || '');
    _apSetState(forbidden ? 'forbidden' : 'error', forbidden
      ? '承認規則の確認と変更には管理者の役割が必要です。'
      : '承認規則を読み込めませんでした。タブを開き直してください。');
  }
}

async function saveApprovalPolicy(event) {
  event?.preventDefault();
  if (!_apSaved) return;
  const values = _apForm();
  const problem = _apValidate(values);
  if (problem) { _apFieldError(problem[0], problem[1]); _apSetState('invalid', '入力を直すと保存できます。'); return; }
  _apSetState('saving', '保存中です。');
  try {
    const response = await fetch('/api/admin/approval-policy', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...values, rev: _apSaved.rev }),
    });
    let data = {};
    try { data = await response.json(); } catch (_) { data = {}; }
    if (response.status === 409) {
      _apSetState('conflict', '保存できませんでした（競合）。入力は残っています。');
      const latest = data.policy || {};
      document.getElementById('ap-conflict-detail').textContent =
        `${latest.forbid_self_approval ? '同一を禁止' : '同一を許可'}・例外${latest.small_tenant_exception ? 'あり' : 'なし'}（${latest.updated_by || '—'}、${latest.updated_at || '—'}）`;
      document.getElementById('ap-conflict').hidden = false;
      return;
    }
    if (!response.ok) {
      _apFieldError(data.field || '', data.error || '');
      _apSetState('invalid', data.error || `保存できませんでした（${response.status}）。入力は残っています。`);
      if (response.status === 403) _apSetState('forbidden', '承認規則の変更には管理者の役割が必要です。');
      return;
    }
    _apRender(data.policy || {});
    _apSetState('normal', '保存しました。監査ログに記録しました。');
    loadAdminAudit();
  } catch (_) {
    _apSetState('error', '保存できませんでした。通信を確認してもう一度保存してください。入力は残っています。');
    document.getElementById('ap-save').disabled = false;
  }
}

document.getElementById('approval-policy')?.addEventListener('input', _apOnInput);
document.getElementById('approval-policy')?.addEventListener('change', _apOnInput);
document.getElementById('approval-policy')?.addEventListener('submit', saveApprovalPolicy);
document.getElementById('ap-cancel')?.addEventListener('click', () => { if (_apSaved) { _apRender(_apSaved); _apSetState('normal', '保存済みの値に戻しました。'); } });
document.getElementById('ap-reload')?.addEventListener('click', () => loadApprovalPolicy({restored: true}));
window.addEventListener('beforeunload', (event) => {
  const state = document.getElementById('approval-policy')?.dataset.state;
  if (state === 'dirty' || state === 'invalid' || state === 'conflict') { event.preventDefault(); event.returnValue = ''; }
});
document.getElementById('audit-clear')?.addEventListener('click', () => {
  Object.values(_AUDIT_FILTER_IDS).forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  loadAdminAudit();
});
document.getElementById('audit-export')?.addEventListener('click', () => {
  window.location.href = `/api/admin/audit.csv?${_auditParams().toString()}`;
});

document.getElementById('audit-refresh')?.addEventListener('click', () => loadAdminAudit());
document.getElementById('audit-search')?.addEventListener('click', () => loadAdminAudit());
document.getElementById('audit-load-more')?.addEventListener('click', () => loadAdminAudit({append: true}));
document.getElementById('audit-query')?.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') loadAdminAudit();
});

// 初期ロード
loadSettingsForm();
// settings ビューに遷移した時にサーバー設定を読む
document.querySelector('.app-nav-item[data-view="settings"]')?.addEventListener('click', () => {
  setTimeout(loadServerSettings, 50);
  setTimeout(loadTestDesignSettings, 50);
});
