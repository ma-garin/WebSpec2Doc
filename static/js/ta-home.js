// ---- テスト活動支援 / ホーム ----
// 型E（俯瞰する）。産出物は持たない。「どこで止まっているか」を見せて離脱させる画面。
// データ源: /api/history（ドメイン一覧）, /api/ta/process, /api/ta/defects,
//           /api/ta/completion, /api/ta/manual-runs（すべて domain 必須）。
// 色・ロックの塗り分けは ta-process-gate.js（window.taProcessGate）と揃える。
// このファイルは工程マスの「実数テキスト」と、ブロッカー帯・詰まり行だけを担当する。
(function () {
  'use strict';

  const esc = (v) => String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const $ = (id) => document.getElementById(id);

  // ta-process-gate.js と同じキー。ここで選んだドメインを他画面のゲートにも渡す。
  const DOMAIN_KEY = 'webspec2doc.ta.domain';

  const PHASE_LABELS = {
    'test-plan': 'テスト計画',
    'test-analysis': 'テスト基本設計',
    'test-strategy': 'テスト詳細設計',
    'test-design': 'テストケース実装',
    'test-implementation': '自動テストケース実装',
    'test-execution': '自動テスト実行',
    'manual-execution': '手動テスト実行',
    'defect-analysis': '不具合分析',
    'code-fix': 'コード修正提案',
    'test-completion': 'テスト完了',
  };

  function go(view) {
    if (typeof switchView === 'function') switchView(view);
  }

  function currentDomain() {
    const sel = $('ta-project-select');
    if (sel && sel.value) return sel.value;
    try { return sessionStorage.getItem(DOMAIN_KEY) || ''; } catch (_) { return ''; }
  }

  function rememberDomain(value) {
    try { sessionStorage.setItem(DOMAIN_KEY, value); } catch (_) { /* 非対応環境 */ }
  }

  function setHint(html) {
    const el = $('ta-hero-hint');
    if (el) el.innerHTML = html;
  }

  function errBadge(message) {
    return `<span class="ta2-badge ta2-badge-ng">エラー</span> ${esc(message)}`;
  }

  // ---- プロジェクト一覧 ----
  async function loadDomains() {
    const sel = $('ta-project-select');
    if (!sel) return;
    try {
      const res = await fetch('/api/history');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'サイト一覧を取得できませんでした');
      const items = (data.items || []).filter((it) => it.domain);
      const remembered = currentDomain();
      sel.innerHTML = '<option value="">プロジェクトを選択</option>'
        + items.map((it) => `<option value="${esc(it.domain)}">${esc(it.domain)}（${Number(it.screens) || 0} 画面）</option>`).join('');
      if (items.length && remembered && items.some((it) => it.domain === remembered)) {
        sel.value = remembered;
      }
      if (!items.length) {
        setHint('まだ解析済みのプロジェクトがありません。ドキュメント作成でサイトを解析すると、ここから選べます。');
      }
      if (sel.value) refreshAll();
    } catch (e) {
      setHint(errBadge('プロジェクト一覧の取得に失敗しました（' + (e && e.message ? e.message : e) + '）'));
    }
  }

  // ---- 工程マス ----
  function resetPipelineText() {
    document.querySelectorAll('#ta-pipeline .ta-step-state').forEach((el) => { el.textContent = '未着手'; });
  }

  function applyProcess(data) {
    const byPhase = {};
    (data.phases || []).forEach((p) => { byPhase[p.phase] = p; });
    document.querySelectorAll('#ta-pipeline .ta-step-state').forEach((el) => {
      const p = byPhase[el.dataset.phase];
      if (!p) return;
      el.textContent = p.completed ? '完了' : (p.current ? '現在地' : '未着手');
    });
    return byPhase;
  }

  function appendPhaseText(phase, extra) {
    const el = document.querySelector(`#ta-pipeline .ta-step-state[data-phase="${phase}"]`);
    if (el && extra) el.textContent += `（${extra}）`;
  }

  // ---- ブロッカー帯 ----
  function applyDefects(data) {
    const band = $('ta-blocker-band');
    const text = $('ta-blocker-text');
    const stats = data.stats || {};
    const criticalOpen = Number(stats.critical_open || 0);
    if (band && text) {
      if (criticalOpen > 0) {
        text.textContent = `未対応の重大不具合が ${criticalOpen} 件あります。完了判定をブロックしています。`;
        band.hidden = false;
      } else {
        band.hidden = true;
      }
    }
    if (Number(stats.total || 0) > 0) {
      appendPhaseText('defect-analysis', `重大${criticalOpen}件・計${stats.total}件`);
    }
  }

  // ---- 完了基準 ----
  function applyCompletion(data) {
    const criteria = data.criteria || [];
    if (!criteria.length) return;
    const met = criteria.filter((c) => c.met).length;
    appendPhaseText('test-completion', `${met}/${criteria.length} 達成`);
    return criteria;
  }

  // ---- 手動実行 ----
  function applyManualRuns(data) {
    const stats = data.stats || {};
    if (Number(stats.total || 0) > 0) {
      appendPhaseText('manual-execution', `${stats.done || 0}/${stats.total} 実施`);
    }
  }

  // ---- 詰まり行 ----
  function renderStuckLine(byPhase, currentPhase, criteria) {
    const el = $('ta-stuck-line');
    if (!el) return;
    const label = PHASE_LABELS[currentPhase] || currentPhase;
    const unmet = (criteria || []).filter((c) => !c.met);
    let extra = '';
    if (currentPhase === 'test-completion' && unmet.length) {
      extra = `未達: ${unmet.map((c) => c.label).join('・')}`;
    }
    el.innerHTML = `いま止まっているのは「${esc(label)}」です。${extra ? esc(extra) + ' ' : ''}`
      + `<button type="button" class="ta-linkbtn" id="ta-stuck-open">続きを開く →</button>`;
    const btn = $('ta-stuck-open');
    if (btn) btn.addEventListener('click', () => go(currentPhase));
    const startBtn = $('ta-start-btn');
    if (startBtn) startBtn.textContent = `「${label}」を続ける`;
  }

  async function fetchJson(url) {
    const res = await fetch(url);
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || ('HTTP ' + res.status));
    return data;
  }

  async function refreshAll() {
    const domain = currentDomain();
    if (!domain) {
      resetPipelineText();
      $('ta-blocker-band') && ($('ta-blocker-band').hidden = true);
      setHint('プロジェクトを選ぶと、工程ごとの進捗と成果物がここに集約されます。');
      const el = $('ta-stuck-line');
      if (el) el.textContent = 'プロジェクトを選ぶと、いま止まっている工程がここに出ます。';
      const startBtn = $('ta-start-btn');
      if (startBtn) startBtn.textContent = 'テスト活動を始める';
      return;
    }
    rememberDomain(domain);
    setHint(`「${esc(domain)}」を読み込んでいます…`);

    const [processR, defectsR, completionR, manualR] = await Promise.allSettled([
      fetchJson('/api/ta/process?domain=' + encodeURIComponent(domain)),
      fetchJson('/api/ta/defects?domain=' + encodeURIComponent(domain)),
      fetchJson('/api/ta/completion?domain=' + encodeURIComponent(domain)),
      fetchJson('/api/ta/manual-runs?domain=' + encodeURIComponent(domain)),
    ]);

    let byPhase = {};
    let currentPhase = '';
    let criteria = [];

    if (processR.status === 'fulfilled') {
      byPhase = applyProcess(processR.value);
      currentPhase = processR.value.current_phase || '';
    } else {
      setHint(errBadge('工程状態の取得に失敗しました（' + processR.reason.message + '）'));
    }

    if (defectsR.status === 'fulfilled') {
      applyDefects(defectsR.value);
    } else {
      const band = $('ta-blocker-band');
      const text = $('ta-blocker-text');
      if (band && text) { text.innerHTML = errBadge('不具合状況の取得に失敗しました（' + defectsR.reason.message + '）'); band.hidden = false; }
    }

    if (completionR.status === 'fulfilled') {
      criteria = applyCompletion(completionR.value) || [];
    }

    if (manualR.status === 'fulfilled') {
      applyManualRuns(manualR.value);
    }

    if (currentPhase) {
      renderStuckLine(byPhase, currentPhase, criteria);
      if (processR.status === 'fulfilled') {
        setHint(`「${esc(domain)}」を選択中。いま止まっているのは「${esc(PHASE_LABELS[currentPhase] || currentPhase)}」です。`);
      }
    } else if (processR.status === 'fulfilled') {
      const el = $('ta-stuck-line');
      if (el) el.textContent = 'すべての工程が完了しています。';
    }

    // 色・ロック（is-current / is-done / is-locked）はゲート側の実装と揃える。
    if (window.taProcessGate && typeof window.taProcessGate.reload === 'function') {
      window.taProcessGate.reload();
    }
  }

  let _booted = false;
  function init() {
    if (_booted) return;
    _booted = true;

    const sel = $('ta-project-select');
    if (sel) sel.addEventListener('change', refreshAll);

    const startBtn = $('ta-start-btn');
    if (startBtn) {
      startBtn.addEventListener('click', () => {
        const domain = currentDomain();
        if (!domain) {
          setHint(errBadge('先にプロジェクトを選択してください'));
          if (sel) sel.focus();
          return;
        }
        go('test-plan');
      });
    }

    const reloadBtn = $('ta-pipeline-reload');
    if (reloadBtn) reloadBtn.addEventListener('click', refreshAll);

    const blockerOpen = $('ta-blocker-open');
    if (blockerOpen) blockerOpen.addEventListener('click', () => go('defect-analysis'));

    // 工程マス自体のクリック遷移は ta-process-nav.js が配線済み（重複配線しない）。

    if (typeof onViewEnter === 'function') {
      onViewEnter('test-activity', refreshAll);
    }

    loadDomains();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
