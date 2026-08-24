// ---- 画面別仕様（リデザイン：全幅スクショ・フォームカード・クリック展開テスト条件）----
function renderReport() {
  if (!reportJson || !(reportJson.screens || []).length) {
    resultHero.innerHTML = '<div class="hero-msg"><p>画面別仕様データ（report.json）がありません。</p></div>';
    return;
  }
  const screens = reportJson.screens;
  const pageIds = new Set(screens.map(s => s.page_id));
  const allScreenshots = resultData.screenshots || [];
  const allShots = allScreenshots.filter(p => pageIds.has(p.split('/').pop().replace(/\.png$/, '')));
  // ライトボックス拡大表示は全体スクリーンショット（{page_id}_full.png）があればそちらを使う
  // （ビューポートのみの画像を拡大すると画面が見切れる不具合の修正。view-shots.js と同じ方式）。
  const fullByPageId = {};
  allScreenshots.forEach(p => {
    const m = p.split('/').pop().match(/^(.+)_full\.png$/);
    if (m) fullByPageId[m[1]] = p;
  });
  // 遷移先/遷移元を「P003」等の内部IDのまま出さず画面名で表示するためのマップ
  const idToScreen = {};
  screens.forEach(s => { idToScreen[s.page_id] = s; });

  resultHero.innerHTML =
    '<div class="rpt-pane-wrap">' +
    '<div class="rpt-list" id="rpt-list"></div>' +
    '<div class="rpt-detail" id="rpt-detail"><p class="hero-msg" style="padding:24px">左の一覧から画面を選択してください。</p></div>' +
    '</div>';

  const list = document.getElementById('rpt-list');
  screens.forEach((sc, idx) => {
    const item = document.createElement('div');
    item.className = 'rpt-list-item' + (idx === 0 ? ' is-active' : '');
    item.dataset.pid = sc.page_id;
    const hasForm = (sc.forms || []).some(f => (f.fields || []).length > 0);
    item.innerHTML =
      `<strong>${escHtml(sc.page_id)}</strong>` +
      `<span>${escHtml(sc.title || '')}</span>` +
      (hasForm ? '<span style="font-size:10px;color:var(--primary);font-weight:700">フォームあり</span>' : '');
    item.addEventListener('click', () => {
      list.querySelectorAll('.rpt-list-item').forEach(el => el.classList.remove('is-active'));
      item.classList.add('is-active');
      renderReportDetail(sc, allShots, idToScreen, fullByPageId);
    });
    list.appendChild(item);
  });
  renderReportDetail(screens[0], allShots, idToScreen, fullByPageId);
}

// 証跡が無いとき、画像ブロックを黙って消さない。画面だけが出て証跡が無い状態は
// 「撮れていない」のか「表示できていない」のか利用者に区別が付かないため、理由を書く。
const _SHOT_MISSING_TEXT = {
  not_snapshotted: '実行回ごとの証跡保存を入れる前の実行のため、この回のスクリーンショットは残っていません。'
    + '最新の実行の画像を代わりに表示することはしません（別の実行の画面になるため）。',
  capture_failed: 'この画面のスクリーンショットを撮影できませんでした。'
    + '再解析すると取得できることがあります。',
  not_captured: 'この解析ではスクリーンショットが保存されていません。',
};

function _shotMissingHtml(pageId) {
  const reason = (typeof resultData === 'object' && resultData && resultData.screenshots_reason) || '';
  const text = _SHOT_MISSING_TEXT[reason] || _SHOT_MISSING_TEXT.capture_failed;
  return '<div class="rpt-shot-missing" role="status">'
    + `<strong>スクリーンショットがありません（${escHtml(pageId)}）</strong>`
    + `<span>${escHtml(text)}</span>`
    + '</div>';
}

