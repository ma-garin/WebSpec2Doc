"""文書/メタ/構造系ルール（設計 E1 W3・B 表・E 表）と autocomplete。

入力は snapshot（dict）、出力は ``RuleResult``。純関数。snapshot の前提は rules_name と同じで、
追加で次を使う:
    title: str|None   document.title（要素なし＝空文字。None は取得失敗＝cant_tell）
    elements の tag=html / meta / title / li / ul / ol / a / h1-h6 / 各ランドマーク
ARIA 参照・見出し・ランドマークの判定は属性とタグだけで行い、E1a の role 計算に依存しない。
確信できないものは違反にせず cant_tell にする。
"""
from __future__ import annotations

import re
from typing import Callable

from .data.lang_autocomplete import (
    DEFAULT_REGISTRY, INVALID, VALID, validate_autocomplete, validate_lang,
)
from .models import NodeResult, RuleResult
from .rules_name import (
    CANT_TELL, PASS, VIOLATION, attr_text, attrs, elements_of, exposed, explicit_role,
    has_attr, index_of, input_type, is_disabled, make_node, make_result, tag, undecidable,
)

IDREF_ATTRS = (
    "aria-labelledby", "aria-describedby", "aria-owns", "aria-controls", "aria-flowto",
    "aria-activedescendant", "aria-details", "aria-errormessage",
)
AUTOFILL_INPUT_TYPES = {
    "text", "search", "url", "tel", "email", "password", "date", "month", "week", "time",
    "datetime-local", "number", "range", "color",
}
_WS = re.compile(r"\s+")


def _html_el(els: list[dict]) -> dict | None:
    for e in els:
        if tag(e) == "html":
            return e
    return None


def _doc_node(status: str, els: list[dict], impact: str, message: str, **ev) -> NodeResult:
    html = _html_el(els) or {"selector": "html"}
    return make_node(status, html, impact, message, **ev)


# ------------------------------------------------------------------ doc.*
def check_title(snapshot: dict) -> RuleResult:
    """doc.title（旧 document-title / ACT 2779a5 / WCAG 2.4.2）。最上位文書のみ対象。"""
    rid = "doc.title"
    els = elements_of(snapshot)
    if els is None:
        return undecidable(rid, "snapshot が利用できない")
    title = snapshot.get("title")
    if title is None:
        return undecidable(rid, "document.title を取得できない")
    if str(title).strip():
        return make_result(rid, [_doc_node(PASS, els, "serious", "title がある", title=title)])
    return make_result(rid, [_doc_node(VIOLATION, els, "serious", "title が空", title=title)])


def check_lang_present(snapshot: dict) -> RuleResult:
    """doc.lang-present（旧 html-has-lang / WCAG 3.1.1）。"""
    rid = "doc.lang-present"
    els = elements_of(snapshot)
    html = _html_el(els) if els is not None else None
    if html is None:
        return undecidable(rid, "html 要素を取得できない")
    lang = attr_text(html, "lang")
    if lang:
        return make_result(rid, [make_node(PASS, html, "serious", "lang がある", lang=lang)])
    return make_result(rid, [make_node(VIOLATION, html, "serious", "html に lang がない（または空）", lang=lang)])


def check_lang_valid(snapshot: dict, registry: dict | None = DEFAULT_REGISTRY) -> RuleResult:
    """doc.lang-valid（旧 html-lang-valid / ACT bf051a / WCAG 3.1.1）。

    登録簿は部分スナップショット。確認できないサブタグは cant_tell。registry が空・None なら cant_tell。
    """
    rid = "doc.lang-valid"
    els = elements_of(snapshot)
    html = _html_el(els) if els is not None else None
    if html is None:
        return undecidable(rid, "html 要素を取得できない")
    lang = attr_text(html, "lang")
    if not lang:
        return make_result(rid, [])  # inapplicable（欠落は doc.lang-present が扱う）
    if not registry:
        return undecidable(rid, "言語サブタグ登録簿を参照できない")
    verdict, reason = validate_lang(lang, registry)
    if verdict == VALID:
        return make_result(rid, [make_node(PASS, html, "serious", "lang が有効", lang=lang)])
    if verdict == INVALID:
        return make_result(rid, [make_node(VIOLATION, html, "serious", f"lang が無効: {reason}", lang=lang)])
    return make_result(rid, [make_node(CANT_TELL, html, "serious", f"lang を確認できない: {reason}", lang=lang)])


