// ---- 履歴 ----
async function loadHistory() {
  const body = document.getElementById('history-body');
  body.innerHTML = '<div class="empty">読み込み中...</div>';
  try {
    const res = await fetch('/api/history');
    const data = await res.json();
    if (!data.items.length) { body.innerHTML = '<div class="empty">まだ監視対象がありません。「+ サイトを追加」から最初のサイトをクロールしてください。</div>'; return; }
    let html = '<table class="data"><thead><tr><th>サイト</th><th class="num">画面数</th><th class="num">入力項目</th><th>形式</th><th>最終クロール</th><th>操作</th></tr></thead><tbody>';
    for (const it of data.items) {
      const badges = (it.formats || []).map(f => `<span class="fmt-badge">${escHtml(f)}</span>`).join('');
      html += `<tr><td><strong>${escHtml(it.domain)}</strong></td><td class="num">${it.screens}</td><td class="num">${it.fields}</td>` +
        `<td><div class="fmt-badges">${badges || '—'}</div></td><td>${escHtml(it.updated)}</td>` +
        `<td><div class="history-actions">` +
        `<button type="button" class="btn-outline-sm hist-recrawl" data-domain="${escHtml(it.domain)}">再クロール</button>` +
        `<button type="button" class="btn-primary hist-open" data-domain="${escHtml(it.domain)}" style="height:36px;padding:0 14px;font-size:13px">開く</button>` +
        `</div></td></tr>`;
    }
    html += '</tbody></table>';
    body.innerHTML = html;
    body.querySelectorAll('.hist-open').forEach(b => b.addEventListener('click', () => openResultsForDomain(b.dataset.domain)));
    body.querySelectorAll('.hist-recrawl').forEach(b => b.addEventListener('click', () => recrawlSite(b.dataset.domain)));
  } catch (e) { body.innerHTML = '<div class="empty">サイト一覧の読み込みに失敗しました。</div>'; }
}
document.getElementById('reload-history').addEventListener('click', loadHistory);

