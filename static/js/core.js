
const SETTINGS_KEY = 'webspec2doc.settings';
const SIDEBAR_KEY  = 'webspec2doc.sidebar-collapsed';

// ---- サイドバー折りたたみ（全画面共通・localStorage 永続） ----
function _applySidebarCollapsed(collapsed) {
  document.querySelector('.app-shell').classList.toggle('sidebar-collapsed', collapsed);
  const btn = document.getElementById('sidebar-toggle-btn');
  if (btn) btn.title = collapsed ? 'サイドバーを広げる' : 'サイドバーを折りたたむ';
}
_applySidebarCollapsed(localStorage.getItem(SIDEBAR_KEY) === '1');
document.getElementById('sidebar-toggle-btn')?.addEventListener('click', () => {
  const collapsed = !document.querySelector('.app-shell').classList.contains('sidebar-collapsed');
  _applySidebarCollapsed(collapsed);
  localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0');
});
const VIEW_HEADER = {
  dashboard: { trail: ['WebSpec2Doc', 'ホーム'], title: 'QAドキュメント生成' },
  generate: { trail: ['ダッシュボード', 'サイトを追加'], title: 'サイトを追加 / 再クロール' },
  'qa-quality': { trail: ['ダッシュボード', '品質観点'], title: '品質観点' },
  viewpoints: { trail: ['ダッシュボード', '観点管理'], title: '観点管理' },
  'auto-run': { trail: ['ダッシュボード', 'AutoRun'], title: 'AutoRun — 全自動テスト実行' },
  testcases: { trail: ['ダッシュボード', 'テストケース'], title: 'テストケース一覧' },
  'run-history': { trail: ['ダッシュボード', '実行履歴'], title: '実行履歴' },
  'user-guide': { trail: ['ダッシュボード', 'ユーザーガイド'], title: 'ユーザーガイド' },
  references: { trail: ['ダッシュボード', '参考'], title: '参考 — 依拠する標準・先行研究・事例' },
  settings: { trail: ['ダッシュボード', '設定'], title: '設定' },
};
const escHtml = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// ---- 情報アイコン（用語説明のツールチップ。列見出し・設定項目ラベル等で共通利用） ----
function infoTip(text) {
  const t = escHtml(text || '');
  return `<span class="info-tip" tabindex="0" role="img" aria-label="${t}" data-tip="${t}">ⓘ</span>`;
}

