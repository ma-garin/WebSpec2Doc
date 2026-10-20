"""アクセシブル名の計算（W3C Accessible Name and Description Computation 1.2 の実用サブセット）。

入力は snapshot の素材のみ（ブラウザ非依存・決定論）。対応: aria-labelledby, aria-label,
ネイティブ代替（alt/value/label/legend/caption/figcaption/svg title）, 内容からの名前,
埋め込みコントロール値, title フォールバック, 疑似要素の文字列。placeholder は名前に数えない。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Collection

from .snapshot import Element, Snapshot

_WS = re.compile(r"\s+")
_INLINE_DISPLAY = ("inline", "inline-block", "inline-flex", "inline-grid", "inline-table", "contents", "ruby")

_NAME_FROM_CONTENT = frozenset({
    "button", "cell", "checkbox", "columnheader", "gridcell", "heading", "link", "menuitem",
    "menuitemcheckbox", "menuitemradio", "option", "radio", "row", "rowheader", "switch", "tab",
    "tooltip", "treeitem",
})
_TAG_NAME_FROM_CONTENT = frozenset({"a", "button", "summary", "h1", "h2", "h3", "h4", "h5", "h6",
                                    "th", "td", "legend", "caption", "figcaption", "label", "option"})

_INPUT_ROLE = {
    "button": "button", "image": "button", "reset": "button", "submit": "button",
    "checkbox": "checkbox", "radio": "radio", "range": "slider", "number": "spinbutton",
    "search": "searchbox", "email": "textbox", "tel": "textbox", "text": "textbox", "url": "textbox",
    "password": "textbox",
}
_TAG_ROLE = {
    "article": "article", "aside": "complementary", "button": "button", "datalist": "listbox",
    "details": "group", "dialog": "dialog", "fieldset": "group", "figure": "figure",
    "form": "form", "hr": "separator", "li": "listitem", "main": "main", "menu": "list",
    "nav": "navigation", "ol": "list", "ul": "list", "option": "option", "output": "status",
    "progress": "progressbar", "meter": "meter", "table": "table", "tbody": "rowgroup",
    "thead": "rowgroup", "tfoot": "rowgroup", "td": "cell", "tr": "row", "textarea": "textbox",
    "dt": "term", "dd": "definition", "p": "paragraph", "section": "region", "svg": "graphics-document",
    "h1": "heading", "h2": "heading", "h3": "heading", "h4": "heading", "h5": "heading", "h6": "heading",
}
_SECTIONING = frozenset({"article", "aside", "main", "nav", "section"})
_NAMED_ROLE_TAGS = frozenset({"section", "form"})  # 名前があるときだけランドマーク


@dataclass(frozen=True)
class AccName:
    name: str
    source: str  # aria-labelledby / aria-label / native / content / title / none


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip()


def implicit_role(snap: Snapshot, e: Element) -> str | None:
    """HTML-AAM に基づく暗黙ロール（文脈依存の一部は簡略化）。"""
    tag = e.tag
    if tag in ("a", "area"):
        return "link" if e.has("href") else None
    if tag == "img":
        return "presentation" if e.attr("alt") == "" else "img"
    if tag == "input":
        t = (e.attr("type") or "text").strip().lower()
        if t in ("text", "email", "tel", "url", "search") and e.has("list"):
            return "combobox"
        return _INPUT_ROLE.get(t)
    if tag == "select":
        return "listbox" if e.has("multiple") or int(e.attr("size") or 1) > 1 else "combobox"
    if tag in ("header", "footer"):
        inside = any(a.tag in _SECTIONING for a in snap.ancestors(e.i))
        if inside:
            return None
        return "banner" if tag == "header" else "contentinfo"
    if tag == "th":
        return "columnheader" if (e.attr("scope") or "").lower() != "row" else "rowheader"
    return _TAG_ROLE.get(tag)


def effective_role(snap: Snapshot, e: Element, valid_roles: Collection[str] | None = None) -> str | None:
    """明示 role（最初の有効トークン）を優先し、無ければ暗黙ロール。

    valid_roles を渡すと、その集合に含まれる最初のトークンを採用する（フォールバック規則）。
    """
    tokens = (e.attr("role") or "").lower().split()
    for tok in tokens:
        if valid_roles is None or tok in valid_roles:
            return tok
    return implicit_role(snap, e)


class _Computer:
    def __init__(self, snap: Snapshot) -> None:
        self.snap = snap

    def hidden(self, e: Element) -> bool:
        """名前の走査から除外する要素（レンダリングなし／visibility:hidden／aria-hidden=true）。"""
        return (not e.rendered or not e.visible or
                (e.attr("aria-hidden") or "").strip().lower() == "true")

    def name(self, e: Element, *, traversal: bool, labelledby: bool, visited: frozenset[int]) -> AccName:
        # 2A: 非表示。aria-labelledby の直接参照先と、その参照元の走査中は除外しない
        if e.i in visited:
            return AccName("", "none")
        visited = visited | {e.i}
        if self.hidden(e) and not labelledby:
            return AccName("", "none")
        role = effective_role(self.snap, e)

        # 2B: aria-labelledby（走査の最初の要素のみ）
        if not labelledby and not traversal:
            ids = e.refs.get("aria-labelledby", ())
            targets = [self.snap[k] for k in ids if k >= 0]
            if targets:
                parts = [self.name(t, traversal=True, labelledby=True, visited=visited).name for t in targets]
                joined = _norm(" ".join(p for p in parts if p))
                if joined:
                    return AccName(joined, "aria-labelledby")
        # 2C: aria-label
        label = _norm(e.attr("aria-label") or "")
        if label and not (traversal and self._embedded(role)):
            return AccName(label, "aria-label")
        # 2E: 走査中の埋め込みコントロールは値を使う
        if traversal and self._embedded(role):
            val = self._control_value(e, role)
            if val:
                return AccName(val, "native")
        # 2D: ネイティブ代替
        native = self._native(e, role, visited)
        if native:
            return AccName(native, "native")
        # 2F: 内容から（ロールが許可、または走査中）
        if traversal or role in _NAME_FROM_CONTENT or e.tag in _TAG_NAME_FROM_CONTENT:
            content = self._content(e, visited)
            if content:
                return AccName(content, "content")
        # 2I: ツールチップ属性 / svg title
        title = _norm(e.attr("title") or "")
        if title:
            return AccName(title, "title")
        return AccName("", "none")

    @staticmethod
    def _embedded(role: str | None) -> bool:
        return role in ("textbox", "combobox", "listbox", "slider", "spinbutton", "searchbox")

    def _control_value(self, e: Element, role: str | None) -> str:
        if role in ("slider", "spinbutton"):
            return _norm(e.attr("aria-valuetext") or e.attr("aria-valuenow") or e.value or "")
        return _norm(e.value or "")

    def _native(self, e: Element, role: str | None, visited: frozenset[int]) -> str:
        tag = e.tag
        snap = self.snap
        if tag in ("img", "area") or (tag == "input" and (e.attr("type") or "").lower() == "image"):
            alt = e.attr("alt")
            if alt is not None:
                return _norm(alt)
        if tag == "input":
            t = (e.attr("type") or "text").lower()
            if t in ("button", "submit", "reset"):
                v = _norm(e.attr("value") or "")
                if v:
                    return v
        if tag in ("input", "select", "textarea", "meter", "progress", "output", "button") or role in (
            "textbox", "combobox", "listbox", "checkbox", "radio", "slider", "spinbutton", "searchbox", "switch"
        ):
            names = []
            for k in e.labels:
                lab = self.name(snap[k], traversal=True, labelledby=False, visited=visited)
                if lab.name:
                    names.append(lab.name)
            if names:
                return _norm(" ".join(names))
            if tag == "input" and (e.attr("type") or "").lower() in ("submit", "reset") and not e.labels:
                return "Submit" if (e.attr("type") or "").lower() == "submit" else "Reset"
        if tag == "fieldset":
            for c in snap.children(e.i):
                if c.tag == "legend":
                    return self.name(c, traversal=True, labelledby=False, visited=visited).name
        if tag == "table":
            for c in snap.children(e.i):
                if c.tag == "caption":
                    return self.name(c, traversal=True, labelledby=False, visited=visited).name
        if tag == "figure":
            for c in snap.children(e.i):
                if c.tag == "figcaption":
                    return self.name(c, traversal=True, labelledby=False, visited=visited).name
        if e.ns == "svg" and tag == "svg":
            for c in snap.children(e.i):
                if c.tag == "title":  # SVG title は UA で display:none のため本文を直接読む
                    return _norm("".join(k for k in c.kids if isinstance(k, str)))
        return ""

    def _content(self, e: Element, visited: frozenset[int]) -> str:
        out = [e.before]
        for k in e.kids:
            if isinstance(k, str):
                out.append(k)
                continue
            child = self.snap[k]
            if child.tag == "title" and child.ns == "svg" and e.tag != "svg":
                continue
            sub = self.name(child, traversal=True, labelledby=False, visited=visited).name
            inline = (child.style.get("display") or "inline").split()[0] in _INLINE_DISPLAY
            out.append(sub if inline else f" {sub} ")
        out.append(e.after)
        return _norm("".join(out))


def compute_name(snap: Snapshot, index: int) -> AccName:
    """要素のアクセシブル名を返す。名前が無ければ AccName("", "none")。"""
    return _Computer(snap).name(snap[index], traversal=False, labelledby=False, visited=frozenset())


def has_name(snap: Snapshot, index: int) -> bool:
    return bool(compute_name(snap, index).name)
