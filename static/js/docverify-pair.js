/* 対検査レビュー（要件定義書 ⇔ 基本設計書）。DV.on('pair') で描く。
 * 状態 6 種（normal/loading/empty/error/unsaved/conflict）は API 応答だけで data-state を切り替える。 */
(() => {
  'use strict';
  const DV = window.DV;
  if (!DV) return;
  const esc = DV.esc;
  const root = () => document.querySelector('.dv-view[data-view="pair"]');
  const q = (s) => root().querySelector(s);
  const S = { iid: null, findings: [], gate: null, meta: {}, docs: null, trail: [], filter: 'all', sel: null, pending: null, seq: 0 };
  const MSG = {
    net: 'サーバに接続できませんでした。通信を確かめてから「再読み込み」を押してください。',
    404: 'この案件には対検査の文書がまだありません。要件定義書と基本設計書を取り込んでから、もう一度開いてください。',
    403: 'この操作をする権限がありません。ログインし直すか、担当者に確認してください。',
    409: 'ほかの人が先に更新しました。「最新を読み込む」を押してから、もう一度操作してください。',
    server: 'サーバで問題が起きました。少し待ってから「再読み込み」を押してください。',
    broken: '受け取った内容を読めませんでした。「再読み込み」を押してください。',
  };
  const ACTION = { review_started: 'レビュー開始', finding_decided: '採否を記録', decision_revoked: '採否を取消', review_completed: 'レビュー完了',
    approval_requested: '承認を依頼', approved: '承認', rejected: '差し戻し' };
  const SEV = { 重大: 'sev-c', 警告: 'sev-w', 提案: 'sev-i' };
  const ST = { 採用: 'st-ok', 不採用: 'st-ng', 要確認: 'st-q' };
  const base = () => `/api/docverify/${encodeURIComponent(S.iid)}/pair`;
  const when = (v) => (v ? String(v).replace('T', ' ').slice(0, 16) : '');

  async function call(path, opts = {}) {
    const init = { method: opts.method || 'GET', headers: { Accept: 'application/json' } };
    if (opts.json !== undefined) { init.body = JSON.stringify(opts.json); init.headers['Content-Type'] = 'application/json'; }
    let res;
    try { res = await fetch(base() + path, init); } catch (e) { throw Object.assign(new Error(MSG.net), { status: 0 }); }
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const m = data && data.error && data.error.message;
      throw Object.assign(new Error(m || MSG[res.status] || MSG.server), { status: res.status });
    }
    if (data === null) throw Object.assign(new Error(MSG.broken), { status: 500 });
    return data;
  }

  function setState(state, msg) {
    const r = root();
    r.dataset.state = state;
    q('[data-pair-state-msg]').textContent = state === 'loading' ? '対検査の内容を読み込んでいます。' : (msg || '');
    q('[data-pair-notice-msg]').textContent = state === 'unsaved' || state === 'conflict' ? msg : '';
    q('[data-pair-msg]').textContent = state === 'loading' ? '読込中' : '';
  }

  function fit() {
    const r = root();
    if (!r || r.hidden) return;
    const top = r.getBoundingClientRect().top;
    r.style.height = `${Math.max(300, window.innerHeight - top - 12)}px`;
  }

  async function load() {
    const rv = DV.state.review;
    if (!rv) return;
    S.iid = rv.id;
    const my = ++S.seq;
    setState('loading');
    fit();
    try {
      const [f, d, t] = await Promise.all([call('/findings'), call('/docs'), call('/trail').catch(() => [])]);
      if (my !== S.seq) return;
      if (!f || !Array.isArray(f.findings) || !d) throw Object.assign(new Error(MSG.broken), { status: 500 });
      take(f, t); S.docs = d;
      render();
      setState(S.findings.length ? 'normal' : 'empty');
    } catch (e) {
      if (my !== S.seq) return;
      setState('error', e.message);
    }
  }

  function take(f, t) {
    S.findings = f.findings || [];
    S.gate = f.gate || null;
    S.meta = f.meta || {};
    if (t) S.trail = Array.isArray(t) ? t : (t.trail || []);
  }

  async function refresh() {
    const [f, t] = await Promise.all([call('/findings'), call('/trail').catch(() => null)]);
    take(f, t);
    render();
    setState(S.findings.length ? 'normal' : 'empty');
  }

  const matches = (f) => ({
    all: true, changed: !!f.changed_in_current, review: f.status === '要確認', critical: f.severity === '重大',
  }[S.filter]);

  function findSection(list, ref) {
    if (!ref || !list.length) return null;
    const key = String(ref.section || '').trim(), quote = String(ref.quote || '').trim();
    const named = key && list.find((s) => s.id === key || s.heading === key || String(s.heading || '').includes(key) || key.includes(String(s.id)));
    if (named && (!quote || String(named.text || '').includes(quote))) return named;
    return (quote && list.find((s) => String(s.text || '').includes(quote))) || named || null;
  }

  function renderDoc(side, doc, ref) {
    const box = q(`[data-doc="${side}"]`);
    q(`[data-ver="${side}"]`).textContent = doc && doc.version ? `第 ${doc.version} 版` : '';
    const list = (doc && doc.sections) || [];
    if (!list.length) { box.innerHTML = '<p class="p1-empty">この文書には読める章がありません。文書を取り込み直してください。</p>'; return; }
    const hit = findSection(list, ref);
    const quote = ref && ref.quote ? esc(String(ref.quote).trim()) : '';
    box.innerHTML = list.map((s) => {
      let body = esc(s.text);
      const on = hit === s;
      if (on && quote && body.includes(quote)) body = body.replace(quote, `<mark class="hl">${quote}</mark>`);
      return `<section class="p1-sec${on ? ' is-hit' : ''}" data-sec-id="${esc(s.id)}"><h4 class="p1-doc-h">${esc(s.heading || s.id)}</h4><p class="p1-doc-b">${body}</p></section>`;
    }).join('');
    const target = box.querySelector('mark.hl') || box.querySelector('.p1-sec.is-hit');
    if (target) target.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  function renderDocs() {
    const f = S.findings.find((x) => x.id === S.sel);
    const d = S.docs || {};
    renderDoc('req', d.requirements, f && f.req_ref);
    renderDoc('design', d.design, f && f.design_ref);
    const rv = d.requirements && d.requirements.version, dv = d.design && d.design.version;
    q('[data-pair-ver]').textContent = rv || dv ? `要件定義書 第 ${rv || '—'} 版 ⇔ 基本設計書 第 ${dv || '—'} 版` : '';
  }

  const ref = (label, r) => (r && (r.section || r.quote) ? `${label} ${esc(r.section || '章不明')}` : `${label} 該当なし`);

  function card(f) {
    const on = f.id === S.sel;
    const st = f.status || '未判定';
    const by = f.decided_by ? `<div class="p1-links">${esc(f.decided_by === '_none' ? '未ログイン' : f.decided_by)}・${esc(when(f.decided_at))}</div>` : '';
    return `<article class="p1-card ${SEV[f.severity] || ''}" data-fid="${esc(f.id)}" tabindex="0" role="option" aria-selected="${on}">
      <div class="p1-card-h"><span class="p1-tag ${SEV[f.severity] || ''}">${esc(f.severity || '警告')}</span><span class="p1-tag">${esc(f.type)}</span>
        <span class="p1-tag ${ST[st] || ''}">${esc(st)}</span>${f.changed_in_current ? '<span class="p1-chg">今回の変更</span>' : ''}
        <span>${f.source === 'user' ? '利用者が追加' : 'AI 検出'}</span></div>
      <p class="p1-card-t">${esc(f.id)} ${esc(f.title)}</p>
      <p class="p1-card-d">${esc(f.description)}</p>
      <div class="p1-links">${ref('要件', f.req_ref)} ／ ${ref('設計', f.design_ref)}</div>${by}
      ${on ? `<div class="p1-acts"><textarea class="dvp-reason" data-reason rows="2" maxlength="500" aria-label="採否の理由" placeholder="理由（例: 設計書 4.2 を修正すれば解消する）"></textarea>
        <button type="button" class="p1-btn" data-decide="採用">採用</button><button type="button" class="p1-btn" data-decide="不採用">不採用</button>
        <button type="button" class="p1-btn" data-decide="要確認">要確認</button><button type="button" class="p1-btn" data-pair-act="revoke"${f.decided_by ? '' : ' disabled'}>取消</button></div>` : ''}
    </article>`;
  }

  function renderList() {
    const n = { all: S.findings.length, changed: 0, review: 0, critical: 0 };
    S.findings.forEach((f) => { if (f.changed_in_current) n.changed += 1; if (f.status === '要確認') n.review += 1; if (f.severity === '重大') n.critical += 1; });
    Object.keys(n).forEach((k) => { const el = q(`[data-n="${k}"]`); if (el) el.textContent = String(n[k]); });
    q('[data-n="tab"]').textContent = String(n.all);
    root().querySelectorAll('[data-filter]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.filter === S.filter)));
    const list = S.findings.filter(matches);
    const box = q('[data-pair-list]');
    box.setAttribute('role', 'listbox'); box.setAttribute('aria-label', '指摘');
    box.innerHTML = list.length ? list.map(card).join('')
      : `<p class="p1-empty">${S.findings.length ? 'この絞り込みに当てはまる指摘はありません。「全件」に戻すと全部見られます。' : '要件定義書と基本設計書の間に指摘はありません。判定帯で合否を確かめてください。'}</p>`;
  }

  function gateBox(label, g) {
    if (!g) return `<div class="p5-gate"><div class="lbl">${esc(label)}</div><div class="val">未判定</div><div class="lbl">判定の材料がまだありません。</div></div>`;
    const c = (k) => (g[k] || []).length;
    return `<div class="p5-gate ${g.pass ? 'ok' : 'ng'}"><div class="lbl">${esc(label)}</div><div class="val">${g.pass ? '合格' : '不合格'}</div>
      <div class="lbl">重大の未解消 ${c('unresolved_critical')}・要確認 ${c('needs_review')}・対応の抜け ${c('missing_links')}・未検証 ${c('unverified')}</div></div>`;
  }

  function renderGate() {
    const g = S.gate || {};
    const dv = S.docs && S.docs.design && S.docs.design.version;
    q('[data-pair-gates]').innerHTML = gateBox('全体', g.overall) + gateBox(dv ? `今回の変更分（第 ${dv} 版）` : '今回の変更分', g.changed);
    q('[data-pair-why]').textContent = (g.reasons || []).join(' ');
    const pass = !!(g.overall && g.overall.pass);
    q('[data-pair-approve-hint]').textContent = pass ? '全体が合格です。理由を書いて承認できます。起票した人は承認できません。'
      : '全体が不合格のため、まだ承認できません。重大と要確認の指摘を片付けてください。';
    syncApprove();
  }

  function syncApprove() {
    const pass = !!(S.gate && S.gate.overall && S.gate.overall.pass);
    q('[data-pair-act="approve"]').disabled = !pass || !q('#dvp-approve-reason').value.trim();
  }

  function renderTrail() {
    const items = S.trail.slice().reverse();
    q('[data-pair-trail]').innerHTML = items.length ? items.map((t) => `<li class="ev"><span class="tm">${esc(when(t.at))}</span><span class="who">${esc(t.user === '_none' ? '未ログイン' : t.user)}</span>
      <span class="t">${esc(ACTION[t.action] || t.action)}</span> <span class="s">${esc(t.target || '')}</span>${t.reason ? `<span class="n">${esc(t.reason)}</span>` : ''}</li>`).join('')
      : '<li class="p1-empty">まだ記録はありません。指摘の採否を決めると、ここに残ります。</li>';
  }

  function render() {
    if (S.sel && !S.findings.some((f) => f.id === S.sel)) S.sel = null;
    renderDocs(); renderList(); renderGate(); renderTrail();
  }

  function tab(name) {
    root().querySelectorAll('[data-tab]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
    root().querySelectorAll('[data-pane]').forEach((p) => { p.hidden = p.dataset.pane !== name; });
  }

  // 書き込み。通信断・サーバ障害は「未保存」（もう一度保存で再送）、409 は「競合」、それ以外は通知だけ
  async function write(job, okMsg, errEl) {
    S.pending = job;
    try {
      await call(job.path, { method: 'POST', json: job.body });
      S.pending = null;
      await refresh();
      DV.toast(okMsg);
      return true;
    } catch (e) {
      if (e.status === 409) { S.pending = null; setState('conflict', e.message || MSG[409]); }
      else if (!e.status || e.status >= 500) setState('unsaved', e.status ? `保存できませんでした。${e.message}` : '保存できませんでした。通信を確かめてから「もう一度保存」を押してください。');
      else { S.pending = null; if (errEl) errEl.textContent = e.message; else DV.toast(e.message); }
      return false;
    }
  }

  function select(fid) {
    S.sel = S.sel === fid ? S.sel : fid;
    renderList(); renderDocs();
    const el = q(`[data-fid="${CSS.escape(fid)}"]`);
    if (el) el.focus({ preventScroll: false });
  }

  function bind() {
    const r = root();
    r.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (b && b.dataset.filter) { S.filter = b.dataset.filter; renderList(); return; }
      if (b && b.dataset.tab) { tab(b.dataset.tab); return; }
      if (b && b.dataset.decide) {
        const c = b.closest('[data-fid]'), reason = (c.querySelector('[data-reason]') || {}).value || '';
        DV.busy(b, () => write({ path: `/findings/${encodeURIComponent(c.dataset.fid)}/decide`, body: { status: b.dataset.decide, reason: reason.trim() } }, `${b.dataset.decide}として記録しました。`), '記録中…');
        return;
      }
      const act = b && b.dataset.pairAct;
      if (act === 'reload') { load(); return; }
      if (act === 'retry' && S.pending) { DV.busy(b, () => write(S.pending, '保存しました。'), '保存中…'); return; }
      if (act === 'revoke') { const c = b.closest('[data-fid]'); DV.busy(b, () => write({ path: `/findings/${encodeURIComponent(c.dataset.fid)}/revoke`, body: {} }, '直前の採否を取り消しました。'), '取消中…'); return; }
      if (act === 'to-approve') { tab('trail'); q('#dvp-approve-reason').focus(); return; }
      if (act === 'approve') {
        const err = q('[data-pair-approve-err]'); err.textContent = '';
        DV.busy(b, () => write({ path: '/approve', body: { reason: q('#dvp-approve-reason').value.trim() } }, '承認を記録しました。', err)
          .then((ok) => { if (ok) q('#dvp-approve-reason').value = ''; syncApprove(); }), '承認中…');
        return;
      }
      if (b) return;
      const c = e.target.closest('[data-fid]');
      if (c && !e.target.closest('textarea')) select(c.dataset.fid);
    });
    r.addEventListener('keydown', (e) => {
      const c = e.target.closest && e.target.closest('[data-fid]');
      if (!c || e.target !== c) return;
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(c.dataset.fid); }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const n = e.key === 'ArrowDown' ? c.nextElementSibling : c.previousElementSibling;
        if (n && n.dataset.fid) n.focus();
      }
    });
    r.addEventListener('input', (e) => { if (e.target.id === 'dvp-approve-reason') syncApprove(); });
    window.addEventListener('resize', fit);
  }

  if (root()) bind(); else document.addEventListener('DOMContentLoaded', () => { if (root()) bind(); });
  DV.on('pair', () => {
    const rv = DV.state.review;
    if (!rv) return;
    if (rv.id !== S.iid) { S.sel = null; S.filter = 'all'; }
    requestAnimationFrame(fit);
    load();
  });
})();
