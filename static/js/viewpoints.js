const vpState = {
  booted: false,
  loading: false,
  sets: [],
  currentSet: null,
  versions: [],
  currentVersion: null,
  items: [],
  selectedItem: null,
  selectedIds: new Set(),
  assignments: [],
  tab: 'draft',
  dirty: false,
  aiAvailable: false,
  lastDeleted: null,
  editorMode: 'closed',
  editorOpener: null,
  listScrollTop: 0,
  conflict: null,
  tree: [],
  currentFolder: null, // null = "すべて"
};

const VP_AUTOMATION_LABELS = {
  automated: '自動',
  semi_automated: '半自動',
  manual: '手動',
};

// テンプレート一覧は data/viewpoint_templates/*.json から /api/viewpoint-templates
// 経由で動的取得する（フォルダ名だけでなく実際の観点アイテムを含む）。
let vpTemplatesCache = null;

/* ── API ── */
async function vpApi(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const response = await fetch(url, { ...options, headers });
  let data = {};
  try { data = await response.json(); } catch (_) { data = {}; }
  if (!response.ok) {
    const error = new Error(data.error || `APIエラー (${response.status})`);
    error.status = response.status;
    error.details = data.details;
    throw error;
  }
  return data;
}

/* ── フィードバック ── */
function vpFeedback(message, type = 'success', action = null) {
  const box = document.getElementById('vp-feedback');
  const text = document.getElementById('vp-feedback-text');
  const actionButton = document.getElementById('vp-feedback-action');
  if (!box || !text || !actionButton) return;
  text.textContent = message;
  box.dataset.type = type;
  box.hidden = false;
  actionButton.hidden = !action;
  actionButton.textContent = action?.label || '';
  actionButton.onclick = action?.handler || null;
}

function vpClearFeedback() {
  const box = document.getElementById('vp-feedback');
  if (box) box.hidden = true;
}

/* ── 起動・セット一覧 ── */
async function loadViewpointManager() {
  if (vpState.loading) return;
  vpState.loading = true;
  try {
    const data = await vpApi('/api/viewpoint-sets');
    vpState.sets = data.sets || [];
    vpState.aiAvailable = !!data.ai_available;
    vpRenderSets();
    const selected = vpState.currentSet
      ? vpState.sets.find((item) => item.id === vpState.currentSet.id)
      : vpState.sets[0];
    if (selected) await vpSelectSet(selected.id, { skipDirtyCheck: true });
    else vpRenderTableEmpty('観点セットがありません。「新規セット」から作成してください。');
    vpState.booted = true;
  } catch (error) {
    vpFeedback(`観点管理を読み込めません: ${error.message}`, 'error');
    vpRenderTableEmpty('観点DBを読み込めませんでした。再試行してください。');
  } finally {
    vpState.loading = false;
  }
}

function vpRenderSets() {
  const container = document.getElementById('vp-set-list');
  if (!container) return;
  const byParent = new Map();
  vpState.sets.forEach((item) => {
    const parent = item.parent_set_id || '';
    if (!byParent.has(parent)) byParent.set(parent, []);
    byParent.get(parent).push(item);
  });
  const rows = [];
  const visit = (item, depth) => {
    const active = item.id === vpState.currentSet?.id ? ' is-active' : '';
    const version = item.draft_version
      ? `下書き v${item.draft_version}`
      : item.published_version
        ? `公開 v${item.published_version}`
        : '未公開';
    rows.push(`<button type="button" class="vp-set-row${active}" data-vp-set-id="${escHtml(item.id)}" data-depth="${depth}">
      <strong>${escHtml(item.name)}</strong><span class="vp-set-count">${Number(item.item_count || 0)}</span>
      <span class="vp-set-meta">${escHtml(version)}</span>
    </button>`);
    (byParent.get(item.id) || []).forEach((child) => visit(child, Math.min(depth + 1, 1)));
  };
  (byParent.get('') || vpState.sets).forEach((item) => visit(item, 0));
  container.innerHTML = rows.join('');
  container.querySelectorAll('[data-vp-set-id]').forEach((button) => {
    button.addEventListener('click', () => vpSelectSet(button.dataset.vpSetId));
  });
  const total = vpState.sets.reduce((sum, item) => sum + Number(item.item_count || 0), 0);
  const summary = document.getElementById('vp-set-summary');
  if (summary) summary.textContent = `${vpState.sets.length}セット / 観点 ${total}件`;
}

async function vpSelectSet(setId, { skipDirtyCheck = false } = {}) {
  if (!skipDirtyCheck && !(await vpMaybeDiscard())) return;
  if (!document.getElementById('vp-editor-overlay')?.hidden) {
    await vpCloseEditor({ force: true, restore: false });
  }
  const selected = vpState.sets.find((item) => item.id === setId);
  if (!selected) return;
  vpState.currentSet = selected;
  vpState.selectedItem = null;
  vpState.selectedIds.clear();
  vpState.dirty = false;
  vpState.currentFolder = null;
  vpRenderSets();
  try {
    const [detail, assignments] = await Promise.all([
      vpApi(`/api/viewpoint-sets/${encodeURIComponent(setId)}`),
      vpApi(`/api/viewpoint-sets/${encodeURIComponent(setId)}/assignments`),
    ]);
    vpState.versions = detail.versions || [];
    vpState.assignments = assignments.assignments || [];
    vpRenderAssignments();
    await vpLoadCurrentTab();
  } catch (error) {
    vpFeedback(error.message, 'error');
  }
}

