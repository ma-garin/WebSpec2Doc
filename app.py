from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from dataclasses import asdict

from flask import Flask, Response, redirect, request, send_file, url_for

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from registry.site_registry import SiteConfig, load_site, save_site  # noqa: E402
from registry.session_store import (  # noqa: E402
    has_session,
    session_path,
    signal_path,
)

app = Flask(__name__)


@app.before_request
def _csrf_guard() -> Response | None:
    """状態変更(POST)は同一オリジンのみ許可。ブラウザに開かれた悪意ページからの
    localhost への cross-site POST を防ぐ簡易CSRF対策。"""
    if request.method != "POST":
        return None
    origin = request.headers.get("Origin") or request.headers.get("Referer") or ""
    if origin and request.host not in origin:
        return Response(status=403)
    return None


OUTPUT_DIR = Path("output")
SCREEN_ROW_RE = re.compile(r"^\|\s*\d+\s*\|")
ENV_FILE = Path(".env")
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DISCOVER_TIMEOUT_SEC = 180
LOGIN_FINISH_TIMEOUT_SEC = 60

# 入力検証（多層防御: クライアントだけでなくサーバでも検証する）
ALLOWED_FORMATS = ("md", "html", "excel", "pdf", "json")
DOMAIN_RE = re.compile(r"^[A-Za-z0-9._:-]{1,253}$")
ENV_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
MAX_DEPTH = 5
MAX_PAGES_LIMIT = 300


