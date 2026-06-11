// ====================== レビューワークフロー ======================

// キャッシュ: 最後に取得したケース一覧（フィルタ再描画用）
let _reviewCases = [];

const _STATUS_LABELS = {
  draft:     '下書き',
  reviewing: 'レビュー中',
  approved:  '承認済み',
  frozen:    '確定版',
};

// ステータス遷移順（差し戻し・次へ用）
const _STATUS_ORDER = ['draft', 'reviewing', 'approved', 'frozen'];

function _prevStatus(status) {
  const idx = _STATUS_ORDER.indexOf(status);
  return idx > 0 ? _STATUS_ORDER[idx - 1] : null;
}

function _nextStatus(status) {
  const idx = _STATUS_ORDER.indexOf(status);
  return idx >= 0 && idx < _STATUS_ORDER.length - 1 ? _STATUS_ORDER[idx + 1] : null;
}

function _statusBadge(status) {
  const label = _STATUS_LABELS[status] || status;
  return `<span class="status-badge status-${escHtml(status)}">${escHtml(label)}</span>`;
}

function renderCaseRow(tc) {
  const frozen = tc.status === 'frozen';
  const prev = _prevStatus(tc.status);
  const next = _nextStatus(tc.status);
  const canFreeze = tc.status === 'approved';

  const prevBtn = prev
    ? `<button type="button" class="btn-outline-sm review-prev-btn"
         data-id="${escHtml(tc.id)}" data-status="${escHtml(prev)}"
         style="font-size:11px;height:28px;padding:0 8px">← 差し戻し</button>`
    : '';
  const nextBtn = (next && next !== 'frozen')
    ? `<button type="button" class="btn-outline-sm review-next-btn"
         data-id="${escHtml(tc.id)}" data-status="${escHtml(next)}"
         style="font-size:11px;height:28px;padding:0 8px">承認 →</button>`
    : '';
  const freezeBtn = canFreeze
    ? `<button type="button" class="btn-primary review-freeze-btn"
         data-id="${escHtml(tc.id)}"
         style="font-size:11px;height:28px;padding:0 8px">確定</button>`
    : '';

  return `
    <tr data-id="${escHtml(tc.id)}" data-status="${escHtml(tc.status)}">
      <td style="white-space:nowrap">${escHtml(tc.id)}</td>
      <td>${escHtml(tc.title)}</td>
      <td>${_statusBadge(tc.status)}</td>
      <td>
        <input type="text" class="review-comment-input"
          data-id="${escHtml(tc.id)}"
          value="${escHtml(tc.comment)}"
          placeholder="コメントを入力"
          ${frozen ? 'disabled' : ''} />
      </td>
      <td style="text-align:center">${tc.version}</td>
      <td>
        <div class="review-row-actions">
          ${prevBtn}${nextBtn}${freezeBtn}
        </div>
      </td>
    </tr>`;
}

function _renderTable(cases) {
  const tbody = document.getElementById('review-cases-tbody');
  const empty = document.getElementById('review-empty');
  if (!tbody) return;

  if (!cases.length) {
    tbody.innerHTML = '';
    if (empty) empty.style.display = '';
    return;
  }
  if (empty) empty.style.display = 'none';
  tbody.innerHTML = cases.map(renderCaseRow).join('');

  // 操作ボタンのイベント登録
  tbody.querySelectorAll('.review-prev-btn, .review-next-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.id;
      const status = btn.dataset.status;
      const comment = _getComment(id);
      updateCaseStatus(_currentReviewDomain(), id, status, comment);
    });
  });
  tbody.querySelectorAll('.review-freeze-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.id;
      const comment = _getComment(id);
      updateCaseStatus(_currentReviewDomain(), id, 'frozen', comment);
    });
  });
}

function _getComment(caseId) {
  const input = document.querySelector(`.review-comment-input[data-id="${caseId}"]`);
  return input ? input.value : '';
}

function _currentReviewDomain() {
  // グローバル変数 currentDomain（他モジュールと共有）があれば使う
  return (typeof currentDomain !== 'undefined' && currentDomain) ? currentDomain : '';
}

function _applyFilter(cases) {
  const sel = document.getElementById('review-filter');
  const filter = sel ? sel.value : 'all';
  if (filter === 'all') return cases;
  return cases.filter(c => c.status === filter);
}

async function loadReviewCases(domain) {
  const tbody = document.getElementById('review-cases-tbody');
  if (tbody) tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#888">読み込み中...</td></tr>';

  try {
    const res = await fetch('/review/cases?domain=' + encodeURIComponent(domain));
    const data = await res.json();
    _reviewCases = data.cases || [];
    _renderTable(_applyFilter(_reviewCases));
  } catch (e) {
    if (tbody) tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#c00">読み込みに失敗しました</td></tr>';
  }
}

async function updateCaseStatus(domain, caseId, newStatus, comment) {
  try {
    const res = await fetch('/review/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ domain, case_id: caseId, status: newStatus, comment }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert('更新に失敗しました: ' + (err.error || res.status));
      return;
    }
    const updated = await res.json();
    // ローカルキャッシュを更新して再描画（再fetchせず即時反映）
    const idx = _reviewCases.findIndex(c => c.id === caseId);
    if (idx !== -1) {
      _reviewCases[idx] = {
        ..._reviewCases[idx],
        status: updated.status,
        version: updated.version,
        comment,
      };
    }
    _renderTable(_applyFilter(_reviewCases));
  } catch (e) {
    alert('ネットワークエラーが発生しました');
  }
}

async function exportApprovedCases(domain) {
  try {
    const res = await fetch('/review/export?domain=' + encodeURIComponent(domain) + '&filter=approved');
    if (!res.ok) {
      alert('エクスポートに失敗しました: ' + res.status);
      return;
    }
    const data = await res.json();
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = (domain || 'review') + '_approved_cases.json';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert('エクスポート中にエラーが発生しました');
  }
}

function initReview(domain) {
  loadReviewCases(domain);

  const filter = document.getElementById('review-filter');
  if (filter) {
    filter.addEventListener('change', () => {
      _renderTable(_applyFilter(_reviewCases));
    });
  }

  const exportBtn = document.getElementById('review-export-btn');
  if (exportBtn) {
    exportBtn.addEventListener('click', () => exportApprovedCases(domain));
  }
}
