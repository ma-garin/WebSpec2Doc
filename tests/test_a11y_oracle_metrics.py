"""scripts/a11y_oracle.py の突合・指標計算（ブラウザ不要）。"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("a11y_oracle", ROOT / "scripts/a11y_oracle.py")
o = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(o)


def test_normalize_selector():
    assert o.normalize_selector("div > #v1") == "#v1"
    assert o.normalize_selector(["iframe", "main #x"]) == "#x"
    assert o.normalize_selector("HTML") == "html"
    assert o.normalize_selector("meta[name=\"viewport\"]") == "meta"
    assert o.normalize_selector("") == ""


def test_prf_and_jaccard():
    assert o.prf(3, 1, 1)["precision"] == 0.75
    assert o.prf(0, 0, 0)["recall"] is None
    assert o.jaccard({"a", "b"}, {"b", "c"}) == 1 / 3
    assert o.jaccard(set(), set()) is None


def _entry(v, severe=False):
    return {"violations": v, "severe": severe, "expect": "violation" if v else "pass"}


def test_classify_classes():
    r = o.classify_fixture(_entry(["#v1", "#v2"]), {"status": "violation", "violations": ["#v1", "#x"]})
    classes = sorted(f["class"] for f in r["failures"])
    assert classes == sorted(["誤検出", "見逃し"]) and (r["tp"], r["fp"], r["fn"]) == (1, 1, 1)
    r = o.classify_fixture(_entry(["#v1"]), None)
    assert not r["evaluated"] and r["failures"][0]["class"] == "ルール未実装"
    r = o.classify_fixture(_entry(["#v1"]), {"status": "violation", "violations": ["#v1", ""], "unmappable": 1})
    assert any(f["class"] == "対応付け不能" for f in r["failures"])
    e = _entry([]); e["expect"] = "cant_tell"
    r = o.classify_fixture(e, {"status": "pass", "violations": []})
    assert r["failures"]


def _row(rule, v, native, severe=False):
    e = _entry(v, severe)
    return {"fixture": rule, "rule": rule, "entry": e, "result": o.classify_fixture(e, native)}


def test_aggregate_and_gate():
    ok = {"status": "violation", "violations": ["#v1"]}
    rows = [_row("a", ["#v1"], ok, True), _row("b", [], {"status": "pass", "violations": []})]
    m = o.aggregate_fixture_metrics(rows)
    assert m["precision"] == 1.0 and m["recall"] == 1.0 and m["severe"]["recall"] == 1.0
    assert m["gate"] == {"precision": "PASS", "recall": "PASS", "severe_recall": "PASS"}


def test_not_evaluated_is_not_pass():
    rows = [_row("a", ["#v1"], None, True)]
    m = o.aggregate_fixture_metrics(rows)
    assert m["precision"] is None and m["gate"]["precision"] == "NOT_EVALUATED"
    assert m["gate"]["severe_recall"] == "NOT_EVALUATED"
    assert m["not_evaluated_rules"] == ["a"] and m["failure_classes"]["ルール未実装"] == 1


def test_severe_miss_fails():
    rows = [_row("a", ["#v1", "#v2"], {"status": "violation", "violations": ["#v1"]}, True)]
    m = o.aggregate_fixture_metrics(rows)
    assert m["severe"]["recall"] == 0.5 and m["gate"]["severe_recall"] == "FAIL"


def test_compare_sites():
    r = o.compare_sites({"image-alt": {"p|#a"}}, {"image-alt": {"p|#a", "p|#b"}, "bypass": {"p|html"}})
    assert r["image-alt"]["miss"] == 1 and r["image-alt"]["miss_rate"] == 0.5 and r["image-alt"]["agreement"] == 0.5
    assert r["bypass"]["class"] == "ルール未実装"


def test_native_by_axe_rule_and_markdown():
    from types import SimpleNamespace as N
    res = N(rules=[N(rule_id="name.image", status="violation", nodes=[N(status="violation", selector="img#v1"), N(status="pass", selector="img")])])
    d = o.native_by_axe_rule(res, o.DEFAULT_NATIVE_TO_AXE)
    assert d["image-alt"]["violations"] == ["img#v1"]
    m = o.aggregate_fixture_metrics([_row("image-alt", ["#v1"], d["image-alt"], True)])
    assert "Precision" in o.render_markdown({"fixtures": m, "failures": []})


def test_manifest_consistent():
    man = json.loads((ROOT / "tests/a11y_oracle/manifest.json").read_text(encoding="utf-8"))
    for rel, e in man["fixtures"].items():
        assert (ROOT / "tests/a11y_oracle/fixtures" / rel).is_file()
        if e["severe"]:
            assert e["violations"] and e["level"] in ("A", "AA")
    assert any(e["severe"] for e in man["fixtures"].values())
