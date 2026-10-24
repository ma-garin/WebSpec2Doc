// System 01: 結果パネルの「対象と版」判定帯。#r-domain が変わったら /api/s01/versions を引いて描く。
// 判定語は共通語彙（合格／不合格／判定不能／未判定）。状態は data-state（loading / normal / empty / error）。
(function () {
  'use strict';
  var root = document.getElementById('s01-versions');
  var domainEl = document.getElementById('r-domain');
  if (!root || !domainEl) return;
  var lastDomain = '';

  function el(tag, text, attrs) {
    var n = document.createElement(tag);
    if (text != null) n.textContent = String(text);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    return n;
  }
  function setState(state, message) {
    root.setAttribute('data-state', state);
    root.querySelector('.s01-versions__error').textContent = message || '';
  }
  function verdictRow(id, label, v) {
    var row = document.getElementById(id);
    row.replaceChildren();
    row.setAttribute('data-result', v.result);
    row.append(el('strong', label), el('span', v.result, { class: 's01-verdict__result' }));
    var ul = el('ul');
    (v.named || []).forEach(function (t) { ul.append(el('li', t)); });
    row.append(ul);
  }
  function render(data) {
    document.getElementById('s01-target').textContent = '対象: ' + (data.target || '不明');
    var sel = document.getElementById('s01-version-select');
    sel.replaceChildren();
    (data.versions || []).forEach(function (v, i) {
      sel.append(el('option', v.label + '（' + v.screens + ' 画面）' + (i === 0 ? '・最新' : ''), { value: v.id }));
    });
    // 版の切替で判定帯を再計算する API は未提供のため、一覧表示に留めて操作させない。
    sel.disabled = true;
    document.getElementById('s01-version-note').textContent = data.previous_version
      ? '今回の変更分は、1 つ前の版との比較です。' : '前回の版がないため、差分はまだ出ません。';
    verdictRow('s01-verdict-overall', '全体', data.verdict.overall);
    verdictRow('s01-verdict-change', '今回の変更分', data.verdict.change);
    var body = document.getElementById('s01-prov-body');
    body.replaceChildren();
    (data.provenance || []).forEach(function (p) {
      var tr = el('tr');
      var tag = el('td'); tag.append(el('span', p.basis, { class: 's01-tag', 'data-basis': p.basis }));
      tr.append(el('td', p.artifact), tag, el('td', p.count == null ? '—' : p.count), el('td', p.note));
      body.append(tr);
    });
    var fl = document.getElementById('s01-failures');
    fl.replaceChildren();
    (data.failures || []).forEach(function (f) {
      fl.append(el('li', (f.url ? f.url + ': ' : '') + f.message + ' 次の行動: ' + f.next_action));
    });
    if (data.state === 'error') {
      setState('error', (data.failures || []).map(function (f) { return f.message + '\n' + f.next_action; }).join('\n'));
    } else {
      setState('normal');
    }
  }
  function load(domain) {
    setState('loading');
    document.getElementById('s01-target').textContent = '';
    document.getElementById('s01-version-select').replaceChildren();
    document.getElementById('s01-version-note').textContent = '';
    fetch('/api/s01/versions?domain=' + encodeURIComponent(domain), { headers: { Accept: 'application/json' } })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) { setState('error', res.body.error || '版の情報を読み込めませんでした。再読み込みしてください。'); return; }
        render(res.body);
      })
      .catch(function () { setState('error', '版の情報を読み込めませんでした。通信を確かめてから再読み込みしてください。'); });
  }
  function check() {
    var d = (domainEl.textContent || '').trim();
    if (!d || d === '-' || d === lastDomain) return;
    lastDomain = d;
    load(d);
  }
  new MutationObserver(check).observe(domainEl, { childList: true, characterData: true, subtree: true });
  check();
  window.s01Versions = { reload: function () { lastDomain = ''; check(); }, setState: setState };
})();