/* ── タブ ── */
async function vpLoadCurrentTab() {
  const isProposal = vpState.tab === 'proposals';
  const isHistory = vpState.tab === 'history';
  const isTable = !isProposal && !isHistory;

  document.getElementById('vp-standard-toolbar').hidden = !isTable;
  document.getElementById('vp-proposal-toolbar').hidden = !isProposal;
  document.getElementById('vp-publish').hidden = vpState.tab !== 'draft';
  document.getElementById('vp-add-viewpoint').hidden = vpState.tab !== 'draft';
  document.querySelector('.vp-inline-table-wrap').hidden = !isTable;
  document.querySelector('.vp-count-bar').hidden = !isTable;
  document.getElementById('vp-list-content').hidden = isTable;
  document.getElementById('vp-tree-panel').hidden = !isTable;

  if (isProposal) return vpLoadProposals();
  if (isHistory) return vpRenderHistory();

  let version = vpState.versions.find((item) => item.status === vpState.tab);
  if (!version && vpState.tab === 'draft') {
    const created = await vpApi(
      `/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/versions`,
      { method: 'POST', body: '{}' },
    );
    version = created.version;
    vpState.versions.unshift(version);
    await vpRefreshSetsOnly();
  }
  vpState.currentVersion = version || null;
  if (!version) {
    vpState.items = [];
    vpRenderItems();
    vpRenderTableEmpty(vpState.tab === 'published' ? '公開版はまだありません。' : '下書きを作成できません。');
    return;
  }
  const [itemsData] = await Promise.all([
    vpApi(`/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/versions/${version.version_number}/items`),
    vpLoadTree(),
  ]);
  vpState.currentVersion = itemsData.version;
  vpState.items = itemsData.items || [];
  vpPopulateCategoryDatalist();
  vpRenderItems();
}

async function vpRefreshSetsOnly() {
  const data = await vpApi('/api/viewpoint-sets');
  vpState.sets = data.sets || [];
  vpState.currentSet = vpState.sets.find((item) => item.id === vpState.currentSet?.id) || null;
  vpRenderSets();
}

/* ── ツリー ── */
async function vpLoadTree() {
  if (!vpState.currentSet) return;
  try {
    const data = await vpApi(`/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/tree`);
    vpState.tree = data.nodes || [];
    vpRenderTree();
  } catch (_) { /* ignore */ }
}

function vpRenderTree() {
  const root = document.getElementById('vp-tree-root');
  if (!root) return;
  const folders = vpState.tree.filter((node) => node.node_type === 'folder');
  const allCount = vpState.tree.filter((node) => node.node_type !== 'folder').length;

  const allBtn = document.getElementById('vp-tree-all-btn');
  if (allBtn) {
    allBtn.classList.toggle('is-selected', vpState.currentFolder === null);
    const allCountEl = document.getElementById('vp-tree-all-count');
    if (allCountEl) allCountEl.textContent = allCount || '';
  }

  if (!folders.length) {
    root.innerHTML = '<div style="padding:10px 12px;color:var(--text-muted);font-size:11px;">フォルダがありません</div>';
    return;
  }
  root.innerHTML = folders.map((folder) => {
    const selected = vpState.currentFolder === folder.persistent_key ? ' is-selected' : '';
    const count = folder.children_count || 0;
    const isDraft = vpState.tab === 'draft';
    return `<div class="vp-tree-node${selected}" data-vp-folder="${escHtml(folder.persistent_key)}" role="treeitem" tabindex="0">
      <span class="vp-tree-node-icon" aria-hidden="true">📁</span>
      <span class="vp-tree-node-name">${escHtml(folder.name)}</span>
      ${count ? `<span class="vp-tree-count">${count}</span>` : ''}
      ${isDraft ? `<span class="vp-tree-node-actions">
        <button type="button" class="vp-tree-action" data-vp-folder-delete="${escHtml(folder.id)}" title="フォルダを削除" aria-label="${escHtml(folder.name)}を削除">🗑</button>
      </span>` : ''}
    </div>`;
  }).join('');

  root.querySelectorAll('[data-vp-folder]').forEach((node) => {
    node.addEventListener('click', (event) => {
      if (event.target.closest('[data-vp-folder-delete]')) return;
      vpSelectFolder(node.dataset.vpFolder);
    });
    node.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); vpSelectFolder(node.dataset.vpFolder); }
    });
  });
  root.querySelectorAll('[data-vp-folder-delete]').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      vpDeleteFolder(button.dataset.vpFolderDelete);
    });
  });
}

function vpSelectFolder(folderKey) {
  vpState.currentFolder = folderKey === vpState.currentFolder ? null : folderKey;
  vpRenderTree();
  vpRenderItems();
  vpUpdateBreadcrumb();
}

function vpUpdateBreadcrumb() {
  const bc = document.getElementById('vp-breadcrumb');
  if (!bc) return;
  if (!vpState.currentFolder) {
    bc.innerHTML = '<span class="vp-breadcrumb-root">すべて</span>';
    return;
  }
  const folder = vpState.tree.find((n) => n.persistent_key === vpState.currentFolder);
  bc.innerHTML = `<span class="vp-breadcrumb-root">すべて</span>
    <span class="vp-breadcrumb-sep" aria-hidden="true">›</span>
    <span class="vp-breadcrumb-item">${escHtml(folder?.name || vpState.currentFolder)}</span>`;
}

