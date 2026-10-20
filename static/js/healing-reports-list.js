/* オートヒーリングの報告書（templates/healing_reports.html・healing_report.html）: 一覧: 束（画面 × 観点）の表・状態の絞り込み・案件の絞り込み・指揮からの ?site=
   読み込み順: healing-reports-core.js → healing-reports-list.js → healing-reports-doc.js → healing-reports-bundle.js → healing-reports.js。
   ファイル間の共有は window.HealingReports（HL）だけ。他ファイルの関数は呼び出し時に HL から引く。 */
(function (HL) {
  'use strict';

  /* ---- 他ファイルの宣言 ---- */
  function api() { return HL.api.apply(this, arguments); }
  function clearError() { return HL.clearError.apply(this, arguments); }
  function el() { return HL.el.apply(this, arguments); }
  function hasWS() { return HL.hasWS.apply(this, arguments); }
  function relTime() { return HL.relTime.apply(this, arguments); }
  function renderHead() { return HL.renderHead.apply(this, arguments); }
  function showError() { return HL.showError.apply(this, arguments); }
  function showState() { return HL.showState.apply(this, arguments); }
  function tailPath() { return HL.tailPath.apply(this, arguments); }


  /* ---------------- 一覧（束 = 画面 × 観点） ---------------- */

  var state = {
    view: 'needs_review', projectId: '', reportId: '', bundleId: '',
    allBundles: [], expanded: {}
  };

  var STATUS_LABELS = {
    awaiting: '承認待ち', approved: '承認済み', returned: '差し戻し',
    rejected: '却下', submitted: '提出済み', draft: '下書き', mixed: '一部承認・一部却下'
  };
  /* 一覧の絞り込みは状態そのものではなく「要確認か」で分ける（T4）。
   * 決着済み（提出済み・却下）は従来どおり状態で分ける。0 件のものは並べない。 */
  var VIEW_LABELS = { needs_review: '要確認', no_review: '確認不要', submitted: '提出済み', rejected: '却下' };
  var VIEW_ORDER = ['needs_review', 'no_review', 'submitted', 'rejected'];

  function bundleView(bundle) {
    if (bundle.status === 'rejected') { return 'rejected'; }
    if (bundle.status === 'approved' || bundle.status === 'submitted') { return 'submitted'; }
    return bundle.needs_review ? 'needs_review' : 'no_review';
  }

  function verifyBadge(report) {
    if (report.verify_after_ok === true) { return el('span', 'hl-badge is-ok', report.verify_after); }
    if (report.verify_after_ok === false) { return el('span', 'hl-badge is-err', report.verify_after); }
    return el('span', 'hl-badge is-mute', report.verify_after || '未実行');
  }

  function attentionCell(report) {
    if (report.action_empty) {
      return el('span', 'hl-badge is-mute', '直っていません');
    }
    if (report.attention_high > 0) {
      return el('span', 'hl-badge is-err', report.attention_count + ' 件');
    }
    if (report.attention_count > 0) {
      return el('span', 'hl-badge is-warn', report.attention_count + ' 件');
    }
    return el('span', 'hl-badge is-mute', 'なし');
  }

  /* 個票 1 行。束の折りたたみの中でも、束の本文ページでも使う共通部品。 */
  function renderReportRow(report) {
    var tr = el('tr');
    tr.setAttribute('role', 'link');
    tr.setAttribute('tabindex', '0');
    var href = '/healing/reports/' + encodeURIComponent(report.report_id);
    function open() { window.location.href = href; }
    tr.addEventListener('click', open);
    tr.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); }
    });

    var tdTitle = el('td', 'hl-cell-name');
    tdTitle.appendChild(el('b', null, report.title || '（件名なし）'));
    var sub = [report.incident_screen_id, report.incident_screen_name].filter(Boolean).join(' ');
    if (sub) { tdTitle.appendChild(el('small', null, sub)); }
    tr.appendChild(tdTitle);

    var tdVerify = el('td');
    tdVerify.appendChild(verifyBadge(report));
    tr.appendChild(tdVerify);

    var tdAttention = el('td');
    tdAttention.appendChild(attentionCell(report));
    tr.appendChild(tdAttention);

    var tdWhen = el('td', 'hl-cell-when', relTime(report.updated_at || report.created_at));
    tdWhen.title = report.updated_at || report.created_at || '';
    tr.appendChild(tdWhen);

    var tdAction = el('td', 'hl-cell-action');
    var btn = el('button', 'hl-btn hl-btn-sm', '読む');
    btn.type = 'button';
    btn.addEventListener('click', function (ev) { ev.stopPropagation(); open(); });
    tdAction.appendChild(btn);
    tr.appendChild(tdAction);
    return tr;
  }

  function renderReportTable(reports) {
    var wrap = el('div', 'hl-nested-wrap');
    var table = el('table', 'hl-nested-table');
    var thead = el('thead'), htr = el('tr');
    ['件名', '検証', '確認が必要な点', '更新', ''].forEach(function (t) { htr.appendChild(el('th', null, t)); });
    thead.appendChild(htr); table.appendChild(thead);
    var tbody = el('tbody');
    if (reports && reports.length) {
      reports.forEach(function (r) { tbody.appendChild(renderReportRow(r)); });
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    if (!reports || !reports.length) {
      wrap.appendChild(el('p', 'hl-doc-note', '個票がありません。'));
    }
    return wrap;
  }

  function bundleAttentionCell(bundle) {
    if (bundle.attention_high > 0) {
      return el('span', 'hl-badge is-err', bundle.attention_high + ' 件');
    }
    return el('span', 'hl-badge is-mute', 'なし');
  }

  function toggleBundleRow(bundle, toggle, holderRow) {
    var willOpen = holderRow.hidden;
    if (!willOpen) {
      holderRow.hidden = true;
      toggle.textContent = '▸';
      return;
    }
    holderRow.hidden = false;
    toggle.textContent = '▾';
    if (state.expanded[bundle.bundle_id]) { return; }  // 取得済みなので読み直さない
    var cell = holderRow.firstChild;
    cell.textContent = '';
    cell.appendChild(el('p', 'hl-doc-note', '読み込んでいます…'));
    api('/api/healing/bundles/' + encodeURIComponent(bundle.bundle_id))
      .then(function (data) {
        state.expanded[bundle.bundle_id] = true;
        cell.textContent = '';
        cell.appendChild(renderReportTable(data.reports || []));
      })
      .catch(function (e) {
        cell.textContent = '';
        cell.appendChild(el('p', 'hl-doc-note', '個票を読み込めませんでした: ' + e.message));
      });
  }

  function renderBundleRow(bundle) {
    var frag = document.createDocumentFragment();
    var tr = el('tr');
    var href = '/healing/bundles/' + encodeURIComponent(bundle.bundle_id);

    var tdToggle = el('td', 'hl-cell-toggle');
    var toggle = el('button', 'hl-btn hl-btn-sm hl-toggle', '▸');
    toggle.type = 'button';
    toggle.setAttribute('aria-label', '個票を開く');
    tdToggle.appendChild(toggle);
    tr.appendChild(tdToggle);

    var tdProject = el('td', 'hl-cell-name');
    tdProject.appendChild(el('b', null, bundle.project_name || '—'));
    if (bundle.target_url) { tdProject.appendChild(el('small', null, tailPath(bundle.target_url, 34))); }
    tr.appendChild(tdProject);

    var tdTitle = el('td', 'hl-cell-name');
    var titleLink = el('a', null, bundle.title || '（画面不明）');
    titleLink.href = href;
    tdTitle.appendChild(titleLink);
    if (bundle.review_reason) { tdTitle.appendChild(el('small', null, bundle.review_reason)); }
    tr.appendChild(tdTitle);

    var tdCount = el('td');
    tdCount.appendChild(el('b', null, bundle.count + ' 件'));
    if (bundle.awaiting_count > 0) {
      tdCount.appendChild(el('span', 'hl-badge is-warn hl-inline-badge', '承認待ち ' + bundle.awaiting_count));
    }
    tr.appendChild(tdCount);

    var tdVerify = el('td', null, '通過 ' + bundle.verify_after_ok_count + ' / ' + bundle.count);
    tr.appendChild(tdVerify);

    var tdAttention = el('td');
    tdAttention.appendChild(bundleAttentionCell(bundle));
    tr.appendChild(tdAttention);

    var tdWhen = el('td', 'hl-cell-when', relTime(bundle.updated_at));
    tdWhen.title = bundle.updated_at || '';
    tr.appendChild(tdWhen);

    var tdAction = el('td', 'hl-cell-action');
    var readBtn = el('button', 'hl-btn hl-btn-sm', '読む');
    readBtn.type = 'button';
    readBtn.addEventListener('click', function () { window.location.href = href; });
    tdAction.appendChild(readBtn);
    tr.appendChild(tdAction);

    ['', '案件', '画面 × 観点', '件数', '検証', '確認が必要な点', '更新', ''].forEach(function (lab, i) {
      if (lab && tr.children[i]) { tr.children[i].setAttribute('data-label', lab); }
    });

    frag.appendChild(tr);

    var holderRow = el('tr', 'hl-nested-row');
    holderRow.hidden = true;
    var holderCell = el('td');
    holderCell.colSpan = 8;
    holderRow.appendChild(holderCell);
    frag.appendChild(holderRow);

    toggle.addEventListener('click', function () { toggleBundleRow(bundle, toggle, holderRow); });

    return frag;
  }

  /* 「確認不要」束を、開くまで畳んでおく 1 行。一覧の既定表示（要確認のみ）の下に置く。
   * 開いたときの列は本文表と同じ（renderBundleRow を共用）。 */
  function ensureNoReviewHost() {
    var existing = document.getElementById('hl-no-review');
    if (existing) { return existing; }
    var table = document.getElementById('hl-reports-table');
    if (!table || !table.parentNode || !table.parentNode.parentNode) { return null; }
    var details = el('details', 'hl-collapse');
    details.id = 'hl-no-review';
    var summary = el('summary', 'hl-collapse-summary');
    summary.appendChild(el('span', 'hl-collapse-tri', '▸'));
    var label = el('span', null, '');
    label.id = 'hl-no-review-label';
    summary.appendChild(label);
    details.appendChild(summary);
    details.addEventListener('toggle', function () {
      var tri = details.querySelector('.hl-collapse-tri');
      if (tri) { tri.textContent = details.open ? '▾' : '▸'; }
    });
    var innerWrap = el('div', 'hl-table-wrap c-table-wrap');
    var innerTable = el('table', 'hl-reports-table c-table');
    innerTable.appendChild(table.querySelector('thead').cloneNode(true));
    var tbody = el('tbody');
    tbody.id = 'hl-no-review-body';
    innerTable.appendChild(tbody);
    innerWrap.appendChild(innerTable);
    details.appendChild(innerWrap);
    table.parentNode.insertAdjacentElement('afterend', details);
    return details;
  }

  function renderNoReviewCollapse() {
    var details = document.getElementById('hl-no-review');
    if (state.view !== 'needs_review') {
      if (details) { details.hidden = true; }
      return;
    }
    details = ensureNoReviewHost();
    if (!details) { return; }
    var bundles = state.allBundles.filter(function (b) { return bundleView(b) === 'no_review'; });
    details.hidden = bundles.length === 0;
    var label = document.getElementById('hl-no-review-label');
    if (label) { label.textContent = '確認の要らない束 ' + bundles.length + ' 件（テスト側の修正・検証済み）'; }
    var tbody = document.getElementById('hl-no-review-body');
    if (tbody) {
      tbody.textContent = '';
      bundles.forEach(function (b) { tbody.appendChild(renderBundleRow(b)); });
    }
  }

  function renderBundleList() {
    var body = document.getElementById('hl-reports-body');
    var empty = document.getElementById('hl-reports-empty');
    var table = document.getElementById('hl-reports-table');
    if (!body) { return; }
    body.textContent = '';
    var bundles = state.allBundles.filter(function (b) { return bundleView(b) === state.view; });
    var has = bundles.length > 0;
    if (table) { table.hidden = !has; }
    if (empty) {
      empty.hidden = has;
      if (!has) {
        var emptyText = state.view === 'needs_review'
          ? '要確認の報告書はありません。'
          : 'この状態の報告書はありません。';
        showState(empty, {
          kind: 'empty', title: emptyText,
          message: '報告書は、オートヒーリングの実行で修正案ができると並びます。',
          next: '実行の状況は「設定」の実行ビューで確認できます。'
        }, emptyText);
      }
    }
    var needN = state.allBundles.filter(function (b) { return bundleView(b) === 'needs_review'; }).length;
    var highN = state.allBundles.filter(function (b) { return bundleView(b) === 'needs_review' && b.attention_high > 0; }).length;
    renderHead({
      statusCode: needN > 0 ? 'waiting_approval' : 'done',
      statusLabel: needN > 0 ? '要確認 ' + needN + ' 件' : '要確認なし',
      reason: needN > 0
        ? '要確認の束が ' + needN + ' 件あります（うち重大な確認事項を含む束 ' + highN + ' 件）。束を開いて個票を読み、判断してください。'
        : '要確認の束はありません。確認不要・提出済みの束は、上の絞り込みから読めます。',
      reasonKind: needN > 0 ? 'warning' : 'info'
    });
    state.expanded = {};
    bundles.forEach(function (b) { body.appendChild(renderBundleRow(b)); });
    renderNoReviewCollapse();
  }

  /* 0 件のチップは出さない（該当 0 件の選択肢は並べない）。 */
  function renderChips() {
    var wrap = document.getElementById('hl-chips');
    if (!wrap) { return; }
    wrap.textContent = '';
    var counts = {};
    state.allBundles.forEach(function (b) { var v = bundleView(b); counts[v] = (counts[v] || 0) + 1; });
    var visible = VIEW_ORDER.filter(function (s) { return counts[s] > 0; });
    if (visible.length && visible.indexOf(state.view) === -1) { state.view = visible[0]; }
    visible.forEach(function (s) {
      var chip = el('button', 'hl-chip' + (s === state.view ? ' is-on' : ''),
        VIEW_LABELS[s] + ' ' + counts[s]);
      chip.type = 'button';
      chip.addEventListener('click', function () {
        state.view = s;
        renderChips();
        renderBundleList();
      });
      wrap.appendChild(chip);
    });
    if (!visible.length) {
      wrap.appendChild(el('span', 'hl-filter-label', '報告書はありません'));
    }
  }

  function loadBundleList() {
    clearError();
    var params = new URLSearchParams();
    if (state.projectId) { params.set('project_id', state.projectId); }
    var qs = params.toString();
    api('/api/healing/bundles' + (qs ? '?' + qs : ''))
      .then(function (data) {
        state.allBundles = data.bundles || [];
        renderChips();
        renderBundleList();
      })
      .catch(function (e) {
        showError('報告書を読み込めませんでした: ' + e.message);
        var empty = document.getElementById('hl-reports-empty');
        var kept = state.allBundles.length > 0;
        showState(empty, {
          kind: 'error', title: '報告書を読み込めませんでした', message: e.message,
          retained: kept, next: '通信を確認して、もう一度読み込んでください。',
          actionLabel: '再読み込み', onAction: loadBundleList
        }, '報告書を読み込めませんでした。' + e.message);
      });
  }

  function loadCount() {
    api('/api/healing/reports/count?status=awaiting')
      .then(function (data) {
        var badge = document.getElementById('hl-nav-count');
        if (!badge) { return; }
        var n = Number(data.count || 0);
        badge.textContent = n > 0 ? String(n) : '';
        badge.hidden = n === 0;
      })
      .catch(function () { /* バッジが出ないだけなので黙って諦める */ });
  }

  function loadProjects() {
    return api('/api/healing/projects')
      .then(function (data) {
        var sel = document.getElementById('hl-project-filter');
        if (!sel) { return []; }
        (data.projects || []).forEach(function (p) {
          var opt = el('option', null, p.name || p.project_id);
          opt.value = p.project_id;
          sel.appendChild(opt);
        });
        return data.projects || [];
      })
      .catch(function () { return null; /* 絞り込みが効かないだけ */ });
  }

  /* 指揮からの deep link（/healing?site=<domain>）。接続先の「サイト」が一致する対象が 1 つならそれを開く。
     一致しない・複数あるときは推測で選ばず、その旨を出して全件のまま見せる。 */
  var SITE_RE = /^[A-Za-z0-9.-]{1,253}(:\d{1,5})?$/;
  function siteParam() {
    var v = '';
    try { v = (new URLSearchParams(location.search).get('site') || '').trim(); } catch (e) { v = ''; }
    return SITE_RE.test(v) ? v : '';
  }
  function siteNotice(text, kind) {
    var host = document.getElementById('hl-site-notice');
    if (!host) { return; }
    if (hasWS()) { window.WS2D.reason(host, text, kind); } else { host.textContent = text; }
    host.hidden = false;
  }
  function applySite(site, projects) {
    if (projects === null) {
      siteNotice('サイト ' + site + ' の対象を確かめられませんでした（接続先の一覧を読めません）。すべての報告書を表示しています。', 'warning');
      return;
    }
    var key = site.toLowerCase();
    var hits = projects.filter(function (p) { return String(p.domain || '').toLowerCase() === key; });
    if (hits.length === 1) {
      state.projectId = hits[0].project_id;
      var sel = document.getElementById('hl-project-filter');
      if (sel) { sel.value = state.projectId; }
      siteNotice('指揮から開きました: サイト ' + site + ' の対象「' + (hits[0].name || hits[0].project_id) + '」の報告書だけを表示しています。', 'info');
      return;
    }
    siteNotice(hits.length > 1
      ? 'サイト ' + site + ' に対応する接続先が ' + hits.length + ' 件あります。推測では選んでいません。右の「案件」で選んでください。'
      : 'サイト ' + site + ' に対応する接続先は登録されていません。推測では選ばず、すべての報告書を表示しています。設定の接続先で「サイト」を登録すると、次から直接開けます。',
    'warning');
  }

  /* ---- 他ファイルへ公開 ---- */
  HL.STATUS_LABELS = STATUS_LABELS;
  HL.applySite = applySite;
  HL.loadBundleList = loadBundleList;
  HL.loadCount = loadCount;
  HL.loadProjects = loadProjects;
  HL.renderReportTable = renderReportTable;
  HL.siteParam = siteParam;
  HL.state = state;
})(window.HealingReports = window.HealingReports || {});
