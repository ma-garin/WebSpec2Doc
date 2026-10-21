/* Document Assurance パネル: 変更（意味差分）。docassure.js からは window.DAPanels.diff 経由で呼ばれる。
   左＝変更一覧、右＝Before/After（語単位の差分）・意味差分（推定）・影響（候補）の master-detail。 */
(function () {
  'use strict';
  window.DAPanels = window.DAPanels || {};
  var CHANGE = {
    CREATED: ['＋', '新規'], MODIFIED: ['△', '変更'], REMOVED: ['－', '削除'],
    MOVED: ['↔', '位置のみ'], SPLIT: ['⑂', '分割'], MERGED: ['⑃', '統合']
  };
  var TYPE = { threshold_change: 'しきい値の変更' };
  var RISK = { high: ['大', 'dac-imp--high'], medium: ['中', 'dac-imp--mid'], low: ['小', 'dac-imp--low'] };
  var sel = null;

  /* 語単位に分ける: 英数字の連なり・漢字・ひらがな・カタカナ・空白・記号 */
  function tokens(s) { return String(s || '').match(/[A-Za-z0-9_.%]+|[一-鿿々]+|[぀-ゟ]+|[゠-ヿー]+|\s+|./g) || []; }
  function wordDiff(esc, a, b) {
    var x = tokens(a), y = tokens(b), n = x.length, m = y.length;
    if (!n || !m || n * m > 160000) { return [esc(a || ''), esc(b || '')]; }
    var L = [], i, j;
    for (i = 0; i <= n; i++) { L.push(new Array(m + 1).fill(0)); }
    for (i = n - 1; i >= 0; i--) { for (j = m - 1; j >= 0; j--) { L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]); } }
    var outA = '', outB = '';
    i = 0; j = 0;
    while (i < n && j < m) {
      if (x[i] === y[j]) { outA += esc(x[i]); outB += esc(y[j]); i++; j++; }
      else if (L[i + 1][j] >= L[i][j + 1]) { outA += '<del class="dac-del">' + esc(x[i++]) + '</del>'; }
      else { outB += '<ins class="dac-ins">' + esc(y[j++]) + '</ins>'; }
    }
    while (i < n) { outA += '<del class="dac-del">' + esc(x[i++]) + '</del>'; }
    while (j < m) { outB += '<ins class="dac-ins">' + esc(y[j++]) + '</ins>'; }
    return [outA, outB];
  }

  function hunks(a, b) {
    var x = tokens(a), y = tokens(b), n = x.length, m = y.length, out = [];
    if (!n || !m || n * m > 160000) { return out; }
    var L = [], i, j;
    for (i = 0; i <= n; i++) { L.push(new Array(m + 1).fill(0)); }
    for (i = n - 1; i >= 0; i--) { for (j = m - 1; j >= 0; j--) { L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]); } }
    i = 0; j = 0; var cur = null;
    while (i < n || j < m) {
      if (i < n && j < m && x[i] === y[j]) { if (cur) { out.push(cur); cur = null; } i++; j++; continue; }
      cur = cur || { b: '', a: '' };
      if (j >= m || (i < n && L[i + 1][j] >= L[i][j + 1])) { cur.b += x[i++]; } else { cur.a += y[j++]; }
    }
    if (cur) { out.push(cur); }
    return out.filter(function (h) { return (h.a + h.b).trim(); });
  }
  function key(d, i) { return String(d.requirement_id || '') + '#' + i; }
  function titleOf(d) {
    var t = d.topic || ((d.after || d.before || {}).text) || '';
    t = String(t).replace(/\s+/g, ' ').trim();
    return t.length > 48 ? t.slice(0, 48) + '…' : (t || '本文なし');
  }
  function badge(esc, d) {
    var c = CHANGE[d.change] || ['?', d.change || '種別未評価'];
    return '<span class="dax-tag dac-ch dac-ch--' + esc(String(d.change || '').toLowerCase()) + '">' + c[0] + ' ' + esc(c[1]) + '</span>';
  }
  function basisWord(d) {
    var n = (d.impacted_requirements || []).length;
    if (n) { return '参照 ' + n + ' 件'; }
    return d.change_type ? (TYPE[d.change_type] || d.change_type).replace(/の変更$/, '') : (CHANGE[d.change] || ['', ''])[1];
  }
  function impactList(esc, d) {
    if (d.change === 'MOVED') { return impact(esc, d); }
    return impact(esc, d) + '<span class="dax-meta dac-imp__why">' + esc(basisWord(d)) + '</span>';
  }
  function impact(esc, d) {
    if (d.change === 'MOVED') { return '<span class="dac-imp dac-imp--none">影響 なし</span>'; }
    var r = RISK[d.risk];
    return r ? '<span class="dac-imp ' + r[1] + '">影響 ' + r[0] + '</span>' : '<span class="dac-imp dac-imp--na">影響 未評価</span>';
  }

  var flt = '';
  function listHtml(esc, list) {
    var one = function (d, i) {
      var k = key(d, i);
      return '<button type="button" role="option" class="dax-item" aria-selected="' + (k === sel) + '" data-dac-k="' + esc(k) + '">' +
        '<span class="dax-item__meta"><span class="dax-item__req">' + esc(d.requirement_id || '要件 ID なし') + '</span>' + badge(esc, d) + '</span>' +
        '<span class="dax-item__title" title="' + esc(titleOf(d)) + '">' + esc(titleOf(d)) + '</span>' +
        '<span class="dax-item__meta">' + impactList(esc, d) + '</span></button>';
    };
    var main = '', moved = '', nm = 0;
    list.forEach(function (d, i) {
      if (flt && d.change !== flt) { return; }
      if (d.change === 'MOVED') { moved += one(d, i); nm++; } else { main += one(d, i); }
    });
    var selMoved = list.some(function (d, i) { return d.change === 'MOVED' && key(d, i) === sel; });
    return '<div class="dax-md__list" role="listbox" aria-label="変更の一覧">' + (main || (nm ? '' : '<p class="dax-meta dax-md__none">この種別の変更はありません。</p>')) +
      (nm ? '<details class="dac-grp"' + (selMoved || !main ? ' open' : '') + '><summary>位置のみ・影響なし（' + nm + '）</summary>' + moved + '</details>' : '') + '</div>';
  }

  function sideHtml(esc, label, ref, marked) {
    if (!ref) { return '<div class="dac-side"><p class="dac-side__h">' + label + '</p><p class="dax-meta">該当なし</p></div>'; }
    return '<div class="dac-side"><p class="dac-side__h">' + label + ' <span class="dax-meta">' + esc([ref.document_id, ref.section].filter(Boolean).join(' ')) + '</span></p>' +
      '<p class="dac-text" tabindex="0">' + marked + '</p></div>';
  }

  function meaningHtml(esc, d) {
    if (d.change === 'MOVED') { return '<p>位置が変わっただけで、要件の変更ではありません。</p>'; }
    var out = '';
    if (d.change_type) { out += '<p><strong>' + esc(TYPE[d.change_type] || d.change_type) + '</strong>' + (d.topic ? '（' + esc(d.topic) + '）' : '') + '</p>'; }
    if (d.change === 'CREATED') { out += '<p>新しく追加された要件と推定されます。</p>'; }
    if (d.change === 'REMOVED') { out += '<p>削除された要件と推定されます。対応する設計・テストが残っていないか確認してください。</p>'; }
    if (d.change === 'SPLIT') { out += '<p>次の要件に分割されたと推定されます: ' + (d.after_ids || []).map(esc).join('、') + '</p>'; }
    if (d.change === 'MERGED') { out += '<p>次の要件を統合したと推定されます: ' + (d.before_ids || []).map(esc).join('、') + '</p>'; }
    if (!out) { out = '<p class="dax-meta">意味の変化は自動では推定できませんでした。Before / After の原文を確認してください。</p>'; }
    return out;
  }

  function impactHtml(esc, d) {
    var reqs = d.impacted_requirements || [];
    var basis = d.change === 'MOVED' ? '位置のみの変更のため' : (d.risk ? '変更の種類と、この要件を参照する要件の候補 ' + reqs.length + ' 件から推定しました' : '判定の材料が無いため評価していません');
    if (d.change === 'MOVED') { basis += '推定しました'; }
    return '<p>影響 ' + esc(d.change === 'MOVED' ? 'なし' : (RISK[d.risk] || ['未評価'])[0]) + '：' + esc(basis) + '。</p>';
    var rows = '<div class="dax-props__row"><dt>根拠</dt><dd>' + esc(basis) + '推定</dd></div>' +
      '<div class="dax-props__row"><dt>要件の候補</dt><dd>' + (reqs.length ? reqs.map(function (r) { return '<span class="dax-tag">' + esc(r) + '</span>'; }).join(' ') : '<span class="dax-meta">候補なし（影響なしの証明ではありません）</span>') + '</dd></div>';
    return '<dl class="dax-props dax-props--one">' + rows + '</dl>';
  }

  function detailHtml(esc, d) {
    var md = wordDiff(esc, (d.before || {}).text, (d.after || {}).text);
    var n = (d.impacted_requirements || []).length;
    var head = '<header class="dax-md__head dac-head"><div class="dac-head__l"><div class="dax-md__hmeta">' + badge(esc, d) + impact(esc, d) + '<span class="dax-item__req">' + esc(d.requirement_id || '') + '</span></div>' +
      '<h2 class="dax-dh__title">' + esc(titleOf(d)) + '</h2>' + '<p class="dac-cand"><span class="dax-meta">影響の候補</span> ' + (n ? d.impacted_requirements.map(function (r) { return '<span class="dax-tag">' + esc(r) + '</span>'; }).join(' ') : '<span class="dax-meta">なし（影響なしの証明ではありません）</span>') + '</p>' + '</div>' +
      '<div class="dac-cta-w"><button type="button" class="dax-btn dax-btn--primary dac-cta" data-tab-go="trace">影響を確認（要件 ' + n + ' 件）</button><span class="dax-meta dac-cta__hint">トレーサビリティで影響範囲を開きます</span></div>' + '</header>';
    var ba = '<section class="dax-detail__section" aria-label="原文の差分"><h3 class="dax-h3">原文の差分（Before / After）</h3><div class="dac-ba">' +
      sideHtml(esc, 'Before（前の版）', d.before, md[0]) + sideHtml(esc, 'After（今の版）', d.after, md[1]) + '</div>' +
      '<p class="dax-meta dac-legend"><del class="dac-del">削除</del> <ins class="dac-ins">追加</ins> を語単位で示します。</p></section>';
    var body = '<div class="dax-md__body">' + ba +
      '<section class="dac-est" aria-label="意味差分と影響（推定）"><h3 class="dax-h3">推定：意味差分と影響</h3>' + meaningHtml(esc, d) + impactHtml(esc, d) +
      '</section></div>';
    return head + body;
  }

  function versionsText() {
    var vs = ((window.DV && DV.state && DV.state.review && DV.state.review.versions) || []).map(function (v) { return v && typeof v === 'object' ? (v.version != null ? v.version : v.no) : v; }).filter(function (v) { return v != null && v !== ''; });
    return vs.length ? '版 ' + vs.reduce(function (a, b) { return Number(b) > Number(a) ? b : a; }) : '今の版';
  }
  var VER = null;
  function verPair() { return VER && VER[0] != null && VER[1] != null ? '第' + VER[0] + '版 → 第' + VER[1] + '版' : '前の版 → ' + curLabel() + '（版番号は未提供）'; }
  function curLabel() { var v = versionsText(); return v === '今の版' ? v : '今の版（' + v + '）'; }
  function curVer() {
    var v = versionsText(); if (v !== '今の版') { return '第' + v.replace('版 ', '') + '版'; }
    var rv = (window.DV && DV.state && DV.state.review) || {}, t = String(rv.title || rv.name || '') + ' ' + ((document.getElementById('topbar-breadcrumb') || {}).textContent || '');
    var m = t.match(/第\s*(\d+)\s*版/); return m ? '第' + m[1] + '版' : '';
  }
  function verState() { var c = curVer(); return '前の版: なし' + (c ? '\n今の版: ' + c : ''); }
  function emptyHtml(esc, title, why) {
    return '<section class="dax-state dac-empty" role="status"><span class="dac-empty__icon" aria-hidden="true"><svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M7 4h7l4 4v12H7z"/><path d="M14 4v4h4M10 13h5M12.5 10.5v5"/></svg></span><h2 class="dax-h2 dac-empty__title">' + esc(title) + '</h2>' +
      '<p class="dax-state__body dac-empty__msg">' + esc(why) + '</p><p class="dax-meta dac-empty__ver">' + esc(verState()) + '</p>' +
      '</section>';
  }

  function draw(box, ctx, list) {
    var esc = ctx.esc;
    if (!list.some(function (d, i) { return key(d, i) === sel; })) { sel = list.length ? key(list[0], 0) : null; }
    var moved = list.filter(function (d) { return d.change === 'MOVED'; }).length;
    var cur = list.filter(function (d, i) { return key(d, i) === sel; })[0];
    var c = function (k) { return list.filter(function (d) { return d.change === k; }).length; };
    var chips = [['', 'すべて', list.length]].concat([['MODIFIED', '変更'], ['CREATED', '新規'], ['REMOVED', '削除'], ['SPLIT', '分割'], ['MERGED', '統合'], ['MOVED', '位置のみ']].filter(function (p) { return c(p[0]); }).map(function (p) { return [p[0], p[1], c(p[0])]; }));
    var chipsH = '<div class="dac-chips" role="group" aria-label="種別で絞り込む">' + chips.map(function (p) {
      return '<button type="button" class="dac-chip" aria-pressed="' + (flt === p[0]) + '" data-dac-f="' + p[0] + '">' + esc(p[1]) + ' <span class="dac-chip__n">' + p[2] + '</span></button>'; }).join('') + '</div>';
    box.innerHTML = '<h2 class="dax-h2 dac-summary">' + esc(verPair()) + '</h2>' +
      '<div class="dax-md"><div class="dax-md__left">' + chipsH + listHtml(esc, list) + '</div><div class="dax-md__detail" aria-live="polite">' + detailHtml(esc, cur) + '</div></div>';
  }

  window.DAPanels.diff = {
    label: '変更',
    _draw: draw,
    html: function () {
      return '<div class="dac" data-dap-diff aria-live="polite"><p class="dax-meta">読み込み中…</p></div>';
    },
    bind: function (root, ctx) {
      var box = root.querySelector('[data-dap-diff]');
      if (!box) { return; }
      var list = [];
      box.addEventListener('click', function (e) {
        var fb = e.target.closest && e.target.closest('[data-dac-f]');
        if (fb) { flt = fb.getAttribute('data-dac-f'); draw(box, ctx, list); return; }
        var b = e.target.closest && e.target.closest('[data-dac-k]');
        if (!b) { return; }
        sel = b.getAttribute('data-dac-k'); draw(box, ctx, list);
        var f = box.querySelector('.dax-item[aria-selected="true"]'); if (f) { f.focus(); }
      });
      box.addEventListener('keydown', function (e) {
        if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') { return; }
        var b = e.target.closest && e.target.closest('[data-dac-k]'); if (!b) { return; }
        var n = e.key === 'ArrowDown' ? b.nextElementSibling : b.previousElementSibling;
        if (n) { e.preventDefault(); n.click(); }
      });
      ctx.get('diff').then(function (r) {
        if (r.status === 404 && r.body && r.body.code === 'no_previous') {
          var dx = root.closest('.dax'), hm = dx && dx.querySelector('.dax-header__meta');
          if (hm) { hm.textContent = curVer() ? curVer() + '（比較できる前の版なし）' : '比較できる前の版なし'; }
          box.innerHTML = emptyHtml(ctx.esc, '比較できる前の版がありません', (curVer() ? 'この文書は' + curVer().replace(/第(\d+)版/, '第 $1 版') + 'のみ保存されています。' : '保存されている版は 1 つだけです。') + '文書を更新して再解析すると、前の版との差分が出ます。'); return; }
        if (!r.ok) {
          box.innerHTML = '<section class="dax-state dax-state--error" role="alert"><p class="dax-state__title">差分を取得できませんでした</p><p class="dax-state__body">' +
            ctx.esc((r.body && r.body.error) || '時間をおいて再度お試しください。') + '</p><button type="button" class="dax-btn" data-tab-go="diff">再読み込み</button></section>';
          return;
        }
        var b = r.body || {};
        VER = [b.base_version != null ? b.base_version : b.previous_version, b.version != null ? b.version : b.current_version];
        list = b.diff || [];
        if (!list.length) { box.innerHTML = emptyHtml(ctx.esc, '前の版との違いはありません', '要件の追加・変更・削除は見つかりませんでした（違いが無いことの証明ではありません）。'); return; }
        draw(box, ctx, list);
      }).catch(function () {
        box.innerHTML = '<section class="dax-state dax-state--error" role="alert"><p class="dax-state__title">通信に失敗しました</p><p class="dax-state__body">接続を確認して再度お試しください。</p><button type="button" class="dax-btn" data-tab-go="diff">再読み込み</button></section>';
      });
    }
  };
})();
