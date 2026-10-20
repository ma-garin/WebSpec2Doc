"""視覚・操作系ルール（rules_visual / color）の単体テスト。"""
import pytest

from src.ux.a11y import color as C
from src.ux.a11y import rules_visual as V


def el(i, tag="p", parent=None, **kw):
    e = {"id": i, "selector": f"{tag}#{i}", "tag": tag, "attrs": {}, "role": None, "visible": True,
         "focusable": False, "bbox": {"x": 0, "y": 0, "width": 100, "height": 20}, "parent": parent,
         "children": [], "text": "", "style": {}}
    e.update(kw)
    return e


def snap(*els):
    els = list(els)
    byid = {e["id"]: e for e in els}
    for e in els:
        if e["parent"] is not None:
            byid[e["parent"]]["children"].append(e["id"])
    return {"elements": els}


# ---- color ----
def test_luminance_and_ratio():
    assert C.contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
    assert C.contrast_ratio((119, 119, 119), (255, 255, 255)) == pytest.approx(4.48, abs=0.01)
    assert C.contrast_ratio((118, 118, 118), (255, 255, 255)) == pytest.approx(4.54, abs=0.01)
    assert C.contrast_ratio((10, 10, 10), (10, 10, 10)) == pytest.approx(1.0)


def test_parse_color():
    assert C.parse_color("rgb(1, 2, 3)") == (1, 2, 3, 1.0)
    assert C.parse_color("rgba(1, 2, 3, 0.5)") == (1, 2, 3, 0.5)
    assert C.parse_color("rgb(255 0 0 / 50%)") == (255, 0, 0, 0.5)
    assert C.parse_color("#fff") == (255, 255, 255, 1.0)
    assert C.parse_color("transparent")[3] == 0
    assert C.parse_color("color(srgb 1 0 0)") == (255, 0, 0, 1.0)
    assert C.parse_color("lab(50% 10 10)") is None
    assert C.parse_color("") is None and C.parse_color(None) is None
    assert C.blend((0, 0, 0, 0.5), (255, 255, 255)) == (127.5, 127.5, 127.5)


# ---- contrast ----
def txt(color, bg="rgb(255, 255, 255)", **st):
    s = {"color": color, "backgroundColor": bg, "backgroundImage": "none", "fontSize": "16px", "fontWeight": "400"}
    s.update(st)
    return el(0, text="hello", style=s)


def test_contrast_violation_with_ratio():
    f = V.check_contrast(snap(txt("rgb(119, 119, 119)")))
    assert f[0].status == "violation" and f[0].evidence["ratio"] == 4.48


def test_contrast_pass_and_large_text():
    assert V.check_contrast(snap(txt("rgb(118, 118, 118)")))[0].status == "pass"
    grey = "rgb(140, 140, 140)"  # 約 3.4:1
    assert V.check_contrast(snap(txt(grey)))[0].status == "violation"
    assert V.check_contrast(snap(txt(grey, fontSize="24px")))[0].status == "pass"
    assert V.check_contrast(snap(txt(grey, fontSize="19px", fontWeight="700")))[0].status == "pass"


def test_contrast_cant_tell_image_gradient_overlap():
    assert V.check_contrast(snap(txt("rgb(0,0,0)", backgroundImage="url(a.png)")))[0].status == "cant_tell"
    assert V.check_contrast(snap(txt("rgb(0,0,0)", backgroundImage="linear-gradient(red, blue)")))[0].status == "cant_tell"
    assert V.check_contrast(snap(txt("rgb(0,0,0)", bg="lab(1 2 3)")))[0].status == "cant_tell"
    over = el(1, "div", style={"position": "absolute", "backgroundColor": "rgb(0,0,0)", "backgroundImage": "none"},
              bbox={"x": 0, "y": 0, "width": 50, "height": 50})
    assert V.check_contrast(snap(txt("rgb(0,0,0)"), over))[0].status == "cant_tell"


def test_contrast_ancestor_bg_and_alpha():
    parent = el(1, "div", style={"backgroundColor": "rgb(0, 0, 0)", "backgroundImage": "none"})
    child = el(2, text="x", parent=1, style={"color": "rgb(255, 255, 255)", "backgroundColor": "rgba(0, 0, 0, 0)",
                                             "backgroundImage": "none", "fontSize": "16px"})
    assert V.check_contrast(snap(parent, child))[0].status == "pass"
    # 半透明の文字色
    semi = txt("rgba(0, 0, 0, 0.4)")
    assert V.check_contrast(snap(semi))[0].status == "violation"


