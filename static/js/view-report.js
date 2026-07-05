// ---- 画面別仕様（リデザイン：全幅スクショ・フォームカード・クリック展開テスト条件）----
function renderReport() {
  if (!reportJson || !(reportJson.screens || []).length) {
    resultHero.innerHTML = '<div class="hero-msg"><p>画面別仕様データ（report.json）がありません。</p></div>';
    return;
  }
  const screens = reportJson.screens;
  const pageIds = new Set(screens.map(s => s.page_id));
  const allShots = (resultData.screenshots || []).filter(p => pageIds.has(p.split('/').pop().replace(/\.png$/, '')));
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
      renderReportDetail(sc, allShots, idToScreen);
    });
    list.appendChild(item);
  });
  renderReportDetail(screens[0], allShots, idToScreen);
}

function renderReportDetail(sc, allShots, idToScreen) {
  const detail = document.getElementById('rpt-detail');
  if (!detail) return;

  const shotPath = allShots.find(p => p.split('/').pop().replace(/\.png$/, '') === sc.page_id);
  const shotSrc = shotPath ? `/preview?path=${encodeURIComponent(shotPath)}` : '';
  const shotHtml = shotPath
    ? `<img src="${escHtml(shotSrc)}" class="rpt-screenshot" loading="lazy" alt="${escHtml(sc.page_id)}" onclick="openLightbox('${escHtml(shotSrc)}')" /><p class="rpt-screenshot-caption">クリックで全画面表示</p>`
    : '';

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
        return `<tr>
          <td style="font-weight:600">${escHtml(f.name || '(無名)')}</td>
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
}

