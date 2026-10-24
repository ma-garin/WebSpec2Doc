/* 案件一覧（cases）と判定と記録（gate）。一般レビューは inspection/tier、対検査は pair API を使う。
 * 状態: 読込中・0 件・検索 0 件・失敗・通常・作成中・作成失敗・権限なし（403）・競合（409）。
 * 共通の UIStates があればそれで描き、無ければ同じ文言で自前の枠に描く。 */
(function () {
  'use strict';
  const STAGES = ['計画', '対検査', '質問', '判定', '承認'];
  const VCLS = { 合格: 'ok', 不合格: 'ng', 判定不能: 'na' };
  const MSG = { 0: 'サーバに接続できませんでした。少し待ってから再読み込みしてください。', 403: 'この操作の権限がありません。ログインし直すか、管理者に依頼してください。',
    409: '他の人が先に更新しました。再読み込みしてから操作してください。', 500: '処理に失敗しました。時間をおいて再読み込みしてください。' };
  const C = { list: [], q: '', pending: null, busy: false };
  try { C.pending = JSON.parse(sessionStorage.getItem('dv-cases-pending') || 'null'); } catch (e) { /* 保存できない環境 */ }
  function savePending(value) { C.pending = value; try { if (value) sessionStorage.setItem('dv-cases-pending', JSON.stringify(value)); else sessionStorage.removeItem('dv-cases-pending'); } catch (e) { /* 同じ画面内では保持 */ } }
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const sec = (v) => document.querySelector(`section.dv-view[data-view="${v}"]`);
  const roleLabel = (role, fallback) => ({ baseline: '基準', target: '確認対象', reference: '参照' }[role] || fallback);
  const who = (u) => ({ _none: '未ログインの利用者', _seed: '取り込み' }[u] || u);
  const when = (v) => window.DV.fmtJst(v);   // 対検査と同じ日本時間の整形（docverify-core.js）

  async function call(url, opts = {}) {
    let res;
    try { res = await fetch(url, Object.assign({ headers: { Accept: 'application/json' } }, opts)); } catch (e) { throw Object.assign(new Error(MSG[0]), { status: 0 }); }
    const data = await res.json().catch(() => null);
    if (!res.ok) throw Object.assign(new Error((data && (typeof data.error === 'string' ? data.error : data.error && data.error.message)) || MSG[res.status] || MSG[500]), { status: res.status });
    if (data === null) throw Object.assign(new Error(MSG[500]), { status: 500 });
    return data;
  }

  function state(root, body, kind, message, action) {
    root.dataset.state = kind;
    if (kind === 'normal') return;
    if (typeof UIStates !== 'undefined' && UIStates.set) {
      try { UIStates.set(body, kind === 'search-empty' ? 'no-match' : kind, { msg: message, cta: action && kind !== 'loading' ? { label: action.label, onClick: action.fn } : null }); return; } catch (e) { /* 自前で描く */ }
    }
    /* ui-states.js は defer なので、起動直後はまだ無い。読み込み後に共通部品で描き直す（途中で状態が変わっていれば何もしない） */
    if (typeof UIStates === 'undefined' && document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => { if (root.dataset.state === kind && !body.querySelector('.ui-state')) { body.replaceChildren(); state(root, body, kind, message, action); } }, { once: true });
    }
    body.innerHTML = `<div class="dvc-state" data-kind="${esc(kind)}">${kind === 'loading' ? '<div class="p1-skel" aria-hidden="true"><i></i><i></i><i></i></div>' : ''}<p>${esc(message)}</p>`
      + (action ? `<button type="button" class="p1-btn is-primary" data-state-act>${esc(action.label)}</button>` : '') + '</div>';
    const b = body.querySelector('[data-state-act]');
    if (b) b.addEventListener('click', action.fn);
  }

  /* ---- 案件一覧 ---- */
  function steps(cur) {
    return '<span class="dvc-stage" aria-label="現在の工程">' + esc(cur || '計画') + '</span>';
  }
  function openCreate() {
    const root = sec('cases'), dialog = root.querySelector('[data-cases-dialog]');
    msg(root, '[data-cases-msg]', '');
    syncPurpose(root.querySelector('[data-cases-form]'));
    if (!dialog.open) dialog.showModal();
    root.querySelector('[name=name]').focus();
  }
  const docName = (n) => String(n || '').replace(/\.[A-Za-z0-9]{1,5}$/, '');   // ファイル名は出さず文書名だけ
  const docVer = (v) => (v ? ` 第${esc(v)}版` : '');
  function row(c) {
    const open = c.inspection_id || c.iid;
    if (c.general) return `<tr tabindex="0" data-open="${esc(open)}" data-general="1"><td class="c-name"><a class="dvc-case-link" href="?iid=${encodeURIComponent(open)}#trace">${esc(c.name)}</a></td><td class="c-doc">文書 ${esc(c.documents)} 件</td><td class="c-stage">文書の確認</td><td class="c-due">${esc(c.due || '未設定')}</td><td class="c-f">関係を確認</td><td class="c-v">未判定</td><td class="c-who">—</td></tr>`;
    return `<tr tabindex="0" data-open="${esc(open)}"><td class="c-name" title="${esc(c.name)}"><a class="dvc-case-link" href="?iid=${encodeURIComponent(open)}#pair">${esc(c.name)}</a></td>`
      + `<td class="c-doc" title="${esc(docName(c.baseline_name) || '要件定義書')} ⇔ ${esc(docName(c.target_name) || '基本設計書')}"><span class="dvc-doc-line">基準: ${esc(docName(c.baseline_name) || '要件定義書')}${docVer(c.baseline_version)}</span><span class="dvc-doc-line">確認: ${esc(docName(c.target_name) || '基本設計書')}${docVer(c.target_version)}</span></td>`
      + `<td class="c-stage">${steps(c.stage)}</td><td class="c-due">${esc(c.due || '未設定')}</td>`
      + `<td class="c-f"><span class="${c.critical_open ? 'dvc-crit' : ''}">重大 ${esc(c.critical_open)}</span>／未解消 ${esc(c.unresolved)}</td>`
      + `<td class="c-v"><span class="dvc-chip ${VCLS[c.verdict] || 'na'}"${c.verdict === '判定不能' ? ' title="検査が未実行です。開いて検査を実行してください"' : ''}>${esc(c.verdict)}</span></td>`
      + `<td class="c-who" title="${esc(c.assignee)}">${esc(c.assignee ? who(c.assignee) : '未着手')}</td></tr>`;
  }
  function renderCases() {
    const root = sec('cases'), body = root.querySelector('[data-cases-body]');
    const q = C.q.trim().toLowerCase();
    const list = q ? C.list.filter((c) => String(c.name).toLowerCase().includes(q)) : C.list;
    root.querySelector('[data-cases-count]').textContent = C.list.length ? `${C.list.length} 件` + (q ? `（表示 ${list.length} 件）` : '') : '';
    if (!C.list.length) return state(root, body, 'empty', 'レビューはまだありません。確認したい資料から、最初のレビューを作成できます。', { label: '新しいレビュー', fn: openCreate });
    if (!list.length) return state(root, body, 'search-empty', `「${C.q}」に一致するレビューはありません。`, { label: '絞り込みを解除', fn: () => { C.q = ''; root.querySelector('[data-cases-q]').value = ''; renderCases(); } });
    root.dataset.state = 'normal';
    body.innerHTML = '<table class="dvc-t" aria-label="レビュー一覧"><thead><tr><th class="c-name">レビュー名</th><th class="c-doc">対象文書と版</th><th class="c-stage">工程</th>'
      + '<th class="c-due">期限</th><th class="c-f">指摘</th><th class="c-v">判定</th><th class="c-who">担当</th></tr></thead><tbody>'
      + list.map(row).join('') + '</tbody></table>';
    body.querySelectorAll('tr[data-open]').forEach((tr) => {
      const go = () => (tr.dataset.general ? openDocuments(tr.dataset.open, tr.querySelector('.dvc-case-link').textContent) : DV.openReview(tr.dataset.open, 'pair')).catch((e) => msg(root, '[data-cases-msg]', e.message || MSG[500], true));
      tr.addEventListener('click', (e) => { if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return; e.preventDefault(); go(); });
      tr.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    });
  }
  function msg(root, sel, text, err) { root.querySelectorAll(sel).forEach((m) => { m.textContent = text || ''; m.classList.toggle('is-err', !!err); }); }
  async function loadCases() {
    const root = sec('cases'), body = root.querySelector('[data-cases-body]');
    state(root, body, 'loading', 'レビューの一覧を読み込んでいます。');
    try {
      const [pairs, inspections] = await Promise.all([call('/api/docverify/pair/cases'), call('/api/docverify/inspections')]);
      const list = pairs.cases || [], pairIds = new Set(list.map((c) => c.inspection_id));
      C.list = list.concat((inspections.inspections || []).filter((i) => !pairIds.has(i.id)).map((i) => ({ general: true, iid: i.id, name: i.name, due: i.due, documents: ((i.tier || {}).documents || []).length })));
      renderCases();
    }
    catch (e) { state(root, body, e.status === 403 ? 'forbidden' : 'error', e.message, { label: 'もう一度読み込む', fn: loadCases }); }
  }
  async function openDocuments(iid, name) {
    if (!window.DVT || !window.DVT.open) throw new Error('文書の確認画面を読み込めませんでした。ページを再読み込みしてください。');
    await DV.openReview(iid, 'trace');
    DVT.open(iid, name);
  }
  function syncPurpose(form) {
    const pending = C.pending, multi = pending || form.elements.purpose.value === 'multi';
    if (pending) form.elements.purpose.value = 'multi';
    form.querySelectorAll('[data-cases-multi]').forEach((el) => { el.hidden = !multi; });
    form.querySelectorAll('[data-cases-pair]').forEach((el) => { el.hidden = !!multi; });
    form.querySelectorAll('[name=purpose]').forEach((el) => { el.disabled = !!pending || C.busy; });
    ['requirements', 'design', 'baseline_role', 'target_role', 'baseline_version', 'target_version'].forEach((name) => { form.elements[name].disabled = !!multi; });
    form.elements.documents.disabled = !multi;
    form.elements.name.readOnly = !!pending;
    if (pending) { form.elements.name.value = pending.name; form.elements.due.value = pending.due || ''; }
    form.querySelector('[data-cases-recovery]').hidden = !pending;
    form.querySelector('[data-cases-recovery-message]').textContent = pending ? 'レビューは作成済みです。文書を選び直して再送できます。同じ名前の文書は置き換わります。確認画面で登録済み文書を確かめてください。' : '';
    form.querySelectorAll('[data-cases-files]').forEach((el) => {
      const files = Array.from(form.elements[el.dataset.casesFiles].files);
      el.textContent = files.length ? files.map((f) => f.name).join('、') : '文書が選択されていません。';
      el.dataset.state = files.length ? 'normal' : 'empty';
    });
    form.querySelector('[data-cases-submit]').textContent = pending ? '同じレビューへ文書を再送' : multi ? '作成して文書の確認へ' : '作成して比較へ';
  }
  async function create(ev) {
    ev.preventDefault();
    if (C.busy) return;
    const root = sec('cases'), form = ev.currentTarget, btn = form.querySelector('[data-cases-submit]');
    const name = form.elements.name.value.trim(), multi = C.pending || form.elements.purpose.value === 'multi';
    if (!name) return msg(root, '[data-cases-msg]', 'レビュー名を入力してください。', true);
    if (!form.reportValidity()) return;
    const files = Array.from(form.elements.documents.files);
    if (multi) {
      if (!files.length) return msg(root, '[data-cases-msg]', '確認する文書を選んでください。', true);
      if (files.some((f) => !/\.(md|docx|xlsx)$/i.test(f.name))) return msg(root, '[data-cases-msg]', 'Markdown・Word・Excelの文書を選んでください。', true);
      if (new Set(files.map((f) => f.name)).size !== files.length) return msg(root, '[data-cases-msg]', '同じ名前の文書があります。別の名前にして選び直してください。', true);
    } else {
      if (!form.elements.requirements.files.length || !form.elements.design.files.length) return msg(root, '[data-cases-msg]', '比較する基準文書と確認対象を選んでください。', true);
      if ([form.elements.requirements.files[0], form.elements.design.files[0]].some((f) => !/\.(md|txt)$/i.test(f.name))) return msg(root, '[data-cases-msg]', '比較する文書はMarkdown・テキストを選んでください。Word・Excelは文書セットのレビューで登録できます。', true);
    }
    if (C.pending) savePending({ ...C.pending, due: form.elements.due.value });
    const fd = new FormData(form);
    C.busy = true; btn.disabled = true; form.dataset.state = 'loading'; syncPurpose(form);
    msg(root, '[data-cases-msg]', '文書を取り込んでいます…');
    try {
      if (multi) {
        if (!C.pending) {
          const r = await call('/api/docverify/inspections', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
          savePending({ id: r.inspection.id, name, due: form.elements.due.value });
          syncPurpose(form);
        }
        const pending = C.pending;
        await call('/api/docverify/inspections/' + encodeURIComponent(pending.id), { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ due: form.elements.due.value || null }) });
        const upload = new FormData(); files.forEach((f) => upload.append('file', f));
        const result = await call('/api/docverify/inspections/' + encodeURIComponent(pending.id) + '/tier/documents', { method: 'POST', body: upload });
        const rejected = ((result.upload_report || {}).rejected || []);
        if (rejected.length) throw new Error('一部の文書を登録できませんでした。' + rejected.map((r) => r.name + ': ' + r.reason).join('／') + ' 登録済みレビューを開くか、失敗した文書だけを選び直して再送してください。');
        await openDocuments(pending.id, pending.name);
        savePending(null);
      } else {
        const r = await call('/api/docverify/pair/cases', { method: 'POST', body: fd });
        await DV.openReview(r.inspection_id || r.iid, 'pair');
      }
      form.dataset.state = 'normal'; form.reset(); root.querySelector('[data-cases-dialog]').close();
    } catch (e) { form.dataset.state = 'error'; msg(root, '[data-cases-msg]', (C.pending ? 'レビューは作成済みです。' : '') + e.message, true); }
    finally { C.busy = false; btn.disabled = false; syncPurpose(form); }
  }

  /* ---- 判定と記録 ---- */
  const G = { iid: null, rev: null, trail: [], filter: 'all' };
  const FILT = { all: 'すべて', decide: '採否', approve: '承認・差し戻し' };
  const fkind = (a) => (a === 'approved' || a === 'rejected' ? 'approve' : a === 'review_started' ? 'other' : 'decide');
  function trailItems() {
    const t = G.trail.filter((x) => G.filter === 'all' || fkind(x.action) === G.filter);
    return t.slice().reverse().map((x) =>
      `<li>${esc(when(x.at))} ${esc(who(x.user))} ・ ${esc(DV.actionLabel(x.action))} ${esc(x.target)}${x.reason ? ' ・ ' + esc(x.reason) : ''}</li>`).join('') || '<li>該当する記録はありません。</li>';
  }
  const ids = (a) => (a && a.length ? a.map(esc).join('、') : 'なし');
  function card(title, o) {
    const verdict = DV.verdict(o), cls = DV.gateClass(o);
    return `<div class="dvg-card ${cls}"><h3>${esc(title)} <span class="dvc-chip ${cls}">${esc(verdict)}</span></h3><dl>`
      + `<dt>未解消の重大</dt><dd>${o.unresolved_critical.length} 件: ${ids(o.unresolved_critical)}</dd>`
      + `<dt>欠落リンク</dt><dd>${o.missing_links.length} 件: ${ids(o.missing_links.map((m) => m.req_id))}</dd>`
      + `<dt>要確認</dt><dd>${o.needs_review.length} 件: ${ids(o.needs_review)}</dd>`
      + `<dt>未検証</dt><dd>${o.unverified.length} 件: ${ids(o.unverified)}</dd><dt>未確認の理由</dt><dd>${ids(o.unverified_reasons)}</dd>${o.ai_scope ? `<dt>AI 検査</dt><dd>${esc(o.ai_scope)}</dd>` : ''}</dl></div>`;
  }
  function renderGate(f, trail) {
    const root = sec('gate'), body = root.querySelector('[data-gate-body]'), g = f.gate, m = f.meta || {};
    G.rev = m.rev; G.trail = trail; G.filter = 'all';
    root.querySelector('[data-gate-ver]').textContent = `${m.baseline_name || '要件定義書'}（${roleLabel(m.baseline_role, '基準')}・${m.baseline_version || '第 ' + (m.req_version || 1) + ' 版'}） ⇔ ${m.target_name || '基本設計書'}（${roleLabel(m.target_role, '確認対象')}・${m.target_version || '第 ' + (m.design_version || 1) + ' 版'}） ・ 指摘 ${f.findings.length} 件`;
    root.dataset.state = 'normal';
    const approved = trail.find((t) => t.action === 'approved');
    const hint = approved ? `${approved.user} が ${when(approved.at)} に承認済みです。` : DV.verdict(g.overall) === '判定不能' ? '判定不能です。未確認の理由を読み、対象と比較条件を確かめて再検査してください。' : g.overall.pass ? '全体が合格です。理由を書いて承認できます（起票者は承認できません）。' : '全体が不合格のため承認できません。';
    body.innerHTML = `<div class="dvg-grid"><div><div class="dvg-cards">${card('全体', g.overall)}${card('今回の変更分', g.changed)}</div>`
      + `<p class="dvg-why"><b>判定の根拠</b><br>${g.reasons.map(esc).join('<br>')}</p></div>`
      + `<div class="dvg-side"><div class="dvg-box"><h3>承認</h3><p class="dvg-hint">${esc(hint)}</p>`
      + `<textarea rows="2" maxlength="500" aria-label="承認の理由" data-gate-reason placeholder="例: 重大な指摘はすべて解消済み。"></textarea>`
      + `<div class="dvg-row"><span class="dvg-err" role="alert" data-gate-err></span><button type="button" class="p1-btn is-primary" data-gate-act="approve"${g.overall.pass && !approved ? '' : ' disabled'}>承認する</button></div></div>`
      + `<div class="dvg-box"><h3>証跡（新しい順）</h3><div class="dvg-filter" role="group" aria-label="証跡の絞り込み">${Object.keys(FILT).map((k) => `<button type="button" class="dvc-chip ${k === 'all' ? 'ok' : 'na'}" data-gate-filter="${k}" aria-pressed="${k === 'all'}">${FILT[k]}</button>`).join('')}</div><ol class="dvg-log" data-gate-log>${trailItems()}</ol></div></div></div>`;
  }
  const pbase = () => `/api/docverify/${encodeURIComponent(G.iid)}/pair`;
  async function loadGate() {
    const rv = DV.state.review, root = sec('gate'), body = root.querySelector('[data-gate-body]');
    if (!rv) return;
    G.iid = rv.id; msg(root, '[data-gate-msg]', '');
    state(root, body, 'loading', '判定を読み込んでいます。');
    try {
      const [f, t] = await Promise.all([call(pbase() + '/findings'), call(pbase() + '/trail').catch(() => [])]);
      renderGate(f, t);
    } catch (e) {
      state(root, body, e.status === 404 ? 'empty' : e.status === 403 ? 'forbidden' : 'error',
        e.status === 404 ? 'このレビューには対検査の記録がありません。案件一覧から対検査のレビューを開いてください。' : e.message, { label: 'もう一度読み込む', fn: loadGate });
    }
  }
  async function approve(btn) {
    const root = sec('gate'), reason = root.querySelector('[data-gate-reason]').value.trim(), err = root.querySelector('[data-gate-err]');
    if (!reason) { err.textContent = '承認の理由を入力してください。'; return; }
    btn.disabled = true; err.textContent = '';
    try {
      await call(pbase() + '/approve', { method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: JSON.stringify({ reason, rev: G.rev }) });
      DV.toast('承認を記録しました'); await loadGate();
    } catch (e) { err.textContent = e.message; btn.disabled = false; }
  }
  /* 指摘書を出力: 形式（Markdown／Word／Excel）を選ぶメニュー。Esc・外側クリックで閉じる */
  function report(btn) {
    const rv = DV.state.review;
    if (!rv) return;
    const open = document.querySelector('[data-dv-report-menu]');
    if (open) { open.remove(); return; }
    const base = `/api/docverify/${encodeURIComponent(rv.id)}/pair/report`;
    const menu = document.createElement('div');
    menu.setAttribute('role', 'menu'); menu.setAttribute('data-dv-report-menu', '');
    menu.style.cssText = 'position:absolute;z-index:50;background:#fff;border:1px solid #d0d7de;border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,.12);padding:4px 0;min-width:160px';
    [['md', 'Markdown'], ['docx', 'Word'], ['xlsx', 'Excel']].forEach(([ext, label]) => {
      const a = document.createElement('a');
      a.setAttribute('role', 'menuitem'); a.href = `${base}.${ext}`; a.setAttribute('download', ''); a.textContent = label;
      a.style.cssText = 'display:block;padding:6px 14px;color:inherit;text-decoration:none';
      a.addEventListener('click', () => menu.remove());
      menu.appendChild(a);
    });
    const r = btn.getBoundingClientRect();
    menu.style.top = `${r.bottom + window.scrollY + 4}px`; menu.style.left = `${r.left + window.scrollX}px`;
    document.body.appendChild(menu);
    menu.querySelector('a').focus();
  }

  function init() {
    if (!window.DV || !DV.on) { setTimeout(init, 30); return; }
    const cs = sec('cases'), gs = sec('gate');
    if (cs) {
      DV.on('cases', loadCases);
      const form = cs.querySelector('[data-cases-form]');
      form.addEventListener('submit', create);
      form.addEventListener('change', () => { if (!C.busy) { form.dataset.state = 'normal'; msg(cs, '[data-cases-msg]', ''); syncPurpose(form); } });
      form.querySelector('[data-cases-resume]').addEventListener('click', async () => {
        if (!C.pending || C.busy) return;
        try { await openDocuments(C.pending.id, C.pending.name); savePending(null); cs.querySelector('[data-cases-dialog]').close(); form.reset(); syncPurpose(form); }
        catch (e) { msg(cs, '[data-cases-msg]', e.message, true); }
      });
      syncPurpose(form);
      cs.querySelector('[data-cases-q]').addEventListener('input', (e) => { C.q = e.target.value; if (C.list.length) renderCases(); });
      cs.querySelector('[data-cases-act="reload"]').addEventListener('click', loadCases);
      const nb = document.getElementById('dv-new-review');   // サイドバーの「新しいレビュー」は案件一覧の作成フォームへ
      if (nb) nb.addEventListener('click', (e) => { e.stopImmediatePropagation(); e.preventDefault(); openCreate(); }, true);
      const dialog = cs.querySelector('[data-cases-dialog]');
      cs.querySelectorAll('[data-cases-close]').forEach((b) => b.addEventListener('click', () => dialog.close()));
      dialog.addEventListener('click', (e) => {
        const r = dialog.getBoundingClientRect();
        if (e.target === dialog && (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom)) dialog.close();
      });
      dialog.addEventListener('close', () => nb.focus());
    }
    if (gs) {
      DV.on('gate', loadGate);
      gs.addEventListener('click', (e) => {
        const fb = e.target.closest('[data-gate-filter]');
        if (fb) {
          G.filter = fb.dataset.gateFilter;
          gs.querySelectorAll('[data-gate-filter]').forEach((x) => { const on = x.dataset.gateFilter === G.filter; x.setAttribute('aria-pressed', on); x.classList.toggle('ok', on); x.classList.toggle('na', !on); });
          gs.querySelector('[data-gate-log]').innerHTML = trailItems();
          return;
        }
        const b = e.target.closest('[data-gate-act]');
        if (!b) return;
        if (b.dataset.gateAct === 'reload') loadGate();
        else if (b.dataset.gateAct === 'pair') DV.show('pair');
        else if (b.dataset.gateAct === 'approve') approve(b);
      });
    }
    document.addEventListener('click', (e) => {
      const b = e.target.closest('[data-dv-report]');
      if (b) { report(b); return; }
      if (!e.target.closest('[data-dv-report-menu]')) document.querySelector('[data-dv-report-menu]')?.remove();
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') document.querySelector('[data-dv-report-menu]')?.remove(); });
    if (DV.current === 'cases' && cs) loadCases();
    if (DV.current === 'gate' && gs) loadGate();
  }
  init();   // DV.start() より前に DV.on を登録する（DOMContentLoaded を待つと最初の表示に間に合わない）
})();
