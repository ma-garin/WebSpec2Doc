// ---- 実行履歴ビュー ----
// 種別タブは廃止した。5 タブのうち「現新比較」「UXレビュー」「スケジュール」は
// 実データが 0 件で、押しても「実行履歴がありません」しか出なかった。
// 「すべて」は別システム（AutoRun）の記録が混ざり、このシステムの分が埋もれていた。
// 種別は行のバッジで示し、絞り込みは要るときだけ開く。

const RH_TYPE_LABELS = {
  crawl: 'ドキュメント作成',
  testcase_run: 'テスト実行',
  autorun: 'AutoRun',
  comparison: '現新比較',
  ux_review: 'UXレビュー',
  schedule: 'スケジュール',
};
// 系ごとに扱う種別。相手システムの記録を混ぜない（旧「すべて」タブの問題）。
const RH_SYSTEM_TYPES = {
  docs: ['crawl', 'testcase_run', 'comparison', 'ux_review', 'schedule'],
  autorun: ['autorun'],
};
// これを超えたらページ送りを出す。下回るならスクロールで足りる。
const RH_PAGE_THRESHOLD = 50;
const RH_PAGE_SIZE = 25;

let _rhRuns = [];
const RH = { page: 1, site: '', from: '', to: '', status: '', type: '', sort: 'ts', dir: 'desc', open: false };

function _rhSystem() {
  return document.body.getAttribute('data-system') || 'docs';
}
// この系で扱う実行だけを対象にする。相手システムの記録は最初から持ち込まない。
function _rhScoped() {
  const allow = RH_SYSTEM_TYPES[_rhSystem()] || RH_SYSTEM_TYPES.docs;
  return _rhRuns.filter(r => allow.includes(r.type));
}

// ISO 形式のままでは読みにくいので整形する。解析に失敗したら元の文字列を返す
// （未加工の値を握りつぶさない）。
function _rhFormatTimestamp(raw, opts) {
  if (!raw) return '';
  const d = new Date(raw);
  if (isNaN(d.getTime())) return raw;
  const p = (n) => String(n).padStart(2, '0');
  const time = `${p(d.getHours())}:${p(d.getMinutes())}`;
  if (opts && opts.timeOnly) return time;
  return `${d.getFullYear()}/${p(d.getMonth() + 1)}/${p(d.getDate())} ${time}`;
}
function _rhDayKey(raw) {
  const d = new Date(raw);
  if (isNaN(d.getTime())) return '';
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
function _rhDayLabel(key) {
  const d = new Date(key + 'T00:00:00');
  if (isNaN(d.getTime())) return key;
  const w = ['日', '月', '火', '水', '木', '金', '土'][d.getDay()];
  return `${key.slice(5, 7)}/${key.slice(8, 10)}（${w}）`;
}
function _rhRelative(raw) {
  const d = new Date(raw);
  if (isNaN(d.getTime())) return '';
  const days = Math.round((Date.now() - d.getTime()) / 86400000);
  if (days <= 0) return '今日';
  if (days === 1) return '昨日';
  if (days < 30) return `${days}日前`;
  return `${Math.floor(days / 30)}か月前`;
}

function _rhStatusBadge(status) {
  if (status === 'complete') return '<span class="rh-status-badge rh-status-complete">完了</span>';
  if (status === 'failed') return '<span class="rh-status-badge rh-status-failed">失敗</span>';
  if (status === 'cancelled') return '<span class="rh-status-badge rh-status-cancelled">中断</span>';
  return '<span class="rh-status-badge rh-status-running">実行中</span>';
}

// 数値3列。種別ごとに意味が違うので、無い値は空欄にする（0 と混同させない）。
function _rhMetrics(run) {
  const s = run.summary || {};
  if (run.type === 'autorun' || run.type === 'testcase_run') {
    return { screens: '', conds: s.total ?? '', docs: s.passed ?? '' };
  }
  if (run.type === 'comparison' || run.type === 'ux_review') {
    return { screens: s.compare_screen_count ?? '', conds: s.finding_count ?? '', docs: '' };
  }
  if (run.type === 'schedule') {
    return { screens: '', conds: s.attempts ?? '', docs: '' };
  }
  return {
    screens: s.screen_count ?? '',
    conds: s.test_condition_count ?? '',
    docs: s.document_count ?? '',
  };
}

async function loadRunHistory() {
  const tbody = document.getElementById('rh-tbody');
  const empty = document.getElementById('rh-empty');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="8">読み込んでいます…</td></tr>';
  try {
    const res = await fetch('/api/history/runs');
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '実行履歴を取得できませんでした');
    _rhRuns = data.runs || [];
    RH.page = 1;
    _rhRenderAll();
  } catch (e) {
    tbody.innerHTML = '';
    if (empty) { empty.style.display = ''; empty.textContent = String(e.message); }
  }
}

