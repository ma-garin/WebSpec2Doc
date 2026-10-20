#!/usr/bin/env python3
"""Native a11y 検査と axe-core の突合（開発時専用。製品の runtime から呼ばない）。

使い方:
  python scripts/a11y_oracle.py --fixtures [--sites demo/site --url URL ...] [--out DIR]

終了コード: 0=完了 / 2=axe 未取得（オラクル未取得）/ 3=Native 未統合 / 4=ブラウザ無し
指標の正解は tests/a11y_oracle/manifest.json（人が付けた期待）。axe の出力は正解にしない。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AXE = ROOT / "tools/a11y-oracle/node_modules/axe-core/axe.min.js"
MANIFEST = ROOT / "tests/a11y_oracle/manifest.json"
FIXTURES = ROOT / "tests/a11y_oracle/fixtures"

# 比較指標のしきい値（保守者確定）
GATE_PRECISION, GATE_RECALL, GATE_SEVERE_RECALL = 0.95, 0.90, 1.00

CLASSES = ("見逃し", "誤検出", "ルール未実装", "対応付け不能")


# ---------------------------------------------------------------- 純粋関数（ブラウザ不要）
def normalize_selector(sel) -> str:
    """要素の突合キー。末尾の複合セレクタの #id、無ければそのタグ名。空は ''。"""
    if isinstance(sel, (list, tuple)):
        sel = sel[-1] if sel else ""
    s = re.sub(r"\s+", " ", str(sel or "")).strip()
    if not s:
        return ""
    last = re.split(r"\s*[>+~ ]\s*", s)[-1]
    m = re.search(r"#([A-Za-z_][\w-]*)", last)
    if m:
        return "#" + m.group(1)
    m = re.match(r"[A-Za-z][\w-]*", last)
    return m.group(0).lower() if m else ""


def keys(nodes) -> set[str]:
    return {k for k in (normalize_selector(n) for n in nodes) if k}


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r}


def jaccard(a: set, b: set) -> float | None:
    u = a | b
    return len(a & b) / len(u) if u else None


def classify_fixture(entry: dict, native: dict | None) -> dict:
    """1 fixture × 1 ルールの Native 結果を正解と照合する。
    native: {"status": str, "violations": [selector...], "unmappable": int} / None=ルール未実装。"""
    exp = {k for k in (normalize_selector(v) for v in entry.get("violations", [])) if k}
    if native is None or native.get("status") == "not_implemented":
        return {"evaluated": False, "failures": [{"class": "ルール未実装", "key": k} for k in sorted(exp)],
                "tp": 0, "fp": 0, "fn": 0, "status": "not_implemented"}
    got = keys(native.get("violations", []))
    failures = [{"class": "見逃し", "key": k} for k in sorted(exp - got)]
    failures += [{"class": "誤検出", "key": k} for k in sorted(got - exp)]
    failures += [{"class": "対応付け不能", "key": "?"}] * int(native.get("unmappable", 0))
    # 期待が pass/inapplicable/cant_tell のページでステータスが食い違えば記録
    if entry.get("expect") == "cant_tell" and native.get("status") == "pass":
        failures.append({"class": "見逃し", "key": "cant_tell を pass と断定"})
    return {"evaluated": True, "failures": failures, "tp": len(exp & got), "fp": len(got - exp),
            "fn": len(exp - got), "status": native.get("status")}


def aggregate_fixture_metrics(rows: list[dict]) -> dict:
    """rows: {fixture, rule(axe), severe, entry, result(classify_fixture), axe_keys}。"""
    tp = sum(r["result"]["tp"] for r in rows)
    fp = sum(r["result"]["fp"] for r in rows)
    fn = sum(r["result"]["fn"] for r in rows)
    sev = [r for r in rows if r["entry"].get("severe")]
    sev_eval = [r for r in sev if r["result"]["evaluated"]]
    s_tp = sum(r["result"]["tp"] for r in sev_eval)
    s_fn = sum(r["result"]["fn"] for r in sev_eval)
    not_eval = [r for r in rows if not r["result"]["evaluated"]]
    out = prf(tp, fp, fn)
    out["severe"] = {"fixtures": len(sev), "evaluated": len(sev_eval), "not_evaluated": len(sev) - len(sev_eval),
                     "recall": s_tp / (s_tp + s_fn) if s_tp + s_fn else None, "tp": s_tp, "fn": s_fn}
    out["not_evaluated_fixtures"] = len(not_eval)
    out["not_evaluated_rules"] = sorted({r["rule"] for r in not_eval})
    out["failure_classes"] = {c: sum(1 for r in rows for f in r["result"]["failures"] if f["class"] == c) for c in CLASSES}
    out["gate"] = judge_gate(out)
    return out


