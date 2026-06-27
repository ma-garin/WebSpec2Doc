// ---- Delivery Backlog ----
const DELIVERY_ITEMS = {
  'WS2D-142': {
    title: '認証画面を含むサイト解析を安定化する',
    description: 'ログインが必要な Web システムでも、認証状態を維持したまま安定して画面を収集できるようにする。',
    priority: 'High', priorityClass: 'priority-high',
    status: 'In Progress', statusClass: 'status-progress',
    assignee: 'Yuki M.', initials: 'YM', rich: true,
  },
  'WS2D-137': {
    title: '画面仕様書の差分表示を追加する',
    description: '前回クロールとの変更点を画面単位で比較し、追加・変更・削除をすぐに追跡できるようにする。',
    priority: 'Medium', priorityClass: 'priority-medium',
    status: 'To Do', statusClass: 'status-todo',
    assignee: 'Akira S.', initials: 'AS', rich: false,
  },
  'WS2D-131': {
    title: 'レポートの Excel エクスポートを改善する',
    description: '大規模な画面一覧でも閲覧しやすいシート構成と列幅に整え、レビュー時間を短縮する。',
    priority: 'High', priorityClass: 'priority-high',
    status: 'In Review', statusClass: 'status-review',
    assignee: 'Mina K.', initials: 'MK', rich: false,
  },
  'WS2D-126': {
    title: '再クロール時の変更通知を整理する',
    description: '仕様ドリフトの有無と影響範囲を簡潔に通知し、次に確認すべき画面を明確にする。',
    priority: 'Medium', priorityClass: 'priority-medium',
    status: 'Done', statusClass: 'status-done',
    assignee: 'Yuki M.', initials: 'YM', rich: false,
  },
  'WS2D-118': {
    title: '解析対象 URL の一括登録に対応する',
    description: '複数の開始 URL を一度に登録し、共通設定で解析キューへ追加できるようにする。',
    priority: 'Low', priorityClass: 'priority-low',
    status: 'To Do', statusClass: 'status-todo',
    assignee: 'Unassigned', initials: '—', rich: false,
  },
};

function selectDeliveryItem(key, { focusDetail = false } = {}) {
  const item = DELIVERY_ITEMS[key];
  const detail = document.getElementById('issue-detail');
  if (!item || !detail) return;

  document.querySelectorAll('.backlog-row').forEach((row) => {
    const selected = row.dataset.issueKey === key;
    row.classList.toggle('is-selected', selected);
    row.setAttribute('aria-selected', selected ? 'true' : 'false');
  });
  document.getElementById('issue-detail-key').textContent = key;
  document.getElementById('issue-detail-title').textContent = item.title;
  document.getElementById('issue-detail-description').textContent = item.description;
  document.getElementById('issue-detail-priority').innerHTML = `<span class="priority ${item.priorityClass}"><i></i>${item.priority}</span>`;
  document.getElementById('issue-detail-status').innerHTML = `<span class="status ${item.statusClass}">${item.status}</span>`;
  document.getElementById('issue-detail-assignee').innerHTML = `<span class="assignee"><i>${item.initials}</i>${item.assignee}</span>`;
  document.getElementById('issue-rich-detail').hidden = !item.rich;
  if (focusDetail && window.matchMedia('(max-width: 1200px)').matches) detail.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

document.querySelectorAll('.backlog-row').forEach((row) => {
  row.addEventListener('click', () => selectDeliveryItem(row.dataset.issueKey, { focusDetail: true }));
  row.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    selectDeliveryItem(row.dataset.issueKey, { focusDetail: true });
  });
});