async function vpNewFolder() {
  if (vpState.tab !== 'draft' || !vpState.currentSet) return;
  const name = await inputDialog({
    title: 'フォルダを作成',
    message: '分類フォルダの名前を入力してください。',
    placeholder: '例: 機能性 / 認証 / ログイン',
    confirmLabel: '作成',
    validate: (v) => v.trim() ? null : 'フォルダ名を入力してください。',
  });
  if (!name?.trim()) return;
  try {
    await vpApi(`/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/folders`, {
      method: 'POST', body: JSON.stringify({ name: name.trim() }),
    });
    await vpLoadTree();
    vpFeedback(`フォルダ「${name.trim()}」を作成しました。`);
  } catch (error) { vpFeedback(error.message, 'error'); }
}

async function vpDeleteFolder(itemId) {
  const folder = vpState.tree.find((n) => n.id === itemId);
  const confirmed = await confirmDialog({
    title: 'フォルダを削除しますか？',
    message: `「${folder?.name || 'フォルダ'}」を削除します。フォルダ内の観点も一緒に削除されます。`,
    confirmLabel: '削除', danger: true,
  });
  if (!confirmed) return;
  try {
    await vpApi(`/api/viewpoint-folders/${encodeURIComponent(itemId)}`, { method: 'DELETE' });
    if (vpState.currentFolder === folder?.persistent_key) {
      vpState.currentFolder = null;
      vpUpdateBreadcrumb();
    }
    await Promise.all([vpLoadTree(), vpReloadItems()]);
    vpFeedback('フォルダを削除しました。', 'success', { label: '元に戻す', handler: () => vpUndoDeleteFolder(itemId) });
  } catch (error) { vpFeedback(error.message, 'error'); }
}

async function vpUndoDeleteFolder(itemId) {
  try {
    await vpApi(`/api/viewpoint-items/${encodeURIComponent(itemId)}/restore`, { method: 'POST', body: '{}' });
    await Promise.all([vpLoadTree(), vpReloadItems()]);
    vpFeedback('フォルダを元に戻しました。');
  } catch (error) { vpFeedback(error.message, 'error'); }
}

async function vpFetchTemplates() {
  if (vpTemplatesCache) return vpTemplatesCache;
  try {
    const data = await vpApi('/api/viewpoint-templates');
    vpTemplatesCache = data.templates || [];
  } catch (error) {
    vpTemplatesCache = [];
    vpFeedback(error.message, 'error');
  }
  return vpTemplatesCache;
}

function vpRenderTemplateMenu(templates) {
  const container = document.getElementById('vp-template-menu-items');
  if (!container) return;
  container.innerHTML = templates.length
    ? templates.map((t) => `
      <button type="button" class="vp-template-item" data-template="${escHtml(t.key)}" role="menuitem">
        <strong>${escHtml(t.name)}</strong>
        <span>${escHtml(t.description || '')}（${t.folder_count}フォルダ・${t.item_count}観点）</span>
      </button>`).join('')
    : '<div class="vp-template-menu-empty">利用可能なテンプレートがありません。</div>';
}

async function vpLoadTemplate(templateKey) {
  const templates = await vpFetchTemplates();
  const template = templates.find((t) => t.key === templateKey);
  if (!template || !vpState.currentSet || vpState.tab !== 'draft') return;
  const confirmed = await confirmDialog({
    title: `「${template.name}」を読み込みますか？`,
    message: `${template.folder_count}個のフォルダと${template.item_count}件の観点アイテムを追加します。既存のフォルダ・観点は変更されません。`,
    confirmLabel: '読み込む',
  });
  if (!confirmed) return;
  try {
    await vpApi(
      `/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/templates/${encodeURIComponent(templateKey)}/apply`,
      { method: 'POST' }
    );
    await vpLoadCurrentTab();
    vpFeedback(`「${template.name}」を読み込みました（${template.folder_count}フォルダ・${template.item_count}観点）。`);
  } catch (error) { vpFeedback(error.message, 'error'); }
}

/* ── アイテム一覧 ── */
function vpFilteredItems() {
  const query = (document.getElementById('vp-search')?.value || '').trim().toLowerCase();
  const risk = document.getElementById('vp-filter-risk')?.value || '';
  const automation = document.getElementById('vp-filter-automation')?.value || '';
  const state = document.getElementById('vp-filter-state')?.value || '';

  let folder = vpState.currentFolder;
  return vpState.items.filter((item) => {
    if (item.node_type === 'folder') return false;
    if (folder) {
      if (item.parent_key !== folder) return false;
    }
    const haystack = [item.name, item.category, item.purpose, ...(item.tags || [])].join(' ').toLowerCase();
    return (!query || haystack.includes(query))
      && (!risk || String(item.risk_weight) === risk)
      && (!automation || item.automation === automation)
      && (!state || (state === 'enabled') === !!item.enabled);
  });
}

function vpPopulateCategoryDatalist() {
  const datalist = document.getElementById('vp-category-datalist');
  if (!datalist) return;
  const categories = [...new Set(vpState.items.map((item) => item.category).filter(Boolean))].sort();
  while (datalist.firstChild) datalist.removeChild(datalist.firstChild);
  categories.forEach((cat) => {
    const opt = document.createElement('option');
    opt.value = cat;
    datalist.appendChild(opt);
  });
}

// keep old name for compatibility with viewpoint-editor.js
function vpPopulateCategoryFilter() {
  vpPopulateCategoryDatalist();
}

