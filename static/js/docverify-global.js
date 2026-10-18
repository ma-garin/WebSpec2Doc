/* ドキュメント検証 v2: 全体・管理の画面（home, mine, reviews, findings, checklists, metrics, settings） */
(function () {
  'use strict';
  var DV = window.DV;
  if (!DV) return;
  var esc = DV.esc;
  var $ = function (id) { return document.getElementById(id); };

  var SEV = { critical: ['重大', 'c-crit'], major: ['主要', 'c-maj'], minor: ['軽微', 'c-min'], warning: ['主要', 'c-maj'], info: ['軽微', 'c-min'] };
  var STATUS = { candidate: '候補', adopted: '未対応', rejected: '却下', fixed: '修正済', verified: '確認済' };
  var PHASE = { plan: '計画', individual: '個別レビュー', triage: '指摘の検討', rework: '修正', followup: '修正版の確認', closed: '完了' };
  var ROLE = { author: '作成者', moderator: '進行役', reviewer: 'レビュアー', approver: '承認者' };

  function sevChip(s) { var v = SEV[s] || [s || '-', '']; return '<span class="chip ' + v[1] + '">' + esc(v[0]) + '</span>'; }
  function loading(el) { el.innerHTML = '<p class="mut">読み込み中…</p>'; }
  function failed(el) { el.innerHTML = '<p class="mut">読み込めませんでした。画面を開き直してください。</p>'; }
  function empty(el, msg) { el.innerHTML = '<p class="mut dvg-empty">' + esc(msg) + '</p>'; }
  function lbl(map, k) { return esc(map[k] || k || '-'); }
  function load(el, path, render) {
    loading(el);
    return DV.api(path).then(render).catch(function () { failed(el); });
  }
  function table(head, rows) {
    return '<table class="dv-t"><thead><tr>' + head.map(function (h) { return '<th>' + esc(h) + '</th>'; }).join('') +
      '</tr></thead><tbody>' + rows.join('') + '</tbody></table>';
  }
  function bindRows(el, fn) {
    el.querySelectorAll('tr[data-id]').forEach(function (tr) {
      tr.addEventListener('click', function () { fn(tr.dataset.id); });
    });
  }
  function reviewRow(r) {
    var rid = r.id || r.review_id;  // 一覧は id/name、ホームは review_id/review_name で返る
    return '<tr data-id="' + esc(rid) + '" class="dv-click" data-key-open><td>' + esc(r.name || r.review_name || rid) + '</td><td>' + (r.role ? lbl(ROLE, r.role) : '-') +
      '</td><td>' + lbl(PHASE, r.phase) + '</td><td>' + esc(r.due || '-') + '</td></tr>';
  }
  function reviewTable(el, list, msg) {
    if (!list || !list.length) return empty(el, msg);
    el.innerHTML = table(['レビュー', '役割', '工程', '期限'], list.map(reviewRow));
    bindRows(el, DV.openReview);
    DV.keyOpen(el);
  }

  // ISO/IEC/IEEE 29148 の品質特性（チェックリスト項目 id → 表示名）
  var CK_LABEL = { necessary: '必要', unambiguous: '曖昧でない', complete: '完全', consistent: '一貫', feasible: '実現可能', verifiable: '検証可能', traceable: '追跡可能', singular: '単一' };
  function relabel(obj) { var o = {}; Object.keys(obj || {}).forEach(function (k) { o[CK_LABEL[k] || k] = obj[k]; }); return o; }

  /* home */
  var TODO_SCOPE = { mine: '自分の担当から', active: '進行中のレビューから' };
  function isNum(v) { return v !== null && v !== undefined && !isNaN(+v); }
  function statCard(key, label, num, sub, warn) {
    return '<div class="stat-card' + (warn ? ' is-warn' : '') + '" data-stat="' + key + '"><div class="stat-card-head"><span class="stat-card-label">' +
      esc(label) + '</span></div><div class="stat-card-num">' + esc(num) + '</div>' + (sub ? '<div class="stat-card-sub">' + esc(sub) + '</div>' : '') + '</div>';
  }
  function homeStats(d) {
    var c = d.counts || {}; var q = d.quality || {};
    var crit = +c.open_critical || 0;
    var qOk = isNum(q.overall);
    return statCard('active', '進行中のレビュー', +c.active || 0, '', false) +
      statCard('critical', '未対応の重大な指摘', crit, '', crit > 0) +
      statCard('answers', '回答待ちの質問', +c.awaiting_answers || 0, '', false) +
      statCard('quality', '品質スコア', DV.scoreText(q.overall), qOk ? '算出できた ' + (+q.n_scored || 0) + ' 件の平均' : DV.NO_SCORE, false);
  }
  function homeQuality(q) {
    q = q || {};
    var head = '<h3>特性別の品質スコア</h3>';
    if (!(+q.n_scored)) return head + '<p class="sub">' + esc(DV.NO_SCORE) + '</p>';
    var items = q.items || {};
    var rows = Object.keys(items).map(function (k) { return { label: items[k].label || CK_LABEL[k] || k, score: items[k].score }; });
    rows.sort(function (a, b) {
      var an = !isNum(a.score); var bn = !isNum(b.score);
      if (an || bn) return an === bn ? 0 : (an ? 1 : -1);
      return a.score - b.score;
    });
    return head + '<p class="sub">' + esc('算出できた ' + (+q.n_scored) + ' 件の平均') + '</p>' + rows.map(function (r) {
      return '<div class="dv-qrow"><span class="dv-ellipsis" title="' + esc(r.label) + '">' + esc(r.label) + '</span>' +
        DV.scoreBar(r.score, r.label) + '<b>' + esc(DV.scoreText(r.score)) + '</b></div>';
    }).join('');
  }
  function homeTodo(list, scope) {
    var head = '<h3>次にやること</h3><p class="sub">' + esc(TODO_SCOPE[scope] || TODO_SCOPE.active) + '</p>';
    if (!list || !list.length) return head + '<p class="mut dvg-empty">いまやることはありません。</p>';
    return head + '<ul class="dv-todo">' + list.map(function (t) {
      var name = t.review_name || t.review_id;
      return '<li><span class="dv-ellipsis" title="' + esc(name) + '">' + esc(name) + '</span><button type="button" class="dv-link" data-review="' +
        esc(t.review_id) + '" data-view="' + esc(t.view || 'read') + '">' + esc(t.label) + '</button></li>';
    }).join('') + '</ul>';
  }
  function homeRow(r) {
    var doc = r.document_name || r.review_name || r.review_id;
    var crit = +r.open_critical || 0;
    var stage = '<span class="dv-stage' + (r.phase === 'closed' ? ' is-done' : '') + '">' + lbl(PHASE, r.phase) + '</span>';
    var score = '<span class="dv-score">' + DV.scoreBar(r.quality_overall, '品質スコア') + '<b>' + esc(DV.scoreText(r.quality_overall)) + '</b></span>';
    var open = esc(+r.open || 0) + (crit > 0 ? ' <span class="dv-sev c">重大 ' + esc(crit) + '</span>' : '');
    var upd = r.updated_at ? String(r.updated_at).slice(0, 16).replace('T', ' ') : '-';
    return '<tr data-id="' + esc(r.review_id) + '" data-key-open><td class="site-cell"><span class="dv-ellipsis" title="' + esc(doc) + '">' + esc(doc) + '</span>' +
      ((+r.versions || 0) > 1 ? '<span class="diff-badge">改版あり</span>' : '') + '</td><td>' + stage + '</td><td>' + score +
      '</td><td class="num">' + open + '</td><td>' + esc(upd) + '</td><td><button type="button" class="btn-outline-sm">開く</button></td></tr>';
  }
  function homeTable(active) {
    if (!active || !active.length) return '<p class="mut dvg-empty">進行中のレビューはありません。「＋ 新しいレビュー」から始められます。</p>';
    return '<table class="data dashboard-table"><thead><tr><th>文書</th><th>工程</th><th>品質スコア</th><th>未対応</th><th>更新</th><th>操作</th></tr></thead><tbody>' +
      active.map(homeRow).join('') + '</tbody></table>';
  }
  function renderHome(d) {
    d = d || {};
    $('dvgHomeStats').innerHTML = homeStats(d);
    $('dvgHomeQuality').innerHTML = homeQuality(d.quality);
    $('dvgHomeTodo').innerHTML = homeTodo(d.next_actions, d.next_scope);
    var tbl = $('dvgHomeTable');
    tbl.innerHTML = homeTable(d.active);
    bindRows(tbl, function (id) { DV.openReview(id, 'read').catch(function () {}); });
    $('dvgHomeTodo').querySelectorAll('button[data-review]').forEach(function (b) {
      b.addEventListener('click', function () { DV.openReview(b.dataset.review, b.dataset.view).catch(function () {}); });
    });
    DV.keyOpen(tbl);
    DV.keyOpen($('dvgHomeTodo'));
  }
  function loadHome() {
    var ids = ['dvgHomeQuality', 'dvgHomeTodo', 'dvgHomeTable'];
    $('dvgHomeStats').innerHTML = '';
    ids.forEach(function (id) { loading($(id)); });
    return DV.api('/api/docverify/home').then(renderHome).catch(function (e) { ids.forEach(function (id) { failed($(id)); }); throw e; });
  }
  DV.on('home', function () { loadHome().catch(function () {}); });
  var homeReload = $('dvgHomeReload');
  if (homeReload) homeReload.addEventListener('click', function () { DV.busy(homeReload, loadHome, '読み込み中…').catch(function () {}); });
  function startNew() {
    DV.show('reviews');
    var input = document.querySelector('#dvgNewForm [name=name]');
    if (input) input.focus();
  }
  ['dv-new-review', 'dvgHeroStart', 'dvgHomeNew'].forEach(function (id) { var b = $(id); if (b) b.addEventListener('click', startNew); });

  /* mine */
  DV.on('mine', function () {
    var el = $('dvgMine');
    load(el, '/api/docverify/home', function (d) { reviewTable(el, d.mine, 'いま担当しているレビューはありません。'); });
  });

  /* reviews */
  function fillChecklistSelect(sel, keepFirst) {
    return DV.api('/api/docverify/checklists').then(function (r) { var cls = (r && r.checklists) || r;
      var first = keepFirst ? sel.options[0].outerHTML : '';
      sel.innerHTML = first + (cls || []).map(function (c) { return '<option value="' + esc(c.id) + '">' + esc(c.name) + '</option>'; }).join('');
      return cls || [];
    });
  }
  DV.on('reviews', function () {
    var el = $('dvgReviews');
    fillChecklistSelect($('dvgNewChecklist'), true).catch(function () {});
    load(el, '/api/docverify/inspections', function (d) {
      var list = Array.isArray(d) ? d : (d.inspections || d.items || []);
      if (!list.length) return empty(el, 'レビューはまだありません。上の欄から作成してください。');
      el.innerHTML = table(['レビュー', '工程', '期限', '指摘'], list.map(function (r) {
        return '<tr data-id="' + esc(r.id) + '" data-key-open><td>' + esc(r.name || r.id) + '</td><td>' + lbl(PHASE, r.phase) +
          '</td><td>' + esc(r.due || '-') + '</td><td>' + esc(r.findings_count != null ? r.findings_count : (r.findings || []).length) + '</td></tr>';
      }));
      bindRows(el, DV.openReview);
      DV.keyOpen(el);
    });
  });
  var form = $('dvgNewForm');
  var DEFAULT_REVIEW_TYPE = 'informal';
  function createReview(fd) {
    // 種別は作成時に必須（FR-06-140）。この画面に選択欄が無ければ既定の種別で作り、計画の画面で変更できる
    var rtype = fd.get('review_type') || DEFAULT_REVIEW_TYPE;
    return DV.api('/api/docverify/r4/inspections', { method: 'POST', json: { name: fd.get('name') || '', goal: fd.get('goal') || '', review_type: rtype } }).then(function (r) {
      var iid = r.id || (r.inspection && r.inspection.id);
      var extra = {};
      if (fd.get('checklist_id')) extra.checklist_id = fd.get('checklist_id');
      if (fd.get('due')) extra.due = fd.get('due');
      var p = Object.keys(extra).length ? DV.api('/api/docverify/inspections/' + encodeURIComponent(iid), {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(extra) }) : Promise.resolve();
      var file = fd.get('file');  // 作成と同時に対象の文書を取り込む（取り込むと自動の候補が並ぶ）
      var hasFile = !!(file && file.size);
      var up = function () { if (!hasFile) return Promise.resolve(); var f2 = new FormData(); f2.append('file', file); return DV.api('/api/docverify/inspections/' + encodeURIComponent(iid) + '/document', { method: 'POST', form: f2 }); };
      return p.then(up).then(function () { form.reset(); DV.toast('レビューを作成しました'); return DV.openReview(iid, hasFile ? 'read' : 'plan'); });
    });
  }
  if (form) form.addEventListener('submit', function (e) {
    e.preventDefault();
    var btn = form.querySelector('button[type=submit]');
    var fd = new FormData(form);
    // 失敗時は入力を残す（form.reset しない）。文言は帯（#dv-banner）に出る
    DV.busy(btn, function () { return createReview(fd); }, '文書を読み取り中…').catch(function () {});
  });

  /* findings */
  var fReviewsLoaded = false;
  function loadFindings() {
    var el = $('dvgFindings');
    var q = '?status=' + encodeURIComponent($('dvgFStatus').value) + '&severity=' + encodeURIComponent($('dvgFSeverity').value) +
      '&review=' + encodeURIComponent($('dvgFReview').value);
    load(el, '/api/docverify/findings' + q, function (d) {
      var list0 = Array.isArray(d) ? d : (d.findings || []);
      var rank = { critical: 0, major: 1, minor: 2 };
      var list = list0.map(function (f, i) { return { f: f, i: i }; }).sort(function (a, b) {
        var ra = rank[a.f.severity] != null ? rank[a.f.severity] : 3, rb = rank[b.f.severity] != null ? rank[b.f.severity] : 3;
        return ra - rb || a.i - b.i;
      }).map(function (x) { return x.f; });
      if (!fReviewsLoaded) {
        var seen = {}; var sel = $('dvgFReview');
        list.forEach(function (f) {
          if (seen[f.review_id]) return; seen[f.review_id] = 1;
          var o = document.createElement('option'); o.value = f.review_id; o.textContent = f.review_name || f.review_id; sel.appendChild(o);
        });
        fReviewsLoaded = true;
      }
      if (!list.length) return empty(el, '条件に合う指摘はありません。');
      el.innerHTML = table(['重大度', '内容', 'レビュー', '状態', '指摘者'], list.map(function (f, i) {
        return '<tr data-id="' + i + '" data-key-open><td>' + sevChip(f.severity) + '</td><td>' + esc(f.message || f.text || f.title || '') +
          '</td><td>' + esc(f.review_name || f.review_id) + '</td><td>' + lbl(STATUS, f.status) + '</td><td>' + esc(f.raised_by || '-') + '</td></tr>';
      }));
      bindRows(el, function (i) {
        var f = list[+i];
        DV.openReview(f.review_id, 'triage');
      });
      DV.keyOpen(el);
    });
  }
  ['dvgFStatus', 'dvgFSeverity', 'dvgFReview'].forEach(function (id) { var s = $(id); if (s) s.addEventListener('change', loadFindings); });
  DV.on('findings', loadFindings);


  /* metrics */
  function bars(title, obj, labels) {
    var keys = Object.keys(obj || {});
    if (!keys.length) return '<h3 class="dvg-h3">' + esc(title) + '</h3><p class="mut">データがありません。</p>';
    var max = Math.max.apply(null, keys.map(function (k) { return +obj[k] || 0; })) || 1;
    return '<h3 class="dvg-h3">' + esc(title) + '</h3><table class="dv-t"><tbody>' + keys.map(function (k) {
      var v = +obj[k] || 0;
      return '<tr><td class="dvg-bl">' + esc((labels && labels[k]) ? labels[k][0] || labels[k] : k) + '</td><td><span class="dvg-bar" style="width:' +
        Math.round(v / max * 100) + '%"></span></td><td class="dvg-bn">' + esc(v) + '</td></tr>';
    }).join('') + '</tbody></table>';
  }
  DV.on('metrics', function () {
    var el = $('dvgMetrics');
    load(el, '/api/docverify/metrics', function (d) {
      d = (d && d.metrics) || d || {};
      if (Array.isArray(d.by_review)) { var br = {}; d.by_review.forEach(function (r) { br[r.review_name || r.review_id] = r.findings; }); d.by_review = br; }
      if (!d || !Object.keys(d).length) return empty(el, 'まだ集計できるレビューがありません。');
      var rate = d.fix_rate != null ? d.fix_rate : d.completion_rate;
      var dens = d.density != null ? d.density : d.findings_per_fragment;
      el.innerHTML = '<div class="dvg-cards"><div class="card dvg-card"><div class="mut">修正完了率</div><div class="dvg-num">' +
        esc(rate == null ? '-' : Math.round(rate * (rate <= 1 ? 100 : 1)) + '%') + '</div></div><div class="card dvg-card"><div class="mut">断片あたりの指摘</div><div class="dvg-num">' +
        esc(dens == null ? '-' : (+dens).toFixed(2)) + '</div></div></div>' +
        bars('重大度別', d.by_severity, SEV) + bars('観点別', relabel(d.by_viewpoint || d.by_checklist_item || d.by_checklist)) + bars('レビュー別', d.by_review);
    });
  });

  /* settings */
  DV.on('settings', function () {
    var el = $('dvgSettings');
    load(el, '/api/docverify/settings', function (s) {
      s = (s && s.settings) || s || {};  // API は {settings: {...}} で返す
      var sev = (s.severities || []).map(function (x) {
        var k = x.id || x.key || x; return '<li>' + sevChip(k) + ' ' + esc(x.description || x.desc || '') + '</li>';
      }).join('');
      var types = (s.types || []).map(function (x) { return '<li>' + esc(x.name || x.label || x) + (x.description ? '：' + esc(x.description) : '') + '</li>'; }).join('');
      var ec = s.exit_criteria || {};
      var EC_LABEL = { max_open_critical: '未対応の重大な指摘の上限', max_open_major: '未対応の主要な指摘の上限' };
      var exit = Object.keys(ec).map(function (k) { return '<li>' + esc(EC_LABEL[k] || k) + '：' + esc(ec[k]) + ' 件</li>'; }).join('');
      var roles = Object.keys(ROLE).map(function (k) {
        var d = { author: '文書を書いた人。指摘への対応を記入します。', moderator: '進め方と期限を決め、検討の場を回します。',
          reviewer: '文書を読み、指摘を出します。', approver: '判定と記録の画面で、出口基準を満たしたかを判断します。' }[k];
        return '<li><strong>' + esc(ROLE[k]) + '</strong>：' + esc(d) + '</li>';
      }).join('');
      el.innerHTML = '<div class="card"><p class="mut">利用者: ' + esc(s.me || 'ゲスト') + '</p></div>' +
        '<h3 class="dvg-h3">重大度</h3>' + (sev ? '<ul class="dvg-list">' + sev + '</ul>' : '<p class="mut">未設定です。</p>') +
        '<h3 class="dvg-h3">指摘の種別</h3>' + (types ? '<ul class="dvg-list">' + types + '</ul>' : '<p class="mut">未設定です。</p>') +
        '<h3 class="dvg-h3">出口基準</h3>' + (exit ? '<ul class="dvg-list">' + exit + '</ul>' : '<p class="mut">未設定です。</p>') +
        '<h3 class="dvg-h3">役割</h3><ul class="dvg-list">' + roles + '</ul>';
    });
  });
})();
