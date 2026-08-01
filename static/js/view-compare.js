// ---- 現新比較ワークスペース ----
// 従来は comparison.html を iframe に埋めるだけで、画面ペアを選ぶ・差分を辿る・
// 根拠を見る、が画面上でできなかった。ここでその一連の操作を担う。
// データは GET /api/snapshot-comparison.json（ペア単位に整形済み）。

const CMP_CATEGORY_LABELS = {
  inoperable: '操作不可',
  incomprehensible: '理解不可能',
  text_garbled: '文字化け・意味消失',
  layout_broken: '表示崩れ',
  unclassified: '未分類（要確認）',
};
// severity は src/diff/differ.py の値（breaking / warning / info）。
// 画面には日本語で出すが、判定は必ずこの値で行う。
const CMP_SEVERITY_LABELS = { breaking: '高', warning: '中', info: '低' };
const CMP_SEVERITY_TOP = 'breaking';
// 比較できなかった画面。「指摘0件」と同じ見た目にしない。
const CMP_STATE_LABELS = { added: '追加', removed: '削除' };

const CMP = {
  domain: '',
  snapshots: [],
  from: '',
  to: '',
  data: null,
  selected: 0,      // 選択中のペア index
  filter: 'all',    // all | high | <category>
  loading: false,
  zoom: 100,        // 表示倍率（%）
  syncScroll: true, // 左右のスクロールを合わせる
  overlay: false,   // 重ね合わせ表示
};
const CMP_ZOOM_STEPS = [50, 75, 100, 150, 200];

function cmpPanel() { return document.getElementById('rp-compare'); }

// ---- 入口（results.js のタブ登録から呼ばれる） ----
// 描画関数は引数なしで呼ばれる規約（results.js:322-324）。ドメインは
// renderTimeline と同じく #r-domain から取る。
async function renderCompare() {
  const domain = document.getElementById('r-domain')?.textContent?.trim() || '';
  const panel = cmpPanel();
  if (!panel) return;
  if (!domain) {
    panel.innerHTML = '<div class="hero-msg">対象サイトが特定できませんでした。</div>';
    return;
  }
  // ドメインが変わったら前回の選択を持ち越さない（別サイトの2時点が残る）
  if (CMP.domain !== domain) { CMP.from = ''; CMP.to = ''; CMP.data = null; }
  CMP.domain = domain;
  panel.innerHTML = '<div class="hero-msg">スナップショットを読み込んでいます…</div>';
  try {
    const data = await fetch('/api/snapshots?domain=' + encodeURIComponent(domain)).then(r => r.json());
    // API は新しい順の {id, label, screens, ...}。古い順に直して「1つ前 → 最新」を既定にする。
    CMP.snapshots = (data.snapshots || []).slice().reverse();
  } catch (e) {
    panel.innerHTML = '<div class="hero-msg">スナップショット一覧を取得できませんでした。</div>';
    return;
  }
  if (CMP.snapshots.length < 2) {
    // 何が足りないかを書く。「比較できません」だけだと次に何をすればよいか分からない。
    panel.innerHTML = '<div class="hero-msg">比較には2時点以上のスナップショットが必要です。' +
      `現在 ${CMP.snapshots.length} 件です。再解析すると1件増えます。</div>`;
    return;
  }
  const last = CMP.snapshots.length - 1;
  CMP.from = CMP.from || CMP.snapshots[last - 1].id;
  CMP.to = CMP.to || CMP.snapshots[last].id;
  await cmpLoad();
}

async function cmpLoad() {
  const panel = cmpPanel();
  if (!panel || CMP.loading) return;
  CMP.loading = true;
  panel.innerHTML = '<div class="hero-msg">比較しています…（画面数によっては時間がかかります）</div>';
  try {
    const url = `/api/snapshot-comparison.json?domain=${encodeURIComponent(CMP.domain)}` +
      `&from=${encodeURIComponent(CMP.from)}&to=${encodeURIComponent(CMP.to)}`;
    const res = await fetch(url);
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || '比較に失敗しました');
    CMP.data = data;
    CMP.selected = 0;
    cmpRender();
  } catch (e) {
    panel.innerHTML = `<div class="hero-msg">比較に失敗しました: ${escHtml(e.message || e)}</div>`;
  } finally {
    CMP.loading = false;
  }
}

