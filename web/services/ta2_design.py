"""System 02 テスト設計ボード: ケースごとの根拠要件・観点・期待結果・状態と、全体／今回の変更分の判定。

読み取り専用の導出が中心。書き込むのは判定基準（baseline）の記録だけで、tests.json は変更しない。
真実規律: 未実行は合格に数えない。期待結果が要確認のケースは判定に使えない（判定不能）。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from web.services import ta2_store as _ta2

_DA_PREFIX = "docassure-"
_KIND_LABEL = {"happy": "正常系", "boundary": "境界値", "permission": "権限", "negative": "異常系",
               "error": "エラー処理", "state": "状態遷移", "recovery": "復旧"}
_PROV_LABEL = {"DERIVED": "文書から導出", "INFERRED": "推論（要確認）", "OBSERVED": "観測"}
# 共通語彙（common-contract §2.1）
PASS, FAIL, UNDECIDABLE, UNJUDGED = "合格", "不合格", "判定不能", "未判定"


class BaselineConflict(Exception):
    """基準の記録が他の人と競合した（409）。"""


def is_docassure(domain: str) -> bool:
    return domain.startswith(_DA_PREFIX)


def origin_label(domain: str) -> str:
    if is_docassure(domain):
        return f"ドキュメント検証から受領（検証 {domain[len(_DA_PREFIX):]}）"
    return f"画面解析（{domain}）"


def baseline_path(domain: str) -> Path:
    return _ta2.base_dir(domain) / "design_baseline.json"


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def sources() -> list[dict[str, Any]]:
    root = _ta2._root()
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.iterdir()):
        if not (d / "ta2" / "tests.json").is_file():
            continue
        n = len(_ta2.load(d.name).get("tests") or [])
        out.append({"domain": d.name, "label": origin_label(d.name), "from_docverify": is_docassure(d.name),
                    "cases": n})
    return sorted(out, key=lambda s: (not s["from_docverify"], s["domain"]))


def _text_steps(t: dict) -> list[str]:
    raw = t.get("design_steps") or []
    if raw:
        return [str(s) for s in raw]
    out = []
    for s in t.get("steps") or []:
        if isinstance(s, dict):
            out.append(" ".join(str(s.get(k) or "") for k in ("action", "target", "arg")).strip())
    return out


def _expected(t: dict) -> str:
    if t.get("expected"):
        return str(t["expected"])
    for s in _text_steps(t):
        if s.startswith("Then "):
            return s[5:]
    asserts = [s for s in t.get("steps") or [] if isinstance(s, dict) and s.get("kind") == "assert"]
    if asserts:
        return "、".join(" ".join(str(a.get(k) or "") for k in ("target", "action", "arg")).strip() for a in asserts)
    return ""


def case_state(t: dict, expected: str) -> str:
    if not expected or "要確認" in expected:
        return "要確認"
    if not (t.get("last") or {}).get("at"):
        return "未実行"
    st = str(t.get("status") or "")
    if st == "pass":
        return "合格"
    if st == "fail":
        return "失敗"
    return "要確認"  # flaky・不明は確信できない


def _fingerprint(t: dict) -> str:
    keys = ("name", "requirement_id", "technique", "screen", "design_steps", "steps", "expected")
    blob = json.dumps({k: t.get(k) for k in keys}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _requirements(domain: str) -> tuple[dict[str, dict], dict[str, list[dict]], str]:
    """docassure 由来なら S06 の要件本文と指摘を読む（読み取りのみ）。"""
    if not is_docassure(domain):
        return {}, {}, ""
    iid = domain[len(_DA_PREFIX):]
    try:
        from web.services.docassure import store as _da
        from web.services.docassure.testability import unit_view
        r = _da.load(iid) or {}
    except Exception:  # noqa: BLE001  S06 側が読めなくても S02 の表示は止めない
        return {}, {}, "ドキュメント検証の結果を読めませんでした。根拠の本文は表示されません。"
    reqs: dict[str, dict] = {}
    for u in r.get("requirements") or []:
        try:
            v = unit_view(u)
        except Exception:  # noqa: BLE001
            continue
        reqs[str(v["requirement_id"])] = {"id": str(v["requirement_id"]), "text": str(v.get("raw_text") or "")}
    finds: dict[str, list[dict]] = {}
    for f in r.get("findings") or []:
        if not isinstance(f, dict):
            continue
        rid = str(f.get("requirement_id") or f.get("req_id") or "")
        if rid:
            finds.setdefault(rid, []).append({"id": str(f.get("id") or f.get("finding_id") or ""),
                                              "kind": str(f.get("title") or f.get("rule_id") or f.get("kind") or ""),
                                              "severity": str(f.get("severity") or "")})
    return reqs, finds, "" if r else "ドキュメント検証がまだ分析されていません。"


def _case(t: dict, reqs: dict, finds: dict, base: dict) -> dict[str, Any]:
    exp = _expected(t).replace("<要確認: ", "要確認: ").rstrip(">") if "<要確認" in _expected(t) else _expected(t)
    rid = str(t.get("requirement_id") or "")
    kind = str(t.get("technique") or "")
    fp = _fingerprint(t)
    return {"id": str(t.get("id") or ""), "case_id": str(t.get("case_id") or ""), "name": str(t.get("name") or ""),
            "requirement_id": rid, "requirement_text": (reqs.get(rid) or {}).get("text", ""),
            "findings": finds.get(rid, []), "viewpoint": _KIND_LABEL.get(kind, kind or "未設定"),
            "expected": exp, "steps": _text_steps(t), "state": case_state(t, exp),
            "basis": _PROV_LABEL.get(str(t.get("provenance") or ""), "観測（画面解析）" if not rid else "未設定"),
            "last_at": str((t.get("last") or {}).get("at") or ""),
            "changed": base.get(str(t.get("id"))) != fp, "fingerprint": fp}


def _gate(title: str, cases: list[dict], missing: list[str]) -> dict[str, Any]:
    by = {s: [c for c in cases if c["state"] == s] for s in ("合格", "失敗", "要確認", "未実行")}
    if not cases:
        verdict = UNJUDGED
    elif by["失敗"]:
        verdict = FAIL
    elif by["要確認"] or by["未実行"] or missing:
        verdict = UNDECIDABLE
    else:
        verdict = PASS
    name = lambda cs: [{"id": c["id"], "name": c["name"]} for c in cs]  # noqa: E731
    return {"title": title, "verdict": verdict, "total": len(cases), "passed": len(by["合格"]),
            "failed": name(by["失敗"]), "needs_check": name(by["要確認"]), "not_run": name(by["未実行"]),
            "missing_links": missing}


def board(domain: str) -> dict[str, Any]:
    tests = list(_ta2.load(domain).get("tests") or [])
    bl = _read(baseline_path(domain))
    base = bl.get("fingerprints") if isinstance(bl.get("fingerprints"), dict) else {}
    reqs, finds, note = _requirements(domain)
    cases = [_case(t, reqs, finds, base) for t in tests]
    covered = {c["requirement_id"] for c in cases if c["requirement_id"]}
    missing = [f"{rid}: テストケースがありません" for rid in sorted(set(reqs) - covered)]
    changed = [c for c in cases if c["changed"]]
    gone = sorted(set(base) - {c["id"] for c in cases})
    return {"domain": domain, "origin": origin_label(domain), "from_docverify": is_docassure(domain),
            "note": note, "cases": cases,
            "gates": [_gate("全体", cases, missing),
                      _gate("今回の変更分", changed, [f"{i}: 前回の基準から削除" for i in gone])],
            "baseline": {"at": bl.get("at", ""), "by": bl.get("by", ""), "history": bl.get("history", [])[-5:]},
            "changed_basis": "前回の基準" if bl else "基準が未記録のため全ケースを変更分として扱います"}


def record_baseline(domain: str, user: str, expected_at: str = "") -> dict[str, Any]:
    """現在の設計内容を「今回の変更分」の基準として記録する。expected_at が現行と違えば競合。"""
    path = baseline_path(domain)
    cur = _read(path)
    if expected_at and cur.get("at", "") != expected_at:
        raise BaselineConflict("他の人が先に基準を記録しました。画面を再読み込みしてから記録してください。")
    tests = list(_ta2.load(domain).get("tests") or [])
    at = _ta2._now()
    hist = list(cur.get("history") or []) + [{"at": at, "by": user, "cases": len(tests)}]
    data = {"at": at, "by": user, "fingerprints": {str(t.get("id")): _fingerprint(t) for t in tests},
            "history": hist[-50:]}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return {"at": at, "by": user, "cases": len(tests)}
