// ====================== 実行 ======================
const genPanel = document.getElementById('gen-panel');
const executionView = document.getElementById('execution-view');
const appContent = document.getElementById('app-content');
const execTitle = document.getElementById('exec-title');
const execMessage = document.getElementById('exec-message');
const execElapsed = document.getElementById('exec-elapsed');
const execProgressBar = document.getElementById('exec-progress-bar');
const execTarget = document.getElementById('exec-target');
const execPhase = document.getElementById('exec-phase');
const execLog = document.getElementById('exec-log');
const execError = document.getElementById('exec-error');
const execActions = document.getElementById('exec-actions');
const execRunningActions = document.getElementById('exec-running-actions');
const previewImage = document.getElementById('exec-preview-image');
const previewPlaceholder = document.getElementById('exec-preview-placeholder');
const estep = [0,1,2,3].map(i => document.getElementById('estep-' + i));
let timer, startTime, previewTimer, activeDomain = '';
let runAbort = null, lastRun = null, activeRunId = '';

function domainOf(url) { try { return new URL(url).host; } catch { return ''; } }
function startTimer() { startTime = Date.now(); timer = setInterval(() => { const s = Math.floor((Date.now() - startTime) / 1000); execElapsed.textContent = String(Math.floor(s / 60)).padStart(2,'0') + ':' + String(s % 60).padStart(2,'0'); }, 500); }
function stopTimer() { clearInterval(timer); }
function setStep(idx) { estep.forEach((el, i) => { el.className = 'execution-step' + (i < idx ? ' is-complete' : i === idx ? ' is-active' : ''); }); execProgressBar.style.width = (8 + idx * 23) + '%'; }
function guessStep(line) {
  if (line.includes('解析') || line.includes('analyz')) return 2;
  if (line.includes('グラフ') || line.includes('graph') || line.includes('保存') || line.includes('出力') || line.includes('完了')) return 3;
  if (line.includes('クロール') || line.includes('crawl') || line.includes('ページ')) return 1;
  return -1;
}
function startPreviewPolling() {
  if (!activeDomain) return;
  const poll = () => {
    const img = new Image();
    img.onload = () => { previewImage.src = img.src; previewImage.classList.add('show'); previewPlaceholder.classList.add('hidden'); };
    img.src = `/api/live-screenshot?domain=${encodeURIComponent(activeDomain)}&t=${Date.now()}`;
  };
  poll(); previewTimer = setInterval(poll, 1500);
}
function stopPreviewPolling() { clearInterval(previewTimer); }

document.getElementById('form').addEventListener('submit', (e) => {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (!url) { setUrlMessage('URL を入力してください', true); return; }
  const urls = buildTargetUrls();
  if (!urls.length) {
    setUrlMessage(discovered.length ? 'ドキュメント化する画面を1件以上選択してください' : '先に「画面分析」を実行してください', true);
    return;
  }
  const body = new URLSearchParams({
    urls: urls.join(','),
    depth: document.getElementById('crawl-depth').value,
    max_pages: document.getElementById('max-pages').value,
    format: 'html,pdf,md,excel,json',
    compare: document.getElementById('compare').checked ? 'true' : 'false',
    auth: document.getElementById('auth-path').value.trim() || getSettings().auth || '',
    crawl_mode: 'crawl',
  });
  const label = urls.length > 1 ? `${urls[0]} ほか ${urls.length - 1}件` : urls[0];
  runWith(body.toString(), domainOf(urls[0]), label, urls.length);
});

