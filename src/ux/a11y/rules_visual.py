"""視覚・操作系ルール（D 表）: contrast / target-size / scroll-focusable / tabindex。

snapshot["elements"] の要素が使うキー:
  id, selector, tag, attrs, role, visible, focusable, bbox{x,y,width,height}, parent, children,
  text(直下テキスト), style{color, backgroundColor, backgroundImage, opacity, fontSize,
  fontWeight, display, position, overflowX, overflowY, appearance, overlapped(任意 bool)},
  scroll{scrollHeight, clientHeight, scrollWidth, clientWidth}
確信できないものは cant_tell。背景が画像・グラデーション・重なりで決まらない場合は判定しない。
"""
from __future__ import annotations

import math
import re
from typing import Callable

from src.ux.a11y.color import RGBA, blend, contrast_ratio, parse_color
from src.ux.a11y.models import Finding

CONTRAST = "visual.contrast"
TARGET = "visual.target-size"
SCROLL = "op.scroll-focusable"
TABINDEX = "bp.tabindex"


def _f(rule, status, el, impact, message, **ev) -> Finding:
    return Finding(rule_id=rule, status=status, selector=el.get("selector", ""),
                   bbox=el.get("bbox"), evidence=ev, impact=impact, message=message)


def _index(snapshot):
    return {e["id"]: e for e in snapshot.get("elements", [])}


def _px(v, default=None):
    try:
        return float(str(v).replace("px", "").strip())
    except (TypeError, ValueError):
        return default


def _chain(el, idx):
    """自身→祖先の順。"""
    out, cur, n = [], el, 0
    while cur is not None and n < 300:
        out.append(cur)
        cur = idx.get(cur.get("parent"))
        n += 1
    return out


# ---- visual.contrast --------------------------------------------------------
def _is_disabled(chain) -> bool:
    for e in chain:
        a = e.get("attrs") or {}
        if "disabled" in a or a.get("aria-disabled", "").strip().lower() == "true":
            return True
    return False


def _overlaps(a, b) -> bool:
    return not (a["x"] + a["width"] <= b["x"] or b["x"] + b["width"] <= a["x"]
                or a["y"] + a["height"] <= b["y"] or b["y"] + b["height"] <= a["y"])


def _covered(el, chain_ids, snapshot) -> bool:
    bb = el.get("bbox")
    if not bb:
        return False
    for o in snapshot.get("elements", []):
        if o["id"] in chain_ids or not o.get("visible", True) or not o.get("bbox"):
            continue
        st = o.get("style") or {}
        if st.get("position") not in ("absolute", "fixed", "sticky"):
            continue
        painted = (parse_color(st.get("backgroundColor")) or (0, 0, 0, 1))[3] > 0 or \
            st.get("backgroundImage", "none") not in ("none", "")
        if painted and _overlaps(bb, o["bbox"]):
            return True
    return False


