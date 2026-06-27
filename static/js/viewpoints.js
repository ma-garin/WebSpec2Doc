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
};

const VP_AUTOMATION_LABELS = {
  automated: '自動',
  semi_automated: '半自動',
  manual: '手動',
};

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
    else vpRenderEmpty('観点セットがありません。「新規セット」から作成してください。');
    vpState.booted = true;
  } catch (error) {
    vpFeedback(`観点管理を読み込めません: ${error.message}`, 'error');
    vpRenderEmpty('観点DBを読み込めませんでした。再試行してください。');
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
  document.getElementById('vp-set-summary').textContent = `アプリケーション合計 ${vpState.sets.length}セット / 観点 ${total}件`;
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

async function vpLoadCurrentTab() {
  const isProposal = vpState.tab === 'proposals';
  const isHistory = vpState.tab === 'history';
  document.getElementById('vp-standard-toolbar').hidden = isProposal || isHistory;
  document.getElementById('vp-proposal-toolbar').hidden = !isProposal;
  document.getElementById('vp-publish').hidden = vpState.tab !== 'draft';
  document.getElementById('vp-new-item').hidden = vpState.tab !== 'draft';
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
    vpRenderEmpty(vpState.tab === 'published' ? '公開版はまだありません。' : '下書きを作成できません。');
    return;
  }
  const data = await vpApi(
    `/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/versions/${version.version_number}/items`,
  );
  vpState.currentVersion = data.version;
  vpState.items = data.items || [];
  vpPopulateCategoryFilter();
  vpRenderItems();
}

async function vpRefreshSetsOnly() {
  const data = await vpApi('/api/viewpoint-sets');
  vpState.sets = data.sets || [];
  vpState.currentSet = vpState.sets.find((item) => item.id === vpState.currentSet?.id) || null;
  vpRenderSets();
}

function vpFilteredItems() {
  const query = (document.getElementById('vp-search')?.value || '').trim().toLowerCase();
  const category = document.getElementById('vp-filter-category')?.value || '';
  const risk = document.getElementById('vp-filter-risk')?.value || '';
  const automation = document.getElementById('vp-filter-automation')?.value || '';
  const state = document.getElementById('vp-filter-state')?.value || '';
  return vpState.items.filter((item) => {
    const haystack = [item.name, item.category, item.purpose, ...(item.tags || [])].join(' ').toLowerCase();
    return (!query || haystack.includes(query))
      && (!category || item.category === category)
      && (!risk || String(item.risk_weight) === risk)
      && (!automation || item.automation === (automation === 'human' ? 'manual' : automation))
      && (!state || (state === 'enabled') === !!item.enabled);
  });
}

function vpPopulateCategoryFilter() {
  const select = document.getElementById('vp-filter-category');
  if (!select) return;
  const current = select.value;
  const categories = [...new Set(vpState.items.map((item) => item.category).filter(Boolean))].sort();
  select.innerHTML = '<option value="">カテゴリ</option>' + categories.map((value) => `<option value="${escHtml(value)}">${escHtml(value)}</option>`).join('');
  if (categories.includes(current)) select.value = current;
  const datalist = document.getElementById('vp-category-datalist');
  if (datalist) {
    while (datalist.firstChild) datalist.removeChild(datalist.firstChild);
    categories.forEach((cat) => {
      const opt = document.createElement('option');
      opt.value = cat;
      datalist.appendChild(opt);
    });
  }
}

