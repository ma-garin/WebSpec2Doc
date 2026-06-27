async function vpSelectItem(itemId, opener = null) {
  const item = vpState.items.find((row) => row.id === itemId);
  if (!item) return;
  vpState.selectedItem = { ...item };
  vpState.dirty = false;
  vpOpenEditor(item, { opener });
  vpRenderItems();
}

function vpSetEditorState(state, label, detail = '') {
  const badge = document.getElementById('vp-editor-state');
  const rail = document.getElementById('vp-rail-save');
  const railDetail = document.getElementById('vp-rail-save-detail');
  if (badge) {
    badge.dataset.state = state;
    badge.textContent = label;
  }
  if (rail) rail.textContent = label;
  if (railDetail) railDetail.textContent = detail || label;
}

function vpClearFieldErrors() {
  document.querySelectorAll('#vp-editor-form [aria-invalid="true"]').forEach((field) => field.removeAttribute('aria-invalid'));
  document.querySelectorAll('#vp-editor-form .vp-field-error').forEach((error) => {
    error.textContent = '';
    error.hidden = true;
  });
  document.getElementById('vp-editor-error').textContent = '';
}

function vpSetFieldError(fieldId, message) {
  const field = document.getElementById(fieldId);
  const error = document.getElementById(`${fieldId}-error`);
  field?.setAttribute('aria-invalid', 'true');
  if (error) {
    error.textContent = message;
    error.hidden = false;
  }
}

function vpValidateItem(payload, { focus = false } = {}) {
  vpClearFieldErrors();
  const invalid = [];
  if (!payload.name) {
    vpSetFieldError('vp-item-name', '名称を入力してください。');
    invalid.push('vp-item-name');
  }
  if (!payload.category) {
    vpSetFieldError('vp-item-category', 'カテゴリを入力してください。');
    invalid.push('vp-item-category');
  }
  const condition = payload.trigger_rule?.condition;
  if (condition && condition.operator !== 'present' && (condition.value === '' || condition.value === undefined)) {
    vpSetFieldError('vp-rule-value', '条件値を入力するか、「が存在」を選択してください。');
    invalid.push('vp-rule-value');
  }
  const duplicate = vpState.items.find((item) =>
    item.name.trim().toLowerCase() === payload.name.toLowerCase()
    && item.persistent_key !== vpState.selectedItem?.persistent_key
  );
  if (payload.name && duplicate) {
    vpSetFieldError('vp-item-name', `同名の観点「${duplicate.name}」があります。名称を変更してください。`);
    invalid.push('vp-item-name');
  }
  const validation = document.getElementById('vp-rail-validation');
  const validationDetail = document.getElementById('vp-rail-validation-detail');
  if (validation) {
    validation.className = invalid.length ? 'vp-rail-error' : 'vp-rail-ok';
    validation.textContent = invalid.length ? `! ${invalid.length}件の修正が必要` : '✓ 問題なし';
  }
  if (validationDetail) validationDetail.textContent = invalid.length ? '項目付近の案内に沿って修正してください' : '必須項目と条件式を確認済み';
  vpUpdateSectionStates();
  if (focus && invalid.length) document.getElementById(invalid[0])?.focus();
  return invalid.length === 0;
}

function vpUpdateSectionStates() {
  const definitions = {
    'vp-section-basic': Boolean(document.getElementById('vp-item-name')?.value.trim() && document.getElementById('vp-item-category')?.value.trim()),
    'vp-section-conditions': !document.getElementById('vp-rule-field')?.value || document.getElementById('vp-rule-operator')?.value === 'present' || Boolean(document.getElementById('vp-rule-value')?.value.trim()),
    'vp-section-checks': Boolean(document.getElementById('vp-item-purpose')?.value.trim() || document.getElementById('vp-item-checks')?.value.trim()),
    'vp-section-evidence': Boolean(document.getElementById('vp-item-standards')?.value.trim() || document.getElementById('vp-item-tags')?.value.trim()),
  };
  document.querySelectorAll('[data-vp-section]').forEach((button) => {
    const section = document.getElementById(button.dataset.vpSection);
    const hasError = Boolean(section?.querySelector('[aria-invalid="true"]'));
    const complete = definitions[button.dataset.vpSection];
    button.classList.toggle('is-error', hasError);
    button.classList.toggle('is-complete', !hasError && complete);
    const state = button.querySelector('[data-vp-section-state]');
    if (state) state.textContent = hasError ? 'エラー' : complete ? '✓ 完了' : '未完了';
  });
}