def test_contrast_inapplicable_cases():
    assert V.check_contrast(snap(el(0, text="", style={}))) == []
    assert V.check_contrast(snap(el(0, text="x", visible=False, style={"color": "red"}))) == []
    dis = txt("rgb(200,200,200)")
    dis["attrs"] = {"disabled": ""}
    assert V.check_contrast(snap(dis)) == []


# ---- target size ----
def tgt(i, x, y, w, h, tag="button", **kw):
    return el(i, tag, focusable=True, bbox={"x": x, "y": y, "width": w, "height": h}, **kw)


def test_target_size_cases():
    assert V.check_target_size(snap(tgt(0, 0, 0, 30, 30)))[0].status == "pass"
    assert V.check_target_size(snap(tgt(0, 0, 0, 16, 16)))[0].status == "pass"  # 周囲に他対象なし = 間隔例外
    close = snap(tgt(0, 0, 0, 16, 16), tgt(1, 18, 0, 16, 16))
    assert [f.status for f in V.check_target_size(close)] == ["violation", "violation"]
    spaced = snap(tgt(0, 0, 0, 16, 16), tgt(1, 100, 0, 16, 16))
    assert [f.status for f in V.check_target_size(spaced)] == ["pass", "pass"]
    big_near_small = snap(tgt(0, 0, 0, 16, 16), tgt(1, 18, 0, 40, 40))
    assert V.check_target_size(big_near_small)[0].status == "violation"


def test_target_size_exceptions_and_inapplicable():
    parent = el(0, "p", text="read this link here")
    link = tgt(1, 0, 0, 40, 16, "a", parent=0, style={"display": "inline"})
    link["attrs"] = {"href": "/x"}
    link2 = tgt(2, 0, 20, 40, 16, "a", style={"display": "block"})
    link2["attrs"] = {"href": "/y"}
    res = V.check_target_size(snap(parent, link, link2))
    assert res[0].status == "pass" and res[0].message.startswith("文中")
    dup_big = tgt(3, 0, 0, 40, 40, "a")
    dup_big["attrs"] = {"href": "/z"}
    dup_small = tgt(4, 0, 42, 10, 10, "a")
    dup_small["attrs"] = {"href": "/z"}
    assert V.check_target_size(snap(dup_big, dup_small))[1].message.startswith("同じ遷移先")
    assert V.check_target_size(snap(el(0, "p"))) == []
    hidden_in = tgt(0, 0, 0, 10, 10, "input")
    hidden_in["attrs"] = {"type": "hidden"}
    assert V.check_target_size(snap(hidden_in)) == []
    srcb = tgt(0, 0, 0, 1, 1)
    assert V.check_target_size(snap(srcb)) == []
    cb = tgt(0, 0, 0, 13, 13, "input", style={"appearance": "auto"})
    cb["attrs"] = {"type": "checkbox"}
    cb2 = tgt(1, 15, 0, 13, 13, "input", style={"appearance": "auto"})
    cb2["attrs"] = {"type": "checkbox"}
    assert all(f.status == "pass" for f in V.check_target_size(snap(cb, cb2)))


# ---- scroll focusable ----
def scroller(**kw):
    return el(0, "div", style={"overflowY": "auto"}, scroll={"scrollHeight": 500, "clientHeight": 100}, **kw)


def test_scroll_focusable():
    assert V.check_scroll_focusable(snap(scroller()))[0].status == "violation"
    assert V.check_scroll_focusable(snap(scroller(focusable=True)))[0].status == "pass"
    s = snap(scroller(), el(1, "a", parent=0, focusable=True))
    assert V.check_scroll_focusable(s)[0].status == "pass"
    notscroll = el(0, "div", style={"overflowY": "hidden"}, scroll={"scrollHeight": 500, "clientHeight": 100})
    assert V.check_scroll_focusable(snap(notscroll)) == []
    fits = el(0, "div", style={"overflowY": "auto"}, scroll={"scrollHeight": 100, "clientHeight": 100})
    assert V.check_scroll_focusable(snap(fits)) == []


# ---- tabindex ----
def test_tabindex():
    def t(v):
        return el(0, "div", attrs={"tabindex": v})
    assert V.check_tabindex(snap(t("3")))[0].status == "violation"
    assert V.check_tabindex(snap(t("0")))[0].status == "pass"
    assert V.check_tabindex(snap(t("-1")))[0].status == "pass"
    assert V.check_tabindex(snap(t("abc"))) == []
    assert V.check_tabindex(snap(el(0, "div"))) == []


def test_runner_all_rules():
    assert set(V.run_visual_rules(snap(el(0)))) == set(V.VISUAL_RULES)
