// ====================== B: ファイルプレビューモーダル ======================
function openFilePreview(path, label) {
  const modal = document.getElementById('file-preview-modal');
  const body = document.getElementById('file-preview-body');
  const titleEl = document.getElementById('file-preview-title');
  const newtab = document.getElementById('file-preview-newtab');
  if (!modal || !body) return;
  titleEl.textContent = label || 'プレビュー';
  const previewUrl = '/preview?path=' + encodeURIComponent(path);
  newtab.href = previewUrl;
  // ローディング表示
  body.innerHTML = '<div class="file-preview-loading"><span class="spinner"></span><span>読み込み中…</span></div>';
  modal.classList.remove('hidden');
  const ext = path.split('.').pop().toLowerCase();
  if (ext === 'html' || ext === 'htm') {
    // HTMLはiframeでサンドボックス表示
    body.innerHTML = `<iframe src="${escHtml(previewUrl)}" title="${escHtml(label || 'プレビュー')}" sandbox="allow-scripts allow-same-origin"></iframe>`;
  } else if (ext === 'md') {
    // Markdown はレンダリングして表示する（記号だらけの生テキスト表示を解消）
    fetch(previewUrl)
      .then(r => { if (!r.ok) throw new Error('読み込み失敗'); return r.text(); })
      .then(text => {
        body.innerHTML = '<div class="md-preview">' + renderMarkdownLite(text) + '</div>';
      })
      .catch(() => {
        const pre = document.createElement('pre');
        pre.textContent = 'ファイルの読み込みに失敗しました。';
        body.innerHTML = '';
        body.appendChild(pre);
      });
  } else {
    // JSON / テキストはコードブロックで表示
    fetch(previewUrl)
      .then(r => { if (!r.ok) throw new Error('読み込み失敗'); return r.text(); })
      .then(text => {
        const pre = document.createElement('pre');
        pre.textContent = text; // textContent でXSSを完全回避
        body.innerHTML = '';
        body.appendChild(pre);
      })
      .catch(() => {
        const pre = document.createElement('pre');
        pre.textContent = 'ファイルの読み込みに失敗しました。';
        body.innerHTML = '';
        body.appendChild(pre);
      });
  }
}

function closeFilePreview() {
  const modal = document.getElementById('file-preview-modal');
  const body = document.getElementById('file-preview-body');
  if (!modal) return;
  modal.classList.add('hidden');
  if (body) body.innerHTML = '';
}

document.getElementById('file-preview-close').addEventListener('click', closeFilePreview);
document.getElementById('file-preview-overlay').addEventListener('click', closeFilePreview);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !document.getElementById('file-preview-modal')?.classList.contains('hidden')) {
    closeFilePreview();
  }
});

// B: プレビューボタンのイベント委譲（動的生成ボタン対応）
document.addEventListener('click', (e) => {
  const btn = e.target.closest('.qa-preview-btn');
  if (btn && btn.dataset.path) openFilePreview(btn.dataset.path, btn.dataset.label || 'プレビュー');
});
