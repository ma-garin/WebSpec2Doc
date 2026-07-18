// ====================== 結果ページ（QAビュー軸） ======================
const resultPanel = document.getElementById('result-panel');
// 描画先シム: selectResultTab がアクティブなパネル/サブパネル要素へ差し替える。
// 各 view-*.js は resultHero へ描画するだけで、自分のパネルにだけ描かれ状態が保持される。
let resultHero = document.getElementById('rp-overview');

// タブレジストリ: パネルID・描画関数（グローバル名前解決）・サブタブ構成
const TAB_DEFS = {
  overview:      { panel: 'rp-overview', render: 'renderOverview' },
  screens:       { panel: 'rp-screens', defaultSub: 'spec',
                   subs: { spec: 'renderReport', gallery: 'renderShots', coverage: 'renderCoverageHeatmap' } },
  'test-design': { panel: 'rp-test-design', defaultSub: 'matrix',
                   subs: { matrix: 'renderMatrix', summary: 'renderDesign', detail: 'renderTechniqueDetail', mbt: 'renderMbtDesign' } },
  flow:          { panel: 'rp-flow', defaultSub: 'diagram',
                   subs: { diagram: 'renderTransition', table: 'renderTransitionTable' } },
  runs:          { panel: 'rp-runs', render: 'renderTestRuns' },
  'doc-fusion':  { panel: 'rp-doc-fusion', render: 'renderDocFusion' },
  history:       { panel: 'rp-history', render: 'renderTimeline' },
};

// 旧8タブ時代のディープリンク互換（共有済みURLを壊さない）
const LEGACY_TAB_MAP = {
  report: ['screens', 'spec'],
  matrix: ['test-design', 'matrix'],
  design: ['test-design', 'summary'],
  'technique-detail': ['test-design', 'detail'],
  transition: ['flow', 'diagram'],
  'transition-table': ['flow', 'table'],
};

let resultData = null, reportJson = null, docFusionData = null;
let activeResultTab = 'overview', activeResultSub = '';
const _renderedPanels = new Set(); // "tab/sub" 単位の描画済みフラグ（dirty 管理）

async function showResults(domain, tab, sub) {
  let data;
  try {
    const res = await fetch('/api/result?domain=' + encodeURIComponent(domain));
    data = await res.json();
    if (!res.ok) throw new Error(data.error || '結果の取得に失敗しました');
  } catch (e) {
    // 実行ビューが隠れている（履歴から開いた）場合は結果領域にエラーを表示
    executionView.classList.add('hidden'); resultPanel.classList.remove('hidden');
    appContent.classList.remove('is-executing');
    appContent.classList.add('is-reporting');
    setHeader(['ダッシュボード', domain], domain);
    _renderedPanels.clear();
    _switchPanels('overview', '');
    uiError(document.getElementById('rp-overview'), {
      title: '結果の取得に失敗しました',
      message: e.message,
      onRetry: () => showResults(domain, tab, sub),
    });
    return;
  }
  resultData = data;
  reportJson = null;
  if (data.files && data.files.json) {
    try { reportJson = await fetch('/preview?path=' + encodeURIComponent(data.files.json)).then(r => r.json()); } catch (e) {}
  }
  const s = data.summary || {};
  const required = reportJson ? countRequired(reportJson) : 0;
  const crawledAt = reportJson && reportJson.meta ? reportJson.meta.crawled_at : '';
  document.getElementById('r-crawled').textContent = crawledAt ? ('最終クロール: ' + crawledAt) : '';
  document.getElementById('r-domain').textContent = domain;
  _updateKpiHero(s, required, data);

  // 差分バッジ（DOM APIで構築 — innerHTML を使わない）
  const diffBadge = document.getElementById('r-diff-badge');
  if (diffBadge) {
    const hasDiff = data.files && data.files.diff;
    diffBadge.replaceChildren();
    if (hasDiff) {
      const span = document.createElement('span');
      span.className = 'diff-badge';
      span.style.cursor = 'pointer';
      span.title = '履歴・差分タブを開く';
      span.textContent = '差分あり';
      span.addEventListener('click', () => selectResultTab('history'));
      diffBadge.appendChild(span);
      diffBadge.style.display = '';
    } else {
      diffBadge.style.display = 'none';
    }
  }

  // タブ件数バッジ
  const screenCount = s.screens || 0;
  const fieldCount = s.fields || 0;
  const snapCount = data.snapshot_count || 0;
  const setTabCount = (id, n) => { const el = document.getElementById(id); if (el) el.textContent = n > 0 ? ` ${n}` : ''; };
  setTabCount('tab-count-screens', screenCount);
  setTabCount('tab-count-test-design', fieldCount);
  setTabCount('tab-count-history', snapCount);

  // 文書突合タブ（doc_fusion.json 存在時のみ表示 — AC-4/AC-5）
  docFusionData = null;
  try {
    const dfRes = await fetch('/api/doc-fusion?domain=' + encodeURIComponent(domain));
    if (dfRes.ok) docFusionData = await dfRes.json();
  } catch (e) { /* 突合結果なしとして扱う */ }
  const docFusionTab = document.getElementById('tab-doc-fusion');
  if (docFusionTab) docFusionTab.hidden = !docFusionData;
  if (docFusionData) {
    setTabCount('tab-count-doc-fusion', (docFusionData.meta && docFusionData.meta.field_gaps) || 0);
  }

  setHeader(['ダッシュボード', domain], domain);

  executionView.classList.add('hidden'); resultPanel.classList.remove('hidden');
  appContent.classList.add('is-reporting');
  _buildExportDropdown(data);
  showWizardStep(4);
  _renderedPanels.clear(); // データ更新 → 全パネル dirty 化（次回表示時に再描画）
  selectResultTab(tab || 'overview', sub);
}

