"""snapshot.js / snapshot.py / accname の単体テスト（AC-W1-1）。ブラウザ起動不可なら実機分のみ skip。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ux.a11y.accname import compute_name, effective_role
from ux.a11y.snapshot import parse_snapshot, take_snapshot

HTML = """<!doctype html><html lang="ja"><head><title>T</title>
<meta name="viewport" content="width=device-width, initial-scale=1"></head><body>
<img id="a" src="x.png"><img id="b" alt="ロゴ" src="x.png"><img id="c" alt="" src="x.png">
<label for="n">氏名</label><input id="n" type="text">
<input id="p" type="text" placeholder="only placeholder">
<label>メール <input id="m" type="email"></label>
<button id="b1"></button><button id="b2"><span>保存</span> <b>する</b></button>
<button id="b3" aria-label="閉じる"></button>
<button id="b4"><img alt="検索" src="x.png"></button>
<span id="lb">見出し語</span><div id="dv" role="button" aria-labelledby="lb">x</div>
<a id="l1" href="/x"><svg width="10" height="10"><title>地図</title></svg></a>
<input id="sub" type="submit"><input id="hid" type="hidden">
<div id="hd" style="display:none"><a id="l2" href="/y">隠れ</a></div>
<button id="b5"><span style="display:none">非表示</span>表示</button>
<button id="b6" title="ツールチップ"></button>
<div id="ph" style="color:#777;background:#fff;font-size:20px">text</div>
<div id="sc" style="width:50px;height:20px;overflow:auto"><div style="height:200px">tall</div></div>
<div tabindex="0" id="tb"></div><p id="dup">1</p><p id="dup">2</p>
</body></html>"""


def _idx(snap, dom_id):
    return next(e.i for e in snap.elements if e.attr("id") == dom_id)


@pytest.fixture(scope="module")
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as exc:  # ブラウザ未導入、またはビルド番号違いの代替を探す
            alt = sorted(Path.home().glob(
                "Library/Caches/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell"))
            try:
                browser = pw.chromium.launch(executable_path=str(alt[-1])) if alt else None
            except Exception:
                browser = None
            if browser is None:
                pytest.skip(f"chromium を起動できない: {exc}")
        pg = browser.new_page()
        requests = []
        pg.on("request", lambda r: requests.append(r.url))
        pg.set_content(HTML)
        pg.requests = requests
        yield pg
        browser.close()


def test_deterministic_and_no_network(page):
    a, b = take_snapshot(page), take_snapshot(page)
    assert a == b
    assert all(u.endswith("x.png") for u in page.requests)  # スナップショットは外部リクエストを起こさない
    assert a.doc.lang == "ja" and a.doc.title == "T" and "width=device-width" in a.doc.viewport


def test_names(page):
    s = take_snapshot(page)
    n = lambda i: compute_name(s, _idx(s, i))
    assert n("a").name == ""
    assert n("b").name == "ロゴ" and n("c").name == ""
    assert n("n").name == "氏名" and n("n").source == "native"
    assert n("p").name == ""                       # placeholder は数えない
    assert n("m").name.startswith("メール")
    assert n("b1").name == "" and n("b2").name == "保存 する"
    assert n("b3").name == "閉じる" and n("b4").name == "検索"
    assert n("dv").name == "見出し語" and n("dv").source == "aria-labelledby"
    assert n("l1").name == "地図"
    assert n("sub").name == "Submit"
    assert n("l2").name == ""                      # 非表示配下は除外されないが親 hidden: 要素自体は rendered=False
    assert n("b5").name == "表示"
    assert n("b6").name == "ツールチップ" and n("b6").source == "title"


def test_roles_focus_style_scroll(page):
    s = take_snapshot(page)
    e = lambda i: s[_idx(s, i)]
    assert effective_role(s, e("a")) == "img" and effective_role(s, e("c")) == "presentation"
    assert effective_role(s, e("dv")) == "button" and effective_role(s, e("n")) == "textbox"
    assert e("n").focusable and e("tb").focusable and e("tb").tab_stop
    assert not e("l2").rendered and not e("l2").focusable and not e("hid").focusable
    assert e("ph").style["color"] == "rgb(119, 119, 119)"
    assert e("ph").style["backgroundColor"] == "rgb(255, 255, 255)"
    assert e("sc").scroll[2] > e("sc").scroll[3]
    assert e("a").box[2] >= 0 and e("n").selector == "#n"
    assert list(s.duplicate_ids()) == ["dup"]


def test_parse_snapshot_pure():
    raw = {"url": "u", "doc": {"title": "", "lang": None}, "elements": [
        {"i": 0, "p": -1, "tag": "html", "attrs": {}, "kids": [1]},
        {"i": 1, "p": 0, "tag": "button", "attrs": {"aria-label": " OK "}, "kids": []},
    ]}
    s = parse_snapshot(raw)
    assert compute_name(s, 1).name == "OK"
    assert s.parent(1).tag == "html" and s.aria_hidden(1) is False
