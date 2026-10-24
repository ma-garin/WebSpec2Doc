/* ドキュメント検証 v2: レビューの中の画面（plan, read, triage, questions, followup, screen, gate）。
 * 土台は docverify-core.js の window.DV。API の値は DV.esc か textContent で入れる。 */
(function () {
  // ISO/IEC/IEEE 29148 の品質特性（チェックリスト項目 id → 画面の表示名）
  var CK_LABEL = { necessary: '必要', unambiguous: '曖昧でない', complete: '完全', consistent: '一貫', feasible: '実現可能', verifiable: '検証可能', traceable: '追跡可能', singular: '単一' };
  'use strict';

  var PHASES = [
    ['plan', '計画'], ['individual', '個別レビュー'], ['triage', '指摘の検討'],
    ['rework', '修正'], ['followup', '修正版の確認'], ['closed', '判定と記録']
  ];
  var SEV = { critical: '重大', major: '主要', minor: '軽微', warning: '主要', info: '軽微' };
  var SEV_CLS = { critical: 'c-crit', major: 'c-maj', minor: 'c-min' };
  var STATUS = { candidate: '未検討', adopted: '未対応', fixed: '修正済', verified: '確認済', rejected: '却下' };
  var ROLES = { author: '作成者', moderator: '司会', reviewer: 'レビュアー', approver: '承認者', scribe: '記録者' };
  var DEFAULT_TYPES = ['曖昧さ', '完全性', '一貫性', '検証可能性', '実現可能性', '追跡可能性', '誤記'];

  var cache = { settings: null, checklists: null };
  var ui = { tab: 'mine', selLine: null };

  function E() { return window.DV; }
  function esc(s) { return E().esc(s == null ? '' : String(s)); }
  function sev(s) { return SEV[s] ? (s === 'warning' ? 'major' : s === 'info' ? 'minor' : s) : 'minor'; }
  function rv() { return E().state.review; }
  // サーバが返した役割判定。無いとき（旧応答）は押せる扱いにし、押した結果の 403 は従来どおり日本語で出る
  function can(op) { var c = E().state.can; return !c || c[op] !== false; }
  var NO_ROLE_HINT = 'この操作には議長・レビュアー・記録者の役割が必要です。議長（またはテナント管理者）に参加者へ追加してもらってください。';
  function base() { return '/api/docverify/inspections/' + encodeURIComponent(rv().id); }
  function sect(view) { return document.querySelector('.dvr-view[data-view="' + view + '"]'); }
  function part(view, name) { return sect(view).querySelector('[data-dvr-' + name + ']'); }
  function json(method, body) {
    return { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) };
  }
  function errText(e) { return (e && (e.error || e.message)) || '処理に失敗しました。もう一度試してください。'; }

  function msg(view, text, isErr) {
    var m = part(view, 'msg');
    m.textContent = text || '';
    m.className = 'dvr-msg' + (isErr ? ' err' : '');
    // 同じ文を画面上部の帯にも出すと 2 重になる。この画面内の表示を正とする
    if (isErr && text && window.DV && typeof window.DV.banner === 'function') window.DV.banner('');
  }
  function loading(view) { part(view, 'body').innerHTML = '<div class="dvr-empty">読み込み中…</div>'; msg(view, ''); }
  function failed(view, e) {
    part(view, 'body').innerHTML = '<div class="dvr-empty">表示できませんでした。再読み込みしてください。</div>';
    msg(view, errText(e), true);
  }
  function empty(text) { return '<div class="dvr-empty">' + esc(text) + '</div>'; }

  /* 二重送信防止つきで実行（DV.busy へ委ねる） */
  function busy(btn, p, label) {
    if (!btn) return Promise.resolve(typeof p === 'function' ? p() : p);
    return E().busy(btn, p, label || btn.textContent);
  }

  /* ---------- 文書の帯・スコア・版・検査範囲（FR-06-015・075・100〜104） ---------- */
  var CK_ORDER = Object.keys(CK_LABEL);
  function qItems(q) {
    var items = (q && q.items) || {};
    var keys = CK_ORDER.filter(function (k) { return items[k]; });
    Object.keys(items).forEach(function (k) { if (keys.indexOf(k) < 0) keys.push(k); });
    return keys.map(function (k) { return { key: k, label: items[k].label || CK_LABEL[k] || k, score: items[k].score, open: items[k].open }; });
  }
  function helpBtn() { return '<button type="button" class="dv-link" data-act="score-help">スコアの意味</button>'; }
  function docBand(r, s) {
    var d = (r && r.document) || {}, lines = (s && s.unread_lines) || [];
    var n = d.passages != null ? d.passages : ((r && r.passages) || []).length;
    var unread = lines.map(function (x) {
      return '<span' + (String(x).indexOf('読んでいません') >= 0 ? ' class="is-warn"' : '') + '>' + esc(x) + '</span>';
    }).join('<br>');
    return '<div class="dvr-docband"><strong class="dv-ellipsis" title="' + esc(d.name) + '">' + esc(d.name) + '</strong>' +
      '<span class="chip">' + esc(d.format) + '</span><span>' + esc(n) + ' 断片</span><span>版 ' + esc(d.version) + '</span>' +
      (lines.length ? '<p class="dv-unread">' + unread + '</p>' : '') + '</div>';
  }
  function scoreBand(q) {
    if (!q || q.overall == null) return '<div class="dv-scoreband"><p>' + esc(E().NO_SCORE) + '</p></div>';
    return '<div class="dv-scoreband"><div class="dv-score-big"><span class="dv-score-cap">自動検出のみ・網羅性は未検証</span> ' + esc(E().scoreText(q.overall)) + '</div><ul class="dv-mini">' +
      qItems(q).map(function (it) { return '<li><span class="dv-ellipsis">' + esc(it.label) + '</span>' + E().scoreBar(it.score, it.label) + '</li>'; }).join('') +
      '</ul>' + helpBtn() + '</div>';
  }
  function qualityTable(q) {
    var none = !q || q.overall == null;
    return '<div class="dvr-quality">' + (none ? '<p class="role">' + esc(E().NO_SCORE) + '</p>' :
      '<div class="dv-score-total"><span>総合</span><b>' + esc(E().scoreText(q.overall)) + '</b></div>') +
      '<table class="dv-t"><thead><tr><th>特性</th><th>スコア</th><th>未解決</th></tr></thead><tbody>' +
      qItems(q).map(function (it) {
        return '<tr><td>' + esc(it.label) + '</td><td>' + E().scoreBar(it.score, it.label) + ' <b>' + esc(E().scoreText(it.score)) + '</b></td><td class="num">' + esc(it.open != null ? it.open : '—') + '</td></tr>';
      }).join('') + '</tbody></table>' + helpBtn() + '</div>';
  }
  function historyTable(h) {
    if (!h || !h.length) return '<div class="dvr-history">' + empty('まだ版がありません。文書を取り込むと記録されます。') + '</div>';
    return '<div class="dvr-history"><table class="dv-t"><thead><tr><th>版</th><th>文書名</th><th>取り込み日</th><th>総合</th><th>状態</th></tr></thead><tbody>' +
      h.map(function (v) {
        var st = v.current ? '現在' : (v.final ? '確定' : '');
        return '<tr><td>' + esc(v.version) + '</td><td><span class="dv-ellipsis" title="' + esc(v.name) + '">' + esc(v.name) + '</span></td><td>' +
          esc(String(v.uploaded_at || '').slice(0, 10)) + '</td><td>' + esc(E().scoreText(v.overall)) + '</td><td>' + esc(st) + '</td></tr>';
      }).join('') + '</tbody></table></div>';
  }
  function scopeValue(v) {
    var t = String(v == null ? '' : v), m = /^(未検証|未測定)/.exec(t);
    return m ? '<span class="dv-unverified">' + esc(m[1]) + '</span>' + esc(t.slice(m[1].length)) : esc(t);
  }
  function scopeRows(rows) {
    return '<table class="dv-t"><thead><tr><th>項目</th><th>内容</th></tr></thead><tbody>' + (rows || []).map(function (x) {
      return '<tr><td>' + esc(x.label) + '</td><td>' + scopeValue(x.value) + '</td></tr>';
    }).join('') + '</tbody></table>';
  }
  function scopeTables(sc) {
    sc = sc || {};
    return '<div class="dvr-scope"><h3>検査した範囲</h3>' + scopeRows(sc.checked) + '<h3>検査していないこと</h3>' + scopeRows(sc.unchecked) + '<p class="mut">自動検出の規則ごとの精度は <a href="#accuracy">精度ページ</a> にあります。</p></div>';
  }
  function showScoreHelp(q) {
    var note = (q && q.note) || [];
    return E().modal({ title: 'スコアの意味', html: note.map(function (x) { return '<p>' + esc(x) + '</p>'; }).join(''), ok: null, cancel: '閉じる' });
  }
  function confirmClose() {
    return E().modal({ title: 'レビューを終えますか', html: '<p>' + esc('終えると判定と記録が確定します。指摘の状態はこのあとも変えられます。') + '</p>', ok: '終える', cancel: '取りやめる' });
  }
  function scoreHelpClicked(ev) {
    if (!ev.target.closest('[data-act="score-help"]')) return false;
    showScoreHelp((E().state.summary || {}).quality);
    return true;
  }

  function setReview(d) {
    if (d && d.inspection) { E().state.review = d.inspection; }
    if (d && d.summary) { E().state.summary = d.summary; }
    if (d && d.can) { E().state.can = d.can; }
    return d;
  }
  function reload() { return E().api(base()).then(setReview); }
  function settings() {
    if (cache.settings) return Promise.resolve(cache.settings);
    return E().api('/api/docverify/settings').then(function (s) { cache.settings = s || {}; return cache.settings; });
  }
  function checklists() {
    if (cache.checklists) return Promise.resolve(cache.checklists);
    return E().api('/api/docverify/checklists').then(function (d) {
      cache.checklists = Array.isArray(d) ? d : (d && d.checklists) || [];
      return cache.checklists;
    });
  }
  function currentChecklist(lists) {
    var id = rv().checklist_id;
    for (var i = 0; i < lists.length; i++) if (lists[i].id === id) return lists[i];
    return null;
  }
  function me() { var s = cache.settings || {}; return s.me || (s.settings && s.settings.me) || 'ゲスト'; }  // API は {settings:{me}} で返る
  function myRole() {
    var ps = rv().participants || [];
    for (var i = 0; i < ps.length; i++) if (ps[i].name === me()) return ps[i];
    return null;
  }
  function upload(path, file) {
    var fd = new FormData();
    fd.append('file', file);
    return E().api(path, { method: 'POST', body: fd });
  }
  function setFinding(fid, body) {
    return E().api(base() + '/findings/' + encodeURIComponent(fid), json('POST', body)).then(setReview);
  }

  /* 工程表示（全画面共通） */
  function renderSteps(view) {
    var ph = rv().phase || 'plan', idx = 0;
    PHASES.forEach(function (p, i) { if (p[0] === ph) idx = i; });
    var ps = rv().participants || [];
    var revs = ps.filter(function (p) { return p.role === 'reviewer'; });
    var done = revs.filter(function (p) { return p.done; }).length;
    part(view, 'steps').innerHTML = PHASES.map(function (p, i) {
      var label = p[1];
      if (p[0] === 'individual' && revs.length) label += '（' + done + '/' + revs.length + ' 人）';
      if (i < idx || ph === 'closed') return '<span class="done">✓ ' + esc(label) + '</span>';
      if (i === idx) return '<span class="now">● ' + esc(label) + '</span>';
      return '<span>' + esc(label) + '</span>';
    }).join('');
  }

  /* 画面を開いたときの共通処理 */
  function open(view, render) {
    return function () {
      if (!rv()) { part(view, 'body').innerHTML = ''; r2State(view, 'empty', 'レビューが開かれていません。案件一覧から選んでください。'); return; }
      loading(view);
      r2State(view, 'loading', '読み込んでいます。');
      part(view, 'headright').innerHTML = '';
      Promise.all([reload(), settings()]).then(function () {
        renderSteps(view);
        return render(view);
      }).catch(function (e) { failed(view, e); r2State(view, 'error', errText(e)); });
    };
  }
  function rerender(view, render) { renderSteps(view); return render(view); }

  /* ---------- r3: 計画・文書を読む・質問票（対検査の API を使う） ---------- */
  var R2_ROLES = { author: '作成者', moderator: '司会', reviewer: 'レビュアー', approver: '承認者' };
  var R2_SEV = ['重大', '警告', '提案'];
  var R2_Q = ['未回答', '回答済み', '解消'];
  var r2 = { sel: null };
  function pbase() { return '/api/docverify/' + encodeURIComponent(rv().id) + '/pair'; }
  function r2State(view, st, text) {
    var el = sect(view) && sect(view).querySelector('[data-dvr-state]'); if (!el) return;
    el.hidden = !st; el.setAttribute('data-st', st || '');
    el.innerHTML = st ? '<span>' + esc(text) + '</span>' + (st === 'error' ? ' <button type="button" class="p1-btn" data-r2-retry>もう一度読み込む</button>' : '') : '';
    var b = el.querySelector('[data-r2-retry]'); if (b) b.onclick = function () { window.DV.show(view); };
  }
  function r2GateBox(label, g) {
    if (!g) return '<div class="p5-gate"><div class="lbl">' + esc(label) + '</div><div class="val">判定不能</div><div class="lbl">判定の材料がまだありません。</div></div>';
    var c = function (k) { return (g[k] || []).length; };
    return '<div class="p5-gate ' + (g.pass ? 'ok' : 'ng') + '"><div class="lbl">' + esc(label) + '</div><div class="val">' + (g.pass ? '合格' : '不合格') + '</div><div class="lbl">採用のまま残る重大 ' + c('unresolved_critical') + '・要確認 ' + c('needs_review') + '・対応の抜け ' + c('missing_links') + '</div></div>';
  }
  function r2Gate(view) {
    var el = sect(view) && sect(view).querySelector('[data-dvr-gate]'); if (!el || !rv()) return Promise.resolve();
    el.innerHTML = '<div class="p5-gates"><div class="p5-gate"><div class="lbl">判定</div><div class="val">読込中</div></div></div>';
    return E().api(pbase() + '/gate').then(function (g) {
      el.innerHTML = '<div class="p5-gates">' + r2GateBox('全体', g.overall) + r2GateBox('今回の変更分', g.changed) + '</div><p class="p5-why">' + esc((g.reasons || []).join(' ')) + '</p><button type="button" class="p1-btn" data-r2-pair>対検査で判定する</button>';
    }, function () {
      el.innerHTML = '<p class="p5-why">判定を読み込めませんでした。対検査を開いて、文書が取り込まれているか確かめてください。</p><button type="button" class="p1-btn" data-r2-pair>対検査を開く</button>';
    }).then(function () { var b = el.querySelector('[data-r2-pair]'); if (b) b.onclick = function () { window.DV.show('pair'); }; });
  }
  function bands(fn) {
    return function (view) {
      r2State(view, 'loading', '読み込んでいます。');
      return Promise.resolve().then(function () { return fn(view); }).then(function () {
        if (sect(view).querySelector('[data-dvr-state]').getAttribute('data-st') === 'loading') r2State(view, null);
        r2Gate(view);
      }, function (e) { part(view, 'body').innerHTML = ''; r2State(view, 'error', errText(e)); r2Gate(view); });
    };
  }

  function renderPlan2(view) {
    return Promise.all([E().api('/api/docverify/settings').catch(function () { return null; }), E().api(pbase() + '/docs').catch(function () { return null; })]).then(function (res) {
      var st = res[0], dd = res[1] || {}, r = rv(), ps = r.participants || [];
      var v = (st && (st.values || st.settings)) || {}, mo = (v.exit || {}).max_open || {};
      var lim = function (k, l) { return l + ' ' + (mo[k] == null ? '上限なし' : esc(mo[k]) + ' 件以下'); };
      var exitTxt = st ? '採用のまま残る ' + [lim('critical', '重大'), lim('major', '警告'), lim('minor', '提案')].join('・') : '出口基準を読み込めませんでした。設定を開いて確かめてください。';
      var who = function (k) { return ps.filter(function (p) { return p.role === k; }).map(function (p) { return p.name; }).join('、'); };
      var ver = function (label, d) { return '<li>' + label + ' ' + (d && d.version ? '第 ' + esc(d.version) + ' 版・章 ' + ((d.sections || []).length) + ' 件' : '<span class="r2-hint">まだ取り込んでいません</span>') + '</li>'; };
      part(view, 'body').innerHTML = '<div class="r2-card">' +
        '<div class="r2-row"><label class="r2-k" for="r2-goal">目的</label><input type="text" id="r2-goal" maxlength="200" value="' + esc(r.goal) + '" placeholder="例: 要件定義書と基本設計書の食い違いを出荷前に潰す"></div>' +
        '<div class="r2-row"><span class="r2-k">出口基準</span><div class="r2-v"><span>' + exitTxt + '</span> <button type="button" class="p1-btn" data-act="to-settings">設定で変える</button></div></div>' +
        '<div class="r2-row"><label class="r2-k" for="r2-due">期限</label><input type="date" id="r2-due" value="' + esc(r.due) + '"></div>' +
        '<div class="r2-row"><span class="r2-k">担当</span><div class="r2-roles">' + Object.keys(R2_ROLES).map(function (k) {
          return '<label class="r2-role"><span>' + R2_ROLES[k] + '</span><input type="text" data-role="' + k + '" value="' + esc(who(k)) + '" placeholder="名前（複数は「、」で区切る）"></label>'; }).join('') + '</div></div>' +
        '<div class="r2-row"><span class="r2-k">対象文書と版</span><ul class="r2-docs">' + ver('要件定義書', dd.requirements) + ver('基本設計書', dd.design) + '</ul></div>' +
        '<div class="r2-actions"><button type="button" class="p1-btn is-primary" data-act="save">計画を保存</button></div></div>';
      part(view, 'body').onclick = function (ev) {
        var b = ev.target.closest('[data-act]'); if (!b) return;
        if (b.getAttribute('data-act') === 'to-settings') { window.DV.show('settings'); return; }
        busy(b, savePlan2(view));
      };
    });
  }
  function savePlan2(view) {
    var body = part(view, 'body'), old = rv().participants || [], parts = old.filter(function (p) { return !R2_ROLES[p.role]; });
    body.querySelectorAll('[data-role]').forEach(function (inp) {
      var k = inp.getAttribute('data-role');
      inp.value.split(/[、,，]/).map(function (s) { return s.trim(); }).filter(Boolean).forEach(function (n) {
        var was = old.filter(function (p) { return p.role === k && p.name === n; })[0];
        parts.push({ name: n, role: k, done: !!(was && was.done) });
      });
    });
    var payload = { name: rv().name, goal: body.querySelector('#r2-goal').value.trim(), due: body.querySelector('#r2-due').value, participants: parts };
    return E().api(base(), json('PATCH', payload)).then(setReview).then(function () { E().toast('計画を保存しました'); msg(view, ''); })
      .catch(function (e) { msg(view, errText(e), true); });
  }

  function r2Doc(side, label, d) {
    var list = (d && d.sections) || [];
    return '<article class="p1-doc" aria-label="' + label + '"><header class="p1-doc-t">' + label + ' <span class="p1-doc-v">' + (d && d.version ? '第 ' + esc(d.version) + ' 版' : '') + '</span></header>' +
      '<div class="p1-doc-s" data-r2doc="' + side + '" tabindex="0">' + (list.length ? list.map(function (s) {
        return '<section class="p1-sec" data-sec-id="' + esc(s.id) + '"><h4 class="p1-doc-h">' + esc(s.heading || s.id) + '</h4><p class="p1-doc-b">' + esc(s.text) + '</p></section>'; }).join('')
        : '<p class="p1-empty">この文書には読める章がありません。修正版の確認で文書を取り込んでください。</p>') + '</div></article>';
  }
  function renderRead2(view) {
    return E().api(pbase() + '/docs').then(function (dd) {
      var n = ((dd.requirements || {}).sections || []).length + ((dd.design || {}).sections || []).length;
      r2.sel = null;
      part(view, 'body').innerHTML = '<div class="p1-pair r2-pair">' + r2Doc('req', '要件定義書', dd.requirements) + r2Doc('design', '基本設計書', dd.design) +
        '<aside class="p1-side r2-side" aria-label="指摘にする"><div class="r2-sec-t">選んだ本文</div><blockquote class="r2-quote" data-r2-quote>文書の本文をドラッグで選ぶと、ここに入ります。</blockquote>' +
        '<label class="r2-k" for="r2-title">指摘の内容</label><input type="text" id="r2-title" maxlength="80" placeholder="例: タイムアウトが要件60秒・設計30秒で食い違う">' +
        '<label class="r2-k" for="r2-sev">重大度</label><select id="r2-sev">' + R2_SEV.map(function (s) { return '<option' + (s === '警告' ? ' selected' : '') + '>' + s + '</option>'; }).join('') + '</select>' +
        '<div class="r2-actions"><button type="button" class="p1-btn is-primary" data-act="add" disabled>指摘にする</button></div>' +
        '<p class="r2-hint">採否（採用／不採用／要確認／解消済み）は対検査で決めます。</p></aside></div>';
      if (!n) r2State(view, 'empty', '読める文書がまだありません。修正版の確認で要件定義書と基本設計書を取り込んでください。');
      var body = part(view, 'body'), btn = body.querySelector('[data-act="add"]');
      body.onmouseup = function () {
        var s = window.getSelection(), t = s && String(s).trim();
        var node = s && s.anchorNode && (s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement);
        var box = node && node.closest('[data-r2doc]');
        if (!t || !box) return;
        var sec = node.closest('[data-sec-id]');
        r2.sel = { side: box.getAttribute('data-r2doc'), section: sec ? sec.getAttribute('data-sec-id') : '', quote: t.slice(0, 300) };
        body.querySelector('[data-r2-quote]').textContent = (r2.sel.side === 'req' ? '要件定義書' : '基本設計書') + '：' + r2.sel.quote;
        btn.disabled = false;
      };
      btn.onclick = function () {
        var title = body.querySelector('#r2-title').value.trim();
        if (!r2.sel) { msg(view, '先に文書の本文を選んでください。', true); return; }
        if (!title) { msg(view, '指摘の内容を書いてください。', true); return; }
        busy(btn, E().api(pbase() + '/findings', json('POST', { side: r2.sel.side, section: r2.sel.section, quote: r2.sel.quote, title: title, severity: body.querySelector('#r2-sev').value }))
          .then(function (d) { E().toast('指摘にしました'); msg(view, (d && d.finding ? d.finding.id + ' を登録しました。' : '') + '採否は対検査で決めます。'); body.querySelector('#r2-title').value = ''; r2Gate(view); })
          .catch(function (e) { msg(view, errText(e), true); }));
      };
    });
  }

  function renderQuestions2(view) {
    return Promise.all([E().api(pbase() + '/findings'), E().api(pbase() + '/questions')]).then(function (res) {
      var fs = (res[0] && res[0].findings) || [], qs = (res[1] && res[1].questions) || [], asked = {};
      qs.forEach(function (q) { asked[q.finding_id] = 1; });
      var cand = fs.filter(function (f) { return f.status === '要確認' && !asked[f.id]; });
      part(view, 'headright').innerHTML = '<a class="p1-btn" href="' + esc(base() + '/questions.csv') + '">CSV で出力</a>';
      var ask = '<div class="r2-card"><div class="r2-sec-t">要確認の指摘から質問を起こす（' + cand.length + ' 件）</div>' + (cand.length ? '<ul class="r2-list">' + cand.map(function (f) {
          return '<li><span class="r2-id">' + esc(f.id) + '</span><span class="r2-t">' + esc(f.title) + '</span><button type="button" class="p1-btn" data-ask="' + esc(f.id) + '">質問を起こす</button></li>'; }).join('') + '</ul>'
        : '<p class="r2-hint">要確認の指摘はありません。対検査で採否を「要確認」にすると、ここから質問を起こせます。</p>') + '</div>';
      var rows = qs.map(function (q) {
        return '<tr data-q="' + esc(q.id) + '"><td>' + esc(q.id) + '<div class="r2-hint">' + esc(q.finding_id) + '</div></td><td><textarea data-f="question" rows="2" maxlength="500">' + esc(q.question) + '</textarea></td>' +
          '<td><input type="text" data-f="to" maxlength="60" value="' + esc(q.to) + '" placeholder="宛先の名前"><input type="date" data-f="due" value="' + esc(q.due) + '"></td>' +
          '<td><textarea data-f="answer" rows="2" maxlength="1000" placeholder="回答を書く">' + esc(q.answer) + '</textarea></td>' +
          '<td><select data-f="state">' + R2_Q.map(function (s) { return '<option' + (s === q.state ? ' selected' : '') + '>' + s + '</option>'; }).join('') + '</select> <button type="button" class="p1-btn" data-save>保存</button></td></tr>'; }).join('');
      part(view, 'body').innerHTML = ask + '<div class="r2-card"><div class="r2-sec-t">質問（' + qs.length + ' 件）</div>' + (qs.length ? '<div class="r2-tbl"><table class="dv-t r2-q"><thead><tr><th>番号</th><th>質問</th><th>宛先・期限</th><th>回答</th><th>状態</th></tr></thead><tbody>' + rows + '</tbody></table></div>' : '') + '</div>';
      if (!qs.length) r2State(view, 'empty', '質問はまだありません。上の「質問を起こす」から作れます。');
      part(view, 'body').onclick = function (ev) {
        var a = ev.target.closest('[data-ask]'), s = ev.target.closest('[data-save]');
        if (a) {
          var f = fs.filter(function (x) { return x.id === a.getAttribute('data-ask'); })[0];
          busy(a, E().api(pbase() + '/questions', json('POST', { finding_id: f.id, question: f.title + ' について、意図を確認させてください。' }))
            .then(function () { E().toast('質問を起こしました'); return rerender(view, bands(renderQuestions2)); }).catch(function (e) { msg(view, errText(e), true); }));
        }
        if (s) {
          var tr = s.closest('[data-q]'), o = qs.filter(function (x) { return x.id === tr.getAttribute('data-q'); })[0], b = { id: o.id, finding_id: o.finding_id };
          tr.querySelectorAll('[data-f]').forEach(function (i) { b[i.getAttribute('data-f')] = i.value; });
          busy(s, E().api(pbase() + '/questions', json('POST', b)).then(function () { E().toast('保存しました'); msg(view, ''); }).catch(function (e) { msg(view, errText(e), true); }));
        }
      };
    });
  }

  /* ---------- 文書を読む ---------- */
  function hl(text, words) {
    var out = esc(text);
    words.forEach(function (w) { if (w) out = out.split(esc(w)).join('<mark>' + esc(w) + '</mark>'); });
    return out;
  }
  /* 指摘の根拠: 文書（本文の引用あり）／推論（引用なし）／未確認（作成者に質問中）を形＋文字で示し、詳細は WS2D.drawer に出す */
  function evCode(f) { return f.certainty === '要確認' ? 'unverified' : (f.quote ? 'document' : 'inferred'); }
  function evRow(f) {
    var ws = window.WS2D;
    if (!ws || !ws.evidence) return '';
    return '<span class="dv-evrow">' + ws.evidence.html(evCode(f)) + '<button type="button" class="dv-evbtn" data-ev-fid="' + esc(f.id) + '">根拠を見る</button></span>';
  }
  function openEvidence(fid, btn) {
    var f = ((rv() || {}).findings || []).filter(function (x) { return x.id === fid; })[0];
    if (!f || !window.WS2D || !WS2D.drawer) return;
    var code = evCode(f);
    var facts = [], inf = [], lim = [];
    if (f.quote) facts.push({ label: '本文の該当箇所', value: f.quote });
    if (f.origin === 'auto') inf.push('自動検出の規則による候補です。人が確かめるまで確定した指摘ではありません。');
    if (!f.quote) lim.push('本文の引用がありません。該当箇所を本文で確かめてください。');
    if (code === 'unverified') lim.push('作成者に質問中です。回答が届くまで未確認です。');
    var src = [{ label: '位置', value: f.location || '—' }];
    if (f.viewpoint) src.push({ label: '観点', value: f.viewpoint });
    src.push({ label: '起票', value: f.raised_by || (f.origin === 'auto' ? '自動候補' : '—') });
    WS2D.drawer.open({ title: '指摘 ' + f.id + ' の根拠', state: code, stateReason: { document: '本文の引用があります。', inferred: '本文の引用がなく、推論です。', unverified: '作成者への確認待ちです。' }[code], claim: f.message, facts: facts, inferences: inf, limitations: lim, sources: src, returnFocus: btn });
  }
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest && ev.target.closest('[data-ev-fid]');
    if (b) { ev.preventDefault(); openEvidence(b.getAttribute('data-ev-fid'), b); }
  });
  function findingCard(f, withActs) {
    var s = sev(f.severity);
    var acts = '';
    if (withActs && f.status === 'candidate' && !can('finding_edit')) {
      acts = '<div class="act role">指摘にする・却下するには役割が必要です（議長に参加者へ追加してもらってください）。</div>';
    } else if (withActs && f.status === 'candidate') {
      acts = '<div class="act"><button class="b p" data-fa="adopt" data-fid="' + esc(f.id) + '">指摘にする</button>' +
        '<button class="b" data-fa="reject" data-fid="' + esc(f.id) + '">却下</button>' +
        '<button class="b" data-fa="ask" data-fid="' + esc(f.id) + '">作成者に質問</button></div>';
    } else if (withActs && f.status !== 'rejected') {
      acts = '<div class="act"><button class="b" data-fa="ask" data-fid="' + esc(f.id) + '">作成者に質問</button></div>';
    }
    return '<div class="f"><div class="top"><span class="chip ' + SEV_CLS[s] + '">' + SEV[s] + '</span><b>' + esc(f.id) + '</b>' +
      (f.viewpoint ? '<span class="ck">観点: ' + esc(f.viewpoint) + '</span>' : '') +
      (f.checklist_item ? '<span class="chip c-auto">' + esc(CK_LABEL[f.checklist_item] || f.checklist_item) + '</span>' : '') +
      '<span class="loc">' + esc(f.location) + '</span>' + evRow(f) + '</div><div>' + esc(f.message) + '</div>' +
      '<div class="role">起票: ' + esc(f.raised_by || (f.origin === 'auto' ? '自動候補' : '')) + '・状態: ' + esc(STATUS[f.status] || f.status) +
      (f.certainty === '要確認' ? '・作成者に質問中' : '') + '</div>' + acts + '</div>';
  }
  /* ---------- 修正版の確認 ---------- */
  function diffText(x) { return typeof x === 'string' ? x : (x && (x.text || (x.new && x.new.text) || x.location)) || ''; }
  function renderFollowup(view) {
    var r = rv(), d = r.diff, fixed = (r.findings || []).filter(function (f) { return f.status === 'fixed'; });
    var diffHtml = !d ? empty('まだ新しい版を取り込んでいません。') :
      '<div class="dvr-kpi"><div>追加<b>' + (d.added || []).length + '</b></div><div>削除<b>' + (d.removed || []).length + '</b></div><div>変更<b>' + (d.changed || []).length + '</b></div></div>' +
      [['added', '追加'], ['removed', '削除'], ['changed', '変更']].map(function (k) {
        var xs = d[k[0]] || []; if (!xs.length) return '';
        return '<h3 style="font-size:13px">' + k[1] + '</h3>' + xs.map(function (x) { return '<div class="f">' + esc(diffText(x)) + '</div>'; }).join('');
      }).join('');
    part(view, 'body').innerHTML = '<div class="dv-panel" style="margin:0 0 12px">現在 第 ' + esc(r.document ? r.document.version : '-') + ' 版。新しい版: <input type="file" accept=".txt,.md,.docx,.xlsx,.pdf" data-file> <button type="button" class="b p" data-act="up">新しい版を取り込む</button></div>' +
      '<div class="wrap"><section class="card"><h3>版の差分</h3><div class="dvr-scroll" style="padding:10px 14px">' + diffHtml + '</div></section>' +
      '<section class="card"><h3>修正済みの指摘の確認 <span class="role">' + fixed.length + ' 件</span></h3><div class="dvr-scroll">' +
      (fixed.length ? fixed.map(function (f) {
        return findingCard(f, false).replace(/<\/div>$/, '<div class="act"><button class="b p" data-ok="' + esc(f.id) + '">確認済にする</button><button class="b" data-ng="' + esc(f.id) + '">未対応に戻す</button></div></div>');
      }).join('') : empty('確認待ちの修正済み指摘はありません。')) + '</div></section></div>';
    part(view, 'body').onclick = function (ev) {
      var b = ev.target.closest('button'); if (!b) return;
      if (b.getAttribute('data-act') === 'up') {
        var f = part(view, 'body').querySelector('[data-file]').files[0];
        if (!f) { msg(view, '取り込むファイルを選んでください。', true); return; }
        msg(view, '取り込み中…');
        return busy(b, upload(base() + '/document', f).then(setReview).then(function () { msg(view, '新しい版を取り込みました。'); return rerender(view, renderFollowup); })
          .catch(function (e) { msg(view, errText(e), true); }));
      }
      var id = b.getAttribute('data-ok') || b.getAttribute('data-ng'); if (!id) return;
      busy(b, setFinding(id, { status: b.getAttribute('data-ok') ? 'verified' : 'adopted' }).then(function () { return rerender(view, renderFollowup); })
        .catch(function (e) { msg(view, errText(e), true); }));
    };
    return Promise.resolve();
  }

  /* ---------- 実画面との照合 ---------- */
  function renderScreen(view) {
    return E().api('/api/docverify/domains').then(function (d) {
      var ds = (d && d.domains) || [];
      var hits = (rv().findings || []).filter(function (f) { return f.viewpoint === '実画面との食い違い'; });
      if (!ds.length) { part(view, 'body').innerHTML = empty('巡回済みのサイトがありません。まず System 01 で対象サイトを巡回してください。'); return; }
      part(view, 'body').innerHTML = '<div class="dv-panel" style="margin:0 0 12px">照合するサイト: <select data-dom>' +
        ds.map(function (x) { return '<option>' + esc(x) + '</option>'; }).join('') + '</select> <button type="button" class="b p" data-act="m">照合する</button></div>' +
        (hits.length ? hits.map(function (f) { return findingCard(f, false); }).join('') : empty('照合の結果はまだありません。'));
      part(view, 'body').querySelector('[data-act="m"]').onclick = function () {
        var b = this; msg(view, '照合中…');
        busy(b, E().api(base() + '/match', json('POST', { domain: part(view, 'body').querySelector('[data-dom]').value })).then(setReview)
          .then(function () { return rerender(view, renderScreen); }).then(function () { msg(view, '照合しました。候補は文書を読む画面で指摘にするか却下してください。'); })
          .catch(function (e) { msg(view, errText(e), true); }));
      };
    });
  }

  /* ---------- 判定と記録 ---------- */
  function renderGate(view) {
    var s = E().state.summary || {}, r = rv(), ap = r.approval || {};
    var reasons = s.reasons || [];
    part(view, 'headright').innerHTML = '<button type="button" class="b" data-act="report">報告を Excel で出力</button>';
    part(view, 'headright').onclick = function (ev) {
      var b = ev.target.closest('[data-act="report"]'); if (!b) return;
      E().busy(b, function () { return E().download(base() + '/report.xlsx', 'inspection-' + rv().id + '.xlsx'); }, '報告を作成中…');
    };
    part(view, 'body').innerHTML =
      '<div class="dvr-kpi"><div>未対応の重大<b>' + esc(s.open_critical != null ? s.open_critical : '-') + '</b></div><div>未対応の主要<b>' + esc(s.open_warning != null ? s.open_warning : '-') + '</b></div>' +
      '<div>指摘密度（1 文あたり）<b>' + esc(s.density != null ? Number(s.density).toFixed(2) : '-') + '</b></div>' +
      '<div>出口基準<b class="' + (s.exit_ok ? 'dv-ok' : 'dv-err-text') + '">' + (s.exit_ok ? '満たす' : '満たさない') + '</b></div></div>' +
      qualityTable(s.quality) + historyTable(s.history) +
      '<div class="dv-panel dvr-gap' + (s.exit_ok ? '' : ' dv-err') + '"><b>判定の理由</b>' +
      (reasons.length ? '<ul>' + reasons.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '<div class="role">理由はありません。</div>') + '</div>' +
      scopeTables(s.scope) +
      '<div class="dv-panel dvr-gap"><b>承認</b><div class="role">承認者が自分で名前と日付を記入します。</div><div class="dvr-form dvr-gap">' +
      '<label for="dvr-apn">承認者名</label><input type="text" id="dvr-apn" value="' + esc(ap.approver || '') + '">' +
      '<label for="dvr-apd">承認日</label><input type="date" id="dvr-apd" value="' + esc((ap.decided_at || '').slice(0, 10)) + '"></div>' +
      '<div class="dvr-actions"><button type="button" class="b" data-act="ap"' + (can('approve') ? '' : ' disabled title="承認欄は承認者だけが記入できます"') + '>承認欄を保存</button></div></div>' +
      '<div class="dvr-actions"><button type="button" class="b p" data-act="close"' + (r.status === 'closed' ? ' disabled' : (can('plan_edit') ? '' : ' disabled title="レビューを終えられるのは議長（またはテナント管理者）です"')) + '>' + (r.status === 'closed' ? '終了しています' : 'レビューを終える') + '</button></div>';
    part(view, 'body').onclick = function (ev) {
      if (scoreHelpClicked(ev)) return;
      var b = ev.target.closest('[data-act]'); if (!b) return;
      if (b.getAttribute('data-act') === 'ap') {
        var n = part(view, 'body').querySelector('#dvr-apn').value.trim(), dt = part(view, 'body').querySelector('#dvr-apd').value;
        if (!n || !dt) { msg(view, '承認者名と承認日を入れてください。', true); return; }
        return busy(b, E().api(base(), json('PATCH', { approval: { approver: n, decided_at: dt } })).then(setReview)
          .then(function () { E().toast('承認欄を保存しました'); return rerender(view, renderGate); }).catch(function (e) { msg(view, errText(e), true); }));
      }
      if (b.getAttribute('data-act') !== 'close') return;
      return confirmClose().then(function (ok) {
        if (!ok) return;
        return busy(b, function () { return closeReview(view); });
      });
    };
    return Promise.resolve();
  }

  function closeReview(view) {
    return E().api(base() + '/close', { method: 'POST' }).then(function () { return reload(); })
      .then(function () { E().toast('レビューを終えました'); return rerender(view, renderGate); })
      .catch(function (e) {
        return reload().then(function () { return rerender(view, renderGate); }).then(function () {
          msg(view, errText(e) + (e && e.reasons ? ' ' + e.reasons.join('／') : ''), true);
        });
      });
  }

  // 指摘の採否は対検査で決める（同じ機能を 2 か所に置かない・S06 r2）
  function toPair(view) {
    var b = sect(view).querySelector('[data-dvr-body]');
    b.innerHTML = '<p class="dvr-redirect">指摘の採否（採用／不採用／要確認／解消済み）は対検査で決めます。 <button type="button" class="b p" data-go-pair>対検査を開く</button></p>';
    b.querySelector('[data-go-pair]').addEventListener('click', function () { window.DV.show('pair'); });
    return Promise.resolve();
  }

  function init() {
    if (!window.DV || !window.DV.on) { setTimeout(init, 30); return; }
    var map = { plan: bands(renderPlan2), read: bands(renderRead2), triage: bands(toPair), questions: bands(renderQuestions2), followup: bands(renderFollowup), screen: renderScreen };
    Object.keys(map).forEach(function (v) { if (sect(v)) window.DV.on(v, open(v, map[v])); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
