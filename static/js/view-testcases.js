// ---- テストケース専用ビュー ----
let _tcDomainsLoaded = false;
let _tcReturnView = '';
let _tcPendingPresetDomain = '';

function tcNavigateFromApproval(domain) {
  _tcReturnView = 'auto-run';
  _tcPendingPresetDomain = domain || '';
  switchView('testcases');
  loadTestcasesSites(true, domain);
  _tcPendingPresetDomain = '';
}

function tcOnEnterView() {
  const banner = document.getElementById('tc-back-banner');
  if (banner) banner.hidden = !_tcReturnView;
  if (!_tcPendingPresetDomain) loadTestcasesSites(false);
}

async function loadTestcasesSites(force, presetDomain) {
  const select = document.getElementById('tc-domain-select');
  if (!select) return;
  if (_tcDomainsLoaded && !force) {
    if (select.value) await loadTestcasesData(select.value);
    return;
  }
  setTcStatus('解析済みサイトを読み込んでいます。');
  try {
    const res = await fetch('/api/history');
    const data = await res.json();
    const items = data.items || [];
    const previous = select.value;
    select.innerHTML = '<option value="">解析済みサイトを選択</option>' +
      items.map(it => `<option value="${escHtml(it.domain)}">${escHtml(it.domain)}</option>`).join('');
    const target = presetDomain || (items.some(it => it.domain === previous) ? previous : (items[0] && items[0].domain) || '');
    if (target) select.value = target;
    _tcDomainsLoaded = true;
    if (select.value) {
      await loadTestcasesData(select.value);
    } else {
      setTcStatus('解析済みサイトがありません。');
      document.getElementById('tc-content').innerHTML = '<div class="empty">解析済みサイトがありません。</div>';
    }
  } catch (e) {
    setTcStatus('サイト一覧の読み込みに失敗しました。', true);
  }
}

function setTcStatus(message, isError) {
  const el = document.getElementById('tc-status');
  if (!el) return;
  el.textContent = message || '';
  el.classList.toggle('input-field-message-error', !!isError);
}

async function loadTestcasesData(domain) {
  if (!domain) return;
  setTcStatus('テストケースを読み込んでいます。');
  try {
    const res = await fetch('/api/testcases?domain=' + encodeURIComponent(domain));
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'テストケースを取得できませんでした');
    renderTestcases(data);
    setTcStatus(`${data.count || 0}件のテストケースを読み込みました。`);
  } catch (e) {
    document.getElementById('tc-content').innerHTML = `<div class="empty">${escHtml(e.message)}</div>`;
    setTcStatus(e.message, true);
  }
}

function renderTestcases(data) {
  const cases = data.cases || [];
  const content = document.getElementById('tc-content');
  if (content) {
    if (cases.length) {
      const rows = cases.map(c => `<tr>
        <td class="tc-id">${escHtml(c.test_id)}</td>
        <td>${escHtml(c.title)}</td>
        <td><ol class="tc-cell-list">${(c.preconditions || []).map(p => `<li>${escHtml(p)}</li>`).join('')}</ol></td>
        <td><ol class="tc-cell-list">${(c.steps || []).map(s => `<li>${escHtml(s)}</li>`).join('')}</ol></td>
        <td>${escHtml(c.expected_result || '')}</td>
        <td>${escHtml(c.automation_status || '')}</td>
      </tr>`).join('');
      content.innerHTML = `<table class="ov-screens tc-table"><thead><tr>
        <th>ID</th><th>タイトル</th><th>前提条件</th><th>手順</th><th>期待結果</th><th>自動化</th>
      </tr></thead><tbody>${rows}</tbody></table>`;
    } else {
      content.innerHTML = '<div class="empty">テストケースがありません。</div>';
    }
  }
  const outputsEl = document.getElementById('tc-output-links');
  if (outputsEl) {
    outputsEl.innerHTML = data.html_path
      ? `<div class="qa-output-item"><span class="qa-output-item-name">テストケースHTML</span><div class="qa-output-item-actions"><button class="qa-output-btn qa-preview-btn" data-path="${escHtml(data.html_path)}" data-label="テストケースHTML">プレビュー</button><a class="qa-output-btn" href="/download?path=${encodeURIComponent(data.html_path)}" download>DL</a></div></div>`
      : `<div class="qa-output-item is-missing"><span class="qa-output-item-name">テストケースHTML</span><span style="font-size:11px;color:var(--text-muted)">未生成</span></div>`;
  }
}

document.getElementById('tc-domain-select')?.addEventListener('change', (e) => loadTestcasesData(e.target.value));
document.getElementById('tc-back-btn')?.addEventListener('click', () => {
  const target = _tcReturnView || 'dashboard';
  _tcReturnView = '';
  switchView(target);
});
