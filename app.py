from __future__ import annotations

import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, Response, redirect, render_template_string, request, url_for

app = Flask(__name__)

_HTML = """
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>WebSpec2Doc</title>
  <style>
    :root { --navy: #00285E; --cyan: #009FCA; --gray: #F5F5F5; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: "Noto Sans JP","Meiryo",sans-serif; background: var(--gray); color: #333; }
    header { background: var(--navy); color: #fff; padding: 1.2rem 2rem; }
    header h1 { font-size: 1.4rem; }
    header p  { font-size: .85rem; opacity: .75; margin-top: .3rem; }
    main { max-width: 640px; margin: 2.5rem auto; padding: 0 1rem; }
    .card { background: #fff; border-radius: 8px; padding: 1.8rem 2rem; box-shadow: 0 1px 4px rgba(0,0,0,.1); }
    label { display: block; font-size: .9rem; font-weight: 600; margin-bottom: .35rem; margin-top: 1.2rem; }
    label:first-of-type { margin-top: 0; }
    input[type=url], input[type=number] {
      width: 100%; padding: .6rem .8rem; border: 1px solid #ccc;
      border-radius: 6px; font-size: 1rem;
    }
    .row { display: flex; gap: 1rem; }
    .row > div { flex: 1; }
    .checks { display: flex; gap: 1rem; margin-top: .4rem; }
    .checks label { font-weight: 400; display: flex; align-items: center; gap: .4rem; margin-top: 0; }
    button {
      margin-top: 1.8rem; width: 100%; padding: .85rem;
      background: var(--navy); color: #fff; border: none;
      border-radius: 6px; font-size: 1rem; cursor: pointer;
    }
    button:hover { background: #003f91; }
    .log-wrap { margin-top: 1.5rem; }
    pre {
      background: #1e1e1e; color: #d4d4d4; padding: 1rem;
      border-radius: 6px; font-size: .82rem; white-space: pre-wrap;
      max-height: 360px; overflow-y: auto;
    }
    .open-btn {
      display: none; margin-top: 1rem; width: 100%; padding: .75rem;
      background: var(--cyan); color: #fff; border: none;
      border-radius: 6px; font-size: 1rem; cursor: pointer; text-align: center;
      text-decoration: none;
    }
    .open-btn.show { display: block; }
    footer { text-align: center; color: #aaa; font-size: .8rem; padding: 2rem; }
  </style>
</head>
<body>
<header>
  <h1>WebSpec2Doc</h1>
  <p>URL を渡すだけで QA テストインプット文書を自動生成</p>
</header>
<main>
  <div class="card">
    <form id="form">
      <label>クロール対象 URL <span style="color:red">*</span></label>
      <input type="url" id="url" name="url" placeholder="https://example.com" required>

      <div class="row">
        <div>
          <label>深さ</label>
          <input type="number" id="depth" name="depth" value="2" min="1" max="5">
        </div>
        <div>
          <label>最大ページ数</label>
          <input type="number" id="max_pages" name="max_pages" value="30" min="1" max="200">
        </div>
      </div>

      <label>出力形式</label>
      <div class="checks">
        <label><input type="checkbox" name="fmt" value="html" checked> HTML レポート</label>
        <label><input type="checkbox" name="fmt" value="md"   checked> Markdown</label>
        <label><input type="checkbox" name="fmt" value="excel"> Excel</label>
      </div>

      <button type="submit" id="btn">生成する</button>
    </form>

    <div class="log-wrap" id="log-wrap" style="display:none">
      <pre id="log"></pre>
      <a id="open-btn" class="open-btn" target="_blank">レポートを開く</a>
    </div>
  </div>
</main>
<footer>WebSpec2Doc</footer>

<script>
const form = document.getElementById('form');
const logEl = document.getElementById('log');
const logWrap = document.getElementById('log-wrap');
const openBtn = document.getElementById('open-btn');
const btn = document.getElementById('btn');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fmts = [...document.querySelectorAll('input[name=fmt]:checked')].map(c => c.value);
  if (!fmts.length) { alert('出力形式を1つ以上選んでください'); return; }

  const body = new URLSearchParams({
    url: document.getElementById('url').value,
    depth: document.getElementById('depth').value,
    max_pages: document.getElementById('max_pages').value,
    format: fmts.join(','),
  });

  btn.disabled = true;
  btn.textContent = '実行中...';
  logEl.textContent = '';
  logWrap.style.display = 'block';
  openBtn.classList.remove('show');

  const res = await fetch('/run', { method: 'POST', body });
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let reportPath = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = dec.decode(value);
    // extract report path hint from stream
    const match = chunk.match(/REPORT_PATH:(.*)/);
    if (match) reportPath = match[1].trim();
    logEl.textContent += chunk.replace(/REPORT_PATH:.*\\n?/g, '');
    logEl.parentElement.scrollTop = logEl.scrollHeight;
  }

  btn.disabled = false;
  btn.textContent = '生成する';
  if (reportPath) {
    openBtn.href = '/open?path=' + encodeURIComponent(reportPath);
    openBtn.textContent = 'レポートを開く → ' + reportPath.split('/').slice(-2).join('/');
    openBtn.classList.add('show');
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
            yield "\nエラーが発生しました。上記のログを確認してください。\n"

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
