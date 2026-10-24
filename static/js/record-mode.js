// ====================== 記録＆リプレイ（「操作を記録して作る」） ======================
// 見えるブラウザで操作を記録し、そこから文書・テストケースを作る第3の入力方式。
// 配線のみ（表示・整形はサーバの応答をそのまま使う）。ポーリングは1秒間隔。
(function () {
  'use strict';

  const state = { pid: null, domain: '', timer: null };

  function $(id) { return document.getElementById(id); }

  function hostOf(u) {
    try { return new URL(u).host; } catch (e) { return ''; }
  }

  function setStatus(msg, isError) {
    const el = $('record-status');
    if (!el) return;
    el.textContent = msg || '';
    el.classList.toggle('input-field-message-error', !!(msg && isError));
  }

  function setResult(html) {
    const el = $('record-result');
    if (el) el.innerHTML = html;
  }

  function stopPolling() {
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
  }

  const RECORD_PHASE_TEXT = {
    idle: '記録は開始されていません',
    recording: '記録中…',
    stopped: '記録を終了しました。',
  };

  function renderStatus(data) {
    const phase = data.phase || 'idle';
    const parts = [RECORD_PHASE_TEXT[phase] || phase];
    if (typeof data.actions === 'number') parts.push('操作 ' + data.actions + ' 件');
    if (data.last_url) parts.push(data.last_url);
    if (!data.last_screenshot_abs && data.last_screenshot) parts.push('スクショ: ' + data.last_screenshot);
    setStatus(parts.filter(Boolean).join(' / '), false);

    const shot = $('record-last-shot');
    if (shot) {
      if (data.last_screenshot_abs) {
        shot.src = '/preview?path=' + encodeURIComponent(data.last_screenshot_abs);
        shot.style.display = '';
      } else {
        shot.removeAttribute('src');
        shot.style.display = 'none';
      }
    }

    const stopBtn = $('record-stop-btn');
    const startBtn = $('record-start-btn');
    const finalizeBtn = $('record-finalize-btn');
    // 主ボタンは同時に 1 個: 開始 → 記録中は終了 → 終了後は「文書を作る」に差し替える
    if (phase === 'recording') {
      if (stopBtn) stopBtn.style.display = '';
      if (startBtn) { startBtn.disabled = true; startBtn.style.display = 'none'; }
    } else if (phase === 'stopped') {
      if (stopBtn) stopBtn.style.display = 'none';
      if (startBtn) { startBtn.disabled = false; startBtn.style.display = 'none'; }
      if (finalizeBtn) finalizeBtn.style.display = '';
      stopPolling();
    } else {
      if (stopBtn) stopBtn.style.display = 'none';
      if (startBtn) { startBtn.disabled = false; startBtn.style.display = ''; }
    }
  }

  async function pollStatus() {
    if (!state.domain) return;
    try {
      const res = await fetch('/api/record/status?domain=' + encodeURIComponent(state.domain), { credentials: 'same-origin' });
      const data = await res.json();
      renderStatus(data || {});
    } catch (e) {
      // ポーリング失敗は次回に任せる（ネットワーク瞬断等）
    }
  }

  const startBtn = $('record-start-btn');
  if (startBtn) startBtn.addEventListener('click', async () => {
    const urlEl = $('url-input');
    const url = urlEl ? urlEl.value.trim() : '';
    if (!url) { setStatus('先に解析対象URLを入力してください', true); return; }
    const domain = hostOf(url);
    if (!domain) { setStatus('URL の形式が正しくありません', true); return; }
    state.domain = domain;
    const authEl = $('auth-path');
    const auth = authEl ? authEl.value.trim() : '';
    startBtn.disabled = true;
    setStatus('記録用ブラウザを起動しています…', false);
    setResult('');
    try {
      const body = { url: url, domain_name: domain };
      if (auth) body.auth = auth;
      const res = await fetch('/api/record/start', { method: 'POST', credentials: 'same-origin', body: new URLSearchParams(body) });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || '起動に失敗しました');
      state.pid = data.pid;
      state.domain = data.domain || domain;
      setStatus('記録用ブラウザを起動しました。操作するとここに反映されます。', false);
      stopPolling();
      state.timer = setInterval(pollStatus, 1000);
      pollStatus();
    } catch (e) {
      setStatus(e.message || '起動に失敗しました', true);
      startBtn.disabled = false;
    }
  });

  const stopBtn = $('record-stop-btn');
  if (stopBtn) stopBtn.addEventListener('click', async () => {
    if (!state.domain) return;
    stopBtn.disabled = true;
    setStatus('記録を終了しています…', false);
    try {
      const body = { domain: state.domain };
      if (state.pid) body.pid = String(state.pid);
      const res = await fetch('/api/record/stop', { method: 'POST', credentials: 'same-origin', body: new URLSearchParams(body) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || (data && data.ok === false)) throw new Error((data && data.error) || '終了に失敗しました');
      pollStatus();
    } catch (e) {
      setStatus(e.message || '終了に失敗しました', true);
    } finally {
      stopBtn.disabled = false;
    }
  });

  function renderFinalizeSteps(data) {
    const steps = (data && data.steps) || [];
    if (!steps.length) { setResult('<p class="input-field-message-error">結果を取得できませんでした</p>'); return; }
    const rows = steps.map(function (s) {
      const mark = s.ok ? '✓' : '✗';
      return '<li>' + mark + ' ' + escHtml(s.name || '') + (s.detail ? '（' + escHtml(s.detail) + '）' : '') + '</li>';
    }).join('');
    const domain = (data && data.domain) || state.domain;
    let html = '<ul style="margin:0 0 8px;padding-left:20px">' + rows + '</ul>';
    html += '<button type="button" id="record-show-report-btn" class="btn-outline-sm">レポートを見る</button>';
    setResult(html);
    const showBtn = $('record-show-report-btn');
    if (showBtn) showBtn.addEventListener('click', () => {
      if (typeof showResults === 'function') showResults(domain, 'overview');
    });
    const replayBtn = $('record-replay-btn');
    if (replayBtn) replayBtn.style.display = '';
  }

  const finalizeBtn = $('record-finalize-btn');
  if (finalizeBtn) finalizeBtn.addEventListener('click', async () => {
    if (!state.domain) return;
    finalizeBtn.disabled = true;
    setStatus('記録から文書を作成しています…', false);
    setResult('');
    try {
      const authEl = $('auth-path');
      const auth = authEl ? authEl.value.trim() : '';
      const body = { domain: state.domain };
      if (auth) body.auth = auth;
      const res = await fetch('/api/record/finalize', { method: 'POST', credentials: 'same-origin', body: new URLSearchParams(body) });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error((data && data.error) || '作成に失敗しました');
      setStatus('作成しました。', false);
      renderFinalizeSteps(data);
    } catch (e) {
      setStatus(e.message || '作成に失敗しました', true);
    } finally {
      finalizeBtn.disabled = false;
    }
  });

  function renderReplayResult(data) {
    const steps = (data && data.steps) || [];
    const summary = (data && data.summary) || {};
    const rows = steps.map(function (s) {
      return '<tr><td>' + escHtml(String(s.order != null ? s.order : '')) + '</td><td>' + escHtml(s.type || '')
        + '</td><td>' + escHtml(s.selector || '') + '</td><td>' + escHtml(s.status || '') + '</td></tr>';
    }).join('');
    let html = '<p>成功 ' + (summary.passed || 0) + ' / 失敗 ' + (summary.failed || 0) + ' / スキップ ' + (summary.skipped || 0) + '</p>';
    html += '<table class="data-table"><thead><tr><th>順序</th><th>種別</th><th>セレクタ</th><th>結果</th></tr></thead><tbody>' + rows + '</tbody></table>';
    setResult(html);
  }

  const replayBtn = $('record-replay-btn');
  if (replayBtn) replayBtn.addEventListener('click', async () => {
    if (!state.domain) return;
    replayBtn.disabled = true;
    setStatus('リプレイしています…', false);
    try {
      const res = await fetch('/api/record/replay', { method: 'POST', credentials: 'same-origin', body: new URLSearchParams({ domain: state.domain }) });
      const data = await res.json();
      if (!res.ok || (data && data.ok === false)) throw new Error((data && data.error) || 'リプレイに失敗しました');
      setStatus('リプレイが完了しました。', false);
      renderReplayResult(data);
    } catch (e) {
      setStatus(e.message || 'リプレイに失敗しました', true);
    } finally {
      replayBtn.disabled = false;
    }
  });

  const importBtn = $('record-import-btn');
  if (importBtn) importBtn.addEventListener('click', async () => {
    const fileEl = $('record-import-input');
    const file = fileEl && fileEl.files && fileEl.files[0];
    if (!file) { setStatus('取り込むファイルを選択してください', true); return; }
    const urlEl = $('url-input');
    const url = urlEl ? urlEl.value.trim() : '';
    const domain = state.domain || hostOf(url) || 'site';
    importBtn.disabled = true;
    setStatus('取り込んでいます…', false);
    try {
      const fd = new FormData();
      fd.append('domain', domain);
      fd.append('file', file);
      const res = await fetch('/api/record/import', { method: 'POST', credentials: 'same-origin', body: fd });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error((data && data.error) || '取り込みに失敗しました');
      state.domain = domain;
      setStatus('取り込みました。', false);
      const finalizeBtnEl = $('record-finalize-btn');
      if (finalizeBtnEl) {
        // 取り込み後は「取り込む」を「文書を作る」に差し替える（主ボタンは 1 個）
        importBtn.parentNode.appendChild(finalizeBtnEl);
        finalizeBtnEl.style.display = '';
        importBtn.style.display = 'none';
      }
    } catch (e) {
      setStatus(e.message || '取り込みに失敗しました', true);
    } finally {
      importBtn.disabled = false;
    }
  });

  // 入力方式の切替（URL から／操作を記録／記録ファイルから）。表示中の方式の欄だけを出す。
  const seg = $('gen-method');
  if (seg) {
    const apply = (method) => {
      seg.querySelectorAll('[data-method-tab]').forEach(b => {
        const on = b.dataset.methodTab === method;
        b.classList.toggle('is-active', on);
        b.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      document.querySelectorAll('#wizard-p1 [data-method]').forEach(el => { el.hidden = el.dataset.method !== method; });
    };
    seg.querySelectorAll('[data-method-tab]').forEach(b => b.addEventListener('click', () => apply(b.dataset.methodTab)));
    apply('url');
  }
  // ファイル選択部品: 選択名を隣に表示する
  document.querySelectorAll('[data-file-name-for]').forEach(nameEl => {
    const input = $(nameEl.dataset.fileNameFor);
    if (!input) return;
    input.addEventListener('change', () => {
      const names = Array.from(input.files || []).map(f => f.name);
      nameEl.textContent = names.length ? names.join('、') : '未選択';
    });
  });
})();