def check_contrast(snapshot: dict) -> list[Finding]:
    idx = _index(snapshot)
    out = []
    for el in snapshot.get("elements", []):
        if not el.get("visible", True) or not (el.get("text") or "").strip():
            continue
        chain = _chain(el, idx)
        if _is_disabled(chain):
            continue
        st = el.get("style") or {}
        fg = parse_color(st.get("color"))
        if fg is None:
            out.append(_f(CONTRAST, "cant_tell", el, "serious", "文字色を解釈できない", color=st.get("color")))
            continue
        # 不透明度（祖先を含めて掛け合わせ）
        op = 1.0
        for e in chain:
            o = _px((e.get("style") or {}).get("opacity"), 1.0)
            op *= 1.0 if o is None else o
        # 背景を自身→祖先で収集
        layers: list[RGBA] = []
        reason = None
        opaque = False
        for e in chain:
            es = e.get("style") or {}
            if es.get("backgroundImage", "none") not in ("none", ""):
                reason = "背景が画像・グラデーション"
                break
            bg = parse_color(es.get("backgroundColor") or "transparent")
            if bg is None:
                reason = "背景色を解釈できない"
                break
            if bg[3] > 0:
                layers.append(bg)
            if bg[3] >= 1.0:
                opaque = True
                break
        if reason is None and _covered(el, {e["id"] for e in chain}, snapshot):
            reason = "別要素が重なっている可能性"
        if reason is None and st.get("overlapped"):
            reason = "別要素が重なっている"
        if reason is None and fg[3] <= 0:
            reason = "文字が透明"
        if reason:
            out.append(_f(CONTRAST, "cant_tell", el, "serious", reason))
            continue
        base = (255.0, 255.0, 255.0)  # 最上位が不透明でなければキャンバス白
        bgc = base
        for layer in reversed(layers):
            bgc = blend(layer, bgc)
        text = blend((fg[0], fg[1], fg[2], fg[3] * op), bgc)
        ratio = contrast_ratio(text, bgc)
        size = _px(st.get("fontSize"), 16.0)
        weight = st.get("fontWeight", "400")
        try:
            bold = int(weight) >= 700
        except ValueError:
            bold = str(weight).lower() in ("bold", "bolder")
        large = size >= 24.0 or (bold and size >= 18.66)
        need = 3.0 if large else 4.5
        ev = {"ratio": round(ratio, 2), "required": need, "large_text": large,
              "foreground": [round(c) for c in text], "background": [round(c) for c in bgc]}
        if ratio + 1e-9 < need:
            out.append(_f(CONTRAST, "violation", el, "serious", "コントラスト比が基準未満", **ev))
        else:
            out.append(_f(CONTRAST, "pass", el, "serious", "コントラスト比が基準以上", **ev))
    return out


# ---- visual.target-size -----------------------------------------------------
_TARGET_TAGS = {"button", "select", "textarea", "summary"}
_TARGET_ROLES = {"button", "link", "checkbox", "radio", "switch", "tab", "menuitem",
                 "menuitemcheckbox", "menuitemradio", "option", "slider", "spinbutton",
                 "textbox", "searchbox", "combobox", "treeitem"}
MIN = 24.0


def _is_target(e) -> bool:
    if not e.get("visible", True) or not e.get("focusable") or not e.get("bbox"):
        return False
    a = e.get("attrs") or {}
    if "disabled" in a or a.get("aria-disabled", "").strip().lower() == "true":
        return False
    tag = e.get("tag", "")
    if tag == "input":
        return a.get("type", "text").lower() != "hidden"
    if tag == "a":
        return "href" in a
    return tag in _TARGET_TAGS or e.get("role") in _TARGET_ROLES


def _circle_hits_rect(cx, cy, r, bb) -> bool:
    nx = min(max(cx, bb["x"]), bb["x"] + bb["width"])
    ny = min(max(cy, bb["y"]), bb["y"] + bb["height"])
    return (cx - nx) ** 2 + (cy - ny) ** 2 < r * r


