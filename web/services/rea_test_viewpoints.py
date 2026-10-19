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


def _route_rows(evidence: list[dict]) -> list[dict]:
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


def build_viewpoints(rea: dict | None, before: int | None = None) -> dict:
    """site_evidence() の結果から観点候補と Before→After を作る。

    before: System 02 既存のテスト候補数。None なら実測 API 由来の数を Before とする。
    """
    if not rea or rea.get("state") != "ok":
        msg = (rea or {}).get("message") or "このサイトのリバース解析結果はまだありません。"
        return {"state": "no_evidence", "message": f"リバース解析の根拠なし（未確認）。{msg}",
                "next_action": NO_EVIDENCE_NEXT, "viewpoints": [], "covered_by_runtime": [],
                "metrics": {"before": before if before is not None else 0, "after": before if before is not None else 0,
                            "new": 0, "with_evidence": 0, "before_basis": "既存テスト候補数" if before is not None else "未確認"}}  # fmt: skip
    evidence = rea.get("evidence") or []
    api_rows, covered = _api_rows(evidence)
    rows = _route_rows(evidence) + api_rows + _module_rows(rea.get("dependencies") or [])
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
                    "with_evidence": sum(1 for r in new if r["evidence_id"]), "before_basis": basis},  # fmt: skip
        "last_run": rea.get("last_run"),
    }
