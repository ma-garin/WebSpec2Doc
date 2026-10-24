// ====================== 通知・フィードバック（Notify） ======================
// 2 段構成: ①右上トースト（一過性の結果）②画面内の帯（その画面に居る間は残る状態）。
//   Notify.toast(message, { kind, next, timeout })
//   Notify.band(container, message, { kind, next, id, dismissible }) → 帯要素
//   Notify.clearBand(container, id)
// kind: success / info / warning / error。error と warning のトーストは自動で消さない。
// 常時表示が必要なログ（AutoRun の実行ログ等）は通知に流さず、画面内に出したままにする（折りたたまない）。
const Notify = (function () {
  const KINDS = ['success', 'info', 'warning', 'error'];
  const LABEL = { success: '完了', info: 'お知らせ', warning: '注意', error: '失敗' };
  const AUTO_MS = { success: 4000, info: 6000, warning: 0, error: 0 };
  const MAX_TOASTS = 4;

  function _kind(k) { return KINDS.includes(k) ? k : 'info'; }
  function _el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }
  function _stack() {
    let s = document.getElementById('notify-stack');
    if (!s) {
      s = _el('div', 'notify-stack');
      s.id = 'notify-stack';
      s.setAttribute('aria-live', 'polite');
      document.body.appendChild(s);
    }
    return s;
  }
  function _body(kind, message, next) {
    const frag = document.createDocumentFragment();
    const txt = _el('div', 'notify-text');
    txt.appendChild(_el('span', 'notify-label', LABEL[kind]));
    txt.appendChild(_el('span', 'notify-message', message));
    if (next) txt.appendChild(_el('span', 'notify-next', next));
    frag.appendChild(txt);
    return frag;
  }
  function _close(el, onClose) {
    const b = _el('button', 'notify-close', '閉じる');
    b.type = 'button';
    b.addEventListener('click', () => { el.remove(); if (onClose) onClose(); });
    return b;
  }

  function toast(message, opts) {
    const o = opts || {};
    const kind = _kind(o.kind);
    const stack = _stack();
    const t = _el('div', 'notify-toast is-' + kind);
    t.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    t.appendChild(_body(kind, String(message || ''), o.next));
    t.appendChild(_close(t));
    stack.appendChild(t);
    while (stack.childElementCount > MAX_TOASTS) stack.firstElementChild.remove();
    const ms = o.timeout === undefined ? AUTO_MS[kind] : o.timeout;
    if (ms > 0) {
      let timer = setTimeout(() => t.remove(), ms);
      // 読んでいる間は消さない。
      t.addEventListener('mouseenter', () => clearTimeout(timer));
      t.addEventListener('mouseleave', () => { timer = setTimeout(() => t.remove(), ms); });
    }
    return t;
  }

  function band(container, message, opts) {
    if (!container) return null;
    const o = opts || {};
    const kind = _kind(o.kind);
    if (o.id) clearBand(container, o.id);
    const b = _el('div', 'notify-band is-' + kind);
    if (o.id) b.dataset.bandId = o.id;
    b.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    b.appendChild(_body(kind, String(message || ''), o.next));
    if (o.dismissible) b.appendChild(_close(b));
    container.prepend(b);
    return b;
  }
  function clearBand(container, id) {
    if (!container) return;
    const sel = id ? '.notify-band[data-band-id="' + CSS.escape(id) + '"]' : '.notify-band';
    container.querySelectorAll(sel).forEach((e) => e.remove());
  }
  return { toast, band, clearBand };
})();
window.Notify = Notify;
