"""ARIA ルール（rules_aria）の単体テスト。各ルール: 違反・合格・判定不能/適用外。"""
from ux.a11y import rules_aria as R


def mk(snaps):
    """snaps: (tag, attrs, role, parent_index|None, extra) のリスト → snapshot。"""
    els = []
    for i, (tag, attrs, role, parent, extra) in enumerate(snaps):
        e = {"id": i, "selector": f"{tag}#{i}", "tag": tag, "attrs": attrs, "role": role,
             "visible": True, "focusable": False, "bbox": {"x": 0, "y": 0, "width": 10, "height": 10},
             "parent": parent, "children": []}
        e.update(extra or {})
        els.append(e)
    for e in els:
        if e["parent"] is not None:
            els[e["parent"]]["children"].append(e["id"])
    return {"elements": els}


def statuses(fn, snap):
    return [f.status for f in fn(snap)]


def test_roles():
    s = mk([("div", {"role": "bogus"}, None, None, None), ("div", {"role": "button"}, "button", None, None),
            ("div", {"role": "widget"}, None, None, None), ("div", {"role": "foo button"}, "button", None, None)])
    assert statuses(R.check_roles, s) == ["violation", "pass", "violation", "pass"]
    assert R.check_roles(mk([("div", {}, None, None, None)])) == []


def test_valid_attr():
    s = mk([("div", {"aria-foo": "x"}, None, None, None), ("div", {"aria-label": "x"}, None, None, None)])
    assert statuses(R.check_valid_attr, s) == ["violation", "pass"]
    assert R.check_valid_attr(mk([("p", {"class": "a"}, None, None, None)])) == []


def test_valid_attr_value():
    s = mk([("div", {"aria-hidden": "yes"}, None, None, None),
            ("div", {"aria-level": "2"}, None, None, None),
            ("div", {"aria-labelledby": "nope"}, None, None, None),
            ("div", {"aria-valuenow": "abc"}, None, None, None),
            ("div", {"id": "t", "aria-describedby": "t"}, None, None, None)])
    assert statuses(R.check_valid_attr_value, s) == ["violation", "pass", "cant_tell", "violation", "pass"]
    assert R.check_valid_attr_value(mk([("p", {}, None, None, None)])) == []


def test_required_attr():
    s = mk([("div", {"role": "checkbox"}, "checkbox", None, None),
            ("div", {"role": "checkbox", "aria-checked": "false"}, "checkbox", None, None),
            ("input", {"role": "checkbox", "type": "checkbox"}, "checkbox", None, None),
            ("div", {"role": "heading"}, "heading", None, None),
            ("h2", {"role": "heading"}, "heading", None, None),
            ("div", {"role": "combobox", "aria-expanded": "true"}, "combobox", None, None),
            ("div", {"role": "slider"}, "slider", None, None)])
    got = statuses(R.check_required_attr, s)
    assert got == ["violation", "pass", "violation", "violation", "violation"]  # 入力 checkbox / h2 は対象外
    assert R.check_required_attr(mk([("div", {"role": "button"}, "button", None, None)])) == []


def test_allowed_attr():
    s = mk([("div", {"aria-checked": "true"}, "generic", None, None),
            ("div", {"role": "button", "aria-pressed": "true"}, "button", None, None),
            ("div", {"role": "doc-chapter", "aria-checked": "true"}, "doc-chapter", None, None),
            ("div", {"role": "link", "aria-valuenow": "3"}, "link", None, None)])
    assert statuses(R.check_allowed_attr, s) == ["violation", "pass", "violation"]
    assert R.check_allowed_attr(mk([("p", {}, None, None, None)])) == []


def test_prohibited_attr():
    s = mk([("div", {"role": "presentation", "aria-label": "x"}, "presentation", None, None),
            ("div", {"role": "button", "aria-label": "x"}, "button", None, None),
            ("div", {"aria-label": "x"}, "generic", None, None)])
    assert statuses(R.check_prohibited_attr, s) == ["violation", "pass", "violation"]
    assert R.check_prohibited_attr(mk([("div", {"role": "none"}, "none", None, None)])) == []


