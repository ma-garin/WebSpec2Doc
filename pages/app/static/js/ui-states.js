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