// ---- 描画 ----
function cmpRender() {
  const panel = cmpPanel();
  if (!panel || !CMP.data) return;
  panel.innerHTML =
    '<section class="cmp-card">' +
      cmpHead() +
      '<div class="cmp-layout">' + cmpRail() + cmpMain() + '</div>' +
    '</section>';
  cmpBind();
}

function cmpHead() {
  const c = CMP.data.counts || {};
  return '<header class="cmp-head">' +
    '<h3>現新比較</h3>' +
    '<p class="cmp-lede">画面対応・画面差分・仕様差分を同じ根拠で確認します。' +
    '比較できない対象は未確認として残します。</p>' +
    '<div class="cmp-context">' +
      `<b>比較対象</b><span class="cmp-date">${escHtml(CMP.data.from)}</span>` +
      '<span class="cmp-arrow">→</span>' +
      `<span class="cmp-date">${escHtml(CMP.data.to)}</span>` +
      `<span class="cmp-context-sum">対応 ${c.matched || 0} / ${c.pairs || 0}　` +
      `追加 ${c.added || 0}　削除 ${c.removed || 0}　指摘 ${c.findings || 0}</span>` +
      '<button type="button" class="btn-outline-sm" id="cmp-change-btn">比較条件を変更</button>' +
    '</div>' +
  '</header>';
}

function cmpRail() {
  const pairs = CMP.data.pairs || [];
  const rows = pairs.map((p, i) => {
    const badge = p.state === 'matched'
      ? (p.finding_count
        ? `<span class="cmp-badge cmp-cat-${escHtml(p.top_category)}">` +
          `${escHtml(CMP_CATEGORY_LABELS[p.top_category] || p.top_category)}</span>`
        : '<span class="cmp-badge cmp-none">変更なし</span>')
      : `<span class="cmp-badge cmp-unmatched">${escHtml(CMP_STATE_LABELS[p.state] || p.state)}</span>`;
    return `<button type="button" class="cmp-pair${i === CMP.selected ? ' is-active' : ''}" data-cmp-pair="${i}">` +
      `<span class="cmp-pair-title">${escHtml(p.title || p.old_page_id || p.new_page_id)}</span>` +
      `<span class="cmp-pair-url">${escHtml(p.url || '—')}</span>${badge}</button>`;
  }).join('');
  return '<aside class="cmp-rail">' +
    `<div class="cmp-rail-head">画面対応<span>${pairs.length} 件</span></div>` +
    `<div class="cmp-rail-list">${rows}</div></aside>`;
}

function cmpMain() {
  const pair = (CMP.data.pairs || [])[CMP.selected];
  if (!pair) return '<section class="cmp-main"><div class="hero-msg">画面を選択してください。</div></section>';
  if (pair.state !== 'matched') {
    return '<section class="cmp-main"><div class="cmp-unmatched-pane">' +
      `<p><b>${escHtml(CMP_STATE_LABELS[pair.state] || pair.state)}</b>: ${escHtml(pair.title)}</p>` +
      `<p class="cmp-note">${escHtml(pair.unmatched_reason || '比較対象がありません')}</p>` +
      '</div></section>';
  }
  return '<section class="cmp-main">' + cmpFilters(pair) + cmpStage(pair) + cmpIssues(pair) + '</section>';
}

function cmpFilters(pair) {
  // 出す選択肢は、その画面に実在するものだけにする。
  // 空振りするフィルタを並べると、押しても何も起きない理由が分からない。
  const findings = pair.findings || [];
  if (!findings.length) return '';
  const btn = (key, label) =>
    `<button type="button" class="cmp-filter${CMP.filter === key ? ' is-active' : ''}"` +
    ` data-cmp-filter="${escHtml(key)}">${escHtml(label)}</button>`;
  const buttons = [btn('all', 'すべて')];
  if (findings.some(f => f.severity === CMP_SEVERITY_TOP)) buttons.push(btn('high', '重要度 高'));
  [...new Set(findings.map(f => f.category))].forEach(c => {
    buttons.push(btn(c, CMP_CATEGORY_LABELS[c] || c));
  });
  return `<div class="cmp-filters">${buttons.join('')}</div>`;
}