function vpRenderItems() {
  const tbody = document.getElementById('vp-table-body');
  const emptyEl = document.getElementById('vp-table-empty');
  if (!tbody) return;

  const items = vpFilteredItems();
  const countEl = document.getElementById('vp-item-count');
  if (countEl) countEl.textContent = `${items.length}件`;

  if (!items.length) {
    tbody.innerHTML = '';
    if (emptyEl) emptyEl.hidden = false;
    vpUpdateBulkbar();
    return;
  }
  if (emptyEl) emptyEl.hidden = true;

  tbody.innerHTML = items.map((item) => {
    const checked = vpState.selectedIds.has(item.id) ? ' checked' : '';
    const active = vpState.selectedItem?.id === item.id ? ' is-active' : '';
    const disabled = item.enabled ? '' : ' is-disabled';
    const inherited = item.inherited ? ' <span class="vp-inherited">継承</span>' : '';
    return `<tr class="${active}${disabled}" data-vp-item-id="${escHtml(item.id)}" tabindex="0" aria-label="${escHtml(item.name)}">
      <td class="vp-col-check"><input type="checkbox" data-vp-check="${escHtml(item.id)}" aria-label="${escHtml(item.name)}を選択"${checked}></td>
      <td class="vp-col-name">
        <span class="vp-cell-name">${escHtml(item.name)}${inherited}</span>
        <span class="vp-cell-tags">${escHtml((item.tags || []).join(' / '))}</span>
      </td>
      <td class="vp-col-category">${escHtml(item.category)}</td>
      <td class="vp-col-risk"><span class="vp-risk-badge" data-risk="${Number(item.risk_weight)}">${Number(item.risk_weight)}</span></td>
      <td class="vp-col-auto"><span class="vp-auto-badge" data-value="${escHtml(item.automation)}">${escHtml(VP_AUTOMATION_LABELS[item.automation] || item.automation)}</span></td>
      <td class="vp-col-state"><span class="vp-state-dot${item.enabled ? '' : ' is-disabled'}">${item.enabled ? '有効' : '無効'}</span></td>
      <td class="vp-col-actions"><button type="button" class="vp-row-action" data-vp-edit="${escHtml(item.id)}" aria-label="${escHtml(item.name)}を編集">✏</button></td>
    </tr>`;
  }).join('');

  tbody.querySelectorAll('tr[data-vp-item-id]').forEach((row) => {
    row.addEventListener('click', (event) => {
      if (event.target.matches('input[type="checkbox"]') || event.target.closest('[data-vp-edit]')) return;
      vpSelectItem(row.dataset.vpItemId, row);
    });
    row.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      vpSelectItem(row.dataset.vpItemId, row);
    });
  });
  tbody.querySelectorAll('[data-vp-edit]').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      vpSelectItem(button.dataset.vpEdit, button.closest('tr'));
    });
  });
  tbody.querySelectorAll('[data-vp-check]').forEach((checkbox) => {
    checkbox.addEventListener('change', () => vpToggleSelection(checkbox.dataset.vpCheck, checkbox.checked));
  });
  document.getElementById('vp-check-all')?.addEventListener('change', (event) => {
    items.forEach((item) => event.target.checked ? vpState.selectedIds.add(item.id) : vpState.selectedIds.delete(item.id));
    vpRenderItems();
  });
  vpUpdateBulkbar();
}

function vpRenderTableEmpty(message) {
  const tbody = document.getElementById('vp-table-body');
  const emptyEl = document.getElementById('vp-table-empty');
  if (tbody) tbody.innerHTML = '';
  if (emptyEl) {
    emptyEl.hidden = false;
    emptyEl.innerHTML = `<p>${escHtml(message)}</p>`;
  }
  const countEl = document.getElementById('vp-item-count');
  if (countEl) countEl.textContent = '0件';
}

// keep old name for viewpoint-editor.js
function vpRenderEmpty(message) {
  vpRenderTableEmpty(message);
}

function vpToggleSelection(itemId, checked) {
  if (checked) vpState.selectedIds.add(itemId);
  else vpState.selectedIds.delete(itemId);
  vpUpdateBulkbar();
}

function vpUpdateBulkbar() {
  const count = vpState.selectedIds.size;
  const bulkbar = document.getElementById('vp-bulkbar');
  if (bulkbar) bulkbar.hidden = !count || vpState.tab !== 'draft';
  const countEl = document.getElementById('vp-selected-count');
  if (countEl) countEl.textContent = `${count}件を選択`;
}

/* ── アンドゥ ── */
async function vpUndoDelete() {
  if (!vpState.lastDeleted) return;
  const target = vpState.lastDeleted;
  const url = target.type === 'item'
    ? `/api/viewpoint-items/${encodeURIComponent(target.id)}/restore`
    : `/api/viewpoint-sets/${encodeURIComponent(target.id)}/restore`;
  try {
    await vpApi(url, { method: 'POST', body: '{}' });
    vpState.lastDeleted = null;
    await loadViewpointManager();
    vpFeedback('削除を取り消しました。');
  } catch (error) { vpFeedback(error.message, 'error'); }
}

