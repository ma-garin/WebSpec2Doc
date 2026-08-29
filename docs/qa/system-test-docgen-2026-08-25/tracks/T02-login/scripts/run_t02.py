"""T02 主実行スクリプト（curl 相当＝urllib）。契約 login の failure_modes を実測する。
秘密値は evidence に平文で残さない（lib.mask / save_evidence が置換）。
使い方: venv/bin/python run_t02.py  （8765 と 9102 が稼働している前提）
出力: evidence/*.json と標準出力への 1 行結果。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import lib

R: list[dict] = []


def rec(cid: str, result: str, observed, evidence: str = "", note: str = "") -> None:
    R.append(
        {
            "case": cid,
            "result": result,
            "observed": observed,
            "evidence": evidence,
            "note": note,
        }
    )


def auth_cookies() -> list[str]:
    """auth.json のクッキー名一覧（値は読まない＝秘密を証跡化しない）。"""
    p = lib.OUT / "auth.json"
    if not p.exists():
        return ["<absent>"]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return [f"<unreadable:{e}>"]
    names = []
    for c in data.get("cookies", []):
        names.append(f"{c.get('name')}={'ok' if c.get('value')=='ok' else '<v>'}")
    return names or ["<no-cookies>"]


def auth_has_plaintext_secret() -> bool:
    p = lib.OUT / "auth.json"
    if not p.exists():
        return False
    return lib.SECRET in p.read_text(encoding="utf-8", errors="replace")


def save_masked_auth(name: str) -> str:
    p = lib.OUT / "auth.json"
    if not p.exists():
        (lib.EVID).mkdir(parents=True, exist_ok=True)
        (lib.EVID / name).write_text("<auth.json absent>", encoding="utf-8")
        return f"evidence/{name}"
    txt = p.read_text(encoding="utf-8", errors="replace")
    txt = txt.replace(lib.SECRET, "***MASKED***")
    (lib.EVID).mkdir(parents=True, exist_ok=True)
    (lib.EVID / name).write_text(txt, encoding="utf-8")
    return f"evidence/{name}"


def main() -> None:
    lib.EVID.mkdir(parents=True, exist_ok=True)

    # ---- 前提: 開始時点の auth.json 状態を記録 ----
    rec("PRE", "INFO", {"auth_json_exists": (lib.OUT / "auth.json").exists()})

    # ================= バリデーション（400） =================
    st, body = lib.post("/api/login/simple", {"domain": "", "login_url": lib.LOGIN_URL,
                                               "username": "admin", "password": lib.SECRET})
    rec("C009a_domain_empty", "PASS" if st == 400 else "FAIL",
        {"status": st, "body": lib.jparse(body)}, note="domain 空 → 400 期待")

    st, body = lib.post("/api/login/simple", {"domain": "../etc/passwd", "login_url": lib.LOGIN_URL,
                                              "username": "admin", "password": lib.SECRET})
    rec("C009b_domain_traversal", "PASS" if st == 400 else "FAIL",
        {"status": st, "body": lib.jparse(body)}, note="'../' 含むドメイン → 400 期待")

    st, body = lib.post("/api/login/simple", {"domain": lib.DOMAIN, "login_url": "",
                                              "username": "admin", "password": lib.SECRET})
    rec("C009c_loginurl_empty", "PASS" if st == 400 else "FAIL",
        {"status": st, "body": lib.jparse(body)}, note="login_url 空 → 400 期待")

    st, body = lib.post("/api/login/scrape", {"url": "", "domain": lib.DOMAIN})
    rec("C009d_scrape_url_empty", "PASS" if st == 400 else "FAIL",
        {"status": st, "body": lib.jparse(body)}, note="scrape url 空 → 400 期待")

    # ================= invalid_credentials =================
    st, body = lib.post("/api/login/simple", {"domain": lib.DOMAIN, "login_url": lib.LOGIN_URL,
                                              "username": "admin", "password": "wrong-pass"})
    j = lib.jparse(body) or {}
    auth_after_invalid = (lib.OUT / "auth.json").exists()
    ok = (st == 200 and j.get("success") is False and not auth_after_invalid)
    lib.save_evidence("c002_invalid_credentials.json",
                      {"status": st, "resp": j, "auth_json_created": auth_after_invalid,
                       "cookies": auth_cookies()})
    rec("C002_invalid_credentials", "PASS" if ok else "FAIL",
        {"status": st, "success": j.get("success"), "error": j.get("error"),
         "auth_json_created": auth_after_invalid},
        "evidence/c002_invalid_credentials.json",
        note="誤PW → success=false かつ auth.json を残さない")

    # ================= mfa_required（simple フローに /mfa を通す） =================
    st, body = lib.post("/api/login/simple", {"domain": lib.DOMAIN, "login_url": f"{lib.MOCK}/mfa",
                                              "username": "admin", "password": lib.SECRET})
    j = lib.jparse(body) or {}
    cookies_after_mfa = auth_cookies()
    mfa_auth_exists = (lib.OUT / "auth.json").exists()
    session_ok = any(c.startswith("session=ok") for c in cookies_after_mfa)
    ev = save_masked_auth("c004_mfa_auth_after.json")
    lib.save_evidence("c004_mfa_result.json",
                      {"status": st, "resp": j, "auth_json_created": mfa_auth_exists,
                       "cookies_in_auth": cookies_after_mfa, "authenticated_session": session_ok})
    # 期待: MFA 未完了なら success=false（またはsuccess時でも認証済セッションが無ければ欠陥）
    mfa_finding = bool(j.get("success")) and not session_ok
    rec("C004_mfa_required",
        "FAIL" if mfa_finding else ("PASS" if j.get("success") is False else "OBSERVE"),
        {"status": st, "success": j.get("success"), "error": j.get("error"),
         "auth_json_created": mfa_auth_exists, "authenticated_session": session_ok,
         "cookies": cookies_after_mfa},
        f"{ev}; evidence/c004_mfa_result.json",
        note="simple フローが MFA を扱えるか。success=true かつ session 未確立なら偽陽性(欠陥)")

    # mfa が auth.json を作った場合、後続 happy の判定汚染を避けるため削除
    if mfa_auth_exists and not session_ok:
        try:
            (lib.OUT / "auth.json").unlink()
        except OSError:
            pass

    # ================= simple happy_path =================
    st, body = lib.post("/api/login/simple", {"domain": lib.DOMAIN, "login_url": lib.LOGIN_URL,
                                              "username": "admin", "password": lib.SECRET})
    j = lib.jparse(body) or {}
    cookies = auth_cookies()
    plaintext = auth_has_plaintext_secret()
    session_ok = any(c.startswith("session=ok") for c in cookies)
    ev = save_masked_auth("c001_auth_masked.json")
    perm = ""
    p = lib.OUT / "auth.json"
    if p.exists():
        perm = oct(p.stat().st_mode & 0o777)
    lib.save_evidence("c001_simple_happy.json",
                      {"status": st, "resp": j, "cookies": cookies,
                       "auth_perm": perm, "plaintext_secret_in_auth": plaintext})
    ok = (j.get("success") is True and session_ok and not plaintext)
    rec("C001_simple_happy", "PASS" if ok else "FAIL",
        {"status": st, "success": j.get("success"), "session_ok": session_ok,
         "auth_perm": perm, "plaintext_secret_in_auth": plaintext},
        f"{ev}; evidence/c001_simple_happy.json",
        note="success=true / auth.json 生成 / session=ok / PW平文なし / 権限0600")

    # ================= scrape happy + display_missing =================
    st, body = lib.post("/api/login/scrape", {"url": lib.LOGIN_URL, "domain": lib.DOMAIN})
    j = lib.jparse(body) or {}
    ftypes = sorted({f.get("field_type") for f in (j.get("fields") or [])})
    has_pw = "password" in ftypes
    lib.save_evidence("c005a_scrape_login.json", {"status": st, "ok": j.get("ok"),
                                                  "field_types": ftypes, "n_fields": len(j.get("fields") or [])})
    rec("C005a_scrape_login", "PASS" if (j.get("ok") and has_pw) else "FAIL",
        {"status": st, "ok": j.get("ok"), "field_types": ftypes},
        "evidence/c005a_scrape_login.json", note="/login のフォーム項目（password 含む）抽出")

    st, body = lib.post("/api/login/scrape", {"url": f"{lib.MOCK}/about", "domain": lib.DOMAIN})
    j = lib.jparse(body) or {}
    lib.save_evidence("c005b_display_missing.json", {"status": st, "ok": j.get("ok"),
                                                     "error": j.get("error"), "n_fields": len(j.get("fields") or [])})
    # display_missing: フォームが無い → ok=false（fields 空）が期待の扱い
    rec("C005b_display_missing", "PASS" if (st == 200 and j.get("ok") is False) else "OBSERVE",
        {"status": st, "ok": j.get("ok"), "n_fields": len(j.get("fields") or [])},
        "evidence/c005b_display_missing.json", note="フォーム無しページ→ok=false（display_missing）")

    # ================= record: バリデーション・状態・pid 不正 =================
    st, body = lib.post("/api/login/record/start", {"domain": "", "login_url": lib.LOGIN_URL})
    rec("C006a_record_start_domain_empty", "PASS" if st == 400 else "FAIL",
        {"status": st, "body": lib.jparse(body)}, note="record/start domain 空 → 400")

    st, body = lib.get(f"/api/login/record/status?domain={lib.DOMAIN}")
    j = lib.jparse(body) or {}
    rec("C006b_record_status_default", "PASS" if (st == 200 and j.get("phase") == "waiting") else "OBSERVE",
        {"status": st, "phase": j.get("phase"), "success": j.get("success")},
        note="status 初期＝waiting（状態ファイル無し時のデフォルト）")

    # browser_closed 相当: pid 非数値 → 400、存在しない数値 pid → success（ProcessLookupError 握り）
    st, body = lib.post("/api/login/record/cancel", {"pid": "not-a-number"})
    rec("C008a_cancel_pid_nonnumeric", "PASS" if st == 400 else "FAIL",
        {"status": st, "body": lib.jparse(body)}, note="pid 非数値 → 400")

    st, body = lib.post("/api/login/record/cancel", {"pid": "2147483646"})
    j = lib.jparse(body) or {}
    rec("C008b_cancel_pid_nonexistent", "PASS" if (st == 200 and j.get("success")) else "OBSERVE",
        {"status": st, "success": j.get("success")},
        note="存在しない大 pid → ProcessLookupError 握りで success（安全側）")

    st, body = lib.post("/api/login/record/cancel", {"pid": ""})
    rec("C008c_cancel_pid_empty", "PASS" if st == 400 else "FAIL",
        {"status": st, "body": lib.jparse(body)}, note="pid 空 → 400")

    # ================= 出力 =================
    (lib.EVID / "run_summary.json").write_text(
        json.dumps(R, ensure_ascii=False, indent=2).replace(lib.SECRET, "***MASKED***"),
        encoding="utf-8")
    for r in R:
        print(json.dumps(r, ensure_ascii=False).replace(lib.SECRET, "***MASKED***"))


if __name__ == "__main__":
    main()