_VP_SPLIT = re.compile(r"[,;\s]+")


def _parse_viewport(content: str) -> dict:
    out = {}
    for part in _VP_SPLIT.split(re.sub(r"\s*=\s*", "=", content.strip().lower())):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _num(v: str) -> float | None:
    try:
        return float(v)
    except ValueError:
        return None


def check_viewport_zoom(snapshot: dict) -> RuleResult:
    """doc.viewport-zoom（旧 meta-viewport / ACT b4f0c3 / WCAG 1.4.4）。"""
    rid = "doc.viewport-zoom"
    els = elements_of(snapshot)
    if els is None:
        return undecidable(rid, "snapshot が利用できない")
    metas = [e for e in els if tag(e) == "meta" and attr_text(e, "name").lower() == "viewport"
             and has_attr(e, "content")]
    if not metas:
        return make_result(rid, [])
    el = metas[-1]  # 複数ある場合はブラウザと同様に最後を採用
    content = attr_text(el, "content")
    props = _parse_viewport(content)
    problems, unsure = [], []
    us = props.get("user-scalable")
    if us in ("no", "0"):
        problems.append("user-scalable で拡大を禁止している")
    elif us is not None and us not in ("yes", "1", "device-width", "device-height"):
        unsure.append(f"user-scalable={us!r} を解釈できない")
    ms = props.get("maximum-scale")
    if ms is not None and ms not in ("device-width", "device-height"):
        n = _num(ms)
        if n is None or n < 0:
            unsure.append(f"maximum-scale={ms!r} を解釈できない")
        elif n < 2:
            problems.append(f"maximum-scale={ms} が 2 未満")
    if problems:
        return make_result(rid, [make_node(VIOLATION, el, "critical", "; ".join(problems), content=content)])
    if unsure:
        return make_result(rid, [make_node(CANT_TELL, el, "critical", "; ".join(unsure), content=content)])
    return make_result(rid, [make_node(PASS, el, "critical", "拡大を妨げない", content=content)])