function vpRenderItems() {
  const container = document.getElementById('vp-list-content');
  if (!container) return;
  const items = vpFilteredItems();
  document.getElementById('vp-item-count').textContent = `${items.length}件`;
  document.getElementById('vp-list-title').textContent = vpState.tab === 'published' ? '公開中の観点' : '観点一覧';
  if (!items.length) {
    vpRenderEmpty(vpState.items.length ? '条件に一致する観点がありません。' : 'この版には観点がありません。');
    vpUpdateBulkbar();
    return;
  }
  const rows = items.map((item) => {
    const checked = vpState.selectedIds.has(item.id) ? ' checked' : '';
    const active = vpState.selectedItem?.id === item.id ? ' class="is-active"' : '';
    const inherited = item.inherited ? '<span class="vp-inherited">継承</span>' : '';
    return `<tr${active} data-vp-item-id="${escHtml(item.id)}" tabindex="0" aria-label="${escHtml(item.name)}を編集">
      <td class="vp-check-col"><input type="checkbox" data-vp-check="${escHtml(item.id)}" aria-label="${escHtml(item.name)}を選択"${checked}></td>
      <td class="vp-name-col"><span class="vp-item-name">${escHtml(item.name)}${inherited}</span><span class="vp-item-tags">${escHtml((item.tags || []).join(' / '))}</span></td>
      <td class="vp-category-col">${escHtml(item.category)}</td>
      <td class="vp-risk-col"><span class="vp-risk" data-risk="${Number(item.risk_weight)}">${Number(item.risk_weight)}</span></td>
      <td class="vp-auto-col"><span class="vp-automation" data-value="${escHtml(item.automation)}">${escHtml(VP_AUTOMATION_LABELS[item.automation] || item.automation)}</span></td>
      <td class="vp-state-col"><span class="vp-status${item.enabled ? '' : ' is-disabled'}">${item.enabled ? '有効' : '無効'}</span></td>
    </tr>`;
  }).join('');
  container.innerHTML = `<table class="vp-table"><thead><tr>
    <th class="vp-check-col"><input type="checkbox" id="vp-check-all" aria-label="表示中の観点をすべて選択"></th>
    <th>観点</th><th class="vp-category-col">カテゴリ</th><th class="vp-risk-col">リスク</th><th class="vp-auto-col">自動化</th><th class="vp-state-col">状態</th>
  </tr></thead><tbody>${rows}</tbody></table>`;
  container.querySelectorAll('tr[data-vp-item-id]').forEach((row) => {
    row.addEventListener('click', (event) => {
      if (event.target.matches('input[type="checkbox"]')) return;
      vpSelectItem(row.dataset.vpItemId, row);
    });
    row.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      vpSelectItem(row.dataset.vpItemId, row);
    });
  });
  container.querySelectorAll('[data-vp-check]').forEach((checkbox) => {
    checkbox.addEventListener('change', () => vpToggleSelection(checkbox.dataset.vpCheck, checkbox.checked));
  });
  document.getElementById('vp-check-all')?.addEventListener('change', (event) => {
    items.forEach((item) => event.target.checked ? vpState.selectedIds.add(item.id) : vpState.selectedIds.delete(item.id));
    vpRenderItems();
  });
  vpUpdateBulkbar();
}

function vpRenderEmpty(message) {
  const container = document.getElementById('vp-list-content');
  if (container) container.innerHTML = `<div class="vp-empty">${escHtml(message)}</div>`;
  document.getElementById('vp-item-count').textContent = '0件';
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
  document.getElementById('vp-selected-count').textContent = `${count}件を選択`;
}


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

async function vpBulkApply(action) {
  const changes = {};
  if (action === 'enable') changes.enabled = true;
  if (action === 'disable') changes.enabled = false;
  if (action === 'tag') {
    const existingTags = [...new Set(vpState.items.flatMap(item => item.tags || []).filter(Boolean))].sort();
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
    const categories = [...new Set(vpState.items.map(item => item.category).filter(Boolean))].sort();
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

function vpRenderHistory() {
  const container = document.getElementById('vp-list-content');
  document.getElementById('vp-list-title').textContent = '変更履歴';
  document.getElementById('vp-item-count').textContent = `${vpState.versions.length}版`;
  const statusLabel = { draft: '下書き', published: '公開中', archived: 'アーカイブ' };
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

async function vpLoadProposals() {
  document.getElementById('vp-list-title').textContent = 'AI提案';
  try {
    const data = await vpApi(`/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/proposals`);
    vpState.aiAvailable = !!data.ai_available;
    document.getElementById('vp-generate-proposals').disabled = !vpState.aiAvailable;
    document.getElementById('vp-generate-proposals').textContent = vpState.aiAvailable ? 'AIに提案を依頼' : 'OpenAI設定が必要';
    const proposals = data.proposals || [];
    document.getElementById('vp-item-count').textContent = `${proposals.length}件`;
    const container = document.getElementById('vp-list-content');
    if (!proposals.length) return vpRenderEmpty('AI提案はまだありません。既存観点を確認したうえで提案を依頼できます。');
    const itemsByKey = Object.fromEntries(vpState.items.map(i => [i.persistent_key, i.name]));
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
  const priority = Number(priorityStr) || 0;
  try {
    await vpApi(`/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}`, {
      method: 'PATCH', body: JSON.stringify({ revision: vpState.currentSet.revision, description, priority }),
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
  document.getElementById('vp-conflict-panel').hidden = true;
  vpState.conflict = null;
  vpSetEditorState('dirty', '未保存', '保存していない変更があります');
  vpUpdateSectionStates();
}

document.getElementById('vp-feedback-close')?.addEventListener('click', vpClearFeedback);
document.getElementById('vp-new-set')?.addEventListener('click', vpNewSet);
document.getElementById('vp-edit-set')?.addEventListener('click', vpEditSet);
document.getElementById('vp-delete-set')?.addEventListener('click', vpDeleteSet);
document.getElementById('vp-new-assignment')?.addEventListener('click', vpNewAssignment);
document.getElementById('vp-new-item')?.addEventListener('click', vpNewItem);
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
['vp-search', 'vp-filter-category', 'vp-filter-risk', 'vp-filter-automation', 'vp-filter-state'].forEach((id) => {
  document.getElementById(id)?.addEventListener(id === 'vp-search' ? 'input' : 'change', vpRenderItems);
});
document.getElementById('vp-editor-form')?.addEventListener('input', vpMarkDirty);
document.getElementById('vp-rule-operator')?.addEventListener('change', (event) => {
  document.getElementById('vp-rule-value').disabled = event.target.value === 'present';
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
