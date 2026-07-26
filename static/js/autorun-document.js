// ====================== AutoRun: 文書駆動モード ======================
let _autorunReferenceDocs = [];
// 直近の実行条件。失敗・停止からのやり直しに使う。
let _autoRunLastPayload = null;

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

// 開始できない理由を1つだけ返す（無ければ空文字）。
// 押してから叱るのではなく、押す前に理由を見せるための判定。
function autorunStartBlockReason() {
  const url = (document.getElementById('autorun-url')?.value || '').trim();
  if (!url) return 'URLを入力すると開始できます。';
  const mode = _autorunMode();
  if (mode === 'document' && !_autorunReferenceDocs.length) {
    return '文書駆動では要件・仕様文書を1件以上追加してください。';
  }
  const criterion = document.getElementById('autorun-selection-criterion')?.value || '';
  const targetPageId = (document.getElementById('autorun-target-page-id')?.value || '').trim();
  if (mode === 'document' && criterion === 'reached_target' && !targetPageId) {
    return '到達する画面IDを入力してください。';
  }
  return '';
}

// 開始ボタンの活性と、その理由表示を同期する。
// 「押せるのに押すと失敗する」状態を作らない。
function autorunSyncStartButton() {
  const btn = document.getElementById('autorun-start-btn');
  if (!btn || btn.dataset.busy === '1') return;
  const reason = autorunStartBlockReason();
  btn.disabled = !!reason;
  const hint = document.getElementById('autorun-start-status');
  if (hint && !hint.dataset.sticky) {
    hint.textContent = reason;
    hint.classList.remove('input-field-message-error');
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
  if (btn) { btn.dataset.busy = '1'; btn.disabled = true; btn.textContent = '開始中…'; }
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
    // 失敗しても「最初から入力し直す」しか手が無かった。
    // 同じ条件で再実行できるよう、送った内容を保持する。
    _autoRunLastPayload = payload;
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
    if (btn) { delete btn.dataset.busy; btn.textContent = '開始'; }
    autorunSyncStartButton();
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

// 失敗・停止した実行を、同じ条件でやり直す。
// これが無いと復旧手段が「受付へ戻って全部入力し直す」しかなくなる。
async function autorunRetryLastRun() {
  if (!_autoRunLastPayload) {
    // 条件が分からないなら受付へ戻す（黙って何もしないより良い）。
    autorunReset();
    return;
  }
  const payload = _autoRunLastPayload;
  try {
    const response = await fetch('/api/autorun/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || '再実行に失敗しました');
    _autorunAttachJob(data.job_id);
  } catch (error) {
    autorunReset();
    autorunSetStartStatus(String(error), true);
  }
}
