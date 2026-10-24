/* 修正版の確認（S06 版差分と再レビュー）。DV.on('followup') で描く。
 * API: POST pair/versions（新版）・GET pair/diff（章差分）・GET pair/findings（再レビュー対象）・GET pair/gate（判定帯）。 */
(function () {
  'use strict';
  const MSG = { net: '通信できませんでした。接続を確かめて、もう一度読み込んでください。', server: '読み込めませんでした。時間をおいて、もう一度読み込んでください。',
    404: 'レビューが見つかりません。案件一覧から開き直してください。', broken: '応答を読めませんでした。もう一度読み込んでください。' };
  const CLS = { 変更: 'is-mod', 追加: 'is-add', 削除: 'is-del' };
  const DOCL = { requirements: '基準文書', design: '確認する文書' };
  const S = { iid: null, seq: 0, rev: null };
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const root = () => document.querySelector('.dvf[data-view="followup"]');
  const q = (sel) => root().querySelector(sel);
  const base = () => `/api/docverify/${encodeURIComponent(S.iid)}/pair`;

  async function call(path, init = {}) {
    let res;
    try { res = await fetch(base() + path, { headers: { Accept: 'application/json' }, ...init }); } catch (e) { throw Object.assign(new Error(MSG.net), { status: 0 }); }
    const data = await res.json().catch(() => null);
    if (!res.ok) throw Object.assign(new Error((data && data.error && data.error.message) || MSG[res.status] || MSG.server), { status: res.status, code: data && data.error && data.error.code });
    if (data === null) throw Object.assign(new Error(MSG.broken), { status: 500 });
    return data;
  }

  function setState(state, msg) {
    root().dataset.state = state;
    q('[data-f-state-msg]').textContent = state === 'loading' ? '修正版の内容を読み込んでいます。' : (msg || '');
    q('[data-f-msg]').textContent = state === 'loading' ? '読込中' : (msg && state === 'ready' ? msg : '');
  }

  function renderDiff(diff) {
    const box = q('[data-f-secs]');
    if (!diff) {
      q('[data-f-summary]').textContent = '';
      box.innerHTML = '<li class="dvf-empty">まだ版が 1 つだけです。直した文書を上でアップロードすると、変わった章がここに出ます。</li>';
      return;
    }
    q('[data-f-summary]').textContent = diff.summary;
    box.innerHTML = diff.sections.length ? diff.sections.map((s) => `<li class="dvf-s ${CLS[s.change] || ''}">
      <div class="dvf-s-h"><span class="dvf-tag ${CLS[s.change] || ''}">${esc(s.change)}</span><span>${esc(s.heading)}</span><span class="dvf-s-doc">${esc(DOCL[s.doc] || '')}</span></div>
      <div class="dvf-ex"><p class="is-before"><b>前</b>${esc(s.before_excerpt || '（なし）')}</p><p class="is-after"><b>後</b>${esc(s.after_excerpt || '（なし）')}</p></div></li>`).join('')
      : '<li class="dvf-empty">章の変更はありません。</li>';
  }

  function renderFindings(list) {
    const hit = list.filter((f) => f.changed_in_current);
    q('[data-f-n]').textContent = String(hit.length);
    q('[data-f-list]').innerHTML = hit.length ? hit.map((f) => `<li class="dvf-f"><span class="id">${esc(f.id)}</span>
      <span class="t">${esc(f.title)}</span><span class="dvf-st">${esc(f.status || '未判定')}</span>
      <span class="r">基準 ${esc((f.req_ref || {}).section || '-')} ／ 対象 ${esc((f.design_ref || {}).section || '-')}</span></li>`).join('')
      : '<li class="dvf-empty">変わった章に紐づく指摘はありません。</li>';
  }

  function renderGate(g) {
    const one = (lbl, o) => `<div class="p5-gate ${DV.gateClass(o)}"><div class="lbl">${lbl}</div><div class="val">${DV.verdict(o)}</div></div>`;
    q('[data-f-gates]').innerHTML = one('全体', g.overall) + one('今回の変更分', g.changed);
    const c = g.changed;
    const why = DV.verdict(c) === '判定不能' ? (c.unverified_reasons || ['検査範囲が未確認です。']).join(' ') : c.pass ? '今回の変更分に未解決の問題はありません。' : `今回の変更分: 要確認 ${c.needs_review.length} 件・重大の未解決 ${c.unresolved_critical.length} 件・対応の抜け ${c.missing_links.length} 件。`;
    q('[data-f-why]').textContent = why + ' ' + (g.reasons || []).join('');
  }

  function fit() {   // 対検査と同じく、画面の残りの高さに収めて内側だけスクロールさせる
    const r = root();
    if (!r || r.hidden) return;
    r.style.height = `${Math.max(320, window.innerHeight - r.getBoundingClientRect().top - 12)}px`;
  }

  async function load(note) {
    const rv = DV.state.review;
    if (!rv) return;
    S.iid = rv.id;
    const my = ++S.seq;
    setState('loading');
    try {
      const [fl, gate] = await Promise.all([call('/findings'), call('/gate')]);
      const diff = await call('/diff').catch((e) => { if (e.code === 'version_not_found') return null; throw e; });
      if (my !== S.seq) return;
      const m = fl.meta || {};
      S.rev = m.rev;
      q('[data-f-ver]').textContent = `${m.baseline_name || '基準文書'} v${m.req_version || 1} ／ ${m.target_name || '確認する文書'} v${m.design_version || 1}`;
      renderDiff(diff); renderFindings(fl.findings || []); renderGate(gate);
      setState('ready', note || '');
    } catch (e) {
      if (my === S.seq) setState('error', e.message);
    }
  }

  function syncUpload() {
    const any = Array.from(root().querySelectorAll('input[type=file]')).some((i) => i.files && i.files.length);
    q('[data-f-act="upload"]').disabled = !any;
  }

  async function upload(form) {
    const err = q('[data-f-up-err]');
    err.textContent = '';
    const fd = new FormData();
    form.querySelectorAll('input[type=file]').forEach((i) => { if (i.files[0]) fd.append(i.name, i.files[0]); });
    if (S.rev != null) fd.append('rev', String(S.rev));
    const btn = q('[data-f-act="upload"]');
    btn.disabled = true;
    q('[data-f-msg]').textContent = '取り込み中';
    try {
      const r = await call('/versions', { method: 'POST', body: fd });
      form.reset();
      await load(`取り込みました。要確認に戻した指摘 ${r.reopened.length} 件。`);
    } catch (e) {
      err.textContent = e.message;
      q('[data-f-msg]').textContent = '';
      syncUpload();
    }
  }

  function toPair() {
    DV.show('pair');
    const chip = document.querySelector('.dvp [data-filter="changed"]');
    if (chip) chip.click();   // 対検査は同じ案件なら絞り込みを保つ。読み込み後もこの絞り込みで描く
  }

  function bind() {
    const r = root();
    r.addEventListener('change', (e) => { if (e.target.type === 'file') syncUpload(); });
    r.addEventListener('submit', (e) => { e.preventDefault(); upload(e.target); });
    r.addEventListener('click', (e) => {
      const b = e.target.closest('[data-f-act]');
      if (!b) return;
      if (b.dataset.fAct === 'reload') load();
      else if (b.dataset.fAct === 'to-pair') toPair();
    });
  }

  function init() {
    if (!window.DV || !window.DV.on || !root()) { setTimeout(init, 30); return; }
    bind();
    window.addEventListener('resize', fit);
    DV.on('followup', () => { requestAnimationFrame(fit); load(); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
