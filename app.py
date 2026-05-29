from __future__ import annotations

import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, Response, redirect, render_template_string, request, url_for

app = Flask(__name__)

_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WebSpec2Doc</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --primary:      #0F62FE;
      --primary-dark: #0043CE;
      --text:         #161616;
      --text-muted:   #525252;
      --bg:           #F4F8FF;
      --surface:      #FFFFFF;
      --surface-soft: #F7FBFF;
      --border:       #C9D9EE;
      --ok:           #198038;
      --ok-bg:        #DEFBE6;
      --critical:     #DA1E28;
      --critical-bg:  #FFF1F1;
      --critical-border: #FFB3B8;
      --info-bg:      #EDF5FF;
      --info-border:  #A6C8FF;
      --focus-ring:   rgba(15, 98, 254, .18);
      --radius:       8px;
      --shadow:       0 1px 2px rgba(22,22,22,.06), 0 8px 20px rgba(15,98,254,.04);
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Sans', 'Noto Sans JP', sans-serif;
      background: var(--bg);
      color: var(--text);
      font-size: 15px;
      line-height: 1.6;
    }
    body.app-page { overflow: hidden; }

    /* ── シェル ── */
    .app-shell {
      height: 100vh;
      display: grid;
      grid-template-columns: 248px minmax(0, 1fr);
    }
    .app-sidebar {
      height: 100vh;
      overflow: auto;
      padding: 22px 16px;
      display: flex;
      flex-direction: column;
      gap: 18px;
      background: #EDF5FF;
      border-right: 1px solid var(--border);
    }
    .app-brand {
      color: var(--text);
      text-decoration: none;
      font-size: 20px;
      font-weight: 700;
      letter-spacing: -.01em;
    }
    .app-nav { display: grid; gap: 6px; }
    .app-nav-item {
      display: flex;
      align-items: center;
      min-height: 44px;
      padding: 0 14px;
      border-radius: var(--radius);
      color: var(--text);
      text-decoration: none;
      background: transparent;
      border: 1px solid transparent;
      font-size: 14px;
      transition: background .15s, border-color .15s;
    }
    .app-nav-item:hover { background: #fff; border-color: var(--info-border); }
    .app-nav-item.is-active {
      background: #fff;
      border-color: var(--info-border);
      color: var(--primary-dark);
      box-shadow: inset 4px 0 0 var(--primary);
      font-weight: 600;
    }
    .app-sidebar-section {
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: .06em;
      color: var(--text-muted);
      padding: 0 14px;
    }

    /* ── メイン ── */
    .app-main {
      min-width: 0;
      height: 100vh;
      display: flex;
      flex-direction: column;
    }
    .app-topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 30px;
      border-bottom: 1px solid var(--border);
      background: rgba(247,251,255,.96);
      backdrop-filter: blur(10px);
      flex-shrink: 0;
    }
    .app-topbar-kicker {
      color: var(--text-muted);
      font-size: 11px;
      font-weight: 800;
      letter-spacing: .06em;
      text-transform: uppercase;
      margin-bottom: 3px;
    }
    .app-topbar-title { font-size: 24px; font-weight: 700; line-height: 1.15; }
    .app-content { flex: 1; overflow: auto; padding: 28px 30px; }
    .app-content-inner { max-width: 760px; }
    .app-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 30px;
      border-top: 1px solid var(--border);
      background: rgba(247,251,255,.96);
      color: var(--text-muted);
      font-size: 12px;
      flex-shrink: 0;
    }

    /* ── フォームカード ── */
    .input-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 24px;
      box-shadow: var(--shadow);
      margin-bottom: 16px;
    }
    .form-label { display: block; font-size: 13px; font-weight: 700; margin-bottom: 8px; }
    .input-row { display: flex; gap: 8px; }
    .url-input {
      flex: 1;
      height: 44px;
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 0 12px;
      font-size: 15px;
      outline: none;
      background: var(--surface-soft);
      color: var(--text);
      transition: border-color .15s, box-shadow .15s;
    }
    .url-input:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px var(--focus-ring);
    }
    .input-hint { margin-top: 8px; font-size: 13px; color: var(--text-muted); }

    .options-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-top: 18px;
    }
    .options-grid .full { grid-column: 1 / -1; }
    .field { display: grid; gap: 6px; }
    .field label { font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: .04em; }
    .field input[type=number] {
      height: 40px;
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 0 12px;
      font-size: 14px;
      background: var(--surface-soft);
      color: var(--text);
      outline: none;
    }
    .field input[type=number]:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px var(--focus-ring);
    }
    .checkbox-group { display: flex; gap: 8px; flex-wrap: wrap; }
    .checkbox-chip {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      height: 36px;
      padding: 0 12px;
      border: 1px solid var(--border);
      border-radius: 4px;
      background: var(--surface);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: border-color .15s, background .15s, color .15s;
    }
    .checkbox-chip input { accent-color: var(--primary); width: 15px; height: 15px; }
    .checkbox-chip:has(input:checked) {
      border-color: var(--primary);
      background: var(--info-bg);
      color: var(--primary-dark);
    }

    /* ── ボタン ── */
    .btn-primary {
      height: 44px;
      padding: 0 22px;
      background: var(--primary);
      color: #fff;
      border: none;
      border-radius: 4px;
      font-size: 15px;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
      transition: background .15s;
    }
    .btn-primary:hover:not(:disabled) { background: var(--primary-dark); }
    .btn-primary:disabled { opacity: .5; cursor: not-allowed; }
    .btn-outline-sm {
      display: inline-flex;
      align-items: center;
      height: 36px;
      padding: 0 16px;
      border: 1px solid var(--border);
      border-radius: 4px;
      font-size: 13px;
      font-weight: 500;
      color: var(--text);
      background: var(--surface);
      text-decoration: none;
      transition: border-color .15s, background .15s, color .15s;
    }
    .btn-outline-sm:hover { border-color: var(--info-border); color: var(--primary-dark); background: var(--info-bg); }

    /* ── 実行パネル ── */
    .exec-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px 24px;
      box-shadow: var(--shadow);
      display: none;
    }
    .exec-card.show { display: block; }
    .exec-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 14px;
    }
    .exec-title { font-size: 16px; font-weight: 700; }
    .exec-elapsed { font-size: 22px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
    .exec-progress {
      width: 100%;
      height: 6px;
      border-radius: 2px;
      background: #D0E2FF;
      overflow: hidden;
      margin-bottom: 14px;
    }
    .exec-progress-bar {
      height: 100%;
      width: 5%;
      border-radius: inherit;
      background: linear-gradient(90deg, #0F62FE 0%, #4589FF 55%, #78A9FF 100%);
      transition: width .45s ease;
      position: relative;
      overflow: hidden;
    }
    .exec-progress-bar::after {
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,.42) 50%, transparent 100%);
      animation: shimmer 1.4s linear infinite;
    }
    .exec-steps {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 6px;
      margin-bottom: 14px;
    }
    .exec-step {
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 6px 8px;
      font-size: 11px;
      color: var(--text-muted);
      background: var(--surface-soft);
      text-align: center;
      transition: border-color .2s, background .2s, color .2s;
    }
    .exec-step.is-active { border-color: var(--info-border); background: var(--info-bg); color: var(--primary-dark); }
    .exec-step.is-complete { border-color: #bdddb0; background: var(--ok-bg); color: var(--ok); }
    pre#log {
      background: #1e1e1e;
      color: #d4d4d4;
      padding: 14px;
      border-radius: 6px;
      font-size: .8rem;
      white-space: pre-wrap;
      max-height: 260px;
      overflow-y: auto;
      margin-bottom: 12px;
    }
    .exec-complete {
      display: none;
      align-items: center;
      gap: 12px;
      padding: 12px 16px;
      border: 1px solid #bdddb0;
      border-radius: var(--radius);
      background: var(--ok-bg);
    }
    .exec-complete.show { display: flex; }
    .exec-complete-label {
      display: inline-flex;
      align-items: center;
      padding: 3px 9px;
      border-radius: 4px;
      background: var(--ok);
      color: #fff;
      font-size: 12px;
      font-weight: 800;
    }
    .exec-complete strong { font-size: 15px; color: var(--ok); }
    .exec-error {
      display: none;
      padding: 12px 16px;
      border: 1px solid var(--critical-border);
      border-radius: var(--radius);
      background: var(--critical-bg);
      color: var(--critical);
      font-size: 14px;
      font-weight: 700;
    }
    .exec-error.show { display: block; }
    .open-report-btn {
      display: none;
      height: 40px;
      padding: 0 18px;
      background: var(--primary);
      color: #fff;
      border: none;
      border-radius: 4px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      align-items: center;
      transition: background .15s;
    }
    .open-report-btn.show { display: inline-flex; }
    .open-report-btn:hover { background: var(--primary-dark); }

    .hidden { display: none !important; }
    @keyframes shimmer { from { transform: translateX(-100%); } to { transform: translateX(100%); } }
    @keyframes spin { to { transform: rotate(360deg); } }
    .spinner {
      width: 16px; height: 16px;
      border: 2px solid rgba(255,255,255,.4);
      border-top-color: #fff;
      border-radius: 50%;
      animation: spin .7s linear infinite;
      flex-shrink: 0;
      display: none;
    }
    .btn-primary.running .spinner { display: inline-block; }
    .btn-primary.running { display: inline-flex; align-items: center; gap: 8px; }
  </style>