function vpUpdateEditorRail(item, readonly) {
  const version = vpState.currentVersion;
  document.getElementById('vp-rail-version').textContent = version ? `${version.status === 'published' ? '公開版' : '下書き'} v${version.version_number}` : '版情報なし';
  document.getElementById('vp-rail-version-detail').textContent = readonly ? '公開済みのため読み取り専用です' : '編集可能な下書きです';
  document.getElementById('vp-rail-inheritance').textContent = item.inherited ? '親セットから継承' : 'このセットで定義';
  document.getElementById('vp-rail-inheritance-detail').textContent = item.inherited ? '保存するとこのセットの上書きを作成します' : 'このセットの観点として保存します';
  document.getElementById('vp-rail-applicability').textContent = `適用ルール ${vpState.assignments.length}件`;
}

function vpFillEditor(item, { isNew = false } = {}) {
  const form = document.getElementById('vp-editor-form');
  document.getElementById('vp-editor-title').textContent = isNew ? '観点を追加' : item.name || '観点を編集';
  document.getElementById('vp-editor-context').textContent = vpState.currentSet?.name || '観点セット';
  document.getElementById('vp-item-id').value = item.id || '';
  document.getElementById('vp-item-name').value = item.name || '';
  document.getElementById('vp-item-category').value = item.category || '';
  document.getElementById('vp-item-purpose').value = item.purpose || '';
  document.getElementById('vp-item-checks').value = item.recommended_checks || '';
  document.getElementById('vp-item-risk').value = String(item.risk_weight || 3);
  document.getElementById('vp-item-automation').value = item.automation === 'manual' ? 'human' : (item.automation || 'human');
  document.getElementById('vp-item-standards').value = item.standards || '';
  document.getElementById('vp-item-tags').value = (item.tags || []).join(', ');
  document.getElementById('vp-item-enabled').checked = item.enabled !== false;
  const condition = item.trigger_rule?.condition || {};
  document.getElementById('vp-rule-field').value = condition.field || '';
  document.getElementById('vp-rule-operator').value = condition.operator || 'eq';
  document.getElementById('vp-rule-value').value = condition.value === undefined ? '' : String(condition.value);
  const readonly = vpState.tab !== 'draft';
  form.querySelectorAll('input,select,textarea').forEach((control) => { control.disabled = readonly; });
  document.getElementById('vp-rule-value').disabled = readonly || condition.operator === 'present';
  document.getElementById('vp-save-item').hidden = readonly;
  document.getElementById('vp-discard-item').hidden = readonly;
  document.getElementById('vp-delete-item').hidden = readonly || isNew || !!item.inherited;
  document.getElementById('vp-create-next-draft').hidden = !readonly;
  document.getElementById('vp-conflict-panel').hidden = true;
  vpState.conflict = null;
  vpClearFieldErrors();
  vpUpdateEditorRail(item, readonly);
  vpSetEditorState(readonly ? 'readonly' : isNew ? 'dirty' : 'saved', readonly ? '読み取り専用' : isNew ? '未保存' : '保存済み', readonly ? '公開版は変更できません' : isNew ? '新しい観点はまだ保存されていません' : '変更はありません');
  vpUpdateSectionStates();
}

function vpOpenEditor(item, { isNew = false, opener = null } = {}) {
  const overlay = document.getElementById('vp-editor-overlay');
  const list = document.getElementById('vp-list-content');
  vpState.editorMode = vpState.tab === 'published' ? 'view' : isNew ? 'new' : 'edit';
  vpState.editorOpener = opener || document.activeElement;
  vpState.listScrollTop = list?.scrollTop || 0;
  vpFillEditor(item, { isNew });
  overlay.hidden = false;
  document.body.classList.add('vp-modal-open');
  document.getElementById('vp-editor-form').scrollTop = 0;
  vpSyncSectionNav('vp-section-basic');
  setTimeout(() => (isNew ? document.getElementById('vp-item-name') : document.getElementById('vp-editor-title'))?.focus(), 0);
}

