"""System 06 対検査レビュー API の通し確認（実サーバに対して叩く）。

順序: 検査前の判定 → analyze → GET findings → decide 3 件 → revoke 1 件 → gate → approve（未合格で 403 を期待）
      → 重大は不採用・他は採用 → gate → approve（合格で 200 を期待）→ trail。
結果を Markdown の表で標準出力へ出す。期待と違う行が 1 つでもあれば exit 1。

認証オフで起動したサーバでは、承認は常に 403 が正（CONTRACT: 認証オフは承認系 403）。
認証ありで確かめるときは --decider-cookie（採否する人）と --approver-cookie（別の承認者）を渡す。

使い方:
    venv/bin/python scripts/docverify_pair_smoke.py --base http://127.0.0.1:8769 [--iid v1-a-order-payment]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def call(base: str, method: str, path: str, body: dict | None = None, cookie: str = "") -> tuple[int, object]:
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw, code = r.read().decode(), r.status
    except urllib.error.HTTPError as e:
        raw, code = e.read().decode(), e.code
    except urllib.error.URLError as e:
        return 0, {"error": {"message": f"接続できません: {e.reason}"}}
    try:
        return code, json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return code, {"_raw": raw[:200]}


def _gate_pass(obj) -> bool | None:
    if not isinstance(obj, dict):
        return None
    gate = obj.get("gate", obj)
    overall = gate.get("overall") if isinstance(gate, dict) else None
    return overall.get("pass") if isinstance(overall, dict) else None


def _verdict(obj) -> str:
    gate = obj.get("gate", obj) if isinstance(obj, dict) else {}
    overall = gate.get("overall") if isinstance(gate, dict) else None
    return overall.get("verdict", "") if isinstance(overall, dict) else ""


def _err_note(obj) -> str:
    if not isinstance(obj, dict) or "error" not in obj:
        return ""
    err = obj["error"]
    return str(err.get("message", "") if isinstance(err, dict) else err)[:60]


def _actions(obj) -> set:
    items = obj if isinstance(obj, list) else (obj.get("trail", []) if isinstance(obj, dict) else [])
    return {t.get("action") for t in items if isinstance(t, dict)}


def run(base: str, iid: str, decider: str, approver: str) -> list[tuple]:
    p = f"/api/docverify/{iid}/pair"
    rows: list[tuple] = []
    auth_on = bool(decider and approver)

    def step(name, method, path, body, expect, cookie, check=None):
        code, obj = call(base, method, p + path, body, cookie)
        ok = code == expect and (check(obj) if check else True)
        rows.append((name, f"{method} {path}", expect, code, "OK" if ok else "NG", _err_note(obj)))
        return obj

    # 検査（assessment）が無いレビューは判定不能。合格には検査の実行が要る（pair_review._judge）
    step("判定（検査前は判定不能）", "GET", "/gate", None, 200, decider,
         lambda o: _gate_pass(o) is False or _verdict(o) == "判定不能")
    step("検査を実行", "POST", "/analyze", {}, 200, decider,
         lambda o: isinstance(o, dict) and (o.get("assessment") or {}).get("status") == "complete")
    obj = step("指摘の取得", "GET", "/findings", None, 200, decider,
               lambda o: isinstance(o, dict) and len(o.get("findings", [])) >= 12)
    items = obj.get("findings", []) if isinstance(obj, dict) else []
    fids = [f["id"] for f in items]
    critical = {f["id"] for f in items if f.get("severity") == "重大"}
    if len(fids) < 3:
        return rows
    body = {"status": "採用", "reason": "通し確認"}
    for fid in fids[:3]:
        step(f"採否 {fid}", "POST", f"/findings/{fid}/decide", body, 200, decider)
    step(f"取消 {fids[2]}", "POST", f"/findings/{fids[2]}/revoke", {}, 200, decider)
    step("判定（未合格）", "GET", "/gate", None, 200, decider, lambda o: _gate_pass(o) is False)
    step("承認（未合格）", "POST", "/approve", {"reason": "通し確認"}, 403, approver)
    # 重大は「採用」のままだと未解決として残る（pair_review._judge）。合格経路は重大を不採用にして確かめる
    for fid in fids:
        st = "不採用" if fid in critical else "採用"
        step(f"{st} {fid}", "POST", f"/findings/{fid}/decide", {"status": st, "reason": "通し確認"}, 200, decider)
        if st == "採用":  # 採用は「直す」の意味で未解消のまま残る。出口基準の上限に依らず通すため解消済みまで進める
            step(f"解消済み {fid}", "POST", f"/findings/{fid}/decide", {"status": "解消済み", "reason": "通し確認で修正済みとした"}, 200, decider)
    step("判定（合格）", "GET", "/gate", None, 200, decider, lambda o: _gate_pass(o) is True)
    if auth_on:
        step("承認（同一人物）", "POST", "/approve", {"reason": "通し確認"}, 403, decider)
    step("承認（合格）", "POST", "/approve", {"reason": "通し確認"}, 200 if auth_on else 403, approver)
    want = {"finding_decided", "decision_revoked"} | ({"approved"} if auth_on else set())
    step("証跡", "GET", "/trail", None, 200, decider, lambda o: want <= _actions(o))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://127.0.0.1:8769")
    ap.add_argument("--iid", default="v1-a-order-payment")
    ap.add_argument("--decider-cookie", default="")
    ap.add_argument("--approver-cookie", default="")
    a = ap.parse_args(argv)
    rows = run(a.base.rstrip("/"), a.iid, a.decider_cookie, a.approver_cookie)
    print("| 手順 | 要求 | 期待 | 実際 | 判定 | エラー文 |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        print("| " + " | ".join(str(c) for c in r) + " |")
    ng = sum(1 for r in rows if r[4] == "NG")
    print(f"\nOK={len(rows) - ng} / NG={ng}")
    return 1 if ng or not rows else 0


if __name__ == "__main__":
    sys.exit(main())
