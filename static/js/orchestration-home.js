/* 指揮ホーム（日常運用）。全サイトの状態を /api/home/summary 1 本で出す。
 * 部品は window.WS2D（c-hybrid.js）。文字は textContent で入れる。 */
(function () {
  'use strict';
  if (document.body.getAttribute('data-mode') !== 'home') { return; }
  var W = window.WS2D;
  var VIEWS = [
    { key: 'all', label: 'すべて' }, { key: 'human', label: '人の対応待ち' },
    { key: 'failed', label: '失敗' }, { key: 'unverified', label: '未確認' }
  ];
  var SOURCE_NAME = {
    sites: 'サイト一覧', runs: '実行記録', projects: '保守プロジェクト', reports: '報告書',
    failures: '失敗テスト', evidence: '根拠（リバース解析）'
  };
  var STAGE_NONE = '—';
  var IS_ADMIN = document.body.getAttribute('data-hl-admin') === 'true';
  var data = null;
  var view = 'all';

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text !== undefined && text !== null) { n.textContent = text; }
    return n;
  }
  function clear(n) { while (n.firstChild) { n.removeChild(n.firstChild); } }
  function viewFromLocation() {
    var v = new URLSearchParams(window.location.search).get('view') || 'all';
    return VIEWS.some(function (x) { return x.key === v; }) ? v : 'all';
  }
  function fmtAt(ts) {
    if (!ts) { return '—'; }
    var m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(ts);
    return m ? (m[2] + '/' + m[3] + ' ' + m[4] + ':' + m[5]) : ts;
  }

  /* サーバの filter_sites と同じ条件（絞り込みはクライアントで行う）。 */
  function filterSites(sites, v) {
    return sites.filter(function (s) {
      if (v === 'human') { return !!s.human_action; }
      if (v === 'failed') { return s.status === 'failed' || !!s.latest_failure; }
      if (v === 'unverified') {
        return s.status === 'unverified' || !s.evidence || s.evidence.unverified > 0;
      }
      return true;
    });
  }

  function setView(v, push) {
    view = v;
    var url = new URL(window.location.href);
    if (v === 'all') { url.searchParams.delete('view'); } else { url.searchParams.set('view', v); }
    if (push) { window.history.pushState({ view: v }, '', url.toString()); }
    renderTabs();
    renderList();
  }

  /* ---------- 帯・KPI ---------- */

  function renderSplit() {
    var host = $('ch-split');
    clear(host);
    var sum = { fact: 0, inference: 0, unverified: 0 };
    var any = false;
    (data.sites || []).forEach(function (s) {
      if (s.evidence) {
        any = true;
        sum.fact += s.evidence.fact; sum.inference += s.evidence.inference; sum.unverified += s.evidence.unverified;
      }
    });
    [['fact', '事実（実測・記録）'], ['inference', '推論（文書・静的・推論）'], ['unverified', '未確認（曖昧・未確認・利用不可）']].forEach(function (c) {
      var cell = el('div', 'c-split__cell c-split__cell--' + c[0]);
      cell.appendChild(el('span', 'c-split__label', c[1]));
      cell.appendChild(el('span', 'c-split__value', any ? String(sum[c[0]]) : '未計測'));
      host.appendChild(cell);
    });
  }

  function renderKpis() {
    var c = data.counts || {};
    function go(v) { return function () { setView(v, true); var b = $('ch-body'); if (b) { b.focus(); } }; }
    var items = [
      { label: '全サイト', value: c.sites, onClick: go('all') },
      { label: '正常', value: c.ok, sub: '完了のみ。一部完了は含めない' },
      { label: '実行中', value: c.running },
      { label: '失敗', value: c.failed, onClick: go('failed') },
      { label: '人の対応待ち', value: c.human_action, onClick: go('human') },
      { label: '承認待ち', value: c.awaiting_approval, sub: '修正案の報告書', onClick: go('human') },
      { label: '未確認', value: c.unverified, category: 'unverified', onClick: go('unverified'),
        sub: '根拠の件数（解析結果があるサイトのみ）' + (c.unanalyzed ? '。未解析 ' + c.unanalyzed + ' サイト' : '') },
      { label: '今日の変更', value: c.changes_today, sub: '集計元なし' },
      { label: '今日のテスト', value: c.tests_today, sub: '実行の回数' },
      { label: '今日の修正', value: c.fixes_today, sub: '直す工程の回数' },
      { label: '今日の報告', value: c.reports_today }
    ];
    W.kpis($('ch-kpis'), items);
  }

  function renderReason() {
    var c = data.counts || {};
    var text;
    if (c.sites === null || c.sites === undefined) {
      text = 'サイト一覧を取得できていません。数字は未計測です。';
    } else if (c.sites === 0) {
      text = 'サイトがまだありません。追加すると、ここに状態が並びます。';
    } else {
      var parts = [c.sites + ' サイト'];
      if (c.failed) { parts.push('失敗 ' + c.failed); }
      if (c.human_action) { parts.push('人の対応待ち ' + c.human_action); }
      if (!c.failed && !c.human_action) { parts.push('失敗・対応待ちはありません'); }
      text = parts.join(' ／ ') + '（' + fmtAt(data.updated_at) + ' 時点）';
    }
    W.reason($('ch-reason'), text, (data.partial_errors || []).length ? 'warning' : undefined);
  }

  function renderBanner(errorInfo) {
    var host = $('ch-banner');
    clear(host);
    if (errorInfo) {
      W.state(host, { kind: 'error', title: '最新の状態を取得できませんでした', message: errorInfo,
        retained: !!data, next: '再読み込みを押してください。', actionLabel: '再読み込み', onAction: load });
      return;
    }
    var errs = (data && data.partial_errors) || [];
    if (errs.length) {
      var names = errs.map(function (e) { return SOURCE_NAME[e] || e; }).join('・');
      W.state(host, { kind: 'partial', message: '取得できなかった情報: ' + names + '。該当する数字は「未計測」と表示しています。',
        next: '時間をおいて再読み込みしてください。', actionLabel: '再読み込み', onAction: load });
    }
  }

  /* ---------- タブ・表 ---------- */

  function renderTabs() {
    var host = $('ch-tabs');
    clear(host);
    VIEWS.forEach(function (v, i) {
      var b = el('button', null, v.label);
      b.type = 'button';
      b.setAttribute('role', 'tab');
      b.id = 'ch-tab-' + v.key;
      b.setAttribute('aria-selected', v.key === view ? 'true' : 'false');
      b.setAttribute('aria-controls', 'ch-body');
      b.tabIndex = v.key === view ? 0 : -1;
      if (data) {
        b.appendChild(el('span', 'ch-tab-n', ' ' + filterSites(data.sites || [], v.key).length));
      }
      b.addEventListener('click', function () { setView(v.key, true); });
      b.addEventListener('keydown', function (ev) {
        var d = ev.key === 'ArrowRight' ? 1 : (ev.key === 'ArrowLeft' ? -1 : 0);
        if (!d) { return; }
        ev.preventDefault();
        var next = VIEWS[(i + d + VIEWS.length) % VIEWS.length];
        setView(next.key, true);
        var t = $('ch-tab-' + next.key);
        if (t) { t.focus(); }
      });
      host.appendChild(b);
    });
    $('ch-body').setAttribute('aria-labelledby', 'ch-tab-' + view);
  }

  function cell(tr, label, node) {
    var td = el('td');
    td.setAttribute('data-label', label);
    if (typeof node === 'string') { td.textContent = node; } else if (node) { td.appendChild(node); }
    tr.appendChild(td);
    return td;
  }
  function badge(html) { var s = el('span'); s.innerHTML = html; return s; }

  function evidenceCell(ev) {
    var box = el('span', 'ch-ev');
    if (!ev) { box.appendChild(badge(W.evidence.html('unverified', '未確認（解析結果なし）'))); return box; }
    box.appendChild(badge(W.evidence.html('observed', '事実 ' + ev.fact)));
    box.appendChild(badge(W.evidence.html('inferred', '推論 ' + ev.inference)));
    box.appendChild(badge(W.evidence.html('unverified', '未確認 ' + ev.unverified)));
    return box;
  }

  function linkCell(site) {
    var box = el('span', 'ch-links');
    /* [キー, 番号, 名前, サイトを開いた状態で開けるか]。03・09・05 は入口へ行き、画面でサイトを選ぶ */
    [['s01', '01', 'ドキュメント作成', true], ['s02', '02', 'テスト自動化', true], ['s03', '03', 'AutoRun', false],
     ['s09', '09', '影響度分析', false], ['s05', '05', 'オートヒーリング', false]].forEach(function (p) {
      var href = site.links && site.links[p[0]];
      if (href) {
        var a = el('a', null, p[1]);
        a.href = href;
        var what = 'System ' + p[1] + ' ' + p[2] + ' を開く';
        a.title = what + (p[3] ? '' : '（サイトは開いた画面で選びます）');
        a.setAttribute('aria-label', what + (p[3] ? '（' + site.domain + '）' : '（入口。サイトは画面で選びます）'));
        box.appendChild(a);
      } else {
        var m = el('span', 'ch-link-off', p[1]);
        m.title = 'System ' + p[1] + ' ' + p[2] + ': 解析結果が無いため開けません';
        m.appendChild(el('span', 'ch-sr', '（' + p[2] + '。解析結果が無いため開けません）'));
        box.appendChild(m);
      }
    });
    var d = el('a', 'ch-detail', '詳細');
    d.href = '/orchestration?site=' + encodeURIComponent(site.domain);
    d.setAttribute('aria-label', '個別実行詳細を開く（' + site.domain + '）');
    box.appendChild(d);
    return box;
  }

  /* 状態の理由（「なぜこの状態か」）。サーバが返した記録だけから文にする。推測は入れない */
  function whyState(s) {
    var st = s.status;
    if (st === 'failed') { return (s.latest_failure && s.latest_failure.text) || '失敗が記録されていますが、内容の記録は取得できていません。'; }
    if (st === 'waiting_approval' || st === 'waiting_review') {
      return (s.human_action && s.human_action.text) || '人の判断を待つ状態として記録されています。';
    }
    if (st === 'running') { return '実行記録で' + (s.stage ? '工程「' + s.stage.label + '」' : '工程') + 'が進行中です。'; }
    if (st === 'not_started') { return '指揮の実行記録がありません。解析結果の有無とは別です。'; }
    if (st === 'done') { return '全工程が完了として記録されています。内容の正しさまでは確認していません。'; }
    if (st === 'partial') { return '一部の工程だけが完了として記録されています。成功ではありません。'; }
    return '状態「' + W.status.label(st) + '」として記録されています。';
  }

  function openWhy(s, opener) {
    var ev = s.evidence;
    var facts = [{ label: '現在の状態', value: W.status.label(s.status) }, { label: '現在の工程', value: s.stage ? s.stage.label : STAGE_NONE },
      { label: '最終実行', value: s.last_run ? fmtAt(s.last_run.at) : '実行なし' }];
    if (ev) { facts.push({ label: '根拠の件数', value: '事実 ' + ev.fact + ' / 推論 ' + ev.inference + ' / 未確認 ' + ev.unverified }); }
    var inf = ev ? ['根拠の ' + ev.inference + ' 件は推論です（実測ではありません）。'] : [];
    var lim = ['状態は指揮の実行記録から出しています。サイトの機能が正しく動くことを示すものではありません。'];
    if (!ev) { lim.push('解析結果が無いため、根拠の件数は未確認です。'); }
    var loc = [{ label: 'サイト', value: s.domain }];
    if (s.human_action && s.human_action.href) { loc.push({ label: '対応する画面', value: s.human_action.href }); }
    if (s.latest_failure && s.latest_failure.href) { loc.push({ label: '失敗の詳細', value: s.latest_failure.href }); }
    var extra = el('a', 'c-btn c-btn--secondary c-btn--sm', '個別実行詳細を開く');
    extra.href = '/orchestration?site=' + encodeURIComponent(s.domain);
    W.drawer.open({
      title: (s.label || s.domain) + ' の状態の根拠', state: s.status, stateReason: whyState(s),
      claim: 'このサイトの状態は「' + W.status.label(s.status) + '」です。',
      facts: facts, inferences: inf, limitations: lim,
      sources: [{ label: '出典', value: '指揮の実行記録・サイト一覧' + (ev ? '・リバース解析の結果' : '') }],
      location: loc, provider: [{ label: 'Provider / version', value: ev ? 'WebSpec2Doc Native Analyzer（version は記録なし）' : '解析なし' }],
      extra: extra, returnFocus: opener
    });
  }

  function textOrNone(item) {
    if (!item) { return '—'; }
    var box = el('span');
    var t = item.text || '';
    if (item.href) {
      var a = el('a', null, t);
      a.href = item.href;
      box.appendChild(a);
    } else { box.textContent = t; }
    return box;
  }

  function renderList() {
    var host = $('ch-body');
    clear(host);
    var c = data.counts || {};
    if (c.sites === 0 && !(data.partial_errors || []).length) {
      W.state(host, { kind: 'empty', title: 'サイトがまだありません', message: '見張りたいサイトを追加すると、状態がここに並びます。',
        next: IS_ADMIN ? '「サイトを追加」から URL を入れてください。' : 'サイトの追加は管理者の操作です。管理者に依頼してください。',
        actionLabel: IS_ADMIN ? 'サイトを追加' : undefined,
        onAction: IS_ADMIN ? function () { window.location.href = '/orchestration?mode=detail'; } : undefined });
      return;
    }
    var rows = filterSites(data.sites || [], view);
    if (!rows.length) {
      W.state(host, { kind: 'empty', title: 'この条件に当てはまるサイトはありません',
        message: (data.sites || []).length ? '' : 'サイト一覧を取得できていません。',
        next: view === 'all' ? '再読み込みしてください。' : '「すべて」のタブで全サイトを確認できます。',
        actionLabel: view === 'all' ? '再読み込み' : 'すべてを見る',
        onAction: function () { if (view === 'all') { load(); } else { setView('all', true); } } });
      return;
    }
    var wrap = el('div', 'c-table-wrap');
    var table = el('table', 'c-table');
    /* 何の記録から出した値かを表の上に書く（指揮の未実行を「未解析」と取り違えさせない） */
    var cap = el('caption', 'ch-cap', 'サイトごとの状態。状態・工程・最終実行は指揮の実行記録、根拠の健全性はリバース解析の結果から。');
    table.appendChild(cap);
    var head = el('tr');
    ['サイト・各 System へ', '現在の状態', '現在の工程', '最終実行', '根拠の健全性', '人の対応待ち', '最新の変更', '最新の失敗'].forEach(function (h) {
      var th = el('th', null, h); th.scope = 'col'; head.appendChild(th);
    });
    var thead = el('thead'); thead.appendChild(head); table.appendChild(thead);
    var tbody = el('tbody');
    rows.forEach(function (s) {
      var tr = el('tr');
      /* deep link はサイト名の直下に置く（列が増えて右端に隠れないように） */
      var site = el('div', 'ch-site');
      var nameRow = el('div', 'ch-site__name');
      nameRow.appendChild(el('strong', null, s.label || s.domain));
      var why = el('button', 'c-btn c-btn--ghost c-btn--sm ch-why', '根拠');
      why.type = 'button';
      why.setAttribute('aria-label', (s.label || s.domain) + ' の状態の根拠を開く（なぜこの状態か）');
      why.addEventListener('click', function () { openWhy(s, why); });
      nameRow.appendChild(why);
      site.appendChild(nameRow);
      site.appendChild(linkCell(s));
      cell(tr, 'サイト', site);
      cell(tr, '現在の状態', badge(W.status.html(s.status)));
      cell(tr, '現在の工程', s.stage ? s.stage.label : STAGE_NONE);
      cell(tr, '最終実行', s.last_run ? fmtAt(s.last_run.at) : '実行なし');
      cell(tr, '根拠の健全性', evidenceCell(s.evidence));
      cell(tr, '人の対応待ち', textOrNone(s.human_action));
      cell(tr, '最新の変更', textOrNone(s.latest_change));
      cell(tr, '最新の失敗', textOrNone(s.latest_failure));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    host.appendChild(wrap);
  }

  /* ---------- 取得 ---------- */

  function render() {
    renderReason(); renderBanner(null); renderSplit(); renderKpis(); renderTabs(); renderList();
  }

  function load() {
    if (!data) { W.state($('ch-body'), { kind: 'loading', message: '全サイトの状態を集めています。' }); }
    fetch('/api/home/summary', { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          if (!res.ok || !body || !body.counts) { throw new Error((body && body.error) || (res.status === 401 ? 'ログインの有効期限が切れました。' : res.status === 403 ? 'この一覧を見る権限がありません。' : 'サーバから状態を取得できませんでした。')); }
          return body;
        });
      })
      .then(function (body) { data = body; render(); })
      .catch(function (err) {
        if (data) { renderBanner(String(err.message || err)); return; }
        W.reason($('ch-reason'), '状態を取得できていません。数字は未計測です。', 'warning');
        W.state($('ch-body'), { kind: 'error', message: String(err.message || err),
          next: '再読み込みを押してください。', actionLabel: '再読み込み', onAction: load });
      });
  }

  function init() {
    if (!W || !$('ch-body')) { return; }
    view = viewFromLocation();
    if (!IS_ADMIN) {
      /* サイト追加は管理者だけ（押しても 403 になる操作を出さない） */
      var add = document.querySelector('.c-page-head__actions a[href*="mode=detail"]');
      if (add && add.parentNode) { add.parentNode.removeChild(add); }
    }
    renderTabs();
    $('ch-reload').addEventListener('click', load);
    window.addEventListener('popstate', function () {
      view = viewFromLocation();
      if (data) { renderTabs(); renderList(); }
    });
    load();
  }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }
  window.__chHome = { filterSites: filterSites, setView: setView };
})();