async function vpCloseEditor({ force = false, restore = true, selectedId = '' } = {}) {
  const overlay = document.getElementById('vp-editor-overlay');
  if (!overlay || overlay.hidden) return true;
  if (!force && vpState.dirty) {
    const discard = await confirmDialog({
      title: '未保存の変更があります',
      message: '編集を続けるか、保存していない変更を破棄してください。',
      confirmLabel: '変更を破棄',
      cancelLabel: '編集を続ける',
      danger: true,
    });
    if (!discard) return false;
  }
  vpState.dirty = false;
  vpState.editorMode = 'closed';
  vpState.conflict = null;
  overlay.hidden = true;
  document.body.classList.remove('vp-modal-open');
  document.getElementById('vp-conflict-panel').hidden = true;
  if (restore) {
    const list = document.getElementById('vp-list-content');
    if (list) list.scrollTop = vpState.listScrollTop;
    const focusId = selectedId || vpState.selectedItem?.id;
    const target = focusId
      ? document.querySelector(`[data-vp-item-id="${CSS.escape(focusId)}"]`)
      : vpState.editorOpener;
    if (target && typeof target.focus === 'function') {
      if (selectedId && !target.getBoundingClientRect().height) target.scrollIntoView({ block: 'nearest' });
      target.focus();
    }
  }
  return true;
}

function vpNewItem() {
  if (vpState.tab !== 'draft') return;
  const item = {
    id: '', name: '', category: '', purpose: '', trigger_rule: {}, recommended_checks: '',
    risk_weight: 3, automation: 'manual', standards: 'ISO/IEC 25010:2023', tags: [], enabled: true,
    revision: 0,
  };
  vpState.selectedItem = item;
  vpState.dirty = true;
  vpOpenEditor(item, { isNew: true, opener: document.getElementById('vp-new-item') });
}

function vpCollectItem() {
  const field = document.getElementById('vp-rule-field').value;
  const operator = document.getElementById('vp-rule-operator').value;
  let value = document.getElementById('vp-rule-value').value.trim();
  if (field === 'has_forms' && operator !== 'present') value = value.toLowerCase() === 'true';
  const triggerRule = field
    ? { condition: { field, operator, ...(operator === 'present' ? {} : { value }) } }
    : {};
  return {
    persistent_key: vpState.selectedItem?.persistent_key,
    name: document.getElementById('vp-item-name').value.trim(),
    category: document.getElementById('vp-item-category').value.trim(),
    purpose: document.getElementById('vp-item-purpose').value.trim(),
    trigger_rule: triggerRule,
    recommended_checks: document.getElementById('vp-item-checks').value.trim(),
    risk_weight: Number(document.getElementById('vp-item-risk').value),
    automation: document.getElementById('vp-item-automation').value === 'human' ? 'manual' : document.getElementById('vp-item-automation').value,
    standards: document.getElementById('vp-item-standards').value.trim(),
    tags: document.getElementById('vp-item-tags').value.split(',').map((value) => value.trim()).filter(Boolean),
    enabled: document.getElementById('vp-item-enabled').checked,
    revision: vpState.selectedItem?.revision,
  };
}

async function vpSaveItem(event) {
  event?.preventDefault?.();
  const payload = vpCollectItem();
  if (!vpValidateItem(payload, { focus: true })) {
    vpSetEditorState('error', '検証エラー', '入力内容を修正してください');
    return;
  }
  const saveButton = document.getElementById('vp-save-item');
  saveButton.disabled = true;
  vpSetEditorState('saving', '保存中…', 'サーバーへ変更を送信しています');
  try {
    let data;
    const shouldCreate = !vpState.selectedItem?.id || vpState.selectedItem?.inherited;
    if (shouldCreate) {
      data = await vpApi(
        `/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/versions/${vpState.currentVersion.version_number}/items`,
        { method: 'POST', body: JSON.stringify(payload) },
      );
    } else {
      data = await vpApi(`/api/viewpoint-items/${encodeURIComponent(vpState.selectedItem.id)}`, {
        method: 'PATCH', body: JSON.stringify(payload),
      });
    }
    vpState.selectedItem = data.item;
    vpState.dirty = false;
    vpSetEditorState('saved', '保存完了', '下書きへ保存しました');
    await vpReloadItems();
    await vpCloseEditor({ force: true, selectedId: data.item.id });
    vpFeedback('下書きを保存しました');
  } catch (error) {
    if (error.status === 409) {
      vpState.conflict = error.details || {};
      const fields = Object.keys(vpState.conflict.diff || {});
      document.getElementById('vp-conflict-summary').textContent = fields.length
        ? `差分項目: ${fields.join('、')}。サーバー版を再読込するか、編集内容を最新revisionへ再適用してください。`
        : 'サーバー上の版が更新されています。再読込または再適用を選択してください。';
      document.getElementById('vp-conflict-panel').hidden = false;
      vpSetEditorState('conflict', '競合', '他の操作による更新を確認してください');
    } else {
      document.getElementById('vp-editor-error').textContent = error.message;
      vpSetEditorState('error', '保存失敗', '通信状態と入力内容を確認してください');
    }
  } finally {
    saveButton.disabled = false;
  }
}