def judge_gate(m: dict) -> dict:
    """未評価（NOT_EVALUATED）は PASS に数えない。評価対象が 0 なら NOT_EVALUATED。"""
    def j(v, th):
        return "NOT_EVALUATED" if v is None else ("PASS" if v >= th else "FAIL")
    sev = m["severe"]
    sev_v = j(sev["recall"], GATE_SEVERE_RECALL)
    if sev["not_evaluated"]:
        sev_v = "FAIL" if sev_v == "FAIL" else "NOT_EVALUATED"
    return {"precision": j(m["precision"], GATE_PRECISION), "recall": j(m["recall"], GATE_RECALL),
            "severe_recall": sev_v}


def compare_sites(native_by_axe: dict[str, set], axe_by_rule: dict[str, set]) -> dict:
    """正解の無い実サイト: 旧 axe id 単位で Native と axe の違反ノード集合を比較する。"""
    per = {}
    for rule in sorted(set(native_by_axe) | set(axe_by_rule)):
        n, a = native_by_axe.get(rule), axe_by_rule.get(rule, set())
        if n is None:
            per[rule] = {"class": "ルール未実装", "axe": len(a), "native": None, "miss": len(a), "extra": 0,
                         "agreement": None, "miss_rate": 1.0 if a else None}
            continue
        miss, extra = a - n, n - a
        per[rule] = {"class": "", "axe": len(a), "native": len(n), "miss": len(miss), "extra": len(extra),
                     "agreement": jaccard(n, a), "miss_rate": len(miss) / len(a) if a else None,
                     "miss_keys": sorted(miss), "extra_keys": sorted(extra)}
    return per


def render_markdown(report: dict) -> str:
    L = ["# a11y オラクル比較", ""]
    L.append("- Native: %s / axe: %s / ブラウザ: %s" % (report.get("native_version", "-"), report.get("axe_version", "-"), report.get("browser", "-")))
    fx = report.get("fixtures")
    if fx:
        g, s = fx["gate"], fx["severe"]
        fmt = lambda v: "n/a" if v is None else "%.3f" % v
        L += ["", "## Fixture（正解は manifest）", "",
              "| 指標 | 値 | 基準 | 判定 |", "|---|---|---|---|",
              "| Precision | %s | ≥%.2f | %s |" % (fmt(fx["precision"]), GATE_PRECISION, g["precision"]),
              "| Recall | %s | ≥%.2f | %s |" % (fmt(fx["recall"]), GATE_RECALL, g["recall"]),
              "| 重大 A/AA Recall | %s | =%.2f | %s |" % (fmt(s["recall"]), GATE_SEVERE_RECALL, g["severe_recall"]),
              "", "- 重大 fixture: %d 件（評価 %d / NOT_EVALUATED %d）" % (s["fixtures"], s["evaluated"], s["not_evaluated"]),
              "- NOT_EVALUATED fixture: %d 件（PASS に数えない）" % fx["not_evaluated_fixtures"],
              "- 失敗分類: " + " / ".join("%s %d" % (c, fx["failure_classes"][c]) for c in CLASSES)]
        if fx["not_evaluated_rules"]:
            L.append("- 未評価ルール: " + ", ".join(fx["not_evaluated_rules"]))
        if report.get("axe_vs_truth"):
            a = report["axe_vs_truth"]
            L.append("- 参考 axe 対正解: Precision %s / Recall %s" % (fmt(a["precision"]), fmt(a["recall"])))
        bad = [f for f in report.get("failures", [])]
        if bad:
            L += ["", "### 失敗一覧", "", "| fixture | 分類 | 要素 |", "|---|---|---|"]
            L += ["| %s | %s | %s |" % (f["fixture"], f["class"], f["key"]) for f in bad[:200]]
    st = report.get("sites")
    if st:
        L += ["", "## 実サイト（正解なし。Native と axe の差）", "",
              "| 旧 axe id | axe | Native | 見逃し | 一致率 |", "|---|---|---|---|---|"]
        for rule, r in st["rules"].items():
            ag = "-" if r["agreement"] is None else "%.2f" % r["agreement"]
            L.append("| %s | %d | %s | %d | %s |" % (rule, r["axe"], "未実装" if r["native"] is None else r["native"], r["miss"], ag))
        L.append("")
        L.append("- cant_tell: Native %d / axe incomplete %d" % (st["native_cant_tell"], st["axe_incomplete"]))
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- Native / axe の取得
def load_native():
    """Native ランナーを遅延 import。無ければ None。"""
    sys.path.insert(0, str(ROOT / "src"))
    try:
        from ux.a11y import runner  # type: ignore
        return runner
    except Exception:
        return None


