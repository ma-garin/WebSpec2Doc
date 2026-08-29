// ---- テスト活動支援 / 工程ゲート ----
// 工程は順番にしか進めない。未到達の工程はナビで無効化し、遷移も止める。
//
// 止め方は 2 段構え:
//   1. ナビ項目を disabled にして押せなくする（見えているが押せない）
//   2. switchView を包んで、URL 直打ち・戻る操作・他画面のリンクからの侵入も止める
// 1 だけだと素通りできる。2 だけだと押せてしまい「押したのに動かない」になる。
(function () {
  'use strict';

  let _status = null;      // サーバから取った工程状態。これが唯一の正
  let _domain = '';
  let _origSwitchView = null;

  const labelOf = (phase) => {
    const p = (_status && _status.phases || []).find((x) => x.phase === phase);
    return p ? p.label : phase;
  };

  const DOMAIN_SELECTS = ['ta-design-domain', 'ta-exec-suite', 'ta-analysis-doc-select'];
  const DOMAIN_KEY = 'webspec2doc.ta.domain';

  function rememberDomain(value) {
    try { sessionStorage.setItem(DOMAIN_KEY, value); } catch (e) { /* 非対応環境 */ }
  }

  function currentDomain() {
    for (const id of DOMAIN_SELECTS) {
      const el = document.getElementById(id);
      if (el && el.value) { rememberDomain(el.value); return el.value; }
    }
    try { return sessionStorage.getItem(DOMAIN_KEY) || ''; } catch (e) { return ''; }
  }

  function phaseOf(view) {
    if (!_status) return null;
    return (_status.phases || []).find((p) => p.phase === view) || null;
  }

  // ---- ナビの無効化 ----
  function applyToNav() {
    if (!_status) return;
    (_status.phases || []).forEach((p) => {
      const btn = document.querySelector(`.app-nav-item[data-view="${p.phase}"]`);
      if (!btn) return;
      btn.disabled = !p.unlocked;
      btn.classList.toggle('is-locked', !p.unlocked);
      if (p.unlocked) {
        btn.removeAttribute('aria-disabled');
        btn.title = p.completed ? `${p.label}（完了）` : p.label;
      } else {
        // 押せない理由をその場で言う。押せないことだけ示して理由が無いと、
        // 利用者は「壊れている」と受け取る。
        btn.setAttribute('aria-disabled', 'true');
        const prev = (_status.phases || [])[p.order - 2];
        btn.title = prev ? `${prev.label} を完了すると開けます` : '前の工程を完了すると開けます';
      }
    });
    markStepper();
  }

  // ホームの工程ストリップにも同じ状態を反映する。
  // ナビとストリップで解放状況が食い違うと、どちらが正か分からなくなる。
  function markStepper() {
    document.querySelectorAll('#ta-pipeline .ta-pipeline-step[data-view]').forEach((el) => {
      const p = phaseOf(el.dataset.view);
      if (!p) return;
      el.classList.toggle('is-done', p.completed);
      el.classList.toggle('is-current', p.current);
      el.classList.toggle('is-locked', !p.unlocked);
      el.disabled = !p.unlocked;
    });
  }

  // ---- 遷移ガード ----
  function guardSwitchView() {
    if (_origSwitchView || typeof window.switchView !== 'function') return;
    _origSwitchView = window.switchView;
    window.switchView = function (name, opts) {
      const p = phaseOf(name);
      if (p && !p.unlocked) {
        const prev = (_status.phases || [])[p.order - 2];
        notify(`${p.label} はまだ開けません。${prev ? prev.label : '前の工程'} を完了してください。`);
        // 開ける最後の工程へ送る。何も起きずに黙って止まると原因が分からない。
        return _origSwitchView(_status.current_phase, opts);
      }
      return _origSwitchView(name, opts);
    };
  }

  function notify(message) {
    let el = document.getElementById('ta-gate-toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'ta-gate-toast';
      el.className = 'ta-gate-toast';
      el.setAttribute('role', 'status');
      document.body.appendChild(el);
    }
    el.textContent = message;
    el.classList.add('is-on');
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove('is-on'), 3600);
  }

  // ---- 各工程画面の「この工程を完了する」ボタン ----
  function injectCompleteButtons() {
    if (!_status) return;
    (_status.phases || []).forEach((p) => {
      const section = document.getElementById('view-' + p.phase);
      if (!section) return;
      const nav = section.querySelector('.ta2-stepnav');
      if (!nav) return;
      let btn = nav.querySelector('[data-gate-complete]');
      if (!btn) {
        btn = document.createElement('button');
        btn.type = 'button';
        btn.setAttribute('data-gate-complete', p.phase);
        nav.insertBefore(btn, nav.querySelector('[data-sn-next]') || null);
        btn.addEventListener('click', () => togglePhase(p.phase));
      }
      btn.className = p.completed ? 'btn-outline-sm' : 'btn-primary';
      btn.textContent = p.completed ? '✓ 完了済み（やり直す）' : 'この工程を完了する';
      // 次へ進むボタンは、完了するまで押せない
      const next = nav.querySelector('[data-sn-next]');
      if (next) {
        next.disabled = !p.completed;
        next.title = p.completed ? '' : 'この工程を完了すると進めます';
      }
    });
  }

  async function togglePhase(phase) {
    const p = phaseOf(phase);
    if (!p) return;
    const url = p.completed ? '/api/ta/process/reopen' : '/api/ta/process/complete';
    if (p.completed
        && !confirm(`${p.label} の完了を取り消します。これ以降の工程の完了も外れます。よろしいですか？`)) {
      return;
    }
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: _domain, phase }),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || '更新に失敗しました');
      _status = data;
      applyToNav();
      injectCompleteButtons();
      notify(p.completed ? `${p.label} の完了を取り消しました` : `${p.label} を完了しました`);
    } catch (e) {
      notify(String(e && e.message ? e.message : e));
    }
  }

  async function load() {
    _domain = currentDomain();
    if (!_domain) {
      // 対象が決まるまでは止めない。何も選んでいない状態で全部灰色だと
      // 「壊れている」ようにしか見えないため。
      _status = null;
      document.querySelectorAll('.app-nav-item.is-locked').forEach((b) => {
        b.disabled = false;
        b.classList.remove('is-locked');
        b.removeAttribute('aria-disabled');
      });
      return;
    }
    try {
      const res = await fetch('/api/ta/process?domain=' + encodeURIComponent(_domain));
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || '工程状態を取得できませんでした');
      _status = data;
      applyToNav();
      injectCompleteButtons();
      guardSwitchView();
    } catch (e) {
      // 取得に失敗したときは止めない。ゲートの故障で全機能が使えなくなる方が損害が大きい
      _status = null;
    }
  }

  function init() {
    load();
    // 対象ドメインが変わると進捗も変わる
    DOMAIN_SELECTS.forEach((id) => {
      document.getElementById(id)?.addEventListener('change', load);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window.taProcessGate = { reload: load };
})();
