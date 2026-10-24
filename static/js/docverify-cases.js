/* 案件一覧（cases）と判定と記録（gate）。API は対検査（/api/docverify/pair/cases・/<iid>/pair/*）だけを使う。
 * 状態: 読込中・0 件・検索 0 件・失敗・通常・作成中・作成失敗・権限なし（403）・競合（409）。
 * 共通の UIStates があればそれで描き、無ければ同じ文言で自前の枠に描く。 */
(function () {
  'use strict';
  const STAGES = ['計画', '対検査', '質問', '判定', '承認'];
  const VCLS = { 合格: 'ok', 不合格: 'ng', 判定不能: 'na' };
  const MSG = { 0: 'サーバに接続できませんでした。少し待ってから再読み込みしてください。', 403: 'この操作の権限がありません。ログインし直すか、管理者に依頼してください。',
    409: '他の人が先に更新しました。再読み込みしてから操作してください。', 500: '処理に失敗しました。時間をおいて再読み込みしてください。' };
  const C = { list: [], q: '' };
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const sec = (v) => document.querySelector(`section.dv-view[data-view="${v}"]`);
  const ACT = { review_started: 'レビュー開始', finding_decided: '採否を記録', finding_revoked: '採否を取り消し', approved: '承認', rejected: '差し戻し' };
  const who = (u) => ({ _none: '未ログインの利用者', _seed: '取り込み' }[u] || u);
  const when = (v) => (v ? String(v).replace('T', ' ').slice(0, 16) : '');

  async function call(url, opts = {}) {
    let res;
    try { res = await fetch(url, Object.assign({ headers: { Accept: 'application/json' } }, opts)); } catch (e) { throw Object.assign(new Error(MSG[0]), { status: 0 }); }
    const data = await res.json().catch(() => null);
    if (!res.ok) throw Object.assign(new Error((data && data.error && data.error.message) || MSG[res.status] || MSG[500]), { status: res.status });
    if (data === null) throw Object.assign(new Error(MSG[500]), { status: 500 });
    return data;
  }

  function state(root, body, kind, message, action) {
    root.dataset.state = kind;
    if (kind === 'normal') return;
    if (typeof UIStates !== 'undefined' && UIStates.set) {
      try { UIStates.set(body, kind === 'search-empty' ? 'empty' : kind, { message, next: action ? action.label : '', onAction: action && action.fn }); return; } catch (e) { /* 自前で描く */ }
    }
    body.innerHTML = `<div class="dvc-state" data-kind="${esc(kind)}">${kind === 'loading' ? '<div class="p1-skel" aria-hidden="true"><i></i><i></i><i></i></div>' : ''}<p>${esc(message)}</p>`
      + (action ? `<button type="button" class="p1-btn is-primary" data-state-act>${esc(action.label)}</button>` : '') + '</div>';
    const b = body.querySelector('[data-state-act]');
    if (b) b.addEventListener('click', action.fn);
  }

  /* ---- 案件一覧 ---- */
  function steps(cur) {
    const k = STAGES.indexOf(cur);
    return '<span class="dvc-steps" aria-label="工程 ' + esc(cur) + '">' + STAGES.map((s, i) =>
      `<i class="${i < k ? 'is-done' : i === k ? 'is-cur' : ''}"${i === k ? ' aria-current="step"' : ''}>${esc(s)}</i>`).join('') + '</span>';
  }
  function row(c) {
    const open = c.inspection_id || c.iid;
    return `<tr tabindex="0" data-open="${esc(open)}"><td class="c-name" title="${esc(c.name)}">${esc(c.name)}</td>`
      + `<td class="c-doc" title="要件定義書 第 ${c.req_version} 版 ⇔ 基本設計書 第 ${c.design_version} 版">要件 v${esc(c.req_version)} ⇔ 設計 v${esc(c.design_version)}</td>`
      + `<td class="c-stage">${steps(c.stage)}</td><td class="c-due">${esc(c.due || '未設定')}</td>`
      + `<td class="c-f"><span class="${c.critical_open ? 'dvc-crit' : ''}">重大 ${esc(c.critical_open)}</span>／未解消 ${esc(c.unresolved)}</td>`
      + `<td class="c-v"><span class="dvc-chip ${VCLS[c.verdict] || 'na'}">${esc(c.verdict)}</span></td>`
      + `<td class="c-who" title="${esc(c.assignee)}">${esc(c.assignee ? who(c.assignee) : '未着手')}</td></tr>`;
  }
  function renderCases() {
    const root = sec('cases'), body = root.querySelector('[data-cases-body]');
    const q = C.q.trim().toLowerCase();
    const list = q ? C.list.filter((c) => String(c.name).toLowerCase().includes(q)) : C.list;
    root.querySelector('[data-cases-count]').textContent = C.list.length ? `${C.list.length} 件` + (q ? `（表示 ${list.length} 件）` : '') : '';
    if (!C.list.length) return state(root, body, 'empty', 'レビューはまだありません。上のフォームで名前と 2 つの文書を選んで作成してください。');
    if (!list.length) return state(root, body, 'search-empty', `「${C.q}」に一致するレビューはありません。`, { label: '絞り込みを解除', fn: () => { C.q = ''; root.querySelector('[data-cases-q]').value = ''; renderCases(); } });
    root.dataset.state = 'normal';
    body.innerHTML = '<table class="dvc-t"><thead><tr><th class="c-name">レビュー名</th><th class="c-doc">対象文書と版</th><th class="c-stage">工程</th>'
      + '<th class="c-due">期限</th><th class="c-f">指摘</th><th class="c-v">判定</th><th class="c-who">担当</th></tr></thead><tbody>'
      + list.map(row).join('') + '</tbody></table>';
    body.querySelectorAll('tr[data-open]').forEach((tr) => {
      const go = () => DV.openReview(tr.dataset.open, 'pair').catch((e) => msg(root, '[data-cases-msg]', e.message || MSG[500], true));
      tr.addEventListener('click', go);
      tr.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    });
  }
  function msg(root, sel, text, err) { const m = root.querySelector(sel); m.textContent = text || ''; m.classList.toggle('is-err', !!err); }
  async function loadCases() {
    const root = sec('cases'), body = root.querySelector('[data-cases-body]');
    state(root, body, 'loading', 'レビューの一覧を読み込んでいます。');
    try { C.list = (await call('/api/docverify/pair/cases')).cases || []; renderCases(); }
    catch (e) { state(root, body, e.status === 403 ? 'forbidden' : 'error', e.message, { label: 'もう一度読み込む', fn: loadCases }); }
  }
  async function create(ev) {
    ev.preventDefault();
    const root = sec('cases'), form = ev.currentTarget, btn = form.querySelector('[data-cases-submit]');
    const fd = new FormData(form);
    if (!String(fd.get('name') || '').trim()) return msg(root, '[data-cases-msg]', 'レビュー名を入力してください。', true);
    if (!form.requirements.files.length || !form.design.files.length) return msg(root, '[data-cases-msg]', '要件定義書と基本設計書の 2 つのファイルを選んでください。', true);
    btn.disabled = true; msg(root, '[data-cases-msg]', '取り込んで自動検査しています…');
    try {
      const r = await call('/api/docverify/pair/cases', { method: 'POST', body: fd });
      form.reset();
      const skipped = (r.errors || []).length ? `（未実行の検査 ${r.errors.length} 件）` : '';
      msg(root, '[data-cases-msg]', `作成しました。自動検査の指摘 ${r.added} 件${skipped}。`);
      await DV.openReview(r.inspection_id || r.iid, 'pair');
    } catch (e) { msg(root, '[data-cases-msg]', e.message, true); } finally { btn.disabled = false; }
  }

  /* ---- 判定と記録 ---- */
  const G = { iid: null, rev: null };
  const ids = (a) => (a && a.length ? a.map(esc).join('、') : 'なし');
  function card(title, o) {
    const ok = o.pass;
    return `<div class="dvg-card ${ok ? 'ok' : 'ng'}"><h3>${esc(title)} <span class="dvc-chip ${ok ? 'ok' : 'ng'}">${ok ? '合格' : '不合格'}</span></h3><dl>`
      + `<dt>未解消の重大</dt><dd>${o.unresolved_critical.length} 件: ${ids(o.unresolved_critical)}</dd>`
      + `<dt>欠落リンク</dt><dd>${o.missing_links.length} 件: ${ids(o.missing_links.map((m) => m.req_id))}</dd>`
      + `<dt>要確認</dt><dd>${o.needs_review.length} 件: ${ids(o.needs_review)}</dd>`
      + `<dt>未検証</dt><dd>${o.unverified.length} 件: ${ids(o.unverified)}</dd></dl></div>`;
  }
  function renderGate(f, trail) {
    const root = sec('gate'), body = root.querySelector('[data-gate-body]'), g = f.gate, m = f.meta || {};
    G.rev = m.rev;
    root.querySelector('[data-gate-ver]').textContent = `要件定義書 第 ${m.req_version || 1} 版 ⇔ 基本設計書 第 ${m.design_version || 1} 版 ・ 指摘 ${f.findings.length} 件`;
    if (!f.findings.length) return state(root, body, 'empty', '指摘がまだありません。対検査で指摘を確かめてから判定してください。', { label: '対検査へ', fn: () => DV.show('pair') });
    root.dataset.state = 'normal';
    const approved = trail.find((t) => t.action === 'approved');
    const hint = approved ? `${approved.user} が ${when(approved.at)} に承認済みです。` : g.overall.pass ? '全体が合格です。理由を書いて承認できます（起票者は承認できません）。' : '全体が不合格のため承認できません。';
    body.innerHTML = `<div class="dvg-grid"><div><div class="dvg-cards">${card('全体', g.overall)}${card('今回の変更分', g.changed)}</div>`
      + `<p class="dvg-why"><b>判定の根拠</b><br>${g.reasons.map(esc).join('<br>')}</p></div>`
      + `<div class="dvg-side"><div class="dvg-box"><h3>承認</h3><p class="dvg-hint">${esc(hint)}</p>`
      + `<textarea rows="2" maxlength="500" aria-label="承認の理由" data-gate-reason placeholder="例: 重大な指摘はすべて解消済み。"></textarea>`
      + `<div class="dvg-row"><span class="dvg-err" role="alert" data-gate-err></span><button type="button" class="p1-btn is-primary" data-gate-act="approve"${g.overall.pass && !approved ? '' : ' disabled'}>承認する</button></div></div>`
      + `<div class="dvg-box"><h3>証跡（新しい順）</h3><ol class="dvg-log">${trail.slice().reverse().map((t) =>
        `<li>${esc(when(t.at))} ${esc(who(t.user))} ・ ${esc(ACT[t.action] || t.action)} ${esc(t.target)}${t.reason ? ' ・ ' + esc(t.reason) : ''}</li>`).join('') || '<li>記録はまだありません。</li>'}</ol></div></div></div>`;
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
      cs.querySelector('[data-cases-form]').addEventListener('submit', create);
      cs.querySelector('[data-cases-q]').addEventListener('input', (e) => { C.q = e.target.value; if (C.list.length) renderCases(); });
      cs.querySelector('[data-cases-act="reload"]').addEventListener('click', loadCases);
      const nb = document.getElementById('dv-new-review');   // サイドバーの「新しいレビュー」は案件一覧の作成フォームへ
      if (nb) nb.addEventListener('click', (e) => { e.stopImmediatePropagation(); e.preventDefault(); DV.show('cases'); const n = cs.querySelector('[name=name]'); if (n) n.focus(); }, true);
    }
    if (gs) {
      DV.on('gate', loadGate);
      gs.addEventListener('click', (e) => {
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