def _clean_int(value: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _clean_formats(raw: str) -> list[str]:
    picked = [f.strip().lower() for f in raw.split(",") if f.strip()]
    return [f for f in picked if f in ALLOWED_FORMATS]


def _valid_domain(domain: str) -> bool:
    return bool(DOMAIN_RE.match(domain))


def _safe_auth_path(raw: str) -> str:
    """auth.json はプロジェクト配下のファイルのみ許可（任意ファイル読み取りを防ぐ）。"""
    if not raw:
        return ""
    try:
        target = Path(raw).resolve()
    except (OSError, ValueError, RuntimeError):
        return ""
    base = Path.cwd().resolve()
    if (target == base or base in target.parents) and target.is_file():
        return str(target)
    return ""

# 実行中クロールのサブプロセス（run_id → Popen）。停止ボタンから kill するために保持。
_RUNNING_PROCS: dict[str, subprocess.Popen] = {}


def _terminate_proc(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

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
      --text:         #111827;
      --text-muted:   #6B7280;
      --text-subtle:  #9CA3AF;
      --bg:           #F7F8FA;
      --surface:      #FFFFFF;
      --surface-soft: #F9FAFB;
      --surface-subtle:#F2F4F7;
      --border:       #E5E7EB;
      --border-strong:#D1D5DB;
      --ok:           #1F8A4C;
      --ok-bg:        #E7F4EC;
      --ok-border:    #A7E0BD;
      --warning:      #B45309;
      --warning-bg:   #FEF6E7;
      --warning-border:#FCD9A0;
      --critical:     #D32F2F;
      --critical-bg:  #FDECEC;
      --critical-border: #F5B5B5;
      --info:         #0F62FE;
      --info-bg:      #EFF4FF;
      --info-border:  #C7D7FE;
      --primary-pale: #DCE7FB;
      --accent:       #6E56CF;
      --focus-ring:   rgba(15, 98, 254, .16);
      --radius:       6px;
      --radius-lg:    8px;
      --shadow-sm:    0 1px 2px rgba(16,24,40,.05);
      --shadow:       0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.08);
      --shadow-pop:   0 10px 24px rgba(16,24,40,.12), 0 2px 6px rgba(16,24,40,.08);
      --sidebar-w:    256px;
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Sans', 'Noto Sans JP', sans-serif;
      background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.6;
      -webkit-font-smoothing: antialiased;
    }
    body.app-page { overflow: hidden; }
    .app-shell { height: 100vh; display: grid; grid-template-columns: var(--sidebar-w) minmax(0, 1fr); }

    /* ── サイドバー ── */
    .app-sidebar {
      height: 100vh; overflow: auto; padding: 16px 12px;
      display: flex; flex-direction: column; gap: 14px;
      background: var(--surface); border-right: 1px solid var(--border);
    }
    .app-brand { display: flex; align-items: center; gap: 10px; padding: 4px 8px; color: var(--text); text-decoration: none; }
    .app-brand-mark {
      width: 28px; height: 28px; border-radius: 7px; flex-shrink: 0;
      background: linear-gradient(135deg, var(--primary) 0%, #4589FF 100%);
      display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 800; font-size: 15px;
      box-shadow: var(--shadow-sm);
    }
    .app-brand-text { display: grid; line-height: 1.15; }
    .app-brand-text strong { font-size: 15px; font-weight: 700; letter-spacing: -.01em; }
    .app-brand-text span { font-size: 10px; color: var(--text-subtle); font-weight: 600; letter-spacing: .02em; }
    .app-nav { display: grid; gap: 2px; }
    .app-nav-item {
      display: flex; align-items: center; gap: 10px; min-height: 38px; padding: 0 10px;
      border-radius: var(--radius); color: var(--text-muted); text-decoration: none;
      background: transparent; border: 0; font-size: 13.5px; font-weight: 600; width: 100%;
      cursor: pointer; transition: background .12s, color .12s;
    }
    .app-nav-item svg { width: 17px; height: 17px; flex-shrink: 0; opacity: .85; }
    .app-nav-item:hover { background: var(--surface-subtle); color: var(--text); }
    .app-nav-item.is-active { background: var(--info-bg); color: var(--primary-dark); }
    .app-nav-item.is-active svg { opacity: 1; }
    .app-nav-group { font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .07em; color: var(--text-muted); padding: 10px 10px 2px; }
    .result-collapsible > summary { font-size: 13px; font-weight: 700; color: var(--text-muted); cursor: pointer; padding: 2px 0; }
    .app-sidebar-section { font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: .07em; color: var(--text-subtle); padding: 0 10px; }
    .app-sidebar-foot { font-size: 11.5px; color: var(--text-muted); line-height: 1.6; padding: 0 10px; }
    .app-sidebar-foot a { color: var(--text-muted); }

    .app-main { min-width: 0; height: 100vh; display: flex; flex-direction: column; background: var(--bg); }

    /* ── ヘッダー（文脈：パンくず＋タイトル＋主要アクション）── */
    .app-topbar {
      display: flex; align-items: center; justify-content: space-between; gap: 16px;
      padding: 14px 28px; border-bottom: 1px solid var(--border);
      background: var(--surface); flex-shrink: 0;
    }
    .app-breadcrumb { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-subtle); font-weight: 600; margin-bottom: 2px; }
    .app-breadcrumb a { color: var(--text-muted); text-decoration: none; cursor: pointer; }
    .app-breadcrumb a:hover { color: var(--primary-dark); }
    .app-breadcrumb .sep { color: var(--border-strong); }
    .app-topbar-title { font-size: 20px; font-weight: 700; line-height: 1.2; letter-spacing: -.01em; }
    .app-topbar-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
    .app-topbar-actions:empty { display: none; }
    .app-content { flex: 1; overflow: auto; padding: 28px 30px; }
    .app-content-inner { max-width: 880px; }
    .app-content.is-executing { overflow: hidden; padding: 16px 20px; height: 100%; }
    .app-content.is-executing .app-content-inner { height: 100%; max-width: none; }
    .app-content.is-executing .view.is-active { height: 100%; }
    .view { display: none; }
    .view.is-active { display: block; }
    .input-card {
      background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
      padding: 24px; box-shadow: var(--shadow); margin-bottom: 16px;
    }
    .form-label { display: block; font-size: 13px; font-weight: 700; margin-bottom: 8px; }
    .input-row { display: flex; gap: 8px; }
    .url-input {
      flex: 1; height: 44px; border: 1px solid var(--border); border-radius: 4px;
      padding: 0 12px; font-size: 15px; outline: none; background: var(--surface-soft);
      color: var(--text); transition: border-color .15s, box-shadow .15s;
    }
    .url-input:focus { border-color: var(--primary); box-shadow: 0 0 0 3px var(--focus-ring); }
    .input-hint { margin-top: 8px; font-size: 13px; color: var(--text-muted); }
    .input-field-message { margin-top: 8px; min-height: 18px; font-size: 13px; font-weight: 700; color: var(--text-muted); }
    .input-field-message-error { color: var(--critical); }
    .field { display: grid; gap: 6px; }
    .field label { font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: .04em; }
    .field input[type=number], .field input[type=text], .field input[type=url], .field input[type=password] {
      height: 40px; border: 1px solid var(--border); border-radius: 4px; padding: 0 12px;
      font-size: 14px; background: var(--surface-soft); color: var(--text); outline: none; width: 100%;
    }
    .field input:focus { border-color: var(--primary); box-shadow: 0 0 0 3px var(--focus-ring); }
    .checkbox-group { display: flex; gap: 8px; flex-wrap: wrap; }
    .checkbox-chip {
      display: inline-flex; align-items: center; gap: 7px; height: 36px; padding: 0 12px;
      border: 1px solid var(--border); border-radius: 4px; background: var(--surface);
      font-size: 13px; font-weight: 600; cursor: pointer;
      transition: border-color .15s, background .15s, color .15s;
    }
    .checkbox-chip input { accent-color: var(--primary); width: 15px; height: 15px; }
    .checkbox-chip:has(input:checked) { border-color: var(--primary); background: var(--info-bg); color: var(--primary-dark); }
    .btn-primary {
      display: inline-flex; align-items: center; justify-content: center;
      height: 40px; padding: 0 18px; background: var(--primary); color: #fff;
      border: none; border-radius: var(--radius); font-size: 14px; font-weight: 600;
      cursor: pointer; white-space: nowrap; box-shadow: var(--shadow-sm);
      transition: background .12s, box-shadow .12s;
    }
    .btn-primary:hover:not(:disabled) { background: var(--primary-dark); }
    .btn-primary:disabled { opacity: .5; cursor: not-allowed; box-shadow: none; }
    .btn-outline-sm {
      display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px;
      border: 1px solid var(--border-strong); border-radius: var(--radius); font-size: 13px; font-weight: 600;
      color: var(--text); background: var(--surface); text-decoration: none; cursor: pointer;
      transition: border-color .12s, background .12s, color .12s;
    }
    .btn-outline-sm:hover { border-color: var(--border-strong); color: var(--primary-dark); background: var(--surface-subtle); }
    .btn-outline-sm:disabled { opacity: .45; cursor: not-allowed; }
    .btn-primary:focus-visible, .btn-outline-sm:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }

    /* ── ウィザード ── */
    .wizard-progress { display: flex; align-items: center; gap: 6px; margin-bottom: 22px; }
    .wizard-step-node { display: flex; align-items: center; gap: 8px; }
    .wizard-step-circle {
      width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
      border: 2px solid var(--border); background: var(--surface); color: var(--text-muted);
      font-size: 13px; font-weight: 800; flex-shrink: 0;
    }
    .wizard-step-node.is-active .wizard-step-circle { border-color: var(--primary); background: var(--primary); color: #fff; }
    .wizard-step-node.is-done .wizard-step-circle { border-color: var(--ok); background: var(--ok); color: #fff; }
    .wizard-step-label { font-size: 13px; font-weight: 700; color: var(--text-muted); white-space: nowrap; }
    .wizard-step-node.is-active .wizard-step-label { color: var(--primary-dark); }
    .wizard-step-line { flex: 1; height: 2px; background: var(--border); border-radius: 2px; min-width: 16px; }
    .wizard-step-line.is-done { background: var(--ok); }
    .wizard-page { display: none; }
    .wizard-page.is-active { display: block; }
    .wizard-page-header { margin-bottom: 16px; }
    .wizard-page-header h2 { font-size: 18px; line-height: 1.3; }
    .wizard-page-header p { color: var(--text-muted); font-size: 13px; margin-top: 4px; }
    .wizard-section { margin-bottom: 18px; }
    .wizard-footer { display: flex; align-items: center; gap: 10px; margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--border); }
    .wizard-footer .btn-primary { margin-left: auto; }
    .wizard-footer .btn-outline-sm + .btn-primary { margin-left: auto; }

    /* ── クロールモード ── */
    .crawl-mode-group { display: grid; gap: 10px; }
    .crawl-mode-option {
      display: flex; align-items: flex-start; gap: 10px; cursor: pointer; padding: 10px 12px;
      border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-soft);
      transition: border-color .15s, background .15s;
    }
    .crawl-mode-option:has(input:checked) { border-color: var(--primary); background: var(--info-bg); }
    .crawl-mode-option input[type=radio] { margin-top: 3px; flex-shrink: 0; accent-color: var(--primary); }
    .crawl-mode-label { display: flex; flex-direction: column; gap: 2px; }
    .crawl-mode-label strong { font-size: 14px; }
    .crawl-mode-desc { font-size: 12px; color: var(--text-muted); }
    .crawl-depth-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 4px 0 4px 30px; }
    .crawl-depth-label { font-size: 13px; color: var(--text-muted); }
    .crawl-depth-input { width: 64px; height: 36px; border: 1px solid var(--border); border-radius: 4px; padding: 0 8px; font-size: 14px; text-align: center; outline: none; background: var(--surface-soft); }
    .crawl-depth-input:focus { border-color: var(--primary); box-shadow: 0 0 0 3px var(--focus-ring); }
    .crawl-depth-unit { font-size: 13px; color: var(--text-muted); }
    .crawl-discovery-section { display: grid; gap: 10px; padding-left: 30px; }
    .discover-loading { display: flex; align-items: center; gap: 10px; padding: 12px; border: 1px solid var(--info-border); border-radius: var(--radius); background: var(--info-bg); color: var(--primary-dark); font-size: 13px; font-weight: 700; }
    .discover-status { min-height: 18px; font-size: 13px; color: var(--text-muted); }
    .discover-status-error { color: var(--critical); font-weight: 700; }
    .section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .discovered-url-actions { display: flex; gap: 8px; }
    .discovered-url-panel { display: grid; gap: 8px; padding: 12px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-soft); }
    .discovered-url-list { display: grid; gap: 6px; max-height: 260px; overflow: auto; }
    .discovered-url-item { display: grid; grid-template-columns: 18px minmax(0,1fr); gap: 10px; align-items: flex-start; padding: 10px 12px; border: 1px solid var(--border); border-radius: 4px; background: var(--surface); cursor: pointer; }
    .discovered-url-item input { width: 16px; height: 16px; margin-top: 3px; accent-color: var(--primary); }
    .discovered-url-item span { display: grid; gap: 2px; min-width: 0; }
    .discovered-url-item strong { font-size: 12px; }
    .discovered-url-item code { font-family: ui-monospace, monospace; font-size: 12px; color: var(--text-muted); word-break: break-all; }
    .disc-login-badge { display: inline-block; width: fit-content; margin-top: 2px; font-size: 11px; font-weight: 600; color: #8a4b00; background: #fff3e0; border: 1px solid #ffcc80; border-radius: 999px; padding: 1px 8px; cursor: help; }
    .manual-url-section { display: grid; gap: 8px; padding-left: 30px; }
    .url-list { display: grid; gap: 8px; }
    .url-list-item { display: flex; gap: 8px; align-items: center; }
    .url-list-input { flex: 1; }
    .url-list-remove { flex-shrink: 0; }
    .target-preview { margin-top: 14px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-soft); padding: 12px; display: grid; gap: 8px; }
    .target-preview strong { font-size: 13px; }
    .target-preview ol { margin: 0; padding-left: 20px; display: grid; gap: 6px; }
    .target-preview li { font-size: 12px; color: var(--text-muted); }
    .target-preview li span { display: inline-block; min-width: 76px; font-weight: 800; color: var(--text); }
    .target-preview code { font-family: ui-monospace, monospace; color: var(--text-muted); word-break: break-all; }
    .login-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .login-field-full { grid-column: 1 / -1; }

    /* ── 実行ビュー ── */
    .execution-view { height: 100%; display: flex; flex-direction: column; gap: 10px; }
    .execution-view.hidden { display: none; }
    .execution-topbar { flex-shrink: 0; background: rgba(255,255,255,.96); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px 16px; display: flex; flex-direction: column; gap: 8px; }
    .execution-topbar-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
    .execution-title { font-size: 17px; font-weight: 700; line-height: 1.2; }
    .execution-message { font-size: 12px; color: var(--text-muted); margin: 0; }
    .execution-elapsed { font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; flex-shrink: 0; }
    .execution-progress { width: 100%; height: 6px; border-radius: 2px; background: var(--primary-pale); overflow: hidden; }
    .execution-progress-bar { height: 100%; width: 4%; border-radius: inherit; background: linear-gradient(90deg,#0F62FE 0%,#4589FF 55%,#78A9FF 100%); transition: width .45s ease; position: relative; overflow: hidden; }
    .execution-progress-bar::after { content: ''; position: absolute; inset: 0; background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,.42) 50%, transparent 100%); animation: shimmer 1.4s linear infinite; }
    .execution-steps { display: grid; grid-template-columns: repeat(4,1fr); gap: 6px; }
    .execution-step { border: 1px solid var(--border); border-radius: 4px; padding: 5px 8px; font-size: 11px; color: var(--text-muted); background: var(--surface-soft); text-align: center; transition: border-color .2s, background .2s, color .2s; }
    .execution-step.is-active { border-color: var(--info-border); background: var(--info-bg); color: var(--primary-dark); }
    .execution-step.is-complete { border-color: #bdddb0; background: var(--ok-bg); color: var(--ok); }
    .execution-preview-frame { flex: 1; min-height: 0; border-radius: var(--radius); overflow: hidden; border: 1px solid var(--border); background: var(--primary-pale); display: flex; align-items: center; justify-content: center; }
    .execution-preview-image { display: none; width: 100%; height: 100%; object-fit: contain; background: var(--info-bg); }
    .execution-preview-image.show { display: block; }
    .execution-preview-placeholder { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: var(--text-muted); text-align: center; padding: 20px; }
    .execution-preview-placeholder.hidden { display: none; }
    .execution-log { flex-shrink: 0; background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px; font-size: .78rem; white-space: pre-wrap; max-height: 220px; overflow-y: auto; }
    .execution-error-card { flex-shrink: 0; border: 1px solid var(--critical-border); background: var(--critical-bg); color: var(--critical); border-radius: var(--radius); padding: 12px 16px; font-size: 14px; font-weight: 700; }
    .execution-error-card.hidden { display: none; }
    .execution-bottombar { flex-shrink: 0; background: rgba(255,255,255,.96); border: 1px solid var(--border); border-radius: var(--radius); padding: 10px 16px; display: flex; align-items: center; gap: 12px; }
    .execution-meta-list { display: flex; gap: 20px; flex: 1; min-width: 0; }
    .execution-meta-item { min-width: 0; }
    .execution-meta-item dt { font-size: 10px; font-weight: 800; color: var(--text-muted); letter-spacing: .06em; text-transform: uppercase; }
    .execution-meta-item dd { font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 420px; }
    .execution-bottombar-actions { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
    .execution-bottombar-actions.hidden { display: none; }
    .spinner { width: 18px; height: 18px; border: 2px solid var(--border); border-top-color: var(--primary); border-radius: 50%; animation: spin .7s linear infinite; flex-shrink: 0; }
    .spinner-light { border-color: rgba(255,255,255,.4); border-top-color: #fff; }

    /* ── 結果ページ ── */
    .result-panel { height: 100%; display: flex; flex-direction: column; gap: 10px; }
    .result-panel.hidden { display: none; }
    .result-summary { flex-shrink: 0; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px; }
    .result-summary-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
    .result-ok { display: inline-flex; align-items: center; padding: 3px 9px; border-radius: 4px; background: var(--ok-bg); color: var(--ok); font-size: 12px; font-weight: 800; }
    .result-summary-head strong { font-size: 15px; word-break: break-all; }
    .result-stats { display: grid; grid-template-columns: repeat(5,1fr); gap: 10px; }
    .result-stats > div { border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-soft); padding: 10px; text-align: center; display: grid; gap: 2px; }
    .result-stats .num { font-size: 22px; font-weight: 800; color: var(--primary-dark); }
    .result-stats span:last-child { font-size: 11px; color: var(--text-muted); }
    .result-bar { flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
    .result-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
    .result-tab { height: 34px; padding: 0 14px; border: 1px solid var(--border); border-radius: 4px; background: var(--surface-soft); color: var(--text-muted); font-size: 13px; font-weight: 700; cursor: pointer; }
    .result-tab.is-active { border-color: var(--primary); background: var(--info-bg); color: var(--primary-dark); }
    .result-bar-actions { display: flex; gap: 8px; align-items: center; }
    .result-hero { flex: 1; min-height: 0; border: 1px solid var(--border); border-radius: var(--radius); overflow: auto; background: var(--surface); }
    .result-hero iframe { width: 100%; height: 100%; border: 0; display: block; }
    .result-hero pre { margin: 0; padding: 16px; font-size: .8rem; white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, monospace; color: var(--text); }
    .result-hero .hero-msg { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 12px; color: var(--text-muted); text-align: center; padding: 20px; }
    .hero-pad { padding: 16px; }
    .hero-section-title { font-size: 14px; font-weight: 800; color: var(--primary-dark); margin: 4px 0 10px; }
    /* マトリクス */
    .matrix-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; padding: 12px 14px; background: var(--surface); border-bottom: 1px solid var(--border); }
    .matrix-toolbar input[type=search], .matrix-toolbar select { height: 34px; border: 1px solid var(--border); border-radius: 4px; padding: 0 10px; font-size: 13px; background: var(--surface-soft); color: var(--text); outline: none; }
    .matrix-toolbar input[type=search] { min-width: 200px; }
    .matrix-toolbar label { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-muted); font-weight: 700; }
    .matrix-toolbar .matrix-count { margin-left: auto; font-size: 12px; color: var(--text-muted); font-weight: 700; }
    table.matrix { width: 100%; border-collapse: collapse; font-size: .8rem; }
    table.matrix th { position: sticky; top: 0; background: var(--primary); color: #fff; text-align: left; padding: 8px 10px; white-space: nowrap; z-index: 2; }
    table.matrix td { padding: 8px 10px; border-bottom: 1px solid #eef; vertical-align: top; background: var(--surface); }
    table.matrix tr:nth-child(even) td { background: var(--surface-soft); }
    /* 画面列を左固定 */
    table.matrix th:first-child { left: 0; z-index: 3; }
    table.matrix td:first-child { position: sticky; left: 0; z-index: 1; box-shadow: 1px 0 0 var(--border); }
    table.matrix .c-screen { font-weight: 700; color: var(--primary-dark); white-space: nowrap; }
    table.matrix .c-req { color: var(--critical); font-weight: 700; }
    table.matrix .c-loc { font-family: ui-monospace, monospace; font-size: .72rem; color: var(--accent); overflow-wrap: anywhere; min-width: 130px; }
    table.matrix .c-cond { white-space: normal; }
    .cond-pill { display: inline-block; margin: 1px 2px 1px 0; padding: 1px 6px; border-radius: 4px; font-size: .72rem; border: 1px solid; line-height: 1.5; }
    .cc-req { background: var(--critical-bg); border-color: var(--critical-border); color: #a2191f; }
    .cc-bound { background: #fff8e1; border-color: #f1c21b; color: #8d6b00; }
    .cc-format { background: var(--info-bg); border-color: var(--info-border); color: var(--primary-dark); }
    .cc-opt { background: var(--ok-bg); border-color: #a7f0ba; color: #0e6027; }
    .cc-other { background: #f4f4f4; border-color: #e0e0e0; color: var(--text-muted); }
    .cond-legend { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 11px; color: var(--text-muted); }
    .cond-legend .cond-pill { cursor: default; }
    /* 概要 */
    .ov-screens { width: 100%; border-collapse: collapse; font-size: .85rem; }
    .ov-screens th { background: var(--surface-soft); color: var(--text-muted); font-size: 12px; font-weight: 800; text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); white-space: nowrap; }
    .ov-screens td { padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
    .ov-screens tr:hover td { background: var(--surface-soft); }
    .ov-screens .num { font-variant-numeric: tabular-nums; }
    .ov-screens td.num, .ov-screens th { white-space: nowrap; }
    .tl-table input[type=radio] { accent-color: var(--primary); width: 15px; height: 15px; }
    .tl-table th { text-align: left; }
    .tl-latest { display: inline-block; padding: 0 6px; border-radius: 4px; background: var(--ok-bg); color: var(--ok); font-size: 11px; font-weight: 800; border: 1px solid var(--ok-border); }
    .tl-diff-frame { border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; height: 60vh; background: var(--surface); }
    .tl-diff-frame iframe { width: 100%; height: 100%; border: 0; display: block; }
    .tl-diff-frame .hero-msg { height: 100%; }
    .r-shots { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; }
    .r-shots a { display: block; border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
    .r-shots figure { margin: 0; }
    .r-shots figcaption { font-size: 11px; color: var(--text-muted); padding: 4px 6px; background: var(--surface-soft); }
    .r-shots img { width: 100%; display: block; }
    .export-grid { display: grid; gap: 10px; }
    .export-row { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-soft); }
    .export-row strong { font-size: 14px; }
    .export-row .export-desc { font-size: 12px; color: var(--text-muted); }
    .export-row .export-main { flex: 1; min-width: 0; display: grid; gap: 2px; }
    .export-row a { text-decoration: none; }
    .export-missing { opacity: .5; }

    .app-footer { display: flex; align-items: center; justify-content: space-between; padding: 14px 30px; border-top: 1px solid var(--border); background: var(--surface); color: var(--text-muted); font-size: 12px; flex-shrink: 0; }
    table.data { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
    table.data th { background: var(--surface-soft); color: var(--text-muted); font-size: 12px; font-weight: 800; text-align: left; padding: 12px 14px; border-bottom: 1px solid var(--border); white-space: nowrap; }
    table.data td { padding: 12px 14px; border-bottom: 1px solid var(--border); font-size: 14px; }
    table.data tr:last-child td { border-bottom: none; }
    table.data tbody tr:hover { background: var(--surface-soft); }
    .num { font-variant-numeric: tabular-nums; }
    .history-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .fmt-badges { display: flex; gap: 4px; flex-wrap: wrap; }
    .fmt-badge { display: inline-flex; align-items: center; height: 22px; padding: 0 8px; border-radius: 4px; background: var(--info-bg); border: 1px solid var(--info-border); color: var(--primary-dark); font-size: 11px; font-weight: 700; }
    .empty { padding: 28px; text-align: center; color: var(--text-muted); border: 1px dashed var(--border); border-radius: var(--radius); background: var(--surface-soft); }
    .options-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 4px; }
    .options-grid .full { grid-column: 1 / -1; }
    .settings-msg { margin-top: 14px; padding: 10px 14px; border-radius: var(--radius); background: var(--ok-bg); color: var(--ok); font-size: 13px; font-weight: 700; display: none; }
    .settings-msg.show { display: block; }
    .set-tabs { display: inline-flex; gap: 4px; padding: 4px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-soft); margin-bottom: 16px; }
    .set-tab { height: 34px; padding: 0 16px; border: 0; border-radius: 4px; background: transparent; color: var(--text-muted); font-size: 13px; font-weight: 700; cursor: pointer; }
    .set-tab.is-active { background: var(--surface); color: var(--primary-dark); box-shadow: inset 0 -2px 0 var(--primary); }
    .set-panel { display: none; }
    .set-panel.is-active { display: block; }
    .key-current { padding: 10px 12px; border: 1px solid var(--border); border-radius: 4px; background: var(--surface-soft); font-size: 13px; font-family: ui-monospace, monospace; color: var(--text); }
    .set-card-title { font-size: 16px; font-weight: 700; margin-bottom: 4px; }
    @keyframes shimmer { from { transform: translateX(-100%); } to { transform: translateX(100%); } }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* ── レスポンシブ ── */
    #history-body { overflow-x: auto; }
    table.data { min-width: 640px; }
    .result-tab:focus-visible, .app-nav-item:focus-visible { outline: 2px solid var(--primary); outline-offset: 1px; }
    @media (max-width: 1020px) {
      .result-stats { grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); }
      .login-fields, .options-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 860px) {
      :root { --sidebar-w: 60px; }
      .app-brand-text, .nav-label, .add-site-label, .app-sidebar-foot, .app-nav-group { display: none; }
      .app-sidebar { padding: 14px 8px; align-items: center; }
      .app-brand { justify-content: center; padding: 0; }
      #add-site-btn { padding: 0; }
      .app-nav-item { justify-content: center; padding: 0; }
      .app-topbar { padding: 12px 16px; }
      .app-content { padding: 18px 16px; }
    }
  </style>
</head>
<body class="app-page">
<div class="app-shell">

  <aside class="app-sidebar">
    <a href="/" class="app-brand">
      <span class="app-brand-mark">W</span>
      <span class="app-brand-text"><strong>WebSpec2Doc</strong><span>QA テスト分析インプット</span></span>
    </a>
    <button type="button" class="btn-primary" id="add-site-btn" style="width:100%;height:40px;gap:6px">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" width="16" height="16"><path d="M12 5v14M5 12h14"/></svg>
      <span class="add-site-label">サイトを追加</span>
    </button>
    <nav class="app-nav">
      <div class="app-nav-group">メニュー</div>
      <button class="app-nav-item is-active" data-view="dashboard">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
        <span class="nav-label">ダッシュボード</span>
      </button>
      <button class="app-nav-item" data-view="settings">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        <span class="nav-label">設定</span>
      </button>
    </nav>
    <div style="margin-top:auto" class="app-sidebar-foot">
      稼働中のWebシステムから QA テスト分析インプットを生成し、<strong>再クロールで仕様ドリフトを検知</strong>します。
    </div>
  </aside>

  <div class="app-main">
    <header class="app-topbar">
      <div style="min-width:0">
        <div class="app-breadcrumb" id="topbar-breadcrumb"><span>Dashboard</span></div>
        <h1 class="app-topbar-title" id="topbar-title">監視対象サイト</h1>
      </div>
      <div class="app-topbar-actions" id="topbar-actions"></div>
    </header>

    <main class="app-content" id="app-content">
      <div class="app-content-inner">

        <!-- ===== 生成ビュー ===== -->
        <section class="view" id="view-generate">
          <div id="gen-panel">
            <div class="input-card">
              <nav class="wizard-progress" aria-label="設定ステップ">
                <div class="wizard-step-node is-active" id="wnode-1"><div class="wizard-step-circle">1</div><span class="wizard-step-label">対象設定</span></div>
                <div class="wizard-step-line" id="wline-12"></div>
                <div class="wizard-step-node" id="wnode-2"><div class="wizard-step-circle">2</div><span class="wizard-step-label">出力形式</span></div>
              </nav>

              <form id="form">
                <!-- ページ1: 対象設定 -->
                <div class="wizard-page is-active" id="wpage-1">
                  <label for="url-input" class="form-label">クロール対象 URL <span style="color:#DA1E28">*</span></label>
                  <div class="input-row">
                    <input type="url" id="url-input" class="url-input" placeholder="https://example.com" autocomplete="url" list="url-history-list" />
                    <datalist id="url-history-list"></datalist>
                  </div>
                  <div id="url-input-message" class="input-field-message"></div>
                  <p class="input-hint">公開ページはそのまま入力できます。サイト内URLを自動収集するか、入力したURLをまとめてドキュメント化できます。</p>

                  <div class="wizard-section" style="margin-top:16px">
                    <p class="app-sidebar-section" style="padding:0 0 10px">URLの指定方法</p>
                    <div class="crawl-mode-group">
                      <label class="crawl-mode-option">
                        <input type="radio" name="crawl-mode" value="single" />
                        <span class="crawl-mode-label"><strong>単体ページで生成</strong><span class="crawl-mode-desc">入力した1ページだけをドキュメント化します</span></span>
                      </label>
                      <label class="crawl-mode-option">
                        <input type="radio" name="crawl-mode" value="crawl" checked />
                        <span class="crawl-mode-label"><strong>オートクローリング</strong><span class="crawl-mode-desc">画面リストを取得して、選択したページだけをドキュメント化します</span></span>
                      </label>
                      <div class="crawl-discovery-section" id="crawl-discovery-section" style="display:none">
                        <div class="crawl-depth-row">
                          <label for="crawl-depth" class="crawl-depth-label">収集する階層数</label>
                          <input type="number" id="crawl-depth" class="crawl-depth-input" value="2" min="1" max="5" />
                          <span class="crawl-depth-unit">階層</span>
                          <label for="max-pages" class="crawl-depth-label">最大</label>
                          <input type="number" id="max-pages" class="crawl-depth-input" value="30" min="1" max="300" />
                          <span class="crawl-depth-unit">ページ</span>
                          <button type="button" id="discover-btn" class="btn-outline-sm">画面リスト取得</button>
                        </div>
                        <div id="discover-loading" class="discover-loading" style="display:none"><span class="spinner"></span><span>画面リストを取得しています…</span></div>
                        <div id="discover-status" class="discover-status"></div>
                        <div id="discovered-url-panel" class="discovered-url-panel" style="display:none">
                          <div class="section-head">
                            <p class="app-sidebar-section" style="padding:0">取得した画面リスト</p>
                            <div class="discovered-url-actions">
                              <button type="button" id="select-all-btn" class="btn-outline-sm">全選択</button>
                              <button type="button" id="clear-all-btn" class="btn-outline-sm">全解除</button>
                            </div>
                          </div>
                          <div id="discovered-url-list" class="discovered-url-list"></div>
                        </div>
                      </div>
                      <label class="crawl-mode-option">
                        <input type="radio" name="crawl-mode" value="manual" />
                        <span class="crawl-mode-label"><strong>URLを手動で追加</strong><span class="crawl-mode-desc">入力したURLをまとめてドキュメント化します</span></span>
                      </label>
                      <div id="manual-url-section" class="manual-url-section" style="display:none">
                        <div class="section-head">
                          <p class="app-sidebar-section" style="padding:0">追加URL（任意）</p>
                          <button type="button" id="url-add-btn" class="btn-outline-sm">+ URL を追加</button>
                        </div>
                        <div id="url-list" class="url-list"></div>
                      </div>
                    </div>
                  </div>

                  <div id="target-preview" class="target-preview">
                    <strong>チェック対象 0件</strong>
                    <ol id="target-preview-list"></ol>
                  </div>

                  <details class="result-collapsible" style="margin-top:14px">
                    <summary>詳細設定（ログイン）</summary>
                    <div class="wizard-section" style="margin-top:12px">
                      <p class="app-sidebar-section" style="padding:0 0 8px">手渡しログイン</p>
                      <p class="input-hint" style="margin-top:0">「ログイン用ブラウザを開く」を押すとローカルにブラウザが開きます。ご自身でログイン（MFA・SSO 可）したら「ログイン完了」を押してください。パスワードはツールに保存されません。</p>
                      <div class="login-handoff-actions" style="display:flex;gap:8px;flex-wrap:wrap;margin:10px 0">
                        <button type="button" id="login-start-btn" class="btn-outline-sm">ログイン用ブラウザを開く</button>
                        <button type="button" id="login-finish-btn" class="btn-outline-sm" disabled>ログイン完了</button>
                      </div>
                      <div id="login-status" class="input-field-message"></div>
                      <div class="login-fields" style="margin-top:12px">
                        <div class="field login-field-full">
                          <label for="auth-path">認証セッション auth.json パス（手動指定する場合）</label>
                          <input type="text" id="auth-path" placeholder="auth.json" />
                        </div>
                      </div>
                      <p class="input-hint">CLI で <code>python src/main.py --login &lt;ログインURL&gt;</code> により保存した auth.json のパスを直接指定することもできます。</p>
                    </div>
                  </details>

                  <div class="wizard-footer">
                    <button type="button" class="btn-primary" id="wnext-1">次へ：出力形式 →</button>
                  </div>
                </div>

                <!-- ページ2: 出力設定 -->
                <div class="wizard-page" id="wpage-2">
                  <div class="wizard-page-header"><h2>出力設定</h2><p>生成するドキュメントの形式を選びます。</p></div>
                  <div class="wizard-section">
                    <label class="form-label">出力形式</label>
                    <div class="checkbox-group">
                      <label class="checkbox-chip"><input type="checkbox" name="fmt" value="html" checked> HTML レポート</label>
                      <label class="checkbox-chip"><input type="checkbox" name="fmt" value="pdf"> PDF</label>
                      <label class="checkbox-chip"><input type="checkbox" name="fmt" value="md" checked> Markdown</label>
                      <label class="checkbox-chip"><input type="checkbox" name="fmt" value="excel"> Excel</label>
                      <label class="checkbox-chip"><input type="checkbox" name="fmt" value="json"> JSON</label>
                    </div>
                  </div>
                  <div class="wizard-section">
                    <label class="form-label">オプション</label>
                    <div class="checkbox-group">
                      <label class="checkbox-chip"><input type="checkbox" id="compare"> 前回との差分を出力 (--compare)</label>
                    </div>
                  </div>
                  <div class="wizard-footer">
                    <button type="button" class="btn-outline-sm" id="wback-2">← 戻る</button>
                    <button type="submit" class="btn-primary" id="submit-btn">ドキュメント生成を開始</button>
                  </div>
                </div>
              </form>
            </div>
          </div>

          <!-- 実行ビュー -->
          <div id="execution-view" class="execution-view hidden">
            <div class="execution-topbar">
              <div class="execution-topbar-head">
                <h2 class="execution-title" id="exec-title">ジョブを準備しています</h2>
                <span class="execution-elapsed" id="exec-elapsed">00:00</span>
              </div>
              <p class="execution-message" id="exec-message">対象を受け付けて、クロールの準備を進めています。</p>
              <div class="execution-progress"><div class="execution-progress-bar" id="exec-progress-bar"></div></div>
              <div class="execution-steps">
                <div class="execution-step is-active" id="estep-0">1. 受付</div>
                <div class="execution-step" id="estep-1">2. ページ取得</div>
                <div class="execution-step" id="estep-2">3. 解析</div>
                <div class="execution-step" id="estep-3">4. 結果整理</div>
              </div>
            </div>
            <div class="execution-preview-frame">
              <img id="exec-preview-image" class="execution-preview-image" alt="クロール中のライブプレビュー" />
              <div id="exec-preview-placeholder" class="execution-preview-placeholder">
                <div class="spinner"></div>
                <p>ライブプレビューを準備しています…</p>
              </div>
            </div>
            <pre class="execution-log" id="exec-log"></pre>
            <div class="execution-error-card hidden" id="exec-error">エラーが発生しました。ログを確認してください。</div>
            <div class="execution-bottombar">
              <dl class="execution-meta-list">
                <div class="execution-meta-item"><dt>対象</dt><dd id="exec-target">-</dd></div>
                <div class="execution-meta-item"><dt>状態</dt><dd id="exec-phase">準備中</dd></div>
              </dl>
              <div class="execution-bottombar-actions" id="exec-running-actions">
                <button type="button" id="exec-stop-btn" class="btn-outline-sm">停止</button>
              </div>
              <div class="execution-bottombar-actions hidden" id="exec-actions">
                <button type="button" id="exec-new-btn" class="btn-outline-sm">入力に戻る</button>
              </div>
            </div>
          </div>

          <!-- 結果ページ -->
          <div id="result-panel" class="result-panel hidden">
            <div class="result-summary">
              <div class="result-summary-head">
                <div style="display:flex;align-items:center;gap:10px;min-width:0">
                  <strong id="r-domain">-</strong>
                  <span id="r-crawled" style="font-size:12px;color:var(--text-muted)"></span>
                </div>
                <button type="button" id="r-recrawl-btn" class="btn-outline-sm">再クロール（ドリフト検知）</button>
              </div>
              <div class="result-stats">
                <div><span class="num" id="r-screens">0</span><span>画面数</span></div>
                <div><span class="num" id="r-forms">0</span><span>フォーム数</span></div>
                <div><span class="num" id="r-fields">0</span><span>入力項目数</span></div>
                <div><span class="num" id="r-required">0</span><span>必須項目数</span></div>
                <div><span class="num" id="r-buttons">0</span><span>操作要素数</span></div>
              </div>
            </div>
            <div class="result-bar">
              <div class="result-tabs" role="tablist" aria-label="結果ビュー">
                <button type="button" role="tab" aria-selected="true" class="result-tab is-active" data-tab="overview">概要</button>
                <button type="button" role="tab" aria-selected="false" class="result-tab" data-tab="matrix">入力項目・テスト条件</button>
                <button type="button" role="tab" aria-selected="false" class="result-tab" data-tab="report">画面別仕様</button>
                <button type="button" role="tab" aria-selected="false" class="result-tab" data-tab="history">履歴・差分</button>
                <button type="button" role="tab" aria-selected="false" class="result-tab" data-tab="export">エクスポート</button>
              </div>
              <div class="result-bar-actions">
                <button type="button" id="r-new-btn" class="btn-outline-sm">ダッシュボードへ</button>
              </div>
            </div>
            <div class="result-hero" id="result-hero" role="tabpanel" tabindex="0"></div>
          </div>
        </section>

        <!-- ===== ダッシュボード（監視対象サイト） ===== -->
        <section class="view is-active" id="view-dashboard">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px">
            <p style="color:var(--text-muted);font-size:13px">監視対象サイト。<strong>再クロール</strong>すると前回からの仕様ドリフトを検知できます。</p>
            <div style="display:flex;gap:8px">
              <button class="btn-outline-sm" id="reload-history">再読み込み</button>
              <button class="btn-primary" id="add-site-btn-2" style="height:36px;padding:0 16px;font-size:13px">+ サイトを追加</button>
            </div>
          </div>
          <div id="history-body"><div class="empty">読み込み中...</div></div>
        </section>

        <!-- ===== 設定ビュー ===== -->
        <section class="view" id="view-settings">
          <div class="set-tabs">
            <button class="set-tab is-active" data-tab="api">APIキー</button>
            <button class="set-tab" data-tab="model">モデル</button>
            <button class="set-tab" data-tab="crawl">クロール既定値</button>
          </div>

          <div class="set-panel is-active" id="set-panel-api">
            <div class="input-card">
              <h2 class="set-card-title">OpenAI API キー</h2>
              <p class="input-hint" style="margin-top:0;margin-bottom:14px">キーは <code>.env</code> に保存されます（ブラウザには保存しません）。空欄で保存すると既存キーを保持します。</p>
              <div class="field full" style="margin-bottom:14px">
                <label>現在のキー</label>
                <div class="key-current" id="api-key-current">未設定</div>
              </div>
              <div class="options-grid">
                <div class="field full"><label for="api-key">OPENAI_API_KEY</label><input type="password" id="api-key" placeholder="sk-..." autocomplete="off"></div>
                <div class="field"><label for="api-org">OPENAI_ORG_ID（任意）</label><input type="text" id="api-org" placeholder="org-..."></div>
                <div class="field"><label for="api-project">OPENAI_PROJECT_ID（任意）</label><input type="text" id="api-project" placeholder="proj_..."></div>
              </div>
              <button class="btn-primary" id="save-api" style="margin-top:18px">APIキーを保存</button>
              <div class="settings-msg" id="api-msg">保存しました</div>
              <p class="input-hint" style="margin-top:14px">⚠ LLMテスト観点生成機能は未実装です。本設定はその準備です。</p>
            </div>
          </div>

          <div class="set-panel" id="set-panel-model">
            <div class="input-card">
              <h2 class="set-card-title">回答生成モデル</h2>
              <p class="input-hint" style="margin-top:0;margin-bottom:14px">LLMテスト観点生成（今後実装）で使うモデルです。</p>
              <div class="field full">
                <label for="api-model">OPENAI_MODEL</label>
                <select id="api-model" class="url-input" style="height:40px">
                  <option value="gpt-5.4-mini">gpt-5.4-mini（コスト効率・推奨）</option>
                  <option value="gpt-5.4-nano">gpt-5.4-nano（最安・最速）</option>
                  <option value="gpt-5.4">gpt-5.4（標準）</option>
                  <option value="gpt-5.5">gpt-5.5（高精度）</option>
                  <option value="gpt-5.5-pro">gpt-5.5-pro（最高精度）</option>
                  <option value="gpt-4.1">gpt-4.1（非推論・ツール呼び出し）</option>
                </select>
              </div>
              <button class="btn-primary" id="save-model" style="margin-top:18px">モデルを保存</button>
              <div class="settings-msg" id="model-msg">保存しました</div>
            </div>
          </div>

          <div class="set-panel" id="set-panel-crawl">
            <div class="input-card">
              <h2 class="set-card-title">クロール既定値</h2>
              <p class="input-hint" style="margin-top:0;margin-bottom:14px">このブラウザに保存され、生成ウィザードの初期値に反映されます。</p>
              <div class="options-grid">
                <div class="field"><label for="set-depth">階層数（既定）</label><input type="number" id="set-depth" min="1" max="5"></div>
                <div class="field"><label for="set-max">最大ページ数（既定）</label><input type="number" id="set-max" min="1" max="300"></div>
                <div class="field full">
                  <label>出力形式（既定）</label>
                  <div class="checkbox-group">
                    <label class="checkbox-chip"><input type="checkbox" name="set-fmt" value="html"> HTML</label>
                    <label class="checkbox-chip"><input type="checkbox" name="set-fmt" value="pdf"> PDF</label>
                    <label class="checkbox-chip"><input type="checkbox" name="set-fmt" value="md"> Markdown</label>
                    <label class="checkbox-chip"><input type="checkbox" name="set-fmt" value="excel"> Excel</label>
                    <label class="checkbox-chip"><input type="checkbox" name="set-fmt" value="json"> JSON</label>
                  </div>
                </div>
                <div class="field full"><label for="set-auth">認証セッション auth.json パス（任意）</label><input type="text" id="set-auth" placeholder="auth.json"></div>
              </div>
              <button class="btn-primary" id="save-settings" style="margin-top:18px">設定を保存</button>
              <div class="settings-msg" id="settings-msg">設定を保存しました</div>
            </div>
          </div>
        </section>

      </div>
    </main>

    <footer class="app-footer">
      <span>WebSpec2Doc</span>
      <span>output/ フォルダに保存されます</span>
    </footer>
  </div>
</div>


<script>
const SETTINGS_KEY = 'webspec2doc.settings';
const VIEW_HEADER = {
  dashboard: { trail: ['ダッシュボード'], title: '監視対象サイト' },
  generate: { trail: ['ダッシュボード', 'サイトを追加'], title: 'サイトを追加 / 再クロール' },
  settings: { trail: ['ダッシュボード', '設定'], title: '設定' },
};
const escHtml = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// ---- ヘッダー（パンくず＋タイトル）----
function setHeader(trail, title) {
  const bc = document.getElementById('topbar-breadcrumb');
  bc.innerHTML = trail.map((t, i) => i === 0
    ? `<a data-bc-root="1">${escHtml(t)}</a>`
    : `<span class="sep">›</span><span>${escHtml(t)}</span>`).join('');
  const root = bc.querySelector('[data-bc-root]');
  if (root && trail.length > 1) root.addEventListener('click', () => switchView('dashboard'));
  document.getElementById('topbar-title').textContent = title;
  document.getElementById('topbar-actions').innerHTML = '';
}

// ---- ナビ切替 ----
document.querySelectorAll('.app-nav-item').forEach(btn => btn.addEventListener('click', () => switchView(btn.dataset.view)));
function switchView(name) {
  document.querySelectorAll('.app-nav-item').forEach(b => b.classList.toggle('is-active', b.dataset.view === name));
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('is-active', v.id === 'view-' + name));
  const h = VIEW_HEADER[name];
  if (h) setHeader(h.trail, h.title);
  if (name === 'dashboard') loadHistory();
}
// 「+ サイトを追加」: 新規ウィザードを開く
function openAddSite() {
  switchView('generate');
  executionView.classList.add('hidden'); resultPanel.classList.add('hidden');
  appContent.classList.remove('is-executing'); genPanel.style.display = '';
  document.getElementById('url-input').value = '';
  clearDiscovered(); updateTargetPreview(); showStep(1);
}
document.getElementById('add-site-btn').addEventListener('click', openAddSite);
document.getElementById('add-site-btn-2').addEventListener('click', openAddSite);

// ---- 設定（localStorage）----
function getSettings() { try { return JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {}; } catch { return {}; } }
function applySettings() {
  const s = getSettings();
  if (s.depth) document.getElementById('crawl-depth').value = s.depth;
  if (s.maxPages) document.getElementById('max-pages').value = s.maxPages;
  if (Array.isArray(s.formats)) document.querySelectorAll('input[name=fmt]').forEach(c => { c.checked = s.formats.includes(c.value); });
  if (s.auth) document.getElementById('auth-path').value = s.auth;
}
function loadSettingsForm() {
  const s = getSettings();
  document.getElementById('set-depth').value = s.depth || 2;
  document.getElementById('set-max').value = s.maxPages || 30;
  const fmts = Array.isArray(s.formats) ? s.formats : ['html','md'];
  document.querySelectorAll('input[name=set-fmt]').forEach(c => { c.checked = fmts.includes(c.value); });
  document.getElementById('set-auth').value = s.auth || '';
}
document.getElementById('save-settings').addEventListener('click', () => {
  const formats = [...document.querySelectorAll('input[name=set-fmt]:checked')].map(c => c.value);
  localStorage.setItem(SETTINGS_KEY, JSON.stringify({
    depth: document.getElementById('set-depth').value,
    maxPages: document.getElementById('set-max').value,
    formats,
    auth: document.getElementById('set-auth').value.trim(),
  }));
  applySettings();
  const msg = document.getElementById('settings-msg'); msg.classList.add('show');
  setTimeout(() => msg.classList.remove('show'), 2000);
});

// ---- 履歴 ----
async function loadHistory() {
  const body = document.getElementById('history-body');
  body.innerHTML = '<div class="empty">読み込み中...</div>';
  try {
    const res = await fetch('/api/history');
    const data = await res.json();
    if (!data.items.length) { body.innerHTML = '<div class="empty">まだ監視対象がありません。「+ サイトを追加」から最初のサイトをクロールしてください。</div>'; return; }
    let html = '<table class="data"><thead><tr><th>サイト</th><th class="num">画面数</th><th class="num">入力項目</th><th>形式</th><th>最終クロール</th><th>操作</th></tr></thead><tbody>';
    for (const it of data.items) {
      const badges = (it.formats || []).map(f => `<span class="fmt-badge">${escHtml(f)}</span>`).join('');
      html += `<tr><td><strong>${escHtml(it.domain)}</strong></td><td class="num">${it.screens}</td><td class="num">${it.fields}</td>` +
        `<td><div class="fmt-badges">${badges || '—'}</div></td><td>${escHtml(it.updated)}</td>` +
        `<td><div class="history-actions">` +
        `<button type="button" class="btn-outline-sm hist-recrawl" data-domain="${escHtml(it.domain)}">再クロール</button>` +
        `<button type="button" class="btn-primary hist-open" data-domain="${escHtml(it.domain)}" style="height:36px;padding:0 14px;font-size:13px">開く</button>` +
        `</div></td></tr>`;
    }
    html += '</tbody></table>';
    body.innerHTML = html;
    body.querySelectorAll('.hist-open').forEach(b => b.addEventListener('click', () => openResultsForDomain(b.dataset.domain)));
    body.querySelectorAll('.hist-recrawl').forEach(b => b.addEventListener('click', () => recrawlSite(b.dataset.domain)));
  } catch (e) { body.innerHTML = '<div class="empty">サイト一覧の読み込みに失敗しました。</div>'; }
}
document.getElementById('reload-history').addEventListener('click', loadHistory);

// ---- 再クロール（ドリフト検知）: 既知のサイトを同じ画面構成で取り直す ----
const FILE_TO_FMT = { html: 'html', pdf: 'pdf', excel: 'excel', screens_md: 'md', json: 'json' };
async function recrawlSite(domain) {
  // 保存済み site.json があれば前回設定を忠実に再現。無ければ旧データ用フォールバック。
  let site = null;
  try { site = (await fetch('/api/site?domain=' + encodeURIComponent(domain)).then(r => r.json())).site; } catch (e) {}
  let urls = [], depth = '2', maxPages = '300', fmts = [], auth = getSettings().auth || '';
  if (site) {
    urls = site.urls || [];
    depth = String(site.depth || 2);
    maxPages = String(site.max_pages || 300);
    fmts = site.formats || [];
    auth = site.auth_path || auth;
  } else {
    try {
      const data = await fetch('/api/result?domain=' + encodeURIComponent(domain)).then(r => r.json());
      fmts = Object.keys(FILE_TO_FMT).filter(k => (data.files || {})[k]).map(k => FILE_TO_FMT[k]);
      if (data.files && data.files.json) {
        const rj = await fetch('/preview?path=' + encodeURIComponent(data.files.json)).then(r => r.json());
        urls = (rj.screens || []).map(s => s.url).filter(Boolean);
      }
    } catch (e) {}
  }
  if (!urls.length) urls = ['https://' + domain + '/'];
  if (!fmts.length) fmts = ['html', 'md'];
  if (!fmts.includes('json')) fmts.push('json');
  const body = new URLSearchParams({
    urls: urls.join(','), depth: depth, max_pages: maxPages,
    format: fmts.join(','), compare: 'true', auth: auth,
  });
  switchView('generate');
  runWith(body.toString(), domain, domain, urls.length);
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

// ====================== ウィザード ======================
let wizardStep = 1;
let discovered = [];
const urlInput = document.getElementById('url-input');
const crawlDiscoverySection = document.getElementById('crawl-discovery-section');
const manualUrlSection = document.getElementById('manual-url-section');
const targetPreview = document.getElementById('target-preview');
const targetPreviewList = document.getElementById('target-preview-list');

function showStep(n) {
  for (let i = 1; i <= 2; i++) {
    document.getElementById('wpage-' + i).classList.toggle('is-active', i === n);
    const node = document.getElementById('wnode-' + i);
    node.classList.toggle('is-active', i === n);
    node.classList.toggle('is-done', i < n);
  }
  document.getElementById('wline-12').classList.toggle('is-done', n > 1);
  wizardStep = n;
}
function selectedMode() { return (document.querySelector('input[name=crawl-mode]:checked') || {}).value || 'single'; }

function applyCrawlMode() {
  const m = selectedMode();
  crawlDiscoverySection.style.display = m === 'crawl' ? '' : 'none';
  manualUrlSection.style.display = m === 'manual' ? '' : 'none';
  updateTargetPreview();
}
document.querySelectorAll('input[name=crawl-mode]').forEach(r => r.addEventListener('change', applyCrawlMode));
applyCrawlMode();  // 既定（オートクローリング）をロード時に反映
urlInput.addEventListener('input', () => { clearDiscovered(); updateTargetPreview(); });

document.getElementById('wnext-1').addEventListener('click', () => {
  const url = urlInput.value.trim();
  if (!url) { setUrlMessage('URL を入力してください', true); return; }
  if (selectedMode() === 'crawl' && !selectedDiscovered().length) {
    setUrlMessage(discovered.length ? 'ドキュメント化する画面を1件以上選択してください' : 'オートクローリングでは先に「画面リスト取得」を実行してください', true);
    return;
  }
  setUrlMessage(''); showStep(2);
});
document.getElementById('wback-2').addEventListener('click', () => showStep(1));

function setUrlMessage(msg, isError) {
  const el = document.getElementById('url-input-message');
  el.textContent = msg; el.classList.toggle('input-field-message-error', !!(msg && isError));
}

// ---- 画面リスト取得（discover）----
document.getElementById('discover-btn').addEventListener('click', discoverUrls);

// ---- 手渡しログイン（ADR-0001: サブプロセス＋シグナル）----
function loginDomain() {
  const u = urlInput.value.trim();
  try { return new URL(u).hostname; } catch (e) { return ''; }
}
function setLoginStatus(msg, isError) {
  const el = document.getElementById('login-status');
  el.textContent = msg; el.classList.toggle('input-field-message-error', !!(msg && isError));
}
document.getElementById('login-start-btn').addEventListener('click', async () => {
  const domain = loginDomain();
  if (!domain) { setLoginStatus('先に有効なURLを入力してください', true); return; }
  const startBtn = document.getElementById('login-start-btn');
  const finishBtn = document.getElementById('login-finish-btn');
  startBtn.disabled = true;
  setLoginStatus('ログイン用ブラウザを起動しています…', false);
  try {
    const res = await fetch('/api/login/start', { method: 'POST', body: new URLSearchParams({ url: urlInput.value.trim(), domain }) });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'ログイン開始に失敗しました');
    setLoginStatus('ブラウザでログインを完了したら「ログイン完了」を押してください。', false);
    finishBtn.disabled = false;
  } catch (e) {
    setLoginStatus(e.message, true); startBtn.disabled = false;
  }
});
document.getElementById('login-finish-btn').addEventListener('click', async () => {
  const domain = loginDomain();
  const startBtn = document.getElementById('login-start-btn');
  const finishBtn = document.getElementById('login-finish-btn');
  finishBtn.disabled = true;
  setLoginStatus('セッションを保存しています…', false);
  try {
    const res = await fetch('/api/login/finish', { method: 'POST', body: new URLSearchParams({ domain }) });
    const data = await res.json();
    if (!res.ok || !data.session_saved) throw new Error(data.error || 'セッション保存に失敗しました');
    setLoginStatus('ログインセッションを保存しました。認証後ページを取得できます。', false);
    document.getElementById('auth-path').value = 'output/' + domain + '/auth.json';
  } catch (e) {
    setLoginStatus(e.message, true); finishBtn.disabled = false;
  } finally {
    startBtn.disabled = false;
  }
});
document.getElementById('select-all-btn').addEventListener('click', () => setAllDiscovered(true));
document.getElementById('clear-all-btn').addEventListener('click', () => setAllDiscovered(false));
async function discoverUrls() {
  const url = urlInput.value.trim();
  if (!url) { setUrlMessage('URLを入力してから画面リスト取得を実行してください', true); return; }
  const loading = document.getElementById('discover-loading');
  const status = document.getElementById('discover-status');
  const btn = document.getElementById('discover-btn');
  loading.style.display = 'flex'; status.textContent = ''; status.classList.remove('discover-status-error'); btn.disabled = true;
  try {
    const body = new URLSearchParams({
      url, depth: document.getElementById('crawl-depth').value,
      max_pages: document.getElementById('max-pages').value, auth: getSettings().auth || document.getElementById('auth-path').value.trim() || '',
    });
    const res = await fetch('/api/discover', { method: 'POST', body });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || '画面リスト取得に失敗しました');
    discovered = (data.pages || []).filter(p => p && p.url);
    renderDiscovered();
    status.textContent = discovered.length ? `${discovered.length}件の画面を取得しました。対象を選択してください。` : '画面リストは0件でした。URLや階層数を確認してください。';
  } catch (e) {
    clearDiscovered(); status.textContent = e.message; status.classList.add('discover-status-error');
  } finally {
    loading.style.display = 'none'; btn.disabled = false; updateTargetPreview();
  }
}
function renderDiscovered() {
  const panel = document.getElementById('discovered-url-panel');
  const list = document.getElementById('discovered-url-list');
  panel.style.display = discovered.length ? '' : 'none';
  list.innerHTML = discovered.map((it, i) => `
    <label class="discovered-url-item">
      <input type="checkbox" class="discovered-cb" value="${escHtml(it.url)}" checked />
      <span><strong>${escHtml(it.title || ('タイトル未取得 ' + (i + 1)))}</strong><code>${escHtml(it.url)}</code>${it.login_required ? `<span class="disc-login-badge" title="${escHtml('認証が必要な可能性があります（根拠: ' + ((it.login_reasons || []).join(', ') || '不明') + '）。不要ならチェックを外してスキップできます。')}">要ログイン</span>` : ''}</span>
    </label>`).join('');
  list.querySelectorAll('.discovered-cb').forEach(cb => cb.addEventListener('change', updateTargetPreview));
}
function clearDiscovered() {
  discovered = [];
  document.getElementById('discovered-url-panel').style.display = 'none';
  document.getElementById('discovered-url-list').innerHTML = '';
  document.getElementById('discover-status').textContent = '';
}
function setAllDiscovered(v) { document.querySelectorAll('.discovered-cb').forEach(cb => { cb.checked = v; }); updateTargetPreview(); }
function selectedDiscovered() { return [...document.querySelectorAll('.discovered-cb:checked')].map(cb => cb.value); }

// ---- 手動URL追加 ----
document.getElementById('url-add-btn').addEventListener('click', () => {
  const item = document.createElement('div');
  item.className = 'url-list-item';
  item.innerHTML = '<input type="url" class="url-input url-list-input" placeholder="https://example.com/page" /><button type="button" class="btn-outline-sm url-list-remove">削除</button>';
  item.querySelector('.url-list-input').addEventListener('input', updateTargetPreview);
  item.querySelector('.url-list-remove').addEventListener('click', () => { item.remove(); updateTargetPreview(); });
  document.getElementById('url-list').appendChild(item);
  updateTargetPreview();
});
function manualUrls() {
  const primary = urlInput.value.trim();
  const extras = [...document.querySelectorAll('.url-list-input')].map(i => i.value.trim()).filter(Boolean);
  return [...new Set([primary, ...extras].filter(Boolean))];
}

// ---- 対象URLの確定 ----
function buildTargetUrls() {
  const mode = selectedMode();
  if (mode === 'single') { const u = urlInput.value.trim(); return u ? [u] : []; }
  if (mode === 'crawl') return selectedDiscovered();
  return manualUrls();
}
function updateTargetPreview() {
  const urls = buildTargetUrls();
  targetPreview.querySelector('strong').textContent = `チェック対象 ${urls.length}件`;
  if (!urls.length) {
    const mode = selectedMode();
    const msg = mode === 'crawl' && urlInput.value.trim() ? '画面リスト取得を実行してください' : 'URLを入力してください';
    targetPreviewList.innerHTML = `<li><span>未確定</span><code>${msg}</code></li>`;
    return;
  }
  targetPreviewList.innerHTML = urls.map((u, i) => `<li><span>${i === 0 ? 'メイン' : '対象 ' + (i + 1)}</span><code>${escHtml(u)}</code></li>`).join('');
}

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
  const urls = buildTargetUrls();
  if (!urls.length) { showStep(1); setUrlMessage('対象URLが確定していません', true); return; }
  const fmts = [...document.querySelectorAll('input[name=fmt]:checked')].map(c => c.value);
  if (!fmts.length) { showStep(2); return; }
  const body = new URLSearchParams({
    urls: urls.join(','),
    depth: document.getElementById('crawl-depth').value,
    max_pages: document.getElementById('max-pages').value,
    format: fmts.join(','),
    compare: document.getElementById('compare').checked ? 'true' : 'false',
    auth: document.getElementById('auth-path').value.trim() || getSettings().auth || '',
    crawl_mode: (document.querySelector('input[name="crawl-mode"]:checked') || {}).value || '',
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
  let reportPath = '', summary = null, ok = false, cur = 0, cancelled = false;
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
      const clean = chunk.replace(/(RUN_ID|REPORT_PATH|PDF_PATH|SUMMARY):.*\\n?/g, '');
      execLog.textContent += clean; execLog.scrollTop = execLog.scrollHeight;
      for (const line of clean.split('\\n')) { const st = guessStep(line); if (st >= 0 && st >= cur) { cur = st; setStep(st); } }
    }
  } catch (err) {
    if (err.name === 'AbortError') cancelled = true;
    else execLog.textContent += '\\n通信エラー: ' + err.message;
  }

  stopTimer(); stopPreviewPolling(); execRunningActions.classList.add('hidden');
  if (cancelled) {
    execActions.classList.remove('hidden');
    execTitle.textContent = '実行を停止しました'; execPhase.textContent = '停止';
    execMessage.textContent = '停止要求により処理を終了しました。必要に応じて入力に戻って再実行してください。';
  } else if (ok || reportPath) {
    setStep(4); execProgressBar.style.width = '100%';
    estep.forEach(el => el.className = 'execution-step is-complete');
    await showResults(activeDomain);
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

document.getElementById('exec-new-btn').addEventListener('click', () => switchView('dashboard'));
document.getElementById('r-new-btn').addEventListener('click', () => switchView('dashboard'));
document.getElementById('r-recrawl-btn').addEventListener('click', () => {
  const domain = document.getElementById('r-domain').textContent.trim();
  if (domain && domain !== '-') recrawlSite(domain);
});

// ====================== 結果ページ（QAビュー軸） ======================
const resultPanel = document.getElementById('result-panel');
const resultHero = document.getElementById('result-hero');
const EXPORT_DEFS = [
  { key: 'html', label: 'HTMLレポート', desc: 'テスト分析インプット文書（画面別カード＋テスト条件）' },
  { key: 'pdf', label: 'PDF', desc: '配布・印刷用（HTMLレポートのPDF版）' },
  { key: 'screens_md', label: 'Markdown（画面一覧）', desc: 'screens.md' },
  { key: 'forms_md', label: 'Markdown（フォーム）', desc: 'forms.md' },
  { key: 'excel', label: 'Excel', desc: 'spec.xlsx（表計算で編集）' },
  { key: 'json', label: 'JSON（機械可読）', desc: '自動化・連携用の構造化データ' },
  { key: 'diff', label: '差分レポート', desc: '前回スナップショットとの差分' },
];
let resultData = null, reportJson = null, activeResultTab = 'overview';

async function showResults(domain) {
  let data;
  try {
    const res = await fetch('/api/result?domain=' + encodeURIComponent(domain));
    data = await res.json();
    if (!res.ok) throw new Error(data.error || '結果の取得に失敗しました');
  } catch (e) {
    // 実行ビューが隠れている（履歴から開いた）場合は結果領域にエラーを表示
    executionView.classList.add('hidden'); resultPanel.classList.remove('hidden');
    appContent.classList.add('is-executing');
    setHeader(['ダッシュボード', domain], domain);
    resultHero.innerHTML = `<div class="hero-msg"><p>結果の取得に失敗しました。</p><p style="font-size:13px;color:var(--text-muted)">${escHtml(e.message)}</p></div>`;
    return;
  }
  resultData = data;
  reportJson = null;
  if (data.files && data.files.json) {
    try { reportJson = await fetch('/preview?path=' + encodeURIComponent(data.files.json)).then(r => r.json()); } catch (e) {}
  }
  const s = data.summary || {};
  const required = reportJson ? countRequired(reportJson) : 0;
  const crawledAt = reportJson && reportJson.meta ? reportJson.meta.crawled_at : '';
  document.getElementById('r-crawled').textContent = crawledAt ? ('最終クロール: ' + crawledAt) : '';
  document.getElementById('r-domain').textContent = domain;
  document.getElementById('r-screens').textContent = s.screens || 0;
  document.getElementById('r-forms').textContent = s.forms || 0;
  document.getElementById('r-fields').textContent = s.fields || 0;
  document.getElementById('r-required').textContent = required;
  document.getElementById('r-buttons').textContent = s.buttons || 0;
  setHeader(['ダッシュボード', domain], domain);

  executionView.classList.add('hidden'); resultPanel.classList.remove('hidden');
  selectResultTab('overview');
}

document.querySelectorAll('.result-tab').forEach(t => {
  t.addEventListener('click', () => selectResultTab(t.dataset.tab));
  t.addEventListener('keydown', e => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const tabs = [...document.querySelectorAll('.result-tab')].filter(x => x.offsetParent !== null);
    const i = tabs.indexOf(t);
    const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    if (next) { selectResultTab(next.dataset.tab); next.focus(); }
  });
});
function selectResultTab(tab) {
  activeResultTab = tab;
  document.querySelectorAll('.result-tab').forEach(t => {
    const on = t.dataset.tab === tab;
    t.classList.toggle('is-active', on);
    t.setAttribute('aria-selected', on ? 'true' : 'false');
    t.tabIndex = on ? 0 : -1;
  });
  if (tab === 'overview') renderOverview();
  else if (tab === 'matrix') renderMatrix();
  else if (tab === 'report') renderReport();
  else if (tab === 'history') renderTimeline();
  else if (tab === 'export') renderExport();
}

// ---- 履歴・差分（クロール履歴タイムライン＋任意2点の仕様ドリフト比較）----
let timelineDomain = '';
async function renderTimeline() {
  const domain = document.getElementById('r-domain').textContent.trim();
  timelineDomain = domain;
  resultHero.innerHTML = '<div class="hero-msg">クロール履歴を読み込み中…</div>';
  let snaps = [];
  try {
    const data = await fetch('/api/snapshots?domain=' + encodeURIComponent(domain)).then(r => r.json());
    snaps = data.snapshots || [];
  } catch (e) {}
  if (snaps.length < 2) {
    resultHero.innerHTML = '<div class="hero-pad"><div class="hero-section-title">クロール履歴</div>' +
      '<p style="color:var(--text-muted);font-size:13px">履歴が' + snaps.length + '件です。<strong>再クロール</strong>すると、前回との仕様ドリフト（追加/削除された画面・変更されたフォーム）を時系列で比較できます。</p></div>';
    return;
  }
  // 既定: to=最新(0), from=ひとつ前(1)
  const rows = snaps.map((s, i) => `
    <tr>
      <td style="text-align:center"><input type="radio" name="snap-from" value="${escHtml(s.id)}" ${i === 1 ? 'checked' : ''}></td>
      <td style="text-align:center"><input type="radio" name="snap-to" value="${escHtml(s.id)}" ${i === 0 ? 'checked' : ''}></td>
      <td>${escHtml(s.label)}${i === 0 ? ' <span class="tl-latest">最新</span>' : ''}</td>
      <td class="num">${s.screens}</td><td class="num">${s.forms}</td><td class="num">${s.fields}</td>
    </tr>`).join('');
  resultHero.innerHTML = '<div class="hero-pad">' +
    '<div class="hero-section-title">クロール履歴（' + snaps.length + '件）</div>' +
    '<p style="color:var(--text-muted);font-size:13px;margin-bottom:10px">比較する2時点を選び、仕様ドリフトを確認します（比較元＝古い／比較先＝新しい）。</p>' +
    '<table class="ov-screens tl-table"><thead><tr><th>比較元</th><th>比較先</th><th>クロール日時</th><th>画面</th><th>フォーム</th><th>入力項目</th></tr></thead><tbody>' +
    rows + '</tbody></table>' +
    '<div style="margin:12px 0"><button type="button" class="btn-primary" id="tl-diff-btn">この2時点の差分を表示</button></div>' +
    '<div class="tl-diff-frame" id="tl-diff"></div></div>';
  document.getElementById('tl-diff-btn').addEventListener('click', showTimelineDiff);
  showTimelineDiff();
}
function showTimelineDiff() {
  const from = (document.querySelector('input[name=snap-from]:checked') || {}).value;
  const to = (document.querySelector('input[name=snap-to]:checked') || {}).value;
  const box = document.getElementById('tl-diff');
  if (!from || !to) { box.innerHTML = '<div class="hero-msg">2時点を選択してください。</div>'; return; }
  if (from === to) { box.innerHTML = '<div class="hero-msg">異なる2時点を選択してください。</div>'; return; }
  box.innerHTML = `<iframe src="/api/snapshot-diff?domain=${encodeURIComponent(timelineDomain)}&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}" title="仕様ドリフト差分"></iframe>`;
}

function allFields(rj) {
  const rows = [];
  for (const sc of (rj.screens || [])) {
    for (const fm of (sc.forms || [])) {
      for (const fld of (fm.fields || [])) rows.push({ screen: sc.page_id, title: sc.title || '', field: fld });
    }
  }
  return rows;
}
function countRequired(rj) { return allFields(rj).filter(r => r.field.required).length; }
function constraintText(f) {
  const p = [];
  if (f.maxlength != null) p.push('最大' + f.maxlength + '文字');
  if (f.minlength != null) p.push('最小' + f.minlength + '文字');
  if (f.min_value) p.push('min=' + f.min_value);
  if (f.max_value) p.push('max=' + f.max_value);
  if (f.pattern) p.push('pattern=' + f.pattern);
  if (f.placeholder) p.push('例: ' + f.placeholder);
  return p.join(' / ');
}
function defaultOptionsText(f) {
  if (f.options && f.options.length) return f.options.filter(Boolean).join(', ').slice(0, 120);
  return f.default || '';
}

// ---- 概要 ----
function renderOverview() {
  if (!reportJson) {
    const shots = (resultData.screenshots || []).map(p =>
      `<a href="/preview?path=${encodeURIComponent(p)}" target="_blank"><figure><img src="/preview?path=${encodeURIComponent(p)}" loading="lazy" alt="${escHtml(p.split('/').pop())}"><figcaption>${escHtml(p.split('/').pop())}</figcaption></figure></a>`).join('');
    resultHero.innerHTML = '<div class="hero-pad">' +
      '<p style="color:var(--text-muted);font-size:13px;margin-bottom:12px">このサイトは旧バージョンで生成されたため画面別の構造化データがありません。「<strong>再クロール</strong>」で最新のテスト条件マトリクスを生成できます。詳細は「画面別仕様」タブを参照してください。</p>' +
      (shots ? '<div class="hero-section-title">スクリーンショット</div><div class="r-shots">' + shots + '</div>' : '') +
      '</div>';
    return;
  }
  const screens = reportJson.screens || [];
  const meta = reportJson.meta || {};
  const rows = screens.map(sc => {
    const fields = (sc.forms || []).reduce((n, fm) => n + (fm.fields || []).length, 0);
    const to = (sc.transitions && sc.transitions.to || []).join(', ') || '—';
    return `<tr><td class="c-screen">${escHtml(sc.page_id)}</td><td>${escHtml(sc.title || '')}</td>` +
      `<td><code style="font-size:.78rem;color:var(--text-muted)">${escHtml(sc.url || '')}</code></td>` +
      `<td class="num">${(sc.forms || []).length}</td><td class="num">${fields}</td><td>${escHtml(to)}</td></tr>`;
  }).join('');
  // 現在のクロールに含まれる画面IDのスクショだけ表示（過去の残骸を除外）
  const pageIds = new Set(screens.map(sc => sc.page_id));
  const shots = (resultData.screenshots || []).filter(p => pageIds.has(p.split('/').pop().replace(/\\.png$/, ''))).map(p =>
    `<a href="/preview?path=${encodeURIComponent(p)}" target="_blank"><figure><img src="/preview?path=${encodeURIComponent(p)}" loading="lazy" alt="${escHtml(p.split('/').pop())}"><figcaption>${escHtml(p.split('/').pop())}</figcaption></figure></a>`).join('');
  resultHero.innerHTML = '<div class="hero-pad">' +
    `<p style="color:var(--text-muted);font-size:13px;margin-bottom:12px">対象 ${escHtml(meta.target_url || '')} ／ クロール: 深さ${meta.crawl_depth ?? '-'} ・最大${meta.max_pages ?? '-'}ページ ／ ${escHtml(meta.crawled_at || '')}</p>` +
    '<div class="hero-section-title">画面インベントリ</div>' +
    '<table class="ov-screens"><thead><tr><th>画面ID</th><th>タイトル</th><th>URL</th><th>フォーム</th><th>入力項目</th><th>遷移先</th></tr></thead><tbody>' +
    (rows || '<tr><td colspan="6" style="color:var(--text-muted)">画面がありません</td></tr>') + '</tbody></table>' +
    (shots ? '<div class="hero-section-title" style="margin-top:18px">スクリーンショット</div><div class="r-shots">' + shots + '</div>' : '') +
    '</div>';
}

// ---- 入力項目・テスト条件マトリクス ----
function renderMatrix() {
  if (!reportJson) { resultHero.innerHTML = '<div class="hero-msg">マトリクスデータ（report.json）を読み込めませんでした。</div>'; return; }
  const screens = (reportJson.screens || []).map(s => s.page_id);
  resultHero.innerHTML =
    '<div class="matrix-toolbar">' +
    '<select id="mx-screen"><option value="">全画面</option>' + screens.map(s => `<option value="${escHtml(s)}">${escHtml(s)}</option>`).join('') + '</select>' +
    '<input type="search" id="mx-search" placeholder="項目名・条件で検索" />' +
    '<label><input type="checkbox" id="mx-required"> 必須のみ</label>' +
    '<button type="button" class="btn-outline-sm" id="mx-csv">CSVで書き出し</button>' +
    '<span class="matrix-count" id="mx-count"></span>' +
    '<span class="cond-legend">種別:' +
    '<span class="cond-pill cc-req">必須</span>' +
    '<span class="cond-pill cc-bound">境界値</span>' +
    '<span class="cond-pill cc-format">形式</span>' +
    '<span class="cond-pill cc-opt">選択肢</span>' +
    '<span class="cond-pill cc-other">その他</span>' +
    '</span>' +
    '</div><div id="mx-table-wrap"></div>';
  let t = null;
  const debounced = () => { clearTimeout(t); t = setTimeout(drawMatrix, 150); };
  document.getElementById('mx-screen').addEventListener('change', drawMatrix);
  document.getElementById('mx-search').addEventListener('input', debounced);
  document.getElementById('mx-required').addEventListener('change', drawMatrix);
  document.getElementById('mx-csv').addEventListener('click', exportMatrixCsv);
  drawMatrix();
}
function condClass(c) {
  if (c.includes('必須')) return 'cc-req';
  if (c.includes('最大長') || c.includes('最小長') || c.includes('範囲') || c.includes('境界')) return 'cc-bound';
  if (c.includes('形式') || c.includes('メール') || c.includes('パターン') || c.includes('日付') || c.includes('電話') || c.includes('数値') || c.includes('パスワード')) return 'cc-format';
  if (c.includes('選択肢') || c.includes('ON / OFF') || c.includes('未選択')) return 'cc-opt';
  return 'cc-other';
}
function matrixRows() {
  const scFilter = (document.getElementById('mx-screen') || {}).value || '';
  const q = ((document.getElementById('mx-search') || {}).value || '').toLowerCase();
  const reqOnly = (document.getElementById('mx-required') || {}).checked;
  return allFields(reportJson).filter(r => {
    if (scFilter && r.screen !== scFilter) return false;
    if (reqOnly && !r.field.required) return false;
    if (q) {
      const hay = (r.field.name + ' ' + (r.field.test_conditions || []).join(' ') + ' ' + constraintText(r.field)).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}
function drawMatrix() {
  const rows = matrixRows();
  document.getElementById('mx-count').textContent = rows.length + ' 項目';
  const body = rows.map(r => {
    const f = r.field;
    return '<tr>' +
      `<td class="c-screen">${escHtml(r.screen)}</td>` +
      `<td>${escHtml(f.name || '(無名)')}</td>` +
      `<td>${escHtml(f.field_type || '')}</td>` +
      `<td>${f.required ? '<span class="c-req">必須</span>' : '-'}</td>` +
      `<td>${escHtml(constraintText(f)) || '-'}</td>` +
      `<td>${escHtml(defaultOptionsText(f)) || '-'}</td>` +
      `<td class="c-loc">${escHtml((f.locators || []).join(' / ')) || '-'}</td>` +
      `<td class="c-cond">${(f.test_conditions || []).map(c => `<span class="cond-pill ${condClass(c)}">${escHtml(c)}</span>`).join('') || '-'}</td>` +
    '</tr>';
  }).join('');
  document.getElementById('mx-table-wrap').innerHTML =
    '<table class="matrix"><thead><tr><th>画面</th><th>項目名</th><th>型</th><th>必須</th><th>制約</th><th>既定/選択肢</th><th>ロケータ候補</th><th>導出テスト条件</th></tr></thead><tbody>' +
    (body || '<tr><td colspan="8" style="padding:16px;color:var(--text-muted)">該当する入力項目がありません</td></tr>') + '</tbody></table>';
}
function exportMatrixCsv() {
  const head = ['画面', '項目名', '型', '必須', '制約', '既定/選択肢', 'ロケータ候補', '導出テスト条件'];
  const esc = v => '"' + String(v).replace(/"/g, '""') + '"';
  const lines = [head.map(esc).join(',')];
  for (const r of matrixRows()) {
    const f = r.field;
    lines.push([r.screen, f.name || '(無名)', f.field_type || '', f.required ? '必須' : '', constraintText(f), defaultOptionsText(f), (f.locators || []).join(' / '), (f.test_conditions || []).join(' / ')].map(esc).join(','));
  }
  const blob = new Blob(['\\uFEFF' + lines.join('\\r\\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'test_conditions.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
}

// ---- 画面別仕様（HTMLレポート埋め込み）----
function renderReport() {
  const html = (resultData.files || {}).html;
  if (!html) { resultHero.innerHTML = '<div class="hero-msg"><p>HTMLレポートは生成されていません。</p><p style="font-size:13px">出力形式で「HTML」を選ぶと、ここに画面別の詳細仕様が表示されます。</p></div>'; return; }
  resultHero.innerHTML = `<iframe src="/preview?path=${encodeURIComponent(html)}" title="画面別仕様"></iframe>`;
}

// ---- エクスポート ----
function renderExport() {
  const files = resultData.files || {};
  const rows = EXPORT_DEFS.map(d => {
    const path = files[d.key];
    if (path) {
      return `<div class="export-row"><div class="export-main"><strong>${escHtml(d.label)}</strong><span class="export-desc">${escHtml(d.desc)}</span></div>` +
        `<a class="btn-outline-sm" href="/preview?path=${encodeURIComponent(path)}" target="_blank">開く</a>` +
        `<a class="btn-primary" style="height:36px;padding:0 16px;font-size:13px;display:inline-flex;align-items:center" href="/download?path=${encodeURIComponent(path)}" download>DL</a></div>`;
    }
    return `<div class="export-row export-missing"><div class="export-main"><strong>${escHtml(d.label)}</strong><span class="export-desc">未生成（出力形式で選択すると生成されます）</span></div></div>`;
  }).join('');
  resultHero.innerHTML = '<div class="hero-pad"><div class="export-grid">' +
    `<div class="export-row" style="background:var(--info-bg);border-color:var(--info-border)"><div class="export-main"><strong>すべてまとめてダウンロード</strong><span class="export-desc">生成物一式を ZIP で取得</span></div>` +
    `<a class="btn-primary" style="height:36px;padding:0 16px;font-size:13px;display:inline-flex;align-items:center" href="/download-zip?domain=${encodeURIComponent(resultData_domain())}">ZIP DL</a></div>` +
    rows + '</div></div>';
}
function resultData_domain() { return document.getElementById('r-domain').textContent || ''; }

// ---- 設定サブタブ ----
document.querySelectorAll('.set-tab').forEach(t => t.addEventListener('click', () => {
  document.querySelectorAll('.set-tab').forEach(x => x.classList.toggle('is-active', x === t));
  document.querySelectorAll('.set-panel').forEach(p => p.classList.toggle('is-active', p.id === 'set-panel-' + t.dataset.tab));
}));

// ---- API設定（.env にサーバ保存）----
function flash(id) { const m = document.getElementById(id); m.classList.add('show'); setTimeout(() => m.classList.remove('show'), 2000); }
async function loadApiSettings() {
  try {
    const res = await fetch('/api/settings'); const s = await res.json();
    document.getElementById('api-model').value = s.openai_model || 'gpt-5.4-mini';
    document.getElementById('api-org').value = s.openai_org_id || '';
    document.getElementById('api-project').value = s.openai_project_id || '';
    document.getElementById('api-key-current').textContent = s.openai_key_set ? s.openai_key_masked : '未設定';
  } catch (e) {}
}
document.getElementById('save-api').addEventListener('click', async () => {
  await fetch('/api/settings', { method: 'POST', body: new URLSearchParams({
    api_key: document.getElementById('api-key').value,
    org_id: document.getElementById('api-org').value,
    project_id: document.getElementById('api-project').value,
  }) });
  document.getElementById('api-key').value = ''; flash('api-msg'); loadApiSettings();
});
document.getElementById('save-model').addEventListener('click', async () => {
  await fetch('/api/settings', { method: 'POST', body: new URLSearchParams({ model: document.getElementById('api-model').value }) });
  flash('model-msg'); loadApiSettings();
});

// ---- URL履歴 datalist ----
async function loadUrlHistory() {
  try {
    const res = await fetch('/api/history'); const data = await res.json();
    const dl = document.getElementById('url-history-list');
    dl.innerHTML = (data.items || []).map(it => `<option value="https://${escHtml(it.domain)}/">`).join('');
  } catch (e) {}
}

// 初期化
applySettings(); loadSettingsForm(); loadApiSettings(); loadUrlHistory(); updateTargetPreview(); switchView('dashboard');
</script>
</body>
</html>
"""


@app.get("/")
def index() -> str:
    return _HTML


def _domain_of(url: str) -> str:
    parsed = urlparse(url.strip())
    return parsed.netloc or "site"


@app.post("/api/discover")
def api_discover() -> Response | tuple[dict, int] | dict:
    url = request.form.get("url", "").strip()
    depth = str(_clean_int(request.form.get("depth", "2"), 2, 1, MAX_DEPTH))
    max_pages = str(_clean_int(request.form.get("max_pages", "30"), 30, 1, MAX_PAGES_LIMIT))
    auth = _safe_auth_path(request.form.get("auth", "").strip())
    if not url:
        return {"pages": [], "error": "URLを入力してください"}, 400
    cmd = [
        sys.executable, "src/main.py", "--discover",
        "--url", url, "--depth", depth, "--max-pages", max_pages,
    ]
    if auth:
        cmd += ["--auth", auth]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=DISCOVER_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return {"pages": [], "error": "画面リスト取得がタイムアウトしました"}, 504
    try:
        data = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError:
        return {"pages": [], "error": "画面リストの解析に失敗しました"}, 500
    return {"pages": data.get("pages", [])}


def _save_site_config(
    domain: str, urls: str, crawl_mode: str, depth: str, max_pages: str,
    formats: list[str], auth: str,
) -> None:
    """クロール成功時に再クロール用の設定を site.json へ保存する。"""
    try:
        save_site(
            SiteConfig(
                domain=domain,
                urls=tuple(u for u in urls.split(",") if u),
                crawl_mode=crawl_mode,
                depth=int(depth),
                max_pages=int(max_pages),
                formats=tuple(formats),
                auth_path=auth,
            ),
            OUTPUT_DIR,
        )
    except (OSError, ValueError) as exc:
        app.logger.warning("site.json の保存に失敗しました: %s (%s)", domain, exc)


@app.get("/api/site")
def api_site() -> dict:
    domain = request.args.get("domain", "").strip()
    if not domain or not _valid_domain(domain):
        return {"site": None}
    config = load_site(domain, OUTPUT_DIR)
    return {"site": asdict(config) if config else None}


_LOGIN_PROCS: dict[str, subprocess.Popen] = {}


@app.post("/api/login/start")
def api_login_start() -> tuple[dict, int] | dict:
    """手渡しログイン用ブラウザをサブプロセスで開く（ADR-0001）。"""
    login_url = request.form.get("url", "").strip()
    domain = request.form.get("domain", "").strip()
    if not login_url or not domain or not _valid_domain(domain):
        return {"ok": False, "error": "ログインURLとドメインを指定してください"}, 400
    sig = signal_path(domain, OUTPUT_DIR)
    auth = session_path(domain, OUTPUT_DIR)
    auth.parent.mkdir(parents=True, exist_ok=True)
    if sig.exists():
        sig.unlink()  # 前回の取り残しシグナルを掃除
    cmd = [
        sys.executable, "src/main.py", "--login", login_url,
        "--login-signal", str(sig), "--auth", str(auth),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    _LOGIN_PROCS[domain] = proc
    return {"ok": True, "domain": domain}


@app.post("/api/login/finish")
def api_login_finish() -> tuple[dict, int] | dict:
    """ログイン完了シグナルを置き、サブプロセスのセッション保存完了を待つ。"""
    domain = request.form.get("domain", "").strip()
    if not domain or not _valid_domain(domain):
        return {"ok": False, "error": "ドメインを指定してください"}, 400
    proc = _LOGIN_PROCS.pop(domain, None)
    if proc is None:
        return {"ok": False, "error": "ログインセッションが開始されていません"}, 409
    signal_path(domain, OUTPUT_DIR).write_text("", encoding="utf-8")
    try:
        proc.wait(timeout=LOGIN_FINISH_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        _terminate_proc(proc)
        return {"ok": False, "error": "セッション保存がタイムアウトしました"}, 504
    saved = proc.returncode == 0 and has_session(domain, OUTPUT_DIR)
    return {"ok": saved, "session_saved": saved}


@app.post("/run")
def run() -> Response:
    urls = request.form.get("urls", "").strip()
    depth = str(_clean_int(request.form.get("depth", "2"), 2, 1, MAX_DEPTH))
    max_pages = str(_clean_int(request.form.get("max_pages", "30"), 30, 1, MAX_PAGES_LIMIT))
    # 出力形式は許可リストで検証。report.json は結果ページのデータ源なので常に生成する
    selected = _clean_formats(request.form.get("format", "md,html")) or ["md", "html"]
    if "json" not in selected:
        selected.append("json")
    fmt = ",".join(selected)
    compare = request.form.get("compare", "false") == "true"
    auth = _safe_auth_path(request.form.get("auth", "").strip())
    crawl_mode = request.form.get("crawl_mode", "").strip()
    domain = _domain_of(urls.split(",")[0]) if urls else ""

    run_id = uuid.uuid4().hex

    def generate():
        cmd = [
            sys.executable, "src/main.py", "--urls", urls,
            "--depth", depth, "--max-pages", max_pages, "--format", fmt,
        ]
        if compare:
            cmd.append("--compare")
        if auth:
            cmd += ["--auth", auth]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        _RUNNING_PROCS[run_id] = proc
        try:
            yield f"RUN_ID:{run_id}\n"
            for line in proc.stdout:  # type: ignore[union-attr]
                yield line
            proc.wait()
            if proc.returncode is not None and proc.returncode < 0:
                yield "\n停止しました。\n"
                return
            domain_dir = OUTPUT_DIR / domain
            report = domain_dir / "report.html"
            pdf = domain_dir / "report.pdf"
            if report.exists():
                yield f"REPORT_PATH:{report.resolve()}\n"
            if pdf.exists():
                yield f"PDF_PATH:{pdf.resolve()}\n"
            yield f"SUMMARY:{json.dumps(_summary_for_domain(domain))}\n"
            if proc.returncode == 0 and domain:
                _save_site_config(domain, urls, crawl_mode, depth, max_pages, selected, auth)
            if proc.returncode != 0:
                yield "\nエラーが発生しました。\n"
        finally:
            _RUNNING_PROCS.pop(run_id, None)
            _terminate_proc(proc)

    return Response(generate(), mimetype="text/plain")


@app.post("/api/cancel")
def api_cancel() -> dict:
    proc = _RUNNING_PROCS.get(request.form.get("run_id", ""))
    if proc is None:
        return {"ok": False}
    _terminate_proc(proc)
    return {"ok": True}


@app.get("/api/live-screenshot")
def live_screenshot() -> Response:
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return Response(status=404)
    shots_dir = OUTPUT_DIR / domain / "screenshots"
    if not shots_dir.is_dir():
        return Response(status=404)
    pngs = sorted(shots_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pngs:
        return Response(status=404)
    resp = send_file(pngs[0].resolve(), mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _summary_for_domain(domain: str) -> dict[str, int]:
    """最新の生成結果（report.json）を唯一の真実源として集計する。
    結果ページのサマリー／概要／マトリクス／履歴をすべて一致させるため。
    report.json が無い旧データのみ snapshot → screens.md にフォールバック。"""
    domain_dir = OUTPUT_DIR / domain
    report_json = domain_dir / "report.json"
    if report_json.exists():
        try:
            data = json.loads(report_json.read_text(encoding="utf-8"))
            screens = data.get("screens", [])
            return {
                "screens": len(screens),
                "forms": sum(len(s.get("forms", [])) for s in screens),
                "fields": sum(len(f.get("fields", [])) for s in screens for f in s.get("forms", [])),
                "buttons": sum(len(s.get("buttons", [])) for s in screens),
            }
        except (OSError, json.JSONDecodeError):
            pass
    snaps_dir = domain_dir / "snapshots"
    snaps = sorted(snaps_dir.glob("*.json")) if snaps_dir.is_dir() else []
    if not snaps:
        return {"screens": _count_screens(domain_dir / "screens.md"), "forms": 0, "fields": 0, "buttons": 0}
    try:
        pages = json.loads(snaps[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"screens": 0, "forms": 0, "fields": 0, "buttons": 0}
    forms = sum(len(p.get("forms", [])) for p in pages)
    fields = sum(len(f.get("fields", [])) for p in pages for f in p.get("forms", []))
    buttons = sum(len(p.get("buttons", [])) for p in pages)
    return {"screens": len(pages), "forms": forms, "fields": fields, "buttons": buttons}


def _safe_output_path(raw: str) -> Path | None:
    """Resolve a path and ensure it stays inside OUTPUT_DIR (anti path-traversal)."""
    if not raw:
        return None
    try:
        target = Path(raw).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    base = OUTPUT_DIR.resolve()
    if target != base and base not in target.parents:
        return None
    return target if target.is_file() else None


_PREVIEW_MIME = {
    ".html": "text/html; charset=utf-8",
    ".pdf": "application/pdf",
    ".json": "application/json; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".mmd": "text/plain; charset=utf-8",
    ".png": "image/png",
}


@app.get("/preview")
def preview() -> Response:
    target = _safe_output_path(request.args.get("path", ""))
    if target is None:
        return Response(status=404)
    mime = _PREVIEW_MIME.get(target.suffix.lower(), "text/plain; charset=utf-8")
    resp = send_file(target, mimetype=mime)
    resp.headers["Content-Disposition"] = "inline"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/download")
def download() -> Response:
    target = _safe_output_path(request.args.get("path", ""))
    if target is None:
        return Response(status=404)
    return send_file(target, as_attachment=True, download_name=target.name)


@app.get("/download-zip")
def download_zip() -> Response:
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return Response(status=404)
    base = (OUTPUT_DIR / domain).resolve()
    if OUTPUT_DIR.resolve() not in base.parents or not base.is_dir():
        return Response(status=404)
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in base.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(base.parent))
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"{domain}.zip", mimetype="application/zip")


@app.get("/api/result")
def api_result() -> dict | tuple[dict, int]:
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    domain_dir = OUTPUT_DIR / domain
    if not domain_dir.is_dir():
        return {"error": "not found"}, 404

    def path_of(name: str) -> str:
        f = domain_dir / name
        return str(f.resolve()) if f.exists() else ""

    shots_dir = domain_dir / "screenshots"
    shots = sorted(shots_dir.glob("*.png")) if shots_dir.is_dir() else []
    return {
        "summary": _summary_for_domain(domain),
        "files": {
            "html": path_of("report.html"),
            "pdf": path_of("report.pdf"),
            "json": path_of("report.json"),
            "excel": path_of("spec.xlsx"),
            "screens_md": path_of("screens.md"),
            "forms_md": path_of("forms.md"),
            "transition_mmd": path_of("transition.mmd"),
            "diff": path_of("diff_report.html"),
        },
        "screenshots": [str(s.resolve()) for s in shots],
    }


def _fmt_snap_ts(stem: str) -> str:
    try:
        return datetime.strptime(stem, "%Y%m%d-%H%M%S").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return stem


@app.get("/api/snapshots")
def api_snapshots() -> dict | tuple[dict, int]:
    """サイトのクロール履歴（スナップショット）一覧。新しい順。"""
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    snaps_dir = OUTPUT_DIR / domain / "snapshots"
    items: list[dict] = []
    if snaps_dir.is_dir():
        for f in sorted(snaps_dir.glob("*.json"), reverse=True):
            try:
                pages = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            forms = sum(len(p.get("forms", [])) for p in pages)
            fields = sum(len(fm.get("fields", [])) for p in pages for fm in p.get("forms", []))
            items.append({
                "id": f.stem,
                "label": _fmt_snap_ts(f.stem),
                "screens": len(pages),
                "forms": forms,
                "fields": fields,
            })
    return {"snapshots": items}


@app.get("/api/snapshot-diff")
def api_snapshot_diff() -> Response:
    """2つのスナップショット間の仕様ドリフト差分をHTMLで返す。"""
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return Response(status=404)
    snaps_dir = OUTPUT_DIR / domain / "snapshots"
    from_path = _safe_output_path(str(snaps_dir / (request.args.get("from", "") + ".json")))
    to_path = _safe_output_path(str(snaps_dir / (request.args.get("to", "") + ".json")))
    if from_path is None or to_path is None:
        return Response("<p style='font-family:sans-serif;padding:16px'>指定されたスナップショットが見つかりません。</p>", mimetype="text/html")
    if str(Path("src").resolve()) not in sys.path:
        sys.path.insert(0, str(Path("src").resolve()))
    try:
        from diff.differ import compute_diff
        from diff.snapshot import load_snapshot
        from generator.diff_reporter import generate_diff_report
    except ImportError:
        return Response(status=500)
    old_pages = load_snapshot(from_path)
    new_pages = load_snapshot(to_path)
    diff = compute_diff(old_pages, new_pages)
    report_html = generate_diff_report(
        diff=diff,
        old_label=_fmt_snap_ts(from_path.stem),
        new_label=_fmt_snap_ts(to_path.stem),
        target_url=f"https://{domain}/",
    )
    resp = Response(report_html, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/history")
def api_history() -> dict:
    items: list[dict] = []
    if OUTPUT_DIR.is_dir():
        domains = [d for d in OUTPUT_DIR.iterdir() if d.is_dir()]
        for d in sorted(domains, key=lambda p: p.stat().st_mtime, reverse=True):
            summary = _summary_for_domain(d.name)
            formats = [
                name for name, fname in (
                    ("HTML", "report.html"), ("PDF", "report.pdf"),
                    ("Excel", "spec.xlsx"), ("JSON", "report.json"),
                    ("MD", "screens.md"), ("差分", "diff_report.html"),
                )
                if (d / fname).exists()
            ]
            items.append({
                "domain": d.name,
                "screens": summary.get("screens", 0),
                "fields": summary.get("fields", 0),
                "updated": datetime.fromtimestamp(d.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                "formats": formats,
            })
    return {"items": items}


def _count_screens(screens_md: Path) -> int:
    if not screens_md.exists():
        return 0
    return sum(1 for line in screens_md.read_text(encoding="utf-8").splitlines() if SCREEN_ROW_RE.match(line))


def _sanitize(value: str) -> str:
    return value.strip().replace("\n", "").replace("\r", "")


def _read_env() -> dict[str, str]:
    data: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            data[key.strip()] = value.strip()
    return data


def _write_env(updates: dict[str, str]) -> None:
    # キー名を検証して .env への行インジェクションを防ぐ
    updates = {k: v for k, v in updates.items() if ENV_KEY_RE.match(k)}
    if not updates:
        return
    lines: list[str] = []
    seen: set[str] = set()
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if "=" in stripped and not stripped.startswith("#"):
                key = stripped.split("=", 1)[0].strip()
                if key in updates:
                    lines.append(f"{key}={updates[key]}")
                    seen.add(key)
                    continue
            lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 9:
        return "****"
    return f"{key[:5]}…{key[-4:]}"


@app.get("/api/settings")
def get_settings() -> dict:
    env = _read_env()
    key = env.get("OPENAI_API_KEY", "")
    return {
        "openai_key_set": bool(key),
        "openai_key_masked": _mask_key(key),
        "openai_model": env.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        "openai_org_id": env.get("OPENAI_ORG_ID", ""),
        "openai_project_id": env.get("OPENAI_PROJECT_ID", ""),
    }


@app.post("/api/settings")
def post_settings() -> dict:
    updates: dict[str, str] = {}
    api_key = _sanitize(request.form.get("api_key", ""))
    if api_key:
        updates["OPENAI_API_KEY"] = api_key
    if "model" in request.form:
        updates["OPENAI_MODEL"] = _sanitize(request.form.get("model", "")) or DEFAULT_OPENAI_MODEL
    if "org_id" in request.form:
        updates["OPENAI_ORG_ID"] = _sanitize(request.form.get("org_id", ""))
    if "project_id" in request.form:
        updates["OPENAI_PROJECT_ID"] = _sanitize(request.form.get("project_id", ""))
    if updates:
        _write_env(updates)
    return {"ok": True, "openai_key_set": bool(_read_env().get("OPENAI_API_KEY"))}


@app.get("/open")
def open_file() -> Response:
    target = _safe_output_path(request.args.get("path", ""))
    if target is not None:
        subprocess.Popen(["open", str(target)])
    return redirect(url_for("index"))


PORT = int(os.environ.get("WEBSPEC2DOC_PORT", "8765"))


def _open_browser() -> None:
    import time
    time.sleep(1.0)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    app.run(host="127.0.0.1", port=PORT, debug=False)