def catalog_specs():
    sys.path.insert(0, str(ROOT / "src"))
    from ux.a11y.catalog import CATALOG  # type: ignore
    return CATALOG


def native_axe_map() -> dict[str, list[str]]:
    """native rule_id -> 旧 axe id。catalog の legacy_axe_ids が唯一の対応表。"""
    return {s.rule_id: list(s.legacy_axe_ids) for s in catalog_specs() if s.legacy_axe_ids}


def declared_axe_ids() -> set[str]:
    """WebSpec2Doc が対応を宣言する（implementation が full/partial）ルールの旧 axe id。"""
    return {a for s in catalog_specs() if s.declared for a in s.legacy_axe_ids}


def native_by_axe_rule(result, mapping: dict) -> dict[str, dict]:
    """PageA11yResult -> 旧 axe id ごとの {status, violations, unmappable}。実装が無い id は含めない。"""
    out: dict[str, dict] = {}
    for rr in getattr(result, "rules", ()):
        axe_ids = mapping.get(rr.rule_id, [])
        nodes = [n for n in rr.nodes if getattr(getattr(n, "status", ""), "value", getattr(n, "status", "")) == "violation"]
        sels = [getattr(n, "selector", "") for n in nodes]
        for aid in axe_ids:
            out[aid] = {"status": getattr(rr.status, "value", rr.status), "message": getattr(rr, "message", ""), "violations": sels,
                        "unmappable": sum(1 for s in sels if not normalize_selector(s))}
    return out


def native_cant_tell_count(result) -> int:
    return sum(getattr(r, "counts", {}).get("cant_tell", 0) if isinstance(getattr(r, "counts", None), dict)
               else sum(1 for n in r.nodes if getattr(n.status, "value", n.status) == "cant_tell") for r in getattr(result, "rules", ()))


def run_axe(page, axe_path: Path) -> dict:
    page.add_script_tag(path=str(axe_path))
    res = page.evaluate("async () => { const r = await axe.run(document); "
                        "return {v: r.violations.map(x => ({id: x.id, t: x.nodes.map(n => n.target)})), "
                        "i: r.incomplete.reduce((a, x) => a + x.nodes.length, 0), ver: axe.version}; }")
    by: dict[str, set] = {}
    for v in res["v"]:
        by.setdefault(v["id"], set()).update(k for k in (normalize_selector(t) for t in v["t"]) if k)
    return {"by_rule": by, "incomplete": res["i"], "version": res["ver"]}


def launch(pw):
    """製品と同じ検出（Chrome / Edge の channel）で起動する。headless-shell の代替起動はしない。"""
    sys.path.insert(0, str(ROOT / "src"))
    from browser_detect import BrowserUnavailable, detect_browser, launch_browser  # type: ignore
    try:
        return launch_browser(pw), detect_browser().channel
    except BrowserUnavailable:
        return None, None


