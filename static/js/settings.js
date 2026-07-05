// ---- 設定タブ切替（APIキー・モデル/クロール既定値/通知）----
// 従来 .set-tab ボタンに click ハンドラが未実装で「タブ操作ができない」不具合があったため追加。
function selectSettingsTab(tab) {
  const tabs = [...document.querySelectorAll('.set-tabs .set-tab')];
  if (!tabs.some(t => t.dataset.tab === tab)) return;
  tabs.forEach(t => {
    const on = t.dataset.tab === tab;
    t.classList.toggle('is-active', on);
    t.setAttribute('aria-selected', on ? 'true' : 'false');
    t.tabIndex = on ? 0 : -1;
  });
  document.querySelectorAll('.set-panel').forEach(p => {
    p.classList.toggle('is-active', p.id === 'set-panel-' + tab);
  });
}
document.querySelectorAll('.set-tabs .set-tab').forEach(t => {
  t.addEventListener('click', () => selectSettingsTab(t.dataset.tab));
  t.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const tabs = [...document.querySelectorAll('.set-tabs .set-tab')];
    const i = tabs.indexOf(t);
    const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    if (next) { selectSettingsTab(next.dataset.tab); next.focus(); }
  });
});

// ---- 設定（localStorage）----
function getSettings() { try { return JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {}; } catch { return {}; } }
function applySettings() {
  const s = getSettings();
  // crawl-depth / max-pages はウィザードの自動クロールモードでのみ使う値のため
  // ここでは上書きしない（既定値のまま）。
  if (s.auth) document.getElementById('auth-path').value = s.auth;
}
function loadSettingsForm() {
  const s = getSettings();
  document.getElementById('set-depth').value = s.depth || 2;
  document.getElementById('set-max').value = s.maxPages || 30;
  document.getElementById('set-auth').value = s.auth || '';
  const caseEl = document.getElementById('set-case-minutes');
  if (caseEl) caseEl.value = s.caseMinutes || 10;
  const urlHistEl = document.getElementById('set-url-history-limit');
  if (urlHistEl) urlHistEl.value = String(s.urlHistoryLimit ?? 10);
}
document.getElementById('save-settings').addEventListener('click', () => {
  const caseEl = document.getElementById('set-case-minutes');
  const urlHistEl = document.getElementById('set-url-history-limit');
  const urlHistoryLimit = urlHistEl ? (Number(urlHistEl.value) || 0) : 10;
  localStorage.setItem(SETTINGS_KEY, JSON.stringify({
    depth: document.getElementById('set-depth').value,
    maxPages: document.getElementById('set-max').value,
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
    await loadAllowLocalToggle();
  } catch (e) { /* 設定読み込み失敗は無視 */ }
}

async function saveApiKey() {
  const key = document.getElementById('api-key')?.value?.trim() || '';
  const org = document.getElementById('api-org')?.value?.trim() || '';
  const proj = document.getElementById('api-project')?.value?.trim() || '';
  const model = document.getElementById('api-model')?.value || '';
  const form = new FormData();
  if (key) form.append('api_key', key);
  if (org) form.append('org_id', org);
  if (proj) form.append('project_id', proj);
  form.append('model', model);
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

document.getElementById('save-api')?.addEventListener('click', saveApiKey);
document.getElementById('test-connection')?.addEventListener('click', testConnection);
document.getElementById('save-slack')?.addEventListener('click', saveSlackWebhook);
document.getElementById('allow-local-toggle')?.addEventListener('change', saveAllowLocal);
document.getElementById('save-test-design')?.addEventListener('click', saveTestDesignSettings);

// 初期ロード
loadSettingsForm();
// settings ビューに遷移した時にサーバー設定を読む
document.querySelector('.app-nav-item[data-view="settings"]')?.addEventListener('click', () => {
  setTimeout(loadServerSettings, 50);
  setTimeout(loadTestDesignSettings, 50);
});
