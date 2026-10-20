// ドキュメント作成(app): ドキュメント作成の画面をそのまま使い、ステップ 1 の入力だけを
// アプリ向けに差し替える。選んだアプリを https://app.<package> として #url-input に同期し、
// 以降の画面解析・実行・レポートは URL 版と同じ JS（wizard.js / execution.js / results.js）が動く。
// サーバ側の切り替えは web/services/app_mock.py。
(function () {
  'use strict';
  if (!document.body.hasAttribute('data-app-mode')) return;

  // /doc-app を「新規解析」ビューの URL にする（core.js の対応表はここで差し替える）
  if (typeof VIEW_PATHS !== 'undefined') VIEW_PATHS.generate = '/doc-app';
  if (typeof PATH_VIEWS !== 'undefined') PATH_VIEWS['/doc-app'] = 'generate';
  // 見出しも試作であることを示す（URL 版の「サイトを追加 / 再解析」を出さない）
  var APP_HEADER = { trail: ['ダッシュボード', 'ドキュメント作成(app)［試作］'], title: 'サンプルで出力を見る（試作）' };
  if (typeof VIEW_HEADER !== 'undefined') VIEW_HEADER.generate = APP_HEADER;

  var DEVICES = {
    android: ['エミュレータ Pixel 8 (API 34)', '実機 (adb 接続)'],
    ios: ['iPhone 15 シミュレータ (iOS 17.5)', 'iPad (10th) シミュレータ']
  };

  function $(id) { return document.getElementById(id); }

  function sync() {
    var pkg = $('app-package'), url = $('url-input');
    if (!pkg || !url) return;
    url.value = 'https://app.' + pkg.value.split('.').pop();
    url.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function applyPlatform() {
    var sel = document.querySelector('input[name="app-platform"]:checked');
    var platform = sel ? sel.value : 'android';
    var file = $('app-file');
    if (file) file.setAttribute('accept', platform === 'ios' ? '.app,.zip' : '.apk,.aab');
    var dev = $('app-device');
    if (dev) {
      dev.innerHTML = '';
      DEVICES[platform].forEach(function (name) {
        var o = document.createElement('option'); o.textContent = name; dev.appendChild(o);
      });
    }
  }

  function boot() {
    var name = $('sys-current-name');
    if (name) name.textContent = 'ドキュメント作成(app)';
    var title = $('topbar-title');
    if (title && title.textContent === 'QAドキュメント生成') title.textContent = 'QAドキュメント生成（app）';
    // core.js は読み込み時に見出しを当て終えているため、生成画面ならここで当て直す
    var gen = $('view-generate');
    if (gen && gen.classList.contains('is-active') && typeof setHeader === 'function') setHeader(APP_HEADER.trail, APP_HEADER.title);
    applyPlatform();
    sync();
    document.querySelectorAll('input[name="app-platform"]').forEach(function (r) { r.addEventListener('change', applyPlatform); });
    var pkg = $('app-package');
    if (pkg) pkg.addEventListener('change', sync);
    // 「新規解析」ボタン（core.js の openAddSite）が #url-input を空にするので、押す直前に同期し直す
    var discover = $('discover-btn');
    if (discover) discover.addEventListener('click', sync, true);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
