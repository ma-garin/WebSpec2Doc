"""文書/メタ/構造系ルール（E1 W3）の単体テスト。各ルール: 違反・合格・適用外・判定不能。"""
from __future__ import annotations

import copy

import pytest

from a11y_snapshot_helper import build_snapshot, mutate
from ux.a11y import rules_document as rd
from ux.a11y.data.lang_autocomplete import validate_autocomplete, validate_lang


def snap(body="<p>x</p>", head="", lang="en", title="T"):
    la = f' lang="{lang}"' if lang is not None else ""
    return build_snapshot(f"<html{la}><head><title>{title}</title>{head}</head><body>{body}</body></html>")


def st(rule, **kw):
    return rule(snap(**kw)).status


# ---------------- doc.title
def test_title():
    assert st(rd.check_title, title="") == "violation"
    assert st(rd.check_title, title="  ") == "violation"
    assert st(rd.check_title, title="首页") == "pass"
    s = snap(); s["title"] = None
    assert rd.check_title(s).status == "cant_tell"
    assert rd.check_title({}).status == "cant_tell"


# ---------------- doc.lang-present / lang-valid
def test_lang_present():
    assert st(rd.check_lang_present, lang=None) == "violation"
    assert st(rd.check_lang_present, lang="") == "violation"
    assert st(rd.check_lang_present, lang="ja") == "pass"
    assert rd.check_lang_present({"elements": [{"tag": "body", "attrs": {}}]}).status == "cant_tell"


def test_lang_valid():
    assert st(rd.check_lang_valid, lang="xx-invalid") == "violation"
    assert st(rd.check_lang_valid, lang="en_US") == "violation"
    assert st(rd.check_lang_valid, lang="ja") == "pass"
    assert st(rd.check_lang_valid, lang="ja-JP") == "pass"
    assert st(rd.check_lang_valid, lang="zh-Hans-CN") == "pass"
    assert st(rd.check_lang_valid, lang=None) == "inapplicable"   # 欠落は lang-present が扱う
    assert st(rd.check_lang_valid, lang="") == "inapplicable"
    # 部分登録簿で確認できないものは違反にも合格にもしない
    assert st(rd.check_lang_valid, lang="tlh") == "cant_tell"
    assert st(rd.check_lang_valid, lang="en-ZZ") == "cant_tell"


def test_lang_valid_registry_unavailable_is_cant_tell():
    s = snap(lang="en")
    assert rd.check_lang_valid(s, registry=None).status == "cant_tell"
    assert rd.check_lang_valid(s, registry={}).status == "cant_tell"


def test_validate_lang_direct():
    assert validate_lang("i-klingon")[0] == "valid"
    assert validate_lang("x-private")[0] == "valid"
    assert validate_lang("en-")[0] == "invalid"
    assert validate_lang("e")[0] == "invalid"
    assert validate_lang("ja-u-ca-japanese")[0] == "valid"
    assert validate_lang("zh-yue-HK")[0] == "valid"


# ---------------- doc.viewport-zoom
@pytest.mark.parametrize("content,expected", [
    ("width=device-width, user-scalable=no", "violation"),
    ("width=device-width, user-scalable=0", "violation"),
    ("width=device-width, maximum-scale=1.0", "violation"),
    ("width=device-width,maximum-scale=1", "violation"),
    ("width=device-width, initial-scale=1", "pass"),
    ("width=device-width, user-scalable=yes, maximum-scale=5", "pass"),
    ("width=device-width, maximum-scale=2", "pass"),
    ("width=device-width, user-scalable = no", "violation"),
    ("width=device-width, maximum-scale=abc", "cant_tell"),
    ("width=device-width, user-scalable=maybe", "cant_tell"),
])
def test_viewport(content, expected):
    head = f'<meta name="viewport" content="{content}">'
    assert st(rd.check_viewport_zoom, head=head) == expected


def test_viewport_absent_is_inapplicable_and_last_meta_wins():
    assert st(rd.check_viewport_zoom) == "inapplicable"
    head = '<meta name="viewport" content="user-scalable=no"><meta name="viewport" content="width=device-width">'
    assert st(rd.check_viewport_zoom, head=head) == "pass"
    assert rd.check_viewport_zoom({}).status == "cant_tell"