// KPIヒーロー: 生数値の羅列ではなく「テスト計画に効く」指標を出す
function _updateKpiHero(s, required, data) {
  const setText = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  const fields = s.fields || 0;
  setText('k-screens', s.screens || 0);
  setText('k-forms-sub', s.forms ? `フォーム ${s.forms}` : '');
  setText('k-fields', fields);
  setText('k-required-sub', fields ? `必須 ${required}（${Math.round(required / fields * 100)}%）` : '必須 0');
  const bar = document.getElementById('k-required-bar');
  if (bar) bar.style.width = fields ? Math.round(required / fields * 100) + '%' : '0%';

  if (reportJson) {
    const effort = estimateTestEffort(reportJson);
    setText('k-conds', countTestConditions(reportJson));
    setText('k-cases', effort.cases);
    setText('k-hours-sub', effort.cases ? `約${effort.hours}時間（1件${effort.caseMinutes}分）` : '');
  } else {
    setText('k-conds', '—');
    setText('k-cases', '—');
    setText('k-hours-sub', '再クロールで算出');
  }

  // 直近テスト実行の PASS 率（playwright_report.json があれば非同期で反映）
  const passEl = document.getElementById('k-passrate');
  const subEl = document.getElementById('k-runs-sub');
  const tile = document.getElementById('k-runs-tile');
  if (passEl) { passEl.textContent = '—'; passEl.classList.remove('is-pass', 'is-fail'); }
  if (subEl) subEl.textContent = '未実行';
  const pwJson = data.files && data.files.playwright_json;
  if (pwJson) {
    fetch('/preview?path=' + encodeURIComponent(pwJson)).then(r => r.json()).then(r => {
      if (!passEl || !subEl) return;
      if (r.unavailable) { subEl.textContent = '実行不可（要セットアップ）'; return; }
      const total = r.total || 0;
      if (r.error && !total) {
        // evidence-only: 実行が解析不能・未実行だった場合を「未実行」のまま放置しない
        // （0/0/0が無言で「未実行」表示され続けた不具合の再発防止）。
        passEl.textContent = '!';
        passEl.classList.add('is-fail');
        subEl.textContent = '実行エラー（テスト実行タブを確認）';
        return;
      }
      if (!total) return;
      const rate = Math.round((r.passed || 0) / total * 100);
      passEl.textContent = rate + '%';
      passEl.classList.add((r.failed || 0 || r.interrupted) ? 'is-fail' : 'is-pass');
      const suffix = data.playwright_run_at ? ` ・ ${data.playwright_run_at}` : '';
      subEl.textContent = (r.interrupted ? '（中断・部分結果）' : '') +
        `PASS ${r.passed || 0} / FAIL ${r.failed || 0}` + suffix;
    }).catch(() => {});
  }
  if (tile && !tile._bound) {
    tile._bound = true;
    tile.addEventListener('click', () => selectResultTab('runs'));
  }
}