def test_required_children():
    ok = mk([("div", {"role": "list"}, "list", None, None), ("div", {}, "generic", 0, None),
             ("div", {"role": "listitem"}, "listitem", 1, None)])
    assert statuses(R.check_required_children, ok) == ["pass"]
    bad = mk([("div", {"role": "tablist"}, "tablist", None, None), ("button", {}, "button", 0, None)])
    assert statuses(R.check_required_children, bad) == ["violation"]
    empty = mk([("div", {"role": "listbox"}, "listbox", None, None)])
    assert statuses(R.check_required_children, empty) == ["violation"]
    owns = mk([("div", {"role": "menu", "aria-owns": "x"}, "menu", None, None), ("div", {}, "generic", 0, None)])
    assert statuses(R.check_required_children, owns) == ["cant_tell"]
    assert R.check_required_children(mk([("div", {}, None, None, None)])) == []


def test_required_children_group_and_rowgroup():
    t = mk([("div", {"role": "table"}, "table", None, None), ("div", {"role": "rowgroup"}, "rowgroup", 0, None),
            ("div", {"role": "row"}, "row", 1, None)])
    assert statuses(R.check_required_children, t)[0] == "pass"


def test_required_parent():
    ok = mk([("ul", {}, "list", None, None), ("div", {"role": "listitem"}, "listitem", 0, None)])
    assert statuses(R.check_required_parent, ok) == ["pass"]
    bad = mk([("div", {}, "generic", None, None), ("div", {"role": "listitem"}, "listitem", 0, None)])
    assert statuses(R.check_required_parent, bad) == ["violation"]
    wrong = mk([("div", {"role": "button"}, "button", None, None), ("div", {"role": "tab"}, "tab", 0, None)])
    assert statuses(R.check_required_parent, wrong) == ["violation"]
    owned = mk([("div", {"id": "x", "role": "tab"}, "tab", None, None),
                ("div", {"role": "tablist", "aria-owns": "x"}, "tablist", None, None)])
    assert "cant_tell" in statuses(R.check_required_parent, owned)
    assert R.check_required_parent(mk([("div", {}, None, None, None)])) == []


def test_hidden_body():
    assert statuses(R.check_hidden_body, mk([("body", {"aria-hidden": "true"}, None, None, None)])) == ["violation"]
    assert statuses(R.check_hidden_body, mk([("body", {}, None, None, None)])) == ["pass"]
    assert R.check_hidden_body(mk([("div", {}, None, None, None)])) == []


def test_hidden_focus():
    bad = mk([("div", {"aria-hidden": "true"}, None, None, None),
              ("button", {}, "button", 0, {"focusable": True})])
    assert statuses(R.check_hidden_focus, bad) == ["violation"]
    ok = mk([("div", {"aria-hidden": "true"}, None, None, None),
             ("button", {"tabindex": "-1"}, "button", 0, {"focusable": True}),
             ("button", {"disabled": ""}, "button", 0, {"focusable": True})])
    assert statuses(R.check_hidden_focus, ok) == ["pass"]
    assert R.check_hidden_focus(mk([("div", {}, None, None, None)])) == []


def test_nested_interactive():
    bad = mk([("div", {"role": "button"}, "button", None, None), ("a", {"href": "#"}, "link", 0, {"focusable": True})])
    assert statuses(R.check_nested_interactive, bad) == ["violation"]
    ok = mk([("button", {}, "button", None, None), ("span", {}, None, 0, None)])
    assert statuses(R.check_nested_interactive, ok) == ["pass"]
    unsure = mk([("button", {}, "button", None, None), ("a", {"tabindex": "-1"}, "link", 0, {"focusable": True})])
    assert statuses(R.check_nested_interactive, unsure) == ["cant_tell"]
    assert R.check_nested_interactive(mk([("div", {}, None, None, None)])) == []


def test_invisible_ignored_and_runner():
    s = mk([("div", {"role": "bogus"}, None, None, {"visible": False})])
    assert R.check_roles(s) == []
    res = R.run_aria_rules(s)
    assert set(res) == set(R.ARIA_RULES) and len(res) == 11


def test_implicit_generic_name_prohibition_and_explicit_role_override():
    s = mk([("span", {"aria-labelledby": "label"}, "generic", None, None),
            ("div", {"role": "group", "aria-label": "group"}, "group", None, None),
            ("div", {"aria-label": ""}, "generic", None, None)])
    assert statuses(R.check_prohibited_attr, s) == ["violation", "pass"]


def test_empty_required_children_requires_explicit_loading_evidence():
    for role in ("list", "grid", "menu", "tablist"):
        empty = mk([("div", {"role": role}, role, None, None)])
        assert statuses(R.check_required_children, empty) == ["violation"]
        busy = mk([("div", {"role": role, "aria-busy": "true"}, role, None, None)])
        assert statuses(R.check_required_children, busy) == ["cant_tell"]