def check_target_size(snapshot: dict) -> list[Finding]:
    idx = _index(snapshot)
    targets = [e for e in snapshot.get("elements", []) if _is_target(e)]
    out = []
    for t in targets:
        bb = t["bbox"]
        w, h = bb["width"], bb["height"]
        if w * h <= 1.0:
            continue  # 視覚的に存在しない（sr-only 等）
        if w >= MIN and h >= MIN:
            out.append(_f(TARGET, "pass", t, "serious", "24x24 以上", width=w, height=h))
            continue
        st = t.get("style") or {}
        a = t.get("attrs") or {}
        ev = {"width": w, "height": h}
        # 例外 1: UA 既定の見た目のコントロール（appearance を変更していないもの）
        if t.get("tag") in ("select", "input") and st.get("appearance", "auto") in ("auto", "menulist", "checkbox", "radio", ""):
            if t.get("tag") == "select" or a.get("type", "").lower() in ("checkbox", "radio"):
                out.append(_f(TARGET, "pass", t, "serious", "ブラウザ標準コントロールは例外", **ev))
                continue
        # 例外 2: 文章中のインラインリンク
        parent = idx.get(t.get("parent"))
        if st.get("display") == "inline" and parent and (parent.get("text") or "").strip():
            out.append(_f(TARGET, "pass", t, "serious", "文中のインライン対象は例外", **ev))
            continue
        # 例外 3: 同じ遷移先を持つ 24px 以上の等価コントロールがある
        href = a.get("href")
        if href and any((o is not t and (o.get("attrs") or {}).get("href") == href
                        and o["bbox"]["width"] >= MIN and o["bbox"]["height"] >= MIN) for o in targets):
            out.append(_f(TARGET, "pass", t, "serious", "同じ遷移先の十分な大きさの対象がある", **ev))
            continue
        # 例外 4: 間隔（24px 直径の円が他の対象/円と交差しない）
        cx, cy = bb["x"] + w / 2, bb["y"] + h / 2
        hit = False
        for o in targets:
            if o is t:
                continue
            ob = o["bbox"]
            if _circle_hits_rect(cx, cy, MIN / 2, ob):
                hit = True
                break
            if ob["width"] < MIN or ob["height"] < MIN:
                ox, oy = ob["x"] + ob["width"] / 2, ob["y"] + ob["height"] / 2
                if math.hypot(cx - ox, cy - oy) < MIN:
                    hit = True
                    break
        if not hit:
            out.append(_f(TARGET, "pass", t, "serious", "間隔の例外を満たす", **ev))
        else:
            out.append(_f(TARGET, "violation", t, "serious", "24x24 未満で間隔の例外も満たさない", **ev))
    return out


# ---- op.scroll-focusable ----------------------------------------------------
def check_scroll_focusable(snapshot: dict) -> list[Finding]:
    idx = _index(snapshot)
    out = []
    for el in snapshot.get("elements", []):
        if not el.get("visible", True) or el.get("tag") in ("html", "body"):
            continue
        sc = el.get("scroll") or {}
        st = el.get("style") or {}
        scrollable = False
        for ov, total, client in (("overflowY", "scrollHeight", "clientHeight"),
                                  ("overflowX", "scrollWidth", "clientWidth")):
            if st.get(ov) in ("auto", "scroll") and (_px(sc.get(client), 0) or 0) > 0 \
                    and (_px(sc.get(total), 0) or 0) - (_px(sc.get(client), 0) or 0) >= 2:
                scrollable = True
        if not scrollable:
            continue
        stack, inner = list(el.get("children", [])), []
        while stack:
            c = idx.get(stack.pop())
            if c is None:
                continue
            if c.get("visible", True) and c.get("focusable"):
                inner.append(c)
            stack.extend(c.get("children", []))
        if el.get("focusable") or inner:
            out.append(_f(SCROLL, "pass", el, "serious", "キーボードで到達できる"))
        else:
            out.append(_f(SCROLL, "violation", el, "serious", "スクロール領域にフォーカス可能な要素が無い",
                          scrollHeight=sc.get("scrollHeight"), clientHeight=sc.get("clientHeight")))
    return out


# ---- bp.tabindex（best-practice。WCAG 違反ではない） -------------------------
def check_tabindex(snapshot: dict) -> list[Finding]:
    out = []
    for el in snapshot.get("elements", []):
        a = el.get("attrs") or {}
        if "tabindex" not in a or not el.get("visible", True):
            continue
        raw = a["tabindex"].strip()
        if not re.fullmatch(r"[+-]?\d+", raw):
            continue
        if int(raw) > 0:
            out.append(_f(TABINDEX, "violation", el, "serious", "tabindex が 0 より大きい", tabindex=int(raw)))
        else:
            out.append(_f(TABINDEX, "pass", el, "serious", "tabindex は 0 以下", tabindex=int(raw)))
    return out


VISUAL_RULES: dict[str, Callable[[dict], list[Finding]]] = {
    CONTRAST: check_contrast,
    TARGET: check_target_size,
    SCROLL: check_scroll_focusable,
    TABINDEX: check_tabindex,
}


def run_visual_rules(snapshot: dict) -> dict[str, list[Finding]]:
    return {rid: fn(snapshot) for rid, fn in VISUAL_RULES.items()}