function _buildExportDropdown(data) {
  const menu = document.getElementById('export-dropdown-menu');
  if (!menu) return;
  const files = (data && data.files) || {};
  const domain = (document.getElementById('r-domain') || {}).textContent || '';
  const defs = [
    { key: 'html', label: 'HTMLレポート' },
    { key: 'pdf', label: 'PDF' },
    { key: 'json', label: 'JSON' },
    { key: 'excel', label: 'Excel' },
    { key: 'screens_md', label: 'Markdown（画面一覧）' },
    { key: 'forms_md', label: 'Markdown（フォーム）' },
    { key: 'transition_mmd', label: '遷移図（Mermaid）' },
    { key: 'diff', label: '差分レポート' },
  ];
  const zipRow = `<div class="export-dropdown-item is-zip"><span>すべてZIPでダウンロード</span><a href="/download-zip?domain=${encodeURIComponent(domain)}" class="btn-primary" style="height:28px;padding:0 10px;font-size:12px">DL</a></div>`;
  const fileRows = defs.map(d => {
    if (files[d.key]) {
      return `<div class="export-dropdown-item"><span>${escHtml(d.label)}</span><div style="display:flex;gap:4px"><a href="/preview?path=${encodeURIComponent(files[d.key])}" target="_blank" class="btn-outline-sm" style="height:28px;padding:0 8px;font-size:12px">開く</a><a href="/download?path=${encodeURIComponent(files[d.key])}" class="btn-outline-sm" style="height:28px;padding:0 8px;font-size:12px" download>DL</a></div></div>`;
    }
    return `<div class="export-dropdown-item is-missing"><span>${escHtml(d.label)}（未生成）</span></div>`;
  }).join('');
  menu.innerHTML = zipRow + fileRows;
}

// エクスポートドロップダウンの開閉
document.getElementById('export-dropdown-btn').addEventListener('click', (e) => {
  e.stopPropagation();
  document.getElementById('export-dropdown').classList.toggle('is-open');
});
document.addEventListener('click', () => {
  const dd = document.getElementById('export-dropdown');
  if (dd) dd.classList.remove('is-open');
});

document.querySelectorAll('.result-tabs .result-tab').forEach(t => {
  t.addEventListener('click', () => selectResultTab(t.dataset.tab));
  t.addEventListener('keydown', e => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const tabs = [...document.querySelectorAll('.result-tabs .result-tab')].filter(x => x.offsetParent !== null);
    const i = tabs.indexOf(t);
    const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    if (next) { selectResultTab(next.dataset.tab); next.focus(); }
  });
});
document.querySelectorAll('.result-subtabs .result-subtab').forEach(t => {
  t.addEventListener('click', () => {
    const tab = t.closest('.result-subtabs')?.dataset.tab;
    if (tab) selectResultTab(tab, t.dataset.sub);
  });
});

// タブ・サブタブ名を正規化（旧8タブ時代の名前も受け付ける）
function _normalizeTab(tab, sub) {
  if (LEGACY_TAB_MAP[tab]) return LEGACY_TAB_MAP[tab];
  const def = TAB_DEFS[tab] ? tab : 'overview';
  const d = TAB_DEFS[def];
  const s = d.subs ? (d.subs[sub] ? sub : d.defaultSub) : '';
  return [def, s];
}

