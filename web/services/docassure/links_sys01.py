"""System01（ドキュメント作成）の観測結果 report.json を、要件の Evidence candidate に結びつける。

- 取得元: テナント分離済みの出力ディレクトリ（scoped_output_dir）配下の <domain>/report.json
  （web/routes/history.py の /api/history と同じ保存先・同じ除外規則）。
- 観測できなかった≠存在しない。candidate は確定した追跡（confirmed trace）ではない。
"""
from __future__ import annotations

import json
from pathlib import Path

from web import config
from web.tenancy import TENANTS_DIR_NAME, scoped_output_dir
from web.validation import _valid_domain

from . import integrations

MIN_LABEL = 2
MAX_OBSERVED = 2000
LIMIT_SCOPE = "System01 が観測した画面の範囲のみ。未観測の領域に存在しないとは言えない"


def _out() -> Path:
    return scoped_output_dir(config.OUTPUT_DIR)


def _report(domain: str) -> dict | None:
    if not _valid_domain(domain):
        return None
    p = _out() / domain / "report.json"
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def list_sources() -> list[dict]:
    """tenant 内で紐付け可能な System01 スキャン（report.json を持つサイト）。"""
    base = _out()
    if not base.is_dir():
        return []
    out = []
    for d in sorted(base.iterdir(), key=lambda p: p.name):
        if (not d.is_dir() or d.name.startswith(".") or d.name == TENANTS_DIR_NAME
                or d.name == config.SAMPLE_DOMAIN):
            continue
        rep = _report(d.name)
        if rep is None:
            continue
        meta = rep.get("meta") or {}
        out.append({"source_id": d.name, "target_url": str(meta.get("target_url") or ""),
                    "crawled_at": str(meta.get("crawled_at") or ""),
                    "screens": int(meta.get("screen_count") or 0)})
    return out


def fetch_observed(source_id: str) -> list[dict] | None:
    """{kind,label,url,observed,limitation} のリスト。source が無ければ None（呼び出し側で 404）。"""
    rep = _report(source_id)
    if rep is None:
        return None
    meta = rep.get("meta") or {}
    items: list[dict] = []

    def add(kind: str, label, url: str, observed: bool = True, limitation: str = LIMIT_SCOPE):
        label = str(label or "").strip()
        if len(label) >= MIN_LABEL and len(items) < MAX_OBSERVED:
            items.append({"kind": kind, "label": label, "url": url, "observed": observed,
                          "limitation": limitation})

    for s in rep.get("screens") or []:
        if not isinstance(s, dict) or not s.get("is_canonical", True):
            continue
        url = str(s.get("url") or "")
        add("screen", s.get("title"), url)
        for h in s.get("headings") or []:
            add("heading", h, url)
        for b in s.get("buttons") or []:
            add("button", b if isinstance(b, str) else (b or {}).get("text"), url)
        for f in s.get("forms") or []:
            for fld in (f or {}).get("fields") or []:
                add("field", fld.get("label") or fld.get("name"), url)
    total, got = meta.get("target_url_count"), meta.get("page_count")
    if isinstance(total, int) and isinstance(got, int) and total > got:
        add("coverage", f"未観測 URL {total - got} 件", "", observed=False,
            limitation=f"指定 {total} 件中 {got} 件のみ観測（残りは取得できていない）")
    return items


def link(units: list, observed: list[dict], source_id: str = "", meta: dict | None = None) -> list[dict]:
    """要件ごとの Evidence candidate。観測できなければ NOT_OBSERVED（欠陥とは断定しない）。"""
    meta = meta or {}
    prov = {"system": "System01", "source_id": source_id, "report_hash": meta.get("report_hash", ""),
            "crawled_at": meta.get("crawled_at", ""), "match": "label-substring（推測。確定追跡ではない）"}
    al = integrations.alignment(units, observed)
    out: list[dict] = []
    matched: set[str] = set()
    for i, a in enumerate(al):
        eid = f"SYS01:{source_id}:{i + 1}"
        loc = {"url": a["url"], "kind": a["evidence_kind"], "label": a["label"]}
        for rid in a["requirement_ids"]:
            matched.add(rid)
            out.append({"requirement_id": rid, "evidence_id": eid, "state": a["status"],
                        "source": "System01", "location": loc, "limitation": a["limitation"] or LIMIT_SCOPE,
                        "provenance": prov, "confirmed": False})
        if a["status"] == "UNMATCHED_OBSERVATION":
            out.append({"requirement_id": None, "evidence_id": eid, "state": "UNMATCHED_OBSERVATION",
                        "source": "System01", "location": loc, "limitation": a["limitation"] or LIMIT_SCOPE,
                        "provenance": prov, "confirmed": False})
    for u in units:
        rid = integrations.unit_view(u)["requirement_id"]
        if rid not in matched:
            out.append({"requirement_id": rid, "evidence_id": "", "state": "NOT_OBSERVED",
                        "source": "System01", "location": {}, "provenance": prov, "confirmed": False,
                        "limitation": "System01 の観測に対応する語が見つからなかった。"
                                      "存在しない・欠陥とは言えない（観測範囲外の可能性）"})
    return out