// ---- 画面別URL（ブックマーク・共有・リロード対応）----
const VIEW_PATHS = {
  dashboard: '/',
  generate: '/generate',
  'qa-quality': '/qa-quality',
  viewpoints: '/viewpoints',
  'auto-run': '/auto-run',
  testcases: '/testcases',
  'run-history': '/run-history',
  'user-guide': '/user-guide',
  references: '/references',
  settings: '/settings',
};
const PATH_VIEWS = { '/home': 'dashboard', '/dashboard': 'dashboard' };
Object.entries(VIEW_PATHS).forEach(([name, path]) => { PATH_VIEWS[path] = name; });
function _viewFromPath(pathname) {
  return PATH_VIEWS[pathname] || null;
}
window.addEventListener('popstate', () => {
  const m = location.hash.match(/^#report\/([^/]+)(?:\/([^/]+))?(?:\/([^/]+))?$/);
  if (m && typeof openResultsForDomain === 'function') {
    openResultsForDomain(decodeURIComponent(m[1]), m[2] && decodeURIComponent(m[2]), m[3] && decodeURIComponent(m[3]));
    return;
  }
  switchView(_viewFromPath(location.pathname) || 'dashboard', { skipHistory: true });
});

// ---- ヘッダー（パンくず＋タイトル）----
function setHeader(trail, title) {
  const bc = document.getElementById('topbar-breadcrumb');
  bc.innerHTML = trail.map((t, i) => i === 0
    ? `<a data-bc-root="1">${escHtml(t)}</a>`
    : `<span class="sep">›</span><span>${escHtml(t)}</span>`).join('');
  const root = bc.querySelector('[data-bc-root]');
  if (root && trail.length > 1) root.addEventListener('click', () => switchView('dashboard'));
  document.getElementById('topbar-title').textContent = title;
  document.getElementById('topbar-actions').innerHTML = '';
}

// ---- ナビ切替 ----
document.querySelectorAll('.app-nav-item[data-view]').forEach(btn => btn.addEventListener('click', () => switchView(btn.dataset.view)));
function switchView(name, opts = {}) {
  document.body.classList.toggle('viewpoints-active', name === 'viewpoints');
  document.querySelectorAll('.app-nav-item[data-view]').forEach(b => b.classList.toggle('is-active', b.dataset.view === name));
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('is-active', v.id === 'view-' + name));
  const h = VIEW_HEADER[name];
  if (h) setHeader(h.trail, h.title);
  if (!opts.skipHistory) {
    const path = VIEW_PATHS[name] || '/';
    // レポートのディープリンク（#report/...）は generate 画面滞在中のみ維持する。
    const keepHash = (name === 'generate' && location.hash.startsWith('#report/')) ? location.hash : '';
    const target = path + keepHash;
    if (location.pathname + location.hash !== target) {
      try { history.pushState({ view: name }, '', target); } catch (e) {}
    }
  }
  if (name === 'dashboard') {
    loadHistory();
    // ディープリンクのハッシュをクリア（レポートから戻った時のみ。初期化時は保持）
    if (window._appBooted && location.hash.startsWith('#report/')) {
      try { history.replaceState(null, '', location.pathname); } catch (e) {}
    }
  }
  if (name === 'qa-quality') loadQaToolSites(name);
  if (name === 'testcases' && typeof tcOnEnterView === 'function') tcOnEnterView();
  if (name === 'run-history' && typeof loadRunHistory === 'function') loadRunHistory();
  if (name === 'viewpoints' && typeof loadViewpointManager === 'function') loadViewpointManager();
  if (name === 'auto-run') {
    if (typeof autorunLoadViewpointSelection === 'function') autorunLoadViewpointSelection();
    // リロード後も実行中ジョブへ再接続し、「最近の実行」を表示する
    if (typeof autorunResume === 'function') autorunResume();
  }
  // A: 2ペインツール画面では全高モードに切り替え
  const appContentEl = document.getElementById('app-content');
  if (appContentEl) appContentEl.classList.toggle('is-qa-tool', ['qa-quality', 'auto-run', 'viewpoints'].includes(name));
  // is-executing / is-reporting は「サイトを追加」画面（generate）専用の全高モードフラグ。
  // 付けっぱなしで他画面に移動すると #app-content が overflow:hidden のまま固定され、
  // ユーザーガイド等の画面がスクロール不能になる不具合が実際に発生していた（再発防止のため
  // switchView 側で必ず後始末する。個別のボタンハンドラの消し忘れに依存しない）。
  if (appContentEl) {
    if (name !== 'generate') {
      appContentEl.classList.remove('is-executing', 'is-reporting');
    } else {
      // generate へ戻った場合のみ、実行中/レポート表示中の全高モードを復元する
      const execVisible = executionView && !executionView.classList.contains('hidden');
      const resultVisible = resultPanel && !resultPanel.classList.contains('hidden');
      appContentEl.classList.toggle('is-executing', !!execVisible);
      appContentEl.classList.toggle('is-reporting', !execVisible && !!resultVisible);
    }
  }
}
// ---- ウィザード ステップ管理 ----
function showWizardStep(n) {
  const p1 = document.getElementById('wizard-p1');
  const p2 = document.getElementById('wizard-p2');
  const bar = document.getElementById('wizard-progress-bar');
  if (p1) p1.style.display = (n === 1) ? '' : 'none';
  if (p2) p2.style.display = (n === 2) ? '' : 'none';
  // ステップ3（実行中）と4（レポート）ではウィザードバー不要（それぞれ専用UIあり）
  if (bar) bar.style.display = (n >= 3) ? 'none' : '';
  [1, 2, 3, 4].forEach(i => {
    const node = document.getElementById('ws-' + i);
    if (!node) return;
    node.classList.toggle('is-active', i === n);
    node.classList.toggle('is-done', i < n);
  });
  [1, 2, 3].forEach(i => {
    const line = document.getElementById('wl-' + i);
    if (line) line.classList.toggle('is-done', i < n);
  });
}

