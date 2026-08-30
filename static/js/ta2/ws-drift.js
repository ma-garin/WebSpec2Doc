/* ============================================================================
 * TA2 / ws-drift.js — 変更 WS の仕上げ（B3）
 *
 * panels.js の `#recrawl-btn` は「POST /api/ta2/recrawl が完了 = クロール完了」
 * を前提にしていたが、B2 でこの API はジョブを受け付けて即返すようになった。
 * そのため押下の配線をここで差し替え、完了までポーリングして待つ。
 *
 * panels.js は編集禁止（計画の禁止事項 1）。差し替えは
 *   1. cloneNode(true) でボタン自身に付いた listener を捨てる
 *   2. 新しいボタンに直接 listener を付け、stopPropagation で
 *      panels.js が document に張った委譲ハンドラまで届かせない
 * の 2 段で行う。
 *
 * 併せて、変更 WS の左ペイン（#ctx-card）に直近 2 回のクロール（基準 / 現在）を出す。
 * ========================================================================== */
(function () {
  'use strict';
  var T = window.TA2;
  if (!T) return;
  var S = T.state, $ = T.$, esc = T.esc;

  var POLL_MS = 2000;
  var DEFAULT_LABEL = '再クロール';
  var busy = false;
  var boundBtn = null;
  var snaps = null;
  var snapsLoading = null;

  function domain() {
    return S.domain || document.body.getAttribute('data-domain') || '';
  }

  /* ------------------------------------------------------- ボタンの差し替え */
  function bindButton() {
    var btn = $('#recrawl-btn');
    if (!btn || btn === boundBtn) return;
    var fresh = btn.cloneNode(true);
    if (btn.parentNode) btn.parentNode.replaceChild(fresh, btn);
    fresh.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation(); // panels.js の document 委譲ハンドラを止める
      start(fresh);
    });
    boundBtn = fresh;
  }

  function setBusy(btn, on) {
    if (!btn) return;
    if (on) {
      if (!btn.getAttribute('data-label')) {
        btn.setAttribute('data-label', btn.textContent || DEFAULT_LABEL);
      }
      btn.disabled = true;
      btn.textContent = 'クロール中…';
      btn.title = 'クロール完了まで待っています';
    } else {
      btn.disabled = false;
      btn.textContent = btn.getAttribute('data-label') || DEFAULT_LABEL;
      btn.title = '';
    }
  }

  /* ------------------------------------------------------------ 実行と監視 */
  function start(btn) {
    if (busy) return;
    var d = domain();
    if (!d) { T.toast('サイトが選ばれていません', 'ng'); return; }
    busy = true;
    setBusy(btn, true);
    T.api.post('/api/ta2/recrawl', { domain: d }).then(function (r) {
      var jobId = (r && r.job_id) || '';
      if (!jobId) { finish(btn, 'ng', '再クロールの受付に失敗しました'); return; }
      schedulePoll(btn, d, jobId);
    }, function (e) {
      finish(btn, 'ng', '再クロールを開始できません: ' + errText(e));
    });
  }

  function schedulePoll(btn, d, jobId) {
    window.setTimeout(function () { pollOnce(btn, d, jobId); }, POLL_MS);
  }

  function pollOnce(btn, d, jobId) {
    var url = '/api/ta2/recrawl/status?domain=' + encodeURIComponent(d)
      + '&job_id=' + encodeURIComponent(jobId);
    T.api.get(url).then(function (r) {
      var st = (r && r.status) || '';
      if (st === 'completed') { onCompleted(btn); return; }
      if (st === 'failed') { finish(btn, 'ng', '再クロールに失敗しました: ' + reasonOf(r)); return; }
      schedulePoll(btn, d, jobId);
    }, function (e) {
      finish(btn, 'ng', '再クロールの状態を取得できません: ' + errText(e));
    });
  }

  function onCompleted(btn) {
    finish(btn, 'ok', '再クロールが完了しました');
    T.loadDrift();
    T.loadMap();
    loadSnaps(true);
  }

  function finish(btn, cls, msg) {
    busy = false;
    setBusy(btn, false);
    T.toast(msg, cls);
  }

  function errText(e) {
    return (e && e.message) || '理由は取得できませんでした';
  }

  function reasonOf(r) {
    var tail = String((r && r.log_tail) || '').replace(/\s+$/, '');
    if (tail) {
      var lines = tail.split('\n');
      for (var i = lines.length - 1; i >= 0; i--) {
        if (lines[i].trim()) return lines[i].trim();
      }
    }
    var code = r && r.exit_code != null ? r.exit_code : null;
    return code === null ? '理由は記録されていません' : '終了コード ' + code;
  }

  /* ------------------------------------------- 左ペイン: 基準 / 現在の 2 件 */
  function snapBox() {
    var card = $('#ctx-card');
    if (!card) return null;
    var el = document.getElementById('ws-drift-snaps');
    if (!el || el.parentNode !== card) {
      el = document.createElement('div');
      el.id = 'ws-drift-snaps';
      card.appendChild(el);
    }
    return el;
  }

  function snapRow(label, s) {
    if (!s) {
      return '<dt>' + label + '</dt><dd>—（まだ記録がありません）</dd>';
    }
    return '<dt>' + label + '</dt><dd>' + esc(s.label || s.id || '')
      + '<br>' + esc(s.screens) + ' 画面 / ' + esc(s.fields) + ' 入力項目</dd>';
  }

  function renderSnaps() {
    if (S.view !== 'drift') return;
    var el = snapBox();
    if (!el) return;
    if (snaps === null) {
      el.innerHTML = '<dl><dt>クロール</dt><dd>読み込んでいます…</dd></dl>';
      return;
    }
    el.innerHTML = '<dl>'
      + snapRow('基準', snaps.length > 1 ? snaps[1] : null)
      + snapRow('現在', snaps.length > 0 ? snaps[0] : null)
      + '</dl>';
  }

  function loadSnaps(force) {
    var d = domain();
    if (!d) return Promise.resolve([]);
    if (snaps !== null && !force) { renderSnaps(); return Promise.resolve(snaps); }
    if (snapsLoading && !force) return snapsLoading;
    renderSnaps();
    snapsLoading = T.api.get('/api/snapshots?domain=' + encodeURIComponent(d)).then(function (r) {
      snaps = (r && r.snapshots) || [];
      snapsLoading = null;
      renderSnaps();
      return snaps;
    }, function () {
      snaps = [];
      snapsLoading = null;
      renderSnaps();
      return snaps;
    });
    return snapsLoading;
  }

  /* ws-shell.js の renderCtx は履歴取得後に #ctx-card を書き直すため、
     消えていたら描き直す（監視ではなく 1 回だけの遅延確認）。 */
  function keepSnaps() {
    window.setTimeout(function () {
      if (S.view !== 'drift') return;
      if (!document.getElementById('ws-drift-snaps')) renderSnaps();
    }, 600);
  }

  function onView(v) {
    var view = v || S.view;
    if (view !== 'drift') return;
    bindButton();
    loadSnaps(false);
    keepSnaps();
  }

  T.on('view', onView);
  T.on('boot', function () { bindButton(); onView(S.view); });
  if (document.readyState !== 'loading') bindButton();
  else document.addEventListener('DOMContentLoaded', bindButton);
})();
