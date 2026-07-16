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
  t.addEventListener('click', () => {
    selectSettingsTab(t.dataset.tab);
    if (t.dataset.tab === 'operations') loadOperationalSites();
  });
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

document.getElementById('save-api')?.addEventListener('click', saveApiKey);
document.getElementById('test-connection')?.addEventListener('click', testConnection);
document.getElementById('save-slack')?.addEventListener('click', saveSlackWebhook);
document.getElementById('allow-local-toggle')?.addEventListener('change', saveAllowLocal);
document.getElementById('save-test-design')?.addEventListener('click', saveTestDesignSettings);
document.getElementById('ops-site')?.addEventListener('change', (e) => loadOperationalConfig(e.target.value));
document.getElementById('ops-save')?.addEventListener('click', saveOperationalConfig);
document.getElementById('ops-test-notify')?.addEventListener('click', testOperationalNotification);

// 初期ロード
loadSettingsForm();
// settings ビューに遷移した時にサーバー設定を読む
document.querySelector('.app-nav-item[data-view="settings"]')?.addEventListener('click', () => {
  setTimeout(loadServerSettings, 50);
  setTimeout(loadTestDesignSettings, 50);
});
