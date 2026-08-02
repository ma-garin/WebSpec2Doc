// ---- 実行結果ページ（実行回のハブ・案A） ----
// 実行履歴の 1 行 = 1 実行回。ここで開くのは「その回の成果物」であって、
// サイトの最新の成果物ではない。保存されていない回は最新で代替せず「無い」と出す。
//
// 3 つの成果物（利用者の呼び方）:
//   1 実行結果        report.json    画面・仕様・条件・ケース
//   2 解析結果        report.html    テスト分析インプット（静的HTML）
//   3 実行結果レポート qa_process/    AutoRun の 8 セクション

const RR_ARTIFACTS = [
  { key: 'result', n: '1', label: '実行結果', desc: '画面と仕様・テスト条件・テストケース', file: 'report.json' },
  { key: 'analysis', n: '2', label: '解析結果', desc: 'テスト分析インプット（アーキテクチャ図・技術スタック）', file: 'report.html' },
  { key: 'autorun', n: '3', label: '実行結果レポート', desc: 'QA仕様書・計画・分析・設計・ケース・スクリプト・実行結果', file: 'qa_process/' },
];

let _rrDomain = '';
let _rrRunId = '';
let _rrDetail = null;
let _rrRuns = [];
let _rrTab = 'result';

// run_id は「20260802-113000」。人が読める形に直す（別途 UUID を持たせていない）。
function _rrRunLabel(runId) {
  const m = String(runId || '').match(/^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})(?:-(\d+))?$/);
  if (!m) return runId;
  const dup = m[7] ? `（同秒 ${m[7]}）` : '';
  return `${m[1]}/${m[2]}/${m[3]} ${m[4]}:${m[5]}:${m[6]}${dup}`;
}

async function openRunResult(domain, runId) {
  _rrDomain = domain;
  _rrRunId = runId;
  _rrTab = 'result';
  // switchView 側の pushState は使わない（この画面のURLは /runs/<domain>/<run_id> で、
  // VIEW_PATHS の固定パスに乗らないため。任せると '/' が余分に積まれる）
  switchView('run-result', { skipHistory: true });
  setHeader(['ダッシュボード', '実行履歴', domain], `実行結果 — ${domain}`);
  const target = `/runs/${encodeURIComponent(domain)}/${encodeURIComponent(runId)}`;
  try {
    if (location.pathname !== target) history.pushState({ view: 'run-result' }, '', target);
  } catch (e) { /* 履歴が触れなくても表示は成立する */ }
  await _rrLoad();
}

async function _rrLoad() {
  const bar = document.getElementById('rr-runbar');
  const body = document.getElementById('rr-body');
  if (!bar || !body) return;
  bar.innerHTML = '<div class="rr-loading">実行回を読み込んでいます…</div>';
  document.getElementById('rr-artifacts').innerHTML = '';
  _rrClearBody();

  // 実行回セレクタの選択肢は同じサイトなら変わらない。回を切り替えるたびに
  // 一覧を取り直すと、N 件を順に辿るだけで一覧取得が N 回走る。
  // 同じサイトを見ている間はクライアント側で使い回す。
  const needRuns = !_rrRuns.length || _rrRuns[0].domain !== _rrDomain;
  const [runsRes, detailRes] = await Promise.all([
    needRuns
      ? fetch(`/api/runs/${encodeURIComponent(_rrDomain)}`).then(r => r.ok ? r.json() : null).catch(() => null)
      : Promise.resolve(null),
    fetch(`/api/runs/${encodeURIComponent(_rrDomain)}/${encodeURIComponent(_rrRunId)}`)
      .then(async r => ({ ok: r.ok, data: await r.json() })).catch(() => null),
  ]);

  if (needRuns) _rrRuns = (runsRes && runsRes.runs) || [];
  if (!detailRes) {
    uiError(body, {
      title: '実行回を取得できませんでした',
      message: '通信状態を確認して、もう一度お試しください。',
      onRetry: _rrLoad,
    });
    _rrRenderRunbar();
    return;
  }
  if (!detailRes.ok) {
    _rrDetail = null;
    _rrRenderRunbar();
    _rrRenderMissingRun(detailRes.data || {});
    return;
  }
  _rrDetail = detailRes.data;
  _rrRenderRunbar();
  _rrRenderArtifactTabs();
  _rrRenderBody();
}

// 保存されていない実行回。最新の成果物で埋めない（別の実行の中身を、この実行の
// ものとして見せないため）。何が無いのかと、なぜ無いのかを書く。
function _rrRenderMissingRun(payload) {
  document.getElementById('rr-artifacts').innerHTML = '';
  document.getElementById('rr-notice').innerHTML = '';
  _rrSetBody(
    '<div class="rr-missing">'
    + `<strong>${escHtml(payload.error || 'この実行回の成果物は保存されていません')}</strong>`
    + `<p>${escHtml(payload.recovery || '')}</p>`
    + '</div>');
}

