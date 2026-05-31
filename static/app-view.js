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
    resultHero.innerHTML = '<div class="hero-pad">' +
      '<p style="color:var(--text-muted);font-size:13px;margin-bottom:12px">このサイトは旧バージョンで生成されたため画面別の構造化データがありません。「<strong>再クロール</strong>」で最新のテスト条件マトリクスを生成できます。詳細は「画面別仕様」タブを参照してください。</p>' +
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
  resultHero.innerHTML = '<div class="hero-pad">' +
    `<p style="color:var(--text-muted);font-size:13px;margin-bottom:12px">対象 ${escHtml(meta.target_url || '')} ／ クロール: 深さ${meta.crawl_depth ?? '-'} ・最大${meta.max_pages ?? '-'}ページ ／ ${escHtml(meta.crawled_at || '')}</p>` +
    '<div class="hero-section-title">画面インベントリ</div>' +
    '<table class="ov-screens"><thead><tr><th>画面ID</th><th>タイトル</th><th>URL</th><th>フォーム</th><th>入力項目</th><th>遷移先</th></tr></thead><tbody>' +
    (rows || '<tr><td colspan="6" style="color:var(--text-muted)">画面がありません</td></tr>') + '</tbody></table>' +
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

// ---- スクリーンショット一覧 ----
function renderShots() {
  if (!reportJson) {
    resultHero.innerHTML = '<div class="hero-msg">スクリーンショットの対応情報がありません。</div>';
    return;
  }
  const pageIds = new Set((reportJson.screens || []).map(s => s.page_id));
  const shots = (resultData.screenshots || []).filter(p => pageIds.has(p.split('/').pop().replace(/\.png$/, '')));
  if (!shots.length) {
    resultHero.innerHTML = '<div class="hero-msg">スクリーンショットがありません。</div>';
    return;
  }
  const items = shots.map(p => {
    const name = p.split('/').pop();
    const src = `/preview?path=${encodeURIComponent(p)}`;
    return `<figure class="shots-item"><img src="${escHtml(src)}" loading="lazy" alt="${escHtml(name)}" class="shots-thumb" onclick="openLightbox('${escHtml(src)}')" /><figcaption>${escHtml(name)}</figcaption></figure>`;
  }).join('');
  resultHero.innerHTML = '<div class="shots-grid">' + items + '</div>';
}

// ---- ライトボックス ----
function openLightbox(src) {
  const lb = document.getElementById('lightbox');
  const img = document.getElementById('lightbox-img');
  if (!lb || !img) return;
  img.src = src;
  lb.style.display = 'flex';
  document.addEventListener('keydown', closeLightboxOnEsc);
}
function closeLightbox() {
  const lb = document.getElementById('lightbox');
  if (lb) lb.style.display = 'none';
  document.removeEventListener('keydown', closeLightboxOnEsc);
}
function closeLightboxOnEsc(e) { if (e.key === 'Escape') closeLightbox(); }
(function initLightbox() {
  const lb = document.getElementById('lightbox');
  if (!lb) return;
  lb.addEventListener('click', (e) => { if (e.target === lb) closeLightbox(); });
  document.getElementById('lightbox-close').addEventListener('click', closeLightbox);
})();

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