async function vpReloadItems(selectedId = '') {
  const data = await vpApi(
    `/api/viewpoint-sets/${encodeURIComponent(vpState.currentSet.id)}/versions/${vpState.currentVersion.version_number}/items`,
  );
  vpState.currentVersion = data.version;
  vpState.items = data.items || [];
  vpPopulateCategoryFilter();
  if (selectedId) {
    const selected = vpState.items.find((item) => item.id === selectedId);
    if (selected) {
      vpState.selectedItem = selected;
      vpFillEditor(selected);
    }
  }
  vpRenderItems();
  await vpRefreshSetsOnly();
}

async function vpDeleteItem() {
  const item = vpState.selectedItem;
  if (!item?.id) return;
  const confirmed = await confirmDialog({
    title: '観点を削除しますか？',
    message: `「${item.name}」を下書きから削除します。公開履歴は保持されます。`,
    confirmLabel: '削除', danger: true,
  });
  if (!confirmed) return;
  try {
    await vpApi(`/api/viewpoint-items/${encodeURIComponent(item.id)}`, { method: 'DELETE' });
    vpState.lastDeleted = { type: 'item', id: item.id };
    vpState.selectedItem = null;
    await vpReloadItems();
    await vpCloseEditor({ force: true, restore: false });
    document.getElementById('vp-new-item')?.focus();
    vpFeedback('観点を削除しました。', 'success', { label: '元に戻す', handler: vpUndoDelete });
  } catch (error) { vpFeedback(error.message, 'error'); }
}

function vpResolveConflictReload() {
  const current = vpState.conflict?.current;
  if (!current) return;
  vpState.selectedItem = { ...current };
  vpState.dirty = false;
  vpFillEditor(current);
  vpSetEditorState('saved', '再読込済み', 'サーバー上の最新内容を表示しています');
}

async function vpResolveConflictReapply() {
  const current = vpState.conflict?.current;
  if (!current) return;
  vpState.selectedItem = { ...vpState.selectedItem, ...current };
  vpState.conflict = null;
  document.getElementById('vp-conflict-panel').hidden = true;
  await vpSaveItem();
}

async function vpCreateNextDraft() {
  const persistentKey = vpState.selectedItem?.persistent_key;
  await vpCloseEditor({ force: true, restore: false });
  vpState.tab = 'draft';
  vpSyncTabs();
  await vpLoadCurrentTab();
  const item = vpState.items.find((row) => row.persistent_key === persistentKey);
  if (item) {
    const row = document.querySelector(`[data-vp-item-id="${CSS.escape(item.id)}"]`);
    await vpSelectItem(item.id, row);
  } else {
    vpNewItem();
  }
}

function vpSyncSectionNav(sectionId) {
  document.querySelectorAll('[data-vp-section]').forEach((button) => {
    const active = button.dataset.vpSection === sectionId;
    button.classList.toggle('is-active', active);
    if (active) button.setAttribute('aria-current', 'true');
    else button.removeAttribute('aria-current');
  });
}

function vpHandleEditorScroll() {
  const form = document.getElementById('vp-editor-form');
  if (!form) return;
  const sections = [...form.querySelectorAll('.vp-form-section')];
  const current = sections.reduce((nearest, section) => {
    const distance = Math.abs(section.offsetTop - form.scrollTop - 18);
    return !nearest || distance < nearest.distance ? { id: section.id, distance } : nearest;
  }, null);
  if (current) vpSyncSectionNav(current.id);
}

function vpHandleEditorKeydown(event) {
  const overlay = document.getElementById('vp-editor-overlay');
  if (!overlay || overlay.hidden) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    event.stopPropagation();
    vpCloseEditor();
    return;
  }
  if (event.key !== 'Tab') return;
  const focusable = [...overlay.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')]
    .filter((element) => !element.hidden && element.offsetParent !== null);
  if (!focusable.length) {
    event.preventDefault();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
