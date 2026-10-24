// ====================== 共通UI状態（スケルトン・空状態・エラー） ======================
// レポートパネル等で使う描画ヘルパー。DOM API のみで構築し innerHTML を使わない。

function _uiClear(container) {
  if (!container) return null;
  container.replaceChildren();
  return container;
}

// 既定アイコン（線 SVG。partials/state.html と同じ意匠）。固定文字列のみを DOMParser で解釈する。
var _UI_ICON_PATHS = {
  empty: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  zero: '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
  loading: '<path d="M12 3a9 9 0 1 0 9 9"/>',
  error: '<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16.5v.01"/>',
  forbidden: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
};
function _uiIcon(kind) {
  const inner = _UI_ICON_PATHS[kind] || _UI_ICON_PATHS.empty;
  const src = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + inner + '</svg>';
  const doc = new DOMParser().parseFromString(src, 'image/svg+xml');
  return document.importNode(doc.documentElement, true);
}

// kind: 'table' | 'cards' | 'diagram'
function uiSkeleton(container, kind) {
  if (!_uiClear(container)) return;
  const wrap = document.createElement('div');
  if (kind === 'cards') {
    wrap.className = 'ui-skeleton-cards';
    for (let i = 0; i < 6; i++) {
      const b = document.createElement('div');
      b.className = 'ui-skeleton-block';
      wrap.appendChild(b);
    }
  } else if (kind === 'diagram') {
    wrap.className = 'ui-skeleton';
    const title = document.createElement('div');
    title.className = 'ui-skeleton-row is-wide';
    const block = document.createElement('div');
    block.className = 'ui-skeleton-block';
    wrap.append(title, block);
  } else {
    wrap.className = 'ui-skeleton';
    const title = document.createElement('div');
    title.className = 'ui-skeleton-row is-wide';
    wrap.appendChild(title);
    for (let i = 0; i < 8; i++) {
      const r = document.createElement('div');
      r.className = 'ui-skeleton-row';
      wrap.appendChild(r);
    }
  }
  wrap.setAttribute('aria-hidden', 'true');
  container.appendChild(wrap);
}

// opts: { icon, title, desc, actionLabel, onAction }
function uiEmpty(container, opts) {
  if (!_uiClear(container)) return;
  const o = opts || {};
  const wrap = document.createElement('div');
  wrap.className = 'ui-empty';

  const icon = document.createElement('div');
  icon.className = 'ui-empty-icon';
  icon.setAttribute('aria-hidden', 'true');
  if (o.icon) icon.textContent = o.icon; else icon.appendChild(_uiIcon('empty'));
  wrap.appendChild(icon);

  const title = document.createElement('p');
  title.className = 'ui-empty-title';
  title.textContent = o.title || 'データがありません';
  wrap.appendChild(title);

  if (o.desc) {
    const desc = document.createElement('p');
    desc.className = 'ui-empty-desc';
    desc.textContent = o.desc;
    wrap.appendChild(desc);
  }

  if (o.actionLabel && typeof o.onAction === 'function') {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn-primary ui-empty-action';
    btn.textContent = o.actionLabel;
    btn.addEventListener('click', o.onAction);
    wrap.appendChild(btn);
  }
  container.appendChild(wrap);
}

// opts: { title, message, onRetry }
function uiError(container, opts) {
  if (!_uiClear(container)) return;
  const o = opts || {};
  const wrap = document.createElement('div');
  wrap.className = 'ui-error';
  wrap.setAttribute('role', 'alert');

  const icon = document.createElement('div');
  icon.className = 'ui-error-icon';
  icon.setAttribute('aria-hidden', 'true');
  icon.textContent = '⚠';
  wrap.appendChild(icon);

  const title = document.createElement('p');
  title.className = 'ui-error-title';
  title.textContent = o.title || '読み込みに失敗しました';
  wrap.appendChild(title);

  if (o.message) {
    const msg = document.createElement('p');
    msg.className = 'ui-error-message';
    msg.textContent = o.message;
    wrap.appendChild(msg);
  }

  if (typeof o.onRetry === 'function') {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn-outline-sm ui-empty-action';
    btn.textContent = '再試行';
    btn.addEventListener('click', o.onRetry);
    wrap.appendChild(btn);
  }
  container.appendChild(wrap);
}