/* ── 公開 ── */
async function vpPublish() {
  if (!vpState.currentVersion || vpState.currentVersion.status !== 'draft') return;
  let diffText = '';
  const published = vpState.versions.find((item) => item.status === 'published');
  if (published) {
    try {
      const data = await vpApi(`/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/versions/diff?from=${published.version_number}&to=${vpState.currentVersion.version_number}`);
      const diff = data.diff;
      diffText = `追加${diff.added.length}件・変更${diff.changed.length}件・削除${diff.removed.length}件。`;
    } catch (_) { diffText = ''; }
  }
  const confirmed = await confirmDialog({
    title: `v${vpState.currentVersion.version_number} を公開しますか？`,
    message: `${diffText} 公開後はこの版を変更できず、AutoRunの選択対象になります。`,
    confirmLabel: '公開',
  });
  if (!confirmed) return;
  const reason = await inputDialog({
    title: '変更理由',
    message: `v${vpState.currentVersion.version_number} を公開します。変更理由を入力してください。`,
    placeholder: '観点セットを更新',
    defaultValue: '観点セットを更新',
    confirmLabel: '公開する',
  }) ?? '';
  try {
    await vpApi(
      `/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/versions/${vpState.currentVersion.version_number}/publish`,
      { method: 'POST', body: JSON.stringify({ revision: vpState.currentVersion.revision, change_reason: reason }) },
    );
    vpState.tab = 'published';
    vpSyncTabs();
    await vpSelectSet(vpState.currentSet.id, { skipDirtyCheck: true });
    vpFeedback(`v${vpState.currentVersion.version_number} を公開しました。`);
  } catch (error) { vpFeedback(error.message, 'error'); }
}

/* ── バルク操作 ── */
async function vpBulkApply(action) {
  const changes = {};
  if (action === 'enable') changes.enabled = true;
  if (action === 'disable') changes.enabled = false;
  if (action === 'tag') {
    const existingTags = [...new Set(vpState.items.flatMap((item) => item.tags || []).filter(Boolean))].sort();
    const tag = await inputDialog({
      title: 'タグを設定',
      message: `選択した${vpState.selectedIds.size}件にタグを追加します。`,
      placeholder: '例: 認証, フォーム',
      confirmLabel: 'タグを設定',
      suggestions: existingTags,
    });
    if (!tag) return;
    changes.tags = [tag.trim()];
  }
  if (action === 'category') {
    const categories = [...new Set(vpState.items.map((item) => item.category).filter(Boolean))].sort();
    const category = await inputDialog({
      title: 'カテゴリを変更',
      message: `選択した${vpState.selectedIds.size}件のカテゴリを変更します。`,
      placeholder: '例: 機能 > 処理 > 正常処理',
      confirmLabel: 'カテゴリを変更',
      suggestions: categories,
    });
    if (!category) return;
    changes.category = category.trim();
  }
  if (action === 'risk') {
    const risk = await inputDialog({
      title: 'リスク重みを設定',
      message: `選択した${vpState.selectedIds.size}件のリスク重みを変更します（1〜5）。`,
      placeholder: '3',
      defaultValue: '3',
      confirmLabel: 'リスクを設定',
      validate: (v) => {
        const n = Number(v);
        if (!Number.isInteger(n) || n < 1 || n > 5) return 'リスク重みは 1〜5 の整数で入力してください。';
        return null;
      },
    });
    if (!risk) return;
    changes.risk_weight = Number(risk);
  }
  try {
    await vpApi('/api/viewpoint-items/bulk', {
      method: 'POST', body: JSON.stringify({ item_ids: [...vpState.selectedIds], changes }),
    });
    vpState.selectedIds.clear();
    await vpReloadItems();
    vpFeedback('一括変更を保存しました。');
  } catch (error) { vpFeedback(error.message, 'error'); }
}

/* ── 履歴 ── */
function vpRenderHistory() {
  const container = document.getElementById('vp-list-content');
  if (!container) return;
  const statusLabel = { draft: '下書き', published: '公開中', archived: 'アーカイブ' };
  const countEl = document.getElementById('vp-item-count');
  if (countEl) countEl.textContent = `${vpState.versions.length}版`;
  container.innerHTML = `<div class="vp-history-list">${vpState.versions.map((version) => `
    <article class="vp-history-row">
      <div class="vp-history-row-head"><strong>v${version.version_number}・${statusLabel[version.status] || version.status}</strong><span>${Number(version.item_count || 0)}件</span></div>
      <p>${escHtml(version.change_reason || '変更理由なし')} / ${escHtml(version.published_at || version.updated_at || '')}</p>
      <div class="vp-history-actions">
        ${version.status === 'archived' ? `<button type="button" data-vp-rollback="${version.version_number}">この版へロールバック</button>` : ''}
      </div>
    </article>`).join('')}</div>`;
  container.querySelectorAll('[data-vp-rollback]').forEach((button) => {
    button.addEventListener('click', () => vpRollback(Number(button.dataset.vpRollback)));
  });
}

async function vpRollback(version) {
  const confirmed = await confirmDialog({
    title: `v${version} の内容へ戻しますか？`,
    message: '旧版は変更せず、その内容から新しい公開版を作成します。',
    confirmLabel: '新しい公開版を作成',
  });
  if (!confirmed) return;
  try {
    const data = await vpApi(
      `/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/versions/${version}/rollback`,
      { method: 'POST', body: JSON.stringify({ reason: `v${version} へロールバック` }) },
    );
    await vpSelectSet(vpState.currentSet.id, { skipDirtyCheck: true });
    vpFeedback(`v${data.version.version_number} として公開しました。`);
  } catch (error) { vpFeedback(error.message, 'error'); }
}

