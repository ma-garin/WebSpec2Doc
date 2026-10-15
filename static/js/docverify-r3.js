/* ドキュメント検証 R3（SCR-06-07）: 文書の登録・集合の検査・追跡表・規則と語彙。
 * 土台は docverify-core.js（window.DV）。DV.on('setcheck', fn) で描く。結果には必ず「網羅性: 未検証」を出す。 */
(() => {
  'use strict';
  const DV = window.DV;
  if (!DV) return;
  const $ = (s) => document.querySelector(s);
  const esc = DV.esc;
  const COVERAGE = '網羅性: 未検証';
  const DECISIONS = [['contradiction', '矛盾'], ['duplicate', '重複'], ['ok', '問題なし']];
  const KIND_WORD = { contradiction: '矛盾候補', duplicate: '重複候補' };
  let state = null;

  const iid = () => (DV.state.review ? DV.state.review.id : null);
  const base = () => `/api/docverify/inspections/${encodeURIComponent(iid())}/r3`;

  function msg(text) {
    const el = $('#dv3Msg');
    if (el) el.textContent = text || '';
  }

  function renderDocs() {
    const docs = state.documents || [];
    if (!docs.length) {
      $('#dv3Docs').innerHTML = '<p class="dv3-empty">まだ文書がありません。種別を選んで要件・設計・テストの文書を登録してください。</p>';
      return;
    }
    const rows = docs.map((d) => `<tr><td>${esc(d.kind_label)}</td><td>${esc(d.name)}</td><td class="num">${esc(d.passages)}</td>`
      + `<td class="num">${esc((d.candidates || []).length)}</td><td>${d.hidden_passages ? `非表示 ${esc(d.hidden_passages)}${d.include_hidden ? '' : '（対象外）'}` : '—'}</td>`
      + `<td><button type="button" class="btn-outline-sm" data-dv3-del="${esc(d.id)}">外す</button></td></tr>`).join('');
    $('#dv3Docs').innerHTML = `<table class="dv3-table"><thead><tr><th>種別</th><th>文書</th><th>断片</th><th>候補</th><th>非表示の印</th><th></th></tr></thead><tbody>${rows}</tbody></table>`
      + docs.map((d) => candidateList(d)).join('');
  }

  function candidateList(d) {
    const c = d.candidates || [];
    if (!c.length) return `<p class="dv3-sub">${esc(d.name)}: 確認した範囲では指摘はありません。網羅性は未検証です。</p>`;
    const li = c.slice(0, 50).map((f) => `<li><span class="dv3-loc">${esc(f.location)}</span> ${esc(f.message)}</li>`).join('');
    return `<details class="dv3-cands"><summary>${esc(d.name)} の候補 ${esc(c.length)} 件</summary><ul>${li}</ul>`
      + `${c.length > 50 ? '<p class="mut">先頭 50 件を表示しています。</p>' : ''}</details>`;
  }

  function pairRow(p) {
    const btns = DECISIONS.map(([v, label]) => `<button type="button" class="dv3-dec${p.decision === v ? ' is-on' : ''}" aria-pressed="${p.decision === v}" data-dv3-pair="${esc(p.id)}" data-dv3-dec="${v}">${label}</button>`).join('');
    const side = (s) => `<div class="dv3-loc">${esc(s.doc_name)} ${esc(s.location)}</div><div>${esc(s.text)}</div>`;
    return `<tr><td><span class="dv3-kind dv3-kind-${esc(p.kind)}">${esc(KIND_WORD[p.kind] || p.kind)}</span><div class="mut">${esc(p.reason)}</div></td>`
      + `<td>${side(p.a)}</td><td>${side(p.b)}</td><td><div class="dv3-decs" role="group" aria-label="判断">${btns}</div></td></tr>`;
  }

  function renderPairs() {
    const sc = state.set_check || {};
    const el = $('#dv3Pairs');
    if (!sc.ran) { el.innerHTML = '<p class="dv3-empty">まだ実行していません。「検査を実行」を押してください。</p>'; return; }
    const notes = (sc.unchecked || []).map((t) => `<li>${esc(t)}</li>`).join('');
    const foot = `<ul class="dv3-notes">${notes}</ul>`;
    if (!sc.pairs.length) { el.innerHTML = `<p class="dv3-empty">${esc(sc.empty_message || '確認した範囲では指摘はありません。網羅性は未検証です。')}</p>${foot}`; return; }
    el.innerHTML = `<p class="mut">${esc(sc.units)} 文を比べ、${esc(sc.pairs.length)} 組の候補が見つかりました。${esc(COVERAGE)}</p>`
      + `<table class="dv3-table"><thead><tr><th>候補</th><th>文 A</th><th>文 B</th><th>判断</th></tr></thead><tbody>${sc.pairs.map(pairRow).join('')}</tbody></table>${foot}`;
  }

  function renderTrace() {
    const t = state.trace || {};
    const fmt = $('#dv3Format');
    fmt.innerHTML = (state.formats || []).map((f) => `<option value="${esc(f.id)}"${f.id === state.trace_format ? ' selected' : ''}>${esc(f.label)}（例: ${esc(f.example)}）</option>`).join('');
    const c = t.complete || {};
    const rate = c.rate === null || c.rate === undefined ? '—' : `${c.rate}%（${c.covered}/${c.total}）`;
    const warn = [...(t.messages || []), ...(t.unreadable || []).map((u) => `${u.doc}: ${u.message}`)]
      .map((m) => `<p class="dv3-warn" role="alert">${esc(m)}</p>`).join('');
    const orphans = (t.orphans || []).map((o) => `<li>${esc(o.id)}（${esc(o.kind_label)}: ${esc(o.locations.join('／'))}）</li>`).join('');
    $('#dv3TraceSummary').innerHTML = `${warn}<div class="dv3-stats"><div class="dv3-stat"><span>完全率</span><b>${esc(rate)}</b></div>`
      + `<div class="dv3-stat"><span>孤立（上流の無い下流 ID）</span><b>${esc((t.orphans || []).length)} 件</b></div></div>`
      + (orphans ? `<ul class="dv3-notes">${orphans}</ul>` : '');
    const cols = t.columns || [];
    if (!(t.rows || []).length) { $('#dv3Trace').innerHTML = `<p class="dv3-empty">追跡表の行はありません。${esc(COVERAGE)}</p>`; return; }
    const head = `<tr><th>ID</th>${cols.map((x) => `<th>${esc(x.label)}</th>`).join('')}</tr>`;
    const body = t.rows.map((r) => `<tr><th scope="row">${esc(r.id)}</th>${cols.map((x) => {
      const v = r[x.kind] || [];
      return v.length ? `<td>${v.map(esc).join('<br>')}</td>` : '<td class="dv3-gap">対応なし</td>';
    }).join('')}</tr>`).join('');
    $('#dv3Trace').innerHTML = `<table class="dv3-table" id="dv3TraceTable"><thead>${head}</thead><tbody>${body}</tbody></table>`;
  }

  function render(data) {
    state = data;
    renderDocs();
    renderPairs();
    renderTrace();
  }

  async function load() {
    if (!iid()) return;
    msg('読み込み中…');
    try { render(await DV.api(base())); msg(''); } catch (e) { msg('読み込めませんでした。再読み込みしてください。'); }
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
      try { render(await DV.api(`${base()}/documents`, { method: 'POST', form })); DV.toast('文書を登録しました。'); $('#dv3File').value = ''; } catch (err) { msg(''); }
    }, '登録中…');
  }

  async function act(path, opts, done) {
    try { render(await DV.api(path, opts)); if (done) DV.toast(done); } catch (e) { /* 失敗の文は DV.api が帯に出す */ }
  }

  function bind() {
    $('#dv3Upload').addEventListener('submit', upload);
    $('#dv3Run').addEventListener('click', () => DV.busy($('#dv3Run'), () => act(`${base()}/setcheck`, { method: 'POST', json: {} }, '集合の検査を実行しました。'), '検査中…'));
    $('#dv3Format').addEventListener('change', (e) => act(`${base()}/trace`, { method: 'POST', json: { format: e.target.value } }));
    $('#dv3Xlsx').addEventListener('click', () => DV.download(`${base()}/trace.xlsx`, '追跡表.xlsx'));
    $('#dv3Rules').addEventListener('submit', saveRules);
    document.querySelector('[data-view="setcheck"]').addEventListener('click', (e) => {
      const del = e.target.closest('[data-dv3-del]');
      if (del) { act(`${base()}/documents/${encodeURIComponent(del.dataset.dv3Del)}`, { method: 'DELETE' }, '文書を外しました。'); return; }
      const b = e.target.closest('[data-dv3-dec]');
      if (b) {
        const word = DECISIONS.find(([v]) => v === b.dataset.dv3Dec)[1];
        act(`${base()}/setcheck/${encodeURIComponent(b.dataset.dv3Pair)}`, { method: 'POST', json: { decision: b.dataset.dv3Dec } },
          word === '問題なし' ? '「問題なし」を記録しました。' : `指摘に種別「${word}」で追加しました。`);
      }
    });
  }

  const lines = (id) => $(id).value.split('\n').map((s) => s.trim()).filter(Boolean);

  async function loadRules() {
    try {
      const s = await DV.api('/api/docverify/r3/settings');
      const off = new Set(s.disabled_rules || []);
      $('#dv3RuleList').innerHTML = (s.rules || []).map((r) => `<label class="dv3-check"><input type="checkbox" value="${esc(r)}"${off.has(r) ? '' : ' checked'}> ${esc(r)}</label>`).join('');
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
    } catch (err) { /* 帯に出る */ }
  }

  function kinds() {
    $('#dv3Kind').innerHTML = '<option value="">選んでください</option><option value="requirement">要件</option><option value="design">設計</option><option value="test">テスト</option>';
  }

  let bound = false;
  DV.on('setcheck', () => {
    if (!bound) { bound = true; kinds(); bind(); }
    load();
    loadRules();
  });
})();