# ---------------- doc.bypass
def test_bypass():
    assert st(rd.check_bypass, body='<a href="#main">本文へ</a><div id="main">x</div>') == "pass"
    assert st(rd.check_bypass, body="<main>本文</main>") == "pass"
    assert st(rd.check_bypass, body="<p>のみ</p>") == "violation"
    assert st(rd.check_bypass, body="<h1>見出し</h1><p>x</p>") == "cant_tell"
    # 宛先が存在しないスキップリンクは数えない
    assert st(rd.check_bypass, body='<a href="#nowhere">skip</a><p>x</p>') == "violation"
    assert rd.check_bypass({}).status == "cant_tell"


# ---------------- doc.duplicate-id-aria
def test_duplicate_id_aria():
    bad = '<span id="l">a</span><span id="l">b</span><input aria-labelledby="l">'
    res = rd.check_duplicate_id_aria(snap(body=bad))
    assert res.status == "violation" and res.counts["violation"] == 2
    assert st(rd.check_duplicate_id_aria, body='<span id="l">a</span><input aria-labelledby="l">') == "pass"
    # ARIA から参照されない重複 id は対象外
    assert st(rd.check_duplicate_id_aria, body='<p id="d">a</p><p id="d">b</p>') == "inapplicable"
    s = snap(body=bad); s["truncated"] = True
    assert rd.check_duplicate_id_aria(s).status == "cant_tell"


# ---------------- struct.list / listitem
def test_list():
    assert st(rd.check_list, body="<ul><li>a</li><li>b</li></ul>") == "pass"
    assert st(rd.check_list, body="<ul><li>a</li><div>x</div></ul>") == "violation"
    assert st(rd.check_list, body="<ol><script></script><li>a</li></ol>") == "pass"
    assert st(rd.check_list, body='<ul role="menu"><div>x</div></ul>') == "inapplicable"
    assert st(rd.check_list, body="<p>no list</p>") == "inapplicable"
    assert rd.check_list({}).status == "cant_tell"


def test_listitem():
    assert st(rd.check_listitem, body="<ul><li>a</li></ul>") == "pass"
    assert st(rd.check_listitem, body="<div><li>a</li></div>") == "violation"
    assert st(rd.check_listitem, body='<div role="list"><li>a</li></div>') == "pass"
    assert st(rd.check_listitem, body='<ul role="presentation"><li>a</li></ul>') == "cant_tell"
    s = mutate(snap(body="<div><li>a</li></div>"), "li", parent=None)
    assert rd.check_listitem(s).status == "cant_tell"
    assert st(rd.check_listitem, body="<p>no</p>") == "inapplicable"


# ---------------- form.autocomplete
@pytest.mark.parametrize("val,expected", [
    ("email", "pass"), ("given-name", "pass"), ("off", "pass"), ("on", "pass"),
    ("shipping postal-code", "pass"), ("section-a billing cc-number", "pass"),
    ("home tel", "pass"), ("work email webauthn", "pass"),
    ("emial", "violation"), ("nope", "violation"), ("name email", "violation"),
    ("home name", "violation"), ("off email", "violation"), ("section- email", "violation"),
])
def test_autocomplete_values(val, expected):
    assert st(rd.check_autocomplete, body=f'<input type="text" autocomplete="{val}">') == expected


def test_autocomplete_applicability_and_unknown():
    assert st(rd.check_autocomplete, body='<input type="text">') == "inapplicable"
    assert st(rd.check_autocomplete, body='<input type="checkbox" autocomplete="bogus">') == "inapplicable"
    assert st(rd.check_autocomplete, body='<input type="text" autocomplete="bogus" disabled>') == "inapplicable"
    assert st(rd.check_autocomplete, body='<input type="text" autocomplete="bogus" hidden>') == "inapplicable"
    assert st(rd.check_autocomplete, body='<textarea autocomplete="bogus"></textarea>') == "violation"
    s = mutate(snap(body='<input type="text" autocomplete="email">'), "input", visible=None)
    assert rd.check_autocomplete(s).status == "cant_tell"
    assert validate_autocomplete("")[0] is False


