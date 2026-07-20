// ====================== AutoRun: 文書駆動モード ======================
let _autorunReferenceDocs = [];

AUTORUN_STEP_MAP.generating_document_mbt = 'ars-qa';
AUTORUN_PHASE_LABELS.generating_document_mbt = '文書要件からテスト設計中…';
Object.assign(AUTORUN_OUTPUT_LABELS, {
  document_mbt_json: '文書駆動MBTモデル',
  document_candidates_json: '文書駆動Playwright候補',
  manual_procedures_md: '手動テスト手順（Markdown）',
  manual_procedures_xlsx: '手動テスト手順（Excel）',
  test_data_json: 'テストデータ（JSON）',
  test_data_csv: 'テストデータ（CSV）',
  validation_observations_json: '入力検証の観測結果',
});
Object.assign(AUTORUN_OUTPUT_CATEGORIES, {
  document_mbt_json: '設計',
  document_candidates_json: '設計',
  manual_procedures_md: '設計',
  manual_procedures_xlsx: '設計',
  test_data_json: '設計',
  test_data_csv: '設計',
  validation_observations_json: '実行',
});

function _autorunMode() {
  return document.querySelector('input[name="autorun-mode"]:checked')?.value || 'url';
}

function _autorunUpdateTargetField() {
  const field = document.getElementById('autorun-target-page-field');
  const criterion = document.getElementById('autorun-selection-criterion')?.value;
  if (field) field.hidden = criterion !== 'reached_target';
}

function _autorunUpdateMode() {
  const form = document.getElementById('autorun-form-area');
  const options = document.getElementById('autorun-document-options');
  const documentMode = _autorunMode() === 'document';
  if (options) options.hidden = !documentMode;
  if (form) form.classList.toggle('is-document-mode', documentMode);
  // 仕様3: どちらを選択したかを明示する
  const current = document.getElementById('autorun-mode-current');
  if (current) {
    current.textContent = documentMode
      ? '文書駆動を選択中 — 要件・仕様文書と実測画面を突き合わせます。'
      : 'URL駆動を選択中 — 実測した画面からテストを生成します。';
    current.classList.toggle('is-document', documentMode);
  }
  _autorunUpdateTargetField();
}

function _autorunSetReferenceDocStatus(message, isError) {
  const status = document.getElementById('autorun-reference-doc-status');
  if (!status) return;
  status.textContent = message || '';
  status.classList.toggle('input-field-message-error', !!(message && isError));
}

function _autorunRenderReferenceDocs() {
  const list = document.getElementById('autorun-reference-doc-list');
  if (!list) return;
  list.replaceChildren();
  _autorunReferenceDocs.forEach((doc, index) => {
    const item = document.createElement('li');
    const name = document.createElement('span');
    name.textContent = doc.name || '参考文書';
    name.title = name.textContent;
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'btn-outline-sm';
    remove.textContent = '削除';
    remove.addEventListener('click', () => {
      _autorunReferenceDocs.splice(index, 1);
      _autorunRenderReferenceDocs();
    });
    item.append(name, remove);
    list.appendChild(item);
  });
}

function _autorunDomainFromUrl(value) {
  try {
    return new URL(value).host;
  } catch (_error) {
    return '';
  }
}

async function _autorunUploadReferenceDocs(event) {
  const input = event.currentTarget;
  const files = [...(input.files || [])];
  input.value = '';
  if (!files.length) return;
  const url = (document.getElementById('autorun-url')?.value || '').trim();
  const domain = _autorunDomainFromUrl(url);
  if (!domain) {
    _autorunSetReferenceDocStatus('先に有効な対象URLを入力してください。', true);
    return;
  }
  const formData = new FormData();
  formData.append('domain', domain);
  files.forEach(file => formData.append('files', file));
  _autorunSetReferenceDocStatus('アップロード中…', false);
  input.disabled = true;
  try {
    const response = await fetch('/api/reference-docs', { method: 'POST', body: formData });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || 'アップロードに失敗しました');
    for (const saved of data.saved || []) {
      if (!_autorunReferenceDocs.some(doc => doc.path === saved.path)) {
        _autorunReferenceDocs.push(saved);
      }
    }
    _autorunRenderReferenceDocs();
    _autorunSetReferenceDocStatus(`${data.saved?.length || 0}件を追加しました。`, false);
  } catch (error) {
    _autorunSetReferenceDocStatus(error.message || 'アップロードに失敗しました。', true);
  } finally {
    input.disabled = false;
  }
}

async function autorunStart() {
  const url = (document.getElementById('autorun-url')?.value || '').trim();
  if (!url) { autorunSetStartStatus('URLを入力してください。', true); return; }

  const mode = _autorunMode();
  const selectionCriterion = document.getElementById('autorun-selection-criterion')?.value || 'vertex_coverage';
  const targetPageId = (document.getElementById('autorun-target-page-id')?.value || '').trim();
  if (mode === 'document' && !_autorunReferenceDocs.length) {
    autorunSetStartStatus('文書駆動では要件・仕様文書を1件以上追加してください。', true);
    return;
  }
  if (mode === 'document' && selectionCriterion === 'reached_target' && !targetPageId) {
    autorunSetStartStatus('到達する画面IDを入力してください。', true);
    return;
  }

  const depth = document.getElementById('autorun-depth')?.value || '5';
  const maxPages = document.getElementById('autorun-max-pages')?.value || '300';
  const viewpointSetId = document.getElementById('autorun-viewpoint-set')?.value || '';
  const btn = document.getElementById('autorun-start-btn');
  if (btn) { btn.disabled = true; btn.textContent = '開始中…'; }
  autorunSetStartStatus('', false);

  try {
    const payload = {
      url,
      depth: parseInt(depth),
      max_pages: parseInt(maxPages),
      viewpoint_set_id: viewpointSetId,
    };
    if (mode === 'document') {
      Object.assign(payload, {
        mode,
        reference_docs: _autorunReferenceDocs.map(doc => doc.path),
        selection_criterion: selectionCriterion,
        target_page_id: targetPageId,
        observe_validation: !!document.getElementById('autorun-observe-validation')?.checked,
      });
    }
    const response = await fetch('/api/autorun/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || '開始に失敗しました');
    _autorunAttachJob(data.job_id);
  } catch (error) {
    autorunSetStartStatus(String(error), true);
    if (btn) { btn.disabled = false; btn.textContent = '開始'; }
  }
}

function _autorunResetDocumentMode() {
  const urlMode = document.getElementById('autorun-mode-url');
  if (urlMode) urlMode.checked = true;
  _autorunReferenceDocs = [];
  _autorunRenderReferenceDocs();
  _autorunSetReferenceDocStatus('', false);
  const criterion = document.getElementById('autorun-selection-criterion');
  if (criterion) criterion.value = 'vertex_coverage';
  const target = document.getElementById('autorun-target-page-id');
  if (target) target.value = '';
  const observe = document.getElementById('autorun-observe-validation');
  if (observe) observe.checked = false;
  _autorunUpdateMode();
}

document.querySelectorAll('input[name="autorun-mode"]').forEach(input => {
  input.addEventListener('change', _autorunUpdateMode);
});
document.getElementById('autorun-selection-criterion')?.addEventListener('change', _autorunUpdateTargetField);
document.getElementById('autorun-reference-doc-input')?.addEventListener('change', _autorunUploadReferenceDocs);
_autorunUpdateMode();
