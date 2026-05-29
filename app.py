from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, Response, redirect, request, send_file, url_for

app = Flask(__name__)

OUTPUT_DIR = Path("output")
SCREEN_ROW_RE = re.compile(r"^\|\s*\d+\s*\|")
ENV_FILE = Path(".env")
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DISCOVER_TIMEOUT_SEC = 180

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
      --surface-subtle:#E8F1FF;
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
      background: var(--bg); color: var(--text); font-size: 15px; line-height: 1.6;
    }
    body.app-page { overflow: hidden; }
    .app-shell { height: 100vh; display: grid; grid-template-columns: 248px minmax(0, 1fr); }
    .app-sidebar {
      height: 100vh; overflow: auto; padding: 22px 16px;
      display: flex; flex-direction: column; gap: 18px;
      background: #EDF5FF; border-right: 1px solid var(--border);
    }
    .app-brand { color: var(--text); text-decoration: none; font-size: 20px; font-weight: 700; }
    .app-nav { display: grid; gap: 6px; }
    .app-nav-item {
      display: flex; align-items: center; min-height: 44px; padding: 0 14px;
      border-radius: var(--radius); color: var(--text); text-decoration: none;
      background: transparent; border: 1px solid transparent; font-size: 14px;
      cursor: pointer; transition: background .15s, border-color .15s;
    }
    .app-nav-item:hover { background: #fff; border-color: var(--info-border); }
    .app-nav-item.is-active {
      background: #fff; border-color: var(--info-border); color: var(--primary-dark);
      box-shadow: inset 4px 0 0 var(--primary); font-weight: 600;
    }
    .app-sidebar-section {
      font-size: 11px; font-weight: 800; text-transform: uppercase;
      letter-spacing: .06em; color: var(--text-muted); padding: 0 14px;
    }
    .app-main { min-width: 0; height: 100vh; display: flex; flex-direction: column; }
    .app-topbar {
      display: flex; align-items: center; justify-content: space-between; gap: 16px;
      padding: 18px 30px; border-bottom: 1px solid var(--border);
      background: rgba(247,251,255,.96); backdrop-filter: blur(10px); flex-shrink: 0;
    }
    .app-topbar-kicker {
      color: var(--text-muted); font-size: 11px; font-weight: 800;
      letter-spacing: .06em; text-transform: uppercase; margin-bottom: 3px;
    }
    .app-topbar-title { font-size: 24px; font-weight: 700; line-height: 1.15; }
    .app-content { flex: 1; overflow: auto; padding: 28px 30px; }
    .app-content-inner { max-width: 880px; }
    .app-content.is-executing { overflow: hidden; padding: 16px 20px; height: 100%; }
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
      height: 44px; padding: 0 22px; background: var(--primary); color: #fff;
      border: none; border-radius: 4px; font-size: 15px; font-weight: 600;
      cursor: pointer; white-space: nowrap; transition: background .15s;
    }
    .btn-primary:hover:not(:disabled) { background: var(--primary-dark); }
    .btn-primary:disabled { opacity: .5; cursor: not-allowed; }
    .btn-outline-sm {
      display: inline-flex; align-items: center; height: 36px; padding: 0 16px;
      border: 1px solid var(--border); border-radius: 4px; font-size: 13px; font-weight: 500;
      color: var(--text); background: var(--surface); text-decoration: none; cursor: pointer;
      transition: border-color .15s, background .15s, color .15s;
    }
    .btn-outline-sm:hover { border-color: var(--info-border); color: var(--primary-dark); background: var(--info-bg); }
    .btn-outline-sm:disabled { opacity: .45; cursor: not-allowed; }

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
    .execution-progress { width: 100%; height: 6px; border-radius: 2px; background: #D0E2FF; overflow: hidden; }
    .execution-progress-bar { height: 100%; width: 4%; border-radius: inherit; background: linear-gradient(90deg,#0F62FE 0%,#4589FF 55%,#78A9FF 100%); transition: width .45s ease; position: relative; overflow: hidden; }
    .execution-progress-bar::after { content: ''; position: absolute; inset: 0; background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,.42) 50%, transparent 100%); animation: shimmer 1.4s linear infinite; }
    .execution-steps { display: grid; grid-template-columns: repeat(4,1fr); gap: 6px; }
    .execution-step { border: 1px solid var(--border); border-radius: 4px; padding: 5px 8px; font-size: 11px; color: var(--text-muted); background: var(--surface-soft); text-align: center; transition: border-color .2s, background .2s, color .2s; }
    .execution-step.is-active { border-color: var(--info-border); background: var(--info-bg); color: var(--primary-dark); }
    .execution-step.is-complete { border-color: #bdddb0; background: var(--ok-bg); color: var(--ok); }
    .execution-preview-frame { flex: 1; min-height: 0; border-radius: var(--radius); overflow: hidden; border: 1px solid var(--border); background: #D0E2FF; display: flex; align-items: center; justify-content: center; }
    .execution-preview-image { display: none; width: 100%; height: 100%; object-fit: contain; background: #EDF5FF; }
    .execution-preview-image.show { display: block; }
    .execution-preview-placeholder { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: var(--text-muted); text-align: center; padding: 20px; }
    .execution-preview-placeholder.hidden { display: none; }
    .execution-log { flex-shrink: 0; background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px; font-size: .78rem; white-space: pre-wrap; max-height: 130px; overflow-y: auto; }
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

    /* ── 完了モーダル ── */
    .modal-overlay { position: fixed; inset: 0; background: rgba(22,22,22,.45); display: flex; align-items: center; justify-content: center; z-index: 50; padding: 20px; }
    .modal-overlay.hidden { display: none; }
    .completion-modal { width: 100%; max-width: 460px; background: var(--surface); border-radius: 12px; box-shadow: 0 20px 60px rgba(0,0,0,.25); overflow: hidden; }
    .cm-header { display: flex; align-items: center; gap: 14px; padding: 22px 24px 0; }
    .cm-check-icon { width: 44px; height: 44px; border-radius: 50%; background: var(--ok-bg); color: var(--ok); display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: 800; flex-shrink: 0; }
    .cm-title { font-size: 20px; line-height: 1.2; }
    .cm-subtitle { color: var(--text-muted); font-size: 13px; margin-top: 2px; }
    .cm-body { padding: 20px 24px; }
    .cm-severities { display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; }
    .cm-sev { border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-soft); padding: 14px; text-align: center; }
    .cm-sev-num { display: block; font-size: 26px; font-weight: 800; color: var(--primary-dark); }
    .cm-sev-label { font-size: 12px; color: var(--text-muted); }
    .cm-actions { display: flex; gap: 10px; padding: 0 24px 24px; }
    .cm-btn-primary { flex: 1; height: 44px; border: none; border-radius: 4px; background: var(--primary); color: #fff; font-size: 14px; font-weight: 700; cursor: pointer; }
    .cm-btn-primary:hover { background: var(--primary-dark); }
    .cm-btn-close { height: 44px; padding: 0 18px; border: 1px solid var(--border); border-radius: 4px; background: var(--surface); color: var(--text); font-size: 14px; font-weight: 600; cursor: pointer; }

    .app-footer { display: flex; align-items: center; justify-content: space-between; padding: 14px 30px; border-top: 1px solid var(--border); background: rgba(247,251,255,.96); color: var(--text-muted); font-size: 12px; flex-shrink: 0; }
    table.data { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
    table.data th { background: var(--surface-soft); color: var(--text-muted); font-size: 12px; font-weight: 800; text-align: left; padding: 12px 14px; border-bottom: 1px solid var(--border); }
    table.data td { padding: 12px 14px; border-bottom: 1px solid var(--border); font-size: 14px; }
    table.data tr:last-child td { border-bottom: none; }
    table.data tbody tr:hover { background: var(--surface-soft); }
    .num { font-variant-numeric: tabular-nums; }
    .history-actions { display: flex; gap: 8px; flex-wrap: wrap; }
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
  </style>
</head>
<body class="app-page">
<div class="app-shell">

  <aside class="app-sidebar">
    <a href="/" class="app-brand">WebSpec2Doc</a>
    <nav class="app-nav">
      <button class="app-nav-item is-active" data-view="generate">ドキュメント生成</button>
      <button class="app-nav-item" data-view="history">実行履歴</button>
      <button class="app-nav-item" data-view="settings">設定</button>
    </nav>
    <div style="margin-top:auto">
      <p class="app-sidebar-section">出力先</p>
      <p style="font-size:12px;color:var(--text-muted);padding:8px 14px 0;line-height:1.6">
        output/{ドメイン名}/<br>に生成されます
      </p>
    </div>
  </aside>

  <div class="app-main">
    <header class="app-topbar">
      <div>
        <p class="app-topbar-kicker" id="topbar-kicker">Generate</p>
        <h1 class="app-topbar-title" id="topbar-title">QA テストインプット文書を生成する</h1>
      </div>
      <a href="https://github.com/ma-garin/WebSpec2Doc" target="_blank" class="btn-outline-sm">GitHub</a>
    </header>

    <main class="app-content" id="app-content">
      <div class="app-content-inner">

        <!-- ===== 生成ビュー ===== -->
        <section class="view is-active" id="view-generate">
          <div id="gen-panel">
            <div class="input-card">
              <nav class="wizard-progress" aria-label="設定ステップ">
                <div class="wizard-step-node is-active" id="wnode-1"><div class="wizard-step-circle">1</div><span class="wizard-step-label">対象設定</span></div>
                <div class="wizard-step-line" id="wline-12"></div>
                <div class="wizard-step-node" id="wnode-2"><div class="wizard-step-circle">2</div><span class="wizard-step-label">出力設定</span></div>
                <div class="wizard-step-line" id="wline-23"></div>
                <div class="wizard-step-node" id="wnode-3"><div class="wizard-step-circle">3</div><span class="wizard-step-label">オプション</span></div>
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
                        <input type="radio" name="crawl-mode" value="single" checked />
                        <span class="crawl-mode-label"><strong>単体ページで生成</strong><span class="crawl-mode-desc">入力した1ページだけをドキュメント化します</span></span>
                      </label>
                      <label class="crawl-mode-option">
                        <input type="radio" name="crawl-mode" value="crawl" />
                        <span class="crawl-mode-label"><strong>オートクローリング</strong><span class="crawl-mode-desc">画面リストを取得して、選択したページだけをドキュメント化します</span></span>
                      </label>
                      <div class="crawl-discovery-section" id="crawl-discovery-section" style="display:none">
                        <div class="crawl-depth-row">
                          <label for="crawl-depth" class="crawl-depth-label">収集する階層数</label>
                          <input type="number" id="crawl-depth" class="crawl-depth-input" value="2" min="1" max="5" />
                          <span class="crawl-depth-unit">階層</span>
                          <label for="max-pages" class="crawl-depth-label">最大</label>
                          <input type="number" id="max-pages" class="crawl-depth-input" value="30" min="1" max="200" />
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

                  <div class="wizard-footer">
                    <button type="button" class="btn-primary" id="wnext-1">次へ：出力設定 →</button>
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
                    <button type="button" class="btn-primary" id="wnext-2">次へ：オプション設定 →</button>
                  </div>
                </div>

                <!-- ページ3: オプション -->
                <div class="wizard-page" id="wpage-3">
                  <div class="wizard-page-header"><h2>オプション設定</h2><p>ログイン後ページを対象にする場合は、保存済みセッションを指定します。</p></div>
                  <div class="wizard-section">
                    <p class="app-sidebar-section" style="padding:0 0 10px">ログイン設定（任意）</p>
                    <div class="login-fields">
                      <div class="field login-field-full">
                        <label for="auth-path">認証セッション auth.json パス</label>
                        <input type="text" id="auth-path" placeholder="auth.json" />
                      </div>
                    </div>
                    <p class="input-hint">事前に <code>python src/main.py --login &lt;ログインURL&gt;</code> で保存した auth.json のパスを指定すると、認証後ページをクロールできます。</p>
                  </div>
                  <div class="wizard-footer">
                    <button type="button" class="btn-outline-sm" id="wback-3">← 戻る</button>
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
              <div class="execution-bottombar-actions hidden" id="exec-actions">
                <a id="exec-report-btn" class="btn-primary" style="display:none;align-items:center" target="_blank">レポートを見る</a>
                <a id="exec-pdf-btn" class="btn-outline-sm" style="display:none" target="_blank">PDF</a>
                <button type="button" id="exec-new-btn" class="btn-outline-sm">新しく生成</button>
              </div>
            </div>
          </div>
        </section>

        <!-- ===== 履歴ビュー ===== -->
        <section class="view" id="view-history">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
            <p style="color:var(--text-muted);font-size:13px">過去に生成したドキュメント（output/ フォルダ）</p>
            <button class="btn-outline-sm" id="reload-history">再読み込み</button>
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
                <div class="field"><label for="set-max">最大ページ数（既定）</label><input type="number" id="set-max" min="1" max="200"></div>
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

<!-- 完了モーダル -->
<div class="modal-overlay hidden" id="completion-modal">
  <div class="completion-modal" role="dialog" aria-modal="true">
    <div class="cm-header">
      <span class="cm-check-icon">✓</span>
      <div><h2 class="cm-title">生成完了</h2><p class="cm-subtitle" id="cm-subtitle">-</p></div>
    </div>
    <div class="cm-body">
      <div class="cm-severities">
        <div class="cm-sev"><span class="cm-sev-num" id="cm-screens">0</span><span class="cm-sev-label">画面数</span></div>
        <div class="cm-sev"><span class="cm-sev-num" id="cm-forms">0</span><span class="cm-sev-label">フォーム数</span></div>
        <div class="cm-sev"><span class="cm-sev-num" id="cm-fields">0</span><span class="cm-sev-label">入力項目数</span></div>
      </div>
    </div>
    <div class="cm-actions">
      <button type="button" class="cm-btn-primary" id="cm-detail-btn">レポートを見る</button>
      <button type="button" class="cm-btn-close" id="cm-close-btn">閉じる</button>
    </div>
  </div>
</div>

<script>
const SETTINGS_KEY = 'webspec2doc.settings';
const views = { generate: ['Generate','QA テストインプット文書を生成する'], history: ['History','実行履歴'], settings: ['Settings','設定'] };
const escHtml = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// ---- ナビ切替 ----
document.querySelectorAll('.app-nav-item').forEach(btn => btn.addEventListener('click', () => switchView(btn.dataset.view)));
function switchView(name) {
  document.querySelectorAll('.app-nav-item').forEach(b => b.classList.toggle('is-active', b.dataset.view === name));
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('is-active', v.id === 'view-' + name));
  document.getElementById('topbar-kicker').textContent = views[name][0];
  document.getElementById('topbar-title').textContent = views[name][1];
  if (name === 'history') loadHistory();
}

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
    if (!data.items.length) { body.innerHTML = '<div class="empty">まだ生成履歴がありません。「ドキュメント生成」から実行してください。</div>'; return; }
    let html = '<table class="data"><thead><tr><th>ドメイン</th><th class="num">画面数</th><th>更新日時</th><th>操作</th></tr></thead><tbody>';
    for (const it of data.items) {
      const actions = [];
      if (it.report) actions.push(`<a class="btn-outline-sm" href="/open?path=${encodeURIComponent(it.report)}">レポート</a>`);
      if (it.pdf) actions.push(`<a class="btn-outline-sm" href="/open?path=${encodeURIComponent(it.pdf)}">PDF</a>`);
      if (it.json) actions.push(`<a class="btn-outline-sm" href="/open?path=${encodeURIComponent(it.json)}">JSON</a>`);
      if (it.diff) actions.push(`<a class="btn-outline-sm" href="/open?path=${encodeURIComponent(it.diff)}">差分</a>`);
      html += `<tr><td>${escHtml(it.domain)}</td><td class="num">${it.screens}</td><td>${escHtml(it.updated)}</td><td><div class="history-actions">${actions.join('') || '<span style="color:#999">—</span>'}</div></td></tr>`;
    }
    html += '</tbody></table>';
    body.innerHTML = html;
  } catch (e) { body.innerHTML = '<div class="empty">履歴の読み込みに失敗しました。</div>'; }
}
document.getElementById('reload-history').addEventListener('click', loadHistory);

// ====================== ウィザード ======================
let wizardStep = 1;
let discovered = [];
const urlInput = document.getElementById('url-input');
const crawlDiscoverySection = document.getElementById('crawl-discovery-section');
const manualUrlSection = document.getElementById('manual-url-section');
const targetPreview = document.getElementById('target-preview');
const targetPreviewList = document.getElementById('target-preview-list');

function showStep(n) {
  for (let i = 1; i <= 3; i++) {
    document.getElementById('wpage-' + i).classList.toggle('is-active', i === n);
    const node = document.getElementById('wnode-' + i);
    node.classList.toggle('is-active', i === n);
    node.classList.toggle('is-done', i < n);
  }
  document.getElementById('wline-12').classList.toggle('is-done', n > 1);
  document.getElementById('wline-23').classList.toggle('is-done', n > 2);
  wizardStep = n;
}
function selectedMode() { return (document.querySelector('input[name=crawl-mode]:checked') || {}).value || 'single'; }

document.querySelectorAll('input[name=crawl-mode]').forEach(r => r.addEventListener('change', () => {
  const m = selectedMode();
  crawlDiscoverySection.style.display = m === 'crawl' ? '' : 'none';
  manualUrlSection.style.display = m === 'manual' ? '' : 'none';
  updateTargetPreview();
}));
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
document.getElementById('wnext-2').addEventListener('click', () => {
  if (![...document.querySelectorAll('input[name=fmt]:checked')].length) { alert('出力形式を1つ以上選んでください'); return; }
  showStep(3);
});
document.getElementById('wback-3').addEventListener('click', () => showStep(2));

function setUrlMessage(msg, isError) {
  const el = document.getElementById('url-input-message');
  el.textContent = msg; el.classList.toggle('input-field-message-error', !!(msg && isError));
}

// ---- 画面リスト取得（discover）----
document.getElementById('discover-btn').addEventListener('click', discoverUrls);
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
      <span><strong>${escHtml(it.title || ('タイトル未取得 ' + (i + 1)))}</strong><code>${escHtml(it.url)}</code></span>
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
const execReportBtn = document.getElementById('exec-report-btn');
const execPdfBtn = document.getElementById('exec-pdf-btn');
const previewImage = document.getElementById('exec-preview-image');
const previewPlaceholder = document.getElementById('exec-preview-placeholder');
const estep = [0,1,2,3].map(i => document.getElementById('estep-' + i));
let timer, startTime, previewTimer, activeDomain = '';

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

document.getElementById('form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const urls = buildTargetUrls();
  if (!urls.length) { showStep(1); setUrlMessage('対象URLが確定していません', true); return; }
  const fmts = [...document.querySelectorAll('input[name=fmt]:checked')].map(c => c.value);
  if (!fmts.length) { showStep(2); return; }
  activeDomain = domainOf(urls[0]);
  const body = new URLSearchParams({
    urls: urls.join(','),
    depth: document.getElementById('crawl-depth').value,
    max_pages: document.getElementById('max-pages').value,
    format: fmts.join(','),
    compare: document.getElementById('compare').checked ? 'true' : 'false',
    auth: document.getElementById('auth-path').value.trim() || getSettings().auth || '',
  });

  genPanel.style.display = 'none';
  executionView.classList.remove('hidden');
  appContent.classList.add('is-executing');
  execError.classList.add('hidden'); execActions.classList.add('hidden');
  execReportBtn.style.display = 'none'; execPdfBtn.style.display = 'none';
  previewImage.classList.remove('show'); previewPlaceholder.classList.remove('hidden');
  execLog.textContent = '';
  execTarget.textContent = urls.length > 1 ? `${urls[0]} ほか ${urls.length - 1}件` : urls[0];
  execTitle.textContent = 'クロール中…'; execMessage.textContent = `${urls.length}件の対象をクロールしてドキュメント化します。`;
  execPhase.textContent = '実行中'; setStep(0); startTimer(); startPreviewPolling();

  let reportPath = '', pdfPath = '', summary = null, ok = false, cur = 0;
  try {
    const res = await fetch('/run', { method: 'POST', body });
    const reader = res.body.getReader(); const dec = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      let chunk = dec.decode(value);
      const rp = chunk.match(/REPORT_PATH:(.*)/); if (rp) { reportPath = rp[1].trim(); ok = true; }
      const pp = chunk.match(/PDF_PATH:(.*)/); if (pp) pdfPath = pp[1].trim();
      const sm = chunk.match(/SUMMARY:(.*)/); if (sm) { try { summary = JSON.parse(sm[1].trim()); ok = true; } catch {} }
      const clean = chunk.replace(/(REPORT_PATH|PDF_PATH|SUMMARY):.*\\n?/g, '');
      execLog.textContent += clean; execLog.scrollTop = execLog.scrollHeight;
      for (const line of clean.split('\\n')) { const st = guessStep(line); if (st >= 0 && st >= cur) { cur = st; setStep(st); } }
    }
  } catch (err) { execLog.textContent += '\\n通信エラー: ' + err.message; }

  stopTimer(); stopPreviewPolling();
  execActions.classList.remove('hidden');
  if (ok || reportPath) {
    setStep(4); execProgressBar.style.width = '100%';
    estep.forEach(el => el.className = 'execution-step is-complete');
    execTitle.textContent = '生成が完了しました'; execPhase.textContent = '完了';
    execMessage.textContent = 'ドキュメントを生成しました。レポートで内容を確認できます。';
    if (reportPath) { execReportBtn.href = '/open?path=' + encodeURIComponent(reportPath); execReportBtn.style.display = 'inline-flex'; }
    if (pdfPath) { execPdfBtn.href = '/open?path=' + encodeURIComponent(pdfPath); execPdfBtn.style.display = 'inline-flex'; }
    showCompletionModal(summary, reportPath);
  } else {
    execTitle.textContent = 'エラー'; execPhase.textContent = 'エラー'; execError.classList.remove('hidden');
  }
});

