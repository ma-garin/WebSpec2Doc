/* ドキュメント検証（System 06）の土台: 画面の切り替え・API 呼び出し・エスケープ・通知。
 * 各画面は docverify-global.js / docverify-review.js が DV.on(view, fn) で描く。 */
(() => {
  'use strict';
  const REVIEW_VIEWS = ['plan', 'read', 'triage', 'questions', 'followup', 'screen', 'gate'];
  const TITLES = {
    home: 'ホーム', mine: '自分の担当', reviews: 'レビュー一覧', findings: '指摘一覧',
    plan: '計画', read: '文書を読む', triage: '指摘の検討', questions: '質問票', followup: '修正版の確認',
    screen: '実画面との照合', gate: '判定と記録', checklists: '観点チェックリスト', metrics: 'メトリクス', settings: '設定',
  };
  const NET_ERR = 'サーバに接続できませんでした。少し待ってから、もう一度お試しください。';
  const handlers = {};
  const $ = (s) => document.querySelector(s);

  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function banner(msg) {
    const b = $('#dv-banner');
    b.textContent = msg || '';
    b.hidden = !msg;
  }

  let toastTimer = 0;
  function toast(msg) {
    const t = $('#dv-toast');
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 2600);
  }

  async function api(path, opts = {}) {
    const init = { method: opts.method || 'GET', headers: {} };
    if (opts.form) init.body = opts.form;
    else if (opts.json !== undefined) { init.body = JSON.stringify(opts.json); init.headers['Content-Type'] = 'application/json'; }
    else if (opts.body !== undefined) { init.body = opts.body; Object.assign(init.headers, opts.headers || {}); }  // fetch 互換の書き方も受ける
    let res;
    try { res = await fetch(path, init); } catch (e) { banner(NET_ERR); throw e; }
    if (opts.raw) {
      if (!res.ok) { banner(NET_ERR); throw new Error(String(res.status)); }
      return res;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      banner(data.error || NET_ERR);
      const err = new Error(data.error || String(res.status));
      err.status = res.status; err.data = data;
      throw err;
    }
    banner('');
    return data;
  }

  function setCounts() {
    const r = DV.state.review;
    const f = (r && r.findings) || [];
    const set = (k, n) => document.querySelectorAll(`[data-count="${k}"]`).forEach((el) => { el.textContent = n ? String(n) : ''; });
    set('candidates', f.filter((x) => x.status === 'candidate').length);
    set('adopted', f.filter((x) => x.status === 'adopted').length);
  }

  function renderReviewNav() {
    const r = DV.state.review;
    $('#dv-review-nav').hidden = !r;
    const name = $('#dv-review-name');
    name.hidden = !r;
    name.textContent = r ? r.name : '';
    setCounts();
  }

  function show(view) {
    if (!TITLES[view]) view = 'home';
    if (REVIEW_VIEWS.includes(view) && !DV.state.review) view = 'reviews';
    document.querySelectorAll('.dv-view').forEach((v) => { v.hidden = v.dataset.view !== view; });
    document.querySelectorAll('[data-nav]').forEach((a) => a.classList.toggle('active', a.dataset.nav === view));
    const title = $('#topbar-title');
    if (title) title.textContent = TITLES[view];
    const crumb = $('#topbar-breadcrumb');
    if (crumb) {
      const r = DV.state.review;
      crumb.innerHTML = `<span>WebSpec2Doc</span><span class="sep">/</span><span>ドキュメント検証</span>`
        + (r && REVIEW_VIEWS.includes(view) ? `<span class="sep">/</span><span>${esc(r.name)}</span>` : '');
    }
    DV.current = view;
    if (location.hash.slice(1) !== view) history.replaceState(null, '', `#${view}`);
    banner('');
    (handlers[view] || []).forEach((fn) => { try { fn(); } catch (e) { console.error(e); banner('画面を表示できませんでした。再読み込みしてください。'); } });
  }

  async function openReview(iid, view = 'read') {
    const data = await api(`/api/docverify/inspections/${encodeURIComponent(iid)}`);
    DV.state.review = data.inspection;
    DV.state.summary = data.summary;
    try { sessionStorage.setItem('dv-review', iid); } catch (e) { /* 保存できない環境では復元しないだけ */ }
    renderReviewNav();
    show(view);
  }

  function setReview(data) {
    DV.state.review = data.inspection;
    DV.state.summary = data.summary;
    renderReviewNav();
  }

  async function start() {
    document.querySelectorAll('[data-nav]').forEach((a) => a.addEventListener('click', (e) => { e.preventDefault(); show(a.dataset.nav); }));
    let saved = null;
    try { saved = sessionStorage.getItem('dv-review'); } catch (e) { saved = null; }
    if (saved) { try { await openReview(saved, location.hash.slice(1) || 'read'); return; } catch (e) { banner(''); } }
    show(location.hash.slice(1) || 'home');
  }

  window.DV = {
    api, esc, show, toast, openReview, setReview, start, banner,
    state: { review: null, summary: null },
    on(view, fn) { (handlers[view] = handlers[view] || []).push(fn); },
    refreshNav: renderReviewNav,
    PHASES: [['plan', '計画'], ['individual', '個別レビュー'], ['triage', '指摘の検討'], ['rework', '修正'], ['followup', '修正版の確認'], ['closed', '判定と記録']],
  };
})();
