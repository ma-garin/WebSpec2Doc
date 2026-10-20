#!/usr/bin/env python3
"""影響度分析の精度を測る（DD-011）。

tests/fixtures/impact_eval/ の文書と cases.json（変更 20 件・正解の影響つき）を一時 DB に入れて
各ケースを分析し、再現率・適合率・候補率（影響件数 / 項目数）を JSON で出す。
  --mode rule  外部送信なし（つながり・語の一致・文字 n-gram）
  --mode full  LLM と埋め込みを使う（接続先が無ければ rule と同じ結果になる）
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from web.services.impact.engine import run  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "impact_eval"
_LINE = re.compile(r"^([A-Z]{2,5}-\d{3,4})\s+(.+)$")


def _id() -> str:
    return uuid.uuid4().hex[:12]


def parse_doc(path: Path) -> list[dict]:
    """「## 見出し」と「CODE 本文」の行から項目を作る。"""
    out, section = [], ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        m = _LINE.match(line.strip())
        if m:
            out.append({"code": m.group(1), "text": m.group(2), "section": section,
                        "location": section, "ord": len(out) + 1})
    return out


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript((FIXTURES / "schema.sql").read_text(encoding="utf-8"))
    return conn


def build(conn, spec: dict, policy: str) -> tuple[str, dict]:
    """対象システム・文書・項目・つながりを入れる。戻り値は (sid, code→item)。"""
    sid = _id()
    conn.execute("INSERT INTO systems(id, name, policy) VALUES(?,?,?)", (sid, "評価", policy))
    by_code: dict[str, dict] = {}
    for d in spec["documents"]:
        if d.get("old_version_of"):
            continue
        did = _id()
        items = parse_doc(FIXTURES / d["file"])
        conn.execute("INSERT INTO documents(id, system_id, name, kind, item_count) VALUES(?,?,?,?,?)",
                     (did, sid, d["file"], d["kind"], len(items)))
        for it in items:
            iid = _id()
            conn.execute("INSERT INTO items(id, system_id, document_id, code, text, location, section, ord)"
                         " VALUES(?,?,?,?,?,?,?,?)",
                         (iid, sid, did, it["code"], it["text"], it["location"], it["section"], it["ord"]))
            by_code[it["code"]] = {**it, "id": iid, "document_name": d["file"], "kind": d["kind"]}
    for a, b in spec["links"]:
        x, y = sorted((by_code[a]["id"], by_code[b]["id"]))
        conn.execute("INSERT INTO links(id, system_id, a_item, b_item, origin) VALUES(?,?,?,?,'manual')", (_id(), sid, x, y))
    conn.commit()
    return sid, by_code


def _baseline(conn, sid: str, name: str, items: list[dict]) -> str:
    bid = _id()
    conn.execute("INSERT INTO baselines(id, system_id, name) VALUES(?,?,?)", (bid, sid, name))
    for it in items:
        conn.execute("INSERT INTO baseline_items(baseline_id, item_id, document_name, kind, code, text, location, section, ord)"
                     " VALUES(?,?,?,?,?,?,?,?,?)", (bid, it["id"], it["document_name"], it["kind"], it["code"],
                                                  it["text"], it["location"], it["section"], it["ord"]))
    return bid


def add_case(conn, sid: str, by_code: dict, n: int, case: dict) -> str:
    code = f"CR-{n:03d}"
    base = target = None
    if case.get("baseline_pair"):
        old = {it["code"]: it for it in parse_doc(FIXTURES / case["baseline_pair"]["old"])}
        current = list(by_code.values())
        base = _baseline(conn, sid, f"{code}-old", [{**it, "text": old[it["code"]]["text"]}
                                                    if it["document_name"] == case["baseline_pair"]["new"] and it["code"] in old
                                                    else it for it in current])
        target = _baseline(conn, sid, f"{code}-new", current)
    conn.execute("INSERT INTO change_requests(id, system_id, code, title, status, base_baseline, target_baseline, change_text)"
                 " VALUES(?,?,?,?,?,?,?,?)", (_id(), sid, code, case["title"], "draft", base, target, case.get("change_text", "")))
    conn.commit()
    return code


def evaluate(mode: str) -> dict:
    spec = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
    policy = "none" if mode == "rule" else "external"
    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(Path(tmp) / "eval.db")
        sid, by_code = build(conn, spec, policy)
        total_items = len(by_code)
        tp = found_n = exp_n = 0
        per_case, engine = [], None
        for n, case in enumerate(spec["cases"], start=1):
            code = add_case(conn, sid, by_code, n, case)
            res = run.analyze(conn, sid, code, "eval", allow_send=(mode == "full"))
            engine = res["engine"]
            cr_id = conn.execute("SELECT id FROM change_requests WHERE system_id=? AND code=?", (sid, code)).fetchone()[0]
            found = {r[0] for r in conn.execute("SELECT item_code FROM impacts WHERE cr_id=?", (cr_id,))}
            expected = set(case["expected_items"])
            hit = found & expected
            tp, found_n, exp_n = tp + len(hit), found_n + len(found), exp_n + len(expected)
            per_case.append({"title": case["title"], "recall": round(len(hit) / len(expected), 3),
                             "precision": round(len(hit) / len(found), 3) if found else 0.0,
                             "found": len(found), "missed": sorted(expected - found),
                             "extra": sorted(found - expected)})
        conn.close()
    return {"mode": mode, "engine_mode": engine["mode"] if engine else None, "cases": len(per_case), "items": total_items,
            "recall": round(tp / exp_n, 3) if exp_n else 0.0, "precision": round(tp / found_n, 3) if found_n else 0.0,
            "candidate_rate": round(found_n / (len(per_case) * total_items), 3) if per_case else 0.0, "per_case": per_case}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=("rule", "full"), default="rule")
    ap.add_argument("--summary", action="store_true", help="ケース別の内訳を出さない")
    args = ap.parse_args(argv)
    out = evaluate(args.mode)
    if args.summary:
        out.pop("per_case")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