document.getElementById('exec-new-btn').addEventListener('click', () => {
  executionView.classList.add('hidden'); appContent.classList.remove('is-executing');
  genPanel.style.display = ''; showStep(1);
});

// ---- 完了モーダル ----
const completionModal = document.getElementById('completion-modal');
function showCompletionModal(summary, reportPath) {
  const s = summary || {};
  document.getElementById('cm-screens').textContent = s.screens || 0;
  document.getElementById('cm-forms').textContent = s.forms || 0;
  document.getElementById('cm-fields').textContent = s.fields || 0;
  document.getElementById('cm-subtitle').textContent = `${s.screens || 0}画面 / ${s.forms || 0}フォーム / ${s.fields || 0}入力項目を検出`;
  const detailBtn = document.getElementById('cm-detail-btn');
  detailBtn.style.display = reportPath ? '' : 'none';
  detailBtn.onclick = () => { if (reportPath) window.open('/open?path=' + encodeURIComponent(reportPath), '_blank'); };
  completionModal.classList.remove('hidden');
}
document.getElementById('cm-close-btn').addEventListener('click', () => completionModal.classList.add('hidden'));
completionModal.addEventListener('click', e => { if (e.target === completionModal) completionModal.classList.add('hidden'); });

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
applySettings(); loadSettingsForm(); loadApiSettings(); loadUrlHistory(); updateTargetPreview();
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
    depth = request.form.get("depth", "2")
    max_pages = request.form.get("max_pages", "30")
    auth = request.form.get("auth", "").strip()
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


