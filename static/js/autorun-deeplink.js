// AutoRun（System03）の deep link: /auto-run?site=<domain>
// 指揮のサイト一覧から入ったとき、入口でサイトを選び直させない。
// 登録済み（GET /api/history に出るサイト）なら、受付の URL・段階パイプライン・静的候補の探索をそのサイトで開く。
// 未登録・不正な値なら推測で別のサイトを開かず、その旨を出すだけにする。
(function () {
  'use strict';

  if (location.pathname !== '/auto-run') return;
  var site = '';
  try { site = (new URLSearchParams(location.search).get('site') || '').trim(); } catch (e) { site = ''; }
  if (!site) return;

  function host() {
    var h = document.getElementById('autorun-site-reason');
    if (h) return h;
    var form = document.getElementById('autorun-form-area');
    if (!form || !form.parentNode) return null;
    h = document.createElement('p');
    h.id = 'autorun-site-reason';
    form.parentNode.insertBefore(h, form);
    return h;
  }
  function say(text, kind) {
    var h = host();
    if (!h) return;
    if (window.WS2D) window.WS2D.reason(h, text, kind);
    else { h.setAttribute('role', 'status'); h.textContent = text; }
  }

  function open(item) {
    var url = document.getElementById('autorun-url');
    if (url && item.site_url && !url.value) {
      url.value = item.site_url;
      url.dispatchEvent(new Event('input', { bubbles: true }));
    }
    if (window.autorunStages && window.autorunStages.load) window.autorunStages.load(site);
    if (window.autorunStaticRoutes && window.autorunStaticRoutes.load) window.autorunStaticRoutes.load(site);
    say('指揮から開きました。対象サイト ' + site + '（最終解析 ' + (item.updated || '日時不明') + '）を選択済みです。' +
      '「開始」で同じサイトを実行し、下の「静的候補の探索」もこのサイトで開いています。', 'info');
  }

  function run() {
    if (!/^[A-Za-z0-9.\-]+(:\d{1,5})?$/.test(site)) {
      say('指定されたサイト「' + site + '」はサイト名として正しくないため開いていません。受付に URL を入れて始めてください。', 'warning');
      return;
    }
    fetch('/api/history', { headers: { Accept: 'application/json' }, cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (j) {
        var items = (j && j.items) || [];
        var hit = null;
        items.forEach(function (it) { if (it && it.domain === site) hit = it; });
        if (hit) { open(hit); return; }
        say('指定されたサイト「' + site + '」は登録されていません（解析結果がありません）。別のサイトを推測して開くことはしません。' +
          '受付に URL を入れて始めるか、指揮のサイト一覧から選び直してください。', 'warning');
      })
      .catch(function () {
        say('サイト「' + site + '」が登録済みか確認できませんでした（通信エラー）。サイトは開いていません。再読み込みしてください。', 'error');
      });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();
})();
