"""名前系ルール（E1 W2）の単体テスト。各ルール: 違反・合格・適用外・判定不能。"""
from __future__ import annotations

import pytest

from a11y_snapshot_helper import build_snapshot, mutate
from ux.a11y import rules_name as rn


def st(rule, html, **kw):
    return rule(build_snapshot(html, **kw)).status


# rule, 違反HTML, 合格HTML, 適用外HTML, 判定不能にするタグ
CASES = [
    (rn.check_image, '<img src="a.png">', '<img src="a.png" alt="ロゴ">', '<img src="a.png" alt="">', "img"),
    (rn.check_input_image, '<input type="image" src="a.png">', '<input type="image" alt="検索">', '<input type="text" aria-label="x">', "input"),
    (rn.check_form_field, '<input type="text" name="q">', '<label for="q">検索</label><input id="q" type="text">', '<input type="hidden" name="t">', "input"),
    (rn.check_select, '<select><option>1</option></select>', '<label>国<select><option>1</option></select></label>', '<div>なし</div>', "select"),
    (rn.check_button, '<button></button>', '<button>送信</button>', '<div>ボタンなし</div>', "button"),
    (rn.check_link, '<a href="/x"></a>', '<a href="/x">詳細</a>', '<a name="top">アンカー</a>', "a"),
    (rn.check_frame, '<iframe src="a.html"></iframe>', '<iframe src="a.html" title="地図"></iframe>', '<div>フレームなし</div>', "iframe"),
    (rn.check_aria_role_required, '<div role="tab"></div>', '<div role="tab">概要</div>', '<div role="note"></div>', "div"),
    (rn.check_heading, '<h2></h2>', '<h2>概要</h2>', '<p>見出しなし</p>', "h2"),
]
IDS = [c[0].__name__ for c in CASES]


@pytest.mark.parametrize("rule,bad,good,na,tagname", CASES, ids=IDS)
def test_violation(rule, bad, good, na, tagname):
    res = rule(build_snapshot(bad))
    assert res.status == "violation"
    n = [x for x in res.nodes if x.status == "violation"][0]
    assert n.selector and "accname" in n.evidence and n.impact


@pytest.mark.parametrize("rule,bad,good,na,tagname", CASES, ids=IDS)
def test_pass(rule, bad, good, na, tagname):
    assert st(rule, good) == "pass"


@pytest.mark.parametrize("rule,bad,good,na,tagname", CASES, ids=IDS)
def test_inapplicable(rule, bad, good, na, tagname):
    assert st(rule, na) == "inapplicable"


@pytest.mark.parametrize("rule,bad,good,na,tagname", CASES, ids=IDS)
def test_cant_tell_when_accname_unknown(rule, bad, good, na, tagname):
    snap = mutate(build_snapshot(bad), tagname, accname=None)
    assert rule(snap).status == "cant_tell"


@pytest.mark.parametrize("rule,bad,good,na,tagname", CASES, ids=IDS)
def test_cant_tell_when_visibility_unknown(rule, bad, good, na, tagname):
    snap = mutate(build_snapshot(bad), tagname, visible=None)
    assert rule(snap).status == "cant_tell"


@pytest.mark.parametrize("rule,bad,good,na,tagname", CASES, ids=IDS)
def test_cant_tell_when_snapshot_truncated_or_empty(rule, bad, good, na, tagname):
    snap = build_snapshot(bad)
    snap["truncated"] = True
    assert rule(snap).status == "cant_tell"
    assert rule({}).status == "cant_tell"


@pytest.mark.parametrize("rule,bad,good,na,tagname", CASES, ids=IDS)
def test_hidden_elements_are_not_judged(rule, bad, good, na, tagname):
    assert st(rule, f'<div hidden>{bad}</div>') == "inapplicable"
    assert rule(build_snapshot(f'<div aria-hidden="true">{bad}</div>')).status == "inapplicable"


# ---- ルール固有の境界
def test_image_decorative_variants_are_inapplicable():
    assert st(rn.check_image, '<img src="a.png" role="presentation">') == "inapplicable"
    assert st(rn.check_image, '<img src="a.png" role="none">') == "inapplicable"


def test_image_with_empty_alt_but_aria_label_is_not_decorative():
    assert st(rn.check_image, '<img src="a.png" alt="" aria-label="ロゴ">') == "pass"


def test_image_role_img_and_area():
    assert st(rn.check_image, '<svg role="img"></svg>') == "violation"
    assert st(rn.check_image, '<svg role="img" aria-label="グラフ"></svg>') == "pass"
    assert st(rn.check_image, '<map><area href="/a"></map>') == "violation"
    assert st(rn.check_image, '<map><area href="/a" alt="北"></map>') == "pass"


def test_form_field_placeholder_alone_is_violation():
    res = rn.check_form_field(build_snapshot('<input type="text" placeholder="氏名">'))
    assert res.status == "violation"
    assert "placeholder" in res.nodes[0].message


def test_form_field_placeholder_with_label_passes_and_disabled_is_skipped():
    assert st(rn.check_form_field, '<label>氏名<input type="text" placeholder="氏名"></label>') == "pass"
    assert st(rn.check_form_field, '<input type="text" disabled>') == "inapplicable"
    assert st(rn.check_form_field, '<textarea></textarea>') == "violation"
    assert st(rn.check_form_field, '<input type="text" aria-label="x" placeholder="x">') == "pass"


def test_button_input_submit_default_label_is_ok_but_type_button_without_value_is_not():
    assert st(rn.check_button, '<input type="submit">') == "pass"
    assert st(rn.check_button, '<input type="button">') == "violation"
    assert st(rn.check_button, '<input type="button" value="開く">') == "pass"
    assert st(rn.check_button, '<button disabled></button>') == "inapplicable"
    assert st(rn.check_button, '<div role="button"></div>') == "violation"


def test_link_image_only_uses_child_alt():
    assert st(rn.check_link, '<a href="/"><img src="a.png" alt="ホーム"></a>') == "pass"
    assert st(rn.check_link, '<a href="/"><img src="a.png" alt=""></a>') == "violation"


def test_aria_role_required_skips_native_elements():
    assert st(rn.check_aria_role_required, '<button role="menuitem"></button>') == "inapplicable"
    assert st(rn.check_aria_role_required, '<div role="progressbar" aria-labelledby="l"></div><span id="l">進捗</span>') == "pass"


def test_heading_by_role_and_whitespace_only_name():
    assert st(rn.check_heading, '<div role="heading" aria-level="2"> </div>') == "violation"
    assert st(rn.check_heading, '<h1>   </h1>') == "violation"


def test_unknown_name_is_never_pass():
    snap = mutate(build_snapshot('<button>OK</button>'), "button", accname=None)
    res = rn.check_button(snap)
    assert res.status == "cant_tell" and res.counts["pass"] == 0


def test_rules_registry_complete():
    assert set(rn.RULES) == {
        "name.image", "name.input-image", "name.form-field", "name.select", "name.button",
        "name.link", "name.frame", "name.aria-role-required", "name.heading"}
    for rid, fn in rn.RULES.items():
        assert fn(build_snapshot("<p>x</p>")).rule_id == rid
