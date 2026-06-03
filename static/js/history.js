// ---- 履歴 ----
async function loadHistory() {
  const body = document.getElementById('history-body');
  body.innerHTML = '<div class="empty">読み込み中...</div>';
  try {
    const res = await fetch('/api/history');
    const data = await res.json();
    if (!data.items.length) {
      body.innerHTML = _emptyState();
      body.querySelector('.empty-add-btn')?.addEventListener('click', openAddSite);
      return;
    }
    body.innerHTML = _buildTable(data.items);
    body.querySelectorAll('.hist-open').forEach(b => b.addEventListener('click', () => openResultsForDomain(b.dataset.domain)));
    body.querySelectorAll('.hist-recrawl').forEach(b => b.addEventListener('click', () => recrawlSite(b.dataset.domain)));
    body.querySelectorAll('.hist-delete').forEach(b => b.addEventListener('click', () => deleteSite(b.dataset.domain)));
  } catch (e) {
    body.innerHTML = '<div class="empty">サイト一覧の読み込みに失敗しました。</div>';
  }
}
document.getElementById('reload-history').addEventListener('click', loadHistory);

function _emptyState() {
  return `
    <div class="dashboard-empty">
      <div class="dashboard-empty-icon">🔍</div>
      <div class="dashboard-empty-title">まだサイトが登録されていません</div>
      <div class="dashboard-empty-desc">
        クロール対象の URL を登録すると、画面一覧・入力項目・テスト条件を自動生成します。<br>
        再クロールするたびに前回との差分（仕様ドリフト）を検知します。
      </div>
      <button type="button" class="btn-primary empty-add-btn" style="height:44px;padding:0 28px;font-size:15px;margin-top:8px">
        + 最初のサイトを追加する
      </button>
    </div>`;
}

function _freshnessLabel(updatedTs) {
  const now = Date.now() / 1000;
  const diff = now - updatedTs;
  const days = Math.floor(diff / 86400);
  if (days === 0) return { label: '今日', cls: 'fresh-today' };
  if (days <= 7)  return { label: `${days}日前`, cls: 'fresh-week' };
  if (days <= 30) return { label: `${days}日前`, cls: 'fresh-month' };
  return { label: `${days}日前`, cls: 'fresh-old' };
}

function _buildTable(items) {
  let html = `
    <table class="data dashboard-table">
      <thead>
        <tr>
          <th>サイト</th>
          <th class="num">画面</th>
          <th class="num">項目</th>
          <th>クロール履歴</th>
          <th>最終クロール</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>`;

  for (const it of items) {
    const fresh = _freshnessLabel(it.updated_ts || 0);
    const snapBadge = it.snapshot_count >= 2
      ? `<span class="snap-badge">${it.snapshot_count}回</span>`
      : it.snapshot_count === 1
        ? `<span class="snap-badge snap-badge-first">初回</span>`
        : '';
    const diffBadge = it.has_diff
      ? `<span class="diff-badge">差分あり</span>`
      : '';

    html += `
      <tr>
        <td>
          <div class="site-cell">
            <strong>${escHtml(it.domain)}</strong>
            ${diffBadge}
          </div>
        </td>
        <td class="num">${it.screens}</td>
        <td class="num">${it.fields}</td>
        <td>${snapBadge}</td>
        <td><span class="freshness ${fresh.cls}">${fresh.label}</span></td>
        <td>
          <div class="history-actions">
            <button type="button" class="btn-outline-sm hist-delete" data-domain="${escHtml(it.domain)}">削除</button>
            <button type="button" class="btn-outline-sm hist-recrawl" data-domain="${escHtml(it.domain)}">再クロール</button>
            <button type="button" class="btn-primary hist-open" data-domain="${escHtml(it.domain)}" style="height:36px;padding:0 14px;font-size:13px">開く</button>
          </div>
        </td>
      </tr>`;
  }
  html += '</tbody></table>';
  return html;
}

async function deleteSite(domain) {
  if (!confirm(`「${domain}」のクロール結果をすべて削除しますか？\nこの操作は取り消せません。`)) return;
  const res = await fetch('/api/site/' + encodeURIComponent(domain), { method: 'DELETE' });
  let data = {};
  try { data = await res.json(); } catch (e) { data = {}; }
  if (res.ok) { loadHistory(); return; }
  alert('削除に失敗しました: ' + (data.error || res.status));
}