function cmpMatchesFilter(finding) {
  if (CMP.filter === 'all') return true;
  if (CMP.filter === 'high') return finding.severity === CMP_SEVERITY_TOP;
  return finding.category === CMP.filter;
}

// 表示操作。縦長ページを左右で見比べるとき、同期スクロールが無いと
// 対応箇所を目で追えない。重ね合わせは「動いたかどうか」を見るための切替。
function cmpToolbar(pair) {
  const s = pair.screenshots || {};
  const canOverlay = Boolean(s.before && s.after);
  return '<div class="cmp-toolbar">' +
    '<div class="cmp-zoom">' +
      '<button type="button" class="cmp-zoom-btn" data-cmp-zoom="-" aria-label="縮小">−</button>' +
      `<span class="cmp-zoom-val">${CMP.zoom}%</span>` +
      '<button type="button" class="cmp-zoom-btn" data-cmp-zoom="+" aria-label="拡大">＋</button>' +
    '</div>' +
    `<button type="button" class="cmp-toggle${CMP.syncScroll ? ' is-on' : ''}" data-cmp-toggle="sync"` +
    ` aria-pressed="${CMP.syncScroll}">スクロールを同期</button>` +
    (canOverlay
      ? `<button type="button" class="cmp-toggle${CMP.overlay ? ' is-on' : ''}" data-cmp-toggle="overlay"` +
        ` aria-pressed="${CMP.overlay}">重ね合わせ</button>`
      : '') +
  '</div>';
}

function cmpStage(pair) {
  const s = pair.screenshots || {};
  const afterSrc = s.diff || s.after;
  const note = s.same_capture
    ? '<p class="cmp-warn">この2時点は同じキャプチャを指しています（世代別の画像が保存される前に取得されたスナップショットです）。' +
      '画像の比較はできません。再解析すると次回から比較できます。</p>'
    : '';
  if (!s.before && !s.after) {
    return '<div class="cmp-stage"><p class="cmp-note">この画面のキャプチャは取得されていません（未確認）。</p></div>';
  }
  const body = CMP.overlay && s.before && s.after
    ? cmpOverlay(s)
    : '<div class="cmp-split">' +
        cmpShot('現行', CMP.data.from, s.before) +
        cmpShot(s.diff ? '新（変更箇所を赤枠）' : '新', CMP.data.to, afterSrc) +
      '</div>';
  return '<div class="cmp-stage">' + note + cmpToolbar(pair) + body +
    `<p class="cmp-metrics">変化 ${((s.diff_ratio || 0) * 100).toFixed(1)}%` +
    ` / SSIM ${(s.structural_similarity != null ? s.structural_similarity : 1).toFixed(2)}` +
    `${s.is_significant ? '' : '（有意差なし）'}</p>` +
  '</div>';
}

// 重ね合わせ: 現行の上に新を半透明で乗せる。ずれた要素が二重に見えるので、
// 「どこが動いたか」を掴むのに向く。細かい差は赤枠付きの並置のほうが分かる。
function cmpOverlay(s) {
  return '<figure class="cmp-shot cmp-overlay">' +
    '<figcaption>重ね合わせ<span>現行 + 新（半透明）</span></figcaption>' +
    `<div class="cmp-shot-body" data-cmp-scroll="overlay" style="zoom:${CMP.zoom / 100}">` +
      '<div class="cmp-overlay-stack">' +
        `<img src="/preview?path=${encodeURIComponent(s.before)}" alt="現行">` +
        `<img class="cmp-overlay-top" src="/preview?path=${encodeURIComponent(s.after)}" alt="新">` +
      '</div>' +
    '</div></figure>';
}

function cmpShot(caption, stamp, src) {
  const body = src
    ? `<img src="/preview?path=${encodeURIComponent(src)}" alt="${escHtml(caption)}" loading="lazy">`
    : '<div class="cmp-shot-missing">キャプチャなし</div>';
  return '<figure class="cmp-shot">' +
    `<figcaption>${escHtml(caption)}<span>${escHtml(stamp || '')}</span></figcaption>` +
    `<div class="cmp-shot-body" data-cmp-scroll="pane" style="zoom:${CMP.zoom / 100}">${body}</div></figure>`;
}

