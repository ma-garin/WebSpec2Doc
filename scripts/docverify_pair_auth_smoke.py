"""System 06 対検査レビュー: 認証ありの承認フローを 2 利用者の実ログインで通す。

使い方（worktree の直下で。サーバは認証 auto・自前の instance/ で起動しておく）:
  venv/bin/python scripts/docverify_pair_auth_smoke.py <A_order_payment dir> [--base http://127.0.0.1:8771]
初期管理者 admin/password でログインし、利用者 A（レビュアー）と B（承認者）を作る。
seed はテナント（slug）の保存先へ in-process で投入する。認証オフの 403 は test_client で確かめる。
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ROWS: list[tuple] = []
A_NAME, B_NAME = "検証レビュアーA", "検証承認者B"


def check(step: str, resp, expect: int, code: str | None = None) -> dict:
    try:
        body = resp.get_json() if hasattr(resp, "get_json") else resp.json()
    except Exception:
        body = {}
    body = body if isinstance(body, dict) else {"_": body}
    status = resp.status_code
    got_code = (body.get("error") or {}).get("code") if isinstance(body.get("error"), dict) else None
    ok = status == expect and (code is None or got_code == code)
    msg = (body.get("error") or {}).get("message", "") if isinstance(body.get("error"), dict) else ""
    ROWS.append((step, expect if code is None else f"{expect} {code}", f"{status} {got_code or ''}".strip(), "PASS" if ok else "FAIL", msg))
    return body


def assert_row(step: str, cond: bool, detail: str) -> None:
    ROWS.append((step, "真", "真" if cond else "偽", "PASS" if cond else "FAIL", detail))


def login(base: str, email: str, password: str) -> tuple[requests.Session, dict]:
    s = requests.Session()
    r = s.post(f"{base}/auth/login", data={"email": email, "password": password}, allow_redirects=False)
    if r.status_code not in (302, 303):
        raise SystemExit(f"ログイン失敗 {email}: {r.status_code}")
    tenants = s.get(f"{base}/api/auth/tenants").json()
    rows = tenants.get("tenants") or tenants.get("memberships") or [] if isinstance(tenants, dict) else tenants
    t = next(x for x in rows if isinstance(x, dict) and (x.get("id") or x.get("tenant_id")))
    tenant = {"id": t.get("id") or t.get("tenant_id"), "slug": t.get("slug") or t.get("tenant_slug") or "default"}
    r = s.post(f"{base}/auth/tenant", data={"tenant_id": tenant["id"]}, allow_redirects=False)
    if r.status_code not in (302, 303) or "error" in r.headers.get("Location", ""):
        raise SystemExit(f"テナント選択失敗 {email}: {r.status_code} {r.headers.get('Location')}")
    return s, tenant


def seed_in_tenant(iid: str, src: Path, slug: str | None) -> None:
    from flask import Flask, g

    from scripts.docverify_pair_seed import apply_test_marks
    from web.services.docverify import pair_review

    with Flask("seed").test_request_context():
        if slug:
            g.tenant = {"slug": slug}
        pair_review.seed(iid, src, "_seed")
        apply_test_marks(iid)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--base", default="http://127.0.0.1:8771")
    a = ap.parse_args()
    base, src, tag = a.base.rstrip("/"), Path(a.src), secrets.token_hex(3)

    admin, tenant = login(base, "admin", "password")
    for email, name in ((f"a-{tag}@example.com", A_NAME), (f"b-{tag}@example.com", B_NAME)):
        check(f"利用者作成 {name}", admin.post(f"{base}/api/auth/users", json={"email": email, "name": name, "password": "pw-smoke", "role": "member"}), 200)
    sa, _ = login(base, f"a-{tag}@example.com", "pw-smoke")
    sb, _ = login(base, f"b-{tag}@example.com", "pw-smoke")

    iid = f"auth-smoke-{tag}"
    seed_in_tenant(iid, src, tenant["slug"])
    p = f"{base}/api/docverify/{iid}/pair"

    check("未ログインで承認", requests.post(f"{p}/approve", json={"reason": "x"}), 401)
    body = check("A が一覧を開く（起票者になる）", sa.get(f"{p}/findings"), 200)
    findings = body.get("findings", [])
    check("A 承認（未合格）", sa.post(f"{p}/approve", json={"reason": "未合格で承認"}), 403, "gate_not_passed")
    for f in findings:
        if f["severity"] == "重大":
            check(f"A 不採用 {f['id']}", sa.post(f"{p}/findings/{f['id']}/decide", json={"status": "不採用", "reason": "検証: 指摘に当たらない"}), 200)
        else:
            sa.post(f"{p}/findings/{f['id']}/decide", json={"status": "採用", "reason": ""})
            check(f"A 解消済み {f['id']}", sa.post(f"{p}/findings/{f['id']}/decide", json={"status": "解消済み", "reason": "検証: 設計書を修正"}), 200)
    g = check("判定", sa.get(f"{p}/gate"), 200)
    assert_row("判定が合格", bool((g.get("overall") or {}).get("pass")), "; ".join(g.get("reasons", [])))
    check("A 承認（起票者本人）", sa.post(f"{p}/approve", json={"reason": "本人承認"}), 403, "same_person")
    check("B 承認（理由なし）", sb.post(f"{p}/approve", json={"reason": " "}), 400, "reason_required")
    check("B 承認", sb.post(f"{p}/approve", json={"reason": "対検査の結果を確認した"}), 200)
    trail = check("証跡", sb.get(f"{p}/trail"), 200)
    rows = trail.get("_", []) if isinstance(trail, dict) else []
    ap_row = next((t for t in reversed(rows) if t.get("action") == "approved"), {})
    starter = next((t for t in rows if t.get("action") == "review_started" and t.get("user") != "_seed"), {})
    assert_row("証跡の承認者＝B の表示名", ap_row.get("user") == B_NAME, f"approved.user={ap_row.get('user')}")
    assert_row("証跡の起票者＝A の表示名", starter.get("user") == A_NAME, f"review_started.user={starter.get('user')}")
    check("A 承認取消（承認者でない）", sa.post(f"{p}/approve/revoke", json={"reason": "取消"}), 403, "not_approver")
    check("B 承認取消（理由なし）", sb.post(f"{p}/approve/revoke", json={"reason": ""}), 400, "reason_required")
    check("B 承認取消", sb.post(f"{p}/approve/revoke", json={"reason": "再確認のため取消"}), 200)
    check("B 再取消（承認なし）", sb.post(f"{p}/approve/revoke", json={"reason": "再"}), 400, "not_approved")

    # 認証オフ: 実ルートを test_client で通す（保存先はテナント無しの data/docverify/）
    os.environ["WEBSPEC2DOC_AUTH_MODE"] = "off"
    os.environ.setdefault("FLASK_TESTING", "1")
    from web import create_app
    iid_off = f"auth-off-{tag}"
    seed_in_tenant(iid_off, src, None)
    c = create_app().test_client()
    c.get(f"/api/docverify/{iid_off}/pair/findings")
    check("認証オフで承認", c.post(f"/api/docverify/{iid_off}/pair/approve", json={"reason": "x"}), 403, "auth_required")

    print("| 手順 | 期待 | 実際 | 判定 | メッセージ |\n|---|---|---|---|---|")
    for r in ROWS:
        print("| " + " | ".join(str(x) for x in r) + " |")
    n_fail = sum(r[3] == "FAIL" for r in ROWS)
    print(f"\nPASS={len(ROWS) - n_fail} / FAIL={n_fail}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
