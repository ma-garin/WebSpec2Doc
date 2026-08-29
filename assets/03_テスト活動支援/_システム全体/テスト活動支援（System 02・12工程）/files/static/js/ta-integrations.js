// ---- テスト活動支援 / 連携設定 ----
// 3接続先を俯瞰する。実データで判定できるのは「ドキュメント」のみ（/api/history）。
// ソースコード / 開発標準は接続APIが無いため data-wip で明示する。
// ソースコード参照先は GitHub 固定ではなく、複数ホスティング先 + ローカルパス + ZIP から選べる。
// ローカルパスだけは /api/history へのバックエンド疎通確認という形で「接続」を有効化する
// （パスの実在チェックAPIは無いため、疎通確認であることを明示する）。
(function () {
  'use strict';

  let _loaded = false;
  let _docsConnected = false;

  const TOTAL_SOURCES = 3;

  const GIT_PROVIDER_INFO = {
    github: { repoLabel: 'リポジトリ', repoPlaceholder: 'owner/repository', hostPlaceholder: 'github.com（既定）または自ホストURL' },
    gitlab: { repoLabel: 'リポジトリ', repoPlaceholder: 'namespace/project', hostPlaceholder: 'gitlab.com（既定）または自ホストURL' },
    bitbucket: { repoLabel: 'リポジトリ', repoPlaceholder: 'workspace/repository', hostPlaceholder: 'bitbucket.org（既定）' },
    azure: { repoLabel: '組織/プロジェクト/リポジトリ', repoPlaceholder: 'organization/project/repository', hostPlaceholder: 'dev.azure.com（既定）' },
    generic: { repoLabel: 'リモートURL', repoPlaceholder: 'https://example.com/repo.git', hostPlaceholder: '未指定可' },
  };

  const AUTH_METHOD_INFO = {
    token: { secretLabel: 'トークン', secretType: 'password', secretPlaceholder: 'ghp_...', showUsername: false, showSecret: true },
    ssh: { secretLabel: 'SSH鍵のパス', secretType: 'text', secretPlaceholder: '/home/user/.ssh/id_ed25519', showUsername: false, showSecret: true },
    userpass: { secretLabel: 'パスワード', secretType: 'password', secretPlaceholder: '', showUsername: true, showSecret: true },
    anonymous: { secretLabel: 'トークン', secretType: 'password', secretPlaceholder: '', showUsername: false, showSecret: false },
  };

  const AUTH_MISSING_NOTE = '認証情報が未設定のため利用できません';

  // ローカルパス以外は認証トークンが無く本物の接続確認ができないため、
  // 「ローカルパス」選択時だけ接続ボタンを有効化する。
  function setButtonWip(btn, noteEl, enabled) {
    if (!btn) return;
    if (enabled) {
      btn.disabled = false;
      btn.removeAttribute('data-wip');
      if (noteEl) noteEl.hidden = true;
    } else {
      btn.disabled = true;
      btn.setAttribute('data-wip', '1');
      if (noteEl) { noteEl.hidden = false; noteEl.textContent = AUTH_MISSING_NOTE; }
    }
  }

  function updateCodeConnectAvailability() {
    const select = document.getElementById('ta-int-code-provider');
    const isLocal = !!select && select.value === 'local';
    setButtonWip(document.getElementById('ta-int-code-connect'), document.getElementById('ta-int-code-wip-note'), isLocal);
    setButtonWip(document.getElementById('ta-int-code-save'), document.getElementById('ta-int-code-detail-note'), isLocal);
  }

  function updateStandardConnectAvailability() {
    const select = document.getElementById('ta-int-standard-source');
    const isLocal = !!select && select.value === 'local';
    setButtonWip(document.getElementById('ta-int-standard-connect'), document.getElementById('ta-int-standard-wip-note'), isLocal);
  }

  // ローカルパスのみ、バックエンド（/api/history）への疎通を確認する。
  // パスの実在チェックAPIは無いため、疎通確認の結果であることをバッジ文言で明示する。
  async function verifyLocalPath(pathInput, badgeEl, btn) {
    const path = (pathInput && pathInput.value || '').trim();
    if (!path) {
      if (badgeEl) { badgeEl.textContent = 'パス未入力'; badgeEl.className = 'ta2-badge ta2-badge-wa'; }
      return;
    }
    if (!btn) return;
    btn.disabled = true;
    const prevText = btn.textContent;
    btn.textContent = '確認中…';
    try {
      const res = await fetch('/api/history');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
      if (badgeEl) { badgeEl.textContent = '疎通確認済み（パス実在は未検証）'; badgeEl.className = 'ta2-badge ta2-badge-wa'; }
    } catch (e) {
      if (badgeEl) { badgeEl.textContent = '確認失敗（' + (e && e.message ? e.message : e) + '）'; badgeEl.className = 'ta2-badge ta2-badge-ng'; }
    } finally {
      btn.disabled = false;
      btn.textContent = prevText;
    }
  }

  document.getElementById('ta-int-code-connect')?.addEventListener('click', (evt) => {
    verifyLocalPath(document.getElementById('ta-int-code-local-path'), document.getElementById('ta-int-code-badge'), evt.currentTarget);
  });
  document.getElementById('ta-int-code-save')?.addEventListener('click', (evt) => {
    // <summary> 内のボタンなので、クリックで <details> が開閉しないようにする。
    evt.preventDefault();
    evt.stopPropagation();
    verifyLocalPath(document.getElementById('ta-int-code-local-path'), document.getElementById('ta-int-code-badge'), evt.currentTarget);
  });
  document.getElementById('ta-int-standard-connect')?.addEventListener('click', (evt) => {
    verifyLocalPath(document.getElementById('ta-int-standard-local-path'), document.getElementById('ta-int-standard-badge'), evt.currentTarget);
  });

  function setSummary(connectedCount) {
    const el = document.getElementById('ta-int-summary');
    if (!el) return;
    const ng = TOTAL_SOURCES - connectedCount;
    el.textContent = '未接続 ' + ng + ' / ' + TOTAL_SOURCES;
    el.className = 'stat-card-value ' + (ng > 0 ? 'is-ng' : 'is-ok');
  }

  function renderDocsBadge(connected) {
    const badge = document.getElementById('ta-int-docs-badge');
    const btn = document.getElementById('ta-int-docs-connect');
    if (badge) {
      badge.textContent = connected ? '接続済み' : '未接続';
      badge.className = 'ta2-badge ta2-badge-' + (connected ? 'ok' : 'ng');
    }
    if (btn) {
      if (connected) {
        btn.textContent = '確認済み';
        btn.disabled = true;
      } else {
        btn.textContent = '接続する';
        btn.disabled = false;
      }
    }
  }

  async function load() {
    try {
      const res = await fetch('/api/history');
      const data = await res.json();
      _docsConnected = !!(res.ok && data && Array.isArray(data.items) && data.items.length > 0);
    } catch (e) {
      _docsConnected = false;
    }
    renderDocsBadge(_docsConnected);
    setSummary(_docsConnected ? 1 : 0);
    _loaded = true;
  }

  document.getElementById('ta-int-test-all')?.addEventListener('click', load);

  document.getElementById('ta-int-docs-connect')?.addEventListener('click', () => {
    if (_docsConnected) return;
    if (typeof switchView === 'function') {
      switchView('dashboard');
    }
  });

  // ---- ソースコード: 参照元の切り替え ----
  function updateCodeProviderFields() {
    const select = document.getElementById('ta-int-code-provider');
    const gitFields = document.getElementById('ta-int-code-git-fields');
    const localFields = document.getElementById('ta-int-code-local-fields');
    const zipFields = document.getElementById('ta-int-code-zip-fields');
    if (!select || !gitFields || !localFields || !zipFields) return;

    const provider = select.value;
    const isGit = Object.prototype.hasOwnProperty.call(GIT_PROVIDER_INFO, provider);
    gitFields.hidden = !isGit;
    localFields.hidden = provider !== 'local';
    zipFields.hidden = provider !== 'zip';

    if (isGit) {
      const info = GIT_PROVIDER_INFO[provider];
      const repoLabel = document.getElementById('ta-int-code-repo-label');
      const repoInput = document.getElementById('ta-int-code-repo');
      const hostInput = document.getElementById('ta-int-code-host');
      if (repoLabel) repoLabel.textContent = info.repoLabel;
      if (repoInput) repoInput.placeholder = info.repoPlaceholder;
      if (hostInput) hostInput.placeholder = info.hostPlaceholder;
    }
    updateCodeConnectAvailability();
  }

  function updateCodeAuthFields() {
    const select = document.getElementById('ta-int-code-auth-method');
    const usernameRow = document.getElementById('ta-int-code-username-row');
    const secretRow = document.getElementById('ta-int-code-secret-row');
    const secretLabel = document.getElementById('ta-int-code-secret-label');
    const secretInput = document.getElementById('ta-int-code-secret');
    if (!select || !usernameRow || !secretRow || !secretLabel || !secretInput) return;

    const info = AUTH_METHOD_INFO[select.value] || AUTH_METHOD_INFO.token;
    usernameRow.hidden = !info.showUsername;
    secretRow.hidden = !info.showSecret;
    secretLabel.textContent = info.secretLabel;
    secretInput.type = info.secretType;
    secretInput.placeholder = info.secretPlaceholder;
  }

  document.getElementById('ta-int-code-provider')?.addEventListener('change', updateCodeProviderFields);
  document.getElementById('ta-int-code-auth-method')?.addEventListener('change', updateCodeAuthFields);

  // ---- 開発標準: 取り込み元の切り替え ----
  function updateStandardSourceFields() {
    const select = document.getElementById('ta-int-standard-source');
    const uploadFields = document.getElementById('ta-int-standard-upload-fields');
    const urlFields = document.getElementById('ta-int-standard-url-fields');
    const localFields = document.getElementById('ta-int-standard-local-fields');
    if (!select || !uploadFields || !urlFields || !localFields) return;

    const source = select.value;
    uploadFields.hidden = source !== 'upload';
    urlFields.hidden = source !== 'url';
    localFields.hidden = source !== 'local';
    updateStandardConnectAvailability();
  }

  document.getElementById('ta-int-standard-source')?.addEventListener('change', updateStandardSourceFields);

  function initFieldToggles() {
    updateCodeProviderFields();
    updateCodeAuthFields();
    updateStandardSourceFields();
  }

  if (typeof onViewEnter === 'function') {
    onViewEnter('integrations', () => {
      initFieldToggles();
      if (!_loaded) load();
    });
  } else {
    document.addEventListener('DOMContentLoaded', () => {
      initFieldToggles();
      load();
    });
  }
})();
