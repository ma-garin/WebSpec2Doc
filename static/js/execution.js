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
  crawlProgress = {
    total: total || 0, finished: 0, completed: 0, skipped: 0, login: 0, failed: 0,
    saved: 0, parallelism: 1, durations: [],
    // 成果物の生成フェーズ（P1-1）。クロールが終わってからここが終わるまでが
    // 全体の約 25% を占めるため、残り時間に含める。
    gen: { started: false, steps: 0, done: 0, startedAt: 0, stepDurations: [], lastStepAt: 0 },
  };
  updateCrawlProgress();
}
//: 生成フェーズの 1 工程あたりの初期見積（秒）。実測が溜まればそちらを使う。
//  同梱デモ 6 画面で全 7 工程が約 5〜6 秒だったため 0.8 秒/工程から始める。
const GEN_STEP_SEC_INITIAL = 0.8;
// 1 秒刻みで数字が動くと落ち着いて待てず、見積もりの精度以上に正確そうな印象も与えるため丸める。
// 丸め幅は残り時間で変える: 1 画面あたり約2〜3秒（P1-2 実測）なので、一律 30 秒丸めにすると
// 数秒で終わる場面まで「約30秒」と過大に出てしまう。
function formatEta(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '算出中';
  if (seconds < 60) return `約${Math.max(10, Math.round(seconds / 10) * 10)}秒`;
  const rounded = Math.round(seconds / 30) * 30;
  const minutes = Math.floor(rounded / 60);
  return rounded % 60 === 0 ? `約${minutes}分` : `約${minutes}分30秒`;
}
function updateCrawlProgress() {
  if (!crawlProgress) return;
  const p = crawlProgress;
  // サーバの total は「クロール対象になる画面数」。除外（robots・ログイン必須・失敗）は
  // 分子にだけ数えるため、分母が分子を下回って「8 / 6」と出ないよう下限を合わせる。
  const total = Math.max(p.total, p.finished);
  execCount.textContent = `${p.finished} / ${total || '?'}`;
  execTitle.textContent = `解析中…（${p.finished}/${total || '?'}）`;
  execSkipped.textContent = `${p.skipped + p.login + p.failed}件`;
  execSkipped.title = `制約: ${p.skipped} / ログイン必須: ${p.login} / 失敗: ${p.failed}`;
  execSaved.textContent = `${p.saved}件`;
  // 1画面ぶんの実績だけで残り時間を出すと大きく外れるため、2画面完了するまでは「算出中」に留める。
  const average = (p.completed >= 2 && p.durations.length)
    ? p.durations.reduce((a, b) => a + b, 0) / p.durations.length
    : NaN;
  const remaining = Math.max(0, total - p.finished);
  const crawlEta = remaining * average / Math.max(1, p.parallelism);

  // 生成フェーズの残り。工程数が分かっているので、実測の 1 工程あたり時間で見積もる。
  // これを足さないと、クロールが終わった瞬間に「まもなく完了」と出したまま
  // 数秒待たせることになる（全体の約 25% を無視していた）。
  const g = p.gen || {};
  const genStepSec = g.stepDurations && g.stepDurations.length
    ? g.stepDurations.reduce((a, b) => a + b, 0) / g.stepDurations.length
    : GEN_STEP_SEC_INITIAL;
  const genRemainingSteps = Math.max(0, (g.steps || 0) - (g.done || 0));
  // まだ生成フェーズに入っていない場合も、工程数の既定値で先に織り込む
  const genEta = g.started ? genRemainingSteps * genStepSec : 7 * GEN_STEP_SEC_INITIAL;

  const totalEta = (Number.isFinite(crawlEta) ? crawlEta : NaN) + genEta;
  if (g.started && genRemainingSteps === 0) {
    execEta.textContent = 'まもなく完了';
  } else {
    execEta.textContent = formatEta(Number.isFinite(crawlEta) ? totalEta : NaN);
  }

  if (total > 0) execProgressBar.style.width = `${Math.min(76, 8 + (p.finished / total) * 68)}%`;
}
function handleCrawlEvent(event) {
  if (!event || !crawlProgress) return;
  const p = crawlProgress;
  // リンク追跡モードでは対象数がクロール中に判明していく。開始時の値だけを見ていると
  // 分母が古いまま残るため、total を運ぶイベントすべてで更新する。
  const reportedTotal = Number(event.total);
  if (Number.isFinite(reportedTotal) && reportedTotal > 0) p.total = reportedTotal;
  if (event.event === 'crawl_started') {
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
  } else if (event.event === 'generate_started') {
    // クロールは終わり、ここから成果物の生成（P1-1）
    p.gen.started = true;
    p.gen.steps = Number(event.total_steps) || 7;
    p.gen.startedAt = p.gen.lastStepAt = Date.now();
    execPhase.textContent = '成果物を生成中';
    setStep(3);
  } else if (event.event === 'generate_step' || event.event === 'generate_completed') {
    if (event.label) execMessage.textContent = `${event.label}…`;
    if (event.event === 'generate_completed') {
      p.gen.done = Number(event.index) || (p.gen.done + 1);
      const now = Date.now();
      if (p.gen.lastStepAt) p.gen.stepDurations.push((now - p.gen.lastStepAt) / 1000);
      if (p.gen.stepDurations.length > 5) p.gen.stepDurations.shift();
      p.gen.lastStepAt = now;
      // 生成フェーズの進み具合もバーに出す（76%〜96% を割り当てる）
      if (p.gen.steps > 0) {
        execProgressBar.style.width = `${76 + (p.gen.done / p.gen.steps) * 20}%`;
      }
    }
  }
  updateCrawlProgress();
}

