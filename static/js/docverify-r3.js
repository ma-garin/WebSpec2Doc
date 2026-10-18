/* ドキュメント検証 R3（SCR-06-07 トレーサビリティ）: 文書の流れ図・直すべきことの一覧・追跡表・検査の設定。
 * 土台は docverify-core.js（window.DV）。DV.on('setcheck', fn) で描く。結果には必ず「網羅性: 未検証」を出す。 */
(() => {
  'use strict';
  const DV = window.DV;
  if (!DV) return;
  const $ = (s) => document.querySelector(s);
  const esc = DV.esc;
  const COVERAGE = '網羅性: 未検証';
  const DECISIONS = [['contradiction', '矛盾'], ['duplicate', '重複'], ['ok', '問題なし']];
  const RULE_JA = {
    INCOMPLETE: '未決定の記述', OPEN_ENDED: '閉じていない列挙', UNIVERSAL: '例外の無い表現', AND_OR: '「および/または」',
    MEASURABILITY: '数値の無い量・時間', MULTIPLE_REQUIREMENTS: '1 文に複数の要求', AMBIGUOUS_TERM: '用語のゆれ', AMBIGUOUS: '曖昧語',
  };
  const KINDS = [['requirement', '要件'], ['design', '設計'], ['test', 'テスト']];
  const TYPES = [['nodesign', '設計なし'], ['notest', 'テストなし'], ['orphan', '孤立'], ['contradiction', '矛盾候補'], ['duplicate', '重複候補']];
  const TYPE_WORD = Object.fromEntries(TYPES);
  const FIND = '指摘はありません';
  let state = null;
  let issues = [];
  const off = new Set();

  const iid = () => (DV.state.review ? DV.state.review.id : null);
  const base = () => `/api/docverify/inspections/${encodeURIComponent(iid())}/r3`;
  const docsOf = (k) => (state.documents || []).filter((d) => d.kind === k);

  function msg(text) {
    const el = $('#dv3Msg');
    if (el) el.textContent = text || '';
  }

  function collectIssues() {
    const t = state.trace || {};
    const cols = new Set((t.columns || []).map((c) => c.kind));
    const out = [];
    (t.rows || []).forEach((r) => {
      [['design', 'nodesign', '設計'], ['test', 'notest', 'テスト']].forEach(([k, type, label]) => {
        if (cols.has(k) && !(r[k] || []).length) {
          out.push({ type, id: r.id, excerpt: (r.requirement || []).join('／'),
            basis: `この ID が${label}の文書に見つかりません。` });
        }
      });
    });
    (t.orphans || []).forEach((o) => out.push({ type: 'orphan', id: o.id, excerpt: `${o.kind_label}: ${o.locations.join('／')}`,
      basis: '上流の要件に同じ ID がありません。' }));
    ((state.set_check || {}).pairs || []).forEach((p) => out.push({ type: p.kind, id: `${p.a.doc_name} ⇔ ${p.b.doc_name}`, pair: p,
      excerpt: '', basis: p.reason || '文の内容が近い、または食い違っています。' }));
    return out;
  }

  function leadText() {
    const docs = state.documents || [];
    if (!docs.length) return '要件・設計・テストの文書を登録すると、つながりの抜けを自動で見つけます。';
    const t = state.trace || {};
    const n = (type) => issues.filter((i) => i.type === type).length;
    const total = (t.rows || []).length;
    const parts = [];
    const gap = n('nodesign') + n('notest');
    if (total) parts.push(`要件 ${total} 件のうち ${new Set(issues.filter((i) => i.type === 'nodesign' || i.type === 'notest').map((i) => i.id)).size} 件につながりの抜けがあります`);
    if (n('orphan')) parts.push(`孤立 ${n('orphan')} 件`);
    const pair = n('contradiction') + n('duplicate');
    if (pair) parts.push(`矛盾・重複の候補 ${pair} 件`);
    if (!parts.length || (!gap && !n('orphan') && !pair)) return '確認した範囲では、つながりの抜けは見つかっていません。';
    return `${parts.join('。')}。確認してください。`;
  }

  function flowCard(kind, label) {
    const ds = docsOf(kind);
    if (!ds.length) {
      return `<div class="dv3-doc is-empty"><div class="dv3-doc-t">${esc(label)}</div><p class="dv3-sub">文書が未登録です。</p>`
        + `<button type="button" class="btn-outline-sm" data-dv3-add="${kind}">この種別の文書を登録</button></div>`;
    }
    const last = ds[ds.length - 1];
    const when = last.uploaded_at ? String(last.uploaded_at).slice(0, 16).replace('T', ' ') : '—';
    const frag = ds.reduce((s, d) => s + (Number(d.passages) || 0), 0);
    return `<div class="dv3-doc"><div class="dv3-doc-t">${esc(label)}</div><div class="dv3-doc-n"><strong>${esc(ds.length)}</strong> 文書・${esc(frag)} 断片</div>`
      + `<div class="dv3-doc-m">${esc(last.name)}${last.version ? ` <span class="dv3-ver">${esc(last.version)}</span>` : ''}</div>`
      + `<div class="dv3-doc-f"><span>取り込み ${esc(when)}</span><button type="button" class="dv3-link" data-dv3-add="${kind}">差し替え</button></div></div>`;
  }

  function arrow(downKind) {
    const t = state.trace || {};
    const has = docsOf('requirement').length && docsOf(downKind).length;
    if (!has) return '<div class="dv3-arrow"><div class="dv3-rate is-na">—</div><div class="dv3-line"></div></div>';
    const rows = t.rows || [];
    const covered = rows.filter((r) => (r[downKind] || []).length).length;
    const rate = rows.length ? Math.round((covered / rows.length) * 100) : null;
    const miss = rows.length - covered;
    return `<div class="dv3-arrow"><div class="dv3-rate${rate !== null && rate < 100 ? ' is-low' : ''}">${rate === null ? '—' : `${esc(rate)}%`}</div>`
      + `<div class="dv3-rl">カバー率</div><div class="dv3-line"></div>${miss ? `<span class="dv3-miss">欠落 ${esc(miss)} 件</span>` : '<span class="dv3-ok">欠落なし</span>'}</div>`;
  }

  function renderFlow() {
    const [r, d, t] = KINDS;
    $('#dv3Flow').innerHTML = flowCard(...r) + arrow('design') + flowCard(...d) + arrow('test') + flowCard(...t);
  }

  function renderFilter() {
    const box = $('#dv3Filter');
    box.innerHTML = `<legend>種類で絞る</legend>${TYPES.map(([k, label]) => {
      const n = issues.filter((i) => i.type === k).length;
      return `<label class="dv3-check"><input type="checkbox" data-dv3-ft="${k}"${off.has(k) ? '' : ' checked'}> ${esc(label)} <span class="dv3-n">${esc(n)}</span></label>`;
    }).join('')}`;
  }

  function decButtons(p) {
    return DECISIONS.map(([v, label]) => `<button type="button" class="dv3-dec${p.decision === v ? ' is-on' : ''}" aria-pressed="${p.decision === v}" data-dv3-pair="${esc(p.id)}" data-dv3-dec="${v}">${label}</button>`).join('');
  }

  function issueCard(i) {
    const p = i.pair;
    const side = (s) => `<div class="dv3-q"><span class="dv3-loc">${esc(s.doc_name)} ${esc(s.location)}</span>${esc(s.text)}</div>`;
    const body = p ? `<div class="dv3-pairq">${side(p.a)}${side(p.b)}</div>` : `<div class="dv3-q">${esc(i.excerpt)}</div>`;
    const act = p ? `<div class="dv3-decs" role="group" aria-label="判断">${decButtons(p)}</div>`
      : '<div class="dv3-decs"><button type="button" class="btn-outline-sm" data-dv3-show>つながりを見る</button></div>';
    return `<article class="dv3-issue"><div class="dv3-issue-h"><span class="dv3-kind dv3-kind-${esc(i.type)}">${esc(TYPE_WORD[i.type])}</span>`
      + `<b class="dv3-id">${esc(i.id)}</b></div>${body}<p class="dv3-basis">根拠: ${esc(i.basis)}</p>${act}</article>`;
  }

  function renderList() {
    const el = $('#dv3List');
    const docs = state.documents || [];
    if (!docs.length) { el.innerHTML = '<p class="dv3-empty">要件・設計・テストの文書を登録すると、つながりの抜けを自動で見つけます。</p>'; return; }
    const ran = (state.set_check || {}).ran;
    const shown = issues.filter((i) => !off.has(i.type));
    const notRun = !ran ? '<p class="dv3-hint">矛盾・重複の候補はまだ検査していません。「検査を実行」を押してください。</p>' : '';
    if (!shown.length) {
      el.innerHTML = `${notRun}<p class="dv3-empty">${ran || issues.length ? `確認した範囲では${FIND}。${esc(COVERAGE)}` : '「検査を実行」を押すと、矛盾・重複の候補も探します。'}</p>`;
      return;
    }
    el.innerHTML = notRun + shown.map(issueCard).join('');
  }

  function renderTrace() {
    const t = state.trace || {};
    const fmt = $('#dv3Format');
    fmt.innerHTML = (state.formats || []).map((f) => `<option value="${esc(f.id)}"${f.id === state.trace_format ? ' selected' : ''}>${esc(f.label)}（例: ${esc(f.example)}）</option>`).join('');
    const c = t.complete || {};
    const rate = c.rate === null || c.rate === undefined ? '—' : `${c.rate}%（${c.covered}/${c.total}）`;
    const warn = [...(t.messages || []), ...(t.unreadable || []).map((u) => `${u.doc}: ${u.message}`)]
      .map((m) => `<p class="dv3-warn" role="alert">${esc(m)}</p>`).join('');
    $('#dv3TraceSummary').innerHTML = `${warn}<div class="dv3-stats"><div class="dv3-stat"><span>完全率</span><b>${esc(rate)}</b></div>`
      + `<div class="dv3-stat"><span>孤立（上流の無い下流 ID）</span><b>${esc((t.orphans || []).length)} 件</b></div></div>`;
    const cols = t.columns || [];
    if (!(t.rows || []).length) { $('#dv3Trace').innerHTML = `<p class="dv3-empty">追跡表の行はありません。${esc(COVERAGE)}</p>`; return; }
    const head = `<tr><th>ID</th>${cols.map((x) => `<th>${esc(x.label)}</th>`).join('')}</tr>`;
    const body = t.rows.map((r) => `<tr><th scope="row">${esc(r.id)}</th>${cols.map((x) => {
      const v = r[x.kind] || [];
      return v.length ? `<td>${v.map(esc).join('<br>')}</td>` : '<td class="dv3-gap">なし</td>';
    }).join('')}</tr>`).join('');
    $('#dv3Trace').innerHTML = `<table class="dv3-table" id="dv3TraceTable"><thead>${head}</thead><tbody>${body}</tbody></table>`;
  }

  function renderDocs() {
    const docs = state.documents || [];
    if (!docs.length) { $('#dv3Docs').innerHTML = ''; return; }
    const rows = docs.map((d) => `<tr><td>${esc(d.kind_label)}</td><td>${esc(d.name)}</td><td class="num">${esc(d.passages)}</td>`
      + `<td>${d.hidden_passages ? `非表示 ${esc(d.hidden_passages)}${d.include_hidden ? '' : '（対象外）'}` : '—'}</td>`
      + `<td><button type="button" class="btn-outline-sm" data-dv3-del="${esc(d.id)}">外す</button></td></tr>`).join('');
    $('#dv3Docs').innerHTML = `<table class="dv3-table"><thead><tr><th>種別</th><th>文書</th><th>断片</th><th>非表示の印</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  function render(data) {
    state = data;
    issues = collectIssues();
    $('#dv3Lead').textContent = leadText();
    renderFlow();
    renderFilter();
    renderList();
    renderTrace();
    renderDocs();
  }

  async function load() {
    if (!iid()) return;
    msg('読み込み中…');
    try { render(await DV.api(base())); msg(''); } catch (e) { msg('読み込めませんでした。再読み込みしてください。'); }
  }

  function openAdd(kind) {
    const p = $('#dv3AddPanel');
    p.hidden = false;
    $('#dv3AddBtn').setAttribute('aria-expanded', 'true');
    if (kind) $('#dv3Kind').value = kind;
    $('#dv3File').focus();
  }

  async function upload(e) {
    e.preventDefault();
    const file = $('#dv3File').files[0];
    const kind = $('#dv3Kind').value;
    if (!kind || !file) { msg('種別と文書を選んでください。'); return; }
    const form = new FormData();
    form.append('file', file);
    form.append('kind', kind);
    form.append('include_hidden', $('#dv3Hidden').checked ? '1' : '0');
    await DV.busy($('#dv3UploadBtn'), async () => {
      try { render(await DV.api(`${base()}/documents`, { method: 'POST', form })); DV.toast('文書を登録しました。'); $('#dv3File').value = ''; $('#dv3AddPanel').hidden = true; $('#dv3AddBtn').setAttribute('aria-expanded', 'false'); } catch (err) { msg('登録できませんでした。文書の形式を確かめてもう一度お試しください。'); }
    }, '登録中…');
  }

  async function act(path, opts, done) {
    try { render(await DV.api(path, opts)); if (done) DV.toast(done); } catch (e) { msg('操作できませんでした。時間をおいてもう一度お試しください。'); }
  }

  function onClick(e) {
    const add = e.target.closest('[data-dv3-add]');
    if (add) { openAdd(add.dataset.dv3Add); return; }
    const del = e.target.closest('[data-dv3-del]');
    if (del) { act(`${base()}/documents/${encodeURIComponent(del.dataset.dv3Del)}`, { method: 'DELETE' }, '文書を外しました。'); return; }
    if (e.target.closest('[data-dv3-show]')) {
      const f = document.querySelector('[data-view="setcheck"] .dv3-fold'); f.open = true; f.scrollIntoView({ block: 'start' }); return;
    }
    const b = e.target.closest('[data-dv3-dec]');
    if (!b) return;
    const word = DECISIONS.find(([v]) => v === b.dataset.dv3Dec)[1];
    act(`${base()}/setcheck/${encodeURIComponent(b.dataset.dv3Pair)}`, { method: 'POST', json: { decision: b.dataset.dv3Dec } },
      word === '問題なし' ? '「問題なし」を記録しました。' : `指摘に種別「${word}」で追加しました。`);
  }

  function bind() {
    $('#dv3Upload').addEventListener('submit', upload);
    $('#dv3AddBtn').addEventListener('click', () => {
      const p = $('#dv3AddPanel');
      p.hidden = !p.hidden;
      $('#dv3AddBtn').setAttribute('aria-expanded', String(!p.hidden));
    });
    $('#dv3Run').addEventListener('click', () => DV.busy($('#dv3Run'), () => act(`${base()}/setcheck`, { method: 'POST', json: {} }, '検査を実行しました。'), '検査中…'));
    $('#dv3Format').addEventListener('change', (e) => act(`${base()}/trace`, { method: 'POST', json: { format: e.target.value } }));
    $('#dv3Xlsx').addEventListener('click', () => DV.download(`${base()}/trace.xlsx`, '追跡表.xlsx'));
    $('#dv3Rules').addEventListener('submit', saveRules);
    $('#dv3Filter').addEventListener('change', (e) => {
      const k = e.target.dataset.dv3Ft;
      if (!k) return;
      if (e.target.checked) off.delete(k); else off.add(k);
      renderList();
    });
    document.querySelector('[data-view="setcheck"]').addEventListener('click', onClick);
  }

  const lines = (id) => $(id).value.split('\n').map((s) => s.trim()).filter(Boolean);

  async function loadRules() {
    try {
      const s = await DV.api('/api/docverify/r3/settings');
      const dis = new Set(s.disabled_rules || []);
      $('#dv3RuleList').innerHTML = (s.rules || []).map((r) => `<label class="dv3-check"><input type="checkbox" value="${esc(r)}"${dis.has(r) ? '' : ' checked'}> ${esc(RULE_JA[r] || '追加の規則')}</label>`).join('');
      $('#dv3Forbidden').value = (s.forbidden || []).join('\n');
      $('#dv3Allowed').value = (s.allowed || []).join('\n');
      $('#dv3Synonyms').value = (s.synonyms || []).map((x) => `${x.canonical}＝${x.variants.join('、')}`).join('\n');
    } catch (e) { /* 帯に出る */ }
  }

  async function saveRules(e) {
    e.preventDefault();
    const disabled = [...document.querySelectorAll('#dv3RuleList input')].filter((x) => !x.checked).map((x) => x.value);
    const synonyms = lines('#dv3Synonyms').map((l) => {
      const [c, v] = l.split(/[＝=]/);
      return { canonical: (c || '').trim(), variants: (v || '').split(/[、,]/).map((s) => s.trim()).filter(Boolean) };
    });
    try {
      await DV.api('/api/docverify/r3/settings', { method: 'PUT', json: { disabled_rules: disabled, forbidden: lines('#dv3Forbidden'), allowed: lines('#dv3Allowed'), synonyms } });
      DV.toast('設定を保存しました。次に取り込む文書から使います。');
    } catch (err) { msg('設定を保存できませんでした。もう一度お試しください。'); }
  }

  function kinds() {
    $('#dv3Kind').innerHTML = `<option value="">選んでください</option>${KINDS.map(([k, l]) => `<option value="${k}">${l}</option>`).join('')}`;
  }

  let bound = false;
  DV.on('setcheck', () => {
    if (!bound) { bound = true; kinds(); bind(); }
    load();
    loadRules();
  });
})();
