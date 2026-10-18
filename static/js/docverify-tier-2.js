(function () {
  'use strict';
  var R = document.querySelector('#dvtS2 .dvt-s2') || document.querySelector('.dvt-s2');
  if (!R) return;
  var $ = function (s) { return R.querySelector(s); };
  var tabsEl = $('[data-tabs]'), docEl = $('[data-doc]'), cardsEl = $('[data-cards]'),
      band = $('[data-band]'), dlg = $('[data-dlg]'), reasonEl = $('[data-reason]');
  var cur = null, openId = null, showOk = false, reportFor = null, busy = false;
  var SEV = { high: '重大', mid: '注意', low: '軽微' };
  var COL = { high: 'var(--ng,#D92D20)', mid: 'var(--wa,#B54708)', low: '#98A2B3' };
  var VERD = {
    pass: ['合格', '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>'],
    conditional: ['条件付き', '<path d="M12 3 2 20h20z"/><path d="M12 10v4m0 3v.01"/>'],
    fail: ['不合格', '<circle cx="12" cy="12" r="9"/><path d="M15 9l-6 6M9 9l6 6"/>']
  };
  var triI = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l10 18H2z"/></svg>';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function st() { return (window.DVT && window.DVT.state) || null; }
  function toast(m, k) { if (window.DVT) window.DVT.toast(m, k || 'error'); }
  function json(method, obj) {
    return { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(obj || {}) };
  }
  function userName() {
    var el = document.querySelector('[data-user-name],#userName,.user-name,.dv-user');
    var v = el && (el.value || el.textContent || '').trim();
    return v || 'ゲスト';
  }
  function dname(s, id) {
    var d = (s.documents || []).filter(function (x) { return x.id === id; })[0];
    return d ? d.name : '';
  }
  function reported(s, f) { return !!(s.reports && s.reports[f.id]); }

  function render() {
    var s = st();
    if (!s || !s.documents) return;
    var fs = s.findings || [], docs = s.documents;
    var act = fs.filter(function (f) { return !reported(s, f); });
    var cnt = { high: 0, mid: 0, low: 0 };
    act.forEach(function (f) { cnt[f.severity]++; });
    var byDoc = {};
    fs.forEach(function (f) { (byDoc[f.doc_id] = byDoc[f.doc_id] || []).push(f); });
    var actBy = {};
    act.forEach(function (f) { actBy[f.doc_id] = (actBy[f.doc_id] || 0) + 1; });
    var withF = docs.filter(function (d) { return byDoc[d.id]; });
    var without = docs.filter(function (d) { return !byDoc[d.id]; });
    if (!cur || !docs.some(function (d) { return d.id === cur; })) {
      cur = (withF[0] || docs[0] || {}).id || null;
    }

    var lvl = s.auto_level || (cnt.high ? 'fail' : act.length ? 'conditional' : 'pass');
    var v = VERD[lvl] || VERD.pass;
    band.className = 'band ' + lvl;
    $('[data-verdict]').innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' + v[1] + '</svg>' +
      esc(s.level_label || v[0]) + (act.length ? '・指摘 ' + act.length + ' 件' : '');
    $('[data-sum]').textContent = act.length
      ? '重大 ' + cnt.high + ' 件・注意 ' + cnt.mid + ' 件・軽微 ' + cnt.low + ' 件。' +
        (lvl === 'fail' ? '重大が残っているため不合格です。' : lvl === 'conditional' ? '重大はありませんが、直したい点が残っています。' : '')
      : '指摘はありません。';
    $('[data-title]').textContent = 'AI が ' + docs.length + ' 件の文書を検査しました';
    $('[data-lead]').textContent = withF.length
      ? '問題のある ' + withF.length + ' 件を右のカードで確かめてください。確認できたら「つながりとレポートへ」進みます。'
      : '問題は見つかりませんでした。「つながりとレポートへ」進めます。';

    function tab(d, ok) {
      var n = actBy[d.id] || 0, worst = 'low';
      (byDoc[d.id] || []).forEach(function (f) {
        if (!reported(s, f) && (f.severity === 'high' || (f.severity === 'mid' && worst !== 'high'))) worst = f.severity;
      });
      return '<button type="button" class="tab' + (d.id === cur ? ' on' : '') + (ok ? ' okt' : '') + '" data-d="' + esc(d.id) + '"><span>' +
        (ok ? '✓ ' : '') + esc(d.name) + '</span>' + (ok ? '' : '<em style="background:' + COL[worst] + '">' + n + '</em>') + '</button>';
    }
    var th = withF.map(function (d) { return tab(d, false); }).join('');
    if (without.length) {
      th += '<button type="button" class="more" data-more>' + (showOk ? '問題のない文書を隠す' : '問題のない文書 ' + without.length + ' 件を表示') + '</button>';
      if (showOk) th += without.map(function (d) { return tab(d, true); }).join('');
    }
    tabsEl.innerHTML = th;

    renderDoc(s, byDoc);
    var ch = '';
    fs.slice().sort(function (a, b) { return ['high', 'mid', 'low'].indexOf(a.severity) - ['high', 'mid', 'low'].indexOf(b.severity); }).forEach(function (f) {
      var rp = reported(s, f);
      ch += '<div class="card ' + esc(f.severity) + (rp ? ' rp' : '') + (f.id === openId ? ' open' : '') + '" data-f="' + esc(f.id) + '" data-d="' + esc(f.doc_id) + '">' +
        '<div class="chead"><span class="sev">' + triI + esc(SEV[f.severity] || '') + '</span><span class="rule">' + esc(f.rule_label) + '</span><span class="doclabel">' + esc(dname(s, f.doc_id)) + '</span></div>' +
        '<p class="one">' + esc(f.reason) + '</p>' +
        '<div class="detail">' + (f.related_quote ? '関連する箇所: 「' + esc(f.related_quote) + '」' + (f.related_doc_id ? '（' + esc(dname(s, f.related_doc_id)) + '）' : '') : '') +
        (f.fix ? '<div class="fix"><b>修正案</b>' + esc(f.fix) + '</div>' : '') +
        '<button type="button" class="rep" data-rep>誤検知を通報</button><span class="reported">通報済み。理由: ' + esc((s.reports[f.id] || {}).reason || '') + '</span></div></div>';
    });
    cardsEl.innerHTML = ch || '<div class="empty">指摘はありません。</div>';
  }

  function renderDoc(s, byDoc) {
    var d = (s.documents || []).filter(function (x) { return x.id === cur; })[0];
    if (!d) { docEl.innerHTML = '<p class="none">文書がありません。登録からやり直してください。</p>'; return; }
    var tn = (s.tiers || []).filter(function (t) { return t.id === d.tier; })[0];
    var h = '<h2>' + esc(d.name) + '</h2><div class="meta">' + esc(d.name) + (tn ? ' ・ ' + esc(tn.label) : '') + '</div>';
    var ps = (s.documents_text && s.documents_text[d.id]) || [];
    if (!ps.length) h += '<p class="none">本文を表示できません。登録からやり直してください。</p>';
    ps.forEach(function (p) {
      var fl = (byDoc[d.id] || []).filter(function (f) { return f.passage_id === p.id; })
        .sort(function (a, b) { return a.start - b.start; });
      var out = '', pos = 0, t = p.text || '';
      fl.forEach(function (f) {
        if (f.start < pos || f.end > t.length || f.end <= f.start) return;
        out += esc(t.slice(pos, f.start)) + '<mark class="hl s-' + esc(f.severity) + (reported(s, f) ? ' rp' : '') + (f.id === openId ? ' cur' : '') + '" data-f="' + esc(f.id) + '">' + esc(t.slice(f.start, f.end)) + '</mark>';
        pos = f.end;
      });
      out += esc(t.slice(pos));
      h += '<p>' + out + '</p>';
    });
    docEl.innerHTML = h;
  }

  function open(fid, fromCard) {
    var s = st(), f = ((s && s.findings) || []).filter(function (x) { return x.id === fid; })[0];
    if (!f) return;
    openId = fid;
    if (cur !== f.doc_id) cur = f.doc_id;
    render();
    var h = docEl.querySelector('.hl[data-f="' + fid + '"]');
    if (h) { h.scrollIntoView({ behavior: 'smooth', block: 'center' }); h.classList.add('flash'); setTimeout(function () { h.classList.remove('flash'); }, 1400); }
    var c = cardsEl.querySelector('.card[data-f="' + fid + '"]');
    if (c && !fromCard) c.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  tabsEl.addEventListener('click', function (e) {
    var t = e.target.closest('[data-d]');
    if (t) { cur = t.dataset.d; openId = null; render(); return; }
    if (e.target.closest('[data-more]')) { showOk = !showOk; render(); }
  });
  docEl.addEventListener('click', function (e) {
    var h = e.target.closest('.hl');
    if (h) { openId = h.dataset.f; render(); var c = cardsEl.querySelector('.card[data-f="' + openId + '"]'); if (c) c.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
  });
  cardsEl.addEventListener('click', function (e) {
    var c = e.target.closest('.card'); if (!c) return;
    if (e.target.closest('[data-rep]')) { reportFor = c.dataset.f; reasonEl.value = ''; dlg.hidden = false; reasonEl.focus(); return; }
    if (c.dataset.f === openId) { openId = null; render(); } else open(c.dataset.f, true);
  });

  $('[data-cancel]').addEventListener('click', function () { dlg.hidden = true; reportFor = null; });
  $('[data-send]').addEventListener('click', function () {
    var reason = reasonEl.value.trim();
    if (!reason) { toast('通報の理由を書いてください。'); reasonEl.focus(); return; }
    if (busy || !reportFor) return;
    busy = true;
    Promise.resolve(window.DVT.api('tier/findings/' + reportFor + '/report', json('POST', { reason: reason, by: userName() })))
      .then(function () { return window.DVT.refresh(); })
      .then(function () { busy = false; dlg.hidden = true; reportFor = null; toast('誤検知として通報しました。', 'ok'); },
        function (err) { busy = false; toast((err && err.message) || '通報できませんでした。少し待ってからもう一度お試しください。'); });
  });
  $('[data-to-report]').addEventListener('click', function () { window.DVT.go(3); });
  $('[data-redo]').addEventListener('click', function () {
    if (busy) return;
    busy = true;
    Promise.resolve(window.DVT.api('tier/reset', json('POST', { to: 1 })))
      .then(function () { return window.DVT.refresh(); })
      .then(function () { busy = false; openId = null; window.DVT.go(1); },
        function (err) { busy = false; toast((err && err.message) || 'やり直せませんでした。少し待ってからもう一度お試しください。'); });
  });

  document.addEventListener('dvt:state', render);
  render();
})();
