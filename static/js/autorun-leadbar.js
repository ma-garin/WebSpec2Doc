// AutoRun 主導線バー（最上部フル幅・固定）。
//
// 「いま何が起きていて、次に何を押せばよいか」を1箇所に常設する。
// 以前はこれが無く、確定操作が長い一覧の最下部にあったため画面外に出て
// 「先に進めない」状態になっていた（利用者の操作で発覚）。
//
// 表示する状態は5つ。色と内容で区別する。
//   busy   処理中        … いま何をしているか＋進捗。操作は中止のみ
//   stop   停止中(要判断) … なぜ止まったか。選択肢そのものをボタンに出す
//   ready  操作待ち      … STEP名＋残タスク数。押せる
//   blocked操作待ち(不可) … 押せない理由をボタンの手前に出す
//   done   完了          … 結果の要点
(function () {
  'use strict';

  var TONES = ['busy', 'stop', 'ready', 'blocked', 'done'];

  function $(id) { return document.getElementById(id); }
  function host() { return $('autorun-leadbar'); }

  function button(label, onClick, cls) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = cls || 'btn-primary';
    b.textContent = label;
    if (onClick) b.addEventListener('click', onClick);
    return b;
  }

  function hide() {
    var el = host();
    if (!el) return;
    el.style.display = 'none';
    el.replaceChildren();
  }

  /**
   * バーを描画する。
   * @param {object} state
   *   tone    'busy'|'stop'|'ready'|'blocked'|'done'
   *   title   左端の見出し（いま何が起きているか）
   *   meta    見出しの右に出す補足（残件数・経過など）
   *   reason  押せない理由（tone === 'blocked' のときボタン手前に出す）
   *   actions [{label, onClick, kind}] kind: 'primary'|'ghost'|'danger'
   */
  function set(state) {
    var el = host();
    if (!el || !state) return;
    el.style.display = '';
    el.replaceChildren();

    var tone = TONES.indexOf(state.tone) >= 0 ? state.tone : 'ready';
    el.className = 'autorun-leadbar is-' + tone;

    var title = document.createElement('span');
    title.className = 'autorun-leadbar-title';
    title.textContent = state.title || '';
    el.appendChild(title);

    if (state.meta) {
      var sep = document.createElement('span');
      sep.className = 'autorun-leadbar-sep';
      sep.textContent = '—';
      el.appendChild(sep);

      var meta = document.createElement('span');
      meta.className = 'autorun-leadbar-meta';
      meta.textContent = state.meta;
      el.appendChild(meta);
    }

    var tail = document.createElement('span');
    tail.className = 'autorun-leadbar-actions';

    // 押せないときは、必ず理由をボタンの手前に出す。
    // 「押しても何も起きない」を二度と作らない。
    if (state.reason) {
      var why = document.createElement('span');
      why.className = 'autorun-leadbar-reason';
      why.setAttribute('role', 'status');
      why.textContent = state.reason;
      tail.appendChild(why);
    }

    (state.actions || []).forEach(function (action) {
      if (!action || !action.label) return;
      var cls = action.kind === 'ghost' ? 'btn-outline-sm'
        : action.kind === 'danger' ? 'btn-outline-sm btn-danger-outline'
          : 'btn-primary';
      var b = button(action.label, action.onClick, cls);
      b.disabled = !!action.disabled;
      tail.appendChild(b);
    });

    el.appendChild(tail);
  }

  window.autorunLeadBar = { set: set, hide: hide };
})();
