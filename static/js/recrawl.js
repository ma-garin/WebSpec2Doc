
// ---- 再クロール（ドリフト検知）: 既知のサイトを同じ画面構成で取り直す ----

async function recrawlSite(domain) {
  let site = null, urls = [], auth = getSettings().auth || '';
  try { site = (await fetch('/api/site?domain=' + encodeURIComponent(domain)).then(r => r.json())).site; } catch (e) {}
  if (site) {
    urls = site.urls || [];
    auth = site.auth_path || auth;
  } else {
    try {
      const data = await fetch('/api/result?domain=' + encodeURIComponent(domain)).then(r => r.json());
      if (data.files && data.files.json) {
        const rj = await fetch('/preview?path=' + encodeURIComponent(data.files.json)).then(r => r.json());
        urls = (rj.screens || []).map(s => ({ url: s.url, title: s.title || s.url }));
      }
    } catch (e) {}
  }
  if (!urls.length) urls = [{ url: 'https://' + domain + '/', title: domain }];

  // P2へ遷移して前回設定を復元
  switchView('generate');
  executionView.classList.add('hidden'); resultPanel.classList.add('hidden');
  appContent.classList.remove('is-executing'); genPanel.style.display = '';

  document.getElementById('url-input').value = 'https://' + domain + '/';
  if (auth) document.getElementById('auth-path').value = auth;
  document.getElementById('compare').checked = true;
  document.getElementById('p1-summary').style.display = 'none';

  // 前回の画面リストを復元
  discovered = (Array.isArray(urls) ? urls : []).map(u =>
    typeof u === 'string'
      ? { url: u, title: u, login_required: false, login_reasons: [], login_url: '' }
      : { url: u.url, title: u.title || u.url, login_required: false, login_reasons: [], login_url: '' }
  );
  renderDiscovered();
  updateTargetPreview();
  showWizardStep(2);
  showToast(`前回の対象画面（${discovered.length}件）を復元しました。条件を確認して実行してください`, 'info');
}

async function openResultsForDomain(domain) {
  switchView('generate');
  genPanel.style.display = 'none';
  executionView.classList.add('hidden');
  appContent.classList.add('is-executing');
  resultPanel.classList.remove('hidden');
  resultHero.innerHTML = '<div class="hero-msg">読み込み中…</div>';
  await showResults(domain);
}


