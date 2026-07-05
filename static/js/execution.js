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
const execCount = document.getElementById('exec-count');
const execEta = document.getElementById('exec-eta');
const execSkipped = document.getElementById('exec-skipped');
const execSaved = document.getElementById('exec-saved');
const execLog = document.getElementById('exec-log');
const execError = document.getElementById('exec-error');
const execActions = document.getElementById('exec-actions');
const execRunningActions = document.getElementById('exec-running-actions');
const previewImage = document.getElementById('exec-preview-image');
const previewPlaceholder = document.getElementById('exec-preview-placeholder');
const estep = [0,1,2,3].map(i => document.getElementById('estep-' + i));
let timer, startTime, previewTimer, activeDomain = '';
let runAbort = null, lastRun = null, activeRunId = '';
let crawlProgress = null;

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

function resetCrawlProgress(total) {
  crawlProgress = { total: total || 0, finished: 0, completed: 0, skipped: 0, login: 0, failed: 0, saved: 0, parallelism: 1, durations: [] };
  updateCrawlProgress();
}
function formatEta(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '算出中';
  if (seconds < 60) return `約${Math.max(1, Math.ceil(seconds))}秒`;
  return `約${Math.ceil(seconds / 60)}分`;
}
function updateCrawlProgress() {
  if (!crawlProgress) return;
  const p = crawlProgress;
  execCount.textContent = `${p.finished} / ${p.total || '?'}`;
  execSkipped.textContent = `${p.skipped + p.login + p.failed}件`;
  execSkipped.title = `制約: ${p.skipped} / ログイン必須: ${p.login} / 失敗: ${p.failed}`;
  execSaved.textContent = `${p.saved}件`;
  const average = p.durations.length ? p.durations.reduce((a, b) => a + b, 0) / p.durations.length : NaN;
  const remaining = Math.max(0, p.total - p.finished);
  execEta.textContent = remaining === 0 && p.total ? 'まもなく完了' : formatEta(remaining * average / Math.max(1, p.parallelism));
  if (p.total > 0) execProgressBar.style.width = `${Math.min(76, 8 + (p.finished / p.total) * 68)}%`;
}
function handleCrawlEvent(event) {
  if (!event || !crawlProgress) return;
  const p = crawlProgress;
  if (event.event === 'crawl_started') {
    p.total = Number(event.total) || p.total;
    p.parallelism = Number(event.parallelism) || 1;
    execPhase.textContent = `解析中（${p.parallelism}並列）`;
  } else if (event.event === 'page_started') {
    execMessage.textContent = `${event.index || '?'}件目を解析中: ${event.url || ''}`;
    setStep(1);
  } else if (event.event === 'page_completed') {
    p.finished += 1; p.completed += 1;
    const duration = Number(event.elapsed_sec);
    if (Number.isFinite(duration) && duration > 0) p.durations.push(duration);
    if (p.durations.length > 5) p.durations.shift();
    setStep(2);
  } else if (event.event === 'page_skipped') {
    p.finished += 1; p.skipped += 1;
    const reason = event.reason === 'robots' ? 'robots.txt' : event.reason || '制約';
    execLog.textContent += `除外 (${reason}): ${event.url || ''}\n`;
  } else if (event.event === 'login_wall_detected') {
    p.finished += 1; p.login += 1;
    execLog.textContent += `ログイン必須として除外: ${event.url || ''}\n`;
  } else if (event.event === 'page_failed') {
    p.finished += 1; p.failed += 1;
  } else if (event.event === 'checkpoint_saved') {
    p.saved = Number(event.saved_count) || p.saved;
  } else if (event.event === 'crawl_cancelled') {
    execPhase.textContent = '途中結果を保存中';
  }
  updateCrawlProgress();
}

document.getElementById('form').addEventListener('submit', (e) => {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (!url) { setUrlMessage('URL を入力してください', true); return; }
  const mode = crawlTargetMode();
  const urls = buildTargetUrls();
  if (!urls.length) {
    const msg = mode === 'auto'
      ? 'URL を入力してください'
      : (discovered.length ? 'ドキュメント化する画面を1件以上選択してください' : '先に「画面分析」を実行してください');
    setUrlMessage(msg, true);
    return;
  }
  // 認証が必要な画面（再クロール時にログインバナー・フォームを復元するため site.json に保存する）
  const loginUrlSet = new Set(urls);
  const loginUrls = discovered.filter(p => p.login_required && loginUrlSet.has(p.url)).map(p => p.url);
  const loginLandingUrl = discovered.find(p => p.login_required && p.login_url)?.login_url
    || document.getElementById('login-url').value.trim();
  const body = new URLSearchParams({
    urls: urls.join(','),
    depth: document.getElementById('crawl-depth').value,
    max_pages: document.getElementById('max-pages').value,
    format: 'html,pdf,md,excel,json',
    compare: document.getElementById('compare').checked ? 'true' : 'false',
    auth: document.getElementById('auth-path').value.trim() || getSettings().auth || '',
    crawl_mode: mode,
    reference_docs: referenceDocPaths.map(d => d.path).join(','),
    login_urls: loginUrls.join(','),
    login_landing_url: loginLandingUrl,
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
  document.getElementById('btn-view-report').style.display = 'none';
  execRunningActions.classList.remove('hidden');
  const stopBtn = document.getElementById('exec-stop-btn');
  stopBtn.disabled = false; stopBtn.textContent = '停止';
  previewImage.classList.remove('show'); previewPlaceholder.classList.remove('hidden');
  execLog.textContent = '';
  execTarget.textContent = label;
  execTitle.textContent = 'クロール中…'; execMessage.textContent = `${urlCount}件の対象をクロールしてドキュメント化します。`;
  execPhase.textContent = '実行中'; setStep(0); startTimer(); startPreviewPolling();
  resetCrawlProgress(urlCount);

  activeRunId = '';
  let reportPath = '', summary = null, ok = false, cur = 0, cancelled = false, sessionExpired = false;
  try {
    const res = await fetch('/run', { method: 'POST', body: bodyStr, headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, signal: runAbort.signal });
    const reader = res.body.getReader(); const dec = new TextDecoder(); let streamBuf = '';
    const processLine = (line) => {
      if (!line) return;
      if (line.startsWith('RUN_ID:')) { activeRunId = line.slice(7).trim(); return; }
      if (line.startsWith('REPORT_PATH:')) { reportPath = line.slice(12).trim(); ok = true; return; }
      if (line.startsWith('PDF_PATH:')) return;
      if (line.startsWith('SUMMARY:')) { try { summary = JSON.parse(line.slice(8).trim()); ok = true; } catch {} return; }
      if (line.startsWith('CRAWL_EVENT:')) { try { handleCrawlEvent(JSON.parse(line.slice(12))); } catch {} return; }
      if (line.trim() === 'CRAWL_CANCELLED' || line.trim() === '停止しました。') { cancelled = true; return; }
      if (line.includes('SESSION_EXPIRED')) { sessionExpired = true; return; }
      execLog.textContent += line + '\n'; execLog.scrollTop = execLog.scrollHeight;
      const st = guessStep(line); if (st >= 0 && st >= cur) { cur = st; setStep(st); }
    };
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      streamBuf += dec.decode(value, { stream: true });
      const lines = streamBuf.split('\n'); streamBuf = lines.pop() || '';
      lines.forEach(processLine);
    }
    processLine(streamBuf);
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
    execMessage.textContent = `${crawlProgress?.saved || 0}画面の途中結果を保存して停止しました。`;
    if (reportPath) document.getElementById('btn-view-report').style.display = '';
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
  } else if (runAbort) {
    runAbort.abort();
  }
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