// パネル・タブボタンの表示状態だけを切り替え、resultHero シムを差し替える（描画はしない）
function _switchPanels(tab, sub) {
  activeResultTab = tab;
  activeResultSub = sub;
  document.querySelectorAll('.result-tabs .result-tab').forEach(t => {
    const on = t.dataset.tab === tab;
    t.classList.toggle('is-active', on);
    t.setAttribute('aria-selected', on ? 'true' : 'false');
    t.tabIndex = on ? 0 : -1;
  });
  for (const [name, def] of Object.entries(TAB_DEFS)) {
    const panel = document.getElementById(def.panel);
    if (panel) panel.hidden = name !== tab;
  }
  const def = TAB_DEFS[tab];
  let target = document.getElementById(def.panel);
  if (def.subs) {
    const panel = target;
    panel.querySelectorAll('.result-subtab').forEach(t => {
      const on = t.dataset.sub === sub;
      t.classList.toggle('is-active', on);
      t.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    panel.querySelectorAll('.result-subpanel').forEach(p => {
      p.hidden = p.id !== `${def.panel}-${sub}`;
    });
    target = document.getElementById(`${def.panel}-${sub}`) || panel;
  }
  resultHero = target;
  return target;
}

function _writeReportHash() {
  const domain = (document.getElementById('r-domain') || {}).textContent || '';
  if (!domain || domain === '-' || resultPanel.classList.contains('hidden')) return;
  let hash = '#report/' + encodeURIComponent(domain) + '/' + activeResultTab;
  if (activeResultSub) hash += '/' + activeResultSub;
  try { history.replaceState(null, '', hash); } catch (_) {}
}

function selectResultTab(tab, sub) {
  const [nTab, nSub] = _normalizeTab(tab, sub);
  _switchPanels(nTab, nSub);
  _writeReportHash();
  const key = nTab + '/' + nSub;
  if (_renderedPanels.has(key)) return; // 描画済み: 状態（検索条件・スクロール・ズーム）を保持
  _renderedPanels.add(key);
  const def = TAB_DEFS[nTab];
  const fnName = def.subs ? def.subs[nSub] : def.render;
  const fn = window[fnName];
  if (typeof fn === 'function') fn();
}

// ---- 履歴・差分（クロール履歴タイムライン＋任意2点の仕様ドリフト比較）----
let timelineDomain = '';
let _tlDiffToken = 0; // 選択変更・連打時、古い応答の描画を破棄するためのトークン
async function renderTimeline() {
  // await 中にタブ切替で resultHero シムが差し替わっても、自パネルへ描き続ける
  const host = resultHero;
  const domain = document.getElementById('r-domain').textContent.trim();
  timelineDomain = domain;
  uiSkeleton(host, 'table');
  let snaps = [];
  try {
    const data = await fetch('/api/snapshots?domain=' + encodeURIComponent(domain)).then(r => r.json());
    snaps = data.snapshots || [];
  } catch (e) {}
  if (snaps.length < 2) {
    host.innerHTML = '<div class="hero-pad"><div class="hero-section-title">クロール履歴</div>' +
      '<p style="color:var(--text-muted);font-size:13px">履歴が' + snaps.length + '件です。<strong>再クロール</strong>すると、前回との仕様ドリフト（追加/削除された画面・変更されたフォーム）を時系列で比較できます。</p>' +
      _ciGuidanceCard(domain) + '</div>';
    _bindCiCopy();
    return;
  }
  // 既定: to=最新(0), from=ひとつ前(1)
  const rows = snaps.map((s, i) => `
    <tr>
      <td style="text-align:center"><input type="radio" name="snap-from" value="${escHtml(s.id)}" ${i === 1 ? 'checked' : ''}></td>
      <td style="text-align:center"><input type="radio" name="snap-to" value="${escHtml(s.id)}" ${i === 0 ? 'checked' : ''}></td>
      <td>${escHtml(s.label)}${i === 0 ? ' <span class="tl-latest">最新</span>' : ''}</td>
      <td class="num">${s.screens}</td><td class="num">${s.forms}</td><td class="num">${s.fields}</td>
    </tr>`).join('');
  host.innerHTML = '<div class="hero-pad">' +
    '<div class="hero-section-title">クロール履歴（' + snaps.length + '件）</div>' +
    '<p style="color:var(--text-muted);font-size:13px;margin-bottom:10px">比較する2時点を選び、仕様ドリフトを確認します（比較元＝古い／比較先＝新しい）。</p>' +
    '<table class="ov-screens tl-table"><thead><tr><th>比較元</th><th>比較先</th><th>クロール日時</th><th>画面</th><th>フォーム</th><th>入力項目</th></tr></thead><tbody>' +
    rows + '</tbody></table>' +
    '<div class="tl-mode" style="margin:10px 0;font-size:13px">比較モード: ' +
    '<label style="margin-right:14px"><input type="radio" name="tl-mode" value="comparison" checked> 現新比較（4分類・既定）</label>' +
    '<label><input type="radio" name="tl-mode" value="diff"> 簡易ドリフト差分</label></div>' +
    '<div style="margin:12px 0"><button type="button" class="btn-primary" id="tl-diff-btn">この2時点を比較する</button></div>' +
    '<div class="tl-diff-frame" id="tl-diff"></div>' +
    _ciGuidanceCard(domain) + '</div>';
  document.getElementById('tl-diff-btn').addEventListener('click', showTimelineDiff);
  document.querySelectorAll('input[name=tl-mode]').forEach(el => el.addEventListener('change', showTimelineDiff));
  _bindCiCopy();
  showTimelineDiff();
}
function _bindCiCopy() {
  const btn = document.getElementById('ci-copy-btn');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const cmd = document.getElementById('ci-cmd');
    if (!cmd) return;
    navigator.clipboard.writeText(cmd.textContent).then(() => {
      const orig = btn.textContent;
      btn.textContent = 'コピーしました';
      setTimeout(() => { btn.textContent = orig; }, 1500);
    }).catch(() => {});
  });
}
function _ciGuidanceCard(domain) {
  // CI連携先（Jenkins/GitHub Actions等）は顧客環境次第のため断定せず、中立的に提示する。
  const cmd = `python src/main.py --url https://${domain}/ --compare --fail-on-drift`;
  return '<div class="ci-guidance">' +
    '<div class="ci-guidance-title">⚙️ CI/CD で自動ドリフト検知</div>' +
    '<p style="font-size:12.5px;color:var(--text-muted);margin:4px 0 8px">' +
    '定期実行ジョブに組み込むと、前回から仕様ドリフトが出たとき <code>exit code 1</code> で失敗し、パイプラインを止められます。お使いのCIのジョブに以下を追加してください。</p>' +
    '<div class="ci-guidance-cmd"><code id="ci-cmd">' + escHtml(cmd) + '</code>' +
    '<button type="button" class="btn-outline-sm" id="ci-copy-btn">コピー</button></div></div>';
}

