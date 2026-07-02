// ---- 概要 ----

// 画面のリスクスコア: 必須項目×2 + 入力項目 + 遷移先数（テスト工数・障害インパクトの近似）
function _screenRiskScore(sc) {
  const fields = (sc.forms || []).flatMap(fm => fm.fields || []);
  const required = fields.filter(f => f.required).length;
  const to = (sc.transitions && sc.transitions.to || []).length;
  return required * 2 + fields.length + to;
}

function _execSummary(allScreens) {
  // クエリ重複（reserve.html?plan-id=N 等）を統合した正規化済み画面のみで集計する。
  // メトリクスの水増しを防ぐため、画面数・項目数・ケース数・工数はすべて canonical 基準。
  const screens = canonicalScreens(reportJson);
  const pageCount = (allScreens || []).length;
  const screenCount = screens.length;
  const totalFields = screens.reduce((n, sc) => n + (sc.forms || []).reduce((m, fm) => m + (fm.fields || []).length, 0), 0);
  const totalRequired = screens.reduce((n, sc) => n + (sc.forms || []).reduce((m, fm) => m + (fm.fields || []).filter(f => f.required).length, 0), 0);
  const formScreens = screens.filter(sc => (sc.forms || []).some(fm => (fm.fields || []).length)).length;
  // テスト規模の概算は KPI ヒーローと同じ計算式（view-utils.js estimateTestEffort）を使う
  const { cases: estCases, hours: estHours, caseMinutes } = estimateTestEffort(reportJson);
  const top3 = [...screens].sort((a, b) => _screenRiskScore(b) - _screenRiskScore(a)).slice(0, 3)
    .filter(sc => _screenRiskScore(sc) > 0);

  const top3Html = top3.map((sc, i) =>
    `<li><strong>${escHtml(sc.page_id)}</strong> ${escHtml(sc.title || '')}<span style="color:var(--text-muted)">（リスクスコア ${_screenRiskScore(sc)}：必須項目と遷移が多く、障害時の影響が大きい画面）</span></li>`
  ).join('');

  // 到達ページ数 > 画面数 のとき、クエリ重複を統合した旨を明示（数値の信頼性）。
  const dedupNote = pageCount > screenCount
    ? `<span style="color:var(--text-muted)">（${pageCount}ページ検出 → クエリ重複を統合）</span>`
    : '';

  // 信頼性バッジ: メトリクスが重複統合済み・機械導出であることを明示（検証会社の監査用）。
  const trustBreakdown = pageCount > screenCount
    ? `${pageCount}ページ検出 → ${screenCount}画面（クエリ重複を統合）／入力項目は canonical 画面のみ集計／テスト条件は機械導出`
    : `${screenCount}画面・${totalFields}項目を機械導出／クエリ重複は統合済み`;
  const trustBadge = `<span class="trust-badge" title="${escHtml(trustBreakdown)}">✓ 重複統合済み・機械導出（監査可能）</span>`;

  return `
    <div class="exec-summary">
      <div class="hero-section-title">エグゼクティブサマリー ${trustBadge}</div>
      <p style="font-size:13px;line-height:1.7;margin:0 0 10px">
        本システムは <strong>${screenCount}画面</strong>${dedupNote}（うち入力フォームあり ${formScreens}画面）で構成され、
        入力項目は <strong>${totalFields}項目</strong>（必須 ${totalRequired}項目）です。
        機械導出したテスト条件から、概算 <strong>${estCases}テストケース / 約${estHours}時間</strong>のテスト規模と推定されます
        <span style="color:var(--text-muted)">（1ケース${caseMinutes}分換算・設定で変更可／概算＝入力項目×3＋遷移×2）</span>。
      </p>
      ${top3.length ? `<div style="font-size:12.5px;font-weight:700;color:var(--text);margin-bottom:4px">優先テスト対象（リスク上位3画面）</div><ol style="margin:0 0 4px 20px;font-size:12.5px;line-height:1.8">${top3Html}</ol>` : ''}
    </div>`;
}

