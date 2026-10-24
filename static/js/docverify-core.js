/* ドキュメント検証（System 06）の土台: 画面の切り替え・API 呼び出し・エスケープ・通知。
 * 各画面は docverify-global.js / docverify-review.js が DV.on(view, fn) で描く。 */
(() => {
  'use strict';
  const REVIEW_VIEWS = ['pair', 'plan', 'read', 'triage', 'questions', 'followup', 'screen', 'gate'];
  const TITLES = {
    home: 'ホーム', mine: '自分の担当', reviews: 'レビュー一覧', findings: '指摘一覧',
    pair: '対検査', plan: '計画', read: '文書を読む', triage: '指摘の検討', questions: '質問票', followup: '修正版の確認',
    screen: '実画面との照合', gate: '判定と記録', trace: 'トレーサビリティ', assure: 'ドキュメント品質保証', checklists: '検証観点', metrics: '履歴', accuracy: '精度', settings: '設定',
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
  // 英語の通信エラーは日本語に直し、手で閉じるまで残す（クリックで閉じる）
  const NET_RE = /failed to fetch|networkerror|load failed|network request failed/i;
  function toast(msg) {
    const t = $('#dv-toast');
    const net = NET_RE.test(String(msg));
    t.textContent = net ? NET_ERR + '（クリックで閉じる）' : msg;
    t.hidden = false;
    t.style.cursor = net ? 'pointer' : '';
    t.onclick = net ? () => { t.hidden = true; } : null;
    clearTimeout(toastTimer);
    if (!net) toastTimer = setTimeout(() => { t.hidden = true; }, 2600);
  }

  async function api(path, opts = {}) {
    const init = { method: opts.method || 'GET', headers: {} };
    if (opts.form) init.body = opts.form;
    else if (opts.json !== undefined) { init.body = JSON.stringify(opts.json); init.headers['Content-Type'] = 'application/json'; }
    else if (opts.body !== undefined) { init.body = opts.body; Object.assign(init.headers, opts.headers || {}); }  // fetch 互換の書き方も受ける
    let res;
    try { res = await fetch(path, init); } catch (e) { banner(NET_ERR); throw e; }
    if (opts.raw) {
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        banner(data.error || NET_ERR);
        const err = new Error(data.error || String(res.status));
        err.status = res.status; err.data = data;
        throw err;
      }
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

  // サイドの管理群は レビュー一覧・観点・履歴 の 3 つ＋設定。根拠（screen）は履歴の中のタブ。
  // 指摘=「指摘の検討」、根拠=「実画面との照合」の既存画面に対応付ける（新画面は作らない）。
  const SECTIONS = {
    doc: ['home', 'mine', 'reviews', 'findings', 'pair', 'plan', 'read', 'questions', 'followup', 'gate'],
    qa: ['assure'], trace: ['trace'], find: ['triage'], hist: ['metrics', 'screen'], vp: ['checklists', 'accuracy'], set: ['settings'],
  };
  // ドキュメント検証はレビュー一覧 1 画面。ホーム・自分の担当・指摘一覧は廃止（タブ不要・2026-10-18）。
  const DOC_GONE = ['home', 'mine', 'findings'];
  const STEPS = ['pair', 'plan', 'read', 'triage', 'questions', 'followup', 'gate', 'screen'];
  const COUNT = { mine: 'mine', findings: 'open red', read: 'candidates', triage: 'adopted' };
  // 検証観点の精度は観点の行に表示する予定のため、上部のタブには出さない（2026-10-18 保守者指示）
  const NO_TAB = ['accuracy'];
  const sectionOf = (view) => Object.keys(SECTIONS).find((k) => SECTIONS[k].includes(view)) || 'doc';
  const tab = (v, cur) => {
    const c = COUNT[v] ? `<span class="dv-n${COUNT[v].includes('red') ? ' red' : ''}" data-count="${COUNT[v].split(' ')[0]}"></span>` : '';
    return `<a href="#${v}" data-nav="${v}" class="${v === cur ? 'active' : ''}">${esc(TITLES[v])}${c}</a>`;
  };

  function renderSubtabs(view) {
    const nav = $('#dv-subtabs');
    if (!nav) return;
    const r = DV.state.review;
    let html = '';
    if (sectionOf(view) === 'hist') {
      // 根拠は「履歴」画面の中のタブ（ナビには出さない）
      html = [['metrics', '履歴'], ['screen', '根拠']].map(([v, l]) => `<a href="#${v}" data-nav="${v}" class="${v === view ? 'active' : ''}"${v === view ? ' aria-current="page"' : ''}>${l}</a>`).join('');
    } else if (STEPS.includes(view) && r) {
      html = `<a href="#reviews" data-nav="reviews" class="dv-back">← レビュー一覧</a><span class="dv-subtabs-name">${esc(r.name)}</span>`
        + STEPS.map((v) => tab(v, view)).join('');
    } else if (sectionOf(view) === 'doc') {
      html = '';
    } else {
      const list = SECTIONS[sectionOf(view)].filter((v) => !NO_TAB.includes(v));
      html = list.length > 1 ? list.map((v) => tab(v, view)).join('') : '';
    }
    nav.innerHTML = html;
    nav.hidden = !html;
    setCounts();
  }

  // 画面の頭（何の画面か 1 文・現在の状態・状態の理由 1 行）。語は c-hybrid の WS2D 語彙に合わせる
  const PAGE = {
    reviews: ['レビュー', 'レビューを作り、文書の検査から判定までを進めます。', 'AI の自動検出は「候補」です。人が「指摘にする」を押すまで、確定した指摘にはなりません。'],
    pair: ['対検査', '要件定義書と基本設計書を突き合わせ、指摘の採否と判定・承認を記録します。', '指摘を選ぶと両文書の該当箇所が光ります。全体が合格のときだけ承認できます。'],
    plan: ['計画', 'レビューの目的・参加者・期限・終了基準を決めます。', '計画を保存して「個別レビューを始める」を押すと、文書を読む工程に進みます。'],
    read: ['文書を読む', '本文を読み、指摘の候補を確かめて指摘にします。', '自動で見つけたものは候補です。本文に戻って確かめてから指摘にしてください。'],
    triage: ['指摘', '見つかった指摘を採用・却下・保留に仕分けます。', '指摘ごとの「根拠」で、文書にある内容か、推論か、未確認かを確かめられます。'],
    questions: ['質問票', '作成者に確かめたい事項をまとめます。', '回答が届くまで、その指摘は「未確認」のままです。'],
    followup: ['修正版の確認', '修正された文書で、指摘が直ったかを確かめます。', '直ったと確かめられた指摘だけを「修正済み」にします。'],
    screen: ['根拠', '実画面と文書を照らし合わせ、一致・不一致・未確認を見ます。', '照合できていない項目は「未確認」です。一致とは読まないでください。'],
    gate: ['判定と記録', 'レビューの合否を決め、記録を残します。', '判定と承認は人が行います。AI は承認しません。'],
    trace: ['トレーサビリティ', '要件・設計・テストの文書どうしのつながりを確かめます。', 'つながりは文書の記述から読み取った推論です。内容が正しいかは人が確かめてください。'],
    assure: ['ドキュメント品質保証', '文書が次の工程へ進める状態かを判定し、直すべき点と決めることを示します。', '点数は評価できた範囲だけで出します。評価できなかった範囲を 0 点や 100 点にはしません。'],
    metrics: ['履歴', '過去の判定と記録、指摘の件数と修正の進み具合を見ます。', '数値は、画面に表示された時点の記録です。'],
    checklists: ['観点', '文書の検査で何を見るか、見つけた指摘をどれだけ重く扱うかを決めます。', '観点は区分ごとに、見る内容と重さを決められます。'],
    settings: ['設定', '出口基準・言葉・役割・AI の送信先を決めます。保存すると次の判定から反映されます。', 'AI に文書を送る前には、必ず送る内容の確認が出ます。'],
    accuracy: ['精度', '自動検出の規則ごとの適合率・再現率を、評価セットでの測定値で示します。', '測定値は評価セットでの結果です。あなたの文書での正しさを保証するものではありません。'],
  };
  const PHASE_STATUS = { plan: ['preparing', '計画'], individual: ['running', '個別レビュー'], triage: ['waiting_review', '指摘の検討'], rework: ['running', '修正'], followup: ['waiting_review', '修正版の確認'], closed: ['done', '判定と記録'] };
  function renderPageHead(view) {
    const info = PAGE[view];
    const ws = window.WS2D;
    if (!info) return;
    const own = view === 'assure';  // System06 は自前のヘッダ 1 段だけを出す
    ['#dv-pagehead', '#page-reason'].forEach((q) => { const n = $(q); if (n) n.hidden = own; });
    if (own) return;
    const t = $('#dv-ph-title'), d = $('#dv-ph-desc'), st = $('#dv-ph-state'), rs = $('#page-reason');
    if (t) t.textContent = info[0];
    if (d) d.textContent = info[1];
    const r = DV.state.review;
    if (st) {
      st.innerHTML = '';
      if (r && REVIEW_VIEWS.includes(view)) {
        const ps = PHASE_STATUS[r.phase] || ['not_started', ''];
        st.innerHTML = (ws && ws.status ? ws.status.html(ps[0]) : '') + `<span>${esc(r.name)} ・ ${esc(ps[1])}</span>`;
      }
    }
    if (rs) { if (ws && ws.reason) ws.reason(rs, info[2]); else rs.textContent = info[2]; }
  }

  function renderReviewNav() {
    renderSubtabs(DV.current || 'reviews');
    renderPageHead(DV.current || 'reviews');
  }

  function show(view) {
    view = String(view || '').split('/')[0];   // #assure/<iid>/<tab> の深いリンクは先頭だけで画面を決める
    if (!TITLES[view] || DOC_GONE.includes(view)) view = 'reviews';
    const needReview = REVIEW_VIEWS.includes(view) && !DV.state.review;
    if (needReview) view = 'reviews';
    document.querySelectorAll('.dv-view').forEach((v) => { v.hidden = v.dataset.view !== view; });
    const sec = needReview && location.hash.slice(1) === 'setcheck' ? 'trace' : sectionOf(view);
    document.querySelectorAll('.dv-sec').forEach((a) => a.classList.toggle('active', a.dataset.sec === sec));
    const title = $('#topbar-title');
    if (title) { title.textContent = TITLES[view]; title.hidden = view === 'assure'; }
    const crumb = $('#topbar-breadcrumb');
    if (crumb) {
      const r = DV.state.review;
      crumb.innerHTML = `<span>WebSpec2Doc</span><span class="sep">/</span><span>ドキュメント検証</span>`
        + (r && REVIEW_VIEWS.includes(view) ? `<span class="sep">/</span><span>${esc(r.name)}</span>` : '');
    }
    DV.current = view;
    if (location.hash.slice(1).split('/')[0] !== view) history.replaceState(null, '', `#${view}`);
    banner(needReview ? 'この画面はレビューを開いてから使えます。一覧からレビューを選んでください。' : '');
    renderSubtabs(view);
    renderPageHead(view);
    (handlers[view] || []).forEach((fn) => { try { fn(); } catch (e) { console.error(e); banner('画面を表示できませんでした。再読み込みしてください。'); } });
    if (view === 'accuracy' && window.DVAccuracy) window.DVAccuracy.load();
  }

  async function openReview(iid, view = 'read') {
    if (view === 'read' && location.hash.slice(1).split('/')[0] !== 'read') view = 'pair';   // 一覧から開くと対検査を最初に出す（S06）
    const data = await api(`/api/docverify/inspections/${encodeURIComponent(iid)}`);
    DV.state.review = data.inspection;
    DV.state.summary = data.summary; DV.state.can = data.can || null;
    try { sessionStorage.setItem('dv-review', iid); } catch (e) { /* 保存できない環境では復元しないだけ */ }
    renderReviewNav();
    show(view);
  }

  function setReview(data) {
    DV.state.review = data.inspection;
    DV.state.summary = data.summary; DV.state.can = data.can || null;
    renderReviewNav();
  }

  async function start() {
    document.addEventListener('click', (e) => {
      const a = e.target.closest('[data-nav], [data-go]');
      if (!a) return;
      e.preventDefault();
      const v = a.dataset.nav || a.dataset.go;
      if (location.hash.slice(1) !== v) history.pushState(null, '', `#${v}`);   // 戻る・進むで辿れるように履歴へ積む
      show(v);
    });
    const sync = () => {
      const d = location.hash.slice(1).split('/'), h = d[0];
      if (h === 'assure' && d[1] && (!DV.state.review || DV.state.review.id !== decodeURIComponent(d[1]))) { openReview(decodeURIComponent(d[1]), 'assure').catch(() => show('reviews')); return; }
      if (h && h !== DV.current) show(h);
    };
    window.addEventListener('hashchange', sync);
    window.addEventListener('popstate', sync);
    let saved = null;
    try { saved = sessionStorage.getItem('dv-review'); } catch (e) { saved = null; }
    const deep = location.hash.slice(1).split('/');
    if (deep[0] === 'assure' && deep[1]) saved = decodeURIComponent(deep[1]);   // #assure/<iid> からレビューを復元する
    if (saved) { try { await openReview(saved, deep[0] || 'read'); return; } catch (e) { banner(''); } }
    show(location.hash.slice(1) || 'reviews');
  }

  const NO_SCORE = '— 文書を取り込むと表示されます。';

  // 実行中はボタンを無効にし、終わるまでの 2 回目の押下は同じ Promise を返す
  function busy(btn, p, label) {
    const run = () => Promise.resolve().then(() => (typeof p === 'function' ? p() : p));
    if (!btn) return run();
    if (btn.dataset.busy === '1' && btn._dvBusy) return btn._dvBusy;
    const orig = btn.textContent;
    btn.dataset.busy = '1';
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    if (label) btn.textContent = label;
    const done = run().finally(() => {
      btn.textContent = orig;
      btn.disabled = false;
      btn.removeAttribute('aria-busy');
      delete btn.dataset.busy;
      btn._dvBusy = null;
    });
    btn._dvBusy = done;
    return done;
  }

  const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
  function trapTab(dlg, e) {
    if (e.key !== 'Tab') return;
    const f = Array.from(dlg.querySelectorAll(FOCUSABLE)).filter((el) => !el.hidden && !el.disabled && el.offsetParent !== null);
    e.preventDefault();
    if (!f.length) return;
    const i = f.indexOf(document.activeElement);
    const next = e.shiftKey ? (i <= 0 ? f.length - 1 : i - 1) : (i < 0 || i >= f.length - 1 ? 0 : i + 1);
    f[next].focus();
  }

  let modalOpen = null;
  function modal(opt) {
    const dlg = $('#dv-modal');
    if (!dlg || typeof dlg.showModal !== 'function') return Promise.resolve(false);
    if (modalOpen) return modalOpen;
    const o = opt || {};
    const okBtn = dlg.querySelector('[data-modal="ok"]');
    const cancelBtn = dlg.querySelector('[data-modal="cancel"]');
    $('#dv-modal-title').textContent = o.title || '';
    $('#dv-modal-body').innerHTML = o.html || '';  // 呼び出し側が esc() 済みの HTML を渡す
    okBtn.hidden = o.ok == null;
    okBtn.textContent = o.ok == null ? '' : o.ok;
    cancelBtn.textContent = o.cancel || '閉じる';
    const opener = document.activeElement;
    modalOpen = new Promise((resolve) => {
      const onKey = (e) => trapTab(dlg, e);
      const onCancel = (e) => { e.preventDefault(); finish(false); };
      function finish(v) {
        dlg.removeEventListener('keydown', onKey);
        dlg.removeEventListener('cancel', onCancel);
        okBtn.onclick = null; cancelBtn.onclick = null;
        if (dlg.open) dlg.close();
        modalOpen = null;
        if (opener && typeof opener.focus === 'function' && document.contains(opener)) opener.focus();
        resolve(v);
      }
      dlg.addEventListener('keydown', onKey);
      dlg.addEventListener('cancel', onCancel);
      okBtn.onclick = () => finish(true);
      cancelBtn.onclick = () => finish(false);
      dlg.showModal();
      (o.ok == null ? cancelBtn : okBtn).focus();
    });
    return modalOpen;
  }

  async function download(path, filename) {
    const res = await api(path, { raw: true });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || '';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    banner('');
  }

  const emptyFindings = (n) => `確認した範囲では指摘はありません。${Number(n) || 0} 断片を確認しました。網羅性は未検証です。`;
  const scoreText = (v) => (v === null || v === undefined || Number.isNaN(+v) ? '—' : String(Math.round(+v)));
  function scoreClass(v) {
    if (v === null || v === undefined || Number.isNaN(+v)) return 'is-none';
    if (+v < 60) return 'is-bad';
    if (+v < 80) return 'is-warn';
    return '';
  }
  function scoreBar(v, label) {
    const none = v === null || v === undefined || Number.isNaN(+v);
    const w = none ? 0 : Math.max(0, Math.min(100, Math.round(+v)));
    return `<span class="dv-score-bar" role="img" aria-label="${esc(label)} ${esc(scoreText(v))}"><i class="${scoreClass(v)}" style="width:${w}%"></i></span>`;
  }

  // [data-key-open] を Tab で選べるようにし、Enter / Space で開く
  function keyOpen(root) {
    if (!root) return;
    root.querySelectorAll('[data-key-open]').forEach((el) => {
      if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0');
      if (el.dataset.keyBound === '1') return;
      el.dataset.keyBound = '1';
      el.addEventListener('keydown', (e) => {
        if (e.target !== el || (e.key !== 'Enter' && e.key !== ' ')) return;
        e.preventDefault();
        el.click();
      });
    });
  }

  window.DV = {
    api, esc, show, toast, openReview, setReview, start, banner,
    busy, modal, download, emptyFindings, scoreText, scoreClass, scoreBar, keyOpen, NO_SCORE,
    state: { review: null, summary: null },
    on(view, fn) { (handlers[view] = handlers[view] || []).push(fn); },
    refreshNav: renderReviewNav,
    PHASES: [['plan', '計画'], ['individual', '個別レビュー'], ['triage', '指摘の検討'], ['rework', '修正'], ['followup', '修正版の確認'], ['closed', '判定と記録']],
  };
})();
