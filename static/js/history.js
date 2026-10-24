// ---- 解析履歴 ----
async function loadHistory() {
  const body = document.getElementById('history-body');
  if (!body) return;
  body.innerHTML = '<section class="ui-state" data-kind="loading" role="status"><h2 class="ui-state__title">読み込み中…</h2></section>';
  try {
    const res = await fetch('/api/history');
    if (res.status === 403) {
      UIStates.set(body, 'forbidden', {
        title: 'この一覧を見る権限がありません',
        msg: '権限のあるアカウントで入り直すか、管理者に依頼してください。',
        cta: { label: 'システム選択へ戻る', href: '/systems' },
      });
      return;
    }
    if (!res.ok) throw new Error('history ' + res.status);
    const data = await res.json();
    if (!data.items.length) {
      _toggleEmptyHero(true);
      UIStates.set(body, 'empty', {
        title: 'まだ解析したサイトがありません',
        msg: '上の欄に URL を入れて解析するか、サンプルレポートで内容を確かめられます。',
        cta: { label: 'サンプルレポートを見る', onClick: () => document.getElementById('hero-sample-btn')?.click() },
      });
      // 画面の主ボタンは「解析を始める」の 1 個。空状態の操作は副次にする。
      body.querySelector('.ui-state .c-btn')?.classList.remove('c-btn--primary');
      return;
    }
    _toggleEmptyHero(false);
    body.innerHTML = _buildTable(data.items);
    const openRow = (domain) => {
      document.dispatchEvent(new CustomEvent('webspec2doc:report-viewed'));
      openResultsForDomain(domain);
    };
    body.querySelectorAll('.hist-open').forEach(b => b.addEventListener('click', (ev) => { ev.stopPropagation(); openRow(b.dataset.domain); }));
    body.querySelectorAll('tr[data-domain]').forEach(tr => tr.addEventListener('click', (ev) => {
      if (ev.target.closest('button, a, .c-menu')) return;
      openRow(tr.dataset.domain);
    }));
    body.querySelectorAll('.hist-recrawl').forEach(b => b.addEventListener('click', async () => {
      b.disabled = true;
      const orig = b.textContent;
      b.textContent = '読み込み中…';
      try { await recrawlSite(b.dataset.domain); } finally { b.disabled = false; b.textContent = orig; }
    }));
    body.querySelectorAll('.hist-delete').forEach(b => b.addEventListener('click', () => deleteSite(b.dataset.domain, b)));
  } catch (e) {
    // 空状態・エラー状態は ui-states.js に統一（再試行導線つき）。
    UIStates.set(body, 'error', {
      title: '解析履歴の読み込みに失敗しました',
      msg: '通信状態を確認して、もう一度お試しください。',
      cta: { label: '再試行', onClick: loadHistory },
    });
  }
}

// 説明文と工程チップはサイトが 0 件のときだけ出す
function _toggleEmptyHero(isEmpty) {
  document.querySelectorAll('#view-dashboard [data-when-empty]').forEach(el => { el.hidden = !isEmpty; });
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
        <div class="stat-card-head"><span class="stat-card-icon ${driftClass}">${icon('<path d="M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>')}</span><span class="stat-card-label">差分件数</span></div>
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
      <tr class="${it.has_diff ? 'has-drift' : ''} is-clickable" data-domain="${escHtml(it.domain)}">
        <td><div class="site-cell"><strong>${escHtml(it.domain)}</strong>${diffBadge}</div></td>
        <td class="num">${it.screens}</td>
        <td class="num">${it.fields}</td>
        <td>${snapBadge}</td>
        <td><span class="freshness ${fresh.cls}">${fresh.label}</span></td>
        <td><div class="history-actions">
          <button type="button" class="c-btn c-btn--sm hist-open" data-domain="${escHtml(it.domain)}">開く</button>
          <div class="c-menu" data-menu>
            <button type="button" class="c-menu__toggle" aria-haspopup="menu" aria-expanded="false" aria-label="${escHtml(it.domain)} のその他の操作">…</button>
            <ul class="c-menu__list" role="menu" hidden>
              <li role="none"><button type="button" role="menuitem" class="c-menu__item hist-recrawl" data-domain="${escHtml(it.domain)}">再解析</button></li>
              <li role="none"><button type="button" role="menuitem" class="c-menu__item c-menu__item--danger hist-delete" data-domain="${escHtml(it.domain)}">削除</button></li>
            </ul>
          </div>
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