// 「+ サイトを追加」: 新規ウィザードを開く（P1から）
function openAddSite() {
  switchView('generate');
  executionView.classList.add('hidden'); resultPanel.classList.add('hidden');
  appContent.classList.remove('is-executing', 'is-reporting');
  genPanel.style.display = '';
  document.getElementById('url-input').value = '';
  document.getElementById('p1-summary').style.display = 'none';
  clearDiscovered(); updateTargetPreview(); showWizardStep(1);
}
document.getElementById('add-site-btn').addEventListener('click', openAddSite);
document.getElementById('add-site-btn-2').addEventListener('click', openAddSite);
document.getElementById('nav-new-analysis-btn').addEventListener('click', openAddSite);

// ---- ナビ「実行履歴」: 種別を問わない一般化された実行履歴ビューへ遷移する（R2-27）----
document.getElementById('nav-run-history-btn')?.addEventListener('click', () => {
  switchView('run-history');
});

// ---- ダッシュボード・ヒーロー（ゴールデンパス入口） ----
function _heroStartGuided(prefillUrl) {
  openAddSite();
  const input = document.getElementById('url-input');
  if (input && prefillUrl) {
    input.value = prefillUrl;
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }
}
document.getElementById('hero-start-btn')?.addEventListener('click', () => {
  const v = (document.getElementById('hero-url')?.value || '').trim();
  _heroStartGuided(v);
  // URL があれば画面分析まで自動で進める（既存 discover フローを再利用）
  if (v) document.getElementById('discover-btn')?.click();
});
document.getElementById('hero-url')?.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') return;
  event.preventDefault();
  document.getElementById('hero-start-btn')?.click();
});
document.getElementById('hero-guided-btn')?.addEventListener('click', () => {
  _heroStartGuided((document.getElementById('hero-url')?.value || '').trim());
});
document.getElementById('hero-auto-btn')?.addEventListener('click', () => {
  const v = (document.getElementById('hero-url')?.value || '').trim();
  switchView('auto-run');
  const a = document.getElementById('autorun-url');
  if (a && v) { a.value = v; a.dispatchEvent(new Event('input', { bubbles: true })); }
});
document.getElementById('hero-sample-btn')?.addEventListener('click', () => {
  const input = document.getElementById('hero-url');
  if (input) { input.value = 'https://example.com'; input.dispatchEvent(new Event('input', { bubbles: true })); }
});

// P1 → P2: 「次へ」ボタン
document.getElementById('p1-next-btn').addEventListener('click', () => {
  showWizardStep(2);
  // 画面リストと必要なら認証パネルを表示
  if (discovered.length) {
    document.getElementById('discovered-url-panel').style.display = '';
    updateTargetPreview();
  }
});

// P2 → P1: 「解析に戻る」ボタン
document.getElementById('p2-back-btn').addEventListener('click', () => {
  showWizardStep(1);
});

// ---- テーマ（ライト/ダーク）切替・localStorage 永続 ----
const THEME_KEY = 'webspec2doc.theme';
function _applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const btn = document.getElementById('theme-toggle-btn');
  if (btn) btn.title = theme === 'dark' ? 'ライトモードに切替' : 'ダークモードに切替';
}
_applyTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light');
document.getElementById('theme-toggle-btn')?.addEventListener('click', () => {
  const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  _applyTheme(next);
  try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
});

// ---- トースト通知 ----
const TOAST_ICONS = { success: '✓', error: '⚠', info: 'ℹ' };
function showToast(message, type = 'info', duration = 3500) {
  const wrap = document.getElementById('toast-container');
  if (!wrap) return;
  const el = document.createElement('div');
  el.className = 'toast toast-' + (TOAST_ICONS[type] ? type : 'info');
  el.setAttribute('role', 'status');
  const icon = document.createElement('span');
  icon.className = 'toast-icon';
  icon.textContent = TOAST_ICONS[type] || TOAST_ICONS.info;
  const msg = document.createElement('span');
  msg.textContent = message;
  el.append(icon, msg);
  wrap.appendChild(el);
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => {
    el.classList.remove('show');
    setTimeout(() => el.remove(), 300);
  }, duration);
}

