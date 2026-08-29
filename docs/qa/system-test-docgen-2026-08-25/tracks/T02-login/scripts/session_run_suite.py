"""T02 セッション期限切れ / 認証クロール連携 / login_urls 部分集合制限。
実行: venv/bin/python scripts/session_run_suite.py  （CWD=repo ルート）"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import DOMAIN, LOGIN_URL, MOCK, OUT, SECRET, get, jparse, post, save_evidence  # noqa: E402

R = []
def rec(cid, result, observed, evid=""):
    R.append({"id": cid, "result": result, "observed": observed, "evidence": evid})

AUTH = OUT / "auth.json"
AUTH_REL = f"output/{DOMAIN}/auth.json"
DASH = f"{MOCK}/dashboard"


def regen_auth():
    st, body = post("/api/login/simple", {"domain": DOMAIN, "login_url": LOGIN_URL,
                                          "username": "admin", "password": SECRET})
    d = jparse(body)
    cookies = json.loads(AUTH.read_text()).get("cookies", []) if AUTH.exists() else []
    names = [c.get("name") for c in cookies]
    return d, names


def run_crawl(auth_rel, tag):
    """POST /run (selected mode, single url=/dashboard). Return (full_stream, report_dir)."""
    form = {"urls": DASH, "format": "json", "crawl_mode": "selected", "auth": auth_rel,
            "max_pages": "3", "depth": "1"}
    st, body = post("/run", form, timeout=120)
    save_evidence(f"S_stream_{tag}.txt", body)
    report_path = ""
    for line in body.splitlines():
        if line.startswith("REPORT_PATH:"):
            report_path = line.split("REPORT_PATH:", 1)[1].strip()
    return st, body, report_path


def s_valid_auth_crawl():
    d, names = regen_auth()
    if "session" not in names:
        rec("T02-C036", "BLOCKED", f"auth regen produced cookies={names}; cannot test authed crawl", "")
        return
    st, body, rp = run_crawl(AUTH_REL, "valid")
    # find report.json in newest run dir and grep SECRET-AFTER-LOGIN
    secret_found = "SECRET-AFTER-LOGIN" in body
    report_hit = None
    newest = None
    dirs = sorted([p for p in OUT.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime)
    if dirs:
        newest = dirs[-1]
        for f in newest.rglob("*"):
            if f.is_file():
                try:
                    if "SECRET-AFTER-LOGIN" in f.read_text(errors="replace"):
                        report_hit = str(f.relative_to(OUT)); break
                except Exception:  # noqa: BLE001
                    pass
    save_evidence("S_valid_auth_crawl.json", {"status": st, "report_path": rp,
                                              "secret_in_stream": secret_found,
                                              "secret_in_report_file": report_hit,
                                              "newest_run_dir": str(newest) if newest else None,
                                              "login_wall_in_stream": "login_wall" in body or "ログイン" in body})
    ok = secret_found or bool(report_hit)
    rec("T02-C036", "PASS" if ok else "FAIL",
        f"authed /dashboard crawl: SECRET-AFTER-LOGIN in_stream={secret_found} in_report={report_hit}",
        "evidence/S_valid_auth_crawl.json")


def s_session_expired():
    # tamper the cookie value to an invalid one (own track output only)
    data = json.loads(AUTH.read_text())
    tampered = 0
    for c in data.get("cookies", []):
        if c.get("name") == "session":
            c["value"] = "INVALID-EXPIRED"; tampered += 1
    AUTH.write_text(json.dumps(data))
    st, body, rp = run_crawl(AUTH_REL, "expired")
    # session expiry indicators: login_wall event, session expired error, or SECRET absent
    secret_found = "SECRET-AFTER-LOGIN" in body
    wall = ("login_wall" in body) or ("SessionExpired" in body) or ("セッション" in body) or ("ログイン" in body and not secret_found)
    save_evidence("S_session_expired.json", {"status": st, "tampered_cookies": tampered,
                                             "secret_in_stream": secret_found,
                                             "login_wall_or_expiry_signal": wall,
                                             "stream_tail": body[-600:]})
    # expected: with invalid cookie, /dashboard becomes login wall -> SECRET must NOT be reachable
    ok = (not secret_found) and wall
    rec("T02-C037", "PASS" if ok else "FAIL",
        f"expired cookie crawl: SECRET_reachable={secret_found} wall/expiry_signal={wall}",
        "evidence/S_session_expired.json")


def s_login_urls_subset():
    # urls has only /dashboard; login_urls includes an out-of-set URL -> must be dropped
    evil = f"{MOCK}/evil-not-in-urls"
    form = {"urls": DASH, "login_urls": f"{DASH},{evil}", "format": "json",
            "crawl_mode": "selected", "max_pages": "2", "depth": "1"}
    st, body = post("/run", form, timeout=120)
    time.sleep(0.5)
    sst, sbody = get(f"/api/site?domain={DOMAIN}")
    sd = jparse(sbody)
    stored = ""
    if isinstance(sd, dict):
        stored = sd.get("login_urls") or sd.get("site", {}).get("login_urls", "")
    save_evidence("S_login_urls_subset.json", {"sent_login_urls": f"{DASH},{evil}",
                                              "site_status": sst, "stored_login_urls": stored,
                                              "site_json_keys": list(sd.keys()) if isinstance(sd, dict) else None})
    evil_present = evil in json.dumps(sd, ensure_ascii=False) if sd else False
    rec("T02-C038", "PASS" if not evil_present else "FAIL",
        f"out-of-set login_url dropped: evil_present_in_site={evil_present} stored={str(stored)[:80]}",
        "evidence/S_login_urls_subset.json")


def main():
    s_valid_auth_crawl()
    s_session_expired()
    s_login_urls_subset()
    # restore a valid auth for downstream/clean state
    regen_auth()
    save_evidence("_session_run_results.json", R)
    for x in R:
        print(f"{x['id']}\t{x['result']}\t{x['observed']}")


if __name__ == "__main__":
    main()