/* ── AI提案 ── */
async function vpLoadProposals() {
  try {
    const data = await vpApi(`/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/proposals`);
    vpState.aiAvailable = !!data.ai_available;
    const genBtn = document.getElementById('vp-generate-proposals');
    if (genBtn) {
      genBtn.disabled = !vpState.aiAvailable;
      genBtn.textContent = vpState.aiAvailable ? 'AIに提案を依頼' : 'OpenAI設定が必要';
    }
    const proposals = data.proposals || [];
    const countEl = document.getElementById('vp-item-count');
    if (countEl) countEl.textContent = `${proposals.length}件`;
    const container = document.getElementById('vp-list-content');
    if (!proposals.length) return;
    const itemsByKey = Object.fromEntries(vpState.items.map((i) => [i.persistent_key, i.name]));
    const pct = (c) => Math.round(Number(c || 0) * 100);
    const confClass = (c) => pct(c) >= 80 ? 'vp-conf-high' : pct(c) >= 50 ? 'vp-conf-mid' : 'vp-conf-low';
    container.innerHTML = `<div class="vp-proposal-list">${proposals.map((proposal) => {
      const item = proposal.payload || {};
      const dupName = proposal.duplicate_key ? (itemsByKey[proposal.duplicate_key] || proposal.duplicate_key) : '';
      const dupHtml = dupName ? `<p class="vp-duplicate-warning">重複候補: 既存観点「${escHtml(dupName)}」と類似しています。採用する場合はその観点を先に削除または名称変更してください。</p>` : '';
      const statusHtml = proposal.status !== 'pending'
        ? `<span class="vp-proposal-status-badge ${proposal.status === 'adopted' ? 'is-adopted' : 'is-rejected'}">${proposal.status === 'adopted' ? '採用済み' : '却下済み'}</span>`
        : `<button type="button" class="vp-proposal-btn-adopt" data-vp-proposal-adopt="${escHtml(proposal.id)}"${proposal.duplicate_key ? ' disabled title="重複候補を解消してから採用できます"' : ''}>下書きへ採用</button><button type="button" class="vp-proposal-btn-reject" data-vp-proposal-reject="${escHtml(proposal.id)}">却下</button>`;
      return `<article class="vp-proposal-row">
        <div class="vp-proposal-row-head">
          <strong>${escHtml(item.name || '名称未設定')}</strong>
          <span class="vp-proposal-confidence ${confClass(proposal.confidence)}" title="AIの信頼度">${pct(proposal.confidence)}%</span>
        </div>
        <p class="vp-proposal-meta">${escHtml(item.category || '')} / リスク ${Number(item.risk_weight || 3)} / ${escHtml(VP_AUTOMATION_LABELS[item.automation] || item.automation || '')}</p>
        <p class="vp-proposal-rationale">${escHtml(proposal.rationale || '')}</p>
        ${dupHtml}
        <div class="vp-proposal-actions">${statusHtml}</div>
      </article>`;
    }).join('')}</div>`;
    container.querySelectorAll('[data-vp-proposal-adopt]').forEach((button) => button.addEventListener('click', () => vpDecideProposal(button.dataset.vpProposalAdopt, 'adopted')));
    container.querySelectorAll('[data-vp-proposal-reject]').forEach((button) => button.addEventListener('click', () => vpDecideProposal(button.dataset.vpProposalReject, 'rejected')));
  } catch (error) { vpFeedback(error.message, 'error'); }
}

async function vpGenerateProposals() {
  const notes = await inputDialog({
    title: 'AI提案のコンテキスト',
    message: '対象サイトや業種、追加で重視したいリスクを入力してください（省略可）。',
    placeholder: '例: ECサイト、決済フロー、個人情報入力あり',
    type: 'textarea',
    confirmLabel: '提案を依頼',
  }) ?? '';
  const button = document.getElementById('vp-generate-proposals');
  button.disabled = true;
  button.textContent = '提案を生成中…';
  try {
    await vpApi(`/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/proposals`, {
      method: 'POST', body: JSON.stringify({ notes }),
    });
    await vpLoadProposals();
    vpFeedback('AI提案を作成しました。採用するまで下書きには反映されません。');
  } catch (error) { vpFeedback(error.message, 'error'); }
  finally { button.disabled = !vpState.aiAvailable; button.textContent = vpState.aiAvailable ? 'AIに提案を依頼' : 'OpenAI設定が必要'; }
}

async function vpDecideProposal(proposalId, decision) {
  try {
    await vpApi(`/api/viewpoint-proposals/${encodeURIComponent(proposalId)}/decision`, {
      method: 'POST', body: JSON.stringify({ decision }),
    });
    await vpLoadProposals();
    await vpRefreshSetsOnly();
    vpFeedback(decision === 'adopted' ? '提案を下書きへ追加しました。' : '提案を却下しました。');
  } catch (error) { vpFeedback(error.message, 'error'); }
}

/* ── 適用ルール ── */
function vpRenderAssignments() {
  const container = document.getElementById('vp-assignment-list');
  if (!container) return;
  if (!vpState.assignments.length) {
    container.innerHTML = '<span class="vp-set-meta">既定選択のみ</span>';
    return;
  }
  container.innerHTML = vpState.assignments.map((assignment) => {
    const condition = assignment.rule?.condition || {};
    const text = `${condition.field || '条件'} ${condition.operator || ''} ${condition.value ?? ''}`;
    return `<div class="vp-assignment-row"><span>${escHtml(text)}</span><button type="button" data-vp-delete-assignment="${assignment.id}" aria-label="適用ルールを削除">×</button></div>`;
  }).join('');
  container.querySelectorAll('[data-vp-delete-assignment]').forEach((button) => {
    button.addEventListener('click', () => vpDeleteAssignment(button.dataset.vpDeleteAssignment));
  });
}