function renderReportDetail(sc, allShots, idToScreen, fullByPageId) {
  const detail = document.getElementById('rpt-detail');
  if (!detail) return;

  const shotPath = allShots.find(p => p.split('/').pop().replace(/\.png$/, '') === sc.page_id);
  const shotSrc = shotPath ? `/preview?path=${encodeURIComponent(shotPath)}` : '';
  const fullPath = (fullByPageId || {})[sc.page_id];
  const lightboxSrc = fullPath ? `/preview?path=${encodeURIComponent(fullPath)}` : shotSrc;
  // 項目名クリックでスクショ上の位置を指すため、画像を相対配置のラッパで包む。
  // ハイライト枠は同じラッパ内に絶対配置する（report.html の #shot-<page_id> と同じ骨格）。
  const shotHtml = shotPath
    ? `<div class="rpt-shot-wrap" id="rpt-shot-wrap" style="position:relative;display:inline-block;max-width:100%">`
      + `<img src="${escHtml(shotSrc)}" class="rpt-screenshot" loading="lazy" alt="${escHtml(sc.page_id)}" onclick="openLightbox('${escHtml(lightboxSrc)}')" />`
      + `<div class="rpt-shot-hl" id="rpt-shot-hl" style="display:none;position:absolute;border:2px solid #DA1E28;`
      + `background:rgba(218,30,40,.14);border-radius:3px;pointer-events:none;transition:all .15s ease"></div>`
      + `</div><p class="rpt-screenshot-caption">クリックで全画面表示／項目名を押すと位置を表示</p>`
    : _shotMissingHtml(sc.page_id);

  // 「P003」等の内部IDのままでは分かりにくいため、可能な限り画面名で表示する
  const screenLabel = id => (idToScreen && idToScreen[id] && idToScreen[id].title) || id;
  const transTo = (sc.transitions && sc.transitions.to) || [];
  const transFrom = (sc.transitions && sc.transitions.from) || [];
  const transHtml = (transTo.length || transFrom.length)
    ? `<div class="rpt-transitions">遷移先: ${transTo.length ? transTo.map(id => escHtml(screenLabel(id))).join('、') : '—'} ／ 遷移元: ${transFrom.length ? transFrom.map(id => escHtml(screenLabel(id))).join('、') : '—'}</div>`
    : '';

  const nonEmptyForms = (sc.forms || []).filter(f => (f.fields || []).length > 0);
  let formsHtml = '';
  if (!nonEmptyForms.length) {
    // フォームがない場合でも見出し・ボタン・リンクを表示
    const headings = (sc.headings || []).filter(Boolean);
    const buttons = (sc.buttons || []).filter(Boolean);
    const links = (sc.transitions && sc.transitions.to || []).filter(Boolean);
    const rows = [
      ...headings.map(h => `<div class="rpt-element-row"><span class="rpt-element-kind">見出し</span><span class="rpt-element-val">${escHtml(h)}</span></div>`),
      ...buttons.map(b => `<div class="rpt-element-row"><span class="rpt-element-kind">ボタン</span><span class="rpt-element-val">${escHtml(b)}</span></div>`),
      ...links.map(l => `<div class="rpt-element-row"><span class="rpt-element-kind">遷移先</span><span class="rpt-element-val">${escHtml(l)}</span></div>`),
    ];
    formsHtml = '<div class="rpt-page-elements">' +
      '<div class="rpt-page-elements-title">ページ要素（フォームなし）</div>' +
      (rows.length ? rows.join('') : '<p style="color:var(--text-muted);font-size:12px;margin:0">解析可能な要素が見つかりませんでした。</p>') +
      '</div>';
  } else {
    formsHtml = nonEmptyForms.map((fm, fi) => {
      const fieldRows = (fm.fields || []).map(f => {
        const condCount = (f.test_conditions || []).length;
        const condHtml = condCount
          ? `<details class="rpt-cond-expand"><summary class="rpt-cond-summary">${condCount}件</summary><div class="rpt-cond-pills">${(f.test_conditions || []).map(c => `<span class="cond-pill ${condClass(c)}">${escHtml(c)}</span>`).join('')}</div></details>`
          : '—';
        // bbox を持つ項目だけ押せるようにする。持たない項目を押せるように
        // 見せると、押しても何も起きない（何が押せるか分からなくなる）。
        const bb = (f.evidence && f.evidence.bbox) || null;
        const nameLabel = escHtml(f.name || '(無名)');
        const nameCell = (Array.isArray(bb) && bb.length === 4)
          ? `<button type="button" class="rpt-field-locate" data-bbox="${escHtml(bb.join(','))}"`
            + ` title="スクリーンショット上の位置を表示します"`
            + ` style="all:unset;cursor:pointer;font-weight:600;color:var(--primary);text-decoration:underline dotted">`
            + `${nameLabel}</button>`
          : nameLabel;
        return `<tr>
          <td style="font-weight:600">${nameCell}</td>
          <td>${escHtml(f.field_type || '')}</td>
          <td style="text-align:center">${f.required ? '<span style="color:var(--critical);font-weight:700">●</span>' : ''}</td>
          <td style="font-size:11px">${escHtml(constraintText(f)) || '—'}</td>
          <td><code class="loc-hint">${escHtml((f.locators || [])[0] || '')}</code></td>
          <td>${condHtml}</td>
        </tr>`;
      }).join('');
      return `<div class="rpt-form-card">
        <div class="rpt-form-card-header">
          フォーム ${fi + 1}
          <span class="rpt-form-card-method">${escHtml(fm.method || 'get')}</span>
          <span style="font-weight:400;margin-left:4px">${escHtml(fm.action || '')}</span>
        </div>
        <div style="overflow-x:auto">
          <table class="rpt-field-table">
            <thead><tr><th>項目名</th><th>型</th><th>必須</th><th>制約</th><th>ロケータ候補</th><th>テスト条件</th></tr></thead>
            <tbody>${fieldRows}</tbody>
          </table>
        </div>
      </div>`;
    }).join('');
  }

  detail.innerHTML =
    `<div class="rpt-detail-header" style="margin-bottom:12px">
      <h3 style="font-size:16px;margin-bottom:4px">${escHtml(sc.title || sc.page_id)}</h3>
      <code class="rpt-url">${escHtml(sc.url || '')}</code>
    </div>` +
    shotHtml + transHtml + formsHtml;

  _wireFieldLocate(detail);
}

