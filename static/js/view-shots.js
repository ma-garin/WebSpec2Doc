// ---- スクリーンショット一覧 ----
function renderShots() {
  if (!reportJson) {
    resultHero.innerHTML = '<div class="hero-msg">スクリーンショットの対応情報がありません。</div>';
    return;
  }
  const pageIds = new Set((reportJson.screens || []).map(s => s.page_id));
  const shots = (resultData.screenshots || []).filter(p => pageIds.has(p.split('/').pop().replace(/\.png$/, '')));
  if (!shots.length) {
    resultHero.innerHTML = '<div class="hero-msg">スクリーンショットがありません。</div>';
    return;
  }
  const items = shots.map(p => {
    const name = p.split('/').pop();
    const src = `/preview?path=${encodeURIComponent(p)}`;
    return `<figure class="shots-item"><img src="${escHtml(src)}" loading="lazy" alt="${escHtml(name)}" class="shots-thumb" onclick="openLightbox('${escHtml(src)}')" /><figcaption>${escHtml(name)}</figcaption></figure>`;
  }).join('');
  resultHero.innerHTML = '<div class="shots-grid">' + items + '</div>';
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
