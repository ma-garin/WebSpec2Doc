// ---- 解析履歴 ----
async function loadHistory() {
  const body = document.getElementById('history-body');
  if (!body) return;
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
    body.querySelectorAll('.hist-recrawl').forEach(b => b.addEventListener('click', async () => {
      b.disabled = true;
      const orig = b.textContent;
      b.textContent = '読み込み中…';
      try { await recrawlSite(b.dataset.domain); } finally { b.disabled = false; b.textContent = orig; }
    }));
    body.querySelectorAll('.hist-delete').forEach(b => b.addEventListener('click', () => deleteSite(b.dataset.domain, b)));
  } catch (e) {
    body.innerHTML = '<div class="empty">解析履歴の読み込みに失敗しました。</div>';
  }
}
document.getElementById('reload-history')?.addEventListener('click', loadHistory);

function _emptyState() {
  return `
    <div class="dashboard-empty">
      <div class="dashboard-empty-icon">🔍</div>
      <div class="dashboard-empty-title">まだ解析履歴がありません</div>
      <div class="dashboard-empty-desc">
        対象システムのURLを登録すると、画面仕様書・テスト設計・画面遷移図を自動生成します。
      </div>
      <div class="onboard-steps">
        <div class="onboard-step"><span class="onboard-num">1</span><strong>URLを入力</strong><span>対象システムのURLを貼り付けて解析</span></div>
        <div class="onboard-arrow">→</div>
        <div class="onboard-step"><span class="onboard-num">2</span><strong>画面を選択</strong><span>検出された画面から生成対象を選択</span></div>
        <div class="onboard-arrow">→</div>
        <div class="onboard-step"><span class="onboard-num">3</span><strong>ドキュメントを確認</strong><span>生成された仕様書とテスト設計を確認</span></div>
      </div>
      <button type="button" class="btn-primary empty-add-btn" style="height:44px;padding:0 28px;font-size:15px;margin-top:8px">
        最初の解析を始める
      </button>
      <p style="font-size:12px;color:var(--text-muted);margin-top:4px">所要時間の目安: 10画面のサイトで約2〜3分</p>
    </div>`;
}

function _freshnessLabel(updatedTs) {
  const now = Date.now() / 1000;
  const diff = now - updatedTs;
  const days = Math.floor(diff / 86400);
  if (days === 0) return { label: '今日', cls: 'fresh-today' };
  if (days <= 7) return { label: `${days}日前`, cls: 'fresh-week' };
  if (days <= 30) return { label: `${days}日前`, cls: 'fresh-month' };
  return { label: `${days}日前`, cls: 'fresh-old' };
}

function _buildStats(items) {
  // 履歴データ（既取得）から KPI を導出する。空配列は呼び出し側で除外済み。
  const sites = items.length;
  const screens = items.reduce((s, it) => s + (it.screens || 0), 0);
  const fields = items.reduce((s, it) => s + (it.fields || 0), 0);
  const drift = items.reduce((s, it) => s + (it.has_diff ? 1 : 0), 0);
  const icon = (p) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
  const driftClass = drift > 0 ? 'is-warn' : 'is-ok';
  const driftSub = drift > 0 ? '要確認' : '変化なし';
  return `
    <div class="stat-cards" aria-label="解析サマリ">
      <div class="stat-card">
        <div class="stat-card-head"><span class="stat-card-icon">${icon('<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/>')}</span><span class="stat-card-label">解析サイト</span></div>
        <div class="stat-card-num">${sites}</div><div class="stat-card-sub">登録済みのサイト数</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-head"><span class="stat-card-icon">${icon('<rect x="2" y="4" width="20" height="14" rx="2"/><path d="M8 21h8M12 18v3"/>')}</span><span class="stat-card-label">総画面数</span></div>
        <div class="stat-card-num">${screens}</div><div class="stat-card-sub">解析済みの画面の合計</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-head"><span class="stat-card-icon">${icon('<path d="M4 6h16M4 12h16M4 18h10"/>')}</span><span class="stat-card-label">総項目数</span></div>
        <div class="stat-card-num">${fields}</div><div class="stat-card-sub">抽出された入力項目の合計</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-head"><span class="stat-card-icon ${driftClass}">${icon('<path d="M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>')}</span><span class="stat-card-label">差分あり</span></div>
        <div class="stat-card-num">${drift}</div><div class="stat-card-sub">${driftSub}</div>
      </div>
    </div>`;
}

function _buildTable(items) {
  let html = _buildStats(items) + `
    <table class="data dashboard-table">
      <thead><tr><th>サイト</th><th class="num">画面</th><th class="num">項目</th><th>解析回数</th><th>最終解析</th><th>操作</th></tr></thead>
      <tbody>`;

  for (const it of items) {
    const fresh = _freshnessLabel(it.updated_ts || 0);
    const snapBadge = it.snapshot_count >= 2
      ? `<span class="snap-badge">${it.snapshot_count}回</span>`
      : it.snapshot_count === 1 ? '<span class="snap-badge snap-badge-first">初回</span>' : '';
    const diffBadge = it.has_diff ? '<span class="diff-badge">差分あり</span>' : '';
    html += `
      <tr class="${it.has_diff ? 'has-drift' : ''}">
        <td><div class="site-cell"><strong>${escHtml(it.domain)}</strong>${diffBadge}</div></td>
        <td class="num">${it.screens}</td>
        <td class="num">${it.fields}</td>
        <td>${snapBadge}</td>
        <td><span class="freshness ${fresh.cls}">${fresh.label}</span></td>
        <td><div class="history-actions">
          <button type="button" class="btn-primary hist-open" data-domain="${escHtml(it.domain)}" style="height:36px;padding:0 14px;font-size:13px">開く</button>
          <button type="button" class="btn-outline-sm hist-recrawl" data-domain="${escHtml(it.domain)}">再クロール</button>
          <button type="button" class="btn-outline-sm hist-delete" data-domain="${escHtml(it.domain)}">削除</button>
        </div></td>
      </tr>`;
  }
  return html + '</tbody></table>';
}

async function deleteSite(domain, btn) {
  const ok = await confirmDialog({
    title: '解析結果の削除',
    message: `「${domain}」の画面一覧・スナップショット・スクリーンショットをすべて削除します。この操作は取り消せません。`,
    confirmLabel: '削除する', danger: true,
  });
  if (!ok) return;
  if (btn) { btn.disabled = true; btn.textContent = '削除中…'; }
  try {
    const res = await fetch('/api/site/' + encodeURIComponent(domain), { method: 'DELETE' });
    let data = {};
    try { data = await res.json(); } catch (e) { data = {}; }
    if (res.ok) {
      showToast(`「${domain}」を削除しました`, 'success');
      loadHistory();
      return;
    }
    showToast('削除に失敗しました: ' + (data.error || res.status), 'error');
  } catch (e) {
    showToast('削除に失敗しました: 通信エラー', 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '削除'; }
  }
}
