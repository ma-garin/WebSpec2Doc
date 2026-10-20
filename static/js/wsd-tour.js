// 自前の操作ツアー部品（外部ライブラリなし）。
//   const tour = WsdTour.create({ steps, labels, onDestroyed, onPopoverRender });
//   tour.drive() / tour.destroy() / tour.isActive()
// steps: [{element: '#selector', popover: {title, description, side, align}}]
// labels: {next, prev, done, close, progress: '{{current}} / {{total}}'}
// onPopoverRender(popover, {tour}) : popover = {wrapper, title, description, progressText,
//   footerButtons, closeButton, nextButton, prevButton}
(function (root) {
  'use strict';

  var GAP = 12;
  var EDGE = 8;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  // 吹き出しの位置（対象 rect・吹き出しサイズ・画面サイズ）。画面内に収める。
  function place(rect, pw, ph, vw, vh, side, align) {
    var left, top;
    if (side === 'left' || side === 'right') {
      left = side === 'right' ? rect.right + GAP : rect.left - GAP - pw;
      top = align === 'start' ? rect.top : align === 'end' ? rect.bottom - ph : rect.top + rect.height / 2 - ph / 2;
    } else {
      top = side === 'top' ? rect.top - GAP - ph : rect.bottom + GAP;
      left = align === 'start' ? rect.left : align === 'end' ? rect.right - pw : rect.left + rect.width / 2 - pw / 2;
    }
    return {
      left: clamp(left, EDGE, Math.max(EDGE, vw - pw - EDGE)),
      top: clamp(top, EDGE, Math.max(EDGE, vh - ph - EDGE)),
    };
  }

  function create(config) {
    var steps = (config && config.steps) || [];
    var labels = Object.assign({ next: '次へ', prev: '戻る', done: '完了', close: '閉じる', progress: '{{current}} / {{total}}' }, config && config.labels);
    var index = 0;
    var active = false;
    var nodes = null;
    var lastFocus = null;
    var reduceMotion = false;
    try { reduceMotion = !!(root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches); } catch (e) { /* 既定 */ }

    function targetOf(step) {
      try { return step.element ? document.querySelector(step.element) : null; } catch (e) { return null; }
    }

    function build() {
      var backdrop = el('div', 'wsd-tour-backdrop');
      var spot = el('div', 'wsd-tour-spot');
      spot.setAttribute('aria-hidden', 'true');
      var wrapper = el('div', 'wsd-tour-popover');
      wrapper.setAttribute('role', 'dialog');
      wrapper.setAttribute('aria-modal', 'false');
      wrapper.setAttribute('aria-label', '操作ツアー');
      var title = el('div', 'wsd-tour-title');
      title.setAttribute('role', 'presentation');
      var description = el('div', 'wsd-tour-description');
      var footer = el('div', 'wsd-tour-footer');
      var progressText = el('span', 'wsd-tour-progress');
      var buttons = el('div', 'wsd-tour-buttons');
      var prevButton = el('button', 'wsd-tour-prev', labels.prev);
      var nextButton = el('button', 'wsd-tour-next', labels.next);
      prevButton.type = 'button';
      nextButton.type = 'button';
      var closeButton = el('button', 'wsd-tour-close', '×');
      closeButton.type = 'button';
      closeButton.setAttribute('aria-label', labels.close);
      buttons.appendChild(prevButton);
      buttons.appendChild(nextButton);
      footer.appendChild(progressText);
      footer.appendChild(buttons);
      wrapper.appendChild(closeButton);
      wrapper.appendChild(title);
      wrapper.appendChild(description);
      wrapper.appendChild(footer);
      document.body.appendChild(backdrop);
      document.body.appendChild(spot);
      document.body.appendChild(wrapper);
      backdrop.addEventListener('click', destroy);
      closeButton.addEventListener('click', destroy);
      prevButton.addEventListener('click', function () { go(index - 1); });
      nextButton.addEventListener('click', function () { if (index >= steps.length - 1) destroy(); else go(index + 1); });
      return {
        backdrop: backdrop, spot: spot, wrapper: wrapper, title: title, description: description,
        progressText: progressText, footerButtons: buttons, closeButton: closeButton,
        nextButton: nextButton, prevButton: prevButton,
      };
    }

    function reposition() {
      if (!active || !nodes) return;
      var step = steps[index];
      var target = step && targetOf(step);
      var pop = (step && step.popover) || {};
      var vw = root.innerWidth || document.documentElement.clientWidth;
      var vh = root.innerHeight || document.documentElement.clientHeight;
      var rect;
      if (target) {
        var r = target.getBoundingClientRect();
        rect = { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height };
        var pad = 6;
        nodes.spot.style.display = 'block';
        nodes.spot.style.left = (rect.left - pad) + 'px';
        nodes.spot.style.top = (rect.top - pad) + 'px';
        nodes.spot.style.width = (rect.width + pad * 2) + 'px';
        nodes.spot.style.height = (rect.height + pad * 2) + 'px';
      } else {
        // 対象が無いステップは画面中央に吹き出しだけ出す
        nodes.spot.style.display = 'none';
        rect = { left: vw / 2, top: vh / 2, right: vw / 2, bottom: vh / 2, width: 0, height: 0 };
      }
      var pw = nodes.wrapper.offsetWidth, ph = nodes.wrapper.offsetHeight;
      var pos = target
        ? place(rect, pw, ph, vw, vh, pop.side || 'bottom', pop.align || 'center')
        : { left: Math.max(EDGE, (vw - pw) / 2), top: Math.max(EDGE, (vh - ph) / 2) };
      nodes.wrapper.style.left = pos.left + 'px';
      nodes.wrapper.style.top = pos.top + 'px';
    }

    function render() {
      var step = steps[index];
      var pop = (step && step.popover) || {};
      nodes.title.textContent = pop.title || '';
      nodes.description.textContent = pop.description || '';
      nodes.progressText.textContent = labels.progress
        .replace('{{current}}', String(index + 1)).replace('{{total}}', String(steps.length));
      nodes.prevButton.style.visibility = index === 0 ? 'hidden' : 'visible';
      nodes.nextButton.textContent = index >= steps.length - 1 ? labels.done : labels.next;
      var target = targetOf(step);
      if (target && target.scrollIntoView) {
        target.scrollIntoView({ block: 'center', inline: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth' });
      }
      nodes.wrapper.classList.toggle('is-animated', !reduceMotion);
      reposition();
      if (typeof config.onPopoverRender === 'function') {
        config.onPopoverRender(nodes, { tour: api });
      }
      nodes.nextButton.focus({ preventScroll: true });
      // smooth スクロール完了後に再配置
      if (!reduceMotion) root.setTimeout(reposition, 320);
    }

    function go(next) {
      if (!active) return;
      index = clamp(next, 0, steps.length - 1);
      render();
    }

    function onKey(event) {
      if (!active) return;
      if (event.key === 'Escape') { event.preventDefault(); destroy(); }
      else if (event.key === 'ArrowRight') { event.preventDefault(); if (index >= steps.length - 1) destroy(); else go(index + 1); }
      else if (event.key === 'ArrowLeft') { event.preventDefault(); go(index - 1); }
    }

    function drive(start) {
      if (active || !steps.length) return;
      active = true;
      index = clamp(start || 0, 0, steps.length - 1);
      lastFocus = document.activeElement;
      nodes = build();
      document.addEventListener('keydown', onKey, true);
      root.addEventListener('resize', reposition);
      root.addEventListener('scroll', reposition, true);
      render();
    }

    function destroy() {
      if (!active) return;
      active = false;
      document.removeEventListener('keydown', onKey, true);
      root.removeEventListener('resize', reposition);
      root.removeEventListener('scroll', reposition, true);
      ['backdrop', 'spot', 'wrapper'].forEach(function (k) {
        if (nodes[k] && nodes[k].parentNode) nodes[k].parentNode.removeChild(nodes[k]);
      });
      nodes = null;
      if (lastFocus && lastFocus.focus) { try { lastFocus.focus({ preventScroll: true }); } catch (e) { /* 無視 */ } }
      if (typeof config.onDestroyed === 'function') config.onDestroyed();
    }

    var api = { drive: drive, destroy: destroy, isActive: function () { return active; }, next: function () { go(index + 1); }, prev: function () { go(index - 1); } };
    return api;
  }

  var lib = { create: create, _place: place };
  root.WsdTour = lib;
  if (typeof module !== 'undefined' && module.exports) module.exports = lib;
})(typeof window !== 'undefined' ? window : globalThis);
