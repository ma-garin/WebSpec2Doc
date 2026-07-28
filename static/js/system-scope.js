// システムスコープ: ログイン後の「システム選択」で選んだ系（ドキュメント作成 / AutoRun）に応じて
// サイドバーを絞り込み、相手システムの画面を混ぜない。共通(common)は常に表示。
// 系の判定は「現在のパス優先 → sessionStorage → 既定 docs」。切替はシステム選択画面へ戻る。
(function () {
  'use strict';

  var KEY = 'webspec2doc.system';
  var AUTORUN_PATHS = { '/auto-run': 1, '/run-history': 1 };
  var DOCS_PATHS = {
    '/': 1, '/home': 1, '/dashboard': 1, '/generate': 1,
    '/testcases': 1, '/qa-quality': 1, '/viewpoints': 1,
  };

  function inferFromPath() {
    var p = location.pathname;
    if (AUTORUN_PATHS[p]) return 'autorun';
    if (DOCS_PATHS[p]) return 'docs';
    return null; // 共通ページ(/settings, /user-guide 等)は判定不能 → 保存値にフォールバック
  }

  function currentSystem() {
    var sys = inferFromPath();
    if (!sys) {
      try { sys = sessionStorage.getItem(KEY); } catch (e) { /* 非対応環境 */ }
    }
    if (sys !== 'autorun' && sys !== 'docs') sys = 'docs';
    try { sessionStorage.setItem(KEY, sys); } catch (e) { /* 非対応環境 */ }
    return sys;
  }

  function belongs(el, sys) {
    var s = el.getAttribute('data-system');
    return !s || s === 'common' || s === sys;
  }

  function apply(sys) {
    document.body.setAttribute('data-system', sys);

    // 対象外の項目（ナビ・グループ見出し・新規解析ボタン）を非表示
    var scoped = document.querySelectorAll('[data-system]');
    scoped.forEach(function (el) {
      if (el === document.body) return;
      el.style.display = belongs(el, sys) ? '' : 'none';
    });

    // 見出しだけ残って中身が無いグループは畳む
    document.querySelectorAll('.app-nav .app-nav-group').forEach(function (g) {
      if (g.style.display === 'none') return;
      var visible = false;
      var n = g.nextElementSibling;
      while (n && !n.classList.contains('app-nav-group')) {
        if (n.classList.contains('app-nav-item') && n.style.display !== 'none') { visible = true; break; }
        n = n.nextElementSibling;
      }
      g.style.display = visible ? '' : 'none';
    });

    // ブランドロゴのリンク先を各システムのホームに
    var brand = document.querySelector('.app-brand');
    if (brand) brand.setAttribute('href', sys === 'autorun' ? '/auto-run' : '/');

    // 切替UIの表示名
    var name = document.getElementById('sys-current-name');
    if (name) name.textContent = sys === 'autorun' ? 'AutoRun' : 'ドキュメント作成';

    // 切替リンク: セッションの系をクリアしてシステム選択へ
    var link = document.getElementById('sys-switcher-link');
    if (link && !link.dataset.bound) {
      link.dataset.bound = '1';
      link.addEventListener('click', function () {
        try { sessionStorage.removeItem(KEY); } catch (e) { /* 非対応環境 */ }
      });
    }
  }

  function boot() { apply(currentSystem()); }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