// ---- 確認モーダル（confirm() 代替・Promise<boolean>）----
function confirmDialog({ title = '確認', message = '', confirmLabel = 'OK', cancelLabel = 'キャンセル', danger = false } = {}) {
  return new Promise((resolve) => {
    const ov = document.getElementById('confirm-overlay');
    const okBtn = document.getElementById('confirm-ok-btn');
    const cancelBtn = document.getElementById('confirm-cancel-btn');
    if (!ov || !okBtn || !cancelBtn) { resolve(window.confirm(message)); return; }
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').textContent = message;
    okBtn.textContent = confirmLabel;
    cancelBtn.textContent = cancelLabel;
    okBtn.classList.toggle('btn-danger', !!danger);
    ov.classList.remove('hidden');
    const prevFocus = document.activeElement;
    cancelBtn.focus();
    const close = (result) => {
      ov.classList.add('hidden');
      okBtn.removeEventListener('click', onOk);
      cancelBtn.removeEventListener('click', onCancel);
      ov.removeEventListener('click', onOverlay);
      document.removeEventListener('keydown', onKey);
      if (prevFocus && typeof prevFocus.focus === 'function') prevFocus.focus();
      resolve(result);
    };
    const onOk = () => close(true);
    const onCancel = () => close(false);
    const onOverlay = (e) => { if (e.target === ov) close(false); };
    const onKey = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); close(false); return; }
      if (e.key !== 'Tab') return;
      const focusable = [...ov.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')]
        .filter(el => !el.hidden && el.offsetParent !== null);
      if (!focusable.length) { e.preventDefault(); return; }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    okBtn.addEventListener('click', onOk);
    cancelBtn.addEventListener('click', onCancel);
    ov.addEventListener('click', onOverlay);
    document.addEventListener('keydown', onKey);
  });
}

// ---- 入力モーダル（prompt() 代替・Promise<string|null>）----
function inputDialog({ title = '入力', message = '', placeholder = '', defaultValue = '', confirmLabel = 'OK', cancelLabel = 'キャンセル', type = 'text', validate = null, suggestions = [] } = {}) {
  return new Promise((resolve) => {
    const ov = document.getElementById('input-dialog-overlay');
    if (!ov) { resolve(window.prompt(message, defaultValue)); return; }
    const input = document.getElementById('input-dialog-input');
    const textarea = document.getElementById('input-dialog-textarea');
    const errorEl = document.getElementById('input-dialog-error');
    const okBtn = document.getElementById('input-dialog-ok-btn');
    const cancelBtn = document.getElementById('input-dialog-cancel-btn');
    const datalist = document.getElementById('input-dialog-datalist');
    const isTextarea = type === 'textarea';
    const activeField = isTextarea ? textarea : input;
    const inactiveField = isTextarea ? input : textarea;

    document.getElementById('input-dialog-title').textContent = title;
    const msgEl = document.getElementById('input-dialog-message');
    msgEl.textContent = message;
    msgEl.hidden = !message;

    inactiveField.hidden = true;
    activeField.hidden = false;
    activeField.value = defaultValue;
    activeField.placeholder = placeholder;
    if (!isTextarea) activeField.type = type;
    if (datalist) {
      while (datalist.firstChild) datalist.removeChild(datalist.firstChild);
      suggestions.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s;
        datalist.appendChild(opt);
      });
      if (suggestions.length && !isTextarea) activeField.setAttribute('list', 'input-dialog-datalist');
      else activeField.removeAttribute('list');
    }
    errorEl.hidden = true;
    okBtn.textContent = confirmLabel;
    cancelBtn.textContent = cancelLabel;
    ov.classList.remove('hidden');
    const prevFocus = document.activeElement;
    activeField.focus();
    if (activeField.select) activeField.select();

    const close = (result) => {
      ov.classList.add('hidden');
      okBtn.removeEventListener('click', onOk);
      cancelBtn.removeEventListener('click', onCancel);
      ov.removeEventListener('click', onOverlay);
      document.removeEventListener('keydown', onKey);
      activeField.removeEventListener('keydown', onFieldKey);
      if (prevFocus && typeof prevFocus.focus === 'function') prevFocus.focus();
      resolve(result);
    };
    const onOk = () => {
      const value = activeField.value.trim();
      if (validate) {
        const error = validate(value);
        if (error) { errorEl.textContent = error; errorEl.hidden = false; activeField.focus(); return; }
      }
      close(value === '' ? null : value);
    };
    const onCancel = () => close(null);
    const onOverlay = (e) => { if (e.target === ov) close(null); };
    const onKey = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); close(null); return; }
      if (e.key !== 'Tab') return;
      const focusable = [...ov.querySelectorAll('button:not([disabled]), input:not([hidden]), textarea:not([hidden])')].filter(el => el.offsetParent !== null);
      if (!focusable.length) { e.preventDefault(); return; }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    const onFieldKey = (e) => { if (e.key === 'Enter' && !isTextarea) { e.preventDefault(); onOk(); } };
    okBtn.addEventListener('click', onOk);
    cancelBtn.addEventListener('click', onCancel);
    ov.addEventListener('click', onOverlay);
    document.addEventListener('keydown', onKey);
    activeField.addEventListener('keydown', onFieldKey);
  });
}