</head>
<body class="app-page">
<div class="app-shell">

  <!-- サイドバー -->
  <aside class="app-sidebar">
    <a href="/" class="app-brand">WebSpec2Doc</a>
    <nav class="app-nav">
      <a href="/" class="app-nav-item is-active">ドキュメント生成</a>
    </nav>
    <div style="margin-top:auto">
      <p class="app-sidebar-section">出力先</p>
      <p style="font-size:12px;color:var(--text-muted);padding:8px 14px 0;line-height:1.6">
        output/{ドメイン名}/<br>に生成されます
      </p>
    </div>
  </aside>

  <!-- メイン -->
  <div class="app-main">
    <header class="app-topbar">
      <div>
        <p class="app-topbar-kicker">Generate</p>
        <h1 class="app-topbar-title">QA テストインプット文書を生成する</h1>
      </div>
      <div>
        <a href="https://github.com/ma-garin/WebSpec2Doc" target="_blank" class="btn-outline-sm">GitHub</a>
      </div>
    </header>

    <main class="app-content">
      <div class="app-content-inner">

        <!-- 入力フォーム -->
        <div class="input-card">
          <form id="form">
            <label for="url-input" class="form-label">クロール対象 URL <span style="color:#DA1E28">*</span></label>
            <div class="input-row">
              <input
                type="url"
                id="url-input"
                class="url-input"
                placeholder="https://example.com"
                required
                autocomplete="url"
              />
              <button type="submit" id="submit-btn" class="btn-primary">
                <span class="spinner" id="spinner"></span>
                <span id="btn-label">生成する</span>
              </button>
            </div>
            <p class="input-hint">公開されているページの URL を入力してください。ログインが必要なページは対象外です。</p>

            <div class="options-grid">
              <div class="field">
                <label for="depth">深さ</label>
                <input type="number" id="depth" value="2" min="1" max="5">
              </div>
              <div class="field">
                <label for="max-pages">最大ページ数</label>
                <input type="number" id="max-pages" value="30" min="1" max="200">
              </div>
              <div class="field full">
                <label>出力形式</label>
                <div class="checkbox-group">
                  <label class="checkbox-chip">
                    <input type="checkbox" name="fmt" value="html" checked> HTML レポート
                  </label>
                  <label class="checkbox-chip">
                    <input type="checkbox" name="fmt" value="md" checked> Markdown
                  </label>
                  <label class="checkbox-chip">
                    <input type="checkbox" name="fmt" value="excel"> Excel
                  </label>
                </div>
              </div>
            </div>
          </form>
        </div>

        <!-- 実行パネル -->
        <div class="exec-card" id="exec-card">
          <div class="exec-head">
            <span class="exec-title" id="exec-title">クロール中...</span>
            <span class="exec-elapsed" id="elapsed">0:00</span>
          </div>
          <div class="exec-progress"><div class="exec-progress-bar" id="progress-bar"></div></div>
          <div class="exec-steps">
            <div class="exec-step" id="step-crawl">クロール</div>
            <div class="exec-step" id="step-analyze">解析</div>
            <div class="exec-step" id="step-graph">グラフ構築</div>
            <div class="exec-step" id="step-output">出力生成</div>
          </div>
          <pre id="log"></pre>
          <div class="exec-complete" id="exec-complete">
            <span class="exec-complete-label">完了</span>
            <strong>ドキュメントを生成しました</strong>
            <a id="open-report-btn" class="open-report-btn show" target="_blank">レポートを開く</a>
          </div>
          <div class="exec-error" id="exec-error">エラーが発生しました。ログを確認してください。</div>
        </div>

      </div>
    </main>

    <footer class="app-footer">
      <span>WebSpec2Doc</span>
      <span>output/ フォルダに保存されます</span>
    </footer>
  </div>
