// ==================== テーブル共通ユーティリティ ====================
// ページネーション（イミュータブル：入力配列を破壊しない）とページャ描画。
// 各データビュー（run-history / testcases 等）から再利用する。
const TableUtils = (function () {
  const DEFAULT_SIZE = 20;

  // items をページ分割して現在ページの要素とメタ情報を返す（元配列は不変）。
  function paginate(items, page, size) {
    const list = Array.isArray(items) ? items : [];
    const pageSize = size && size > 0 ? size : DEFAULT_SIZE;
    const total = list.length;
    const pageCount = Math.max(1, Math.ceil(total / pageSize));
    const current = Math.min(Math.max(1, Number(page) || 1), pageCount);
    const start = (current - 1) * pageSize;
    return {
      items: list.slice(start, start + pageSize),
      page: current,
      pageCount,
      total,
      pageSize,
      startIndex: total ? start + 1 : 0,
      endIndex: Math.min(start + pageSize, total),
    };
  }

  // 表示するページ番号の窓（先頭・末尾・現在±1、省略は null）を返す。
  function _window(page, pageCount) {
    if (pageCount <= 7) {
      return Array.from({ length: pageCount }, (_, i) => i + 1);
    }
    const out = [1];
    const from = Math.max(2, page - 1);
    const to = Math.min(pageCount - 1, page + 1);
    if (from > 2) out.push(null);
    for (let p = from; p <= to; p++) out.push(p);
    if (to < pageCount - 1) out.push(null);
    out.push(pageCount);
    return out;
  }

  // ページャの HTML を返す（1 ページ以下なら件数表示のみ）。
  // クリックは呼び出し側が data-page を使って委譲する。
  function pagerHtml(info) {
    const counter = `<span class="pager-info">${info.startIndex}–${info.endIndex} / ${info.total}件</span>`;
    if (info.pageCount <= 1) {
      return `<div class="pager" role="navigation" aria-label="ページ送り">${counter}</div>`;
    }
    const btn = (label, page, opts) => {
      opts = opts || {};
      const kind = opts.nav ? ' pager-nav' : ' pager-num';
      const cls = 'pager-btn' + kind + (opts.active ? ' is-active' : '');
      const dis = opts.disabled ? ' disabled' : '';
      const cur = opts.active ? ' aria-current="page"' : '';
      const aria = opts.label ? ` aria-label="${opts.label}"` : '';
      return `<button type="button" class="${cls}" data-page="${page}"${dis}${cur}${aria}>${label}</button>`;
    };
    const nums = _window(info.page, info.pageCount)
      .map((p) =>
        p === null
          ? '<span class="pager-gap" aria-hidden="true">…</span>'
          : btn(String(p), p, { active: p === info.page })
      )
      .join('');
    return `<div class="pager" role="navigation" aria-label="ページ送り">
      ${counter}
      <div class="pager-controls">
        ${btn('‹', info.page - 1, { disabled: info.page <= 1, nav: true, label: '前のページ' })}
        ${nums}
        ${btn('›', info.page + 1, { disabled: info.page >= info.pageCount, nav: true, label: '次のページ' })}
      </div>
    </div>`;
  }

  // ページャ内クリックからページ番号を取り出すヘルパ（無効・非ボタンは null）。
  function pageFromClick(event) {
    const el = event.target.closest('.pager-btn');
    if (!el || el.disabled) return null;
    const n = Number(el.dataset.page);
    return Number.isFinite(n) ? n : null;
  }

  return { paginate, pagerHtml, pageFromClick, DEFAULT_SIZE };
})();
