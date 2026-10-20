/* ============================================================================
 * TA2 / ws-schedule.js — 定期実行と通知（C1）
 *
 *   GET|POST /schedule/config?domain=   フォームの読み書き
 *   GET      /schedule/status           次回・前回の実行予定
 *   GET      /schedule/history          直近 20 件の実行履歴
 *   POST     /schedule/notify/test      いまの設定で 1 通だけ送る
 *
 * 書き込み（POST）は web/routes/schedule.py の before_request で管理者に限られる。
 * 403 が返ったら全フィールドを disabled にして理由を出す（押せるのに失敗する状態を作らない）。
 * 「今すぐ実行」は置かない（/schedule/run-now は実際のクロールを積まないため）。
 * ========================================================================== */
(function () {
  'use strict';
  var T = window.TA2, S = T.state, $ = T.$, esc = T.esc;

  var loaded = false;      // 一度読んだら view 切替のたびに叩き直さない
  var readOnly = false;

  function el(id) { return $('#' + id); }

  function fields() {
    var list = [
      el('sched-interval'), el('sched-notify-type'), el('sched-endpoint'),
      el('sched-severity'), el('sched-timezone'), el('sched-retry'),
      el('sched-window-start'), el('sched-window-end'), el('sched-template'),
      el('sched-save'), el('sched-test')
    ];
    var boxes = document.querySelectorAll('#sched-weekdays input[name=weekday]');
    for (var i = 0; i < boxes.length; i++) list.push(boxes[i]);
    return list.filter(Boolean);
  }

  function setDisabled(node, off, why) {
    if (!node) return;
    node.disabled = !!off;
    if (off && why) node.title = why; else node.removeAttribute('title');
  }

  /** 通知先が「送らない」のときは宛先とテスト送信を閉じる（理由付き） */
  function syncNotifyState() {
    if (readOnly) return;
    var type = el('sched-notify-type');
    var none = !type || type.value === 'none';
    setDisabled(el('sched-endpoint'), none, '通知先を選ぶと入力できます');
    setDisabled(el('sched-test'), none, '通知先を選ぶと送信できます');
  }

  function lockAll(why) {
    readOnly = true;
    fields().forEach(function (f) { setDisabled(f, true, why); });
    var meta = el('sched-meta');
    if (meta) meta.textContent = why;
  }

  /* ------------------------------------------------------------------ 読み込み */
  function fill(cfg) {
    var set = function (id, v) { var n = el(id); if (n) n.value = v; };
    set('sched-interval', cfg.interval || 'disabled');
    set('sched-notify-type', cfg.notify_type || 'none');
    set('sched-severity', cfg.severity_filter || 'breaking');
    set('sched-timezone', cfg.timezone || 'Asia/Tokyo');
    set('sched-retry', cfg.retry_max == null ? 2 : cfg.retry_max);
    set('sched-window-start', cfg.window_start || '');
    set('sched-window-end', cfg.window_end || '');
    set('sched-template', cfg.notify_template || '');

    var endpoint = el('sched-endpoint');
    if (endpoint) {
      endpoint.value = '';
      endpoint.placeholder = cfg.notify_endpoint_set
        ? '保存済み（変更するときだけ入力してください）'
        : 'https://hooks.slack.com/services/...';
    }
    var days = (cfg.weekdays || []).map(String);
    var boxes = document.querySelectorAll('#sched-weekdays input[name=weekday]');
    for (var i = 0; i < boxes.length; i++) {
      boxes[i].checked = days.indexOf(boxes[i].value) >= 0;
    }
    syncNotifyState();
  }

  function collect() {
    var days = [];
    var boxes = document.querySelectorAll('#sched-weekdays input[name=weekday]');
    for (var i = 0; i < boxes.length; i++) {
      if (boxes[i].checked) days.push(parseInt(boxes[i].value, 10));
    }
    var retry = parseInt((el('sched-retry') || {}).value, 10);
    return {
      domain: S.domain,
      interval: (el('sched-interval') || {}).value || 'disabled',
      notify_type: (el('sched-notify-type') || {}).value || 'none',
      notify_endpoint: ((el('sched-endpoint') || {}).value || '').trim(),
      severity_filter: (el('sched-severity') || {}).value || 'breaking',
      notify_template: (el('sched-template') || {}).value || '',
      timezone: ((el('sched-timezone') || {}).value || 'Asia/Tokyo').trim(),
      weekdays: days,
      window_start: (el('sched-window-start') || {}).value || '',
      window_end: (el('sched-window-end') || {}).value || '',
      retry_max: isNaN(retry) ? 2 : retry
    };
  }

  function fmt(iso) {
    if (!iso) return '';
    var s = String(iso).replace('T', ' ');
    return s.length > 16 ? s.slice(0, 16) : s;
  }

  function renderStatus(st) {
    var box = el('sched-status');
    if (!box) return;
    if (!st || st.interval === 'disabled' || !st.next_run_at) {
      box.textContent = '定期実行は止まっています。間隔を選んで保存すると動きます。';
      return;
    }
    var last = st.last_run_at ? '（前回 ' + fmt(st.last_run_at) + '）' : '（まだ実行していません）';
    box.innerHTML = (window.WS2D ? WS2D.status.html('not_started', '次回予定') : '次回予定') + ' ' + esc(fmt(st.next_run_at)) + ' ' + esc(last);
  }

  var RESULT = { success: '成功', ok: '成功', completed: '成功', failed: '失敗', error: '失敗' };

  function renderHistory(items) {
    var body = el('sched-history');
    if (!body) return;
    if (!items || !items.length) {
      body.innerHTML = '<tr><td colspan="4" style="color:var(--tx3)">'
        + '定期実行の記録はまだありません。</td></tr>';
      return;
    }
    body.innerHTML = items.map(function (it) {
      var status = String(it.status || it.result || '');
      var label = RESULT[status] || status || '—';
      var pill = label === '失敗' ? 'p-fail' : (label === '成功' ? 'p-pass' : 'p-new');
      var changes = it.change_count == null ? '—' : (it.change_count + ' 件');
      var notified = it.notified === false ? '—（送信なし）'
        : (it.notify_type ? esc(it.notify_type) + ' へ送信' : '—');
      return '<tr><td>' + esc(fmt(it.at || it.ran_at)) + '</td>'
        + '<td><span class="pill ' + pill + '">' + esc(label) + '</span></td>'
        + '<td>' + esc(changes) + '</td><td>' + notified + '</td></tr>';
    }).join('');
  }

  function load(force) {
    if (!S.domain) return;
    if (loaded && !force) return;
    loaded = true;
    var d = encodeURIComponent(S.domain);
    T.api.get('/schedule/config?domain=' + d).then(fill, function (e) {
      var meta = el('sched-meta');
      if (meta) meta.textContent = '設定を読み込めませんでした: ' + e.message;
    });
    T.api.get('/schedule/status?domain=' + d).then(renderStatus, function () {
      var box = el('sched-status');
      if (box) box.textContent = '次回の予定を読み込めませんでした。';
    });
    T.api.get('/schedule/history?domain=' + d + '&limit=20').then(function (r) {
      renderHistory((r && r.items) || []);
    }, function () { renderHistory([]); });
  }

  /* -------------------------------------------------------------------- 保存 */
  function onError(e, action) {
    if (e && /403|管理者|admin|forbidden/i.test(e.message || '')) {
      lockAll('管理者のみ変更できます');
      T.toast('管理者のみ変更できます', 'ng');
      return;
    }
    T.toast(action + 'できませんでした: ' + (e && e.message), 'ng');
  }

  function save() {
    if (readOnly || !S.domain) return;
    var btn = el('sched-save');
    setDisabled(btn, true, '保存しています');
    T.api.post('/schedule/config', collect()).then(function (r) {
      setDisabled(btn, false);
      T.toast('保存しました', 'ok');
      renderStatus({
        interval: collect().interval,
        next_run_at: r && r.next_run_at,
        last_run_at: null
      });
      load(true);
    }, function (e) { setDisabled(btn, false); onError(e, '保存'); });
  }

  function notifyTest() {
    if (readOnly || !S.domain) return;
    var btn = el('sched-test');
    setDisabled(btn, true, '送信しています');
    T.api.post('/schedule/notify/test', collect()).then(function (r) {
      setDisabled(btn, false);
      syncNotifyState();
      T.toast((r && r.message) || 'テスト通知を送信しました', 'ok');
    }, function (e) {
      setDisabled(btn, false);
      syncNotifyState();
      onError(e, 'テスト通知を送信');
    });
  }

  /* -------------------------------------------------------------------- 配線 */
  function bind() {
    var form = el('sched-form');
    if (form) form.addEventListener('submit', function (e) { e.preventDefault(); save(); });
    var save_btn = el('sched-save');
    if (save_btn) save_btn.addEventListener('click', save);
    var test_btn = el('sched-test');
    if (test_btn) test_btn.addEventListener('click', notifyTest);
    var type = el('sched-notify-type');
    if (type) type.addEventListener('change', syncNotifyState);
  }

  bind();
  T.on('view', function (v) { if (v === 'schedule') load(false); });
  T.on('boot', function () { if (S.view === 'schedule') load(false); });
})();