</div>

<script>
const form = document.getElementById('form');
const logEl = document.getElementById('log');
const execCard = document.getElementById('exec-card');
const execComplete = document.getElementById('exec-complete');
const execError = document.getElementById('exec-error');
const openReportBtn = document.getElementById('open-report-btn');
const submitBtn = document.getElementById('submit-btn');
const btnLabel = document.getElementById('btn-label');
const spinner = document.getElementById('spinner');
const progressBar = document.getElementById('progress-bar');
const elapsedEl = document.getElementById('elapsed');
const execTitle = document.getElementById('exec-title');
const steps = ['step-crawl','step-analyze','step-graph','step-output'];

let timer, startTime;

function startTimer() {
  startTime = Date.now();
  timer = setInterval(() => {
    const s = Math.floor((Date.now() - startTime) / 1000);
    elapsedEl.textContent = Math.floor(s/60) + ':' + String(s%60).padStart(2,'0');
  }, 500);
}

function stopTimer() { clearInterval(timer); }

function setStep(idx) {
  steps.forEach((id, i) => {
    const el = document.getElementById(id);
    el.className = 'exec-step' + (i < idx ? ' is-complete' : i === idx ? ' is-active' : '');
  });
  progressBar.style.width = (10 + idx * 25) + '%';
}

