"""G-6 動的・G-7 自動（仕様 §7.7・§7.8）。"""
from __future__ import annotations

import os
import re

JS_G6 = r"""() => {
  const vis = e => e.offsetParent !== null && !e.closest('[hidden]');
  const sel = el => { let s = el.tagName.toLowerCase(); if (el.id) return s + '#' + el.id;
    if (el.classList.length) s += '.' + [...el.classList].slice(0, 2).join('.'); return s; };
  const out = [];
  document.querySelectorAll('select:not(.c-select)').forEach(e => { if (vis(e)) out.push('c-select 以外の select: ' + sel(e)); });
  document.querySelectorAll('input[type=file]').forEach(e => { const r = e.getBoundingClientRect();
    if (vis(e) && r.width > 1 && r.height > 1) out.push('素の file 入力が見えている: ' + sel(e)); });
  document.querySelectorAll('input[type=search]:not(.c-search)').forEach(e => { if (vis(e)) out.push('c-search 以外の search: ' + sel(e)); });
  document.querySelectorAll('select').forEach(e => { if (vis(e) && getComputedStyle(e).appearance === 'auto')
    out.push('appearance:auto の select: ' + sel(e)); });
  return out;
}"""

JS_G7 = r"""() => {
  const vis = e => e.offsetParent !== null && !e.closest('[hidden]');
  const out = [];
  document.querySelectorAll('[data-denominator="0"]').forEach(e => {
    if (/%/.test(e.innerText || '')) out.push('分母 0 の要素に % 表示: ' + (e.id || e.className || e.tagName));
  });
  const l = [...document.querySelectorAll('[data-kind="loading"]')].filter(vis).length;
  const m = [...document.querySelectorAll('[data-kind="empty"]')].filter(vis).length;
  if (l && m) out.push('loading と empty が同時に表示されている');
  return out;
}"""


def check_dynamic(page) -> list[str]:
    """G-6 動的。"""
    return ["G-6: " + m for m in page.evaluate(JS_G6)]


def check_auto(page) -> list[str]:
    """G-7 自動。"""
    return ["G-7: " + m for m in page.evaluate(JS_G7)]


def snapshot(page, snap_dir: str, path: str, state: str = "normal") -> int:
    """画面 x 状態の最下部までのスクショを保存し、保存枚数（0 or 1）を返す。呼び出し側で合計して
    「G-7 目視対象 n 枚」を出す。"""
    os.makedirs(snap_dir, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9]+", "_", path.strip("/")) or "root"
    page.screenshot(path=os.path.join(snap_dir, f"{name}__{state}.png"), full_page=True)
    return 1


def visual_count_line(n: int) -> str:
    return f"G-7 目視対象 {n} 枚"