def _ids(els: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for e in els:
        i = attr_text(e, "id")
        if i:
            out.setdefault(i, []).append(e)
    return out


def check_bypass(snapshot: dict) -> RuleResult:
    """doc.bypass（旧 bypass / ACT cf77f2 / WCAG 2.4.1）。部分実装。

    スキップリンク（同一文書内の存在する id 宛）または main ランドマークがあれば pass（有効性までは見ない）。
    見出しだけの場合は cant_tell。どれも無ければ violation。
    """
    rid = "doc.bypass"
    els = elements_of(snapshot)
    if els is None:
        return undecidable(rid, "snapshot が利用できない")
    ids = _ids(els)
    skip = [e for e in els if tag(e) == "a" and attr_text(e, "href").startswith("#")
            and len(attr_text(e, "href")) > 1 and attr_text(e, "href")[1:] in ids]
    main = [e for e in els if tag(e) == "main" or explicit_role(e) == "main"]
    if skip:
        return make_result(rid, [_doc_node(PASS, els, "serious", "スキップリンクがある（有効性は未検証）",
                                           mechanism="skip-link", target=attr_text(skip[0], "href"))])
    if main:
        return make_result(rid, [_doc_node(PASS, els, "serious", "main ランドマークがある（有効性は未検証）",
                                           mechanism="main-landmark")])
    heads = [e for e in els if _heading_level(e) not in (None, "bad")]
    if heads:
        return make_result(rid, [_doc_node(CANT_TELL, els, "serious",
                                           "見出しはあるがスキップリンク・main がない。手動確認が必要",
                                           mechanism="headings-only")])
    return make_result(rid, [_doc_node(VIOLATION, els, "serious",
                                       "スキップリンク・main ランドマーク・見出しのいずれもない")])


def check_duplicate_id_aria(snapshot: dict) -> RuleResult:
    """doc.duplicate-id-aria（旧 duplicate-id-aria / WCAG 4.1.2）。ARIA 参照される id の重複のみ。"""
    rid = "doc.duplicate-id-aria"
    els = elements_of(snapshot)
    if els is None:
        return undecidable(rid, "snapshot が利用できない")
    refs: set[str] = set()
    for e in els:
        for a in IDREF_ATTRS:
            refs.update(attr_text(e, a).split())
    if not refs:
        return make_result(rid, [])
    nodes = []
    for i, group in _ids(els).items():
        if i not in refs:
            continue
        if len(group) > 1:
            nodes += [make_node(VIOLATION, e, "critical", f"ARIA から参照される id {i!r} が重複", id=i,
                                count=len(group)) for e in group]
        else:
            nodes.append(make_node(PASS, group[0], "critical", "参照される id は一意", id=i))
    return make_result(rid, nodes)


# ------------------------------------------------------------------ struct.*
def _children(els: list[dict]) -> dict:
    out: dict = {}
    for i, e in enumerate(els):
        out.setdefault(e.get("parent"), []).append(e)
    return out


def check_list(snapshot: dict) -> RuleResult:
    """struct.list（旧 list / WCAG 1.3.1）。ul/ol の直下は li・script・template のみ。"""
    rid = "struct.list"
    els = elements_of(snapshot)
    if els is None:
        return undecidable(rid, "snapshot が利用できない")
    kids = _children(els)
    by_idx = index_of(els)
    nodes = []
    for i, e in enumerate(els):
        if tag(e) not in ("ul", "ol") or explicit_role(e) not in (None, "list"):
            continue
        if exposed(e, by_idx) is False:
            continue
        key = e.get("idx", i)
        bad = [c for c in kids.get(key, []) if tag(c) not in ("li", "script", "template")
               and explicit_role(c) != "listitem"]
        if bad:
            nodes.append(make_node(VIOLATION, e, "serious", "リスト直下に li 以外の要素がある",
                                   offending=[tag(c) for c in bad]))
        else:
            nodes.append(make_node(PASS, e, "serious", "リスト直下は li のみ"))
    return make_result(rid, nodes)


def check_listitem(snapshot: dict) -> RuleResult:
    """struct.listitem（旧 listitem / WCAG 1.3.1）。li の親は ul/ol/menu（または role=list）。"""
    rid = "struct.listitem"
    els = elements_of(snapshot)
    if els is None:
        return undecidable(rid, "snapshot が利用できない")
    by_idx = index_of(els)
    nodes = []
    for e in els:
        if tag(e) != "li" or explicit_role(e) not in (None, "listitem"):
            continue
        if exposed(e, by_idx) is False:
            continue
        p = by_idx.get(e.get("parent"))
        if p is None:
            nodes.append(make_node(CANT_TELL, e, "serious", "親要素を取得できない"))
            continue
        prole = explicit_role(p)
        if prole == "list" or (prole is None and tag(p) in ("ul", "ol", "menu")):
            nodes.append(make_node(PASS, e, "serious", "li の親がリスト"))
        elif prole in ("none", "presentation") and tag(p) in ("ul", "ol", "menu"):
            nodes.append(make_node(CANT_TELL, e, "serious", "親リストの role が none/presentation"))
        else:
            nodes.append(make_node(VIOLATION, e, "serious", "li の親が ul/ol/menu ではない", parent=tag(p)))
    return make_result(rid, nodes)


# ------------------------------------------------------------------ form.autocomplete
def check_autocomplete(snapshot: dict) -> RuleResult:
    """form.autocomplete（旧 autocomplete-valid / ACT 73f2c2 / WCAG 1.3.5）。WHATWG の語彙表と照合。"""
    rid = "form.autocomplete"
    els = elements_of(snapshot)
    if els is None:
        return undecidable(rid, "snapshot が利用できない")
    nodes = []
    for e in els:
        t = tag(e)
        if t not in ("input", "select", "textarea") or not attr_text(e, "autocomplete"):
            continue
        if t == "input" and input_type(e) not in AUTOFILL_INPUT_TYPES:
            continue
        if is_disabled(e):
            continue
        vis = e.get("visible")
        if vis is False:
            continue
        if vis is None:
            nodes.append(make_node(CANT_TELL, e, "serious", "可視性が不明"))
            continue
        val = attr_text(e, "autocomplete")
        ok, reason = validate_autocomplete(val)
        if ok:
            nodes.append(make_node(PASS, e, "serious", "autocomplete が有効", autocomplete=val))
        else:
            nodes.append(make_node(VIOLATION, e, "serious", f"autocomplete が無効: {reason}", autocomplete=val))
    return make_result(rid, nodes)


# ------------------------------------------------------------------ bp.* (best practice)
LANDMARK_ROLES = {"banner", "complementary", "contentinfo", "form", "main", "navigation", "region", "search"}
_SECTIONING = {"article", "aside", "main", "nav", "section"}


def _heading_level(el: dict):
    """見出しなら 1..6、見出しでなければ None、aria-level が不正なら 'bad'。"""
    role = explicit_role(el)
    t = tag(el)
    if role is not None:
        if role != "heading":
            return None
        raw = attr_text(el, "aria-level")
        if not raw:
            return 2
        return int(raw) if raw.isdigit() and 1 <= int(raw) <= 6 else "bad"
    if len(t) == 2 and t[0] == "h" and t[1] in "123456":
        return int(t[1])
    return None


def check_heading_order(snapshot: dict) -> RuleResult:
    """bp.heading-order（旧 heading-order。best-practice）。見出しレベルが 2 以上飛ばない。"""
    rid = "bp.heading-order"
    els = elements_of(snapshot)
    if els is None:
        return undecidable(rid, "snapshot が利用できない")
    by_idx = index_of(els)
    nodes, prev = [], None
    for e in els:
        lvl = _heading_level(e)
        if lvl is None or exposed(e, by_idx) is not True:
            continue
        if lvl == "bad":
            nodes.append(make_node(CANT_TELL, e, "moderate", "aria-level を解釈できない"))
            continue
        if prev is not None and lvl > prev + 1:
            nodes.append(make_node(VIOLATION, e, "moderate", f"見出しレベルが h{prev} から {lvl} へ飛ぶ",
                                   level=lvl, previous=prev))
        else:
            nodes.append(make_node(PASS, e, "moderate", "見出し順が連続", level=lvl))
        prev = lvl
    return make_result(rid, nodes)


def check_page_has_h1(snapshot: dict) -> RuleResult:
    """bp.page-has-heading-one（旧 page-has-heading-one。best-practice）。"""
    rid = "bp.page-has-heading-one"
    els = elements_of(snapshot)
    if els is None:
        return undecidable(rid, "snapshot が利用できない")
    by_idx = index_of(els)
    unsure = False
    for e in els:
        if _heading_level(e) == 1:
            ex = exposed(e, by_idx)
            if ex:
                return make_result(rid, [make_node(PASS, e, "moderate", "レベル 1 の見出しがある")])
            unsure = unsure or ex is None
    if unsure:
        return undecidable(rid, "レベル 1 の見出しの可視性が不明")
    return make_result(rid, [_doc_node(VIOLATION, els, "moderate", "レベル 1 の見出しがない")])


def _landmark_role(el: dict, by_idx: dict) -> str | None:
    role = explicit_role(el)
    if role is not None:
        return role if role in LANDMARK_ROLES else None
    t = tag(el)
    simple = {"main": "main", "nav": "navigation", "aside": "complementary", "search": "search"}
    if t in simple:
        return simple[t]
    if t in ("header", "footer"):
        cur = by_idx.get(el.get("parent"))
        while cur is not None:
            if tag(cur) in _SECTIONING or explicit_role(cur) in ("article", "complementary", "main",
                                                                  "navigation", "region"):
                return None
            cur = by_idx.get(cur.get("parent"))
        return "banner" if t == "header" else "contentinfo"
    if t in ("form", "section") and (el.get("accname") or "").strip():
        return "form" if t == "form" else "region"
    return None


def _landmarks(els: list[dict]):
    """(要素, ランドマーク role, 公開状態) の列。"""
    by_idx = index_of(els)
    out = []
    for e in els:
        r = _landmark_role(e, by_idx)
        if r:
            out.append((e, r, exposed(e, by_idx)))
    return out, by_idx


def _has_landmark_ancestor(e: dict, by_idx: dict) -> bool:
    cur = by_idx.get(e.get("parent"))
    while cur is not None:
        if _landmark_role(cur, by_idx):
            return True
        cur = by_idx.get(cur.get("parent"))
    return False


def _landmark_rule(rid: str, snapshot: dict, per_landmark: Callable) -> RuleResult:
    els = elements_of(snapshot)
    if els is None:
        return undecidable(rid, "snapshot が利用できない")
    lms, by_idx = _landmarks(els)
    return make_result(rid, per_landmark(els, lms, by_idx))


def _one_main(els, lms, by_idx):
    mains = [x for x in lms if x[1] == "main"]
    if any(x[2] for x in mains):
        return [make_node(PASS, mains[0][0], "moderate", "main ランドマークがある")]
    if any(x[2] is None for x in mains):
        return [make_node(CANT_TELL, mains[0][0], "moderate", "main の可視性が不明")]
    return [_doc_node(VIOLATION, els, "moderate", "main ランドマークがない")]


def _no_duplicate(role: str):
    def run(els, lms, by_idx):
        same = [x for x in lms if x[1] == role]
        shown = [x for x in same if x[2]]
        nodes = [make_node(CANT_TELL, x[0], "moderate", "可視性が不明") for x in same if x[2] is None]
        if len(shown) > 1:
            nodes += [make_node(VIOLATION, x[0], "moderate", f"{role} ランドマークが重複", count=len(shown))
                      for x in shown]
        elif shown:
            nodes.append(make_node(PASS, shown[0][0], "moderate", f"{role} は 1 つ"))
        return nodes
    return run


def _top_level(role: str):
    def run(els, lms, by_idx):
        nodes = []
        for e, r, ex in lms:
            if r != role or ex is False:
                continue
            if ex is None:
                nodes.append(make_node(CANT_TELL, e, "moderate", "可視性が不明"))
            elif _has_landmark_ancestor(e, by_idx):
                nodes.append(make_node(VIOLATION, e, "moderate", f"{role} が他のランドマークの内側にある"))
            else:
                nodes.append(make_node(PASS, e, "moderate", f"{role} が最上位"))
        return nodes
    return run


def _unique(els, lms, by_idx):
    groups: dict = {}
    nodes = []
    for e, r, ex in lms:
        if ex is False:
            continue
        name = e.get("accname")
        if ex is None or name is None:
            nodes.append(make_node(CANT_TELL, e, "moderate", "名前または可視性が不明"))
            continue
        groups.setdefault((r, _WS.sub(" ", name.strip().lower())), []).append(e)
    for (r, name), g in groups.items():
        for e in g:
            if len(g) > 1:
                nodes.append(make_node(VIOLATION, e, "moderate", f"同じ role/名前の {r} が複数ある",
                                       role=r, name=name, count=len(g)))
            else:
                nodes.append(make_node(PASS, e, "moderate", "ランドマークが一意", role=r, name=name))
    return nodes


def check_landmark_one_main(s): return _landmark_rule("bp.landmark-one-main", s, _one_main)
def check_landmark_no_dup_main(s): return _landmark_rule("bp.landmark-no-duplicate-main", s, _no_duplicate("main"))
def check_landmark_no_dup_banner(s): return _landmark_rule("bp.landmark-no-duplicate-banner", s, _no_duplicate("banner"))
def check_landmark_no_dup_contentinfo(s): return _landmark_rule("bp.landmark-no-duplicate-contentinfo", s, _no_duplicate("contentinfo"))
def check_landmark_main_top(s): return _landmark_rule("bp.landmark-main-is-top-level", s, _top_level("main"))
def check_landmark_banner_top(s): return _landmark_rule("bp.landmark-banner-is-top-level", s, _top_level("banner"))
def check_landmark_contentinfo_top(s): return _landmark_rule("bp.landmark-contentinfo-is-top-level", s, _top_level("contentinfo"))
def check_landmark_unique(s): return _landmark_rule("bp.landmark-unique", s, _unique)


RULES: dict[str, Callable[[dict], RuleResult]] = {
    "doc.title": check_title,
    "doc.lang-present": check_lang_present,
    "doc.lang-valid": check_lang_valid,
    "doc.viewport-zoom": check_viewport_zoom,
    "doc.bypass": check_bypass,
    "doc.duplicate-id-aria": check_duplicate_id_aria,
    "struct.list": check_list,
    "struct.listitem": check_listitem,
    "form.autocomplete": check_autocomplete,
    "bp.heading-order": check_heading_order,
    "bp.page-has-heading-one": check_page_has_h1,
    "bp.landmark-one-main": check_landmark_one_main,
    "bp.landmark-no-duplicate-main": check_landmark_no_dup_main,
    "bp.landmark-no-duplicate-banner": check_landmark_no_dup_banner,
    "bp.landmark-no-duplicate-contentinfo": check_landmark_no_dup_contentinfo,
    "bp.landmark-main-is-top-level": check_landmark_main_top,
    "bp.landmark-banner-is-top-level": check_landmark_banner_top,
    "bp.landmark-contentinfo-is-top-level": check_landmark_contentinfo_top,
    "bp.landmark-unique": check_landmark_unique,
}
