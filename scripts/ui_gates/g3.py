"""G-3 文言の判定。禁止語辞書（quality/ui_banned_words.yml）を画面の表示文字に照合する。"""
import re
from pathlib import Path

import yaml

DICT_PATH = Path(__file__).resolve().parents[2] / "quality" / "ui_banned_words.yml"

# 表示中の文字（innerText）と placeholder / title / aria-label を連結する。
# 例外セレクタの中の文字は除外する（excl は [selector, ...]）。
JS_TEXT = """(excl) => {
  const hide = [];
  for (const sel of excl) for (const e of document.querySelectorAll(sel)) {
    hide.push([e, e.style.display]); e.style.display = 'none';
  }
  let t = document.body.innerText;
  for (const e of document.querySelectorAll('[placeholder],[title],[aria-label]')) {
    if (e.offsetParent === null) continue;
    t += '\\n' + [e.getAttribute('placeholder'), e.getAttribute('title'), e.getAttribute('aria-label')].filter(Boolean).join('\\n');
  }
  for (const [e, d] of hide) e.style.display = d;
  return t;
}"""

JS_MENU = """() => {
  const h1 = (document.querySelector('h1#topbar-title') || {}).textContent;
  const nav = document.querySelector('[aria-current="page"] .nav-label');
  return {h1: h1 ? h1.trim() : null, nav: nav ? nav.textContent.trim() : null, title: document.title};
}"""


def load_dict(path=DICT_PATH):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _compile(word):
    return re.compile(word["pattern"] if word.get("regex") else re.escape(word["pattern"]))


def _excluded(d, url_path):
    """この画面で body 全体が免除される語 ID と、部分除外セレクタを返す。"""
    skip_ids, selectors = set(), []
    for ex in d.get("exceptions", []):
        if not url_path.startswith(ex["path"]):
            continue
        if ex["selector"] == "body":
            skip_ids.update(ex["ids"] if ex["ids"] != "all" else [w["id"] for w in d["words"]])
        else:
            selectors.append(ex["selector"])
    return skip_ids, selectors


def check_text(text, url_path, d=None):
    """文字列を辞書で照合し ["G-3: ...", ...] を返す（例外の selector 除外は呼び出し側で済ませる）。"""
    d = d or load_dict()
    skip_ids, _ = _excluded(d, url_path)
    out = []
    for w in d["words"]:
        if w["id"] in skip_ids:
            continue
        m = _compile(w).search(text)
        if m:
            out.append(f"G-3: 禁止語「{m.group(0)}」→ {w['replace']}（辞書 No.{w['id']}）")
    return out


def check_menu(info):
    """h1 と選択中メニュー名の一致、document.title の接頭辞を判定する。"""
    out = []
    h1, nav, title = info.get("h1"), info.get("nav"), info.get("title") or ""
    if h1 and nav and h1 != nav:
        out.append(f"G-3: 見出し「{h1}」とメニュー「{nav}」が不一致")
    if h1 and not title.startswith(h1 + " - "):
        out.append(f"G-3: ページタイトル「{title}」が「{h1} - 」で始まらない")
    return out


# 解析対象サイト由来の表示（URL など data 由来）。UI の文言ではないので禁止語の判定から除く。
USER_CONTENT_SELECTORS = ["[data-user-content]"]


def run_g3(page, url_path):
    """画面を評価して G-3 の NG 文字列リストを返す。"""
    d = load_dict()
    _, selectors = _excluded(d, url_path)
    text = page.evaluate(JS_TEXT, selectors + USER_CONTENT_SELECTORS)
    return check_text(text, url_path, d) + check_menu(page.evaluate(JS_MENU))
