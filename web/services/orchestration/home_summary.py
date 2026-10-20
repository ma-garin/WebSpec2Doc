"""指揮ホーム（日常運用）用の全サイト集計。読み取りのみ。

既存の workflow_view の関数を束ねて、全サイトの状態・件数・各 System への
リンクを 1 回で返す。取れなかった値は null（0 と区別する。推測で埋めない）。
取得に失敗した源は partial_errors に名前を残し、その源に依存する値だけ null にする。

null になる指標:
- changes_today / latest_change: 変更を日付つきで返す集計源が無い。
- unverified / evidence: リバース解析（REA）の結果があるサイトだけ数える。1 件も無ければ null。
  結果の無いサイトの数は unanalyzed に出す（保存ビュー「未確認」にも含める）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from web.services.healing import report_doc
from web.services.orchestration import conductor, workflow_view
from web.services.orchestration.run_store import ConductorRun

logger = logging.getLogger(__name__)

VIEWS = ("all", "human", "failed", "unverified")

#: 指揮の run 状態 → 共通部品（WS2D.status）の工程 code。
_RUN_STATUS_CODE = {
    "queued": "preparing", "running": "running", "waiting_human": "waiting_review",
    "succeeded": "done", "failed": "failed", "cancelled": "cancelled", "skipped": "partial",
}

# 区分は共通部品 WS2D.evidence.category（static/js/c-hybrid.js）と同じ。
# 文書の記述は動作の観測ではないので推論、曖昧は確かめられていないので未確認。
_FACT_STATES = frozenset({"observed", "observed_auth", "record"})
_INFERENCE_STATES = frozenset({"document", "static", "inferred"})
_UNVERIFIED_STATES = frozenset({"ambiguous", "unverified", "unavailable"})

_RUN_STEP_TO_STAGE = workflow_view._AGENT_OF_STEP  # noqa: SLF001
_STAGE_LABEL = dict(workflow_view._STEP_DEFS)  # noqa: SLF001


def _today_prefix() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _is_today(ts: str) -> bool:
    return str(ts or "").startswith(_today_prefix())


def _quote(domain: str) -> str:
    from urllib.parse import quote

    return quote(domain, safe=":")


def _links(domain: str, has_report: bool) -> dict[str, str | None]:
    """各 System の実在 URL。解析結果が無いサイトの仕様/テスト画面は / へ戻されるので null。"""
    q = _quote(domain)
    return {
        "s01": f"/sites/{q}/spec" if has_report else None,
        "s02": f"/sites/{q}/tests" if has_report else None,
        "s03": f"/auto-run?site={q}",  # 入口でサイトを選び直させない（static/js/autorun-deeplink.js）
        "s09": "/impact",
        "s05": "/healing",
    }


def _stage_of(run: ConductorRun | None) -> dict[str, str] | None:
    if run is None:
        return None
    if run.status == "succeeded":
        return {"key": "finished", "label": "完了"}
    index = int(run.step_index or 0)
    if not 0 <= index < len(run.steps):
        return None
    key = _RUN_STEP_TO_STAGE.get(run.steps[index].name)
    return {"key": key, "label": _STAGE_LABEL[key]} if key in _STAGE_LABEL else None


def classify_evidence(items: list[dict[str, Any]]) -> dict[str, int]:
    """REA の evidence 配列を 事実／推論／未確認 に数える（曖昧・未知の state は未確認）。"""
    out = {"fact": 0, "inference": 0, "unverified": 0}
    for item in items:
        state = str(item.get("state") or "")
        if state in _FACT_STATES:
            out["fact"] += 1
        elif state in _INFERENCE_STATES:
            out["inference"] += 1
        else:
            out["unverified"] += 1
    return out


def _site_evidence(domain: str) -> tuple[dict[str, int] | None, bool]:
    """(件数 or None, 取得失敗か)。結果が無い・対象不一致は None（失敗ではない）。"""
    try:
        from web.routes.reverse_analysis import site_evidence

        res = site_evidence(domain)
    except Exception:  # noqa: BLE001 - 根拠の源が落ちても一覧は出す
        logger.exception("home_summary: evidence の取得に失敗 %s", domain)
        return None, True
    if res.get("state") != "ok":
        return None, False
    return classify_evidence(_with_route_probe(domain, list(res.get("evidence") or []))), False


# System 03 の到達確認の結果で、静的 route 候補の区分を実測どおりに置き換える。
# 到達を実測した（到達・未到達）→ 事実、確かめられなかった（認証・曖昧・失敗）→ 未確認、未探索 → 静的のまま。
_PROBE_TO_STATE = {"observed": "observed", "unreached": "observed",
                   "auth_required": "unverified", "ambiguous": "unverified", "failed": "unverified"}


def _with_route_probe(domain: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        from web.config import OUTPUT_DIR
        from web.services import static_route_probe_store as store
        from web.tenancy import scoped_output_dir

        probe = store.by_evidence(store.load(scoped_output_dir(OUTPUT_DIR), domain))
    except Exception:  # noqa: BLE001 - 探索結果が読めなくても REA の区分はそのまま出す
        logger.exception("home_summary: route probe の取得に失敗 %s", domain)
        return items
    out = []
    for item in items:
        hit = probe.get(item.get("id")) if item.get("group") == "route" else None
        state = _PROBE_TO_STATE.get((hit or {}).get("status", ""))
        out.append({**item, "state": state} if state else item)
    return out


class _Sources:
    """源ごとの読み取りと、失敗した源名の記録。"""

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self.errors: list[str] = []

    def fail(self, name: str) -> None:
        if name not in self.errors:
            self.errors.append(name)

    def sites(self) -> list[dict[str, str]]:
        try:
            return workflow_view._list_sites(self.out_dir)  # noqa: SLF001
        except Exception:  # noqa: BLE001
            logger.exception("home_summary: サイト一覧の取得に失敗")
            self.fail("sites")
            return []

    def projects(self) -> dict[str, str] | None:
        """domain → project_id。取れなければ None。"""
        try:
            from web.services.healing import project_store

            return {p.domain: p.project_id for p in project_store.list_projects(self.out_dir)}
        except Exception:  # noqa: BLE001
            logger.exception("home_summary: プロジェクトの取得に失敗")
            self.fail("projects")
            return None

    def run_of(self, domain: str) -> tuple[ConductorRun | None, bool]:
        try:
            return workflow_view._latest_run(self.out_dir, domain), False  # noqa: SLF001
        except Exception:  # noqa: BLE001
            logger.exception("home_summary: 実行記録の取得に失敗 %s", domain)
            self.fail("runs")
            return None, True

    def awaiting(self, project_id: str) -> int | None:
        if not project_id:
            return 0
        try:
            return len(workflow_view._awaiting_reports(self.out_dir, project_id))  # noqa: SLF001
        except Exception:  # noqa: BLE001
            logger.exception("home_summary: 報告書の取得に失敗")
            self.fail("reports")
            return None

    def failures(self, domain: str) -> int | None:
        from web.services.healing import autorun_bridge

        try:
            return len(autorun_bridge.load_failures(self.out_dir, domain))
        except Exception:  # noqa: BLE001
            logger.exception("home_summary: 失敗テストの取得に失敗 %s", domain)
            self.fail("failures")
            return None

    def reports_today(self) -> int | None:
        try:
            return sum(
                1 for r in report_doc.list_reports(self.out_dir, limit=1000)
                if _is_today(r.created_at)
            )
        except Exception:  # noqa: BLE001
            logger.exception("home_summary: 報告書の件数取得に失敗")
            self.fail("reports")
            return None


def _human_action(run: ConductorRun | None, awaiting: int | None) -> dict[str, Any] | None:
    if awaiting:
        return {"text": f"承認待ちの報告書が {awaiting} 件あります", "href": "/healing",
                "kind": "approval", "count": awaiting}
    if run is not None and run.status == "waiting_human":
        text = run.human_action
        if not text and 0 <= int(run.step_index or 0) < len(run.steps):
            text = run.steps[int(run.step_index)].human_action
        return {"text": text or "確認が必要です", "kind": "review", "count": 1,
                "href": f"/orchestration?site={_quote(run.domain)}"}
    return None


def _latest_failure(domain: str, run: ConductorRun | None, failures: int | None) -> dict[str, Any] | None:
    href = f"/orchestration?site={_quote(domain)}"
    if failures:
        return {"at": None, "text": f"失敗したテストが {failures} 件あります", "href": "/auto-run"}
    if run is not None and run.status == "failed":
        return {"at": run.finished_at or run.started_at or None,
                "text": run.error or "指揮の実行が失敗しました", "href": href}
    return None


def _build_site(src: _Sources, site: dict[str, str], projects: dict[str, str] | None) -> dict[str, Any]:
    domain = site["domain"]
    run, _run_failed = src.run_of(domain)
    has_report = (src.out_dir / domain / "report.json").is_file()
    awaiting = src.awaiting(projects.get(domain, "")) if projects is not None else None
    failures = src.failures(domain)
    evidence, ev_failed = _site_evidence(domain)
    if ev_failed:
        src.fail("evidence")

    status = _RUN_STATUS_CODE.get(run.status, "unverified") if run is not None else "not_started"
    if status == "waiting_review" and awaiting:
        status = "waiting_approval"
    if failures and status not in ("running", "preparing"):
        status = "failed"
    last_at = (run.finished_at or run.started_at) if run is not None else ""
    return {
        "domain": domain,
        "label": site.get("label") or domain,
        "status": status,
        "stage": _stage_of(run),
        "last_run": ({"at": last_at or None, "status": run.status} if run is not None else None),
        "evidence": ({"fact": evidence["fact"], "inference": evidence["inference"],
                      "unverified": evidence["unverified"]} if evidence else None),
        "human_action": _human_action(run, awaiting),
        "latest_change": None,
        "latest_failure": _latest_failure(domain, run, failures),
        "awaiting_reports": awaiting,
        "failure_count": failures,
        "links": _links(domain, has_report),
    }


def _sum_or_null(values: list[int | None]) -> int | None:
    if any(v is None for v in values):
        return None
    return sum(v for v in values if v is not None)


def _counts(src: _Sources, sites: list[dict[str, Any]], sites_ok: bool) -> dict[str, int | None]:
    if not sites_ok:
        return dict.fromkeys(
            ("sites", "ok", "running", "failed", "human_action", "awaiting_approval", "unverified",
             "unanalyzed", "changes_today", "tests_today", "fixes_today", "reports_today"), None)
    ev = [s["evidence"] for s in sites if s["evidence"] is not None]
    steps_today = _steps_today(src)
    return {
        "sites": len(sites),
        "ok": sum(1 for s in sites if s["status"] == "done"),
        "running": sum(1 for s in sites if s["status"] in ("running", "preparing")),
        "failed": sum(1 for s in sites if s["status"] == "failed"),
        "human_action": sum(1 for s in sites if s["human_action"]),
        "awaiting_approval": _sum_or_null([s["awaiting_reports"] for s in sites]),
        "unverified": sum(e["unverified"] for e in ev) if ev else None,
        # 根拠（REA）の結果が無く、根拠の健全性を確かめられていないサイトの数
        "unanalyzed": sum(1 for s in sites if s["evidence"] is None),
        "changes_today": None,
        "tests_today": steps_today.get("run") if steps_today is not None else None,
        "fixes_today": steps_today.get("healing") if steps_today is not None else None,
        "reports_today": src.reports_today(),
    }


def _steps_today(src: _Sources) -> dict[str, int] | None:
    """今日始まった指揮の段（run=実行 / healing=直す）の数。件数は「実行の回数」で、テスト本数ではない。"""
    try:
        runs = conductor.list_summaries(src.out_dir, limit=400)
    except Exception:  # noqa: BLE001
        logger.exception("home_summary: 実行履歴の取得に失敗")
        src.fail("runs")
        return None
    out: dict[str, int] = {"run": 0, "healing": 0}
    for r in runs:
        if not _is_today(str(r.get("started_at") or "")):
            continue
        for step in r.get("steps") or []:
            name = step.get("name")
            if name in out and step.get("status") not in ("queued", "skipped", ""):
                out[name] += 1
    return out


def filter_sites(sites: list[dict[str, Any]], view: str) -> list[dict[str, Any]]:
    """保存ビューの絞り込み。未知の view は all と同じ。"""
    if view == "human":
        return [s for s in sites if s["human_action"]]
    if view == "failed":
        return [s for s in sites if s["status"] == "failed" or s["latest_failure"]]
    if view == "unverified":
        # 根拠の結果が無いサイトも一覧では「未確認（解析結果なし）」と出すので、ここに含める
        return [s for s in sites
                if s["status"] == "unverified" or s["evidence"] is None or s["evidence"]["unverified"] > 0]
    return list(sites)


def build(out_dir: Path, view: str = "all") -> dict[str, Any]:
    src = _Sources(Path(out_dir))
    sites_raw = src.sites()
    sites_ok = "sites" not in src.errors
    projects = src.projects() if sites_raw else {}
    sites = [_build_site(src, s, projects) for s in sites_raw]
    counts = _counts(src, sites, sites_ok)
    chosen = view if view in VIEWS else "all"
    return {
        "view": chosen,
        "counts": counts,
        "sites": filter_sites(sites, chosen),
        "partial_errors": list(src.errors),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
