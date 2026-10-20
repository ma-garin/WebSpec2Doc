#!/usr/bin/env python3
"""A. 画面仕様・Evidence 抽出の評価。

製品が出力した report.json（解析済みサイト）を quality/commercial_eval/evidence/expected.json と照合する。
照合は「事実」単位（title・見出し・ボタン・入力項目の属性・内部リンク）。正解の定義に従い、重複は数だけ数える
（多重集合）。表・エラーメッセージ・API 通信は製品が Evidence として出していないため、別枠で未抽出として数える。
使い方: venv/bin/python scripts/commercial_eval/evidence_eval.py output/<domain>/report.json
"""
from __future__ import annotations

import json
import posixpath
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import norm_text, prf  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = ROOT / "quality" / "commercial_eval" / "evidence" / "expected.json"
ATTRS = ("type", "required", "maxlength", "minlength", "min", "max", "pattern", "label")
TYPE_ALIAS = {"select-one": "select", "select-multiple": "select"}


def _page_name(url: str) -> str:
    path = urlparse(url).path
    name = posixpath.basename(path) or "index.html"
    return name


def _val(v):
    if v in (None, "", [], False):
        return None if v is not False else False
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return norm_text(str(v))


def expected_facts(page: dict) -> Counter:
    c: Counter = Counter()
    if page.get("title"):
        c[("title", norm_text(page["title"]))] += 1
    for h in (page.get("headings") or []) + (page.get("dynamic_headings") or []):
        c[("heading", norm_text(h))] += 1
    for b in (page.get("buttons") or []) + (page.get("dynamic_buttons") or []):
        c[("button", norm_text(b))] += 1
    for f in page.get("fields") or []:
        for a in ATTRS:
            v = _val(f.get(a))
            if a == "required":
                v = bool(f.get(a))
            if v not in (None,):
                c[("field", f.get("name"), a, v if a != "type" else TYPE_ALIAS.get(v, v))] += 1
    for link in (page.get("links") or []) + (page.get("dynamic_links") or []):
        c[("link", posixpath.basename(link.split("#")[0].split("?")[0]) or "index.html")] += 1
    return c


def product_facts(screen: dict, id_to_name: dict) -> Counter:
    c: Counter = Counter()
    if screen.get("title"):
        c[("title", norm_text(screen["title"]))] += 1
    for h in screen.get("headings") or []:
        c[("heading", norm_text(h))] += 1
    for b in screen.get("buttons") or []:
        c[("button", norm_text(b))] += 1
    for form in screen.get("forms") or []:
        for f in form.get("fields") or []:
            got = {"type": f.get("field_type"), "required": bool(f.get("required")), "maxlength": f.get("maxlength"),
                   "minlength": f.get("minlength"), "min": f.get("min_value"), "max": f.get("max_value"),
                   "pattern": f.get("pattern"), "label": f.get("label_text") or f.get("aria_label")}
            for a in ATTRS:
                v = got[a] if a == "required" else _val(got[a])
                if v is not None:
                    c[("field", f.get("name"), a, v if a != "type" else TYPE_ALIAS.get(v, v))] += 1
    for pid in (screen.get("transitions") or {}).get("to") or []:
        name = id_to_name.get(pid)
        if name and name != _page_name(screen.get("url", "")):
            c[("link", name)] += 1
    return c


def evaluate(report: dict, expected: dict) -> dict:
    screens = report.get("screens") or []
    id_to_name = {s.get("page_id"): _page_name(s.get("url", "")) for s in screens}
    by_name = {_page_name(s.get("url", "")): s for s in screens}
    tot = Counter()
    per_kind: dict[str, Counter] = {}
    forbidden_hits = []
    not_extracted = Counter()
    for name, page in expected["pages"].items():
        exp = expected_facts(page)
        exp[("link", name)] = 0
        got = product_facts(by_name[name], id_to_name) if name in by_name else Counter()
        if name not in by_name:
            not_extracted["missing_page"] += 1
        for key in set(exp) | set(got):
            e, g = exp.get(key, 0), got.get(key, 0)
            tp, fp, fn = min(e, g), max(0, g - e), max(0, e - g)
            k = per_kind.setdefault(key[0], Counter())
            k.update({"tp": tp, "fp": fp, "fn": fn})
            tot.update({"tp": tp, "fp": fp, "fn": fn})
        texts = {norm_text(str(k[-1])) for k in got}
        for bad in page.get("must_not_appear") or []:
            if any(norm_text(bad) and norm_text(bad) in t for t in texts):
                forbidden_hits.append(f"{name}: {bad}")
        not_extracted["tables"] += len(page.get("tables") or [])
        not_extracted["error_messages"] += len(page.get("error_messages") or []) + len(page.get("deferred_error_messages") or [])
        not_extracted["api_endpoints"] += len(page.get("api_endpoints") or [])
    out = {"n_pages": len(expected["pages"]), "all": prf(tot["tp"], tot["fp"], tot["fn"]),
           "by_kind": {k: prf(v["tp"], v["fp"], v["fn"]) for k, v in sorted(per_kind.items())},
           "hidden_or_forbidden_extracted": forbidden_hits,
           "not_extracted_categories": dict(not_extracted)}
    return out


if __name__ == "__main__":
    rep = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(evaluate(rep, json.loads(EXPECTED.read_text(encoding="utf-8"))), ensure_ascii=False, indent=1))