# ---------------------------------------------------------------- 実行
def run(args) -> int:
    axe_path = Path(os.environ.get("A11Y_ORACLE_AXE_PATH", DEFAULT_AXE))
    if not axe_path.is_file():
        print("オラクル未取得: %s がありません。`npm install --prefix tools/a11y-oracle` を実行してください。" % axe_path)
        return 2
    runner = load_native()
    if runner is None or not hasattr(runner, "run_native_a11y"):
        print("Native 未統合: src/ux/a11y の runner が見つかりません（run_native_a11y）。")
        return 3
    from playwright.sync_api import sync_playwright
    mapping = native_axe_map()
    report: dict = {"native_version": "webspec2doc-native-a11y"}
    with sync_playwright() as pw:
        browser, ch = launch(pw)
        if browser is None:
            print("ブラウザ無し: Chrome も Edge も起動できません。")
            return 4
        report["browser"] = ch
        page = browser.new_page()
        if args.fixtures:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
            rows, failures, axe_tp, axe_fp, axe_fn = [], [], 0, 0, 0
            declared = declared_axe_ids()
            skipped_undeclared, pending = [], {}
            for rel, entry in manifest["fixtures"].items():
                if entry["axe_rule"] not in declared:
                    skipped_undeclared.append(rel)  # 未宣言ルール: 指標の母集団に入れない
                    continue
                page.goto((FIXTURES / rel).as_uri())
                nat = native_by_axe_rule(runner.run_native_a11y(page, None), mapping).get(entry["axe_rule"])
                if nat is None or nat["status"] == "not_implemented":
                    pending.setdefault(entry["axe_rule"], []).append(rel)  # 宣言済みだが未結線/実装待ち
                    continue
                ax = run_axe(page, axe_path)
                report["axe_version"] = ax["version"]
                res = classify_fixture(entry, nat)
                rows.append({"fixture": rel, "rule": entry["axe_rule"], "entry": entry, "result": res})
                failures += [{"fixture": rel, **f} for f in res["failures"]]
                exp = {normalize_selector(v) for v in entry["violations"]}
                got = ax["by_rule"].get(entry["axe_rule"], set())
                axe_tp, axe_fp, axe_fn = axe_tp + len(exp & got), axe_fp + len(got - exp), axe_fn + len(exp - got)
            report["fixtures"] = aggregate_fixture_metrics(rows)
            report["axe_vs_truth"] = prf(axe_tp, axe_fp, axe_fn)
            report["failures"] = failures
            report["scope"] = {"declared_fixtures": len(rows),
                               "undeclared_skipped": len(skipped_undeclared),
                               "pending_rules": {k: len(v) for k, v in sorted(pending.items())},
                               "pending_fixtures": sum(len(v) for v in pending.values())}
        pages = [p.as_uri() for d in args.sites for p in sorted(Path(d).glob("*.html"))] + list(args.url)
        if pages:
            n_all: dict[str, set] = {}
            a_all: dict[str, set] = {}
            n_ct = a_inc = 0
            for u in pages:
                page.goto(u)
                nres = runner.run_native_a11y(page, None)
                n_ct += native_cant_tell_count(nres)
                for aid, d in native_by_axe_rule(nres, mapping).items():
                    n_all.setdefault(aid, set()).update("%s|%s" % (u, normalize_selector(s)) for s in d["violations"])
                ax = run_axe(page, axe_path)
                a_inc += ax["incomplete"]
                report["axe_version"] = ax["version"]
                for aid, ks in ax["by_rule"].items():
                    a_all.setdefault(aid, set()).update("%s|%s" % (u, k) for k in ks)
            report["sites"] = {"pages": len(pages), "rules": compare_sites(n_all, a_all),
                               "native_cant_tell": n_ct, "axe_incomplete": a_inc}
        browser.close()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "oracle_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=list), encoding="utf-8")
    (out / "oracle_report.md").write_text(render_markdown(report), encoding="utf-8")
    print("出力: %s" % out)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixtures", action="store_true", help="tests/a11y_oracle の fixture を正解付きで評価")
    ap.add_argument("--sites", action="append", default=[], metavar="DIR", help="HTML ディレクトリ（例 demo/site）")
    ap.add_argument("--url", action="append", default=[], help="比較する URL（手元実行のみ）")
    ap.add_argument("--out", default="a11y_oracle_out")
    args = ap.parse_args(argv)
    if not (args.fixtures or args.sites or args.url):
        ap.error("--fixtures / --sites / --url のいずれかが必要です")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