function _rrRenderRunbar() {
  const bar = document.getElementById('rr-runbar');
  if (!bar) return;
  const d = _rrDetail;
  const options = _rrRuns.map(r => {
    const id = String(r.run_id || '');
    const cur = _rrRuns[0] && String(_rrRuns[0].run_id) === id ? '（現在）' : '';
    return `<option value="${escHtml(id)}"${id === _rrRunId ? ' selected' : ''}>${escHtml(_rrRunLabel(id))}${cur}</option>`;
  }).join('');
  const pos = d && d.position ? `${d.position.index} / ${d.position.total}` : '';
  bar.innerHTML =
    '<span class="rr-runbar-label">実行回</span>'
    + `<button type="button" class="rr-nav" id="rr-older" ${d && d.older_run_id ? '' : 'disabled'} title="前の実行">‹</button>`
    + `<select id="rr-select" class="rr-select" aria-label="実行回を選ぶ">${options}</select>`
    + `<button type="button" class="rr-nav" id="rr-newer" ${d && d.newer_run_id ? '' : 'disabled'} title="次の実行">›</button>`
    + '<span class="rr-meta">'
    + (pos ? `<span>${escHtml(pos)} 件目</span>` : '')
    + `<span class="rr-runid">${escHtml(_rrRunId)}</span>`
    + (d && d.is_current
      ? '<span class="rh-approval is-ok">現在の成果物</span>'
      : '<span class="rh-approval is-neutral">過去の実行</span>')
    + '</span>'
    + '<span class="rr-runbar-actions">'
    + `<button type="button" class="btn-outline-sm" id="rr-back">← 実行履歴へ戻る</button>`
    + '</span>';

  document.getElementById('rr-select')?.addEventListener('change', (e) => {
    openRunResult(_rrDomain, e.target.value);
  });
  document.getElementById('rr-older')?.addEventListener('click', () => {
    if (_rrDetail && _rrDetail.older_run_id) openRunResult(_rrDomain, _rrDetail.older_run_id);
  });
  document.getElementById('rr-newer')?.addEventListener('click', () => {
    if (_rrDetail && _rrDetail.newer_run_id) openRunResult(_rrDomain, _rrDetail.newer_run_id);
  });
  document.getElementById('rr-back')?.addEventListener('click', () => switchView('run-history'));
}

function _rrRenderArtifactTabs() {
  const host = document.getElementById('rr-artifacts');
  if (!host || !_rrDetail) return;
  const flags = _rrDetail.artifacts || {};
  host.innerHTML = RR_ARTIFACTS.map(a => {
    const has = !!flags[a.key];
    const on = _rrTab === a.key;
    return `<button type="button" class="rr-artifact${on ? ' is-active' : ''}" role="tab"
      aria-selected="${on ? 'true' : 'false'}" data-art="${a.key}" ${has ? '' : 'disabled'}>
      <span class="rr-artifact-badge">${has ? '<span class="rh-approval is-ok">あり</span>' : '<span class="rh-approval is-neutral">なし</span>'}</span>
      <span class="rr-artifact-n">${a.n}</span>
      <span class="rr-artifact-t">${escHtml(a.label)}</span>
      <span class="rr-artifact-d">${escHtml(a.desc)}</span>
      <span class="rr-artifact-f">runs/${escHtml(_rrRunId)}/${escHtml(a.file)}</span>
    </button>`;
  }).join('');
  host.querySelectorAll('.rr-artifact').forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.disabled) return;
      _rrTab = btn.dataset.art;
      _rrRenderArtifactTabs();
      _rrRenderBody();
    });
  });
  // 既定タブが「なし」なら、ある方へ寄せる（押せないタブを開いたまま見せない）
  if (!flags[_rrTab]) {
    const first = RR_ARTIFACTS.find(a => flags[a.key]);
    if (first && first.key !== _rrTab) {
      _rrTab = first.key;
      _rrRenderArtifactTabs();
    }
  }
}

function _rrOpen(path, label) {
  if (!path) return;
  if (typeof openFilePreview === 'function') openFilePreview(path, label);
  else window.open('/preview?path=' + encodeURIComponent(path), '_blank');
}

// レポートパネル（#result-panel）は generate と run-result の両方で使うため、
// どちらのビューの中でもない場所（.app-content-inner 直下）に置いてある。
// このビューでは表示/非表示を切り替えるだけでよく、DOM を移動しない。
function _rrShowReportPanel(show) {
  const panel = document.getElementById('result-panel');
  if (panel) panel.classList.toggle('hidden', !show);
  return panel;
}

function _rrClearBody() {
  _rrShowReportPanel(false);
  const body = document.getElementById('rr-body');
  if (body) body.innerHTML = '';
}

// #rr-body の中身を差し替える唯一の入口。レポートパネルは畳んでから書き換える。
function _rrSetBody(html) {
  _rrShowReportPanel(false);
  const body = document.getElementById('rr-body');
  if (body) body.innerHTML = html;
  return body;
}

function _rrRenderBody() {
  const body = document.getElementById('rr-body');
  if (!body || !_rrDetail) return;
  const flags = _rrDetail.artifacts || {};
  if (!flags[_rrTab]) {
    _rrSetBody('<div class="rr-missing"><strong>この実行回にこの成果物はありません</strong>'
      + '<p>他の実行の成果物で埋めることはしません。</p></div>');
    return;
  }
  if (_rrTab === 'result') { _rrRenderResult(body); return; }
  if (_rrTab === 'analysis') { _rrRenderAnalysis(body); return; }
  _rrRenderAutorun(body);
}