// 「この2時点の差分を表示」ボタンの応答が「押しても反応がわからない」と報告された不具合の修正。
// 従来は <iframe src=...> を innerHTML で差し替えるだけで、ローディング表示が無く、
// 選択を変えずに連打すると src が同一文字列のままブラウザが再読込しない場合があり
// 「何も起きていないように見える」状態になっていた。fetch で明示的に取得し、
// 読み込み中・成功・失敗（理由つき）を必ず画面に反映する（evidence-only 原則）。
async function showTimelineDiff() {
  const from = (document.querySelector('input[name=snap-from]:checked') || {}).value;
  const to = (document.querySelector('input[name=snap-to]:checked') || {}).value;
  const box = document.getElementById('tl-diff');
  const btn = document.getElementById('tl-diff-btn');
  if (!box) return;
  if (!from || !to) { box.innerHTML = '<div class="hero-msg">2時点を選択してください。</div>'; return; }
  if (from === to) { box.innerHTML = '<div class="hero-msg">異なる2時点を選択してください。</div>'; return; }

  const mode = (document.querySelector('input[name=tl-mode]:checked') || {}).value || 'comparison';
  const endpoint = mode === 'diff' ? 'snapshot-diff' : 'snapshot-comparison';
  const frameTitle = mode === 'diff' ? '仕様ドリフト差分' : '現新比較（4分類）';
  const myToken = ++_tlDiffToken; // 選択変更・連打時、古い応答の描画を破棄する
  const origLabel = 'この2時点を比較する';
  if (btn) { btn.disabled = true; btn.textContent = mode === 'diff' ? '差分を取得中…' : '現新比較を実行中…'; }
  uiSkeleton(box, 'table');

  let html = '';
  try {
    const res = await fetch(
      `/api/${endpoint}?domain=${encodeURIComponent(timelineDomain)}&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`
    );
    html = await res.text();
    if (!res.ok) throw new Error(`サーバーエラー（HTTP ${res.status}）`);
  } catch (e) {
    if (myToken !== _tlDiffToken) return; // 選択が変わった後の古い失敗応答は無視
    uiError(box, {
      title: (mode === 'diff' ? '差分' : '現新比較') + 'の取得に失敗しました',
      message: e && e.message ? e.message : '通信エラー',
      onRetry: showTimelineDiff,
    });
    if (btn) { btn.disabled = false; btn.textContent = origLabel; }
    return;
  }
  if (myToken !== _tlDiffToken) return; // 選択が変わった後の古い成功応答は無視

  box.replaceChildren();
  const iframe = document.createElement('iframe');
  iframe.title = frameTitle;
  iframe.srcdoc = html; // src の使い回しでは同一URL時にブラウザが再読込しないことがあるため必ず更新される srcdoc を使う
  box.appendChild(iframe);
  if (btn) { btn.disabled = false; btn.textContent = origLabel; }
}