function renderOverview() {
  if (!reportJson) {
    resultHero.innerHTML = '<div class="hero-pad">' +
      '<p style="color:var(--text-muted);font-size:13px;margin-bottom:12px">このサイトは旧バージョンで生成されたため画面別の構造化データがありません。「<strong>再クロール</strong>」で最新のテスト条件マトリクスを生成できます。詳細は「画面別仕様」タブを参照してください。</p>' +
      '</div>';
    return;
  }
  const screens = reportJson.screens || [];
  const meta = reportJson.meta || {};
  // 到達URLは全件表示（第三者検証の網羅性証跡）。クエリ重複は淡色＋バリエーション注釈。
  const screenCount = canonicalScreens(reportJson).length;
  const rows = screens.map(sc => {
    const isCanon = sc.is_canonical !== false;
    const fields = (sc.forms || []).reduce((n, fm) => n + (fm.fields || []).length, 0);
    const to = (sc.transitions && sc.transitions.to || []).join(', ') || '—';
    const rowAttr = isCanon ? '' : ' style="opacity:.5" title="' + escHtml((sc.canonical_key || '') + ' と同一構造（クエリ違い）') + '"';
    const titleCell = isCanon
      ? escHtml(sc.title || '')
      : `<span style="color:var(--text-muted)">↳ ${escHtml(sc.canonical_key || '')} のバリエーション</span>`;
    return `<tr${rowAttr}><td class="c-screen">${escHtml(sc.page_id)}</td><td>${titleCell}</td>` +
      `<td><code style="font-size:.78rem;color:var(--text-muted)">${escHtml(sc.url || '')}</code></td>` +
      `<td class="num">${(sc.forms || []).length}</td><td class="num">${fields}</td><td>${escHtml(to)}</td></tr>`;
  }).join('');
  const invNote = screens.length > screenCount
    ? `<span style="font-weight:400;color:var(--text-muted);font-size:12px">（${screens.length}ページ検出・${screenCount}画面／重複は淡色）</span>`
    : '';
  resultHero.innerHTML = '<div class="hero-pad">' +
    `<p style="color:var(--text-muted);font-size:13px;margin-bottom:12px">対象 ${escHtml(meta.target_url || '')} ／ クロール: 深さ${meta.crawl_depth ?? '-'} ・最大${meta.max_pages ?? '-'}ページ ／ ${escHtml(meta.crawled_at || '')}</p>` +
    _execSummary(screens) +
    `<div class="next-steps-cta">
      <span class="next-steps-label">次のステップ</span>
      <button type="button" class="next-step-btn" onclick="selectResultTab('test-design','matrix')">テスト条件を確認する →</button>
      <button type="button" class="next-step-btn" onclick="selectResultTab('test-design','summary')">技法マトリクスを見る →</button>
      <button type="button" class="next-step-btn next-step-btn--secondary" onclick="selectResultTab('history')">差分・履歴を確認する →</button>
    </div>` +
    '<div class="hero-section-title">画面インベントリ ' + invNote + '</div>' +
    '<table class="ov-screens"><thead><tr><th>画面ID</th><th>タイトル</th><th>URL</th><th>フォーム</th><th>入力項目</th><th>遷移先</th></tr></thead><tbody>' +
    (rows || '<tr><td colspan="6" style="color:var(--text-muted)">画面がありません</td></tr>') + '</tbody></table>' +
    '</div>';
}

// ---- 入力項目・テスト条件マトリクス ----
function renderMatrix() {
  if (!reportJson) { resultHero.innerHTML = '<div class="hero-msg">マトリクスデータ（report.json）を読み込めませんでした。</div>'; return; }
  // テスト設計対象は正規化済み画面のみ（クエリ重複は同一条件なので除外）。
  const screens = canonicalScreens(reportJson).map(s => s.page_id);
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

