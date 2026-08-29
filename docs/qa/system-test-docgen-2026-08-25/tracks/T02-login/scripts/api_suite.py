"""T02 API 試験スイート。/api/login/* を実行し evidence/ に証跡を残す。
実行: venv/bin/python scripts/api_suite.py  （CWD=repo ルート）"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import (  # noqa: E402
    DOMAIN, LOGIN_URL, MOCK, OUT, SECRET, get, jparse, ls_l, mask, post, save_evidence,
)

R = []  # results


def rec(cid, result, observed, evid=""):
    R.append({"id": cid, "result": result, "observed": observed, "evidence": evid})


AUTH = OUT / "auth.json"

# ---------- C001 simple happy path ----------
def c_simple_happy():
    # remove prior auth to observe fresh creation
    if AUTH.exists():
        AUTH.unlink()
    st, body = post("/api/login/simple", {
        "domain": DOMAIN, "login_url": LOGIN_URL, "username": "admin", "password": SECRET})
    d = jparse(body)
    perms = ls_l(AUTH)
    content = AUTH.read_text() if AUTH.exists() else "(missing)"
    has_secret = SECRET in content
    ev = {"status": st, "resp": d, "auth_exists": AUTH.exists(), "ls_l": perms,
          "auth_json_masked": mask(content), "plaintext_password_in_auth": has_secret}
    save_evidence("C001_simple_happy.json", ev)
    ok = bool(d and d.get("success") is True and AUTH.exists() and not has_secret)
    rec("T02-C001", "PASS" if ok else "FAIL",
        f"success={d.get('success') if d else None}, auth_exists={AUTH.exists()}, plaintext_pw={has_secret}, perms={perms.split()[0] if perms else '?'}",
        "evidence/C001_simple_happy.json")


# ---------- C002 invalid creds ----------
def c_simple_invalid():
    # keep the good auth.json; capture mtime to prove not overwritten
    before = AUTH.stat().st_mtime if AUTH.exists() else None
    before_hash = AUTH.read_bytes() if AUTH.exists() else b""
    st, body = post("/api/login/simple", {
        "domain": DOMAIN, "login_url": LOGIN_URL, "username": "admin", "password": "WRONGPASS"})
    d = jparse(body)
    after = AUTH.stat().st_mtime if AUTH.exists() else None
    after_hash = AUTH.read_bytes() if AUTH.exists() else b""
    unchanged = before_hash == after_hash
    ev = {"status": st, "resp": d, "auth_mtime_before": before, "auth_mtime_after": after,
          "auth_unchanged": unchanged}
    save_evidence("C002_simple_invalid.json", ev)
    ok = bool(d and d.get("success") is False and d.get("error") and unchanged)
    rec("T02-C002", "PASS" if ok else "FAIL",
        f"success={d.get('success') if d else None}, msg={mask(str(d.get('error') if d else None))[:60]}, auth_unchanged={unchanged}",
        "evidence/C002_simple_invalid.json")


# ---------- C003 credential leak (runtime ps + artifacts) ----------
def c_leak():
    ps_hits = []
    def fire():
        post("/api/login/simple", {"domain": DOMAIN, "login_url": LOGIN_URL,
                                    "username": "admin", "password": SECRET})
    t = threading.Thread(target=fire); t.start()
    for _ in range(25):
        p = subprocess.run(["ps", "-ww", "-o", "args"], capture_output=True, text=True).stdout
        for line in p.splitlines():
            if "main.py" in line and ("login" in line):
                ps_hits.append(line.strip())
        if SECRET in p:
            ps_hits.append("SECRET_FOUND_IN_PS")
        time.sleep(0.1)
    t.join()
    # artifact grep
    arts = {}
    for name, path in [("ws2d.log", Path("/tmp/ws2d.log")),
                       ("audit.jsonl", Path("output/audit.jsonl")),
                       ("auth.json", AUTH)]:
        try:
            arts[name] = (SECRET in path.read_text(errors="replace")) if path.exists() else "(absent)"
        except Exception as e:  # noqa: BLE001
            arts[name] = f"EXC:{e}"
    # grep whole output tree for this domain
    grep = subprocess.run(["grep", "-rl", SECRET, str(OUT)], capture_output=True, text=True)
    uniq_ps = sorted(set(ps_hits))
    ev = {"ps_cmdlines_with_login": [x for x in uniq_ps if "SECRET" not in x][:5],
          "secret_in_ps": any("SECRET_FOUND" in x for x in uniq_ps),
          "artifact_contains_secret": arts,
          "grep_output_tree_files_with_secret": grep.stdout.strip().splitlines()}
    save_evidence("C003_leak.json", ev)
    leaked = ev["secret_in_ps"] or arts.get("ws2d.log") is True or arts.get("audit.jsonl") is True or arts.get("auth.json") is True or bool(grep.stdout.strip())
    rec("T02-C003", "FAIL" if leaked else "PASS",
        f"secret_in_ps={ev['secret_in_ps']}, log={arts.get('ws2d.log')}, audit={arts.get('audit.jsonl')}, auth={arts.get('auth.json')}, tree_hits={len(ev['grep_output_tree_files_with_secret'])}",
        "evidence/C003_leak.json")


# ---------- C004..C010 input validation (domain / login_url) ----------
def c_validation():
    cases = [
        ("T02-C004", {"domain": "../etc", "login_url": LOGIN_URL, "username": "a", "password": "b"}, "domain=../etc"),
        ("T02-C005", {"domain": "/abs/path", "login_url": LOGIN_URL, "username": "a", "password": "b"}, "domain=/abs/path"),
        ("T02-C006", {"domain": "", "login_url": LOGIN_URL, "username": "a", "password": "b"}, "domain=empty"),
        ("T02-C007", {"domain": "127.0.0.1:9102/../x", "login_url": LOGIN_URL, "username": "a", "password": "b"}, "domain=host/../x"),
        ("T02-C008", {"domain": DOMAIN, "login_url": "", "username": "a", "password": "b"}, "login_url=empty"),
    ]
    ev = []
    for cid, form, label in cases:
        st, body = post("/api/login/simple", form)
        d = jparse(body)
        rejected = (st == 400) or (d and d.get("success") is False)
        ev.append({"id": cid, "label": label, "status": st, "resp": d, "rejected": rejected})
        rec(cid, "PASS" if rejected else "FAIL", f"{label} -> status={st} success={d.get('success') if d else None}", "evidence/C004-C008_validation.json")
    save_evidence("C004-C008_validation.json", ev)


# ---------- C009 login_url non-http / other host (simple) ----------
def c_login_url_scheme():
    ev = []
    for cid, url, label in [
        ("T02-C009", "file:///etc/passwd", "file scheme"),
        ("T02-C010", "javascript:alert(1)", "javascript scheme"),
    ]:
        st, body = post("/api/login/simple", {"domain": DOMAIN, "login_url": url,
                                              "username": "admin", "password": SECRET})
        d = jparse(body)
        # expectation: should not succeed / no auth for a non-http login page
        safe = not (d and d.get("success") is True)
        ev.append({"id": cid, "label": label, "url": url, "status": st, "resp": d, "safe": safe})
        rec(cid, "PASS" if safe else "FAIL", f"{label} -> success={d.get('success') if d else None} err={mask(str(d.get('error') if d else ''))[:50]}", "evidence/C009-C010_login_url_scheme.json")
    save_evidence("C009-C010_login_url_scheme.json", ev)


# ---------- C011..C013 scrape ----------
def c_scrape():
    for cid, path, label, expect_pw in [
        ("T02-C011", "/login", "login form", True),
        ("T02-C012", "/mfa", "mfa form", True),
        ("T02-C013", "/form", "non-login form", False),
    ]:
        st, body = post("/api/login/scrape", {"url": f"{MOCK}{path}", "domain": DOMAIN})
        d = jparse(body)
        fields = d.get("fields", []) if d else []
        types = [f.get("field_type") for f in fields]
        has_pw = "password" in types
        save_evidence(f"C011-13_scrape_{path.strip('/')}.json", {"status": st, "resp": d})
        ok = bool(d and d.get("ok") is True and fields)
        rec(cid, "PASS" if ok else "FAIL",
            f"{label}: ok={d.get('ok') if d else None} n_fields={len(fields)} types={types} has_pw={has_pw}",
            f"evidence/C011-13_scrape_{path.strip('/')}.json")


# ---------- C014 scrape invalid ----------
def c_scrape_invalid():
    ev = []
    for cid, form, label in [
        ("T02-C014", {"url": "", "domain": DOMAIN}, "empty url"),
        ("T02-C015", {"url": f"{MOCK}/login", "domain": "../x"}, "bad domain"),
    ]:
        st, body = post("/api/login/scrape", form)
        d = jparse(body)
        rejected = st == 400 or (d and d.get("ok") is False)
        ev.append({"id": cid, "label": label, "status": st, "resp": d})
        rec(cid, "PASS" if rejected else "FAIL", f"{label} -> status={st}", "evidence/C014-C015_scrape_invalid.json")
    save_evidence("C014-C015_scrape_invalid.json", ev)


# ---------- C016..C021 submit ----------
def c_submit():
    good = json.dumps({"username": "admin", "password": SECRET})
    cur = f"{MOCK}/login"
    cases = [
        ("T02-C016", {"domain": DOMAIN, "current_url": cur, "fields_json": good}, "valid json (login)", "accept"),
        ("T02-C017", {"domain": DOMAIN, "current_url": cur, "fields_json": "{not json"}, "invalid json", "reject400"),
        ("T02-C018", {"domain": DOMAIN, "current_url": cur, "fields_json": json.dumps({"username": "admin", "password": SECRET, "evil": "x", "csrf": "y"})}, "extra keys", "accept"),
        ("T02-C019", {"domain": DOMAIN, "current_url": cur, "fields_json": json.dumps({"username": "A" * 200000, "password": SECRET})}, "huge value 200k", "accept-or-graceful"),
        ("T02-C020", {"domain": "../x", "current_url": cur, "fields_json": good}, "bad domain", "reject400"),
        ("T02-C021", {"domain": DOMAIN, "current_url": "", "fields_json": good}, "missing current_url", "reject400"),
    ]
    ev = []
    for cid, form, label, exp in cases:
        st, body = post("/api/login/submit", form)
        d = jparse(body)
        ev.append({"id": cid, "label": label, "expect": exp, "status": st, "resp": mask(json.dumps(d, ensure_ascii=False)) if d else body[:200]})
        if exp == "reject400":
            ok = st == 400 or (d and d.get("success") is False)
        elif exp == "accept":
            ok = st == 200 and d is not None and "success" in d
        else:  # graceful
            ok = st in (200, 400, 500, 504) and d is not None
        rec(cid, "PASS" if ok else "FAIL", f"{label} -> status={st} success={d.get('success') if d else None} err={mask(str(d.get('error') if d else ''))[:40]}", "evidence/C016-C021_submit.json")
    save_evidence("C016-C021_submit.json", ev)


# ---------- C022..C027 record start/status/complete/cancel/double/badpid ----------
def c_record():
    # ensure headless so no visible window pops on the operator's screen is NOT possible via route;
    # route always launches headful. We start, poll status, then cancel (clean up window).
    st1, b1 = post("/api/login/record/start", {"domain": DOMAIN, "login_url": LOGIN_URL})
    d1 = jparse(b1)
    pid = d1.get("pid") if d1 else None
    time.sleep(1.2)
    sst, sb = get(f"/api/login/record/status?domain={DOMAIN}")
    sd = jparse(sb)
    status_file = OUT / ".login_status.json"
    sf_content = status_file.read_text() if status_file.exists() else "(missing)"
    # double start while first running
    st2, b2 = post("/api/login/record/start", {"domain": DOMAIN, "login_url": LOGIN_URL})
    d2 = jparse(b2)
    pid2 = d2.get("pid") if d2 else None
    time.sleep(0.4)
    # cancel both
    canc = []
    for p in [pid, pid2]:
        if p:
            cst, cb = post("/api/login/record/cancel", {"pid": str(p)})
            canc.append({"pid": p, "status": cst, "resp": jparse(cb)})
    time.sleep(0.6)
    save_evidence("C022_record_flow.json", {
        "start1": {"status": st1, "resp": d1}, "status_poll": {"status": sst, "resp": sd},
        "status_file_content": sf_content, "double_start": {"status": st2, "resp": d2},
        "cancels": canc})
    rec("T02-C022", "PASS" if (d1 and d1.get("success") and pid) else "FAIL",
        f"start success={d1.get('success') if d1 else None} pid={pid}", "evidence/C022_record_flow.json")
    rec("T02-C023", "PASS" if (sd and sd.get("success") and sd.get("phase")) else "FAIL",
        f"status phase={sd.get('phase') if sd else None}", "evidence/C022_record_flow.json")
    rec("T02-C024", "PASS" if status_file.exists() else "FAIL",
        f".login_status.json exists={status_file.exists()} content={mask(sf_content)[:120]}", "evidence/C022_record_flow.json")
    rec("T02-C025", "PASS" if (d2 and d2.get("success") and pid2 and pid2 != pid) else "INFO",
        f"double start -> new pid={pid2} (no lock; second recorder spawned)", "evidence/C022_record_flow.json")
    rec("T02-C026", "PASS" if all(c["resp"] and c["resp"].get("success") for c in canc) else "FAIL",
        f"cancel results={[ (c['pid'], c['resp'].get('success') if c['resp'] else None) for c in canc]}", "evidence/C022_record_flow.json")

    # complete signal (idempotent touch) — use a scratch domain reuse
    est, eb = post("/api/login/record/complete", {"domain": DOMAIN})
    ed = jparse(eb)
    sig = OUT / ".login_signal"
    rec("T02-C027", "PASS" if (ed and ed.get("success") and sig.exists()) else "FAIL",
        f"complete success={ed.get('success') if ed else None} signal_exists={sig.exists()}", "evidence/C028_record_edge.json")
    # cleanup signal so it doesn't linger
    try:
        sig.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


# ---------- C028..C031 record edge: bad pid / nonexistent pid / status bad domain ----------
def c_record_edge():
    ev = {}
    st, b = post("/api/login/record/cancel", {"pid": "abc"})
    ev["nondigit_pid"] = {"status": st, "resp": jparse(b)}
    rec("T02-C028", "PASS" if st == 400 else "FAIL", f"non-digit pid -> status={st}", "evidence/C028_record_edge.json")
    st, b = post("/api/login/record/cancel", {"pid": "999999"})
    ev["nonexistent_pid"] = {"status": st, "resp": jparse(b)}
    d = jparse(b)
    rec("T02-C029", "PASS" if (d and d.get("success")) else "FAIL", f"nonexistent pid 999999 -> success={d.get('success') if d else None} (ProcessLookup swallowed)", "evidence/C028_record_edge.json")
    st, b = post("/api/login/record/cancel", {"pid": ""})
    ev["empty_pid"] = {"status": st, "resp": jparse(b)}
    rec("T02-C030", "PASS" if st == 400 else "FAIL", f"empty pid -> status={st}", "evidence/C028_record_edge.json")
    st, b = get(f"/api/login/record/status?domain=../x")
    ev["status_bad_domain"] = {"status": st, "resp": jparse(b)}
    rec("T02-C031", "PASS" if st == 400 else "FAIL", f"status bad domain -> status={st}", "evidence/C028_record_edge.json")
    save_evidence("C028_record_edge.json", ev)


def main():
    c_simple_happy()
    c_simple_invalid()
    c_leak()
    c_validation()
    c_login_url_scheme()
    c_scrape()
    c_scrape_invalid()
    c_submit()
    c_record()
    c_record_edge()
    save_evidence("_api_results.json", R)
    print(json.dumps({"total": len(R),
                      "PASS": sum(1 for x in R if x["result"] == "PASS"),
                      "FAIL": sum(1 for x in R if x["result"] == "FAIL"),
                      "OTHER": [x["id"] + ":" + x["result"] for x in R if x["result"] not in ("PASS", "FAIL")]},
                     ensure_ascii=False))
    for x in R:
        print(f"{x['id']}\t{x['result']}\t{x['observed']}")


if __name__ == "__main__":
    main()