// ====================== 表の密度切替 ======================
const TABLE_DENSITY_KEY = 'wsd_table_density';
function _applyTableDensity(compact) {
  resultPanel.classList.toggle('is-compact', compact);
  const btn = document.getElementById('r-density-btn');
  if (btn) btn.classList.toggle('is-active', compact);
  try { localStorage.setItem(TABLE_DENSITY_KEY, compact ? 'compact' : 'comfortable'); } catch (_) {}
}
document.getElementById('r-density-btn')?.addEventListener('click', () => {
  _applyTableDensity(!resultPanel.classList.contains('is-compact'));
});
(function initTableDensity() {
  let saved = 'comfortable';
  try { saved = localStorage.getItem(TABLE_DENSITY_KEY) || 'comfortable'; } catch (_) {}
  if (saved === 'compact') _applyTableDensity(true);
}());

// ====================== KPI指標バンドの折りたたみ ======================
// 指標カードを完全に隠し、下の解析結果詳細を最大化できるようにする（状態は保存）。
const KPI_COLLAPSED_KEY = 'wsd_kpi_collapsed';
function _applyKpiCollapsed(collapsed) {
  const summary = document.querySelector('#result-panel .result-summary');
  if (summary) summary.classList.toggle('is-kpi-collapsed', collapsed);
  const btn = document.getElementById('r-kpi-toggle');
  if (btn) {
    btn.classList.toggle('is-active', collapsed);
    btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    btn.textContent = collapsed ? '▸ 指標' : '▾ 指標';
  }
  try { localStorage.setItem(KPI_COLLAPSED_KEY, collapsed ? '1' : '0'); } catch (_) {}
}
document.getElementById('r-kpi-toggle')?.addEventListener('click', () => {
  const summary = document.querySelector('#result-panel .result-summary');
  _applyKpiCollapsed(!(summary && summary.classList.contains('is-kpi-collapsed')));
});
(function initKpiCollapsed() {
  let saved = '0';
  try { saved = localStorage.getItem(KPI_COLLAPSED_KEY) || '0'; } catch (_) {}
  if (saved === '1') _applyKpiCollapsed(true);
}());

// ====================== タブ最大化 ======================
function _toggleMaximize() {
  document.body.classList.toggle('result-maximized');
}

document.getElementById('r-maximize-btn')?.addEventListener('click', _toggleMaximize);
document.getElementById('r-maximize-exit-btn')?.addEventListener('click', () => {
  document.body.classList.remove('result-maximized');
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && document.body.classList.contains('result-maximized')) {
    document.body.classList.remove('result-maximized');
  }
});

// ====================== 完了ポップアップ ======================
function _showCompletionPopup(elapsedSec) {
  const overlay = document.getElementById('completion-overlay');
  const elapsedEl = document.getElementById('popup-elapsed');
  if (!overlay) return;
  const m = Math.floor(elapsedSec / 60);
  const s = elapsedSec % 60;
  elapsedEl.textContent = `${m}:${String(s).padStart(2, '0')}`;
  overlay.classList.remove('hidden');
}

document.getElementById('popup-close-btn').addEventListener('click', () => {
  document.getElementById('completion-overlay').classList.add('hidden');
});
document.getElementById('popup-view-report-btn').addEventListener('click', () => {
  document.getElementById('completion-overlay').classList.add('hidden');
  showResults(activeDomain);
});
document.getElementById('completion-overlay').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) document.getElementById('completion-overlay').classList.add('hidden');
});
