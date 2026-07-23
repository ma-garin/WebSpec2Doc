// ---- 文書突合タブ（Doc Fusion — ギャップ3分類の表示） ----
// データソースは results.js が showResults 内で /api/doc-fusion から取得し、
// グローバル docFusionData にキャッシュ済み（存在時のみタブが表示される）。

async function renderDocFusion() {
  const host = resultHero;

  if (!docFusionData) {
    uiEmpty(host, {
      icon: '📄',
      title: '参考文書が指定されていません',
      desc: '条件設定で参考文書（画面一覧・項目定義書など）をアップロードしてから解析してください。',
    });
    return;
  }

  const meta = docFusionData.meta || {};
  const cards = [
    { label: '画面の対応づけ', val: meta.matched_screens || 0 },
    { label: '文書のみ（未実装/廃止疑い）', val: meta.doc_only_screens || 0 },
    { label: '実測のみ（文書化漏れ）', val: meta.crawl_only_screens || 0 },
    { label: '項目レベルのギャップ', val: meta.field_gaps || 0 },
  ].map(c =>
    `<div class="stat-card runs-stat-card"><div class="num">${escHtml(String(c.val))}</div><div class="lbl">${escHtml(c.label)}</div></div>`
  ).join('');

  const kindLabels = { doc_only: '文書のみ', crawl_only: '実測のみ', mismatch: '矛盾' };
  const gaps = docFusionData.field_gaps || [];
  const gapRows = gaps.map(g => {
    const ev = g.doc_evidence || {};
    const location = [ev.file, ev.location].filter(Boolean).join(' ');
    return `<tr>
      <td><span class="runs-status-badge ${g.kind === 'mismatch' ? 'status-critical' : 'status-default'}">${escHtml(kindLabels[g.kind] || g.kind || '')}</span></td>
      <td>${escHtml(g.page_id || '')}</td>
      <td>${escHtml(g.field_name || '')}</td>
      <td>${escHtml(g.detail || '')}</td>
      <td>${escHtml(location)}</td>
      <td>${escHtml(g.crawl_selector || '')}</td>
    </tr>`;
  }).join('');
  const gapSection = gaps.length
    ? '<div class="hero-section-title" style="margin-top:1.5rem">項目レベルのギャップ</div>' +
      '<table class="ov-screens runs-table"><thead><tr><th>分類</th><th>画面</th><th>項目</th><th>内容</th>' +
      '<th>文書の出所</th><th>実測セレクタ</th></tr></thead>' +
      `<tbody>${gapRows}</tbody></table>`
    : '<div class="muted" style="margin-top:1rem">項目レベルのギャップはありません。</div>';

  const rules = docFusionData.documented_rules || [];
  const rulesSection = rules.length
    ? `<div class="hero-section-title" style="margin-top:1.5rem">文書由来の業務ルール（${rules.length}件・詳細は doc_fusion.md 参照）</div>`
    : '';

  host.innerHTML =
    '<div class="hero-pad">' +
    '<div class="hero-section-title">文書×実測 突合</div>' +
    `<div class="runs-summary-row"><div class="runs-stat-grid">${cards}</div></div>` +
    gapSection +
    rulesSection +
    '</div>';
}
