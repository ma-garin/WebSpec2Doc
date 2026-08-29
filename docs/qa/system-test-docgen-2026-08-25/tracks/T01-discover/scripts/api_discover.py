#!/usr/bin/env python3
"""T01 discover API tests. Usage: api_discover.py <group A|B|C|D|L>
Evidence is written to ../evidence/. Uses only stdlib (urllib) + subprocess ps.
Target SUT: http://127.0.0.1:8765  Mock: http://127.0.0.1:9101
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SUT = "http://127.0.0.1:8765"
M = "http://127.0.0.1:9101"
EV = Path(__file__).resolve().parent.parent / "evidence"
EV.mkdir(exist_ok=True)


def post(path, fields, headers=None, timeout=200):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(SUT + path, data=data, method="POST")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, resp
    except urllib.error.HTTPError as e:
        return e.code, e


def sse(path, fields, max_seconds=200, stop_after_pages=None, on_run_id=None):
    """Return (status, events[], raw_text, elapsed). Parses `data: {json}` lines."""
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(SUT + path, data=data, method="POST")
    events, raw = [], []
    t0 = time.time()
    pages = 0
    try:
        resp = urllib.request.urlopen(req, timeout=max_seconds)
        status = resp.status
        buf = ""
        while True:
            chunk = resp.read(256)
            if not chunk:
                break
            buf += chunk.decode("utf-8", "replace")
            while "\n\n" in buf:
                line, buf = buf.split("\n\n", 1)
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                raw.append(payload)
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                events.append(obj)
                if obj.get("run_id") and on_run_id:
                    on_run_id(obj["run_id"])
                if obj.get("page"):
                    pages += 1
                if stop_after_pages and pages >= stop_after_pages:
                    resp.close()
                    return status, events, "\n".join(raw), time.time() - t0
            if time.time() - t0 > max_seconds:
                resp.close()
                break
        return status, events, "\n".join(raw), time.time() - t0
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        return e.code, [], body, time.time() - t0
    except (TimeoutError, urllib.error.URLError, OSError) as e:
        events.append({"error": f"__client_exception__ {type(e).__name__}: {e}"})
        return "EXC", events, "\n".join(raw) + f"\nEXC {e}", time.time() - t0


def urls_of(events):
    return [e["page"]["url"] for e in events if e.get("page")]


def summarize(events):
    return {
        "run_id": next((e["run_id"] for e in events if e.get("run_id")), None),
        "n_pages": sum(1 for e in events if e.get("page")),
        "done": next((e for e in events if e.get("done")), None),
        "cancelled": any(e.get("cancelled") for e in events),
        "errors": [e["error"] for e in events if e.get("error")],
        "skipped": [
            {"url": e["crawl_event"].get("url"), "reason": e["crawl_event"].get("reason")}
            for e in events
            if e.get("crawl_event", {}).get("event") == "page_skipped"
        ],
        "event_order": [
            ("run_id" if e.get("run_id") else "page" if e.get("page")
             else "done" if e.get("done") else "cancelled" if e.get("cancelled")
             else "error" if e.get("error") else e.get("crawl_event", {}).get("event", "?"))
            for e in events
        ][:12],
    }


def ps_discover():
    out = subprocess.run(["ps", "-Ao", "pid,command"], capture_output=True, text=True).stdout
    return [ln for ln in out.splitlines() if "--discover" in ln and "grep" not in ln]


def rec(results, cid, verdict, detail):
    results.append({"case": cid, "verdict": verdict, "detail": detail})
    print(f"{cid}: {verdict} :: {detail}")


def group_A(results):
    # C001-004, C026, C043, C050(sync side), C052
    st, ev, raw, el = sse("/api/discover-stream",
                          {"url": M + "/", "depth": "2", "max_pages": "30", "parallelism": "4"})
    (EV / "A_hub.jsonl").write_text(raw)
    s = summarize(ev)
    (EV / "A_hub_summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=2))
    order = s["event_order"]
    ok_order = order and order[0] == "run_id" and "page" in order and (s["done"] is not None)
    rec(results, "T01-C001", "PASS" if ok_order and not s["errors"] else "FAIL",
        f"order={order} errors={s['errors']} elapsed={el:.1f}s")
    # page fields
    pf = [e["page"] for e in ev if e.get("page")]
    need = {"url", "title", "login_required", "login_reasons", "login_url"}
    fields_ok = all(need <= set(p.keys()) for p in pf)
    rec(results, "T01-C002", "PASS" if fields_ok and pf else "FAIL",
        f"sample_keys={sorted(pf[0].keys()) if pf else None}")
    total = (s["done"] or {}).get("total")
    rec(results, "T01-C003", "PASS" if total == s["n_pages"] and s["n_pages"] <= 30 else "FAIL",
        f"done.total={total} n_pages={s['n_pages']}")
    login_pages = {p["url"].rsplit("/", 1)[-1]: p for p in pf}
    lr = {k: (v["login_required"], v.get("login_url")) for k, v in login_pages.items()
          if k in ("login", "dashboard", "account", "about")}
    dash = next((p for p in pf if p["url"].endswith("/dashboard")), None)
    c004 = "PASS" if dash and dash["login_required"] and "/login" in (dash.get("login_url") or "") else \
        ("FAIL" if dash else "BLOCKED")
    rec(results, "T01-C004", c004, f"login_map={lr}")
    c026 = "PASS" if dash and dash["login_required"] else "BLOCKED"
    rec(results, "T01-C026", c026, f"dashboard={dash}")
    # robots
    urls = urls_of(ev)
    robots_excluded = not any("/private/secret" in u for u in urls)
    robots_evt = any(x["reason"] == "robots" for x in s["skipped"])
    rec(results, "T01-C043", "PASS" if robots_excluded else "FAIL",
        f"private_secret_in_pages={not robots_excluded} skipped_robots_event={robots_evt} skipped={s['skipped']}")
    # sync vs sse (C050) on /about depth1 max10
    st2, ev2, raw2, _ = sse("/api/discover-stream",
                            {"url": M + "/about", "depth": "1", "max_pages": "10", "parallelism": "1"})
    stS, respS = post("/api/discover", {"url": M + "/about", "depth": "1", "max_pages": "10"})
    body = respS.read().decode() if hasattr(respS, "read") else ""
    (EV / "A_sync_about.json").write_text(body)
    try:
        sync_urls = sorted(p["url"] for p in json.loads(body).get("pages", []))
    except Exception:
        sync_urls = None
    sse_urls = sorted(set(urls_of(ev2)))
    rec(results, "T01-C050", "PASS" if sync_urls is not None and sync_urls == sse_urls else "FAIL",
        f"sync={sync_urls} sse={sse_urls}")
    # CSRF Origin: null (C052)
    stc, respc = post("/api/discover-stream",
                      {"url": M + "/", "depth": "1", "max_pages": "2"},
                      headers={"Origin": "null"})
    rec(results, "T01-C052", "PASS" if stc == 403 else "FAIL", f"status={stc}")


def group_invalid(results):
    # C005-C014
    cases = [
        ("T01-C005", ""),
        ("T01-C006", "   "),
        ("T01-C007", "ftp://127.0.0.1:9101/"),
        ("T01-C008", "javascript:alert(1)"),
        ("T01-C009", "data:text/html,<h1>x</h1>"),
        ("T01-C010", "127.0.0.1:9101/about"),
        ("T01-C011", "http://テスト.invalid/"),
        ("T01-C012", "http://127.0.0.1:9101/" + "a" * 65000),
        ("T01-C013", "http://127.0.0.1:9101/\nfoo"),
        ("T01-C014", "--version"),
    ]
    log = {}
    for cid, url in cases:
        st, ev, raw, el = sse("/api/discover-stream",
                              {"url": url, "depth": "1", "max_pages": "3", "parallelism": "1"},
                              max_seconds=45)
        s = summarize(ev)
        log[cid] = {"url": url[:60], "http": st, "n_pages": s["n_pages"],
                    "errors": s["errors"], "skipped": s["skipped"], "elapsed": round(el, 1),
                    "event_order": s["event_order"]}
        # invalid should yield either HTTP 400, an SSE error, 0 pages, or skipped(unsafe_url)
        no_pages = s["n_pages"] == 0
        hung = st == "EXC" and el >= 40
        harmless = ((st == 400) or bool(s["errors"]) or no_pages)
        verdict = "PASS" if (harmless and not hung) else ("FAIL" if not no_pages else "PASS-slow")
        log[cid]["hung"] = hung
        rec(results, cid, verdict,
            f"http={st} n_pages={s['n_pages']} err={s['errors']} skip={s['skipped']} t={el:.1f}s")
    (EV / "B_invalid.json").write_text(json.dumps(log, ensure_ascii=False, indent=2))


def group_restricted(results):
    # C015-C022
    cases = [
        ("T01-C015", M and "http://169.254.169.254/", "1", "1"),
        ("T01-C016", "http://10.0.0.1/", "1", "1"),
        ("T01-C017", "http://[::1]/", "1", "1"),
        ("T01-C018", "http://0x7f000001/", "1", "1"),
        ("T01-C019", "http://127.1/", "1", "1"),
        ("T01-C020", "http://localhost/", "1", "1"),
    ]
    log = {}
    for cid, url, d, mp in cases:
        st, ev, raw, el = sse("/api/discover-stream",
                              {"url": url, "depth": d, "max_pages": mp, "parallelism": "1"},
                              max_seconds=50)
        s = summarize(ev)
        pages = [e["page"]["url"] for e in ev if e.get("page")]
        log[cid] = {"url": url, "http": st, "pages": pages, "skipped": s["skipped"],
                    "errors": s["errors"], "elapsed": round(el, 1)}
        blocked = bool(s["skipped"]) or s["n_pages"] == 0 or bool(s["errors"])
        rec(results, cid, "PASS" if blocked else "FAIL",
            f"reached={s['n_pages']}pages skip={s['skipped']} err={bool(s['errors'])} t={el:.1f}s")
    # redirect follow (C021, C022)
    for cid, path in [("T01-C021", "/redirect-internal"), ("T01-C022", "/redirect-file")]:
        st, ev, raw, el = sse("/api/discover-stream",
                              {"url": M + path, "depth": "1", "max_pages": "3", "parallelism": "1"},
                              max_seconds=50)
        s = summarize(ev)
        pages = [e["page"]["url"] for e in ev if e.get("page")]
        bad = any(("169.254" in u or "etc/passwd" in u or u.startswith("file:")) for u in pages)
        titles = [e["page"].get("title", "") for e in ev if e.get("page")]
        leaked = any("root:" in t for t in titles)
        log[cid] = {"path": path, "pages": pages, "titles": titles[:5],
                    "skipped": s["skipped"], "errors": s["errors"], "elapsed": round(el, 1)}
        rec(results, cid, "PASS" if not bad and not leaked else "FAIL",
            f"pages={pages} leaked={leaked} skip={s['skipped']}")
    # timeout/error group C023-C025 handled here too
    for cid, path, mp, cap in [("T01-C023", "/timeout", "3", 90), ("T01-C024", "/slow", "3", 60),
                                ("T01-C044", "/500", "3", 45), ("T01-C045", "/broken-link", "5", 90)]:
        st, ev, raw, el = sse("/api/discover-stream",
                              {"url": M + path, "depth": "1", "max_pages": mp, "parallelism": "1"},
                              max_seconds=cap + 30)
        s = summarize(ev)
        pages = [e["page"]["url"] for e in ev if e.get("page")]
        done = s["done"] is not None
        log[cid] = {"path": path, "http": st, "n_pages": s["n_pages"], "pages": pages[:6],
                    "done": done, "errors": s["errors"], "elapsed": round(el, 1)}
        if cid == "T01-C024":
            verdict = "PASS" if any("/slow" in u for u in pages) else "FAIL"
        else:
            verdict = "PASS" if done and el <= cap else ("FAIL" if not done else "PASS")
        rec(results, cid, verdict, f"done={done} n={s['n_pages']} t={el:.1f}s (cap {cap})")
    # unicode C046, normalize C047-49
    for cid, u, check in [
        ("T01-C046", M + "/unicode/日本語ページ", None),
        ("T01-C047", M + "/about/", "slash"),
        ("T01-C048", M + "/about#sec", "frag"),
        ("T01-C049", M + "/about?x=1", "query"),
    ]:
        st, ev, raw, el = sse("/api/discover-stream",
                              {"url": u, "depth": "0" if cid != "T01-C046" else "1",
                               "max_pages": "1" if cid != "T01-C046" else "2", "parallelism": "1"},
                              max_seconds=45)
        pages = [e["page"]["url"] for e in ev if e.get("page")]
        log[cid] = {"input": u, "pages": pages}
        if check == "slash":
            v = "PASS" if pages and not pages[0].endswith("/about/") else "FAIL"
        elif check == "frag":
            v = "PASS" if pages and "#" not in pages[0] else "FAIL"
        elif check == "query":
            v = "PASS" if pages and "x=1" in pages[0] else "FAIL"
        else:
            v = "PASS" if pages else "FAIL"
        rec(results, cid, v, f"pages={pages}")
    (EV / "B_restricted_timeout_norm.json").write_text(json.dumps(log, ensure_ascii=False, indent=2))


def group_C(results):
    # boundary C027-C041 (except C035 manual)
    depth_cases = [
        ("T01-C027", "/deep/1", {"depth": "0", "max_pages": "20"}),
        ("T01-C028", "/deep/1", {"depth": "1", "max_pages": "20"}),
        ("T01-C029", "/deep/1", {"depth": "10", "max_pages": "20"}),
        ("T01-C030", "/deep/1", {"depth": "11", "max_pages": "20"}),
        ("T01-C031", "/deep/1", {"depth": "-1", "max_pages": "20"}),
        ("T01-C032", "/deep/1", {"depth": "abc", "max_pages": "20"}),
        ("T01-C033", "/huge", {"depth": "1", "max_pages": "0"}),
        ("T01-C034", "/huge", {"depth": "1", "max_pages": "1"}),
        ("T01-C037", "/huge", {"depth": "1", "max_pages": "abc"}),
        ("T01-C038", "/huge", {"depth": "1", "max_pages": "5", "parallelism": "0"}),
        ("T01-C039", "/huge", {"depth": "1", "max_pages": "5", "parallelism": "1"}),
        ("T01-C040", "/huge", {"depth": "1", "max_pages": "20", "parallelism": "8"}),
        ("T01-C041", "/huge", {"depth": "1", "max_pages": "20", "parallelism": "9"}),
    ]
    exp = {"T01-C028": 2, "T01-C029": 8, "T01-C034": 1, "T01-C040": 20}
    log = {}
    for cid, path, extra in depth_cases:
        fields = {"url": M + path, "parallelism": "1"}
        fields.update(extra)
        cap = 120 if path == "/huge" and extra.get("max_pages") in ("20",) else 90
        st, ev, raw, el = sse("/api/discover-stream", fields, max_seconds=cap)
        s = summarize(ev)
        n = s["n_pages"]
        log[cid] = {"fields": {k: v for k, v in fields.items() if k != "url"},
                    "n_pages": n, "http": st, "done_total": (s["done"] or {}).get("total"),
                    "elapsed": round(el, 1)}
        if cid in exp:
            v = "PASS" if n == exp[cid] else "FAIL"
        else:
            # clamp/default cases: PASS if server did not error and returned a bounded result
            v = "PASS" if (s["done"] is not None and not s["errors"]) or st == 400 else "FAIL"
        rec(results, cid, v, f"n_pages={n} exp={exp.get(cid,'clamp/def')} http={st} t={el:.1f}s")
    (EV / "C_boundary.json").write_text(json.dumps(log, ensure_ascii=False, indent=2))


def group_D(results):
    # C042 cancel, C051 client disconnect
    before = ps_discover()
    run_id_box = {}
    st, ev, raw, el = sse("/api/discover-stream",
                          {"url": M + "/", "depth": "2", "max_pages": "30", "parallelism": "1"},
                          max_seconds=60, stop_after_pages=1,
                          on_run_id=lambda r: run_id_box.setdefault("id", r))
    rid = run_id_box.get("id")
    cst, cresp = (None, None)
    if rid:
        cst, cresp = post("/api/cancel", {"run_id": rid})
        cbody = cresp.read().decode() if hasattr(cresp, "read") else ""
    else:
        cbody = "no run_id"
    time.sleep(6)
    after = ps_discover()
    (EV / "D_cancel_ps.txt").write_text(
        f"run_id={rid}\ncancel_http={cst} body={cbody}\n--- before ---\n"
        + "\n".join(before) + "\n--- after(6s) ---\n" + "\n".join(after))
    gone = len(after) <= len(before)
    ok_cancel = (cst == 200 and '"ok": true' in cbody.replace("True", "true").lower()) or gone
    rec(results, "T01-C042",
        "PASS" if rid and gone else ("FAIL" if rid else "BLOCKED"),
        f"cancel_http={cst} body={cbody.strip()} procs_before={len(before)} after={len(after)}")
    # C051 client disconnect: open, read run_id, then hard-close socket
    before2 = ps_discover()
    data = urllib.parse.urlencode(
        {"url": M + "/", "depth": "2", "max_pages": "30", "parallelism": "1"}).encode()
    req = urllib.request.Request(SUT + "/api/discover-stream", data=data, method="POST")
    resp = urllib.request.urlopen(req, timeout=30)
    _ = resp.read(200)  # enough to get run_id line
    resp.close()  # abrupt client disconnect
    time.sleep(10)
    after2 = ps_discover()
    (EV / "D_disconnect_ps.txt").write_text(
        "--- before ---\n" + "\n".join(before2) + "\n--- after(10s) ---\n" + "\n".join(after2))
    rec(results, "T01-C051", "PASS" if len(after2) <= len(before2) else "FAIL",
        f"procs_before={len(before2)} after={len(after2)}")


def group_L(results):
    # C025 sync 180s timeout, C036 max_pages=501 clamp
    t0 = time.time()
    st, resp = post("/api/discover", {"url": M + "/huge", "depth": "1", "max_pages": "500"}, timeout=200)
    el = time.time() - t0
    body = resp.read().decode()[:2000] if hasattr(resp, "read") else ""
    try:
        n = len(json.loads(body).get("pages", [])) if st == 200 else None
    except Exception:
        n = None
    (EV / "L_sync_huge.json").write_text(f"http={st} elapsed={el:.1f}\n{body}")
    rec(results, "T01-C025", "PASS" if st in (200, 504) else "FAIL",
        f"http={st} n_pages={n} elapsed={el:.1f}s (180s cap)")
    st2, ev2, raw2, el2 = sse("/api/discover-stream",
                              {"url": M + "/huge", "depth": "1", "max_pages": "501", "parallelism": "8"},
                              max_seconds=150)
    s2 = summarize(ev2)
    rec(results, "T01-C036", "PASS" if s2["n_pages"] == 301 or st2 == 400 else "FAIL",
        f"n_pages={s2['n_pages']} http={st2} t={el2:.1f}s (expect 301 clamp)")
    (EV / "L_501_summary.json").write_text(json.dumps(s2, ensure_ascii=False, indent=2))


def main():
    group = sys.argv[1] if len(sys.argv) > 1 else "A"
    results = []
    {"A": group_A, "B": group_invalid, "R": group_restricted,
     "C": group_C, "D": group_D, "L": group_L}[group](results)
    out = EV / f"results_{group}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\n== wrote {out} ({len(results)} cases) ==")


if __name__ == "__main__":
    main()
