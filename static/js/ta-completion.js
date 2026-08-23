// ---- テスト活動支援 / テスト完了 ----
// テスト計画で定めた終了基準に、実測値を突き合わせて判定する。
// 判定は表示するだけで、完了そのものは人が承認する（自動でクローズしない）。
(function () {
  'use strict';

  let _loaded = false;

  const esc = (v) => (typeof escHtml === 'function'
    ? escHtml(String(v))
    : String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])));

  function domain() {
    const sel = document.getElementById('ta-design-domain') || document.getElementById('ta-exec-suite');
    return sel && sel.value ? sel.value : '';
  }

  function renderCriteria(criteria) {
    const box = document.getElementById('ta-completion-criteria-body');
    if (!box) return;
    if (!criteria || !criteria.length) {
      box.innerHTML = '<div class="empty">終了基準がまだありません（テスト計画で設定します）</div>';
      return;
    }
    box.innerHTML = criteria.map((c) => {
      if (c.met) {
        return `<div class="ta-kv-row is-met">
          <div class="ta-kv-key"><span class="ta2-badge ta2-badge-ok">達成</span></div>
          <div class="ta-kv-val">${esc(c.label)} <span class="muted-copy">${esc(c.current)} ／ 目標 ${esc(c.target)}</span></div>
        </div>`;
      }
      return `<div class="ta-kv-row is-unmet">
        <div class="ta-kv-key"><span class="ta2-badge ta2-badge-ng">未達</span></div>
        <div class="ta-kv-val">
          <div>${esc(c.label)}</div>
          <div>現在 <span class="ta-num is-ng">${esc(c.current)}</span> ／ 目標 <span class="ta-num">${esc(c.target)}</span></div>
        </div>
      </div>`;
    }).join('');
  }

  function renderVerdict(overall) {
    const el = document.getElementById('ta-completion-verdict');
    if (!el) return;
    const met = overall && overall.met;
    el.textContent = '総合判定: ' + (overall && overall.label ? overall.label : '判定待ち');
    el.className = 'ta2-badge ta2-badge-' + (met ? 'ok' : 'ng');
  }

  function renderBlockers(blockers) {
    const box = document.getElementById('ta-completion-blockers');
    if (!box) return;
    if (!blockers || !blockers.length) {
      box.innerHTML = '<div class="empty">完了を妨げている重大な不具合はありません</div>';
      return;
    }
    box.innerHTML = blockers.map((b) => {
      const critical = b.severity === 'critical';
      return `<div class="ta-source-row">
        <span class="ta2-badge ${critical ? 'ta2-badge-ng' : 'ta2-badge-wa'}">${esc(b.severity || b.state || '')}</span>
        <b>${esc(b.id || '')}</b> ${esc(b.summary || '')}
      </div>`;
    }).join('');
  }

  // 未達件数と残ブロッカーから「完了と判定する」の可否を決める。
  // 未達0件かつブロッカー0件のときだけ有効。押せない理由は必ず1行で示す。
  function renderGate(criteria, blockers) {
    const unmet = (criteria || []).filter((c) => !c.met).length;
    const countEl = document.getElementById('ta-completion-unmet-count');
    if (countEl) {
      countEl.textContent = String(unmet);
      countEl.className = 'stat-card-value ' + (unmet > 0 ? 'is-ng' : 'is-ok');
    }
    const critical = (blockers || []).find((b) => b.severity === 'critical');
    let reason = '';
    if (critical) {
      reason = `重大な不具合 ${critical.id || ''} が未解決のため判定できません`;
    } else if (blockers && blockers.length) {
      reason = `未解決の不具合が ${blockers.length} 件あるため判定できません`;
    } else if (unmet > 0) {
      reason = `未達の基準が ${unmet} 件あるため判定できません`;
    }
    const reasonEl = document.getElementById('ta-completion-block-reason');
    if (reasonEl) {
      reasonEl.textContent = reason || '終了基準をすべて満たしています。判定できます。';
      reasonEl.classList.toggle('is-error', Boolean(reason));
    }
    const btn = document.getElementById('ta-completion-approve');
    if (btn) btn.disabled = Boolean(reason);
  }

  function renderGateEmpty(message) {
    const countEl = document.getElementById('ta-completion-unmet-count');
    if (countEl) { countEl.textContent = '–'; countEl.className = 'stat-card-value'; }
    const reasonEl = document.getElementById('ta-completion-block-reason');
    if (reasonEl) { reasonEl.textContent = message; reasonEl.classList.remove('is-error'); }
    const btn = document.getElementById('ta-completion-approve');
    if (btn) btn.disabled = true;
  }

  async function load() {
    const dom = domain();
    const box = document.getElementById('ta-completion-criteria-body');
    if (!dom) {
      if (box) box.innerHTML = '<div class="empty">対象を選ぶと判定基準がここに出ます</div>';
      renderGateEmpty('対象を選択すると判定できます');
      return;
    }
    if (box) box.innerHTML = '<div class="empty">読み込んでいます…</div>';
    try {
      const res = await fetch('/api/ta/completion?domain=' + encodeURIComponent(dom));
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || '判定を取得できませんでした');
      renderCriteria(data.criteria);
      renderVerdict(data.overall);
      renderBlockers(data.blockers);
      renderGate(data.criteria, data.blockers);
      _loaded = true;
    } catch (e) {
      const msg = String(e && e.message ? e.message : e);
      if (box) box.innerHTML = `<div class="empty">${esc(msg)}</div>`;
      renderGateEmpty('判定を取得できなかったため判定できません');
    }
  }

  if (typeof onViewEnter === 'function') {
    onViewEnter('test-completion', () => { if (!_loaded) load(); });
  }
  // 承認の記録はバックエンド未実装。押しても黙って何も起きない状態にしない。
  document.getElementById('ta-completion-approve')?.addEventListener('click', () => {
    const el = document.getElementById('ta-completion-block-reason');
    if (el) {
      el.textContent = '承認の記録機能は未実装です（判定の表示のみ動作します）';
      el.classList.remove('is-error');
    }
  });
})();
