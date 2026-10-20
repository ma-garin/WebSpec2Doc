"""HTML 断片から snapshot 相当の dict を作るテスト用ヘルパー（E1b の単体テスト専用）。

実際の snapshot は E1a がブラウザ内で作る。ここでは accname を簡易近似するだけで、
ルールの入出力契約（elements/parent/attrs/accname/visible/title）を再現する。
"""
from __future__ import annotations

import copy
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.els: list[dict] = []
        self.stack: list[int] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, t, attr_list):
        idx = len(self.els)
        attrs = {k.lower(): (v if v is not None else "") for k, v in attr_list}
        hidden = "hidden" in attrs or "display:none" in attrs.get("style", "").replace(" ", "")
        parent = self.stack[-1] if self.stack else None
        if parent is not None and not self.els[parent]["visible"]:
            hidden = True
        self.els.append({"idx": idx, "parent": parent, "tag": t, "attrs": attrs, "visible": not hidden,
                         "selector": f"{t}[{idx}]", "bbox": None, "_text": [], "children": []})
        if parent is not None:
            self.els[parent]["children"].append(idx)
        if t == "title":
            self._in_title = True
        if t not in VOID:
            self.stack.append(idx)

    def handle_endtag(self, t):
        if t == "title":
            self._in_title = False
        if t in VOID:
            return
        for k in range(len(self.stack) - 1, -1, -1):
            if self.els[self.stack[k]]["tag"] == t:
                del self.stack[k:]
                break

    def handle_data(self, d):
        if self._in_title:
            self.title += d
        if self.stack:
            self.els[self.stack[-1]]["_text"].append((len(self.els[self.stack[-1]]["children"]), d))


def _text(els, el):
    if not el["visible"]:
        return ""
    out = []
    kids = el["children"]
    texts = dict()
    for pos, d in el["_text"]:
        texts.setdefault(pos, []).append(d)
    for i in range(len(kids) + 1):
        out += texts.get(i, [])
        if i < len(kids):
            c = els[kids[i]]
            if c["tag"] == "img":
                out.append(c["attrs"].get("alt", ""))
            else:
                out.append(_text(els, c))
    return " ".join("".join(out).split())


def _accname(els, el, by_id, labels_for):
    a = el["attrs"]
    if a.get("aria-labelledby", "").strip():
        parts = [_text(els, by_id[i]) for i in a["aria-labelledby"].split() if i in by_id]
        if any(parts):
            return " ".join(p for p in parts if p)
    if a.get("aria-label", "").strip():
        return a["aria-label"].strip()
    t = el["tag"]
    if t == "img" or (t == "input" and a.get("type") == "image") or t == "area":
        if a.get("alt", "").strip():
            return a["alt"].strip()
    if t in ("input", "textarea", "select"):
        lab = labels_for.get(el["idx"])
        if lab:
            return lab
        if t == "input" and a.get("type") in ("button", "submit", "reset") and a.get("value"):
            return a["value"]
    if a.get("title", "").strip():
        return a["title"].strip()
    if t in ("input", "textarea") and a.get("placeholder", "").strip():
        return a["placeholder"].strip()
    if t in ("iframe", "frame"):
        return ""
    if t in ("input", "textarea", "select", "img"):
        return ""
    return _text(els, el)


def build_snapshot(html: str, *, wrap: bool = True, title: str | None = None, lang: str | None = "en") -> dict:
    if wrap and "<html" not in html.lower():
        la = f' lang="{lang}"' if lang is not None else ""
        html = f"<html{la}><head><title>T</title></head><body>{html}</body></html>"
    b = _Builder()
    b.feed(html)
    els = b.els
    by_id = {e["attrs"]["id"]: e for e in els if e["attrs"].get("id")}
    labels_for = {}
    for e in els:
        if e["tag"] == "label":
            txt = _text(els, e)
            tgt = by_id.get(e["attrs"].get("for"))
            if tgt is not None:
                labels_for[tgt["idx"]] = txt
            else:
                for c in e["children"]:
                    if els[c]["tag"] in ("input", "textarea", "select"):
                        labels_for[c] = txt
    for e in els:
        e["accname"] = _accname(els, e, by_id, labels_for)
        e["labels"] = [labels_for[e["idx"]]] if e["idx"] in labels_for else []
    for e in els:
        e.pop("_text")
        e.pop("children")
    return {"url": "http://t/", "title": b.title.strip() if title is None else title,
            "elements": els, "truncated": False}


def mutate(snapshot: dict, selector_tag: str, **kv) -> dict:
    """指定タグの要素すべてのキーを書き換えた複製を返す（判定不能の再現用）。"""
    s = copy.deepcopy(snapshot)
    for e in s["elements"]:
        if e["tag"] == selector_tag:
            e.update(kv)
    return s
