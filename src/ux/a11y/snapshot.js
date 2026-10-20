// WebSpec2Doc 自社 a11y スナップショット（外部スクリプト・ネットワーク不使用）。
// page.evaluate に関数式として渡す。DOM・計算済みスタイル・名前計算に必要な素材だけを
// 決定論的な JSON で返す（ルール判定と accname 計算は Python 側）。
(maxElements) => {
  const SKIP = new Set(['SCRIPT', 'STYLE', 'TEMPLATE', 'NOSCRIPT', 'LINK', 'BASE']);
  const IDREF_ATTRS = ['aria-labelledby', 'aria-describedby', 'aria-controls', 'aria-owns',
    'aria-activedescendant', 'aria-details', 'aria-flowto', 'aria-errormessage'];
  const STYLE_KEYS = ['display', 'visibility', 'opacity', 'color', 'backgroundColor',
    'backgroundImage', 'fontSize', 'fontWeight', 'position', 'overflowX', 'overflowY',
    'pointerEvents', 'textDecorationLine', 'zIndex', 'clipPath', 'transform'];
  const NATIVE_FOCUS = new Set(['BUTTON', 'SELECT', 'TEXTAREA', 'IFRAME']);

  const els = [];           // 走査順の要素
  const index = new Map();  // 要素 -> 通し番号
  let truncated = false;

  function walk(node, parentIdx) {
    for (let c = node.firstChild; c; c = c.nextSibling) {
      if (c.nodeType !== 1) continue;
      if (SKIP.has(c.tagName)) continue;
      if (els.length >= maxElements) { truncated = true; return; }
      const i = els.length;
      els.push({ el: c, p: parentIdx });
      index.set(c, i);
      walk(c, i);
      if (c.shadowRoot) walk(c.shadowRoot, i);
      if (truncated) return;
    }
  }
  const root = document.documentElement;
  if (root) { index.set(root, 0); els.push({ el: root, p: -1 }); walk(root, 0); }

  function cssPath(el) {
    const parts = [];
    for (let n = el; n && n.nodeType === 1; ) {
      const tag = n.tagName.toLowerCase();
      const rootNode = n.getRootNode();
      let idPart = '';
      if (n.id && rootNode.querySelectorAll) {
        const same = rootNode.querySelectorAll('[id="' + n.id.replace(/"/g, '\\"') + '"]').length;
        if (same === 1) { parts.unshift('#' + CSS.escape(n.id)); break; }
        idPart = '#' + CSS.escape(n.id);  // 重複 id: 識別のため tag#id + nth-of-type にする
      }
      let part = tag + idPart;
      const par = n.parentElement;
      if (par) {
        const same = Array.prototype.filter.call(par.children, (s) => s.tagName === n.tagName);
        if (same.length > 1) part += ':nth-of-type(' + (same.indexOf(n) + 1) + ')';
      }
      parts.unshift(part);
      if (tag === 'html') break;
      n = par || (n.parentNode && n.parentNode.host) || null;
    }
    return parts.join(' > ');
  }

  function pseudoText(el, which) {
    try {
      const cs = getComputedStyle(el, which);
      const c = cs.content;
      if (!c || c === 'none' || c === 'normal' || cs.display === 'none') return '';
      const m = /^"((?:[^"\\]|\\.)*)"$/.exec(c);
      return m ? m[1].replace(/\\(.)/g, '$1') : '';
    } catch (e) { return ''; }
  }

  function isNativeFocusable(el, tag) {
    if (tag === 'A' || tag === 'AREA') return el.hasAttribute('href');
    if (NATIVE_FOCUS.has(tag)) return true;
    if (tag === 'INPUT') return (el.getAttribute('type') || '').toLowerCase() !== 'hidden';
    if (tag === 'AUDIO' || tag === 'VIDEO') return el.hasAttribute('controls');
    if (tag === 'SUMMARY') {
      const par = el.parentElement;
      return !!par && par.tagName === 'DETAILS' && par.querySelector(':scope > summary') === el;
    }
    const ce = el.getAttribute('contenteditable');
    return ce !== null && ce.toLowerCase() !== 'false';
  }

  const out = els.map(({ el, p }, i) => {
    const tag = el.tagName.toLowerCase();
    const cs = getComputedStyle(el);
    const attrs = {};
    for (const a of el.attributes) attrs[a.name] = a.value;
    const kids = [];
    for (let c = el.firstChild; c; c = c.nextSibling) {
      if (c.nodeType === 3) kids.push(c.data);
      else if (c.nodeType === 1 && index.has(c)) kids.push(index.get(c));
    }
    if (el.shadowRoot) {
      for (let c = el.shadowRoot.firstChild; c; c = c.nextSibling) {
        if (c.nodeType === 3) kids.push(c.data);
        else if (c.nodeType === 1 && index.has(c)) kids.push(index.get(c));
      }
    }
    const st = {};
    for (const k of STYLE_KEYS) st[k] = cs[k];
    const r = el.getBoundingClientRect();
    const rendered = typeof el.checkVisibility === 'function' ? el.checkVisibility() : cs.display !== 'none';
    const visible = cs.visibility === 'visible';
    const tiRaw = el.getAttribute('tabindex');
    const tiNum = tiRaw !== null && /^\s*[+-]?\d+\s*$/.test(tiRaw) ? parseInt(tiRaw, 10) : null;
    const inert = !!el.closest('[inert]');
    let disabled = false;
    try { disabled = el.matches(':disabled'); } catch (e) { disabled = false; }
    const native = isNativeFocusable(el, el.tagName);
    const focusable = rendered && visible && !inert && !disabled && (native || tiNum !== null);
    const tabStop = focusable && (tiNum !== null ? tiNum >= 0 : true);
    const refs = {};
    for (const a of IDREF_ATTRS) {
      const v = el.getAttribute(a);
      if (v === null) continue;
      const scope = el.getRootNode();
      refs[a] = v.split(/\s+/).filter(Boolean).map((id) => {
        const t = scope.getElementById ? scope.getElementById(id) : null;
        return t && index.has(t) ? index.get(t) : -1;
      });
    }
    let labels = [];
    if (el.labels) labels = Array.prototype.map.call(el.labels, (l) => (index.has(l) ? index.get(l) : -1)).filter((n) => n >= 0);
    let val = null;
    if (tag === 'select') {
      val = Array.prototype.map.call(el.selectedOptions || [], (o) => o.text).join(' ');
    } else if (tag === 'input' || tag === 'textarea') {
      val = el.value;
    }
    return {
      i, p, tag, ns: el.namespaceURI === 'http://www.w3.org/2000/svg' ? 'svg' : 'html',
      attrs, sel: cssPath(el), kids, pb: pseudoText(el, '::before'), pa: pseudoText(el, '::after'),
      st, box: [Math.round(r.x + window.scrollX), Math.round(r.y + window.scrollY), Math.round(r.width), Math.round(r.height)],
      rendered, visible, focusable, tabStop, tab: tiNum, inert, disabled,
      sc: [el.scrollWidth, el.clientWidth, el.scrollHeight, el.clientHeight],
      refs, labels, val, shadow: !!el.getRootNode().host,
    };
  });

  const vp = document.querySelector('meta[name="viewport" i]');
  return {
    url: location.href,
    doc: {
      title: document.title,
      lang: root ? root.getAttribute('lang') : null,
      viewport: vp ? vp.getAttribute('content') : null,
      doctype: !!document.doctype,
      width: window.innerWidth, height: window.innerHeight,
    },
    truncated,
    elements: out,
  };
}