function _rhFiltered() {
  return _rhScoped().filter(r =>
    (!RH.site || r.domain === RH.site) &&
    (!RH.type || r.type === RH.type) &&
    (!RH.status || r.status === RH.status) &&
    (!RH.from || _rhDayKey(r.timestamp) >= RH.from) &&
    (!RH.to || _rhDayKey(r.timestamp) <= RH.to));
}

function _rhSorted(list) {
  const dir = RH.dir === 'asc' ? 1 : -1;
  const metric = (r, k) => { const v = _rhMetrics(r)[k]; return v === '' ? -1 : Number(v); };
  const key = {
    ts: r => String(r.timestamp || ''),
    domain: r => String(r.domain || ''),
    screens: r => metric(r, 'screens'),
    conds: r => metric(r, 'conds'),
    docs: r => metric(r, 'docs'),
  }[RH.sort] || (r => String(r.timestamp || ''));
  return [...list].sort((a, b) => {
    const x = key(a), y = key(b);
    // 同値は必ず新しい順。並びが描き直すたびに変わると、見ている行を見失う。
    if (x === y) return String(a.timestamp) < String(b.timestamp) ? 1 : -1;
    return (x > y ? 1 : -1) * dir;
  });
}

// 日付区切りは「日時順に並んでいる」ことが前提。別の列で並べ替えたら成り立たない。
const _rhGrouping = () => RH.sort === 'ts';

function _rhActiveCount() {
  return [RH.site, RH.from, RH.to, RH.status, RH.type].filter(Boolean).length;
}

function _rhSet(key, value) {
  RH[key] = value;
  RH.page = 1;
  _rhRenderAll();
}
function _rhClear() {
  RH.site = ''; RH.from = ''; RH.to = ''; RH.status = ''; RH.type = '';
  RH.page = 1;
  _rhRenderAll();
}
function _rhSortBy(col) {
  if (RH.sort === col) RH.dir = RH.dir === 'desc' ? 'asc' : 'desc';
  else { RH.sort = col; RH.dir = col === 'domain' ? 'asc' : 'desc'; }
  RH.page = 1;
  _rhRenderAll();
}

function _rhRenderAll() {
  _rhRenderHead();
  _rhRenderFilter();
  _rhRenderApplied();
  _rhRenderSortIndicators();
  _rhRenderTable();
}

function _rhRenderHead() {
  const scoped = _rhScoped();
  const list = _rhFiltered();
  const n = _rhActiveCount();
  const countEl = document.getElementById('rh-count');
  const subEl = document.getElementById('rh-sub');
  const btn = document.getElementById('rh-filter-btn');
  if (countEl) {
    countEl.innerHTML = `${list.length.toLocaleString()}<span>件の実行`
      + (n ? `（全 ${scoped.length.toLocaleString()} 件中）` : '') + '</span>';
  }
  if (subEl) {
    const sites = new Set(scoped.map(r => r.domain)).size;
    const last = scoped.length ? _rhRelative(scoped[0].timestamp) : '';
    subEl.textContent = scoped.length ? `${sites} サイト ／ 最終 ${last}` : '';
  }
  if (btn) {
    btn.textContent = RH.open ? '絞り込みを閉じる' : '絞り込み';
    if (n) btn.innerHTML += `<span class="rh-filter-n">${n}</span>`;
    btn.setAttribute('aria-expanded', RH.open ? 'true' : 'false');
  }
  const panel = document.getElementById('rh-filter');
  if (panel) panel.hidden = !RH.open;
}

function _rhChip(label, count, on, action) {
  return `<button type="button" class="rh-chip${on ? ' is-on' : ''}" data-act="${escHtml(action)}">`
    + `${escHtml(label)}<span class="rh-chip-n">${count}</span></button>`;
}

