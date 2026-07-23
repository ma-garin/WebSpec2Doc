// ---- スクリーンショット一覧 ----
function renderShots() {
  if (!reportJson) {
    resultHero.innerHTML = '<div class="hero-msg">スクリーンショットの対応情報がありません。</div>';
    return;
  }
  const pageIds = new Set((reportJson.screens || []).map(s => s.page_id));
  const allScreenshots = resultData.screenshots || [];
  const shots = allScreenshots.filter(p => pageIds.has(p.split('/').pop().replace(/\.png$/, '')));
  if (!shots.length) {
    resultHero.innerHTML = '<div class="hero-msg">スクリーンショットがありません。</div>';
    return;
  }
  // ギャラリー拡大表示は全体スクリーンショット（{page_id}_full.png）があればそちらを使う
  // （ビューポートのみの画像を拡大すると画面が見切れる不具合の修正）。無ければ従来通り。
  const fullByPageId = {};
  allScreenshots.forEach(p => {
    const m = p.split('/').pop().match(/^(.+)_full\.png$/);
    if (m) fullByPageId[m[1]] = p;
  });
  const items = shots.map(p => {
    const name = p.split('/').pop();
    const pageId = name.replace(/\.png$/, '');
    const src = `/preview?path=${encodeURIComponent(p)}`;
    const fullSrc = fullByPageId[pageId] ? `/preview?path=${encodeURIComponent(fullByPageId[pageId])}` : src;
    const exportPath = fullByPageId[pageId] || p;
    return `<figure class="shots-item">
      <label class="shots-select"><input type="checkbox" class="shots-select-cb" data-path="${escHtml(exportPath)}"></label>
      <img src="${escHtml(src)}" loading="lazy" alt="${escHtml(name)}" class="shots-thumb" onclick="openLightbox('${escHtml(fullSrc)}')" />
      <figcaption>${escHtml(name)}</figcaption>
    </figure>`;
  }).join('');
  resultHero.innerHTML =
    '<div class="shots-toolbar">' +
    '<button type="button" id="shots-select-all-btn" class="btn-outline-sm">全選択</button>' +
    '<button type="button" id="shots-select-none-btn" class="btn-outline-sm">全解除</button>' +
    '<button type="button" id="shots-export-btn" class="btn-outline-sm">選択をエクスポート (<span id="shots-select-count">0</span>)</button>' +
    '</div>' +
    '<div class="shots-grid">' + items + '</div>';
  _shotsWireToolbar();
}

// ---- ギャラリー一括エクスポート（チェックボックス選択→/download-zip） ----
function _shotsWireToolbar() {
  const checkboxes = () => Array.from(document.querySelectorAll('.shots-select-cb'));
  const countEl = document.getElementById('shots-select-count');
  const updateCount = () => {
    if (countEl) countEl.textContent = String(checkboxes().filter(cb => cb.checked).length);
  };
  checkboxes().forEach(cb => cb.addEventListener('change', updateCount));
  document.getElementById('shots-select-all-btn')?.addEventListener('click', () => {
    checkboxes().forEach(cb => { cb.checked = true; });
    updateCount();
  });
  document.getElementById('shots-select-none-btn')?.addEventListener('click', () => {
    checkboxes().forEach(cb => { cb.checked = false; });
    updateCount();
  });
  document.getElementById('shots-export-btn')?.addEventListener('click', () => {
    const paths = checkboxes().filter(cb => cb.checked).map(cb => cb.dataset.path);
    if (!paths.length || !activeDomain) return;
    const params = new URLSearchParams({ domain: activeDomain });
    paths.forEach(p => params.append('paths', p));
    window.open(`/download-zip?${params.toString()}`, '_blank');
  });
  updateCount();
}

// ---- ライトボックス ----
function openLightbox(src) {
  const lb = document.getElementById('lightbox');
  const img = document.getElementById('lightbox-img');
  if (!lb || !img) return;
  img.src = src;
  lb.style.display = 'flex';
  document.addEventListener('keydown', closeLightboxOnEsc);
}
function closeLightbox() {
  const lb = document.getElementById('lightbox');
  if (lb) lb.style.display = 'none';
  document.removeEventListener('keydown', closeLightboxOnEsc);
}
function closeLightboxOnEsc(e) { if (e.key === 'Escape') closeLightbox(); }
(function initLightbox() {
  const lb = document.getElementById('lightbox');
  if (!lb) return;
  lb.addEventListener('click', (e) => { if (e.target === lb) closeLightbox(); });
  document.getElementById('lightbox-close').addEventListener('click', closeLightbox);
})();