async function vpNewAssignment() {
  if (!vpState.currentSet) return;
  const value = await inputDialog({
    title: '適用ルールを追加',
    message: 'URLにこの文字列が含まれるとき、このセットを自動選択します。',
    placeholder: '例: /checkout',
    confirmLabel: '追加',
    validate: (v) => v ? null : 'URLのパターンを入力してください。',
  });
  if (!value) return;
  try {
    await vpApi(`/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/assignments`, {
      method: 'POST',
      body: JSON.stringify({ rule: { condition: { field: 'url', operator: 'contains', value } }, priority: 50, enabled: true }),
    });
    const data = await vpApi(`/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/assignments`);
    vpState.assignments = data.assignments || [];
    vpRenderAssignments();
    vpFeedback('適用ルールを追加しました。');
  } catch (error) { vpFeedback(error.message, 'error'); }
}

async function vpDeleteAssignment(assignmentId) {
  try {
    await vpApi(`/api/viewpoint-assignments/${encodeURIComponent(assignmentId)}`, { method: 'DELETE' });
    vpState.assignments = vpState.assignments.filter((item) => item.id !== assignmentId);
    vpRenderAssignments();
    vpFeedback('適用ルールを削除しました。');
  } catch (error) { vpFeedback(error.message, 'error'); }
}

/* ── セット CRUD ── */
async function vpNewSet() {
  const name = await inputDialog({
    title: '観点セットを作成',
    message: '新しい観点セットの名前を入力してください。',
    placeholder: '例: ECサイト向け観点セット',
    confirmLabel: '作成',
    validate: (v) => v ? null : 'セット名を入力してください。',
  });
  if (!name?.trim()) return;
  try {
    const data = await vpApi('/api/viewpoint-sets', {
      method: 'POST', body: JSON.stringify({ name: name.trim(), description: '', priority: 0 }),
    });
    await vpRefreshSetsOnly();
    await vpSelectSet(data.set.id, { skipDirtyCheck: true });
    vpFeedback('観点セットを作成しました。');
  } catch (error) { vpFeedback(error.message, 'error'); }
}

async function vpEditSet() {
  if (!vpState.currentSet) return;
  const description = await inputDialog({
    title: 'セット設定',
    message: `「${vpState.currentSet.name}」の説明を入力してください。`,
    placeholder: 'このセットの用途や対象範囲を入力',
    defaultValue: vpState.currentSet.description || '',
    confirmLabel: '保存',
  });
  if (description === null) return;
  const priorityStr = await inputDialog({
    title: '適用優先度',
    message: '数値が大きいほど優先してAutoRunで選択されます（既定: 0）。',
    placeholder: '0',
    defaultValue: String(vpState.currentSet.priority || 0),
    confirmLabel: '保存',
    validate: (v) => Number.isFinite(Number(v)) ? null : '数値を入力してください。',
  });
  if (priorityStr === null) return;
  try {
    await vpApi(`/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}`, {
      method: 'PATCH', body: JSON.stringify({ revision: vpState.currentSet.revision, description, priority: Number(priorityStr) || 0 }),
    });
    await vpRefreshSetsOnly();
    vpFeedback('セット設定を保存しました。');
  } catch (error) { vpFeedback(error.message, 'error'); }
}

async function vpDeleteSet() {
  if (!vpState.currentSet) return;
  const target = vpState.currentSet;
  const confirmed = await confirmDialog({
    title: '観点セットを削除しますか？',
    message: `「${target.name}」を一覧から削除します。公開履歴は保持され、直後なら元に戻せます。`,
    confirmLabel: '削除', danger: true,
  });
  if (!confirmed) return;
  try {
    await vpApi(`/api/viewpoint-sets/${encodeURIComponent(target.id)}`, { method: 'DELETE' });
    vpState.lastDeleted = { type: 'set', id: target.id };
    vpState.currentSet = null;
    await loadViewpointManager();
    vpFeedback('観点セットを削除しました。', 'success', { label: '元に戻す', handler: vpUndoDelete });
  } catch (error) { vpFeedback(error.message, 'error'); }
}

/* ── CSV ── */
function vpExportCsv() {
  if (!vpState.currentSet || !vpState.currentVersion) return;
  window.location.href = `/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/export?version=${vpState.currentVersion.version_number}`;
}

async function vpImportCsv(file) {
  if (!file || !vpState.currentSet) return;
  const form = new FormData();
  form.append('file', file);
  try {
    const data = await vpApi(`/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/import`, { method: 'POST', body: form });
    vpState.tab = 'draft';
    vpSyncTabs();
    await vpSelectSet(vpState.currentSet.id, { skipDirtyCheck: true });
    vpFeedback(`${data.result.imported}件を下書きへ取り込みました。`);
  } catch (error) { vpFeedback(error.message, 'error'); }
  finally { document.getElementById('vp-csv-import').value = ''; }
}

/* ── タブ同期 ── */
function vpSyncTabs() {
  document.querySelectorAll('[data-vp-tab]').forEach((button) => {
    const active = button.dataset.vpTab === vpState.tab;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-selected', String(active));
  });
}

async function vpSwitchTab(tab) {
  if (tab === vpState.tab || !(await vpMaybeDiscard())) return;
  await vpCloseEditor({ force: true, restore: false });
  vpState.tab = tab;
  vpState.selectedItem = null;
  vpState.selectedIds.clear();
  vpSyncTabs();
  await vpLoadCurrentTab();
}

