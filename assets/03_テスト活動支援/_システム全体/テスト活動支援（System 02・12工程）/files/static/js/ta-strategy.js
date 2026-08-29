// ---- テスト活動支援 / テスト詳細設計ビュー ----
// データ源: /api/history（ドメイン一覧）, /api/ta/datasets（保存済みテストデータの実数）,
//           /api/settings/test-design（有効な技法）。
// デシジョンテーブル本体・展開結果はこのアプリにまだ永続化先が無いため、
// 生成系ボタン（AIでテスト条件を生成／条件を追加／技法で展開）は disabled + 準備中表示にしてある。
(function () {
  'use strict';

  const esc = (v) => String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const $ = (id) => document.getElementById(id);

  const TECHNIQUE_LABELS = { bva: '境界値分析', dt: 'デシジョンテーブル', pw: 'ペアワイズ', st: '状態遷移' };

  // 値の状態色: 0 件は「未着手」の警告色、1 件以上は進捗中の主要数値色。
  function setStat(id, value, hasValue) {
    const el = $(id);
    if (!el) return;
    el.textContent = value;
    el.classList.remove('is-wa', 'is-pri');
    el.classList.add(hasValue ? 'is-pri' : 'is-wa');
  }

  async function loadStats(domain) {
    if (!domain) {
      setStat('ta-detail-stat-count', '–', false);
      setStat('ta-detail-stat-rows', '–', false);
      setStat('ta-detail-stat-avg', '–', false);
      return;
    }
    try {
      const res = await fetch('/api/ta/datasets?domain=' + encodeURIComponent(domain));
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      const items = Array.isArray(data.items) ? data.items : [];
      const count = items.length;
      const rows = items.reduce((sum, it) => sum + (Number(it.row_count) || 0), 0);
      const avg = count ? (rows / count).toFixed(1) : '0.0';
      setStat('ta-detail-stat-count', String(count), count > 0);
      setStat('ta-detail-stat-rows', String(rows), rows > 0);
      setStat('ta-detail-stat-avg', avg, rows > 0);
    } catch (e) {
      setStat('ta-detail-stat-count', '取得失敗', false);
      setStat('ta-detail-stat-rows', '–', false);
      setStat('ta-detail-stat-avg', '–', false);
    }
  }

  async function loadTechniques() {
    const host = $('ta-detail-techniques');
    if (!host) return;
    try {
      const res = await fetch('/api/settings/test-design');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      const enabled = Array.isArray(data.enabled_techniques) ? data.enabled_techniques : [];
      host.innerHTML = Object.keys(TECHNIQUE_LABELS).map((key) => {
        const on = enabled.includes(key);
        return `<span class="ta-chip${on ? ' is-on' : ''}" aria-pressed="${on}">${esc(TECHNIQUE_LABELS[key])}</span>`;
      }).join('');
    } catch (e) {
      host.innerHTML = '<div class="empty">技法設定を取得できませんでした（設定 &gt; テスト設計 を確認してください）</div>';
    }
  }

  async function loadDomains() {
    const sel = $('ta-detail-domain');
    if (!sel) return;
    try {
      const res = await fetch('/api/history');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      const items = (data.items || []).filter((it) => it.domain);
      const current = sel.value;
      sel.innerHTML = items.map((it) => `<option value="${esc(it.domain)}">${esc(it.domain)}</option>`).join('');
      if (items.length) {
        sel.value = items.some((it) => it.domain === current) ? current : items[0].domain;
        loadStats(sel.value);
      } else {
        sel.innerHTML = '<option value="">ドメインがありません</option>';
        loadStats('');
      }
    } catch (e) {
      sel.innerHTML = '<option value="">取得失敗</option>';
      loadStats('');
    }
  }

  let _booted = false;
  function init() {
    if (_booted) return;
    _booted = true;
    const sel = $('ta-detail-domain');
    if (sel) sel.addEventListener('change', () => loadStats(sel.value));
    loadDomains();
    loadTechniques();
  }

  // 画面へ入るたびに実数を取り直す（テストデータは別画面での追加・削除で変わり得るため）。
  function onEnter() {
    if (!_booted) { init(); return; }
    const sel = $('ta-detail-domain');
    if (sel && sel.value) loadStats(sel.value);
  }

  // core.js の VIEW_INIT へ登録する（core.js は編集しない）。
  if (typeof onViewEnter === 'function') {
    onViewEnter('test-strategy', onEnter);
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }
})();