function guessStep(line) {
  if (line.includes('クロール') || line.includes('crawl') || line.includes('ページ')) return 0;
  if (line.includes('解析') || line.includes('analyz')) return 1;
  if (line.includes('グラフ') || line.includes('graph') || line.includes('遷移')) return 2;
  if (line.includes('保存') || line.includes('report') || line.includes('出力') || line.includes('output')) return 3;
  return -1;
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fmts = [...document.querySelectorAll('input[name=fmt]:checked')].map(c => c.value);
  if (!fmts.length) { alert('出力形式を1つ以上選んでください'); return; }

  const body = new URLSearchParams({
    url: document.getElementById('url-input').value,
    depth: document.getElementById('depth').value,
    max_pages: document.getElementById('max-pages').value,
    format: fmts.join(','),
  });

  submitBtn.disabled = true;
  submitBtn.classList.add('running');
  btnLabel.textContent = '実行中';
  logEl.textContent = '';
  execCard.classList.add('show');
  execComplete.classList.remove('show');
  execError.classList.remove('show');
  openReportBtn.classList.remove('show');
  setStep(0);
  startTimer();

  let reportPath = '';
  let success = false;

  try {
    const res = await fetch('/run', { method: 'POST', body });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let currentStep = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = dec.decode(value);
      const match = chunk.match(/REPORT_PATH:(.*)/);
      if (match) { reportPath = match[1].trim(); success = true; }
      const clean = chunk.replace(/REPORT_PATH:.*\\n?/g, '');
      logEl.textContent += clean;
      logEl.scrollTop = logEl.scrollHeight;
      for (const line of clean.split('\\n')) {
        const s = guessStep(line);
        if (s >= 0 && s >= currentStep) { currentStep = s; setStep(s); }
      }
    }
  } catch (err) {
    logEl.textContent += '\\n通信エラー: ' + err.message;
  }

  stopTimer();
  progressBar.style.width = '100%';
  steps.forEach(id => {
    const el = document.getElementById(id);
    el.className = 'exec-step is-complete';
  });
  submitBtn.disabled = false;
  submitBtn.classList.remove('running');
  btnLabel.textContent = '生成する';

  if (success || reportPath) {
    execTitle.textContent = '完了';
    execComplete.classList.add('show');
    if (reportPath) {
      openReportBtn.href = '/open?path=' + encodeURIComponent(reportPath);
    }
  } else {
    execTitle.textContent = 'エラー';
    execError.classList.add('show');
  }
});
</script>
</body>
</html>
"""


@app.get("/")
def index() -> str:
    return render_template_string(_HTML)


@app.post("/run")
def run() -> Response:
    url = request.form.get("url", "").strip()
    depth = request.form.get("depth", "2")
    max_pages = request.form.get("max_pages", "30")
    fmt = request.form.get("format", "md,html")

    def generate():
        cmd = [
            sys.executable, "src/main.py",
            "--url", url,
            "--depth", depth,
            "--max-pages", max_pages,
            "--format", fmt,
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        report_path: str | None = None
        for line in proc.stdout:  # type: ignore[union-attr]
            yield line
            if "report.html" in line and report_path is None:
                report_path = line.split()[-1].strip()
        proc.wait()
        if report_path:
            yield f"REPORT_PATH:{report_path}\n"
        elif proc.returncode == 0:
            yield "\n完了しました。output/ フォルダを確認してください。\n"
        else:
            yield "\nエラーが発生しました。\n"

    return Response(generate(), mimetype="text/plain")


@app.get("/open")
def open_file() -> Response:
    path = request.args.get("path", "")
    if path and Path(path).exists():
        import subprocess as sp
        sp.Popen(["open", path])
    return redirect(url_for("index"))


def _open_browser() -> None:
    import time
    time.sleep(1.0)
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    app.run(debug=False)