/* ── ダーティ管理 ── */
async function vpMaybeDiscard() {
  if (!vpState.dirty) return true;
  const discard = await confirmDialog({
    title: '未保存の変更があります',
    message: '編集を続けるか、保存していない変更を破棄してください。',
    confirmLabel: '変更を破棄', cancelLabel: '編集を続ける', danger: true,
  });
  if (discard) vpState.dirty = false;
  return discard;
}

function vpMarkDirty(event) {
  if (vpState.tab !== 'draft' || !vpState.selectedItem) return;
  vpState.dirty = true;
  if (event?.target?.id) {
    event.target.removeAttribute('aria-invalid');
    const fieldError = document.getElementById(`${event.target.id}-error`);
    if (fieldError) fieldError.hidden = true;
  }
  const conflictPanel = document.getElementById('vp-conflict-panel');
  if (conflictPanel) conflictPanel.hidden = true;
  vpState.conflict = null;
  vpSetEditorState('dirty', '未保存', '保存していない変更があります');
  vpUpdateSectionStates();
}

/* ── イベント登録 ── */
document.getElementById('vp-feedback-close')?.addEventListener('click', vpClearFeedback);
document.getElementById('vp-new-set')?.addEventListener('click', vpNewSet);
document.getElementById('vp-edit-set')?.addEventListener('click', vpEditSet);
document.getElementById('vp-delete-set')?.addEventListener('click', vpDeleteSet);
document.getElementById('vp-new-assignment')?.addEventListener('click', vpNewAssignment);
document.getElementById('vp-add-viewpoint')?.addEventListener('click', () => vpNewItem());
document.getElementById('vp-editor-form')?.addEventListener('submit', vpSaveItem);
document.getElementById('vp-delete-item')?.addEventListener('click', vpDeleteItem);
document.getElementById('vp-discard-item')?.addEventListener('click', () => {
  vpState.dirty = false;
  vpCloseEditor({ force: true });
});
document.getElementById('vp-editor-close')?.addEventListener('click', () => vpCloseEditor());
document.getElementById('vp-create-next-draft')?.addEventListener('click', vpCreateNextDraft);
document.getElementById('vp-conflict-reload')?.addEventListener('click', vpResolveConflictReload);
document.getElementById('vp-conflict-reapply')?.addEventListener('click', vpResolveConflictReapply);
document.getElementById('vp-publish')?.addEventListener('click', vpPublish);
document.getElementById('vp-csv-export')?.addEventListener('click', vpExportCsv);
document.getElementById('vp-csv-import')?.addEventListener('change', (event) => vpImportCsv(event.target.files?.[0]));
document.getElementById('vp-generate-proposals')?.addEventListener('click', vpGenerateProposals);
document.getElementById('vp-clear-selection')?.addEventListener('click', () => { vpState.selectedIds.clear(); vpRenderItems(); });
document.querySelectorAll('[data-vp-bulk]').forEach((button) => button.addEventListener('click', () => vpBulkApply(button.dataset.vpBulk)));
document.querySelectorAll('[data-vp-tab]').forEach((button) => button.addEventListener('click', () => vpSwitchTab(button.dataset.vpTab)));

// ツリーパネル
document.getElementById('vp-add-folder')?.addEventListener('click', vpNewFolder);
document.getElementById('vp-tree-all-btn')?.addEventListener('click', () => {
  vpState.currentFolder = null;
  vpRenderTree();
  vpRenderItems();
  vpUpdateBreadcrumb();
});

// テンプレートメニュー（一覧は開いたタイミングで /api/viewpoint-templates から取得）
const templateMenu = document.getElementById('vp-template-menu');
document.getElementById('vp-tree-template-btn')?.addEventListener('click', async () => {
  if (!templateMenu) return;
  const opening = templateMenu.hidden;
  templateMenu.hidden = !templateMenu.hidden;
  if (opening) {
    vpRenderTemplateMenu(await vpFetchTemplates());
  }
});
// テンプレート項目はメニュー開閉のたびに再生成されるため、静的な querySelectorAll
// ではなくイベント委譲で拾う。
templateMenu?.addEventListener('click', (event) => {
  const button = event.target.closest('[data-template]');
  if (!button) return;
  templateMenu.hidden = true;
  vpLoadTemplate(button.dataset.template);
});
document.addEventListener('click', (event) => {
  if (templateMenu && !event.target.closest('#vp-tree-template-btn') && !event.target.closest('#vp-template-menu')) {
    templateMenu.hidden = true;
  }
});

// フィルター
['vp-search', 'vp-filter-risk', 'vp-filter-automation', 'vp-filter-state'].forEach((id) => {
  document.getElementById(id)?.addEventListener(id === 'vp-search' ? 'input' : 'change', vpRenderItems);
});

// エディタ
document.getElementById('vp-editor-form')?.addEventListener('input', vpMarkDirty);
document.getElementById('vp-rule-operator')?.addEventListener('change', (event) => {
  const valueInput = document.getElementById('vp-rule-value');
  if (valueInput) valueInput.disabled = event.target.value === 'present';
  vpMarkDirty(event);
});
document.querySelectorAll('[data-vp-section]').forEach((button) => {
  button.addEventListener('click', () => {
    document.getElementById(button.dataset.vpSection)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    vpSyncSectionNav(button.dataset.vpSection);
  });
});
document.getElementById('vp-editor-form')?.addEventListener('scroll', vpHandleEditorScroll, { passive: true });
document.getElementById('vp-editor-overlay')?.addEventListener('keydown', vpHandleEditorKeydown);
window.addEventListener('beforeunload', (event) => {
  if (!vpState.dirty) return;
  event.preventDefault();
  event.returnValue = '';
});