// ---- URL履歴サジェスト（R3-15）: 実行済みURLを localStorage に保存し datalist へ反映する ----
const URL_HISTORY_KEY = 'wsd_url_history';
function _urlHistoryLimit() { return Number(getSettings().urlHistoryLimit ?? 10); }
function saveUrlHistory(url) {
  const limit = _urlHistoryLimit();
  if (!limit) { try { localStorage.removeItem(URL_HISTORY_KEY); } catch (_) {} return; }
  try {
    const cur = JSON.parse(localStorage.getItem(URL_HISTORY_KEY) || '[]');
    const next = [url, ...cur.filter(u => u !== url)].slice(0, limit);
    localStorage.setItem(URL_HISTORY_KEY, JSON.stringify(next));
  } catch (_) {}
}
// 解析済みサイト（サーバ側）のURL。localStorage はオリジン単位のため、
// ポート違い・別端末・シークレットウィンドウでは履歴が空になる。サーバの
// 解析実績を候補に混ぜて、どこから開いても過去のURLを選べるようにする。
let _serverUrlHistory = [];
async function loadServerUrlHistory() {
  try {
    const res = await fetch('/api/history');
    if (!res.ok) return;
    const data = await res.json();
    _serverUrlHistory = (data.items || []).map(it => it.site_url).filter(Boolean);
  } catch (_) { /* 履歴が取れなくても localStorage 分だけで動作させる */ }
}
function populateUrlHistory() {
  const list = document.getElementById('url-history-list');
  if (!list) return;
  const limit = _urlHistoryLimit();
  if (!limit) { list.replaceChildren(); return; }
  let items = [];
  try { items = JSON.parse(localStorage.getItem(URL_HISTORY_KEY) || '[]'); } catch (_) {}
  const merged = [...items.slice(0, limit)];
  for (const u of _serverUrlHistory) {
    if (merged.length >= limit * 2) break;
    if (!merged.includes(u)) merged.push(u);
  }
  list.replaceChildren(...merged.map(u => {
    const o = document.createElement('option'); o.value = u; return o;
  }));
}
populateUrlHistory();
loadServerUrlHistory().then(populateUrlHistory);
['url-input', 'hero-url'].forEach(id => {
  document.getElementById(id)?.addEventListener('focus', () => {
    populateUrlHistory();
    loadServerUrlHistory().then(populateUrlHistory);
  });
});

document.getElementById('form').addEventListener('submit', (e) => {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (!url) { setUrlMessage('URL を入力してください', true); return; }
  const mode = crawlTargetMode();
  const urls = buildTargetUrls();
  if (!urls.length) {
    const msg = mode === 'auto'
      ? 'URL を入力してください'
      : (discovered.length ? 'ドキュメント化する画面を1件以上選択してください' : '先に「画面解析」を実行してください');
    setUrlMessage(msg, true);
    return;
  }
  // 認証が必要な画面（再解析時にログインバナー・フォームを復元するため site.json に保存する）
  const loginUrlSet = new Set(urls);
  const loginUrls = discovered.filter(p => p.login_required && loginUrlSet.has(p.url)).map(p => p.url);
  const loginLandingUrl = discovered.find(p => p.login_required && p.login_url)?.login_url
    || document.getElementById('login-url').value.trim();
  const body = new URLSearchParams({
    urls: urls.join(','),
    depth: document.getElementById('crawl-depth').value,
    max_pages: document.getElementById('max-pages').value,
    parallelism: document.getElementById('crawl-parallelism')?.value || '2',
    format: 'html,pdf,md,excel,json',
    compare: document.getElementById('compare').checked ? 'true' : 'false',
    auth: document.getElementById('auth-path').value.trim() || getSettings().auth || '',
    crawl_mode: mode,
    reference_docs: referenceDocPaths.map(d => d.path).join(','),
    login_urls: loginUrls.join(','),
    login_landing_url: loginLandingUrl,
  });
  const label = urls.length > 1 ? `${urls[0]} ほか ${urls.length - 1}件` : urls[0];
  saveUrlHistory(url);
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
  execTitle.textContent = '解析中…'; execMessage.textContent = `${urlCount}件の対象をクロールしてドキュメント化します。`;
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
  } else if (crawlProgress?.saved === 0) {
    // 1 画面も保存できていないのに「生成完了」と出すと、失敗を成功と取り違える。
    // （http のサイトを https で取りに行って全滅しても完了と表示されていた）
    execActions.classList.remove('hidden');
    execTitle.textContent = '取得できた画面がありません'; execPhase.textContent = '失敗';
    execMessage.textContent =
      '対象 URL から1画面も取得できませんでした。URL のスキーム（http / https）・到達できるか・'
      + 'robots.txt の制限・ログインの要否を確認してください。';
    execError.classList.remove('hidden');
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
    try {
      await fetch('/api/cancel', { method: 'POST', body: new URLSearchParams({ run_id: activeRunId }) });
    } catch (e) {
      // 停止要求が届かないまま黙って「停止中…」で固まると、利用者は待ち続けてしまう。
      execMessage.textContent = '停止要求を送信できませんでした。サーバ側の処理が続いている可能性があります。';
    }
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
// ダッシュボードへの導線はトップバーのパンくず（ダッシュボード）に一本化した
// 再解析の完了直後だけ「履歴・差分」から開く（P2-1）。初回解析は従来どおり概要タブ。
document.getElementById('btn-view-report').addEventListener('click', () => showResults(activeDomain, initialReportTabFor(activeDomain)));
document.getElementById('r-recrawl-btn').addEventListener('click', () => {
  const domain = document.getElementById('r-domain').textContent.trim();
  if (domain && domain !== '-') recrawlSite(domain);
});