# ---------------- bp.*
def test_heading_order():
    assert st(rd.check_heading_order, body="<h1>a</h1><h2>b</h2><h3>c</h3><h2>d</h2>") == "pass"
    res = rd.check_heading_order(snap(body="<h1>a</h1><h3>c</h3>"))
    assert res.status == "violation" and res.counts["violation"] == 1
    assert st(rd.check_heading_order, body="<p>none</p>") == "inapplicable"
    assert st(rd.check_heading_order, body='<h1>a</h1><div role="heading" aria-level="x">b</div>') == "cant_tell"
    assert st(rd.check_heading_order, body="<h1>a</h1><h3 hidden>c</h3>") == "pass"  # 非表示は数えない


def test_page_has_h1():
    assert st(rd.check_page_has_h1, body="<h1>a</h1>") == "pass"
    assert st(rd.check_page_has_h1, body='<div role="heading" aria-level="1">a</div>') == "pass"
    assert st(rd.check_page_has_h1, body="<h2>a</h2>") == "violation"
    assert st(rd.check_page_has_h1, body="<h1 hidden>a</h1>") == "violation"
    s = mutate(snap(body="<h1>a</h1>"), "h1", visible=None)
    assert rd.check_page_has_h1(s).status == "cant_tell"


def test_landmark_main_rules():
    assert st(rd.check_landmark_one_main, body="<main>x</main>") == "pass"
    assert st(rd.check_landmark_one_main, body="<p>x</p>") == "violation"
    assert st(rd.check_landmark_one_main, body='<div role="main">x</div>') == "pass"
    assert st(rd.check_landmark_no_dup_main, body="<main>a</main><main>b</main>") == "violation"
    assert st(rd.check_landmark_no_dup_main, body="<main>a</main>") == "pass"
    assert st(rd.check_landmark_no_dup_main, body="<p>x</p>") == "inapplicable"
    assert st(rd.check_landmark_main_top, body="<nav><main>a</main></nav>") == "violation"
    assert st(rd.check_landmark_main_top, body="<main>a</main>") == "pass"
    s = mutate(snap(body="<main>a</main>"), "main", visible=None)
    assert rd.check_landmark_one_main(s).status == "cant_tell"


def test_landmark_banner_contentinfo():
    assert st(rd.check_landmark_no_dup_banner, body="<header>a</header><header>b</header>") == "violation"
    # article 内の header/footer はランドマークではない
    assert st(rd.check_landmark_no_dup_banner, body="<header>a</header><article><header>b</header></article>") == "pass"
    assert st(rd.check_landmark_no_dup_contentinfo, body="<footer>a</footer><footer>b</footer>") == "violation"
    assert st(rd.check_landmark_banner_top, body="<main><div role='banner'>a</div></main>") == "violation"
    assert st(rd.check_landmark_banner_top, body="<header>a</header>") == "pass"
    assert st(rd.check_landmark_contentinfo_top, body="<aside><footer role='contentinfo'>a</footer></aside>") == "violation"
    assert st(rd.check_landmark_contentinfo_top, body="<footer>a</footer>") == "pass"


def test_landmark_unique():
    two = '<nav aria-label="主">a</nav><nav aria-label="主">b</nav>'
    assert st(rd.check_landmark_unique, body=two) == "violation"
    ok = '<nav aria-label="主">a</nav><nav aria-label="補助">b</nav>'
    assert st(rd.check_landmark_unique, body=ok) == "pass"
    assert st(rd.check_landmark_unique, body="<p>x</p>") == "inapplicable"
    s = mutate(snap(body=ok), "nav", accname=None)
    assert rd.check_landmark_unique(s).status == "cant_tell"


def test_every_rule_returns_cant_tell_on_garbage_and_never_pass():
    for rid, fn in rd.RULES.items():
        for bad in ({}, {"elements": None}, {"elements": "x"}, None):
            r = fn(bad)
            assert r.rule_id == rid and r.status == "cant_tell" and r.counts["pass"] == 0


def test_rules_do_not_mutate_snapshot():
    s = snap(body='<ul><li>a</li></ul><input autocomplete="email"><h1>x</h1><main>m</main>')
    before = copy.deepcopy(s)
    for fn in rd.RULES.values():
        fn(s)
    assert s == before