function cmpIssues(pair) {
  const items = (pair.findings || []).filter(cmpMatchesFilter);
  if (!items.length) {
    return (pair.findings || []).length
      ? '<p class="cmp-note">この絞り込みに該当する指摘はありません。</p>'
      : '<p class="cmp-note">この画面に指摘はありません。</p>';
  }
  const rows = items.map(f =>
    `<button type="button" class="cmp-issue" data-cmp-issue="${f.index}">` +
    `<span class="cmp-badge cmp-cat-${escHtml(f.category)}">${escHtml(CMP_CATEGORY_LABELS[f.category] || f.category)}</span>` +
    `<span class="cmp-sev">${escHtml(CMP_SEVERITY_LABELS[f.severity] || f.severity || '')}</span>` +
    `<span class="cmp-issue-detail">${escHtml(f.detail || '')}</span></button>`).join('');
  return `<div class="cmp-issues">${rows}</div>`;
}

// ---- モーダル ----
// 比較の根拠を出す。「変わっています」だけでは、どの要素をどう直せばよいか分からない。
function cmpOpenDetail(index) {
  const pair = (CMP.data.pairs || [])[CMP.selected] || {};
  const f = (pair.findings || []).find(x => x.index === index);
  if (!f) return;
  const ev = f.new_evidence || f.old_evidence || {};
  const rows = [
    ['検出内容', f.detail || ''],
    ['分類', CMP_CATEGORY_LABELS[f.category] || f.category || ''],
    ['重要度', CMP_SEVERITY_LABELS[f.severity] || f.severity || ''],
    ['確信度', f.confidence != null ? `${Math.round(f.confidence * 100)}%` : ''],
    ['対象要素', ev.selector || '（記録なし）'],
    ['根拠キャプチャ', ev.screenshot_path || '（記録なし）'],
  ];
  cmpShowModal('差分の詳細',
    '<div class="cmp-modal-alert">' +
      `${escHtml(CMP_CATEGORY_LABELS[f.category] || f.category || '')}　/　` +
      `重要度: ${escHtml(CMP_SEVERITY_LABELS[f.severity] || f.severity || '')}</div>` +
    rows.map(([k, v]) =>
      '<div class="cmp-detail-row">' +
      `<div class="cmp-detail-label">${escHtml(k)}</div>` +
      `<div class="cmp-detail-value">${escHtml(String(v))}</div></div>`).join(''));
}

function cmpOpenChange() {
  const opts = CMP.snapshots.map(s =>
    `<option value="${escHtml(s.id)}">${escHtml(s.label || s.id)}（${s.screens ?? '-'}画面）</option>`).join('');
  cmpShowModal('比較条件を変更',
    '<p class="cmp-note">比較元は比較先より前の時点である必要があります。</p>' +
    '<div class="cmp-detail-row"><div class="cmp-detail-label">比較元（現行）</div>' +
    `<div class="cmp-detail-value"><select id="cmp-from">${opts}</select></div></div>` +
    '<div class="cmp-detail-row"><div class="cmp-detail-label">比較先（新）</div>' +
    `<div class="cmp-detail-value"><select id="cmp-to">${opts}</select></div></div>` +
    '<p class="cmp-modal-err" id="cmp-change-err" hidden></p>' +
    '<div class="cmp-modal-actions">' +
      '<button type="button" class="btn-outline-sm" data-cmp-close>キャンセル</button>' +
      '<button type="button" class="btn-primary" id="cmp-apply">この条件で比較</button></div>',
    () => {
      document.getElementById('cmp-from').value = CMP.from;
      document.getElementById('cmp-to').value = CMP.to;
      document.getElementById('cmp-apply').addEventListener('click', () => {
        const from = document.getElementById('cmp-from').value;
        const to = document.getElementById('cmp-to').value;
        const err = document.getElementById('cmp-change-err');
        // 同一・逆順を黙って通すと、意味の無い比較結果を正しい結果として見せてしまう。
        if (from === to) return cmpSetErr(err, '異なる2時点を選んでください。');
        if (from > to) return cmpSetErr(err, '比較元は比較先より前の時点にしてください。');
        CMP.from = from; CMP.to = to;
        cmpCloseModal();
        cmpLoad();
      });
    });
}

