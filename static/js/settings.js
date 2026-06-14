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
  const caseEl = document.getElementById('set-case-minutes');
  if (caseEl) caseEl.value = s.caseMinutes || 10;
}
document.getElementById('save-settings').addEventListener('click', () => {
  const caseEl = document.getElementById('set-case-minutes');
  localStorage.setItem(SETTINGS_KEY, JSON.stringify({
    depth: document.getElementById('set-depth').value,
    maxPages: document.getElementById('set-max').value,
    auth: document.getElementById('set-auth').value.trim(),
    caseMinutes: caseEl ? (Number(caseEl.value) || 10) : 10,
  }));
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
    await loadAllowLocalToggle();
  } catch (e) { /* 設定読み込み失敗は無視 */ }
}

async function saveApiKey() {
  const key = document.getElementById('api-key')?.value?.trim() || '';
  const org = document.getElementById('api-org')?.value?.trim() || '';
  const proj = document.getElementById('api-project')?.value?.trim() || '';
  const form = new FormData();
  if (key) form.append('api_key', key);
  if (org) form.append('org_id', org);
  if (proj) form.append('project_id', proj);
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

async function saveModel() {
  const model = document.getElementById('api-model')?.value || '';
  const form = new FormData();
  form.append('model', model);
  try {
    await fetch('/api/settings', { method: 'POST', body: form });
    const msg = document.getElementById('model-msg'); msg.classList.add('show');
    setTimeout(() => msg.classList.remove('show'), 2500);
  } catch (e) { showToast('モデル設定の保存に失敗しました', 'error'); }
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

document.getElementById('save-api')?.addEventListener('click', saveApiKey);
document.getElementById('save-model')?.addEventListener('click', saveModel);
document.getElementById('save-slack')?.addEventListener('click', saveSlackWebhook);
document.getElementById('allow-local-toggle')?.addEventListener('change', saveAllowLocal);

// 初期ロード
loadSettingsForm();
// settings ビューに遷移した時にサーバー設定を読む
document.querySelector('.app-nav-item[data-view="settings"]')?.addEventListener('click', () => {
  setTimeout(loadServerSettings, 50);
});
