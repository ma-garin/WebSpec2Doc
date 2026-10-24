"""System06 → System09（影響度分析）の結線。要件の差分を 09 の変更要求として投入し、分析して候補を返す。

影響範囲はすべて「候補」。09 が語の一致等で見つけたものだけを返し、見つからなかった範囲は
NOT_EVALUATED / NO_FINDING とする（影響なしとは言わない）。テナント境界は 09 の DB（テナント別）と
検査のサイドカー（doc_dir）が担う。
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from web.services.docverify import store as _dv

WIRED = True
_SIDECAR = "sys09_impact.json"
_ROUTE = re.compile(r"(?<![\w/.])/(?:api/)?[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_<>:\-{}]+)*")
_MODULE = re.compile(r"\b(?:[\w\-]+/)+[\w\-]+\.(?:py|js|ts|java|go|rb)\b|\b[\w\-]+\.(?:py|js|ts|java|go|rb)\b")
_PAGE_KINDS = ("requirement", "design", "screen", "other")


class Sys09Error(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "error"):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


def _clean(s: str, n: int = 160) -> str:
    return re.sub(r"[。\n\r「」]+", " ", str(s or "")).strip()[:n]


def change_text(diff_items: list[dict]) -> str:
    """意味差分 → 09 の変更指示文（1 文 = 1 変更）。位置だけの移動（MOVED）は変更にしない。"""
    out = []
    for d in diff_items:
        ch, rid = d.get("change"), str(d.get("requirement_id") or "")
        b = _clean(d.get("before_value") or (d.get("before") or {}).get("text"))
        a = _clean(d.get("after_value") or (d.get("after") or {}).get("text"))
        if ch == "REMOVED":
            out.append(f"{rid} {b} を削除する。")
        elif ch == "CREATED":
            out.append(f"{rid} {a} を追加する。")
        elif ch in ("MODIFIED", "SPLIT", "MERGED") and (a or b):
            out.append(f"{rid} 「{b}」から「{a}」に変更する。" if b and a else f"{rid} {a or b} を変更する。")
    return "\n".join(out)


def _path(iid: str) -> Path:
    return _dv.doc_dir(iid) / _SIDECAR


def _save(iid: str, data: dict) -> None:
    d = _path(iid).parent
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, _path(iid))
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def fetch_impact(iid: str) -> dict | None:
    """最新の結果。未実行なら None（空の成功を返さない）。"""
    p = _path(iid)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def _derive(rows: list[dict]) -> tuple[list, list, list, list]:
    docs: dict[str, dict] = {}
    tests: dict[str, dict] = {}
    modules: dict[str, dict] = {}
    routes: dict[str, dict] = {}
    for r in rows:
        src = {"item_code": r["item_code"], "document": r["document_name"], "confidence": r.get("confidence"),
               "evidence": r.get("evidence") or [], "method": r.get("method"), "priority": r.get("priority")}
        if r.get("doc_kind") == "testcase":
            tests.setdefault(r["item_code"], {"test": r["item_code"], "status": "CANDIDATE", "source": src,
                                              "text": r.get("text", "")})
        else:
            d = docs.setdefault(r["document_name"], {"document": r["document_name"], "kind": r.get("doc_kind"),
                                                     "status": "CANDIDATE", "items": []})
            d["items"].append({**src, "text": r.get("text", ""), "reason": r.get("impact_reason", "")})
        for t in r.get("tests") or []:
            tests.setdefault(t, {"test": t, "status": "CANDIDATE", "source": src, "text": ""})
        text = str(r.get("text") or "")
        for m in _MODULE.findall(text):
            modules.setdefault(m, {"module": m, "status": "CANDIDATE", "source": src, "basis": "文書の記述に現れた名前"})
        for m in _ROUTE.findall(text):
            if len(m) > 2:
                routes.setdefault(m, {"route": m, "status": "CANDIDATE", "source": src, "basis": "文書の記述に現れたパス"})
    return list(docs.values()), list(modules.values()), list(routes.values()), list(tests.values())


def _assemble(system: dict, cr: dict, changes: list[dict], rows: list[dict], engine: dict, corpus_docs: int) -> dict:
    documents, modules, routes, tests_ = _derive(rows)
    covered = {c for r in rows for c in (r.get("change_ids") or [])}
    ne: list[dict] = []
    if not changes:
        status = "NOT_EVALUATED"
        ne.append({"scope": "changes", "status": "NOT_EVALUATED", "reason": "変更を 09 が抽出できなかった。影響なしとは言えない"})
    elif corpus_docs == 0:
        status = "NOT_EVALUATED"
        ne.append({"scope": "corpus", "status": "NOT_EVALUATED",
                   "reason": "09 に検索先の文書（設計書・画面仕様書・テストケース）が無く、影響を評価できなかった"})
    else:
        status = "CANDIDATES" if rows else "NO_FINDING"
    for c in changes:
        if c["code"] not in covered and corpus_docs:
            ne.append({"scope": f"change:{c['code']}", "status": "NO_FINDING",
                       "reason": f"{c.get('location')} の変更は、09 の文書内に関連語を検出できなかった（影響なしの証明ではない）"})
    if not modules:
        ne.append({"scope": "modules", "status": "NOT_EVALUATED",
                   "reason": "09 は文書の語から推定するのみで、コードの依存解析はしていない"})
    if not routes:
        ne.append({"scope": "routes", "status": "NOT_EVALUATED",
                   "reason": "09 は文書の語から推定するのみで、ルート定義の解析はしていない"})
    return {"wired": WIRED, "status": status, "system_id": system["id"], "cr_code": cr["code"],
            "changes": [{"code": c["code"], "kind": c["kind"], "location": c.get("location"),
                         "before": c.get("before"), "after": c.get("after")} for c in changes],
            "affected": {"documents": documents, "modules": modules, "routes": routes, "tests": tests_},
            "not_evaluated": ne, "engine": engine, "candidates_only": True,
            "note": "影響範囲は候補。人の確認で確定する。"}


def submit_changes(iid: str, diff_items: list[dict], units: list, system_id: str | None = None,
                   actor: str = "local") -> dict:
    """差分を 09 の変更要求として起票 → 分析（外部送信なし）→ 結果を検査のサイドカーに保存して返す。"""
    from web.services.impact import db, roles
    from web.services.impact.engine import run
    from web.services.impact.repo import crs, impacts, systems
    from web.services.impact.repo.errors import ImpactError
    text = change_text(diff_items)
    if not text:
        raise Sys09Error("影響を調べる変更がありません（位置だけの移動は変更に数えません）。", 400, "no_changes")
    prev = fetch_impact(iid) or {}
    sid = system_id or prev.get("system_id")
    if not sid:
        raise Sys09Error("影響度分析（System09）の対象システムを指定してください。", 400, "no_system")
    conn = db.connect()
    try:
        try:
            roles.require(conn, sid, actor, "analyze")
            system = systems.get(conn, sid)
            dup = conn.execute("SELECT code FROM change_requests WHERE system_id=? AND title=? AND status IN ('draft','analyzing')",
                               (sid, f"System06 要件変更 {iid}")).fetchone()
            if dup:
                raise Sys09Error(f"同じ検査の変更要求 {dup[0]} が未完了のまま残っています。そちらを開いて確認してください。", 409, "duplicate_cr")
            cr = crs.create(conn, sid, f"System06 要件変更 {iid}", "System06 の意味差分から自動起票", text,
                            None, None, None, actor)
            res = run.analyze(conn, sid, cr["code"], actor, allow_send=False)
        except ImpactError as exc:
            raise Sys09Error(exc.message, exc.status, "sys09_error") from exc
        except run.AnalyzeError as exc:
            raise Sys09Error(str(exc), 404, "sys09_error") from exc
        cr_row = conn.execute("SELECT id FROM change_requests WHERE system_id=? AND code=?", (sid, cr["code"])).fetchone()
        rows = impacts.list(conn, cr_row["id"])
        chs = [dict(r) for r in conn.execute("SELECT * FROM changes WHERE cr_id=? ORDER BY code", (cr_row["id"],))]
        corpus = conn.execute("SELECT COUNT(*) FROM documents WHERE system_id=? AND kind IN ('design','screen','testcase','other')",
                              (sid,)).fetchone()[0]
    finally:
        conn.close()
    out = _assemble(system, cr, chs, rows, res["engine"] if isinstance(res, dict) else {}, corpus)
    _save(iid, out)
    return out