function _rhRenderFilter() {
  if (!RH.open) return;
  const scoped = _rhScoped();
  const siteHost = document.getElementById('rh-site-chips');
  const statusHost = document.getElementById('rh-status-chips');
  const typeHost = document.getElementById('rh-type-chips');

  if (siteHost) {
    const sites = [...new Set(scoped.map(r => r.domain))].filter(Boolean);
    siteHost.innerHTML = _rhChip('すべて', scoped.length, RH.site === '', 'site:')
      + sites.map(s => _rhChip(s, scoped.filter(r => r.domain === s).length, RH.site === s, 'site:' + s)).join('');
  }
  if (statusHost) {
    // 該当 0 件の状態は選択肢に出さない（押しても何も出ない選択肢を並べない）
    const present = ['complete', 'failed', 'cancelled']
      .map(s => [s, scoped.filter(r => r.status === s).length])
      .filter(([, c]) => c > 0);
    const label = { complete: '完了', failed: '失敗', cancelled: '中断' };
    statusHost.innerHTML = _rhChip('すべて', scoped.length, RH.status === '', 'status:')
      + present.map(([s, c]) => _rhChip(label[s], c, RH.status === s, 'status:' + s)).join('');
  }
  if (typeHost) {
    // 記録がある種別だけ出す。0 件の種別をタブで並べていたのが元の問題。
    const present = [...new Set(scoped.map(r => r.type))]
      .map(t => [t, scoped.filter(r => r.type === t).length])
      .filter(([, c]) => c > 0);
    typeHost.innerHTML = present.length > 1
      ? _rhChip('すべて', scoped.length, RH.type === '', 'type:')
        + present.map(([t, c]) => _rhChip(RH_TYPE_LABELS[t] || t, c, RH.type === t, 'type:' + t)).join('')
      : present.map(([t, c]) => _rhChip(RH_TYPE_LABELS[t] || t, c, true, 'type:')).join('');
  }
  const from = document.getElementById('rh-from');
  const to = document.getElementById('rh-to');
  if (from) from.value = RH.from;
  if (to) to.value = RH.to;
}

function _rhRenderApplied() {
  const host = document.getElementById('rh-applied');
  if (!host) return;
  const tags = [];
  if (RH.site) tags.push(['サイト: ' + RH.site, 'site:']);
  if (RH.type) tags.push([RH_TYPE_LABELS[RH.type] || RH.type, 'type:']);
  if (RH.status) tags.push([{ complete: '完了のみ', failed: '失敗のみ', cancelled: '中断のみ' }[RH.status] || RH.status, 'status:']);
  if (RH.from) tags.push([RH.from + ' 以降', 'from:']);
  if (RH.to) tags.push([RH.to + ' 以前', 'to:']);
  host.hidden = !tags.length;
  if (!tags.length) return;
  host.innerHTML = '<span class="muted-copy">絞り込み中:</span>'
    + tags.map(([t, act]) => `<span class="rh-tag">${escHtml(t)}`
      + `<button type="button" data-act="${escHtml(act)}" aria-label="${escHtml(t)} を外す">×</button></span>`).join('')
    + '<button type="button" class="btn-outline-sm" data-act="clear">すべて解除</button>';
}

function _rhRenderSortIndicators() {
  document.querySelectorAll('#view-run-history .rh-sortable').forEach(th => {
    const on = th.dataset.sort === RH.sort;
    th.classList.toggle('is-sorted', on);
    const arrow = th.querySelector('.rh-arrow');
    if (arrow) arrow.textContent = on ? (RH.dir === 'asc' ? '▲' : '▼') : '⇅';
    th.setAttribute('aria-sort', on ? (RH.dir === 'asc' ? 'ascending' : 'descending') : 'none');
  });
}

