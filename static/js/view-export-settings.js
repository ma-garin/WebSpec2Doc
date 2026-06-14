
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

function ensureSpecTsExportItem() {
  const menu = document.getElementById('export-dropdown-menu');
  if (!menu || menu.querySelector('.spec-ts-export-item')) return;
  const row = document.createElement('div');
  row.className = 'export-dropdown-item spec-ts-export-item';
  const label = document.createElement('span');
  label.textContent = 'Playwright .spec.ts';
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'btn-outline-sm';
  button.style.cssText = 'height:28px;padding:0 8px;font-size:12px';
  button.textContent = 'DL';
  button.addEventListener('click', async () => {
    const domain = resultData_domain();
    if (!domain) return;
    try {
      const response = await fetch(`/api/report/${encodeURIComponent(domain)}/spec-ts?filter=all`);
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || 'Playwright候補が見つかりません');
      }
      const url = URL.createObjectURL(await response.blob());
      const anchor = Object.assign(document.createElement('a'), {
        href: url,
        download: `${domain}.spec.ts`,
      });
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      showToast(error.message || 'spec.ts の生成に失敗しました', 'error');
    }
  });
  row.append(label, button);
  menu.appendChild(row);
}

document.getElementById('export-dropdown-btn')?.addEventListener('click', ensureSpecTsExportItem);

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
