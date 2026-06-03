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