// ---- 1 実行結果: 既存のレポート画面をそのまま出す（データ源はこの実行回） ----
// 概要・画面と仕様・テスト設計・テストケース・画面遷移・テスト実行・履歴/差分・現新比較の
// タブ構成は既存実装をそのまま使う。ここで作り直さない。
async function _rrRenderResult(body) {
  _rrClearBody();
  if (!_rrShowReportPanel(true)) {
    _rrSetBody('<div class="rr-missing"><strong>レポート画面を表示できません</strong>'
      + '<p>結果パネルが見つかりませんでした。ページを再読み込みしてください。</p></div>');
    return;
  }
  if (typeof showResults !== 'function') return;
  await showResults(_rrDomain, 'overview', '', _rrRunId);
  // showResults は generate 画面向けに全高モードを付ける。実行結果ハブでは
  // 実行回バーと成果物タブを上に置くため、その指定は解除する。
  const appContentEl = document.getElementById('app-content');
  if (appContentEl) appContentEl.classList.remove('is-reporting', 'is-executing');
  // パンくずと見出しは showResults が書き換えるので、実行回のものへ戻す
  setHeader(['ダッシュボード', '実行履歴', _rrDomain], `実行結果 — ${_rrDomain}`);
}

// ---- 2 解析結果: この回の report.html ----
function _rrRenderAnalysis(body) {
  const files = _rrDetail.files || {};
  body = _rrSetBody(
    '<div class="rr-pane">'
    + '<div class="rr-pane-head"><strong>2 解析結果</strong>'
    + '<span class="muted-copy">この実行回に書き出された静的レポート</span>'
    + `<span class="rr-path">runs/${escHtml(_rrRunId)}/report.html</span></div>`
    + '<div class="rr-pane-body">'
    + '<p class="muted-copy">テスト分析インプット（サマリー・アーキテクチャ図・技術スタック・画面遷移図・アクセシビリティ）。'
    + 'この実行回のものなので、後から再クロールしても内容は変わらない。</p>'
    + '<div class="rr-files">'
    + `<button type="button" class="btn-primary rr-open" data-path="${escHtml(files.html)}" data-label="解析結果 ${escHtml(_rrDomain)}">解析結果を開く</button>`
    + `<a class="btn-outline-sm" href="/download?path=${encodeURIComponent(files.html)}" download>↓ ダウンロード</a>`
    + '</div>'
    + `<iframe class="rr-frame" title="解析結果" src="/preview?path=${encodeURIComponent(files.html)}"></iframe>`
    + '</div></div>');
  _rrBindOpen(body);
}

// ---- 3 実行結果レポート: この回の qa_process/ ----
function _rrRenderAutorun(body) {
  const files = _rrDetail.files || {};
  const secs = [
    ['test_plan', '計画', 'test_plan.md'],
    ['test_analysis', '分析', 'test_analysis.md'],
    ['test_design', '設計', 'test_design.md'],
    ['test_cases', 'ケース', 'test_cases.md'],
    ['spec_ts', 'スクリプト', 'autorun.spec.ts'],
    ['playwright_report_html', '実行結果', 'playwright_report.html'],
    ['qa_process_report', 'QAプロセス', 'qa_process_report.html'],
  ];
  const items = secs.map(([k, label, file]) => files[k]
    ? `<button type="button" class="btn-outline-sm rr-open" data-path="${escHtml(files[k])}" data-label="${escHtml(label)}">${escHtml(label)}<span class="rr-file">${escHtml(file)}</span></button>`
    : `<button type="button" class="btn-outline-sm" disabled>${escHtml(label)}<span class="rr-file">未生成</span></button>`
  ).join('');
  body = _rrSetBody(
    '<div class="rr-pane">'
    + '<div class="rr-pane-head"><strong>3 実行結果レポート</strong>'
    + '<span class="muted-copy">この実行回の AutoRun 成果物</span>'
    + `<span class="rr-path">runs/${escHtml(_rrRunId)}/qa_process/</span></div>`
    + '<div class="rr-pane-body">'
    + '<p class="muted-copy">生成されている成果物だけを出す。未生成のものは押せない状態のまま残し、'
    + '別の実行のもので埋めることはしない。</p>'
    + `<div class="rr-files rr-files-grid">${items}</div>`
    + '</div></div>');
  _rrBindOpen(body);
}

function _rrBindOpen(host) {
  host.querySelectorAll('.rr-open').forEach(btn => {
    btn.addEventListener('click', () => _rrOpen(btn.dataset.path, btn.dataset.label || ''));
  });
}

// URL（/runs/<domain>/<run_id>）から復元する
function rrRestoreFromPath(pathname) {
  const m = String(pathname || '').match(/^\/runs\/([^/]+)\/([^/]+)\/?$/);
  if (!m) return false;
  openRunResult(decodeURIComponent(m[1]), decodeURIComponent(m[2]));
  return true;
}