async function runWith(bodyStr, domain, label, urlCount) {
  lastRun = { bodyStr, domain, label, urlCount };
  activeDomain = domain;
  runAbort = new AbortController();
  genPanel.style.display = 'none';
  resultPanel.classList.add('hidden');
  executionView.classList.remove('hidden');
  appContent.classList.add('is-executing');
  showWizardStep(3);
  execError.classList.add('hidden'); execActions.classList.add('hidden');
  execRunningActions.classList.remove('hidden');
  const stopBtn = document.getElementById('exec-stop-btn');
  stopBtn.disabled = false; stopBtn.textContent = '停止';
  previewImage.classList.remove('show'); previewPlaceholder.classList.remove('hidden');
  execLog.textContent = '';
  execTarget.textContent = label;
  execTitle.textContent = 'クロール中…'; execMessage.textContent = `${urlCount}件の対象をクロールしてドキュメント化します。`;
  execPhase.textContent = '実行中'; setStep(0); startTimer(); startPreviewPolling();

  activeRunId = '';
  let reportPath = '', summary = null, ok = false, cur = 0, cancelled = false, sessionExpired = false;
  try {
    const res = await fetch('/run', { method: 'POST', body: bodyStr, headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, signal: runAbort.signal });
    const reader = res.body.getReader(); const dec = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      const chunk = dec.decode(value);
      const ri = chunk.match(/RUN_ID:(.*)/); if (ri) activeRunId = ri[1].trim();
      const rp = chunk.match(/REPORT_PATH:(.*)/); if (rp) { reportPath = rp[1].trim(); ok = true; }
      const sm = chunk.match(/SUMMARY:(.*)/); if (sm) { try { summary = JSON.parse(sm[1].trim()); ok = true; } catch {} }
      if (/(^|\\n)\\s*停止しました。/.test(chunk)) cancelled = true;
      if (/SESSION_EXPIRED/.test(chunk)) sessionExpired = true;
      const clean = chunk.replace(/(RUN_ID|REPORT_PATH|PDF_PATH|SUMMARY):.*\\n?/g, '');
      execLog.textContent += clean; execLog.scrollTop = execLog.scrollHeight;
      for (const line of clean.split('\\n')) { const st = guessStep(line); if (st >= 0 && st >= cur) { cur = st; setStep(st); } }
    }
  } catch (err) {
    if (err.name === 'AbortError') cancelled = true;
    else execLog.textContent += '\\n通信エラー: ' + err.message;
  }

  stopTimer(); stopPreviewPolling(); execRunningActions.classList.add('hidden');
  if (sessionExpired) {
    execActions.classList.remove('hidden');
    execTitle.textContent = 'セッションが失効しています'; execPhase.textContent = '要再ログイン';
    execMessage.textContent = '保存済みのログインセッションが失効していたため、ドリフト誤検知を防ぐためクロールを中断しました（前回の結果は保持されています）。入力に戻り「ログイン情報の設定」から再ログインしてください。';
  } else if (cancelled) {
    execActions.classList.remove('hidden');
    execTitle.textContent = '実行を停止しました'; execPhase.textContent = '停止';
    execMessage.textContent = '停止要求により処理を終了しました。必要に応じて入力に戻って再実行してください。';
  } else if (ok || reportPath) {
    setStep(4); execProgressBar.style.width = '100%';
    estep.forEach(el => el.className = 'execution-step is-complete');
    execTitle.textContent = '生成完了'; execPhase.textContent = '完了';
    execMessage.textContent = 'ドキュメントの生成が完了しました。';
    document.getElementById('btn-view-report').style.display = '';
    execActions.classList.remove('hidden');
    _showCompletionPopup(Math.floor((Date.now() - startTime) / 1000));
  } else {
    execActions.classList.remove('hidden');
    execTitle.textContent = 'エラー'; execPhase.textContent = 'エラー'; execError.classList.remove('hidden');
  }
}

document.getElementById('exec-stop-btn').addEventListener('click', async () => {
  const stopBtn = document.getElementById('exec-stop-btn');
  stopBtn.disabled = true; stopBtn.textContent = '停止中…';
  execMessage.textContent = '停止要求を送信しています…';
  // サーバ側のクロールプロセスを確実に終了させてから、クライアントの受信を中断する
  if (activeRunId) {
    try { await fetch('/api/cancel', { method: 'POST', body: new URLSearchParams({ run_id: activeRunId }) }); } catch (e) {}
  }
  if (runAbort) runAbort.abort();
});

document.getElementById('exec-new-btn').addEventListener('click', () => {
  switchView('generate');
  executionView.classList.add('hidden'); resultPanel.classList.add('hidden');
  appContent.classList.remove('is-executing'); genPanel.style.display = '';
  showWizardStep(2);
});
document.getElementById('r-new-btn').addEventListener('click', () => {
  document.body.classList.remove('result-maximized');
  switchView('dashboard');
});
document.getElementById('btn-view-report').addEventListener('click', () => showResults(activeDomain));
document.getElementById('r-recrawl-btn').addEventListener('click', () => {
  const domain = document.getElementById('r-domain').textContent.trim();
  if (domain && domain !== '-') recrawlSite(domain);
});

