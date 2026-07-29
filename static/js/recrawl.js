
// ---- 再解析（ドリフト検知）: 既知のサイトを同じ画面構成で取り直す ----

// 再解析として始めた実行かどうかを、対象ドメインで覚えておく（P2-1）。
// 再解析の答えは「何が変わったか」なので、完了後は概要ではなく履歴・差分を最初に出す。
// 別サイトを解析したときに誤って差分タブが開かないよう、ドメイン一致を条件にする。
let pendingRecrawlDomain = '';

// 再解析の完了直後に一度だけ 'history' を返す。それ以外は undefined（＝従来どおり概要）。
function initialReportTabFor(domain) {
  if (!domain || pendingRecrawlDomain !== domain) return undefined;
  pendingRecrawlDomain = '';
  return 'history';
}

async function recrawlSite(domain) {
  let site = null, urls = [], auth = getSettings().auth || '';
  // 前回クロールで「認証が必要」と判定された画面の URL 集合とログインページ URL。
  // これを使わず一律 login_required:false で復元すると、再解析のたびに
  // 「認証が必要なページ」バナー直下のログインフォームが消える再発バグになる。
  let loginUrlSet = new Set(), loginLandingUrl = '';
  // noqa: fetch-error 取得できない場合は下の /api/result 経由の復元へフォールバックする
  try { site = (await fetch('/api/site?domain=' + encodeURIComponent(domain)).then(r => r.json())).site; } catch (e) {}
  if (site) {
    urls = site.urls || [];
    auth = site.auth_path || auth;
    loginUrlSet = new Set(site.login_urls || []);
    loginLandingUrl = site.login_landing_url || '';
  } else {
    try {
      const data = await fetch('/api/result?domain=' + encodeURIComponent(domain)).then(r => r.json());
      if (data.files && data.files.json) {
        const rj = await fetch('/preview?path=' + encodeURIComponent(data.files.json)).then(r => r.json());
        urls = (rj.screens || []).map(s => ({ url: s.url, title: s.title || s.url }));
      }
    } catch (e) {}
  }
  // 再解析の対象 URL は、前回実際に解析した URL をそのまま使う。
  // ドメイン名から 'https://' を組み立てると、http で公開されているサイト
  // （社内環境・ローカル検証・デモ）へ https で取りに行って全滅する。
  // しかも1画面も取れなくても画面には「生成完了」と出るため、失敗に気づけなかった。
  const firstUrl = urls.length ? (typeof urls[0] === 'string' ? urls[0] : urls[0].url) : '';
  const baseUrl = firstUrl || 'https://' + domain + '/';
  if (!urls.length) urls = [{ url: baseUrl, title: domain }];

  // P2へ遷移して前回設定を復元
  switchView('generate');
  executionView.classList.add('hidden'); resultPanel.classList.add('hidden');
  appContent.classList.remove('is-executing'); genPanel.style.display = '';

  document.getElementById('url-input').value = baseUrl;
  if (auth) document.getElementById('auth-path').value = auth;
  if (loginLandingUrl) document.getElementById('login-url').value = loginLandingUrl;
  document.getElementById('compare').checked = true;
  document.getElementById('p1-summary').style.display = 'none';

  // 前回の画面リストを復元（認証必須フラグも site.json から復元する）
  discovered = (Array.isArray(urls) ? urls : []).map(u => {
    const url = typeof u === 'string' ? u : u.url;
    const title = typeof u === 'string' ? u : (u.title || u.url);
    const loginRequired = loginUrlSet.has(url);
    return {
      url,
      title,
      login_required: loginRequired,
      login_reasons: [],
      login_url: loginRequired ? loginLandingUrl : '',
    };
  });
  renderDiscovered();
  // 解析方法（自動解析／選択したURLのみ）も前回設定から復元する。
  // renderDiscovered() が画面リストパネルの表示状態を上書きするため、その後に呼ぶ。
  setCrawlTargetMode(site && site.crawl_mode === 'auto' ? 'auto' : 'selected');
  showWizardStep(2);
  pendingRecrawlDomain = domain;
  showToast(`前回の対象画面（${discovered.length}件）を復元しました。条件を確認して実行してください`, 'info');
}

async function openResultsForDomain(domain, tab, sub) {
  switchView('generate');
  genPanel.style.display = 'none';
  executionView.classList.add('hidden');
  // レポート表示は is-reporting を使う（is-executing はクロール実行中専用の状態フラグ）。
  // 誤って is-executing を付けると、他画面へ移動しても解除されずスクロール不能になる不具合の温床だった。
  appContent.classList.remove('is-executing');
  appContent.classList.add('is-reporting');
  resultPanel.classList.remove('hidden');
  uiSkeleton(document.getElementById('rp-overview'), 'table');
  // ディープリンク: URLハッシュにレポート状態を保存（チーム共有用）
  try { history.replaceState(null, '', '#report/' + encodeURIComponent(domain)); } catch (e) {}
  await showResults(domain, tab, sub);
}

// ページロード時にハッシュ #report/<domain>[/<tab>[/<sub>]] があればそのレポートを直接開く
// （旧8タブ時代のタブ名は results.js の互換マップで新タブへ解決される）
window.addEventListener('DOMContentLoaded', () => {
  const m = location.hash.match(/^#report\/([^/]+)(?:\/([^/]+))?(?:\/([^/]+))?$/);
  if (m) {
    const domain = decodeURIComponent(m[1]);
    const tab = m[2] ? decodeURIComponent(m[2]) : undefined;
    const sub = m[3] ? decodeURIComponent(m[3]) : undefined;
    setTimeout(() => {
      openResultsForDomain(domain, tab, sub);
      window._appBooted = true;
    }, 300);
  } else {
    window._appBooted = true;
  }
});


