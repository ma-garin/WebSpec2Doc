/* ドキュメント検証: 検証観点の画面（承認済み案の 6 状態＋取り込み） */
(function () {
  'use strict';
  var DV = window.DV;
  if (!DV) return;
  var $ = function (id) { return document.getElementById(id); };
  var esc = DV.esc || function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var VSEV = [['critical', '重大'], ['major', '主要'], ['minor', '軽微']];
  var SCOPE_NOTE = { req: 'システムテストと対になる', design: '結合テストと対になる', pair: '要件定義書と基本設計書の突き合わせ' };
  var SCOPE_NAME = { req: '要件定義書', design: '基本設計書', pair: '対検査' };
  var vp = { rows: [], scopes: [], note: '', dirty: {}, saveErr: false, busy: false, error: false, saving: false };

  function cnt() { return Object.keys(vp.dirty).length; }
  function sevOf(r) { return vp.dirty[r.id] || r.severity; }
  function setBtns(disabled) {
    ['dvgVpExport', 'dvgVpImport'].forEach(function (id) { var b = $(id); if (b) b.disabled = !!disabled; });
  }

  function pct(v) { return v == null ? '−' : Math.round(v * 100) + '%'; }
  function accCell(r) {
    if (r.kind !== 'auto') return '−';
    if (r.precision == null && r.recall == null) return '未測定';
    var low = r.recall != null && r.recall < 0.5;
    return '適合率 ' + pct(r.precision) + '<br><span' + (low ? ' class="vp-low"' : '') + '>再現率 ' + pct(r.recall) + '</span>' +
      (low ? '<br><small class="vp-low">見落としが多い</small>' : '');
  }
  function segHtml(r) {
    var cur = sevOf(r);
    return '<div class="vp-seg" role="radiogroup" aria-label="' + esc(r.name) + 'の重大度">' + VSEV.map(function (s) {
      var on = s[0] === cur;
      return '<button type="button" role="radio" class="' + s[0] + (on ? ' on' : '') + '" aria-checked="' + on +
        '" tabindex="' + (on ? 0 : -1) + '" data-id="' + esc(r.id) + '" data-s="' + s[0] + '">' + s[1] + '</button>';
    }).join('') + '</div>';
  }
  var COLS = '<colgroup><col><col style="width:130px"><col style="width:150px"><col style="width:190px"></colgroup>';
  var HEAD = '<thead><tr><th>観点</th><th>検査の方法</th><th>精度</th><th>重大度</th></tr></thead>';

  function skeleton() {
    var row = '<tr class="vp-skel"><td><i></i></td><td><i></i></td><td><i></i></td><td><i></i></td></tr>';
    return '<div class="vp-sec"><div class="vp-card"><table class="vp-t" aria-hidden="true">' + COLS + HEAD + '<tbody>' +
      row + row + row + row + '</tbody></table></div></div>';
  }
  function errHtml() {
    return '<div class="vp-err" role="alert"><span class="vp-err-ic" aria-hidden="true">!</span><div>' +
      '<b>検証観点を読み込めませんでした</b>' +
      '<p>通信が切れたか、サーバが混み合っています。時間をおいて「もう一度読み込む」を押してください。</p>' +
      '<button class="btn" type="button" id="vpReload">もう一度読み込む</button></div></div>';
  }
  function legend() {
    return '<p class="vp-legend"><span><i class="vp-dot critical"></i>重大 直すまで次の工程へ進めない</span>' +
      '<span><i class="vp-dot major"></i>主要 直してから承認する</span>' +
      '<span><i class="vp-dot minor"></i>軽微 記録に残す</span>' +
      '<span class="mut">指摘一覧はこの重さの順に並びます</span></p>';
  }
  function rowHtml(r) {
    var auto = r.kind === 'auto';
    return '<tr' + (vp.dirty[r.id] ? ' class="vp-chg"' : '') + '><td><div class="vp-nm">' + esc(r.name) +
      '</div><div class="vp-ds">' + esc(r.desc) + '</div></td>' +
      '<td><span class="vp-kind ' + (auto ? 'auto' : 'hum') + '">' + (auto ? '自動で検査' : '人が確認') + '</span></td>' +
      '<td class="vp-acc">' + accCell(r) + '</td><td>' + segHtml(r) + '</td></tr>';
  }
  function secHtml(s) {
    var rows = vp.rows.filter(function (r) { return r.scope === s.id; });
    var nm = SCOPE_NAME[s.id] || s.name, note = SCOPE_NOTE[s.id] || (s.test ? s.test + 'と対になる' : '');
    return '<section class="vp-sec"><h3 class="vp-sh">' + esc(nm) + ' <span class="mut">' + esc(note) + '</span></h3>' +
      '<div class="vp-card"><table class="vp-t">' + COLS + HEAD + '<tbody>' + rows.map(rowHtml).join('') + '</tbody></table></div></section>';
  }
  function saveBar() {
    var n = cnt(); if (!n) return '';
    if (vp.saveErr) {
      return '<div class="vp-save is-err" role="alert"><span>保存できませんでした。変更はこの画面に残っています。通信を確かめて「もう一度保存」を押してください。</span>' +
        '<span><button class="btn" type="button" id="vpDiscard">変更を破棄</button> <button class="btn btn-primary" type="button" id="vpSave">もう一度保存</button></span></div>';
    }
    return '<div class="vp-save"><span><b>' + n + '</b> 件の変更が未保存です。保存するまで検査には反映されません。</span>' +
      '<span><button class="btn" type="button" id="vpDiscard">変更を破棄</button> <button class="btn btn-primary" type="button" id="vpSave"' +
      (vp.saving ? ' disabled' : '') + '>保存する</button></span></div>';
  }
  function render() {
    var el = $('dvgClEdit'); if (!el) return;
    el.removeAttribute('aria-busy');
    if (vp.busy) {
      el.setAttribute('aria-busy', 'true'); setBtns(true);
      el.innerHTML = legend() + skeleton(); return;
    }
    if (vp.error) {
      setBtns(false); var x = $('dvgVpExport'); if (x) x.disabled = true;
      el.innerHTML = errHtml(); return;
    }
    setBtns(false);
    el.innerHTML = legend() + vp.scopes.map(secHtml).join('') +
      (vp.note ? '<p class="mut vp-note">' + esc(vp.note) + '</p>' : '') + saveBar();
  }
  function setSev(id, v) {
    var r = vp.rows.filter(function (x) { return x.id === id; })[0]; if (!r) return;
    var next = Object.assign({}, vp.dirty);
    if (v === r.severity) delete next[id]; else next[id] = v;
    vp.dirty = next; vp.saveErr = false; render();
    var b = document.querySelector('#dvgClEdit .vp-seg button[data-id="' + id + '"][data-s="' + v + '"]');
    if (b) b.focus();
  }
  function apply(d) {
    vp.rows = d.viewpoints || []; vp.scopes = d.scopes || []; vp.note = d.accuracy_note || '';
  }
  function vpLoad() {
    vp.busy = true; vp.error = false; render();
    return DV.api('/api/docverify/viewpoints').then(function (d) {
      apply(d); vp.dirty = {}; vp.saveErr = false; vp.busy = false; render();
    }).catch(function () { vp.busy = false; vp.error = true; render(); });
  }
  function vpSave() {
    var body = Object.keys(vp.dirty).map(function (id) { return { id: id, severity: vp.dirty[id] }; });
    vp.saving = true; render();
    return DV.api('/api/docverify/viewpoints', { method: 'PUT', json: body }).then(function (d) {
      apply(d); vp.dirty = {}; vp.saveErr = false; vp.saving = false; render();
      DV.toast('保存しました。次の検査から反映されます。'); return true;
    }).catch(function () { vp.saving = false; vp.saveErr = true; render(); return false; });
  }

  /* 取り込み */
  function importDialog(file, p) {
    var s = p.summary;
    var tag = { error: ['e', 'エラー'], dup: ['d', '重複'] };
    var list = p.issues.slice(0, 50).map(function (i) {
      return '<tr><td>' + i.row + '</td><td><span class="vp-tag ' + tag[i.result][0] + '">' + tag[i.result][1] + '</span></td><td>' + esc(i.text) + '</td></tr>';
    }).join('');
    var ok = s.rows - s.dup;
    var rest = '<tr><td>ほか</td><td><span class="vp-tag o">取り込める</span></td><td>問題ありません（' + ok + ' 行）。</td></tr>';
    var html = '<div class="vp-file"><b>' + esc(p.file || file.name) + '</b></div>' +
      '<div class="vp-sum"><div>取り込む行<b>' + s.rows + '</b></div><div class="d">重複（既存と同じ名前）<b>' + s.dup + '</b></div><div class="e">エラー<b>' + s.error + '</b></div></div>' +
      '<div class="vp-scroll"><table class="vp-t"><thead><tr><th style="width:64px">行</th><th style="width:96px">結果</th><th>内容と次の行動</th></tr></thead><tbody>' + list + rest + '</tbody></table></div>' +
      (s.dup ? '<label class="vp-ow"><input type="checkbox" id="vpOw"> 同じ名前の観点は上書きする（外すと取り込まない）</label>' : '') +
      '<p class="mut vp-note">エラーの行は取り込まれません。エラー行を直したファイルを選び直すと、全行を取り込めます。取り込んだ観点は「人が確認」として追加されます。</p>';
    DV.modal({ title: '取り込み内容の確認', html: html, ok: s.rows ? s.rows + ' 行を取り込む' : null, cancel: '閉じる' }).then(function (go) {
      if (!go) return;
      var ow = $('vpOw');
      var fd = new FormData(); fd.append('file', file); fd.append('commit', '1'); fd.append('overwrite', ow && ow.checked ? '1' : '0');
      DV.api('/api/docverify/viewpoints/import', { method: 'POST', form: fd }).then(function (r) {
        DV.toast(r.added + ' 行を追加、' + r.updated + ' 行を上書きしました。' + (r.errors ? r.errors + ' 行はエラーのため取り込んでいません。' : ''));
        vpLoad();
      }).catch(function () {});
    });
  }

  /* 画面内の操作 */
  var el = $('dvgClEdit');
  if (el) {
    el.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      if (b.dataset.s) return setSev(b.dataset.id, b.dataset.s);
      if (b.id === 'vpDiscard') { vp.dirty = {}; vp.saveErr = false; return render(); }
      if (b.id === 'vpSave') return vpSave();
      if (b.id === 'vpReload') return vpLoad();
    });
    el.addEventListener('keydown', function (e) {
      var b = e.target.closest && e.target.closest('.vp-seg button'); if (!b) return;
      var d = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0;
      if (!d) return;
      e.preventDefault();
      var i = (VSEV.map(function (s) { return s[0]; }).indexOf(b.dataset.s) + d + VSEV.length) % VSEV.length;
      setSev(b.dataset.id, VSEV[i][0]);
    });
  }
  var fileIn = $('dvgVpFile'), openBtn = $('dvgVpImport'), expBtn = $('dvgVpExport');
  if (openBtn && fileIn) {
    openBtn.addEventListener('click', function () { fileIn.value = ''; fileIn.click(); });
    fileIn.addEventListener('change', function () {
      var f = fileIn.files[0]; if (!f) return;
      var fd = new FormData(); fd.append('file', f);
      DV.api('/api/docverify/viewpoints/import', { method: 'POST', form: fd }).then(function (p) { importDialog(f, p); }).catch(function () {});
    });
  }
  if (expBtn) {
    expBtn.addEventListener('click', function () {
      if (cnt()) return DV.toast('未保存の変更があります。保存してから書き出してください。');
      location.href = '/api/docverify/viewpoints/export';
    });
  }

  /* 離脱確認: 別ビューへ移るナビ操作を capture で止める */
  document.addEventListener('click', function (e) {
    if (!cnt()) return;
    var a = e.target.closest && e.target.closest('[data-nav], [data-go]');
    if (!a || (a.dataset.nav || a.dataset.go) === 'checklists') return;
    e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
    var html = '<p>' + cnt() + ' 件の重大度の変更が保存されていません。このまま移動すると変更は失われます。</p>' +
      '<p><button class="btn" type="button" id="vpLeave">保存せずに移動</button></p>';
    var left = false;
    DV.modal({ title: '保存していない変更があります', html: html, ok: '保存して移動', cancel: 'この画面に残る' }).then(function (go) {
      if (left) return;
      if (!go) return;
      vpSave().then(function (ok) { if (ok) a.click(); });
    });
    var lv = $('vpLeave');
    if (lv) lv.addEventListener('click', function () {
      left = true; vp.dirty = {}; vp.saveErr = false;
      var c = document.querySelector('#dv-modal [data-modal="cancel"]'); if (c) c.click();
      a.click();
    });
  }, true);
  window.addEventListener('beforeunload', function (e) {
    if (!cnt()) return;
    e.preventDefault(); e.returnValue = '';
  });

  DV.on('checklists', vpLoad);
})();
