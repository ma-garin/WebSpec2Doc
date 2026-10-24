"""指揮ホームの「案件概況」。既存の実データから QA 案件ごとの段と状態を組み立てる（読み取りのみ）。

共通の案件台帳（common.case）はまだ無いため、暫定で次の 2 種を案件として扱う。
- サイト案件: 指揮・解析・接続のいずれかがあるサイト 1 つ = 1 案件
- 仕様評価案件: どのサイトにも紐づいていない System 06 の検査 1 件 = 1 案件
段: 仕様評価(06) → リスク → テスト設計(02) → 実行(03/07/08) → 欠陥(05/09) → 判定。
取れなかった源は partial_errors に名前を残し、その段は「未検証」として名指しする（0 件扱いにしない）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from web.services.orchestration import workflow_view
from web.services.orchestration.run_store import ConductorRun

logger = logging.getLogger(__name__)

STATE_LABEL = {"not_started": "未着手", "in_progress": "進行中",
               "needs_decision": "要判断", "done": "完了"}
STAGES = (("spec", "仕様評価", "06"), ("risk", "リスク", "共通"), ("design", "テスト設計", "02"),
          ("exec", "実行", "03/07/08"), ("defect", "欠陥", "05/09"), ("verdict", "判定", "共通"))
_CRITICAL = {"critical", "重大", "high"}
_STEP_STATE = {"running": "in_progress", "queued": "in_progress", "waiting_human": "needs_decision",
               "failed": "needs_decision", "succeeded": "done", "skipped": "done",
               "cancelled": "needs_decision"}


def _item(kind: str, text: str, href: str | None = None) -> dict[str, Any]:
    """名指し項目。kind は 重大／欠落／未検証。"""
    return {"kind": kind, "text": text, "href": href}


def _stage(key: str, state: str, summary: str, href: str | None,
           items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    label, owner = next((lab, own) for k, lab, own in STAGES if k == key)
    return {"key": key, "label": label, "owner": owner, "state": state,
            "state_label": STATE_LABEL[state], "summary": summary, "href": href,
            "items": items or []}


def _step(run: ConductorRun | None, name: str):
    if run is None:
        return None
    hits = [s for s in run.steps if s.name == name]
    return hits[-1] if hits else None


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _exec_report(out_dir: Path, domain: str) -> dict[str, Any] | None:
    base = out_dir / domain
    for rel in ("qa_process/playwright_report.json", "testcases/playwright_report.json"):
        data = _load_json(base / rel)
        if data is not None and isinstance(data.get("tests"), list):
            return data
    return None


def _spec_stage_for_inspection(insp: dict[str, Any]) -> dict[str, Any]:
    findings = insp.get("findings") or []
    href = "/docverify"
    open_crit = [f for f in findings if str(f.get("severity") or "").lower() in _CRITICAL
                 and f.get("status") not in ("rejected", "resolved", "closed")]
    pending = [f for f in findings if f.get("certainty") == "要確認" and f.get("status") != "rejected"]
    items = [_item("重大", f"{f.get('id') or '指摘'}: {str(f.get('message') or '')[:60]}", href)
             for f in open_crit[:5]]
    items += [_item("未検証", f"{f.get('id') or '指摘'}: 採否が決まっていません", href) for f in pending[:3]]
    closed = insp.get("phase") == "closed" or insp.get("status") == "closed"
    approved = bool((insp.get("approval") or {}).get("approver"))
    if not insp.get("document") and not findings:
        return _stage("spec", "not_started", "文書がまだ登録されていません", href,
                      [_item("欠落", "要件定義書・基本設計書が未登録です", href)])
    if open_crit or pending:
        return _stage("spec", "needs_decision",
                      f"未解消の重大 {len(open_crit)} 件・採否未決 {len(pending)} 件", href, items)
    if closed and approved:
        return _stage("spec", "done", f"指摘 {len(findings)} 件を処理し承認済み", href)
    return _stage("spec", "in_progress", f"指摘 {len(findings)} 件を確認中", href,
                  [] if approved else [_item("未検証", "承認者がまだ判断していません", href)])


def _risk_stage() -> dict[str, Any]:
    return _stage("risk", "not_started", "リスク台帳がまだありません", None,
                  [_item("欠落", "リスクと、それを確かめるテストの対応が記録されていません")])


def _design_stage(out_dir: Path, domain: str, run: ConductorRun | None, links: dict) -> dict[str, Any]:
    href = links.get("s02")
    step = _step(run, "tests")
    tc_dir = out_dir / domain / "testcases"
    files = [p for p in tc_dir.glob("*.json") if p.name != "playwright_report.json"] if tc_dir.is_dir() else []
    if step is not None and step.status in ("running", "queued", "waiting_human", "failed"):
        state = _STEP_STATE[step.status]
        items = [_item("重大", step.error, href)] if step.error else []
        if step.human_action:
            items.append(_item("未検証", step.human_action, href))
        return _stage("design", state, step.summary or "テスト設計を進めています", href, items)
    if files or (step is not None and step.status == "succeeded"):
        return _stage("design", "done", f"テストケースの成果物 {len(files)} 件", href)
    return _stage("design", "not_started", "テストケースがまだありません", href,
                  [_item("欠落", "テスト設計の成果物がありません", href)])


def _exec_stage(report: dict | None, run: ConductorRun | None, links: dict) -> dict[str, Any]:
    href = links.get("s03")
    step = _step(run, "run")
    if step is not None and step.status in ("running", "queued"):
        return _stage("exec", "in_progress", step.summary or "実行中です", href)
    if report is None:
        if step is not None and step.status == "failed":
            return _stage("exec", "needs_decision", "実行が失敗しました", href,
                          [_item("重大", step.error or "実行が途中で止まりました", href)])
        return _stage("exec", "not_started", "実行結果がまだありません", href,
                      [_item("未検証", "テストを 1 度も実行していません", href)])
    tests = report.get("tests") or []
    failed = [t for t in tests if str(t.get("status") or "") not in ("passed", "skipped")]
    skipped = [t for t in tests if str(t.get("status") or "") == "skipped"]
    if not tests:
        return _stage("exec", "needs_decision", "実行結果が 0 件です", href,
                      [_item("未検証", "実行したテストが 0 件のため合否を判断できません", href)])
    items = [_item("重大", f"失敗: {str(t.get('title') or t.get('id') or 'テスト')[:60]}", href)
             for t in failed[:5]]
    if skipped:
        items.append(_item("未検証", f"実行を飛ばしたテスト {len(skipped)} 件", href))
    if failed:
        return _stage("exec", "needs_decision", f"{len(tests)} 件中 {len(failed)} 件失敗", href, items)
    return _stage("exec", "done", f"{len(tests)} 件実行・失敗なし", href, items)


def _defect_stage(report: dict | None, awaiting: int | None, run: ConductorRun | None,
                  links: dict) -> dict[str, Any]:
    href = links.get("s05")
    failed = [t for t in (report or {}).get("tests") or []
              if str(t.get("status") or "") not in ("passed", "skipped")]
    if awaiting is None:
        return _stage("defect", "needs_decision", "修正報告書を読めませんでした", href,
                      [_item("未検証", "修正報告書の状態を確認できません。再読み込みしてください", href)])
    if awaiting:
        return _stage("defect", "needs_decision", f"承認待ちの修正報告書 {awaiting} 件", href,
                      [_item("未検証", f"修正報告書 {awaiting} 件が承認待ちです", href)])
    step = _step(run, "healing")
    if step is not None and step.status in ("running", "queued"):
        return _stage("defect", "in_progress", step.summary or "欠陥を直しています", href)
    if failed:
        return _stage("defect", "needs_decision", f"未対処の欠陥 {len(failed)} 件", href,
                      [_item("重大", f"欠陥 {len(failed)} 件に対処の記録がありません", href)])
    if report is None:
        return _stage("defect", "not_started", "実行前のため欠陥はまだ判断できません", href)
    return _stage("defect", "done", "未対処の欠陥はありません", href)


def _verdict(stages: list[dict[str, Any]]) -> dict[str, Any]:
    """全体と今回の変更分の見立て。人の判断（decision）が無い間は「機械の見立て」と明示する。"""
    items = [i for s in stages for i in s["items"]]
    crit = [i for i in items if i["kind"] == "重大"]
    unknown = [s for s in stages if s["state"] != "done"]
    if crit:
        overall = "不合格"
    elif unknown:
        overall = "判定不能"
    else:
        overall = "合格"
    reason = (f"未解消の重大 {len(crit)} 件" if crit else
              ("未完了の段: " + "・".join(s["label"] for s in unknown)) if unknown else "全段が完了")
    return {"overall": {"value": overall, "reason": reason},
            "changed": {"value": "未判定",
                        "reason": "対象版が固定されていないため、今回の変更分を切り出せません"},
            "decision": None,
            "decision_note": "人の判定はまだ記録されていません。表示は記録データからの見立てです。"}


def _finish(case: dict[str, Any], stages: list[dict[str, Any]]) -> dict[str, Any]:
    verdict = _verdict(stages)
    v_items = [_item("未検証", "リリース可否を人がまだ判断していません")]
    stages.append(_stage("verdict", "needs_decision" if verdict["overall"]["value"] != "合格"
                         else "in_progress", f"見立て: {verdict['overall']['value']}", None, v_items))
    named = [{**i, "stage": s["label"]} for s in stages for i in s["items"]]
    current = next((s for s in stages if s["state"] != "done"), stages[-1])
    return {**case, "stages": stages, "verdict": verdict, "named": named,
            "current_stage": current["key"],
            "counts": {k: sum(1 for i in named if i["kind"] == k) for k in ("重大", "欠落", "未検証")}}


def _site_case(out_dir: Path, site: dict[str, str], projects: dict[str, str] | None,
               errors: list[str]) -> dict[str, Any]:
    from web.services.orchestration.home_summary import _links  # noqa: PLC0415 - 循環回避

    domain = site["domain"]
    try:
        run = workflow_view._latest_run(out_dir, domain)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        logger.exception("case_overview: 実行記録の取得に失敗 %s", domain)
        errors.append("runs")
        run = None
    links = _links(domain, (out_dir / domain / "report.json").is_file())
    awaiting: int | None = 0
    pid = (projects or {}).get(domain, "")
    if projects is None:
        awaiting = None
    elif pid:
        try:
            awaiting = len(workflow_view._awaiting_reports(out_dir, pid))  # noqa: SLF001
        except Exception:  # noqa: BLE001
            logger.exception("case_overview: 報告書の取得に失敗 %s", domain)
            errors.append("reports")
            awaiting = None
    report = _exec_report(out_dir, domain)
    spec = _stage("spec", "not_started", "仕様評価が紐づいていません", "/docverify",
                  [_item("欠落", "この案件の要件定義書・基本設計書の評価がありません", "/docverify")])
    stages = [spec, _risk_stage(), _design_stage(out_dir, domain, run, links),
              _exec_stage(report, run, links), _defect_stage(report, awaiting, run, links)]
    updated = (run.finished_at or run.started_at) if run is not None else ""
    return _finish({"id": f"site:{domain}", "kind": "site", "title": site.get("label") or domain,
                    "target": domain, "updated_at": updated or None,
                    "detail_href": f"/orchestration?site={quote(domain, safe='')}"}, stages)


def _inspection_case(insp: dict[str, Any]) -> dict[str, Any]:
    none_href = None
    stages = [_spec_stage_for_inspection(insp), _risk_stage()]
    for key, label in (("design", "テスト設計"), ("exec", "実行"), ("defect", "欠陥")):
        stages.append(_stage(key, "not_started", "対象サイトが紐づいていません", none_href,
                             [_item("欠落", f"{label}の対象サイトが決まっていません")]))
    return _finish({"id": f"insp:{insp.get('id')}", "kind": "inspection",
                    "title": insp.get("name") or "名称未設定の検査", "target": None,
                    "updated_at": insp.get("created_at"), "detail_href": "/docverify"}, stages)


def _inspections(errors: list[str]) -> list[dict[str, Any]]:
    try:
        from web.services.docverify import store  # noqa: PLC0415

        root = store._root()  # noqa: SLF001
        out = []
        for meta in store.list_all():
            data = _load_json(root / str(meta.get("id")) / "inspection.json")
            out.append(data if data is not None else meta)
        return out
    except Exception:  # noqa: BLE001
        logger.exception("case_overview: 仕様評価の取得に失敗")
        errors.append("inspections")
        return []


def build(out_dir: Path) -> dict[str, Any]:
    out_dir = Path(out_dir)
    errors: list[str] = []
    try:
        sites = workflow_view._list_sites(out_dir)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        logger.exception("case_overview: サイト一覧の取得に失敗")
        errors.append("sites")
        sites = []
    projects: dict[str, str] | None = {}
    if sites:
        try:
            from web.services.healing import project_store  # noqa: PLC0415

            projects = {p.domain: p.project_id for p in project_store.list_projects(out_dir)}
        except Exception:  # noqa: BLE001
            logger.exception("case_overview: プロジェクトの取得に失敗")
            errors.append("projects")
            projects = None
    cases = [_site_case(out_dir, s, projects, errors) for s in sites]
    cases += [_inspection_case(i) for i in _inspections(errors)]
    order = {"needs_decision": 0, "in_progress": 1, "not_started": 2, "done": 3}
    cases.sort(key=lambda c: (-c["counts"]["重大"],
                              order[next(s["state"] for s in c["stages"] if s["key"] == c["current_stage"])],
                              str(c["title"])))
    return {"schema": "orchestration.cases/1", "cases": cases,
            "stages": [{"key": k, "label": lab, "owner": own} for k, lab, own in STAGES],
            "partial_errors": sorted(set(errors)),
            "updated_at": datetime.now().isoformat(timespec="seconds")}