// ---- キーボードショートカット（? でヘルプ / Alt+D / Alt+N）----
function toggleShortcutHelp(force) {
  const ov = document.getElementById('shortcut-overlay');
  if (!ov) return;
  const show = force !== undefined ? force : ov.classList.contains('hidden');
  ov.classList.toggle('hidden', !show);
}
document.getElementById('shortcut-help-btn')?.addEventListener('click', () => toggleShortcutHelp(true));
document.getElementById('shortcut-close-btn')?.addEventListener('click', () => toggleShortcutHelp(false));
document.getElementById('shortcut-overlay')?.addEventListener('click', (e) => {
  if (e.target === e.currentTarget) toggleShortcutHelp(false);
});
document.addEventListener('keydown', (e) => {
  const tag = (e.target.tagName || '').toLowerCase();
  const typing = ['input', 'textarea', 'select'].includes(tag) || e.target.isContentEditable;
  if (e.key === '?' && !typing && !e.altKey && !e.ctrlKey && !e.metaKey) {
    e.preventDefault(); toggleShortcutHelp();
  } else if (e.key === 'Escape') {
    toggleShortcutHelp(false);
  } else if (e.altKey && !e.ctrlKey && !e.metaKey && (e.key === 'd' || e.key === 'D')) {
    e.preventDefault(); switchView('dashboard');
  } else if (e.altKey && !e.ctrlKey && !e.metaKey && (e.key === 'n' || e.key === 'N')) {
    e.preventDefault(); openAddSite();
  } else if (e.altKey && !e.ctrlKey && !e.metaKey && (e.key === 'a' || e.key === 'A')) {
    e.preventDefault(); switchView('auto-run');
  } else if (e.altKey && !e.ctrlKey && !e.metaKey && (e.key === 'h' || e.key === 'H')) {
    e.preventDefault(); switchView('run-history');
  } else if (!typing && !e.altKey && !e.ctrlKey && !e.metaKey && /^[1-9]$/.test(e.key)) {
    const tabs = document.querySelectorAll('.result-tabs .result-tab:not([hidden])');
    const tab = tabs[Number(e.key) - 1];
    if (tab) { e.preventDefault(); tab.click(); }
  } else if (!typing && e.key === '/' && !e.altKey && !e.ctrlKey && !e.metaKey) {
    let target = null;
    for (const sel of ['#mx-search', '#vp-search']) {
      const el = document.querySelector(sel);
      if (el && el.offsetParent !== null) { target = el; break; }
    }
    if (!target) target = document.querySelector('input[type="search"]:not([hidden])');
    if (target) { e.preventDefault(); target.focus(); }
  }
});

// ---- 起動時: URL（/settings 等）に対応する画面を復元する ----
// レポートのディープリンク（#report/...）は recrawl.js 側の起動処理に委ねる。
window.addEventListener('DOMContentLoaded', () => {
  if (location.hash.startsWith('#report/')) return;
  const name = _viewFromPath(location.pathname);
  if (name) switchView(name, { skipHistory: true });
  // switchView 内の後始末（:114-124）と二重で防御する。ディープリンク経路は
  // is-executing/is-reporting が残留してガイド等がスクロール不能になる不具合の
  // 再発を確実に防ぐため、ここでも明示的に解除する（R3-12）。
  const appContentEl = document.getElementById('app-content');
  if (appContentEl && name !== 'generate') {
    appContentEl.classList.remove('is-executing', 'is-reporting');
  }
});
