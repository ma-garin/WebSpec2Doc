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
    return `<figure class="shots-item"><img src="${escHtml(src)}" loading="lazy" alt="${escHtml(name)}" class="shots-thumb" onclick="openLightbox('${escHtml(fullSrc)}')" /><figcaption>${escHtml(name)}</figcaption></figure>`;
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
