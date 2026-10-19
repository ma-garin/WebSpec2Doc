"""リバース解析（System 01）の根拠から、System 02 のテスト観点候補を作る。

入力は site_evidence() が返す dict（state が "ok" のときだけ使う）。
- 静的に宣言された route は「到達は未確認」のまま観点にする（到達済みと書かない）
- 静的 API の HTTP method が null なら「不明」のまま（GET 等を補完しない）
- 実測 API は既存の根拠なので増分に数えない。実測と同じ path の静的 API は
  「実測で確認済みの API の静的出典」として新規観点にしない
- 根拠の state は元のまま運ぶ（上げない）
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

SOURCE_LABEL = {"runtime": "実測由来", "static": "静的候補由来"}
STATE_LABEL = {
    "observed": "実行時に観測",
    "static": "静的に確認",
    "inferred": "推論",
    "ambiguous": "曖昧",
    "unknown": "不明",
    "unavailable": "利用不可",
}
NOT_PROBED_LABEL = "未探索"
RUNNABLE_LABEL = "実行対象（実測で到達）"
NO_EVIDENCE_NEXT = "System01 でリバース解析を実行すると観点が増えます"


def _norm_path(value: Any) -> str:
    """URL・クエリ・末尾スラッシュ違いを同じ path とみなすための正規化。"""
    text = str(value or "").strip()
    if not text:
        return ""
    parts = urlsplit(text)
    path = parts.path if (parts.scheme or parts.netloc or text.startswith("/")) else text.split("?", 1)[0]
    path = path.split("#", 1)[0]
    return path.rstrip("/") or "/"


def _method_text(method: Any) -> str:
    return str(method).upper() if method else "不明"


def _row(*, text: str, kind: str, source: str, state: str, evidence_id: Any,
         location: Any, claim: str, limitations: list[str], is_new: bool) -> dict:  # fmt: skip
    return {
        "text": text,
        "kind": kind,
        "source": source,
        "source_label": SOURCE_LABEL[source],
        "evidence_state": state,
        "evidence_state_label": STATE_LABEL.get(state, "不明"),
        "evidence_id": evidence_id,
        "location": location,
        "claim": claim,
        "limitations": list(limitations or []),
        "is_new": is_new,
    }


def _reach(probe: dict | None, evidence_id: Any) -> tuple[str, str]:
    """System 03 の到達確認結果（by_evidence）から (status, label)。結果が無ければ「未探索」。"""
    from web.services.static_route_probe_store import STATUS_LABEL

    item = (probe or {}).get(evidence_id)
    if not item or item.get("status") not in STATUS_LABEL:
        return "not_probed", NOT_PROBED_LABEL
    status = item["status"]
    if status == "observed":  # 認証状態を使ったかを文字で区別する（authenticated が無ければ未認証扱い）
        return status, "実測で到達（認証済み）" if item.get("authenticated") is True else "実測で到達（未認証）"
    if status == "auth_required" and item.get("auth_attempted") is True:
        return status, "保存済みの認証状態でも未確認"
    return status, STATUS_LABEL[status]


def _route_rows(evidence: list[dict], probe: dict | None = None) -> list[dict]:
    rows, seen = [], set()
    for e in evidence:
        if e.get("group") != "route" or e.get("origin") != "static":
            continue
        value = str(e.get("value") or "")
        if value in seen or not value or value.startswith("（"):  # 値を特定できない route は観点にしない
            continue
        seen.add(value)
        rows.append(_row(
            text=f"静的に宣言された画面ルート {value} に遷移できるか確認する（到達は未確認）",
            kind="route", source="static", state=e.get("state") or "unknown",
            evidence_id=e.get("id"), location=e.get("location"), claim=e.get("claim") or "",
            limitations=e.get("limitations"), is_new=True))  # fmt: skip
        status, label = _reach(probe, e.get("id"))
        row = rows[-1]
        row["reach_status"], row["reach_label"] = status, label
        row["runnable"] = status == "observed"  # 実測で到達した route だけ。source（由来）は static のまま
        row["reach_authenticated"] = row["runnable"] and ((probe or {}).get(e.get("id")) or {}).get("authenticated") is True
        if row["runnable"]:
            # 文言の「到達は未確認」を、System 03 の実測（GET の遷移で到達）に合わせて言い換える
            row["text"] = f"画面ルート {value} の表示と操作を確認する（System 03 が GET の遷移で到達を確認済み）"
            if row["reach_authenticated"]:
                row["text"] += "（認証状態を使用）"
            row["runnable_label"] = RUNNABLE_LABEL
            row["reach_observed_at"] = ((probe or {}).get(e.get("id")) or {}).get("observed_at")
    return rows


def _api_rows(evidence: list[dict]) -> tuple[list[dict], list[dict]]:
    """(観点の行, 実測と同じ path で新規にしなかった静的 API) を返す。"""
    runtime_paths: set[str] = set()
    rows: list[dict] = []
    for e in evidence:
        if e.get("group") == "api" and e.get("origin") == "runtime":
            runtime_paths.add(_norm_path(e.get("value")))
            value = str(e.get("value") or "")
            rows.append(_row(
                text=f"実測した API {_method_text(e.get('method'))} {value} の応答を確認する",
                kind="api", source="runtime", state=e.get("state") or "observed",
                evidence_id=e.get("id"), location=e.get("location"), claim=e.get("claim") or "",
                limitations=e.get("limitations"), is_new=False))  # fmt: skip
    covered, seen = [], set()
    for e in evidence:
        if e.get("group") != "api" or e.get("origin") != "static":
            continue
        path = _norm_path(e.get("value"))
        if path in runtime_paths:
            covered.append({"value": e.get("value"), "evidence_id": e.get("id"), "location": e.get("location"),
                            "note": "実測で確認済みの API の静的出典（新規観点には数えない）"})  # fmt: skip
            continue
        key = (path, e.get("method"))
        if key in seen:
            continue
        seen.add(key)
        rows.append(_row(
            text=f"API 呼び出し {e.get('value')} の正常/異常応答を確認する（HTTP method: {_method_text(e.get('method'))}）",
            kind="api", source="static", state=e.get("state") or "unknown",
            evidence_id=e.get("id"), location=e.get("location"), claim=e.get("claim") or "",
            limitations=e.get("limitations"), is_new=True))  # fmt: skip
    return rows, covered


def _module_rows(dependencies: list[dict]) -> list[dict]:
    rows, seen = [], set()
    for d in dependencies:
        if d.get("external"):
            continue
        src, dst = str(d.get("source") or ""), str(d.get("target") or "")
        if not src or not dst or (src, dst) in seen:
            continue
        seen.add((src, dst))
        rows.append(_row(
            text=f"モジュール {dst} を変更したとき {src} を使う画面の回帰を確認する（静的依存・実行は未証明）",
            kind="module", source="static", state=d.get("state") or "unknown",
            evidence_id=f"dep:{src}->{dst}", location=d.get("location"),
            claim=f"{src} が {dst} を {d.get('relation_label') or '依存'} している（静的に確認）",
            limitations=d.get("limitations"), is_new=True))  # fmt: skip
    return rows


# 「由来と根拠」の区分（C_CONTRACT の Evidence 語彙に対応）: (区分コード, 表示, WS2D.evidence の code)
ORIGIN_LABEL = {
    "existing_candidate": "元候補",
    "rea_added": "REA 追加",
    "static": "静的",
    "observed": "未認証実測",
    "observed_auth": "認証済み実測",
    "unverified": "未確認",
}
RESULT_LABEL = {"pass": "成功", "fail": "失敗", "flaky": "不安定"}
NOT_EXECUTED_LABEL = "未実行"


def _origin(row: dict) -> tuple[str, str]:
    """(区分コード, WS2D.evidence の code)。実測の格上げはしない（実測で到達した route だけ observed*）。"""
    if not row["is_new"]:
        return "existing_candidate", "observed"
    if row.get("runnable"):
        return ("observed_auth", "observed_auth") if row.get("reach_authenticated") else ("observed", "observed")
    if row.get("reach_status") in {"auth_required", "ambiguous", "failed"}:
        return "unverified", "unverified"  # System 03 で到達を確かめようとして確かめられなかった
    state = row["evidence_state"]
    if state == "static":
        return "static", "static"
    if state in {"inferred", "ambiguous"}:
        return "rea_added", state
    return "unverified", "unavailable" if state == "unavailable" else "unverified"


def _test_runs(tests: list | None) -> dict[str, list[dict]]:
    """実行記録のあるテストを evidence_id ごとに集める。リンク（evidence_id / viewpoint_id）が無いテストは対応させない。"""
    out: dict[str, list[dict]] = {}
    for t in tests or []:
        if not isinstance(t, dict):
            continue
        key = t.get("evidence_id") or t.get("viewpoint_id")
        last = t.get("last") if isinstance(t.get("last"), dict) else {}
        if key and t.get("status") in RESULT_LABEL and (last.get("run_id") or last.get("at")):
            out.setdefault(str(key), []).append({"status": t["status"], "at": str(last.get("at") or "")})
    return out


def _attach(rows: list[dict], tests: list | None) -> None:
    """各行に origin（由来と根拠）と execution（実行対象 / 実行済み）を付ける。tests が None なら実行済みは未計測。"""
    runs = _test_runs(tests)
    for r in rows:
        code, ev = _origin(r)
        r["origin"], r["origin_label"], r["ev_code"] = code, ORIGIN_LABEL[code], ev
        r["ev_category"] = {"observed": "fact", "observed_auth": "fact", "static": "inference",
                            "inferred": "inference", "ambiguous": "inference"}.get(ev, "unverified")  # fmt: skip
        found = sorted(runs.get(str(r.get("evidence_id")), []), key=lambda x: x["at"])
        if tests is None:
            ex = {"measured": False, "count": None, "last_result": None, "label": "未計測"}
        elif found:
            res = found[-1]["status"]
            ex = {"measured": True, "count": len(found), "last_result": res,
                  "label": f"{len(found)} 件・最終 {RESULT_LABEL[res]}"}  # fmt: skip
        else:
            ex = {"measured": True, "count": 0, "last_result": None, "label": NOT_EXECUTED_LABEL}
        ex["target"] = bool(r.get("runnable"))  # 実行対象（実測で到達）≠ 実行済み
        r["execution"] = ex


def build_viewpoints(rea: dict | None, before: int | None = None, probe: dict | None = None,
                     tests: list | None = None) -> dict:  # fmt: skip
    """site_evidence() の結果から観点候補と Before→After を作る。

    before: System 02 既存のテスト候補数。None なら実測 API 由来の数を Before とする。
    probe: System 03 の到達確認結果（static_route_probe_store.by_evidence）。省略時は全 route が「未探索」。
    tests: System 02 のテスト定義（ta2_store の tests）。None なら実行済みは未計測(None)、
        リストなら evidence_id / viewpoint_id で観点に結び付いた実行記録だけ数える（無ければ 0）。
    """
    if not rea or rea.get("state") != "ok":
        msg = (rea or {}).get("message") or "このサイトのリバース解析結果はまだありません。"
        return {"state": "no_evidence", "message": f"リバース解析の根拠なし（未確認）。{msg}",
                "next_action": NO_EVIDENCE_NEXT, "viewpoints": [], "covered_by_runtime": [],
                "metrics": {"before": before if before is not None else 0, "after": before if before is not None else 0,
                            "new": 0, "with_evidence": 0, "runnable": 0, "executed": None if tests is None else 0, "probed": 0, "before_basis": "既存テスト候補数" if before is not None else "未確認"}}  # fmt: skip
    evidence = rea.get("evidence") or []
    api_rows, covered = _api_rows(evidence)
    rows = _route_rows(evidence, probe) + api_rows + _module_rows(rea.get("dependencies") or [])
    _attach(rows, tests)
    new = [r for r in rows if r["is_new"]]
    if before is None:
        before, basis = sum(1 for r in rows if r["source"] == "runtime"), "実測 API 由来の観点数"
    else:
        basis = "既存のテスト候補数"
    return {
        "state": "ok",
        "next_action": None,
        "viewpoints": rows,
        "covered_by_runtime": covered,
        "metrics": {"before": before, "after": before + len(new), "new": len(new),
                    "with_evidence": sum(1 for r in new if r["evidence_id"]),
                    "runnable": sum(1 for r in new if r.get("runnable")),
                    "executed": None if tests is None else sum(1 for r in new if (r["execution"]["count"] or 0) > 0),
                    "probed": sum(1 for r in rows if r.get("kind") == "route" and r.get("reach_status") != "not_probed"),
                    "before_basis": basis},  # fmt: skip
        "last_run": rea.get("last_run"),
    }