function cmpSetErr(el, msg) {
  if (!el) return;
  el.textContent = msg;
  el.hidden = false;
}

function cmpShowModal(title, bodyHtml, afterRender) {
  cmpCloseModal();
  const host = document.createElement('div');
  host.className = 'cmp-modal';
  host.id = 'cmp-modal';
  host.innerHTML =
    '<div class="cmp-modal-overlay" data-cmp-close></div>' +
    '<div class="cmp-modal-box" role="dialog" aria-modal="true" aria-label="' + escHtml(title) + '">' +
      `<header class="cmp-modal-head"><h4>${escHtml(title)}</h4>` +
      '<button type="button" class="btn-outline-sm" data-cmp-close aria-label="閉じる">✕</button></header>' +
      `<div class="cmp-modal-body">${bodyHtml}</div>` +
    '</div>';
  document.body.appendChild(host);
  host.querySelectorAll('[data-cmp-close]').forEach(el => el.addEventListener('click', cmpCloseModal));
  document.addEventListener('keydown', cmpEscClose);
  if (afterRender) afterRender();
}

function cmpCloseModal() {
  document.getElementById('cmp-modal')?.remove();
  document.removeEventListener('keydown', cmpEscClose);
}

function cmpEscClose(e) { if (e.key === 'Escape') cmpCloseModal(); }

// ---- 操作 ----
function cmpBind() {
  const panel = cmpPanel();
  if (!panel) return;
  panel.querySelectorAll('[data-cmp-pair]').forEach(b => {
    b.addEventListener('click', () => {
      CMP.selected = Number(b.dataset.cmpPair);
      CMP.filter = 'all';  // 画面が変われば分類の顔ぶれも変わる
      cmpRender();
    });
  });
  panel.querySelectorAll('[data-cmp-filter]').forEach(b => {
    b.addEventListener('click', () => { CMP.filter = b.dataset.cmpFilter; cmpRender(); });
  });
  panel.querySelectorAll('[data-cmp-issue]').forEach(b => {
    b.addEventListener('click', () => cmpOpenDetail(Number(b.dataset.cmpIssue)));
  });
  panel.querySelectorAll('[data-cmp-zoom]').forEach(b => {
    b.addEventListener('click', () => {
      const i = CMP_ZOOM_STEPS.indexOf(CMP.zoom);
      const next = b.dataset.cmpZoom === '+' ? i + 1 : i - 1;
      if (next < 0 || next >= CMP_ZOOM_STEPS.length) return;
      CMP.zoom = CMP_ZOOM_STEPS[next];
      cmpRender();
    });
  });
  panel.querySelectorAll('[data-cmp-toggle]').forEach(b => {
    b.addEventListener('click', () => {
      const key = b.dataset.cmpToggle === 'sync' ? 'syncScroll' : 'overlay';
      CMP[key] = !CMP[key];
      cmpRender();
    });
  });
  document.getElementById('cmp-change-btn')?.addEventListener('click', cmpOpenChange);
  cmpBindSyncScroll(panel);
}

// 左右のスクロールを合わせる。片方を動かしたときだけ他方へ写す
// （両方が互いに反応すると、丸め誤差で震え続ける）。
function cmpBindSyncScroll(panel) {
  const panes = [...panel.querySelectorAll('[data-cmp-scroll="pane"]')];
  if (panes.length < 2) return;
  let source = null;
  panes.forEach(p => {
    p.addEventListener('scroll', () => {
      if (!CMP.syncScroll || (source && source !== p)) return;
      source = p;
      panes.forEach(other => {
        if (other === p) return;
        other.scrollTop = p.scrollTop;
        other.scrollLeft = p.scrollLeft;
      });
      window.requestAnimationFrame(() => { source = null; });
    });
  });
}
