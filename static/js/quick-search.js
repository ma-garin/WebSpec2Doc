// ==================== トップバー クイック検索 ====================
// 画面（ビュー）と解析済みサイトを横断検索し、Enter/クリックで遷移する。
// Cmd/Ctrl+K でフォーカス、Esc で閉じる。core.js の switchView /
// openResultsForDomain に依存する（読み込み順は index.html で保証）。
(function () {
  const input = document.getElementById('topbar-search-input');
  const panel = document.getElementById('topbar-search-results');
  if (!input || !panel) return;

  // ナビ可能なビュー（VIEW_HEADER / nav.html のラベルに対応）。
  const VIEWS = [
    { view: 'dashboard', label: 'ホーム', kw: 'home dashboard qa ドキュメント生成' },
    { view: 'generate', label: '新規解析', kw: 'add site crawl 再クロール url' },
    { view: 'auto-run', label: 'AutoRun', kw: '全自動 テスト実行 autorun' },
    { view: 'run-history', label: '実行履歴', kw: 'history ラン run' },
    { view: 'testcases', label: 'テストケース', kw: 'test case ケース' },
    { view: 'qa-quality', label: '品質観点', kw: 'quality ひんしつ' },
    { view: 'viewpoints', label: '観点管理', kw: 'viewpoint 観点 かんてん' },
    { view: 'user-guide', label: 'ユーザーガイド', kw: 'guide help ヘルプ 使い方' },
    { view: 'settings', label: '設定', kw: 'settings config せってい' },
  ];

  const esc = (s) => (typeof escHtml === 'function' ? escHtml(s) : String(s));
  let sites = [];
  let sitesLoaded = false;
  let items = [];
  let active = -1;

  async function ensureSites() {
    if (sitesLoaded) return;
    sitesLoaded = true;
    try {
      const res = await fetch('/api/history');
      const data = await res.json();
      sites = (data.items || []).map((it) => it.domain).filter(Boolean);
    } catch (e) {
      sites = [];
    }
  }

  function buildItems(query) {
    const q = query.trim().toLowerCase();
    const out = [];
    for (const v of VIEWS) {
      if (!q || v.label.toLowerCase().includes(q) || v.kw.toLowerCase().includes(q)) {
        out.push({ type: 'view', key: v.view, label: v.label, sub: '画面' });
      }
    }
    for (const d of sites) {
      if (!q || d.toLowerCase().includes(q)) {
        out.push({ type: 'site', key: d, label: d, sub: '解析済みサイト' });
      }
    }
    return out.slice(0, 8);
  }

  const ICON_VIEW =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>';
  const ICON_SITE =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></svg>';

  function render() {
    if (!items.length) {
      panel.hidden = true;
      input.setAttribute('aria-expanded', 'false');
      return;
    }
    panel.innerHTML = items
      .map((it, i) => {
        const dataAttr =
          it.type === 'view'
            ? `data-view="${esc(it.key)}"`
            : `data-domain="${esc(it.key)}"`;
        const icon = it.type === 'view' ? ICON_VIEW : ICON_SITE;
        return (
          `<button type="button" role="option" class="topbar-search-item${i === active ? ' is-active' : ''}" ${dataAttr} data-index="${i}" aria-selected="${i === active}">` +
          `<span class="topbar-search-item-icon">${icon}</span>` +
          `<span class="topbar-search-item-label">${esc(it.label)}</span>` +
          `<span class="topbar-search-item-sub">${esc(it.sub)}</span>` +
          `</button>`
        );
      })
      .join('');
    panel.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  }

  function close() {
    panel.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    active = -1;
  }

  function goto(item) {
    if (!item) return;
    close();
    input.blur();
    if (item.type === 'view' && typeof switchView === 'function') {
      switchView(item.key);
    } else if (item.type === 'site' && typeof openResultsForDomain === 'function') {
      openResultsForDomain(item.key);
    }
  }

  async function refresh() {
    await ensureSites();
    items = buildItems(input.value);
    active = items.length ? 0 : -1;
    render();
  }

  input.addEventListener('focus', refresh);
  input.addEventListener('input', refresh);

  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (items.length) {
        active = (active + 1) % items.length;
        render();
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (items.length) {
        active = (active - 1 + items.length) % items.length;
        render();
      }
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (active >= 0) goto(items[active]);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      if (!panel.hidden) close();
      else input.blur();
    }
  });

  panel.addEventListener('mousedown', (e) => {
    // blur より先に確定させるため mousedown を使う
    const btn = e.target.closest('.topbar-search-item');
    if (!btn) return;
    e.preventDefault();
    const idx = Number(btn.dataset.index);
    goto(items[idx]);
  });

  // クリック外で閉じる
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.topbar-search')) close();
  });

  // Cmd/Ctrl+K でフォーカス
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      input.focus();
      input.select();
    }
  });
})();
