function arShowPreview() {
  const panel = document.getElementById('autorun-preview-panel');
  if (!panel) return;
  const isOpen = panel.style.display === 'flex';
  if (isOpen) {
    panel.style.display = 'none';
    return;
  }
  panel.style.display = 'flex';
  if (!_autoRunPreviewLoaded) {
    _autoRunPreviewLoaded = true;
    _autorunLoadPreview();
  }
}

function _autorunClosePreviewOnBackdrop(e) {
  if (e.target === document.getElementById('autorun-preview-panel')) arShowPreview();
}

// ---- AutoRun: テストプレビュー ----
async function _autorunLoadPreview() {
  if (!_autoRunJobId) return;
  const loadingEl = document.getElementById('autorun-preview-loading');
  if (loadingEl) loadingEl.textContent = '読み込み中…';
  try {
    const data = await fetch('/api/autorun/preview?job_id=' + encodeURIComponent(_autoRunJobId)).then(r => r.json());
    _autoRunPreviewData = data;
    _autorunRenderPreview(data);
    if (loadingEl) loadingEl.textContent = '';
  } catch (e) {
    if (loadingEl) loadingEl.textContent = '(読み込みエラー)';
  }
}

function _autorunRenderPreview(data) {
  const summaryEl = document.getElementById('autorun-preview-summary');
  const tableWrap = document.getElementById('autorun-preview-table-wrap');
  const specEl    = document.getElementById('autorun-preview-spec');

  const summary    = data.summary || {};
  const candidates = data.candidates || [];
  const byStatus   = summary.by_status || {};
  const byTitle    = summary.by_title || {};

  // サマリーバー
  if (summaryEl) {
    const autoCount  = byStatus.auto || 0;
    const skipCount  = (byStatus['manual-review'] || 0) + (byStatus.review || 0);
    const titleBadges = Object.entries(byTitle)
      .map(([t, c]) => `<span class="fmt-badge">${escHtml(t)}: ${c}</span>`)
      .join('');
    summaryEl.innerHTML = `
      <div class="autorun-preview-counts">
        <span><strong>${summary.total || 0}</strong> 件</span>
        <span class="status-low">自動: ${autoCount}</span>
        <span class="status-muted">スキップ: ${skipCount}</span>
      </div>
      <div class="fmt-badges autorun-preview-badges">${titleBadges}</div>`;
  }

  // テストケーステーブル（行クリックで手順・期待結果の全文を別行に展開する。
  // 従来は steps がどこにも表示されず、期待結果も60文字で打ち切られていた。）
  if (tableWrap) {
    if (candidates.length) {
      const rows = candidates.map((c, i) => {
        const statusCls = c.automation_status === 'auto' ? 'status-low' : 'status-muted';
        const steps = Array.isArray(c.steps) ? c.steps : [];
        const stepsHtml = steps.length
          ? '<ol class="autorun-case-steps">' + steps.map(s => `<li>${escHtml(String(s))}</li>`).join('') + '</ol>'
          : '<p class="muted-copy">手順の記録なし</p>';
        return `<tr class="autorun-case-row" data-case-idx="${i}" tabindex="0" role="button" aria-expanded="false">
          <td class="cell-id">${escHtml(c.id || '')}</td>
          <td class="cell-title">${escHtml(c.title || '')} <span class="autorun-case-detail-toggle">詳細 ▶</span></td>
          <td class="cell-status ${statusCls}">${escHtml(c.automation_status || '')}</td>
          <td class="cell-id">${escHtml(c.trace_id || '')}</td>
          <td class="cell-muted">${escHtml((c.expected || '').substring(0, 60))}</td>
        </tr>
        <tr class="autorun-case-detail-row" data-case-detail="${i}" hidden>
          <td colspan="5">
            <div class="autorun-case-detail-body">
              <div><strong>手順</strong>${stepsHtml}</div>
              <div><strong>期待結果</strong><p>${escHtml(c.expected || '(記録なし)')}</p></div>
            </div>
          </td>
        </tr>`;
      }).join('');
      tableWrap.innerHTML = `<table class="data autorun-preview-table">
        <thead><tr><th>ID</th><th>タイトル</th><th>自動化</th><th>Trace</th><th>期待結果</th></tr></thead>
        <tbody>${rows}</tbody></table>`;
      tableWrap.querySelectorAll('.autorun-case-row').forEach(row => {
        const toggle = () => {
          const idx = row.dataset.caseIdx;
          const detailRow = tableWrap.querySelector(`[data-case-detail="${idx}"]`);
          const toggleLabel = row.querySelector('.autorun-case-detail-toggle');
          if (!detailRow) return;
          const nowOpen = detailRow.hasAttribute('hidden');
          if (nowOpen) detailRow.removeAttribute('hidden'); else detailRow.setAttribute('hidden', '');
          row.setAttribute('aria-expanded', String(nowOpen));
          if (toggleLabel) toggleLabel.textContent = nowOpen ? '詳細 ▼' : '詳細 ▶';
        };
        row.addEventListener('click', toggle);
        row.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
      });
    } else {
      tableWrap.innerHTML = '<div class="empty arm-empty">テストケースなし</div>';
    }
  }

  // スクリプト
  if (specEl) specEl.textContent = data.spec_content || '(スクリプトなし)';
}
