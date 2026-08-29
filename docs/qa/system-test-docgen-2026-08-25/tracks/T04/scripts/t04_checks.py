#!/usr/bin/env python3
"""T04 成果物・永続化・履歴の自動検査。phase1(成果物+API) / phase2(サンプル) / phase3(再クロール比較)。
実行: venv/bin/python scripts/t04_checks.py phase1  （リポジトリ直下から）"""
import json, re, sys, zipfile, urllib.request, urllib.error
from pathlib import Path

BASE = "http://127.0.0.1:8765"
DOM = "127.0.0.1:9104"
SAMPLE = "sample.webspec2doc.local"
ROOT = Path(__file__).resolve().parents[6]  # repo root
OUT = ROOT / "output" / DOM
EV = Path(__file__).resolve().parents[1] / "evidence"
RESULTS = []

def check(cid, ok, detail):
    RESULTS.append((cid, "PASS" if ok else "FAIL", detail))
    print(f"{cid}: {'PASS' if ok else 'FAIL'} - {detail}")

def http(path, save=None, method="GET", data=None):
    req = urllib.request.Request(BASE + path, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            if save:
                (EV / save).write_bytes(body)
            return r.status, body
    except urllib.error.HTTPError as e:
        body = e.read()
        if save:
            (EV / save).write_bytes(body)
        return e.code, body
    except Exception as e:
        return -1, str(e).encode()

def load_summary():
    txt = (EV / "c001_run_stream.txt").read_text(errors="replace")
    run_id = re.search(r"RUN_ID:(\S+)", txt)
    summary = re.search(r"SUMMARY:(\{.*\})", txt)
    return (run_id.group(1) if run_id else None,
            json.loads(summary.group(1)) if summary else None)

def screens_of(report):
    for key in ("screens", "pages"):
        if isinstance(report.get(key), list):
            return report[key]
    return []

def is_image(p: Path):
    b = p.read_bytes()[:8]
    return b.startswith(b"\x89PNG") or b.startswith(b"\xff\xd8")

def phase1():
    run_id, summary = load_summary()
    # C001 成果物一式
    expected = ["report.json", "report.html", "report.md", "audit.jsonl", "site.json"]
    missing = [f for f in expected if not (OUT / f).is_file()]
    dirs_missing = [d for d in ("screenshots", "snapshots") if not (OUT / d).is_dir()]
    listing = "\n".join(f"{p.relative_to(OUT)}\t{p.stat().st_size}" for p in sorted(OUT.rglob("*")) if p.is_file())
    (EV / "c001_listing.txt").write_text(listing)
    check("C001", not missing and not dirs_missing, f"missing_files={missing} missing_dirs={dirs_missing}")
    # C002 非空 + performance
    empty = [str(p.relative_to(OUT)) for p in OUT.rglob("*") if p.is_file() and p.stat().st_size == 0]
    report = json.loads((OUT / "report.json").read_text())
    perf_hits = sorted(set(re.findall(r'"(lcp[^"]*|cls[^"]*|ttfb[^"]*|LCP|CLS|TTFB)"',
                                      (OUT / "report.json").read_text(), re.I)))
    check("C002", not empty and len(perf_hits) >= 3, f"empty={empty} perf_keys={perf_hits[:8]}")
    # C003 SUMMARY 整合
    scr = screens_of(report)
    forms = sum(len(s.get("forms", []) or []) for s in scr)
    fields = sum(len(f.get("fields", []) or []) for s in scr for f in (s.get("forms") or []))
    ok = summary and summary.get("screens") == len(scr) and summary.get("forms") == forms and summary.get("fields") == fields
    check("C003", bool(ok), f"summary={summary} report(screens={len(scr)},forms={forms},fields={fields})")
    (EV / "c003_report_top.txt").write_text(
        f"top_keys={sorted(report.keys())}\n" + "\n".join(
            f"{s.get('url')} forms={len(s.get('forms') or [])} login_required={s.get('login_required')}" for s in scr))
    # C004 contact フォーム
    contact = next((s for s in scr if "/contact" in str(s.get("url", ""))), None)
    detail = "contact_screen_not_found"
    ok = False
    if contact:
        flds = [f2 for f1 in (contact.get("forms") or []) for f2 in (f1.get("fields") or [])]
        names = {f.get("name"): f for f in flds}
        ok = {"name", "email", "body"} <= set(names)
        detail = json.dumps({n: {k: v for k, v in (names.get(n) or {}).items()
                                 if k in ("required", "maxlength", "max_length", "type", "attributes")}
                             for n in ("name", "email", "body")}, ensure_ascii=False)[:500]
        (EV / "c004_contact_fields.json").write_text(json.dumps(flds, ensure_ascii=False, indent=1))
    check("C004", ok, detail)
    # C005/C006 api/result
    st, body = http(f"/api/result?domain={DOM}", save="c005_api_result.json")
    ok5 = st == 200
    files_cnt = -1
    if ok5:
        j = json.loads(body)
        files_cnt = len(j.get("files", []))
        ok5 = files_cnt > 0 and j.get("is_sample") is False
    check("C005", ok5, f"status={st} files={files_cnt}")
    st6, body6 = http(f"/api/result?domain={DOM}&run_id={run_id}", save="c006_api_result_runid.json")
    check("C006", st6 == 200, f"status={st6} run_id={run_id}")
    # C007 spec-xlsx
    st7, _ = http(f"/api/export/spec-xlsx?domain={DOM}", save="c007_spec.xlsx")
    sheets = []
    try:
        with zipfile.ZipFile(EV / "c007_spec.xlsx") as z:
            wb = z.read("xl/workbook.xml").decode("utf-8")
            sheets = re.findall(r'name="([^"]+)"', wb)
    except Exception as e:
        sheets = [f"ERROR:{e}"]
    need = ["画面一覧", "フォーム", "項目定義", "境界値", "テスト設計", "テストケース", "遷移"]
    ok7 = st7 == 200 and all(any(n in s for s in sheets) for n in need)
    check("C007", ok7, f"status={st7} sheets={sheets}")
    # C008 download-zip
    st8, _ = http(f"/download-zip?domain={DOM}", save="c008_domain.zip")
    ok8, zdetail = False, ""
    try:
        with zipfile.ZipFile(EV / "c008_domain.zip") as z:
            bad = z.testzip()
            znames = {n.split("/", 1)[1] for n in z.namelist() if "/" in n}
            fsnames = {str(p.relative_to(OUT)) for p in OUT.rglob("*") if p.is_file()}
            ok8 = st8 == 200 and bad is None and fsnames <= znames
            zdetail = f"testzip={bad} zip_files={len(znames)} fs_files={len(fsnames)} fs_only={sorted(fsnames - znames)[:5]}"
    except Exception as e:
        zdetail = f"ERROR:{e}"
    check("C008", ok8, f"status={st8} {zdetail}")
    # C009 preview
    st9, body9 = http(f"/preview?path={DOM}/report.json", save="c009_preview.json")
    ok9 = st9 == 200
    try:
        json.loads(body9)
    except Exception:
        ok9 = False
    check("C009", ok9, f"status={st9} bytes={len(body9)}")
    # C010 traversal（軽確認）
    st10a, b10a = http("/preview?path=../../etc/passwd", save="c010_traversal_preview.txt")
    st10b, b10b = http("/download?path=../../etc/passwd", save="c010_traversal_download.txt")
    leak = b"root:" in b10a or b"root:" in b10b
    check("C010", st10a == 404 and st10b == 404 and not leak, f"preview={st10a} download={st10b} leaked={leak}")
    # C014 履歴記録
    st14, b14 = http("/api/history/runs", save="c014_history_runs.json")
    runs_txt = b14.decode(errors="replace")
    in_runs = DOM in runs_txt and (run_id or "") in runs_txt
    ulog = (ROOT / "output" / "usage_log.jsonl")
    in_ulog = ulog.is_file() and any(DOM in ln and (run_id or "") in ln for ln in ulog.read_text(errors="replace").splitlines())
    check("C014", st14 == 200 and in_runs and in_ulog, f"status={st14} in_runs={in_runs} in_usage_log={in_ulog}")
    # C016 スクショ健全性
    shots = sorted((OUT / "screenshots").glob("*")) if (OUT / "screenshots").is_dir() else []
    zero = [s.name for s in shots if s.stat().st_size == 0]
    notimg = [s.name for s in shots if s.is_file() and not is_image(s)]
    ok16 = shots and not zero and not notimg and len(shots) >= len(scr)
    check("C016", bool(ok16), f"shots={len(shots)} screens={len(scr)} zero={zero} not_image={notimg} sizes={[s.stat().st_size for s in shots]}")
    # C018 state-table / coverage-heatmap
    st18a, _ = http(f"/api/state-table?domain={DOM}", save="c018_state_table.json")
    st18b, _ = http(f"/api/coverage-heatmap?domain={DOM}", save="c018_coverage_heatmap.json")
    check("C018", st18a == 200 and st18b == 200, f"state-table={st18a} coverage-heatmap={st18b}")
    # phase3 用の事前状態保存
    pre = {"report_mtime": (OUT / "report.json").stat().st_mtime,
           "audit_lines": len((OUT / "audit.jsonl").read_text(errors="replace").splitlines()),
           "screens": len(scr),
           "shots": len(shots),
           "login_flags": {str(s.get("url")): s.get("login_required") for s in scr},
           "site_json": json.loads((OUT / "site.json").read_text()) if (OUT / "site.json").is_file() else None,
           "run_id": run_id}
    (EV / "c015_prestate.json").write_text(json.dumps(pre, ensure_ascii=False, indent=1))

def phase2():
    # C012: POST 前の履歴採取
    http("/api/history", save="c012_history_before.json")
    http("/api/history/runs", save="c012_runs_before.json")
    # C011: サンプル展開
    st, body = http("/api/sample-report", save="c011_sample_post.json", method="POST", data=b"")
    sdir = ROOT / "output" / SAMPLE
    files = [p.name for p in sorted(sdir.glob("*"))] if sdir.is_dir() else []
    stR, bR = http(f"/api/result?domain={SAMPLE}", save="c011_sample_result.json")
    is_sample = json.loads(bR).get("is_sample") if stR == 200 else None
    bundled = (ROOT / "demo" / "sample_report" / "report.json").is_file()
    ok11 = st == 200 and "report.json" in files and is_sample is True and bundled
    check("C011", ok11, f"post={st} bundled={bundled} files={len(files)} is_sample={is_sample}")
    # C012: POST 後の履歴 diff
    _, hb = http("/api/history", save="c012_history_after.json")
    _, rb = http("/api/history/runs", save="c012_runs_after.json")
    before_h = (EV / "c012_history_before.json").read_bytes()
    before_r = (EV / "c012_runs_before.json").read_bytes()
    sample_new_h = hb.count(SAMPLE.encode()) - before_h.count(SAMPLE.encode())
    sample_new_r = rb.count(SAMPLE.encode()) - before_r.count(SAMPLE.encode())
    pre_existing = before_h.count(SAMPLE.encode()) + before_r.count(SAMPLE.encode())
    check("C012", sample_new_h <= 0 and sample_new_r <= 0,
          f"new_mentions history={sample_new_h} runs={sample_new_r} (pre_existing_mentions={pre_existing})")
    # C013: サンプル再クロール導線の到達性
    stS, bS = http(f"/api/site?domain={SAMPLE}", save="c013_sample_site.json")
    txt = bS.decode(errors="replace")
    urls = re.findall(r'"url":\s*"([^"]+)"', txt)[:5]
    check("C013", stS == 200, f"site_status={stS} first_urls={urls} (recrawl.js は site→result→https://+domain の順で URL 復元)")

def phase3():
    pre = json.loads((EV / "c015_prestate.json").read_text())
    run_id2, summary2 = None, None
    txt = (EV / "c015_run_stream.txt").read_text(errors="replace")
    m = re.search(r"RUN_ID:(\S+)", txt); run_id2 = m.group(1) if m else None
    m = re.search(r"SUMMARY:(\{.*\})", txt); summary2 = json.loads(m.group(1)) if m else None
    report = json.loads((OUT / "report.json").read_text())
    scr = screens_of(report)
    flags = {str(s.get("url")): s.get("login_required") for s in scr}
    mtime_new = (OUT / "report.json").stat().st_mtime
    audit_new = len((OUT / "audit.jsonl").read_text(errors="replace").splitlines())
    shots = sorted((OUT / "screenshots").glob("*"))
    zero = [s.name for s in shots if s.stat().st_size == 0]
    lost = {u: (pre["login_flags"].get(u), flags.get(u)) for u in pre["login_flags"]
            if pre["login_flags"].get(u) and not flags.get(u)}
    ok = (mtime_new > pre["report_mtime"] and len(scr) == pre["screens"]
          and not lost and audit_new >= pre["audit_lines"] and not zero)
    check("C015", ok, f"mtime_updated={mtime_new > pre['report_mtime']} screens={pre['screens']}->{len(scr)} "
                      f"login_flag_lost={lost} audit_lines={pre['audit_lines']}->{audit_new} run_id2={run_id2} summary2={summary2}")
    check("C016b", bool(shots) and not zero and len(shots) >= len(scr),
          f"(再クロール後) shots={len(shots)} screens={len(scr)} zero={zero}")
    (EV / "c015_poststate.json").write_text(json.dumps(
        {"login_flags": flags, "audit_lines": audit_new, "shots": len(shots)}, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    {"phase1": phase1, "phase2": phase2, "phase3": phase3}[sys.argv[1]]()