function _rhRenderTable() {
  const tbody = document.getElementById('rh-tbody');
  const empty = document.getElementById('rh-empty');
  const pager = document.getElementById('rh-pager');
  if (!tbody) return;

  const list = _rhSorted(_rhFiltered());
  if (pager) pager.innerHTML = '';
  if (!list.length) {
    tbody.innerHTML = '';
    if (empty) {
      empty.style.display = '';
      empty.innerHTML = _rhActiveCount()
        ? '条件に合う実行がありません。<button type="button" class="btn-outline-sm" data-act="clear" style="margin-left:10px">絞り込みを解除</button>'
        : '実行履歴がありません。';
    }
    return;
  }
  if (empty) empty.style.display = 'none';

  const usePager = list.length > RH_PAGE_THRESHOLD;
  let items = list;
  if (usePager) {
    const info = TableUtils.paginate(list, RH.page, RH_PAGE_SIZE);
    RH.page = info.page;
    items = info.items;
    if (pager) pager.innerHTML = TableUtils.pagerHtml(info);
  }

  const counts = {};
  if (_rhGrouping()) list.forEach(r => { const d = _rhDayKey(r.timestamp); counts[d] = (counts[d] || 0) + 1; });

  let html = '', lastDay = '';
  items.forEach(run => {
    if (_rhGrouping()) {
      const day = _rhDayKey(run.timestamp);
      if (day && day !== lastDay) {
        lastDay = day;
        html += `<tr class="rh-day"><td colspan="8">${escHtml(_rhDayLabel(day))}`
          + `<span class="rh-day-n">${counts[day]}件</span></td></tr>`;
      }
    }
    const m = _rhMetrics(run);
    const label = run.type_label || RH_TYPE_LABELS[run.type] || run.type;
    // 操作は「開く」1種類に統一する。押した先が「その回」か「最新」かは行の状態で、
    // 操作の種類ではない。その回の成果物が無いことは日時の下に添える。
    const hasRun = !!run.result_url;
    const openAttrs = hasRun
      ? `data-act="run:${escHtml(run.domain)}|${escHtml(run.run_id)}"`
      : (run.report_url ? `data-act="url:${escHtml(run.report_url)}"`
        : (run.link ? `data-act="file:${escHtml(run.link)}|${escHtml(label)} - ${escHtml(run.domain)}"` : ''));
    // 日時セルは1行に収める。文言は短く、意味は title で補う。
    const noSave = hasRun ? ''
      : '<span class="rh-nosave" title="この実行回の成果物は保存されていません（開くと最新が出ます）">・成果物なし</span>';
    const openBtn = openAttrs
      ? `<button type="button" class="btn-outline-sm${hasRun ? ' rh-open-primary' : ''}" ${openAttrs}>開く</button>`
      : '<span class="muted-copy">—</span>';
    html += `<tr${openAttrs ? ' ' + openAttrs : ''}>
      <td><span class="rh-type-badge rh-type-${escHtml(run.type)}">${escHtml(label)}</span></td>
      <td class="rh-site" title="${escHtml(run.domain)}">${escHtml(run.domain)}</td>
      <td class="num">${escHtml(_rhFormatTimestamp(run.timestamp, { timeOnly: _rhGrouping() }))}
        <div class="muted-copy">${escHtml(_rhRelative(run.timestamp))}${noSave}</div></td>
      <td>${_rhStatusBadge(run.status)}</td>
      <td class="num rh-num">${escHtml(String(m.screens))}</td>
      <td class="num rh-num">${escHtml(String(m.conds))}</td>
      <td class="num rh-num">${escHtml(String(m.docs))}</td>
      <td>${openBtn}</td>
    </tr>`;
  });
  tbody.innerHTML = html;
}

// ---- 操作（イベント委譲。行の描き直しでハンドラを付け直さない） ----
function _rhDispatch(act) {
  if (!act) return;
  if (act === 'clear') { _rhClear(); return; }
  const [kind, rest = ''] = [act.slice(0, act.indexOf(':')), act.slice(act.indexOf(':') + 1)];
  if (kind === 'site') { _rhSet('site', rest); return; }
  if (kind === 'type') { _rhSet('type', rest); return; }
  if (kind === 'status') { _rhSet('status', rest); return; }
  if (kind === 'from') { _rhSet('from', rest); return; }
  if (kind === 'to') { _rhSet('to', rest); return; }
  if (kind === 'run') {
    const [domain, runId] = rest.split('|');
    if (typeof openRunResult === 'function') openRunResult(domain, runId);
    return;
  }
  if (kind === 'url') { location.href = rest; return; }
  if (kind === 'file') {
    const [path, label] = rest.split('|');
    if (typeof openFilePreview === 'function') openFilePreview(path, label);
    else window.open('/preview?path=' + encodeURIComponent(path), '_blank');
  }
}

document.getElementById('view-run-history')?.addEventListener('click', (e) => {
  const th = e.target.closest('.rh-sortable');
  if (th) { _rhSortBy(th.dataset.sort); return; }
  const range = e.target.closest('[data-range]');
  if (range) {
    const days = Number(range.dataset.range);
    const d = new Date(Date.now() - days * 86400000);
    const p = (n) => String(n).padStart(2, '0');
    RH.from = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    RH.to = '';
    RH.page = 1;
    _rhRenderAll();
    return;
  }
  const acted = e.target.closest('[data-act]');
  if (acted) { e.stopPropagation(); _rhDispatch(acted.dataset.act); return; }
  // 行のどこを押しても開く（ボタンを狙わせない）
  const row = e.target.closest('#rh-tbody tr[data-act]');
  if (row) _rhDispatch(row.dataset.act);
});

document.getElementById('rh-filter-btn')?.addEventListener('click', () => {
  RH.open = !RH.open;
  _rhRenderAll();
});
document.getElementById('rh-reload-btn')?.addEventListener('click', loadRunHistory);
document.getElementById('rh-from')?.addEventListener('change', (e) => _rhSet('from', e.target.value));
document.getElementById('rh-to')?.addEventListener('change', (e) => _rhSet('to', e.target.value));
document.getElementById('rh-pager')?.addEventListener('click', (e) => {
  const page = TableUtils.pageFromClick(e);
  if (page === null || page === RH.page) return;
  RH.page = page;
  _rhRenderTable();
});
