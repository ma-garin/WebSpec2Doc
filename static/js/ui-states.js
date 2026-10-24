// ====================== 共通UI状態（スケルトン・空状態・エラー） ======================
// レポートパネル等で使う描画ヘルパー。DOM API のみで構築し innerHTML を使わない。

function _uiClear(container) {
  if (!container) return null;
  container.replaceChildren();
  return container;
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
  icon.textContent = o.icon || '📄';
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
const UIStates = (function () {
  const STATES = ['normal', 'empty', 'no-match', 'loading', 'error', 'forbidden', 'dirty', 'conflict', 'restored'];
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
    } else {
      const fn = o.onAction || o.onRetry || o.onClear || o.onDiscard;
      if (label && typeof fn === 'function') {
        acts.appendChild(_btn(label, state === 'error' || state === 'empty' ? 'btn-primary' : 'btn-outline-sm', fn));
      }
    }
    if (acts.childElementCount) pane.appendChild(acts);
  }

  function set(root, state, opts) {
    if (!root) return;
    const s = STATES.includes(state) ? state : 'normal';
    root.classList.add('ui-state-root');
    root.dataset.state = s;
    root.removeAttribute('aria-busy');
    if (s !== 'normal') {
      const pane = _pane(root, s);
      _fill(pane, s, opts || {});
      if (s === 'loading') root.setAttribute('aria-busy', 'true');
    }
    if (s === 'dirty') _dirtyRoots.add(root); else _dirtyRoots.delete(root);
  }
  function get(root) { return (root && root.dataset.state) || 'normal'; }

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

  return { STATES, set, get, fromResponse, guard, isDirty, confirmLeave };
})();
window.UIStates = UIStates;
