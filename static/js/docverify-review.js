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
  var ROLES = { author: '作成者', moderator: '司会', reviewer: 'レビュアー', approver: '承認者' };
  var DEFAULT_TYPES = ['曖昧さ', '完全性', '一貫性', '検証可能性', '実現可能性', '追跡可能性', '誤記'];

  var cache = { settings: null, checklists: null };
  var ui = { tab: 'mine', selLine: null };

  function E() { return window.DV; }
  function esc(s) { return E().esc(s == null ? '' : String(s)); }
  function sev(s) { return SEV[s] ? (s === 'warning' ? 'major' : s === 'info' ? 'minor' : s) : 'minor'; }
  function rv() { return E().state.review; }
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
    return '<div class="dv-scoreband"><div class="dv-score-big">' + esc(E().scoreText(q.overall)) + '</div><ul class="dv-mini">' +
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
  function me() { return (cache.settings && cache.settings.me) || 'ゲスト'; }
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
      if (!rv()) { part(view, 'body').innerHTML = empty('レビューが開かれていません。レビュー一覧から選んでください。'); return; }
      loading(view);
      part(view, 'headright').innerHTML = '';
      Promise.all([reload(), settings()]).then(function () {
        renderSteps(view);
        return render(view);
      }).catch(function (e) { failed(view, e); });
    };
  }
  function rerender(view, render) { renderSteps(view); return render(view); }

  /* ---------- 計画 ---------- */
  function renderPlan(view) {
    return checklists().then(function (lists) {
      var r = rv(), ec = r.exit_criteria || {}, doc = r.document;
      var opts = '<option value="">選ばない</option>' + lists.map(function (c) {
        return '<option value="' + esc(c.id) + '"' + (c.id === r.checklist_id ? ' selected' : '') + '>' + esc(c.name) + '</option>';
      }).join('');
      part(view, 'body').innerHTML =
        '<div class="dvr-form">' +
        '<label for="dvr-name">名前</label><input type="text" id="dvr-name" value="' + esc(r.name) + '">' +
        '<label for="dvr-goal">目的</label><input type="text" id="dvr-goal" value="' + esc(r.goal) + '">' +
        '<label for="dvr-due">期限</label><input type="date" id="dvr-due" value="' + esc(r.due) + '">' +
        '<span>参加者と役割</span><div><div data-plist></div><button type="button" class="b" data-act="addp">参加者を追加</button></div>' +
        '<label for="dvr-cl">観点チェックリスト</label><select id="dvr-cl">' + opts + '</select>' +
        '<span>出口基準</span><div>未対応の重大 <input type="number" min="0" id="dvr-ec-c" value="' + esc(ec.max_open_critical != null ? ec.max_open_critical : 0) + '" style="width:64px"> 件以下、未対応の主要 <input type="number" min="0" id="dvr-ec-w" value="' + esc(ec.max_open_warning != null ? ec.max_open_warning : 5) + '" style="width:64px"> 件以下</div>' +
        '<span>文書</span><div>' + (doc ? '<b>' + esc(doc.name) + '</b> <span class="role">' + esc(doc.format) + '・' + esc(doc.passages) + ' 文・第 ' + esc(doc.version) + ' 版</span>' : '<span class="role">まだ取り込んでいません</span>') +
        '<div style="margin-top:6px"><input type="file" accept=".txt,.md,.docx,.xlsx,.pdf" data-file> <button type="button" class="b" data-act="upload">文書を取り込む</button></div></div>' +
        '</div><div class="dvr-actions"><button type="button" class="b" data-act="save">計画を保存</button>' +
        '<button type="button" class="b p" data-act="start">個別レビューを始める</button></div>';
      var plist = part(view, 'body').querySelector('[data-plist]');
      (r.participants || []).forEach(function (p) { addPRow(plist, p); });
      if (!(r.participants || []).length) plist.innerHTML = '<div class="role" data-none>参加者がいません。追加してください。</div>';
      part(view, 'body').onclick = function (ev) {
        var b = ev.target.closest('[data-act]'); if (!b) return;
        var a = b.getAttribute('data-act');
        if (a === 'addp') { var n = plist.querySelector('[data-none]'); if (n) n.remove(); addPRow(plist, { name: '', role: 'reviewer' }); }
        if (a === 'delp') b.closest('.dvr-row').remove();
        if (a === 'save') busy(b, savePlan(view, null));
        if (a === 'start') busy(b, savePlan(view, 'individual'));
        if (a === 'upload') {
          var f = part(view, 'body').querySelector('[data-file]').files[0];
          if (!f) { msg(view, '取り込むファイルを選んでください。', true); return; }
          msg(view, '取り込み中…');
          busy(b, upload(base() + '/document', f).then(setReview).then(function () {
            msg(view, '取り込みました。'); return rerender(view, renderPlan);
          }).catch(function (e) { msg(view, errText(e), true); }));
        }
      };
    });
  }
  function addPRow(plist, p) {
    var row = document.createElement('div');
    row.className = 'dvr-row';
    row.innerHTML = '<input type="text" placeholder="名前" data-pn><select data-pr>' +
      Object.keys(ROLES).map(function (k) { return '<option value="' + k + '">' + ROLES[k] + '</option>'; }).join('') +
      '</select><button type="button" class="b" data-act="delp">外す</button>';
    row.querySelector('[data-pn]').value = p.name || '';
    row.querySelector('[data-pr]').value = p.role || 'reviewer';
    row._done = !!p.done;
    plist.appendChild(row);
  }
  function savePlan(view, phase) {
    var body = part(view, 'body');
    var parts = [].slice.call(body.querySelectorAll('[data-plist] .dvr-row')).map(function (row) {
      return { name: row.querySelector('[data-pn]').value.trim(), role: row.querySelector('[data-pr]').value, done: row._done };
    }).filter(function (p) { return p.name; });
    var name = body.querySelector('#dvr-name').value.trim();
    if (!name) { msg(view, '名前を入れてください。', true); return Promise.resolve(); }
    if (phase === 'individual') {
      if (!rv().document) { msg(view, '先に文書を取り込んでください。', true); return Promise.resolve(); }
      if (!parts.some(function (p) { return p.role === 'reviewer'; })) { msg(view, 'レビュアーを 1 人以上入れてください。', true); return Promise.resolve(); }
    }
    var payload = {
      name: name, goal: body.querySelector('#dvr-goal').value.trim(), due: body.querySelector('#dvr-due').value,
      participants: parts, checklist_id: body.querySelector('#dvr-cl').value || null,
      exit_criteria: { max_open_critical: Number(body.querySelector('#dvr-ec-c').value || 0), max_open_warning: Number(body.querySelector('#dvr-ec-w').value || 0) }
    };
    if (phase) payload.phase = phase;
    return E().api(base(), json('PATCH', payload)).then(setReview).then(function () {
      if (phase === 'individual') { E().toast('個別レビューを始めました'); E().show('read'); return; }
      msg(view, '保存しました。'); return rerender(view, renderPlan);
    }).catch(function (e) { msg(view, errText(e), true); });
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
    if (withActs && f.status === 'candidate') {
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
  function renderRead(view) {
    return checklists().then(function (lists) {
      var r = rv(), ps = r.passages || [], fs = r.findings || [];
      var mine = myRole();
      part(view, 'headright').innerHTML = '<span class="role">あなたの役割: ' + esc(mine ? ROLES[mine.role] || mine.role : '未登録') +
        (r.due ? ' ・ 期限 ' + esc(r.due) : '') + '</span>' +
        '<button type="button" class="b p" data-act="done"' + (mine && mine.done ? ' disabled' : '') + '>' + (mine && mine.done ? '確認を終えました' : '自分の確認を終える') + '</button>';
      part(view, 'headright').querySelector('[data-act="done"]').onclick = function () {
        var b = this;
        busy(b, E().api(base() + '/participants/me/done', { method: 'POST' }).then(setReview).then(function () {
          E().toast('自分の確認を終えました'); return rerender(view, renderRead);
        }).catch(function (e) { msg(view, errText(e), true); }));
      };
      if (!ps.length) { part(view, 'body').innerHTML = empty('文書がまだ取り込まれていません。計画の画面で取り込んでください。'); return; }
      var byP = {};
      fs.forEach(function (f) { if (f.status !== 'rejected' && f.passage_id) (byP[f.passage_id] = byP[f.passage_id] || []).push(f); });
      var autoN = fs.filter(function (f) { return f.origin === 'auto' && f.status === 'candidate'; }).length;
      var lines = ps.map(function (p) {
        var hit = byP[p.id] || [];
        var words = hit.map(function (f) { return f.quote; }).filter(function (q) { return q && q.length < 30; });
        return '<div class="ln' + (hit.length ? ' hit' : '') + (ui.selLine === p.id ? ' sel' : '') + '" data-pid="' + esc(p.id) + '" data-key-open role="button"><span class="no">' + esc(p.location) + '</span><span>' +
          hl(p.text, words) + hit.map(function (f) { return '<span class="pin">' + esc(f.id) + '</span>'; }).join('') + '</span></div>';
      }).join('');
      var cl = currentChecklist(lists), checks = r.checks || {};
      var nCk = cl ? cl.items.filter(function (i) { return checks[i.id]; }).length : 0;
      var mineList = fs.filter(function (f) { return f.raised_by === me() || f.origin === 'auto'; });
      var tabs = '<div class="tabs"><button data-tab="mine" class="' + (ui.tab === 'mine' ? 'on' : '') + '">自分の指摘・候補 ' + mineList.length + '</button>' +
        '<button data-tab="all" class="' + (ui.tab === 'all' ? 'on' : '') + '">全員 ' + fs.length + '</button>' +
        '<button data-tab="check" class="' + (ui.tab === 'check' ? 'on' : '') + '">チェックリスト ' + (cl ? nCk + '/' + cl.items.length : '') + '</button></div>';
      var side;
      if (ui.tab === 'check') {
        side = !cl ? empty('観点チェックリストが選ばれていません。計画の画面で選べます。') : cl.items.map(function (i) {
          var n = fs.filter(function (f) { return f.checklist_item === i.id; }).length;
          return '<label class="f" style="display:flex;gap:8px"><input type="checkbox" data-ck="' + esc(i.id) + '"' + (checks[i.id] ? ' checked' : '') + '><span>' + esc(i.text) + ' <span class="role">指摘 ' + n + ' 件</span></span></label>';
        }).join('');
      } else {
        var list = ui.tab === 'mine' ? mineList : fs;
        side = list.length ? list.map(function (f) { return findingCard(f, true); }).join('')
          : empty(E().emptyFindings(ps.length));
      }
      var sum = E().state.summary || {};
      part(view, 'body').innerHTML = docBand(r, sum) + scoreBand(sum.quality) + '<div class="wrap dvr-wrap">' +
        '<section class="card"><h3>本文 <span class="role">' + ps.length + ' 文 ・ 自動候補 ' + autoN + ' 件をハイライト ・ 文を押すと指摘を追加</span></h3><div class="doc" data-doc>' + lines + '</div></section>' +
        '<section class="card">' + tabs + '<div class="dvr-scroll">' + side +
        '<div class="f"><b>指摘を追加</b><div class="role">本文の文を押して選び、重大度・観点を選んで 1 行で書く</div></div></div></section></div>';
      if (ui.selLine) openAdd(view, ui.selLine, cl);
      var body = part(view, 'body');
      E().keyOpen(body);
      body.onclick = function (ev) {
        if (scoreHelpClicked(ev)) return;
        var t = ev.target.closest('[data-tab]');
        if (t) { ui.tab = t.getAttribute('data-tab'); return rerender(view, renderRead); }
        var a = ev.target.closest('[data-fa]');
        if (a) {
          var fa = a.getAttribute('data-fa'), fid = a.getAttribute('data-fid');
          var bodyMap = { adopt: { status: 'adopted', raised_by: me() }, reject: { status: 'rejected' }, ask: { certainty: '要確認' } };
          return busy(a, setFinding(fid, bodyMap[fa]).then(function () {
            if (fa === 'ask') E().toast('質問票に入れました');
            return rerender(view, renderRead);
          }).catch(function (e) { msg(view, errText(e), true); }));
        }
        var ln = ev.target.closest('.ln');
        if (ln && !ev.target.closest('.dvr-add')) {
          ui.selLine = ln.getAttribute('data-pid');
          body.querySelectorAll('.ln.sel').forEach(function (x) { x.classList.remove('sel'); });
          ln.classList.add('sel');
          openAdd(view, ui.selLine, cl);
        }
      };
      body.onchange = function (ev) {
        var c = ev.target.closest('[data-ck]'); if (!c) return;
        var next = Object.assign({}, rv().checks || {});
        next[c.getAttribute('data-ck')] = c.checked;
        c.disabled = true;
        E().api(base(), json('PATCH', { checks: next })).then(setReview).then(function () { return rerender(view, renderRead); })
          .catch(function (e) { c.checked = !c.checked; c.disabled = false; msg(view, errText(e), true); });
      };
    });
  }
  function openAdd(view, pid, cl) {
    var body = part(view, 'body');
    var old = body.querySelector('.dvr-add'); if (old) old.remove();
    var ln = body.querySelector('.ln[data-pid="' + CSS.escape(pid) + '"]'); if (!ln) return;
    var types = (cache.settings && cache.settings.types && cache.settings.types.length) ? cache.settings.types : DEFAULT_TYPES;
    var box = document.createElement('div');
    box.className = 'dvr-add';
    box.innerHTML = '<select data-a="sev"><option value="critical">重大</option><option value="major" selected>主要</option><option value="minor">軽微</option></select>' +
      '<select data-a="vp">' + types.map(function (t) { return '<option>' + esc(t) + '</option>'; }).join('') + '</select>' +
      (cl ? '<select data-a="ck"><option value="">チェックリスト項目なし</option>' + cl.items.map(function (i) { return '<option value="' + esc(i.id) + '">' + esc(i.text) + '</option>'; }).join('') + '</select>' : '') +
      '<input type="text" data-a="msg" placeholder="何が問題かを 1 行で" maxlength="200">' +
      '<button type="button" class="b p" data-a="ok">追加</button><button type="button" class="b" data-a="cancel">やめる</button>';
    ln.after(box);
    box.querySelector('[data-a="msg"]').focus();
    box.onclick = function (ev) {
      ev.stopPropagation();
      var a = ev.target.getAttribute('data-a');
      if (a === 'cancel') { ui.selLine = null; box.remove(); ln.classList.remove('sel'); return; }
      if (a !== 'ok') return;
      var text = box.querySelector('[data-a="msg"]').value.trim();
      if (!text) { msg(view, '指摘の文を入れてください。', true); return; }
      var ckSel = box.querySelector('[data-a="ck"]'), ck = ckSel ? ckSel.value : '';
      var before = (rv().findings || []).map(function (f) { return f.id; });
      busy(ev.target, E().api(base() + '/findings', json('POST', {
        passage_id: pid, severity: box.querySelector('[data-a="sev"]').value,
        viewpoint: box.querySelector('[data-a="vp"]').value, message: text
      })).then(setReview).then(function () {
        var added = (rv().findings || []).filter(function (f) { return before.indexOf(f.id) < 0; })[0];
        if (ck && added) return setFinding(added.id, { checklist_item: ck });
      }).then(function () {
        ui.selLine = null; msg(view, ''); E().toast('指摘を追加しました'); return rerender(view, renderRead);
      }).catch(function (e) { msg(view, errText(e), true); }));
    };
  }

  /* ---------- 指摘の検討 ---------- */
  function renderTriage(view) {
    var fs = (rv().findings || []).filter(function (f) { return f.status !== 'candidate'; });
    var pend = (rv().findings || []).length - fs.length;
    if (!fs.length) {
      part(view, 'body').innerHTML = empty('検討する指摘はありません。' + (pend ? '未検討の候補が ' + pend + ' 件あります。文書を読む画面で指摘にするか却下してください。' : ''));
      return;
    }
    var sevOpt = function (v) { return ['critical', 'major', 'minor'].map(function (k) { return '<option value="' + k + '"' + (k === v ? ' selected' : '') + '>' + SEV[k] + '</option>'; }).join(''); };
    var stOpt = function (v) { return ['adopted', 'fixed', 'verified', 'rejected'].map(function (k) { return '<option value="' + k + '"' + (k === v ? ' selected' : '') + '>' + STATUS[k] + '</option>'; }).join(''); };
    part(view, 'body').innerHTML = (pend ? '<div class="role" style="margin-bottom:8px">未検討の候補が ' + pend + ' 件残っています。</div>' : '') +
      '<div style="overflow-x:auto;max-width:100%"><table class="dv-t"><thead><tr><th>番号</th><th>重大度</th><th>指摘</th><th>場所</th><th>起票</th><th>状態</th><th>作成者の対応結果</th><th></th></tr></thead><tbody>' +
      fs.map(function (f) {
        return '<tr data-fid="' + esc(f.id) + '"><td><b>' + esc(f.id) + '</b></td><td><select data-t="sev">' + sevOpt(sev(f.severity)) + '</select></td>' +
          '<td>' + esc(f.message) + evRow(f) + (f.answer ? '<div class="role">回答: ' + esc(f.answer) + '</div>' : '') + '</td><td class="loc">' + esc(f.location) + '</td><td>' + esc(f.raised_by || '') + '</td>' +
          '<td><select data-t="st">' + stOpt(f.status) + '</select></td><td><input type="text" data-t="disp" value="' + esc(f.disposition || '') + '" style="width:100%"></td>' +
          '<td><button type="button" class="b" data-t="save">保存</button></td></tr>';
      }).join('') + '</tbody></table></div>';
    part(view, 'body').onclick = function (ev) {
      var b = ev.target.closest('[data-t="save"]'); if (!b) return;
      var tr = b.closest('tr');
      busy(b, setFinding(tr.getAttribute('data-fid'), {
        severity: tr.querySelector('[data-t="sev"]').value, status: tr.querySelector('[data-t="st"]').value,
        disposition: tr.querySelector('[data-t="disp"]').value.trim() || null
      }).then(function () { E().toast('保存しました'); return rerender(view, renderTriage); })
        .catch(function (e) { msg(view, errText(e), true); }));
    };
  }

  /* ---------- 質問票 ---------- */
  function renderQuestions(view) {
    var qs = (rv().findings || []).filter(function (f) { return f.certainty === '要確認' && f.status !== 'rejected'; });
    part(view, 'headright').innerHTML = '<a class="b" href="' + esc(base() + '/questions.csv') + '">CSV で出力</a><a class="b" href="' + esc(base() + '/questions.xlsx') + '">Excel で出力</a>';
    part(view, 'body').innerHTML = '<div class="dv-panel" style="margin:0 0 12px"><label>回答を書き込んだ CSV を取り込む: <input type="file" accept=".csv" data-file></label> <button type="button" class="b p" data-act="ans">取り込む</button></div>' +
      (qs.length ? '<table class="dv-t"><thead><tr><th>No.</th><th>場所</th><th>質問</th><th>回答</th></tr></thead><tbody>' + qs.map(function (f, i) {
        return '<tr><td>' + (i + 1) + '</td><td class="loc">' + esc(f.location) + '</td><td>' + esc(f.message) + '</td><td>' + (f.answer ? esc(f.answer) : '<span class="role">未回答</span>') + '</td></tr>';
      }).join('') + '</tbody></table>' : empty('作成者への質問はありません。文書を読む画面で「作成者に質問」を押すとここに並びます。'));
    part(view, 'body').querySelector('[data-act="ans"]').onclick = function () {
      var f = part(view, 'body').querySelector('[data-file]').files[0];
      if (!f) { msg(view, '取り込む CSV を選んでください。', true); return; }
      var b = this; msg(view, '取り込み中…');
      busy(b, upload(base() + '/answers', f).then(function (d) {
        setReview(d); return rerender(view, renderQuestions).then(function () { msg(view, '回答を ' + (d.applied || 0) + ' 件反映しました。'); });
      }).catch(function (e) { msg(view, errText(e), true); }));
    };
    return Promise.resolve();
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
      '<div class="dvr-actions"><button type="button" class="b" data-act="ap">承認欄を保存</button></div></div>' +
      '<div class="dvr-actions"><button type="button" class="b p" data-act="close"' + (r.status === 'closed' ? ' disabled' : '') + '>' + (r.status === 'closed' ? '終了しています' : 'レビューを終える') + '</button></div>';
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

  function init() {
    if (!window.DV || !window.DV.on) { setTimeout(init, 30); return; }
    var map = { plan: renderPlan, read: renderRead, triage: renderTriage, questions: renderQuestions, followup: renderFollowup, screen: renderScreen, gate: renderGate };
    Object.keys(map).forEach(function (v) { if (sect(v)) window.DV.on(v, open(v, map[v])); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
