(function () {
  'use strict';
  var R = document.querySelector('#dvtS2 .dvt-s2') || document.querySelector('.dvt-s2');
  if (!R) return;
  var SEV = { high: '重大', mid: '注意', low: '軽微' };
  var SCL = { high: 'h', mid: 'm', low: 'l' };
  var ORDER = ['high', 'mid', 'low'];
  var VERD = {
    pass: ['合格', '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>'],
    conditional: ['条件付き', '<path d="M12 3 2 20h20z"/><path d="M12 10v4m0 3v.01"/>'],
    fail: ['不合格', '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/>']
  };
  var ICO = {
    chk: '<svg viewBox="0 0 24 24"><path d="M5 12l5 5 9-9"/></svg>',
    flag: '<svg viewBox="0 0 24 24"><path d="M5 21V4M5 4h11l-2 4 2 4H5"/></svg>',
    eye: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/></svg>'
  };
  var curId = null, flt = 'all', ext = {}, reportFor = null, busy = false, shown = false;

  // 殻はテンプレートに頼らず、ここで丸ごと組み立てる
  R.innerHTML =
    '<div class="s2box" tabindex="-1">' +
      '<div class="s2top">' +
        '<span class="s2verdict" data-verdict></span>' +
        '<div class="s2prog"><b data-count></b><div class="s2bar"><i data-bar></i></div><span class="s2sub" data-why></span></div>' +
        '<button type="button" class="s2btn" data-redo>登録からやり直す</button>' +
        '<button type="button" class="s2btn pri" data-to-report>つながりとレポートへ →</button>' +
      '</div>' +
      '<div class="s2main">' +
        '<div class="s2list"><div class="s2chips" data-chips></div><div class="s2items" data-items></div></div>' +
        '<div class="s2detail"><div class="s2dh" data-dh></div><div class="s2doc" data-doc></div></div>' +
      '</div>' +
    '</div>' +
    '<div class="s2dlg" data-dlg hidden>' +
      '<div class="s2card" role="dialog" aria-label="誤検知を通報">' +
        '<h4>誤検知として通報する</h4>' +
        '<p class="s2sub" data-dlgt></p>' +
        '<textarea rows="3" data-reason placeholder="なぜ誤検知だと思うか、理由を書いてください"></textarea>' +
        '<p class="s2err" data-err role="alert">通報の理由を書いてください。</p>' +
        '<div class="s2row"><button type="button" class="s2btn" data-cancel>やめる</button><button type="button" class="s2btn pri ready" data-send>通報する</button></div>' +
      '</div>' +
    '</div>';
  var $ = function (s) { return R.querySelector(s); };
  var itemsEl = $('[data-items]'), docEl = $('[data-doc]'), dhEl = $('[data-dh]'),
      dlg = $('[data-dlg]'), errEl = $('[data-err]'), reasonEl = $('[data-reason]');

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

  function ckKey() { return 'dvt-checked:' + (window.DVT && window.DVT.iid); }
  function loadChecked() {
    try { var a = JSON.parse(sessionStorage.getItem(ckKey()) || '[]'); return Array.isArray(a) ? a : []; } catch (e) { return []; }
  }
  function saveChecked(a) { try { sessionStorage.setItem(ckKey(), JSON.stringify(a)); } catch (e) { /* 保存できなくても動く */ } }
  // 0 未確認 / 1 確認済み / 2 通報済み
  function status(s, f, ck) { return reported(s, f) ? 2 : (ck.indexOf(f.id) >= 0 ? 1 : 0); }
  var STN = ['未確認', '確認済み', '通報済み'];

  function toTop() {
    for (var n = R; n; n = n.parentElement) { if (n.scrollTop) n.scrollTop = 0; }
    var se = document.scrollingElement; if (se && se.scrollTop) se.scrollTop = 0;
  }
  function syncShown() {
    var now = R.getClientRects().length > 0;
    if (now && !shown) toTop();
    shown = now;
  }
  // 親ページを動かさず、入れ物の中だけをスクロールする
  function scrollInto(box, el, center) {
    if (!box || !el) return;
    var b = box.getBoundingClientRect(), e = el.getBoundingClientRect();
    if (center) box.scrollTop += (e.top - b.top) - (b.height - e.height) / 2;
    else if (e.top < b.top) box.scrollTop += e.top - b.top;
    else if (e.bottom > b.bottom) box.scrollTop += e.bottom - b.bottom;
  }

  function sortedAll(fs) {
    return fs.slice().sort(function (a, b) { return ORDER.indexOf(a.severity) - ORDER.indexOf(b.severity); });
  }
  function visible(fs) {
    return sortedAll(fs).filter(function (f) { return flt === 'all' || f.severity === flt; });
  }

  function drawTop(s, fs, ck) {
    var act = fs.filter(function (f) { return !reported(s, f); });
    var cnt = { high: 0, mid: 0, low: 0 };
    act.forEach(function (f) { if (cnt[f.severity] != null) cnt[f.severity]++; });
    var lvl = s.auto_level || (cnt.high ? 'fail' : act.length ? 'conditional' : 'pass');
    var v = VERD[lvl] || VERD.pass;
    var vb = $('[data-verdict]');
    vb.className = 's2verdict ' + lvl;
    vb.innerHTML = '<svg viewBox="0 0 24 24">' + v[1] + '</svg>' + esc(s.level_label || v[0]) + '・指摘 ' + act.length + ' 件';
    var total = fs.length, n = fs.filter(function (f) { return status(s, f, ck) > 0; }).length;
    var all = n >= total;
    $('[data-count]').textContent = total ? '確認済み ' + n + ' / ' + total : '規則で見つかる指摘はありません（見落としもあり得ます）';
    $('[data-bar]').style.width = (total ? n / total * 100 : 100) + '%';
    $('[data-why]').textContent = !total ? '' : all ? 'すべて確認しました。次へ進めます'
      : 'あと ' + (total - n) + ' 件' + (lvl === 'fail' ? '・重大が残っています' : '');
    $('[data-to-report]').classList.toggle('ready', all);
  }

  function drawChips(fs) {
    var d = [['all', 'すべて', fs.length]].concat(ORDER.map(function (k) {
      return [k, SEV[k], fs.filter(function (f) { return f.severity === k; }).length];
    }));
    $('[data-chips]').innerHTML = d.map(function (c) {
      return '<button type="button" class="s2chip" data-flt="' + c[0] + '" aria-pressed="' + (flt === c[0]) + '">' + c[1] + ' ' + c[2] + '</button>';
    }).join('');
  }

  function drawList(s, fs, ck) {
    var keep = itemsEl.scrollTop, h = '', last = '';
    if (!fs.length) {
      itemsEl.innerHTML = '<div class="s2gone">指摘はありません</div>';
      return;
    }
    visible(fs).forEach(function (f) {
      if (f.severity !== last) { last = f.severity; h += '<div class="s2grp">' + esc(SEV[f.severity] || '') + '</div>'; }
      var k = status(s, f, ck);
      h += '<button type="button" class="s2it' + (f.id === curId ? ' on' : '') + (k ? ' done' : '') + '" data-id="' + esc(f.id) + '">' +
        '<div class="r1"><span class="sv ' + SCL[f.severity] + '">' + esc(SEV[f.severity] || '') + '</span><span class="vw">' + esc(f.rule_label) + '</span><span class="st s' + k + '">' + STN[k] + '</span></div>' +
        '<div class="sm">' + esc(f.reason) + '</div>' +
        '<div class="r1 dn">' + esc(dname(s, f.doc_id)) + '</div></button>';
    });
    itemsEl.innerHTML = h || '<div class="s2gone">この重大度の指摘はありません</div>';
    itemsEl.scrollTop = keep;
  }

  function lineHtml(p, i, hit, f) {
    var t = p.text || '';
    var mh = /^(#{1,6})\s+/.exec(t), ml = mh ? null : /^[-*]\s+/.exec(t);
    var pos = mh ? mh[0].length : (ml ? ml[0].length : 0), out;
    if (hit && f && f.start >= pos && f.end <= t.length && f.end > f.start) {
      out = esc(t.slice(pos, f.start)) + '<mark data-m>' + esc(t.slice(f.start, f.end)) + '</mark>' + esc(t.slice(f.end));
    } else out = esc(t.slice(pos));
    return '<div class="ln' + (hit ? ' hit' : '') + (mh ? ' hd' : '') + '"><span class="n">' + (i + 1) + '</span><span class="tx">' + (ml ? '・' : '') + out + '</span></div>';
  }

  function drawDetail(s, fs, ck) {
    var f = fs.filter(function (x) { return x.id === curId; })[0];
    if (!fs.length) {
      dhEl.innerHTML = '<h3>規則で見つかる指摘はありません</h3><p>規則には見落としがあり、指摘が 0 件でも問題が無いとは言えません。人が文書を読んで確かめてください。「つながりとレポートへ」進めます。</p>';
      var h0 = '<div class="fn">登録した文書</div>';
      var tiers = s.tiers || [];
      (s.documents || []).forEach(function (d) {
        var tn = tiers.filter(function (t) { return t.id === d.tier; })[0];
        h0 += '<div class="ln"><span class="tx">' + esc(d.name) + (tn ? '（' + esc(tn.label) + '）' : '') + '</span></div>';
      });
      docEl.innerHTML = h0;
      return;
    }
    if (!f) { dhEl.innerHTML = '<p>この重大度の指摘はありません。</p>'; docEl.innerHTML = ''; return; }
    var v = visible(fs), pos = v.indexOf(f) + 1, k = status(s, f, ck), isChk = ck.indexOf(f.id) >= 0;
    dhEl.innerHTML =
      '<div class="r1"><span class="sv ' + SCL[f.severity] + '">' + esc(SEV[f.severity] || '') + '</span><span class="s2sub">確認観点：' + esc(f.rule_label) + '</span><span class="s2sub rt">' + pos + ' / ' + v.length + '</span></div>' +
      '<h3>' + esc(f.reason) + '</h3>' +
      (f.related_quote ? '<p>関連する箇所: 「' + esc(f.related_quote) + '」' + (f.related_doc_id ? '（' + esc(dname(s, f.related_doc_id)) + '）' : '') + '</p>' : '') +
      (f.fix ? '<div class="fix"><b>直し方：</b>' + esc(f.fix) + '</div>' : '') +
      '<p class="s2sub">確信度：' + (f.confidence != null ? esc(Math.round(f.confidence * 100) + '%') : '未測定（規則による検出。この規則の精度はまだ評価セットで測っていません）') + '</p>' +
      (k === 2 ? '<p class="rpd">通報済み。理由: ' + esc((s.reports[f.id] || {}).reason || '') + '</p>' : '') +
      '<div class="acts"><button type="button" class="s2btn nav" data-a="prev">↑ 前の指摘 <kbd>K</kbd></button><button type="button" class="s2btn nav" data-a="next">次の指摘 ↓ <kbd>J</kbd></button><span class="gap"></span>' +
      '<button type="button" class="s2btn" data-a="see">' + ICO.eye + '該当箇所を見る</button>' +
      (k === 2 ? '' : '<button type="button" class="s2btn" data-a="rep">' + ICO.flag + '誤検知を通報</button>' +
        '<button type="button" class="s2btn pri' + (isChk ? '' : ' ready') + '" data-a="ok">' + ICO.chk + (isChk ? '確認済みを取り消す' : '確認済みにする') + '</button>') +
      '</div>';

    var d = (s.documents || []).filter(function (x) { return x.id === f.doc_id; })[0];
    var tn = d && (s.tiers || []).filter(function (t) { return t.id === d.tier; })[0];
    var ps = (s.documents_text && s.documents_text[f.doc_id]) || [];
    var h = '<div class="fn">' + esc(d ? d.name : '') + (tn ? '（' + esc(tn.label) + '）' : '') + '</div>';
    if (!ps.length) { docEl.innerHTML = h + '<div class="s2gone">本文を表示できません。登録からやり直してください。</div>'; return; }
    var hi = 0;
    ps.forEach(function (p, i) { if (p.id === f.passage_id) hi = i; });
    var full = !!ext[f.id], a = full ? 0 : Math.max(0, hi - 2), b = full ? ps.length : Math.min(ps.length, hi + 3);
    if (a > 0) h += '<button type="button" class="more" data-a="full">上の ' + a + ' 行を表示</button>';
    for (var i = a; i < b; i++) h += lineHtml(ps[i], i, i === hi, f);
    if (b < ps.length) h += '<button type="button" class="more" data-a="full">下の ' + (ps.length - b) + ' 行を表示</button>';
    docEl.innerHTML = h;
    scrollInto(docEl, docEl.querySelector('[data-m]') || docEl.querySelector('.hit'), true);
  }

  function render() {
    var s = st();
    if (!s || !s.documents) return;
    var fs = s.findings || [], ck = loadChecked();
    var v = visible(fs);
    if (!v.some(function (f) { return f.id === curId; })) curId = v.length ? v[0].id : null;
    drawTop(s, fs, ck); drawChips(fs); drawList(s, fs, ck); drawDetail(s, fs, ck);
    scrollInto(itemsEl, itemsEl.querySelector('.on'), false);
  }

  function go(d) {
    var s = st(); if (!s) return;
    var v = visible(s.findings || []); if (!v.length) return;
    var i = 0;
    v.forEach(function (f, j) { if (f.id === curId) i = j; });
    curId = v[(i + d + v.length) % v.length].id;
    render();
  }
  function setChecked(on) {
    var ck = loadChecked(), i = ck.indexOf(curId);
    if (on && i < 0) ck.push(curId);
    if (!on && i >= 0) ck.splice(i, 1);
    saveChecked(ck);
  }
  function clearErr() { errEl.classList.remove('on'); reasonEl.classList.remove('bad'); }
  function openDlg() {
    var s = st(), f = ((s && s.findings) || []).filter(function (x) { return x.id === curId; })[0];
    if (!f) return;
    reportFor = f.id; reasonEl.value = ''; clearErr();
    $('[data-dlgt]').textContent = '対象：' + dname(s, f.doc_id) + '「' + (f.reason || '') + '」';
    dlgOpener = document.activeElement;
    dlg.hidden = false; reasonEl.focus();
  }
  // 閉じたら開いた元（誤検知を通報）へフォーカスを戻す。Esc でも閉じる
  var dlgOpener = null;
  function closeDlg() {
    dlg.hidden = true; reportFor = null;
    var o = dlgOpener; dlgOpener = null;
    if (o && o.isConnected && o.focus) o.focus();
    else { var b = R.querySelector('[data-a="rep"]'); if (b) b.focus(); }
  }

  R.addEventListener('click', function (e) {
    var t = e.target.closest('button'); if (!t || !R.contains(t)) return;
    if (t.dataset.flt) { flt = t.dataset.flt; render(); return; }
    if (t.dataset.id) { curId = t.dataset.id; render(); return; }
    var a = t.dataset.a, s = st();
    if (a === 'next') go(1);
    else if (a === 'prev') go(-1);
    else if (a === 'ok') {
      var was = loadChecked().indexOf(curId) >= 0;
      setChecked(!was); render(); if (!was) go(1);
    }
    else if (a === 'see') scrollInto(docEl, docEl.querySelector('[data-m]') || docEl.querySelector('.hit'), true);
    else if (a === 'full') { ext[curId] = true; render(); }
    else if (a === 'rep' && s) openDlg();
  });
  reasonEl.addEventListener('input', clearErr);
  dlg.addEventListener('click', function (e) { if (e.target === dlg) closeDlg(); });
  dlg.addEventListener('keydown', function (e) { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeDlg(); } });
  $('[data-cancel]').addEventListener('click', closeDlg);
  $('[data-send]').addEventListener('click', function () {
    var reason = reasonEl.value.trim();
    if (!reason) { errEl.classList.add('on'); reasonEl.classList.add('bad'); reasonEl.focus(); return; }
    if (busy || !reportFor) return;
    busy = true;
    Promise.resolve(window.DVT.api('tier/findings/' + reportFor + '/report', json('POST', { reason: reason, by: userName() })))
      .then(function () { return window.DVT.refresh(); })
      .then(function () { busy = false; closeDlg(); toast('誤検知として通報しました。', 'ok'); go(1); },
        function (err) { busy = false; toast((err && err.message) || '通報できませんでした。少し待ってからもう一度お試しください。'); });
  });
  // 画面共通の [data-go]（メニュー移動）に拾われないよう data-to-report を使う
  $('[data-to-report]').addEventListener('click', function () { window.DVT.go(3); });
  // 「登録からやり直す」は指摘・通報・承認・結論を消すので、1 クリックでは実行せず確認行を挟む
  var redoBtn = $('[data-redo]');
  var cfm = document.createElement('div');
  cfm.className = 'dvt-confirm'; cfm.hidden = true; cfm.setAttribute('role', 'alertdialog');
  cfm.innerHTML = '<span class="dvt-confirm-msg">検査をやり直すと、この検査の指摘・誤検知の通報・登録の承認・結論がすべて消えます。登録した文書は残ります。元に戻せません。</span>' +
    '<button type="button" class="danger" data-cfm-ok>やり直す</button><button type="button" data-cfm-no>やめる</button>';
  $('.s2top').insertAdjacentElement('afterend', cfm);
  function setCfm(open) {
    cfm.hidden = !open;
    if (open) { $('[data-cfm-no]').focus(); } else { redoBtn.focus(); }
  }
  redoBtn.addEventListener('click', function () { if (!busy) setCfm(cfm.hidden); });
  $('[data-cfm-no]').addEventListener('click', function () { setCfm(false); });
  cfm.addEventListener('keydown', function (e) { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); setCfm(false); } });
  $('[data-cfm-ok]').addEventListener('click', function () {
    if (busy) return;
    busy = true;
    Promise.resolve(window.DVT.api('tier/reset', json('POST', { to: 1 })))
      .then(function () { return window.DVT.refresh(); })
      .then(function () { busy = false; setCfm(false); window.DVT.go(1); },
        function (err) { busy = false; toast((err && err.message) || 'やり直せませんでした。少し待ってからもう一度お試しください。'); });
  });
  document.addEventListener('keydown', function (e) {
    if (!document.body.contains(R) || R.getClientRects().length === 0) return;
    if (!dlg.hidden) { if (e.key === 'Escape') closeDlg(); return; }
    if (/TEXTAREA|INPUT|SELECT/.test((e.target.tagName || '')) || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === 'j' || e.key === 'J') go(1); else if (e.key === 'k' || e.key === 'K') go(-1);
  });

  document.addEventListener('dvt:state', function () { render(); syncShown(); });
  render();
  syncShown();
})();
