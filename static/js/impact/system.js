/* System 09 影響度分析 — 対象システムの画面（概要・文書・ベースライン・つながり・変更要求・設定・メンバー・監査）。DD-008 */
(function () {
  'use strict';
  var IM = window.IM, api = IM.api, ui = IM.ui, esc = ui.esc, $ = ui.$, $$ = ui.$$;
  var TITLE = { overview: '概要', docs: '文書', baselines: 'ベースライン', links: 'つながり', rea: 'コード依存', crs: '変更要求', settings: '設定', members: 'メンバー', audit: '監査' };
  var COUNT = { documents: '文書', items: '項目', baselines: 'ベースライン', links: 'つながり', crs: '変更要求' };

  function head(title, copy, actions) {
    return '<div class="c-section-head"><div class="c-section-head__main"><h2 class="c-section-head__title">' + esc(title) + '</h2>' +
      (copy ? '<p class="c-section-head__desc">' + esc(copy) + '</p>' : '') + '</div><div class="c-section-head__actions">' + (actions || '') + '</div></div>';
  }
  function table(cols, rows, label) {
    return '<div class="bt-tblwrap im-tblwrap"><table class="bt-tbl" aria-label="' + esc(label) + '"><thead><tr>' +
      cols.map(function (c) { return '<th scope="col">' + c + '</th>'; }).join('') + '</tr></thead><tbody>' + rows.join('') + '</tbody></table></div>';
  }
  var ACTION = { 'system.create': '対象システムを作成', 'system.update': '設定を変更', 'system.delete': '対象システムを削除',
    'member.set': '役割を付与', 'member.remove': 'メンバーを外す', 'document.add': '文書を取り込み', 'document.kind': '文書の種類を変更',
    'document.remove': '文書を外す', 'baseline.create': 'ベースラインを作成', 'link.add': 'つながりを登録', 'link.remove': 'つながりを削除',
    'link.suggest.accept': 'つながり候補を採用', 'link.suggest.reject': 'つながり候補を却下', 'cr.create': '変更要求を起票', 'cr.update': '変更要求を編集',
    'cr.transition': '状態を変更', 'cr.approve': '承認', 'cr.return': '差し戻し', 'impact.resolve': '影響を解消', 'impact.override': '影響度・発生可能性を修正',
    'actual.record': '改修後レビューを記録', 'llm.send': 'LLM へ送信', 'analysis.done': '分析が完了', 'migrate': '旧データを移行' };
  var FIELD = { status: '状態', role: '役割', policy: '送信方針', name: '名前', reason: '理由', state: '判断', decision: '決定', note: '注記',
    kind: '種類', p1_min: 'P1 下限', p2_min: 'P2 下限', depth_default: '既定の段数', impact_level: '影響度', likelihood: '発生可能性' };
  function fmtVal(v) {
    if (v === null || v === undefined || v === '') return '';
    if (typeof v === 'string') { try { v = JSON.parse(v); } catch (_) { return v; } }
    if (typeof v !== 'object') return String(v);
    return Object.keys(v).map(function (k) {
      var x = v[k], t = (ui.STATUS && ui.STATUS[x]) || (ui.ROLE && ui.ROLE[x]) || (ui.POLICY && ui.POLICY[x]) || x;
      return (FIELD[k] || k) + ': ' + (x === null ? '（なし）' : typeof t === 'object' ? JSON.stringify(t) : t);
    }).join(' ／ ');
  }
  function num(v) { return esc(v === undefined || v === null ? 0 : v); }
  function on(el, sel, fn) { $$(sel, el).forEach(function (b) { b.addEventListener('click', function (e) { fn(b, e); }); }); }
  function rerender() { IM.app.render(); }
  function act(btn, p, okMsg) {
    btn.disabled = true;
    return p.then(function (r) { if (okMsg) ui.toast(okMsg); rerender(); return r; }, function (e) { btn.disabled = false; ui.banner(e.message); });
  }

  /* ---------- 概要 ---------- */
  function overview(el, ctx) {
    var c = ctx.system.counts || {};
    var kpis = Object.keys(COUNT).map(function (k) { return '<div class="kpi"><b>' + num(c[k]) + '</b><span>' + COUNT[k] + '</span></div>'; }).join('');
    el.innerHTML = head(ctx.system.name, ctx.system.description || '', ui.can(ctx.role, 'cr_write') ? '<button type="button" class="btn-primary" data-act="new-cr">変更要求を起票</button>' : '') +
      '<div class="kpis im-kpis5">' + kpis + '</div>' + head('最近の変更要求', '新しい順に 5 件', '<button type="button" class="btn-outline-sm" data-go="crs">すべて見る</button>') +
      '<div id="im-recent"></div>' +
      head('予測の精度の推移', '改修後レビューを記録した変更要求ごとに、採用率と見逃しの件数を表示します（REQ-F-040）。', '') +
      '<div id="im-trend"></div>';
    trendTable($('#im-trend', el), ctx);
    on(el, '[data-act=new-cr]', function () { openCreateCr(ctx); });
    on(el, '[data-go=crs]', function () { IM.app.go({ sid: ctx.sid, tab: 'crs' }); });
    crTable($('#im-recent', el), ctx, '', 5);
  }

  function trendTable(box, ctx) {
    box.innerHTML = '<div class="empty">読み込み中…</div>';
    api.trend(ctx.sid).then(function (d) {
      var rows = (d && d.trend) || [];
      if (!rows.length) { box.innerHTML = ui.empty({ title: 'まだ推移がありません', desc: '承認済みの変更要求で「改修後レビュー」に実際に影響した項目を記録すると、ここに予測の当たり具合が出ます。' }); return; }
      var pct = function (v) { return v == null ? '—' : Math.round(v * 100) + '%'; };
      box.innerHTML = table(['変更要求', '題名', '採用率', '見逃し', '再現率'], rows.map(function (r) {
        return '<tr><td><code>' + esc(r.code) + '</code></td><td>' + esc(r.title) + '</td><td>' + pct(r.adoption_rate) + '</td><td>' +
          num((r.missed || []).length) + ' 件</td><td>' + pct(r.recall) + '</td></tr>';
      }), '予測の精度の推移');
    }, function (e) { ui.failed(box, e, function () { trendTable(box, ctx); }); });
  }

  /* ---------- 文書 ---------- */
  function docs(el, ctx) {
    var edit = ui.can(ctx.role, 'documents');
    el.innerHTML = head('文書', '取り込んだ文書は項目に分けて保存します。同じ名前の文書は置き換えます。', edit ?
      '<button type="button" class="btn-primary" data-act="pick">文書を取り込む</button><input type="file" id="im-docfile" multiple hidden accept=".xlsx,.docx,.md,.txt,.pdf,.csv" aria-label="取り込む文書">' : '') +
      '<div id="im-upres" role="status" aria-live="polite"></div><div id="im-docs"></div>';
    var box = $('#im-docs', el);
    if (lastUpload) { $('#im-upres', el).innerHTML = lastUpload; lastUpload = ''; }
    if (edit) {
      var input = $('#im-docfile', el);
      on(el, '[data-act=pick]', function () { input.click(); });
      input.addEventListener('change', function () { upload(ctx, Array.prototype.slice.call(input.files), $('#im-upres', el)); });
    }
    ui.loading(box);
    api.documents(ctx.sid).then(function (d) {
      var rows = api.list(d, 'documents');
      if (!rows.length) { box.innerHTML = ui.empty({ title: 'まだ文書がありません', desc: '要件・設計書・画面仕様書・テストケースを取り込むと、影響の分析に使えます。', steps: [['文書を選ぶ', '.xlsx / .docx / .md / .txt / .pdf'], ['種類を確かめる', '名前から推定。違えば選び直す'], ['ベースラインを作る', 'その時点の版を固定']] }); return; }
      box.innerHTML = table(['文書', '種類', '項目数', '取り込み', '<span class="visually-hidden">操作</span>'], rows.map(function (r) {
        var kind = edit ? '<select data-kind="' + esc(r.id) + '" aria-label="' + esc(r.name) + ' の種類">' + Object.keys(ui.KIND).map(function (k) {
          return '<option value="' + k + '"' + (k === r.kind ? ' selected' : '') + '>' + ui.KIND[k] + '</option>'; }).join('') + '</select>' : esc(ui.KIND[r.kind] || r.kind);
        return '<tr><td>' + esc(r.name) + '</td><td>' + kind + '</td><td class="num">' + num(r.item_count) + '</td><td>' + ui.fmtDate(r.created_at) + ' ' + esc(r.created_by || '') + '</td>' +
          '<td>' + (edit ? '<button type="button" class="bt-x" data-del="' + esc(r.id) + '" data-name="' + esc(r.name) + '" aria-label="' + esc(r.name) + ' を削除">削除</button>' : '') + '</td></tr>';
      }), '取り込んだ文書');
      $$('[data-kind]', box).forEach(function (s) {
        s.addEventListener('change', function () { api.setDocKind(ctx.sid, s.dataset.kind, s.value).then(function () { ui.toast('種類を変更しました'); }, function (e) { ui.banner(e.message); }); });
      });
      on(box, '[data-del]', function (b) {
        ui.confirm({ title: '文書を削除', message: '「' + b.dataset.name + '」と、その項目・つながりを削除します。ベースラインに固定した内容は残ります。', submit: '削除する' })
          .then(function () { act(b, api.deleteDocument(ctx.sid, b.dataset.del), '削除しました'); });
      });
    }, function (e) { ui.failed(box, e, rerender); });
  }
  function upload(ctx, files, out) {
    var results = [];
    var draw = function (busy) {
      out.innerHTML = '<div class="bt-card im-upres">' + (busy ? '<p><span class="im-spin" aria-hidden="true"></span>取り込み中 ' + results.length + ' / ' + files.length + '</p>' : '<p><b>取り込み結果</b></p>') +
        '<ul class="bt-list">' + results.map(function (r) {
          return '<li class="' + (r.ok ? 'im-ok' : 'im-ng') + '"><b>' + esc(r.name) + '</b>: ' + esc(r.msg) + '</li>'; }).join('') + '</ul></div>';
    };
    draw(true);
    files.reduce(function (p, f) {
      return p.then(function () {
        return api.uploadDocument(ctx.sid, f).then(function (d) {
          var doc = (d && d.added && d.added[0]) || api.obj(d, 'document'); results.push({ name: f.name, ok: true, msg: '項目 ' + (doc.item_count || 0) + ' 件・' + (ui.KIND[doc.kind] || '種類未設定') });
        }, function (e) { results.push({ name: f.name, ok: false, msg: e.message }); }).then(function () { draw(true); });
      });
    }, Promise.resolve()).then(function () {
      draw(false);
      lastUpload = out.innerHTML; /* 再描画後も文書ごとの結果（失敗の理由）を残す */
      IM.app.refreshSystem().then(rerender, rerender);
    });
  }
  var lastUpload = '';

  /* ---------- ベースライン ---------- */
  function baselines(el, ctx) {
    var edit = ui.can(ctx.role, 'baselines');
    el.innerHTML = head('ベースライン', 'その時点の文書と項目を版名つきで固定します。', edit ? '<button type="button" class="btn-primary" data-act="new-bl">ベースラインを作成</button>' : '') +
      '<div id="im-bls"></div>' + head('2 版の差分', '項目単位で追加・変更・削除を表示します。', '') + '<div id="im-diff"></div>';
    on(el, '[data-act=new-bl]', function () {
      ui.modal({ title: 'ベースラインを作成', submit: '作成する', body: '<label class="bt-field">版名<input name="name" maxlength="100" required placeholder="例: v1.2 リリース時点"></label>' +
        '<label class="bt-field">メモ<textarea name="note" rows="2" maxlength="500" class="im-ta"></textarea></label>',
        onSubmit: function (f) { return api.createBaseline(ctx.sid, { name: ui.need(f.name.value, '版名'), note: f.note.value.trim() }).then(function () { ui.toast('ベースラインを作成しました'); rerender(); }); } });
    });
    var box = $('#im-bls', el), dbox = $('#im-diff', el);
    ui.loading(box);
    api.baselines(ctx.sid).then(function (d) {
      var rows = api.list(d, 'baselines');
      if (!rows.length) { box.innerHTML = ui.empty({ title: 'まだベースラインがありません', desc: '文書を取り込んでからベースラインを作ると、版の差分から変更要求を起票できます。' }); dbox.innerHTML = ''; return; }
      box.innerHTML = table(['版名', 'メモ', '項目数', '作成'], rows.map(function (r) {
        return '<tr><td><b>' + esc(r.name) + '</b></td><td>' + esc(r.note || '') + '</td><td class="num">' + num(r.item_count) + '</td><td>' + ui.fmtDate(r.created_at) + ' ' + esc(r.created_by || '') + '</td></tr>'; }), 'ベースライン');
      if (rows.length < 2) { dbox.innerHTML = '<p class="bt-hint">差分を見るにはベースラインが 2 つ必要です。</p>'; return; }
      var opts = function (sel) { return rows.map(function (r, i) { return '<option value="' + esc(r.id) + '"' + (i === sel ? ' selected' : '') + '>' + esc(r.name) + '</option>'; }).join(''); };
      dbox.innerHTML = '<div class="im-row"><label class="bt-field">変更前<select id="im-dold">' + opts(1) + '</select></label><label class="bt-field">変更後<select id="im-dnew">' + opts(0) + '</select></label>' +
        '<button type="button" class="btn-outline-sm" id="im-dgo">差分を見る</button></div><div id="im-dres"></div>';
      $('#im-dgo', dbox).addEventListener('click', function () { showDiff(ctx, $('#im-dold', dbox).value, $('#im-dnew', dbox).value, $('#im-dres', dbox)); });
    }, function (e) { ui.failed(box, e, rerender); });
  }
  function showDiff(ctx, a, b, out) {
    if (a === b) { out.innerHTML = '<p class="bt-hint im-ng">違う 2 つの版を選んでください。</p>'; return; }
    ui.loading(out, '差分を計算しています…');
    api.baselineDiff(ctx.sid, a, b).then(function (d) {
      d = (d && d.diff) || d; var add = d.added || [], mod = d.modified || [], rem = d.removed || [];
      if (!add.length && !mod.length && !rem.length) { out.innerHTML = '<p class="bt-hint">2 つの版に差はありません。</p>'; return; }
      var rows = add.map(function (i) { return '<tr><td><span class="pill p-pass">追加</span></td><td><code>' + esc(i.code) + '</code></td><td></td><td>' + esc(i.text) + '</td></tr>'; })
        .concat(mod.map(function (m) { return '<tr><td><span class="pill p-warn">変更</span></td><td><code>' + esc((m.new || m.old || {}).code) + '</code></td><td><del>' + esc((m.old || {}).text) + '</del></td><td><ins>' + esc((m.new || {}).text) + '</ins></td></tr>'; }))
        .concat(rem.map(function (i) { return '<tr><td><span class="pill p-fail">削除</span></td><td><code>' + esc(i.code) + '</code></td><td><del>' + esc(i.text) + '</del></td><td></td></tr>'; }));
      out.innerHTML = '<p class="bt-mut">追加 ' + add.length + ' ・ 変更 ' + mod.length + ' ・ 削除 ' + rem.length + '</p>' + table(['区分', '項目', '変更前', '変更後'], rows, 'ベースラインの差分');
    }, function (e) { ui.failed(out, e); });
  }

  /* ---------- つながり ---------- */
  function side(l, k) { var o = l[k] || {}; return { code: l[k + '_code'] || o.code || l[k + '_item'], text: l[k + '_text'] || o.text || '' }; }
  function picker(id, label) {
    return '<div class="im-pick"><label class="bt-field">' + label + '<span class="im-row"><input type="search" class="c-search" id="' + id + '-q" placeholder="項目 ID か本文の語で検索" aria-label="' + label + 'を検索">' +
      '<button type="button" class="btn-outline-sm" data-find="' + id + '">検索</button></span></label><select id="' + id + '" size="5" aria-label="' + label + 'の候補"></select></div>';
  }
  function links(el, ctx) {
    var edit = ui.can(ctx.role, 'links');
    el.innerHTML = head('つながり', '関係する 2 項目を登録すると、分析で両方から辿ります。', '') +
      (edit ? '<div class="bt-card"><h3>つながりを登録</h3><div class="im-pick2">' + picker('im-pa', '項目 A') + picker('im-pb', '項目 B') + '</div>' +
        '<div class="bt-actions"><span class="sp"></span><button type="button" class="btn-primary" id="im-linkadd">登録する</button></div></div>' : '') +
      '<div id="im-links"></div>' + head('つながりの候補', '意味の近い項目・テストケースに現れる項目 ID から作った候補です。', edit ? '<button type="button" class="btn-outline-sm" data-act="suggest">候補を作る</button>' : '') + '<div id="im-sugs"></div>';
    if (edit) {
      on(el, '[data-find]', function (b) { findItems(ctx, b.dataset.find); });
      $$('input[type=search]', el).forEach(function (i) { i.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); findItems(ctx, i.id.replace('-q', '')); } }); });
      $('#im-linkadd', el).addEventListener('click', function () {
        var a = $('#im-pa', el).value, b = $('#im-pb', el).value;
        if (!a || !b) { ui.banner('項目 A と項目 B をそれぞれ検索して 1 つずつ選んでください。'); return; }
        if (a === b) { ui.banner('違う 2 つの項目を選んでください。'); return; }
        act(this, api.addLink(ctx.sid, a, b), 'つながりを登録しました');
      });
      on(el, '[data-act=suggest]', function (b) { act(b, api.suggest(ctx.sid).then(function (d) { ui.toast('候補を ' + (d.count || 0) + ' 件作りました'); })); });
    }
    var box = $('#im-links', el); ui.loading(box);
    api.links(ctx.sid).then(function (d) {
      var rows = api.list(d, 'links');
      box.innerHTML = rows.length ? table(['項目 A', '項目 B', '由来', '登録', '<span class="visually-hidden">操作</span>'], rows.map(function (l) {
        var a = side(l, 'a'), b = side(l, 'b');
        return '<tr><td><code>' + esc(a.code) + '</code> ' + esc(a.text) + '</td><td><code>' + esc(b.code) + '</code> ' + esc(b.text) + '</td><td>' + (l.origin === 'suggested' ? '候補を採用' : '手動') + '</td>' +
          '<td>' + ui.fmtDate(l.created_at) + '</td><td>' + (edit ? '<button type="button" class="bt-x" data-del="' + esc(l.id) + '" aria-label="つながりを削除">削除</button>' : '') + '</td></tr>'; }), 'つながり')
        : ui.empty({ title: 'まだつながりがありません', desc: '2 つの項目を検索して選び「登録する」を押すか、候補を採用してください。' });
      on(box, '[data-del]', function (b) { ui.confirm({ title: 'つながりを削除', message: 'このつながりを削除します。以後の分析では辿りません。', submit: '削除する' }).then(function () { act(b, api.deleteLink(ctx.sid, b.dataset.del), '削除しました'); }); });
    }, function (e) { ui.failed(box, e, rerender); });
    var sbox = $('#im-sugs', el); ui.loading(sbox);
    api.suggestions(ctx.sid).then(function (d) {
      var rows = api.list(d, 'suggestions');
      sbox.innerHTML = rows.length ? table(['項目 A', '項目 B', '近さ', '理由', '<span class="visually-hidden">判断</span>'], rows.map(function (s) {
        var a = side(s, 'a'), b = side(s, 'b');
        return '<tr><td><code>' + esc(a.code) + '</code> ' + esc(a.text) + '</td><td><code>' + esc(b.code) + '</code> ' + esc(b.text) + '</td><td class="num">' + esc(Number(s.score || 0).toFixed(2)) + '</td><td>' + esc(s.reason || '') + '</td>' +
          '<td>' + (edit ? '<button type="button" class="btn-outline-sm" data-acc="1" data-id="' + esc(s.id) + '">採用</button> <button type="button" class="btn-outline-sm" data-acc="0" data-id="' + esc(s.id) + '">却下</button>' : '') + '</td></tr>'; }), 'つながりの候補')
        : '<p class="bt-hint">未判断の候補はありません。</p>';
      on(sbox, '[data-acc]', function (b) { act(b, api.decide(ctx.sid, b.dataset.id, b.dataset.acc === '1'), b.dataset.acc === '1' ? '採用しました' : '却下しました'); });
    }, function (e) { ui.failed(sbox, e); });
  }
  function findItems(ctx, id) {
    var q = $('#' + id + '-q').value.trim(), sel = $('#' + id);
    sel.innerHTML = '<option disabled>検索中…</option>';
    api.items(ctx.sid, { q: q }).then(function (d) {
      var rows = api.list(d, 'items');
      sel.innerHTML = rows.length ? rows.map(function (i) { return '<option value="' + esc(i.id) + '">' + esc(i.code) + ' ' + esc(String(i.text || '').slice(0, 60)) + '（' + esc(i.document_name || '') + '）</option>'; }).join('')
        : '<option disabled>該当する項目がありません</option>';
    }, function (e) { sel.innerHTML = '<option disabled>' + esc(e.message) + '</option>'; });
  }

  /* ---------- 変更要求 ---------- */
  function crs(el, ctx) {
    var cur = (new URLSearchParams(location.search)).get('status') || '';
    el.innerHTML = head('変更要求', '起票して分析すると、影響・リスク・確かめるテストを示します。', ui.can(ctx.role, 'cr_write') ? '<button type="button" class="btn-primary" data-act="new-cr">変更要求を起票</button>' : '') +
      '<div class="fchips im-filter" role="group" aria-label="状態で絞り込む">' + [''].concat(Object.keys(ui.STATUS)).map(function (s) {
        return '<button type="button" class="fchip' + (s === cur ? ' on' : '') + '" aria-pressed="' + (s === cur) + '" data-st="' + s + '">' + (s ? ui.STATUS[s] : 'すべて') + '</button>'; }).join('') + '</div><div id="im-crs"></div>';
    on(el, '[data-act=new-cr]', function () { openCreateCr(ctx); });
    on(el, '[data-st]', function (b) {
      $$('[data-st]', el).forEach(function (x) { x.classList.toggle('on', x === b); x.setAttribute('aria-pressed', String(x === b)); });
      crTable($('#im-crs', el), ctx, b.dataset.st, 0);
    });
    crTable($('#im-crs', el), ctx, cur, 0);
  }
  function crTable(box, ctx, status, limit) {
    ui.loading(box);
    api.crs(ctx.sid, status).then(function (d) {
      var rows = api.list(d, 'crs');
      if (limit) rows = rows.slice(0, limit);
      if (!rows.length) { box.innerHTML = ui.empty({ title: status ? 'この状態の変更要求はありません' : 'まだ変更要求がありません', desc: '題名・理由・変更内容を入れて起票し、「分析する」を押します。' }); return; }
      box.innerHTML = table(['ID', '題名', '状態', '影響', 'P1', '起票'], rows.map(function (r) {
        var s = r.summary || {};
        return '<tr><td><button type="button" class="im-link" data-cr="' + esc(r.code) + '">' + esc(r.code) + '</button></td><td>' + esc(r.title) + (r.source && r.source.kind === 'docverify' ? ' <span class="im-recv">' + esc(r.source.label) + '</span>' : '') + '</td><td>' + ui.statusBadge(r.status, r) + '</td>' +
          '<td class="num">' + num(s.total) + '</td><td class="num">' + num(s.p1) + '</td><td>' + ui.fmtDate(r.created_at) + ' ' + esc(r.created_by || '') + '</td></tr>'; }), '変更要求');
      on(box, '[data-cr]', function (b) { IM.app.go({ sid: ctx.sid, cr: b.dataset.cr }); });
    }, function (e) { ui.failed(box, e, function () { crTable(box, ctx, status, limit); }); });
  }
  function openCreateCr(ctx) {
    var depth = ctx.system.depth_default || 2;
    ui.modal({ title: '変更要求を起票', submit: '起票する',
      body: '<label class="bt-field">題名<input name="title" maxlength="200" required placeholder="例: 電話番号を必須にする"></label>' +
        '<label class="bt-field">理由<textarea name="reason" rows="2" maxlength="1000" class="im-ta" required></textarea></label>' +
        '<fieldset class="im-radios"><legend>変更内容の入れ方</legend><label><input type="radio" name="mode" value="text" checked> 文章で書く</label><label><input type="radio" name="mode" value="bl"> 変更前後のベースラインを選ぶ</label></fieldset>' +
        '<label class="bt-field" data-mode="text">変更内容<textarea name="change_text" rows="4" maxlength="5000" class="im-ta" placeholder="1 文 1 変更で書くと変更箇所に分けやすくなります。"></textarea></label>' +
        '<div class="im-row" data-mode="bl" hidden><label class="bt-field">変更前<select name="base"></select></label><label class="bt-field">変更後<select name="target"></select></label></div>' +
        '<label class="bt-field">波及の段数<select name="depth">' + [1, 2, 3].map(function (n) { return '<option value="' + n + '"' + (n === depth ? ' selected' : '') + '>' + n + ' 段</option>'; }).join('') + '</select></label>',
      onOpen: function (f) {
        var sync = function () { var m = f.mode.value; $$('[data-mode]', f).forEach(function (x) { x.hidden = x.dataset.mode !== m; }); };
        $$('input[name=mode]', f).forEach(function (r) { r.addEventListener('change', sync); });
        api.baselines(ctx.sid).then(function (d) {
          var o = api.list(d, 'baselines').map(function (b) { return '<option value="' + esc(b.id) + '">' + esc(b.name) + '</option>'; }).join('');
          f.base.innerHTML = o || '<option value="">ベースラインがありません</option>'; f.target.innerHTML = f.base.innerHTML;
        }, function () { f.base.innerHTML = '<option value="">読み込めませんでした</option>'; });
      },
      onSubmit: function (f) {
        var body = { title: ui.need(f.title.value, '題名'), reason: ui.need(f.reason.value, '理由'), depth: Number(f.depth.value), change_text: '', base_baseline: null, target_baseline: null };
        if (f.mode.value === 'text') body.change_text = ui.need(f.change_text.value, '変更内容');
        else {
          if (!f.base.value || !f.target.value || f.base.value === f.target.value) throw new Error('変更前と変更後に違うベースラインを選んでください。');
          body.base_baseline = f.base.value; body.target_baseline = f.target.value;
        }
        return api.createCr(ctx.sid, body).then(function (d) { var cr = api.obj(d, 'cr'); ui.toast(cr.code + ' を起票しました'); IM.app.go({ sid: ctx.sid, cr: cr.code }); });
      } });
  }

  /* ---------- 設定 ---------- */
  function pct(v) { return v === null || v === undefined ? '未計測' : esc(Math.round(Number(v) * 100)) + '%'; }
  function settings(el, ctx) {
    var s = ctx.system, edit = ui.can(ctx.role, 'edit_system'), dis = edit ? '' : ' disabled';
    el.innerHTML = head('設定', edit ? '' : '設定を変更できるのは管理者だけです。', '') + '<form class="bt-card im-form" id="im-setf">' +
      '<label class="bt-field">名前<input name="name" maxlength="100" value="' + esc(s.name) + '"' + dis + '></label>' +
      '<label class="bt-field">説明<textarea name="description" rows="2" class="im-ta"' + dis + '>' + esc(s.description || '') + '</textarea></label>' +
      '<fieldset class="im-radios"><legend>LLM への送信方針</legend>' + Object.keys(ui.POLICY).map(function (k) {
        return '<label><input type="radio" name="policy" value="' + k + '"' + (k === (s.policy || 'none') ? ' checked' : '') + dis + '> ' + ui.POLICY[k] + '</label>'; }).join('') + '</fieldset>' +
      '<div class="im-row"><label class="bt-field">P1 の下限リスク値<input type="number" name="p1_min" min="1" max="12" value="' + esc(s.p1_min || 10) + '"' + dis + '></label>' +
      '<label class="bt-field">P2 の下限リスク値<input type="number" name="p2_min" min="1" max="12" value="' + esc(s.p2_min || 6) + '"' + dis + '></label>' +
      '<label class="bt-field">既定の波及段数<select name="depth_default"' + dis + '>' + [1, 2, 3].map(function (n) { return '<option' + (n === (s.depth_default || 2) ? ' selected' : '') + '>' + n + '</option>'; }).join('') + '</select></label></div>' +
      '<p class="bt-hint">縮退時（LLM・埋め込みなし）の精度: 再現率 ' + pct(s.degraded_recall) + ' ・ 適合率 ' + pct(s.degraded_precision) + '</p>' +
      '<p class="bt-hint">コード依存のサイト: ' + (s.code_site ? esc(s.code_site) + '（人が関連付け）' : '未設定（自動では関連付けません）') + '。関連付けと解除は「コード依存」で行います。</p>' +
      (edit ? '<div class="bt-actions"><span class="sp"></span><button type="submit" class="btn-primary">保存する</button></div>' : '') + '</form>' +
      (edit ? '<div class="bt-card im-danger"><h3>対象システムを削除</h3><p class="bt-hint">文書・ベースライン・変更要求をすべて削除します。監査ログは残ります。</p><button type="button" class="btn-outline-sm im-btn-danger" data-act="del-sys">削除する</button></div>' : '');
    if (!edit) return;
    $('#im-setf', el).addEventListener('submit', function (e) {
      e.preventDefault(); var f = e.target, btn = $('[type=submit]', f);
      var p1 = Number(f.p1_min.value), p2 = Number(f.p2_min.value);
      if (p2 > p1) { ui.banner('P2 の下限は P1 の下限以下にしてください。'); return; }
      btn.disabled = true;
      api.updateSystem(ctx.sid, { name: f.name.value.trim(), description: f.description.value.trim(), policy: f.policy.value, p1_min: p1, p2_min: p2, depth_default: Number(f.depth_default.value) })
        .then(function () { ui.toast('設定を保存しました'); return IM.app.refreshSystem(); }).then(rerender, function (er) { btn.disabled = false; ui.banner(er.message); });
    });
    on(el, '[data-act=del-sys]', function (b) {
      ui.confirm({ title: '対象システムを削除', message: '「' + s.name + '」を削除します。元に戻せません。', submit: '削除する' })
        .then(function () { b.disabled = true; return api.deleteSystem(ctx.sid); }).then(function () { ui.toast('削除しました'); IM.app.go({}); }, function (e) { b.disabled = false; ui.banner(e.message); });
    });
  }

  /* ---------- メンバー ---------- */
  function roleSel(name, cur, label) {
    return '<select name="' + name + '" aria-label="' + esc(label) + '">' + Object.keys(ui.ROLE).map(function (k) { return '<option value="' + k + '"' + (k === cur ? ' selected' : '') + '>' + ui.ROLE[k] + '</option>'; }).join('') + '</select>';
  }
  function members(el, ctx) {
    var edit = ui.can(ctx.role, 'members');
    el.innerHTML = head('メンバー', '役割ごとにできる操作が決まります。詳しくはガイドの「役割」を見てください。', '') +
      (edit ? '<form class="bt-card im-row" id="im-memf"><label class="bt-field">利用者<input name="actor" required maxlength="200" placeholder="ログイン ID かメールアドレス"></label>' +
        '<label class="bt-field">役割' + roleSel('role', 'analyst', '役割') + '</label><button type="submit" class="btn-primary">役割を付与</button></form>' : '') + '<div id="im-mems"></div>';
    var box = $('#im-mems', el); ui.loading(box);
    if (edit) $('#im-memf', el).addEventListener('submit', function (e) {
      e.preventDefault(); var f = e.target, a = f.actor.value.trim();
      if (!a) { ui.banner('利用者を入力してください。'); return; }
      act($('[type=submit]', f), api.setMember(ctx.sid, a, f.role.value), '役割を付与しました');
    });
    api.members(ctx.sid).then(function (d) {
      var rows = api.list(d, 'members');
      box.innerHTML = table(['利用者', '役割', '<span class="visually-hidden">操作</span>'], rows.map(function (m) {
        return '<tr><td>' + esc(m.actor) + '</td><td>' + (edit ? roleSel('r', m.role, m.actor + ' の役割').replace('<select', '<select data-actor="' + esc(m.actor) + '"') : esc(ui.ROLE[m.role] || m.role)) + '</td>' +
          '<td>' + (edit ? '<button type="button" class="bt-x" data-rm="' + esc(m.actor) + '" aria-label="' + esc(m.actor) + ' を外す">外す</button>' : '') + '</td></tr>'; }), 'メンバー');
      $$('select[data-actor]', box).forEach(function (s) { s.addEventListener('change', function () { api.setMember(ctx.sid, s.dataset.actor, s.value).then(function () { ui.toast('役割を変更しました'); }, function (e) { ui.banner(e.message); }); }); });
      on(box, '[data-rm]', function (b) { ui.confirm({ title: 'メンバーから外す', message: b.dataset.rm + ' をこの対象システムのメンバーから外します。', submit: '外す' }).then(function () { act(b, api.removeMember(ctx.sid, b.dataset.rm), '外しました'); }); });
    }, function (e) { ui.failed(box, e, rerender); });
  }

  /* ---------- 監査 ---------- */
  function audit(el, ctx) {
    if (!ui.can(ctx.role, 'audit_view')) { el.innerHTML = head('監査', '', '') + '<div class="im-state im-state-ng" role="alert"><b>監査ログを見る権限がありません</b><p>管理者か承認者の役割が必要です。管理者に依頼してください。</p></div>'; return; }
    el.innerHTML = head('監査', '状態の変更・解消・承認・設定変更・LLM への送信を記録しています（追記のみ）。', '<a class="btn-outline-sm" id="im-csv" download>CSV で書き出す</a>') +
      '<form class="bt-card im-row" id="im-audf"><label class="bt-field">開始日<input type="date" name="since"></label><label class="bt-field">終了日<input type="date" name="until"></label>' +
      '<label class="bt-field">操作者<input name="actor" maxlength="200"></label><label class="bt-field">変更要求<input name="cr" maxlength="20" placeholder="CR-001"></label><button type="submit" class="btn-outline-sm">絞り込む</button></form><div id="im-aud"></div>';
    var f = $('#im-audf', el), box = $('#im-aud', el);
    var run = function () {
      var q = { since: f.since.value, until: f.until.value, actor: f.actor.value.trim(), cr: f.cr.value.trim() };
      $('#im-csv', el).href = api.auditCsvUrl(ctx.sid, q);
      ui.loading(box);
      api.audit(ctx.sid, q).then(function (d) {
        var rows = api.list(d, 'audit');
        box.innerHTML = rows.length ? table(['日時', '操作者', '操作', '対象', '変更要求', '変更前', '変更後'], rows.map(function (a) {
          return '<tr><td>' + ui.fmtDate(a.at) + '</td><td>' + esc(a.actor) + '</td><td>' + esc(ACTION[a.action] || a.action) + '</td><td>' + esc(a.target || '') + '</td><td>' + esc(a.cr_code || a.cr_id || '') + '</td>' +
            '<td class="im-clip">' + esc(fmtVal(a.before)) + '</td><td class="im-clip">' + esc(fmtVal(a.after)) + '</td></tr>'; }), '監査ログ') : '<p class="bt-hint">条件に合う記録はありません。</p>';
      }, function (e) { ui.failed(box, e, run); });
    };
    f.addEventListener('submit', function (e) { e.preventDefault(); run(); });
    run();
  }

  function rea(el, ctx) { IM.rea.render(el, ctx); }
  var VIEWS = { overview: overview, rea: rea, docs: docs, baselines: baselines, links: links, crs: crs, settings: settings, members: members, audit: audit };
  function render(root, ctx) {
    var tab = VIEWS[ctx.tab] ? ctx.tab : 'overview';
    ui.setTitle(ctx.system.name, TITLE[tab]);
    root.innerHTML = '<div class="im-view" id="im-sysview"></div>';
    VIEWS[tab]($('#im-sysview', root), Object.assign({}, ctx, { tab: tab }));
  }
  IM.system = { render: render, openCreateCr: openCreateCr };
})();