@app.post("/run")
def run() -> Response:
    urls = request.form.get("urls", "").strip()
    depth = request.form.get("depth", "2")
    max_pages = request.form.get("max_pages", "30")
    fmt = request.form.get("format", "md,html")
    compare = request.form.get("compare", "false") == "true"
    auth = request.form.get("auth", "").strip()
    domain = _domain_of(urls.split(",")[0]) if urls else ""

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
        for line in proc.stdout:  # type: ignore[union-attr]
            yield line
        proc.wait()
        domain_dir = OUTPUT_DIR / domain
        report = domain_dir / "report.html"
        pdf = domain_dir / "report.pdf"
        if report.exists():
            yield f"REPORT_PATH:{report.resolve()}\n"
        if pdf.exists():
            yield f"PDF_PATH:{pdf.resolve()}\n"
        yield f"SUMMARY:{json.dumps(_summary_for_domain(domain))}\n"
        if proc.returncode != 0:
            yield "\nエラーが発生しました。\n"

    return Response(generate(), mimetype="text/plain")


@app.get("/api/live-screenshot")
def live_screenshot() -> Response:
    domain = request.args.get("domain", "")
    shots_dir = OUTPUT_DIR / domain / "screenshots"
    if not domain or not shots_dir.is_dir():
        return Response(status=404)
    pngs = sorted(shots_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pngs:
        return Response(status=404)
    resp = send_file(pngs[0].resolve(), mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _summary_for_domain(domain: str) -> dict[str, int]:
    domain_dir = OUTPUT_DIR / domain
    snaps_dir = domain_dir / "snapshots"
    snaps = sorted(snaps_dir.glob("*.json")) if snaps_dir.is_dir() else []
    if not snaps:
        return {"screens": _count_screens(domain_dir / "screens.md"), "forms": 0, "fields": 0}
    try:
        pages = json.loads(snaps[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"screens": 0, "forms": 0, "fields": 0}
    forms = sum(len(p.get("forms", [])) for p in pages)
    fields = sum(len(f.get("fields", [])) for p in pages for f in p.get("forms", []))
    return {"screens": len(pages), "forms": forms, "fields": fields}


@app.get("/api/history")
def api_history() -> dict:
    items: list[dict] = []
    if OUTPUT_DIR.is_dir():
        domains = [d for d in OUTPUT_DIR.iterdir() if d.is_dir()]
        for d in sorted(domains, key=lambda p: p.stat().st_mtime, reverse=True):
            report = d / "report.html"
            diff = d / "diff_report.html"
            pdf = d / "report.pdf"
            report_json = d / "report.json"
            items.append({
                "domain": d.name,
                "screens": _count_screens(d / "screens.md"),
                "updated": datetime.fromtimestamp(d.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                "report": str(report.resolve()) if report.exists() else "",
                "diff": str(diff.resolve()) if diff.exists() else "",
                "pdf": str(pdf.resolve()) if pdf.exists() else "",
                "json": str(report_json.resolve()) if report_json.exists() else "",
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
    path = request.args.get("path", "")
    if path and Path(path).exists():
        subprocess.Popen(["open", path])
    return redirect(url_for("index"))


PORT = 8765


def _open_browser() -> None:
    import time
    time.sleep(1.0)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    app.run(port=PORT, debug=False)