// ====================== 状態 9 種の切替（UIStates） ======================
// 契約: common-contract §2.3。本文コンテナの data-state 属性 1 つで切り替える。
//   UIStates.set(root, state, { message, next, ...操作 })
// state: normal / empty / no-match / loading / error / forbidden / dirty / conflict / restored
// 文言は textContent で入れる（HTML を解釈しない）。実装語・パスは System 側で渡さないこと。
var UIStates = (function () {
  const STATES = ['normal', 'empty', 'zero', 'no-match', 'loading', 'error', 'forbidden', 'dirty', 'conflict', 'restored'];
  // dirty / restored は本文を隠さず、上部の帯として出す。
  const BANNER_STATES = ['dirty', 'restored'];
  const DEFAULTS = {
    'empty': { title: 'まだ登録がありません', message: 'この一覧に表示できるものがありません。', next: '右上の追加から最初の 1 件を登録してください。' },
    'no-match': { title: '条件に合うものがありません', message: '絞り込みの条件に一致するものが 0 件でした。', next: '条件を解除するか、語を短くして探し直してください。', actionLabel: '条件を解除' },
    'loading': { title: '読み込み中です', message: '', next: '' },
    'error': { title: '読み込めませんでした', message: '一時的に内容を取得できませんでした。', next: '少し待ってから「もう一度読み込む」を押してください。', actionLabel: 'もう一度読み込む' },
    'forbidden': { title: 'この操作の権限がありません', message: 'いまの役割ではこの画面を操作できません。', next: '管理者に役割の付与を依頼してください。' },
    'dirty': { title: '保存していない変更があります', message: 'この画面を離れると、変更は失われます。', next: '離れる前に「保存」を押してください。' },
    'conflict': { title: 'ほかの人が先に更新しました', message: 'あなたが編集している間に、同じ内容が更新されています。', next: '最新を読み直すか、自分の変更を保持して見比べてください。' },
    'restored': { title: '前回の続きを復元しました', message: '保存前に閉じた編集内容を戻しています。', next: '内容を確かめてから保存してください。不要なら破棄できます。', actionLabel: '破棄して最初から' },
  };

  function _el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }
  function _btn(label, cls, fn) {
    const b = _el('button', cls, label);
    b.type = 'button';
    b.addEventListener('click', fn);
    return b;
  }
  // partial（templates/partials/states/*.html）を含めていれば使い、無ければ作る。
  function _pane(root, state) {
    let pane = root.querySelector(':scope > [data-pane="' + state + '"]');
    if (!pane) {
      pane = _el('section', 'ui-state-pane');
      pane.dataset.pane = state;
      if (BANNER_STATES.includes(state)) root.prepend(pane); else root.appendChild(pane);
    }
    return pane;
  }

  function _fill(pane, state, o) {
    const d = DEFAULTS[state] || {};
    pane.replaceChildren();
    const isAlert = state === 'error' || state === 'forbidden' || state === 'conflict';
    pane.setAttribute('role', isAlert ? 'alert' : 'status');
    if (state === 'loading') {
      pane.setAttribute('aria-busy', 'true');
      const sk = _el('div');
      pane.appendChild(sk);
      uiSkeleton(sk, o.kind || 'table');
      pane.appendChild(_el('p', 'ui-state-sr', o.message || d.title));
      return;
    }
    pane.appendChild(_el('p', 'ui-state-title', o.title || d.title));
    const msg = o.message || d.message;
    if (msg) pane.appendChild(_el('p', 'ui-state-message', msg));
    if (state === 'forbidden' && o.role) {
      pane.appendChild(_el('p', 'ui-state-message', '必要な役割: ' + o.role));
    }
    if (state === 'no-match' && o.conditions) {
      pane.appendChild(_el('p', 'ui-state-message', 'いまの条件: ' + o.conditions));
    }
    const next = o.next || d.next;
    if (next) pane.appendChild(_el('p', 'ui-state-next', next));
    const acts = _el('div', 'ui-state-actions');
    const label = o.actionLabel || d.actionLabel;
    if (state === 'conflict') {
      if (typeof o.onReload === 'function') acts.appendChild(_btn('最新を読み直す', 'btn-primary', o.onReload));
      if (typeof o.onKeep === 'function') acts.appendChild(_btn('自分の変更を保持', 'btn-outline-sm', o.onKeep));
    } else if (state === 'dirty') {
      if (typeof o.onSave === 'function') acts.appendChild(_btn('保存', 'btn-primary', o.onSave));
    } else if (state === 'forbidden') {
      const back = o.onAction || function () { if (history.length > 1) history.back(); else location.href = '/systems'; };
      acts.appendChild(_btn(o.actionLabel || '前の画面に戻る', 'btn-outline-sm', back));
    } else {
      const fn = o.onAction || o.onRetry || o.onClear || o.onDiscard;
      if (label && typeof fn === 'function') {
        acts.appendChild(_btn(label, state === 'error' || state === 'empty' ? 'btn-primary' : 'btn-outline-sm', fn));
      }
    }
    if (acts.childElementCount) pane.appendChild(acts);
  }

  // 新形式: opts に msg / cta があるか kind が zero のとき、.ui-state を 1 個だけ生成して置換する。
  // cta: { label, href } または { label, onClick }。loading と cta 未指定では操作を出さない。
  function _isNew(s, o) { return s === 'zero' || 'msg' in o || 'cta' in o; }
  function _renderKind(root, s, o) {
    const d = DEFAULTS[s] || {};
    root.querySelectorAll(':scope > .ui-state').forEach(function (n) { n.remove(); });
    root.querySelectorAll(':scope > [data-pane="' + s + '"]').forEach(function (n) { n.hidden = true; });
    const box = _el('section', 'ui-state');
    box.dataset.kind = s;
    box.setAttribute('role', s === 'error' || s === 'forbidden' ? 'alert' : 'status');
    box.appendChild(_uiIcon(s));
    box.appendChild(_el('h2', 'ui-state__title', o.title || d.title || ''));
    const msg = o.msg || o.message || d.message;
    if (msg) box.appendChild(_el('p', 'ui-state__msg', msg));
    const cta = o.cta;
    if (s !== 'loading' && cta && cta.label) {
      const acts = _el('div', 'ui-state__actions');
      const primary = s === 'empty' || s === 'zero' ? ' c-btn--primary' : '';
      if (cta.href) {
        const a = _el('a', 'c-btn' + primary, cta.label);
        a.href = cta.href;
        acts.appendChild(a);
      } else {
        acts.appendChild(_btn(cta.label, 'c-btn' + primary, typeof cta.onClick === 'function' ? cta.onClick : function () {}));
      }
      box.appendChild(acts);
    }
    root.appendChild(box);
  }

  function set(root, state, opts) {
    if (!root) return;
    const s = STATES.includes(state) ? state : 'normal';
    root.classList.add('ui-state-root');
    root.dataset.state = s;
    root.removeAttribute('aria-busy');
    root.querySelectorAll(':scope > .ui-state').forEach(function (n) { n.remove(); });
    if (s !== 'normal' && _isNew(s, opts || {})) {
      _renderKind(root, s, opts || {});
      if (s === 'loading') root.setAttribute('aria-busy', 'true');
    } else if (s !== 'normal') {
      const pane = _pane(root, s);
      _fill(pane, s, opts || {});
      if (s === 'loading') root.setAttribute('aria-busy', 'true');
    }
    if (s === 'dirty') _dirtyRoots.add(root); else _dirtyRoots.delete(root);
  }
  function get(root) { return (root && root.dataset.state) || 'normal'; }

  // データ到着・失敗のどちらでも loading を必ず置換する。empty / error は set の opts。
  // 戻り値: promiseFn の結果（失敗時は undefined）。空配列・null・{items:[]} は empty 扱い。
  async function run(root, promiseFn, opts) {
    const o = opts || {};
    set(root, 'loading', o.loading || {});
    let result;
    try {
      result = await promiseFn();
      const isEmpty = result == null || (Array.isArray(result) && result.length === 0) ||
        (Array.isArray(result && result.items) && result.items.length === 0);
      if (isEmpty && o.empty) set(root, o.empty.kind || 'empty', o.empty); else set(root, 'normal');
    } catch (err) {
      const e = Object.assign({}, o.error || {});
      if (!e.cta && !e.actionLabel) e.cta = { label: 'もう一度読み込む', onClick: function () { run(root, promiseFn, o); } };
      set(root, 'error', e);
      result = undefined;
    } finally {
      if (get(root) === 'loading') set(root, 'normal');
    }
    return result;
  }

  // fetch の Response（または status 数値）から失敗系の状態を選ぶ。
  function fromResponse(root, res, opts) {
    const status = typeof res === 'number' ? res : (res && res.status) || 0;
    const o = opts || {};
    if (status === 403) return set(root, 'forbidden', o.forbidden || o);
    if (status === 409) return set(root, 'conflict', o.conflict || o);
    if (status === 401) return set(root, 'forbidden', Object.assign({
      title: 'ログインの有効期限が切れました', message: '続けるには、もう一度ログインが必要です。',
      next: '画面を再読み込みしてログインし直してください。',
    }, o.unauthorized || {}));
    return set(root, 'error', o.error || o);
  }

  // ---- 未保存ガード（離脱前確認） ----
  const _dirtyRoots = new Set();
  const _checks = new Set();
  function isDirty() {
    for (const r of _dirtyRoots) if (r.isConnected) return true;
    for (const fn of _checks) { try { if (fn()) return true; } catch (_) { /* 判定失敗は未保存扱いにしない */ } }
    return false;
  }
  // isDirtyFn: System 側の変更有無判定（true で未保存）。戻り値は解除関数。
  function guard(isDirtyFn) {
    if (typeof isDirtyFn === 'function') _checks.add(isDirtyFn);
    return function () { _checks.delete(isDirtyFn); };
  }
  // 画面内リンク・案件切替の前に呼ぶ。未保存なら確認し、離れてよいときだけ true。
  function confirmLeave(message) {
    if (!isDirty()) return true;
    return window.confirm(message || '保存していない変更があります。破棄してこの画面を離れますか？');
  }
  window.addEventListener('beforeunload', function (e) {
    if (!isDirty()) return;
    e.preventDefault();
    e.returnValue = '';
  });
  document.addEventListener('click', function (e) {
    const a = e.target.closest && e.target.closest('a[href]');
    if (!a || a.target === '_blank' || a.hasAttribute('download') || a.dataset.noGuard !== undefined) return;
    if (a.getAttribute('href').startsWith('#')) return;
    if (!confirmLeave()) { e.preventDefault(); e.stopPropagation(); }
  }, true);

  return { STATES, set, run, get, fromResponse, guard, isDirty, confirmLeave };
})();
window.UIStates = UIStates;