// 項目名クリックでスクショ上の bbox をハイライトする。
// report.html には以前からある仕組み（html_reporter.py の _evidence_script）だが、
// アプリの「画面と仕様」タブには移植されておらず、押しても何も起きなかった。
function _wireFieldLocate(detail) {
  const hl = detail.querySelector('#rpt-shot-hl');
  const img = detail.querySelector('.rpt-screenshot');
  if (!hl || !img) return;

  // bbox はスクショの実寸（naturalWidth）基準。表示は縮小されるため必ず換算する。
  const place = (bbox) => {
    if (!img.naturalWidth || !img.naturalHeight) return false;
    const sx = img.clientWidth / img.naturalWidth;
    const sy = img.clientHeight / img.naturalHeight;
    hl.style.left = (bbox[0] * sx) + 'px';
    hl.style.top = (bbox[1] * sy) + 'px';
    hl.style.width = (bbox[2] * sx) + 'px';
    hl.style.height = (bbox[3] * sy) + 'px';
    hl.style.display = 'block';
    return true;
  };

  detail.querySelectorAll('.rpt-field-locate').forEach(btn => {
    btn.addEventListener('click', () => {
      const bbox = String(btn.dataset.bbox || '').split(',').map(Number);
      if (bbox.length !== 4 || bbox.some(n => !Number.isFinite(n))) return;
      // 画像がまだ読めていないと換算できない。読み込み完了を待って置き直す。
      if (!place(bbox)) {
        img.addEventListener('load', () => place(bbox), { once: true });
      }
      // 画面はスクロールさせない。押した項目の行から視線が外れ、
      // どの項目を見ていたか分からなくなるため（scrollIntoView は入れない）。
    });
  });
}

