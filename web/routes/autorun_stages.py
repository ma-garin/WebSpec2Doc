"""AutoRun 段階承認パイプラインの API（仕様7〜13）。

各段階は「生成 → 提示 → （項目単位の修正）→ 承認」で進む。
状態はドメイン単位で `output/<domain>/qa_process/stages.json` に保存し、
同一URLの2回目以降はテスト計画をスキップできるようにする（仕様8）。
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, g, request

from web.config import OUTPUT_DIR
from web.tenancy import scoped_output_dir
from web.validation import _valid_domain

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from autorun.qf_schema import to_csv, to_table  # noqa: E402
from autorun.stages import (  # noqa: E402
    DESIGN_STAGE_IDS,
    STAGE_ORDER,
    STAGE_PLAYWRIGHT,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_SKIPPED,
    Pipeline,
    StageItem,
    build_stage,
    observation_from_report,
    test_case_rows,
)
from autorun.suggest import suggest_additions  # noqa: E402

logger = logging.getLogger(__name__)

bp = Blueprint("autorun_stages", __name__)

STAGES_FILE = "stages.json"


def _actor() -> str:
    """記録に残す実行者。認証が無効なら空にし、偽の名前を作らない。"""
    user = getattr(g, "auth_user", None)
    if isinstance(user, dict):
        return str(user.get("email") or user.get("id") or "")
    return ""


def _domain_dir(domain: str) -> Path:
    return scoped_output_dir(OUTPUT_DIR) / domain


def _stages_path(domain: str) -> Path:
    return _domain_dir(domain) / "qa_process" / STAGES_FILE


def _read_json_file(path: Path) -> dict[str, Any] | None:
    """JSON を読む。無ければ None（無いことを「空」と混同しない）。"""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("読み込めません %s: %s", path, exc)
        return None
    return data if isinstance(data, dict) else None


def _load_report(domain: str) -> dict[str, Any] | None:
    path = _domain_dir(domain) / "report.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("report.json を読めません（%s）: %s", domain, exc)
        return None


def _has_previous_snapshot(domain: str) -> bool:
    snapshots = _domain_dir(domain) / "snapshots"
    return snapshots.is_dir() and any(snapshots.glob("*.json"))


def _load_pipeline(domain: str) -> Pipeline:
    path = _stages_path(domain)
    if path.is_file():
        try:
            return Pipeline.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("stages.json を読めません（%s）: %s", domain, exc)
    return Pipeline.initial(is_rerun=_has_previous_snapshot(domain))


def _save_pipeline(domain: str, pipeline: Pipeline) -> None:
    path = _stages_path(domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pipeline.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def _observation(domain: str, url: str, payload: dict[str, Any]):
    return observation_from_report(
        _load_report(domain),
        url=url,
        has_previous_snapshot=_has_previous_snapshot(domain),
        document_driven=bool(payload.get("document_driven")),
        viewpoint_set_name=str(payload.get("viewpoint_set_name", "")),
    )


def _require_domain(value: str) -> tuple[str, tuple[dict, int] | None]:
    domain = (value or "").strip()
    if not domain or not _valid_domain(domain):
        return "", ({"error": "ドメインを指定してください"}, 400)
    return domain, None


@bp.get("/api/autorun/stages")
def api_stages() -> tuple[dict, int] | dict:
    """段階の一覧と現在地を返す。"""
    domain, error = _require_domain(request.args.get("domain", ""))
    if error:
        return error
    pipeline = _load_pipeline(domain)
    return {"domain": domain, **pipeline.to_dict()}


@bp.post("/api/autorun/stages/generate")
def api_generate_stage() -> tuple[dict, int] | dict:
    """指定段階の内容を生成する（ルールベース）。"""
    payload = request.get_json(silent=True) or {}
    domain, error = _require_domain(str(payload.get("domain", "")))
    if error:
        return error
    stage_id = str(payload.get("stage_id", ""))

    pipeline = _load_pipeline(domain)
    if pipeline.get(stage_id) is None:
        return {"error": f"未知の段階です: {stage_id}"}, 400

    obs = _observation(domain, str(payload.get("url", "")), payload)
    automation = _read_json_file(_domain_dir(domain) / "qa_process" / "automation_coverage.json")
    try:
        stage = build_stage(stage_id, obs, pipeline, automation)
    except ValueError as exc:
        return {"error": str(exc)}, 400

    pipeline = pipeline.replaced(stage).recorded(
        "generate", stage_id, f"{len(stage.items)}項目を生成", _actor()
    )
    _save_pipeline(domain, pipeline)
    return {"domain": domain, **pipeline.to_dict()}


@bp.post("/api/autorun/stages/approve")
def api_approve_stage() -> tuple[dict, int] | dict:
    """段階を承認する。項目承認が必要な段階では全項目の承認を要求する。"""
    payload = request.get_json(silent=True) or {}
    domain, error = _require_domain(str(payload.get("domain", "")))
    if error:
        return error
    stage_id = str(payload.get("stage_id", ""))

    pipeline = _load_pipeline(domain)
    stage = pipeline.get(stage_id)
    if stage is None:
        return {"error": f"未知の段階です: {stage_id}"}, 400
    if not stage.can_approve:
        return {
            "error": "この段階はまだ承認できません。",
            "detail": "全ての項目を承認してから、段階を承認してください。",
        }, 409

    assumed = sum(1 for i in stage.items if i.assumed)
    detail = f"{len(stage.items)}項目を承認"
    if assumed:
        detail += f"（前提 {assumed} 件を含む）"
    pipeline = pipeline.replaced(stage.with_status(STATUS_APPROVED)).recorded(
        "approve", stage_id, detail, _actor()
    )
    _save_pipeline(domain, pipeline)
    return {"domain": domain, **pipeline.to_dict()}


@bp.post("/api/autorun/stages/skip")
def api_skip_stage() -> tuple[dict, int] | dict:
    """2回目以降のみ、スキップ可能な段階を飛ばす（仕様8）。"""
    payload = request.get_json(silent=True) or {}
    domain, error = _require_domain(str(payload.get("domain", "")))
    if error:
        return error
    stage_id = str(payload.get("stage_id", ""))

    pipeline = _load_pipeline(domain)
    stage = pipeline.get(stage_id)
    if stage is None:
        return {"error": f"未知の段階です: {stage_id}"}, 400
    if not stage.definition.skippable_on_rerun:
        return {"error": "この段階はスキップできません"}, 400
    if not pipeline.is_rerun:
        return {
            "error": "初回実行ではスキップできません。",
            "detail": "同一URLの2回目以降のみスキップできます。",
        }, 409

    pipeline = pipeline.replaced(stage.with_status(STATUS_SKIPPED)).recorded(
        "skip", stage_id, "2回目以降のためスキップ", _actor()
    )
    _save_pipeline(domain, pipeline)
    return {"domain": domain, **pipeline.to_dict()}


@bp.post("/api/autorun/stages/item")
def api_update_item() -> tuple[dict, int] | dict:
    """項目の承認状態・内容を更新する。"""
    payload = request.get_json(silent=True) or {}
    domain, error = _require_domain(str(payload.get("domain", "")))
    if error:
        return error
    stage_id = str(payload.get("stage_id", ""))
    item_id = str(payload.get("item_id", ""))

    pipeline = _load_pipeline(domain)
    stage = pipeline.get(stage_id)
    if stage is None:
        return {"error": f"未知の段階です: {stage_id}"}, 400

    target = next((i for i in stage.items if i.item_id == item_id), None)
    if target is None:
        return {"error": f"未知の項目です: {item_id}"}, 404

    updated = target
    if "title" in payload or "detail" in payload:
        updated = updated.edited(
            title=payload.get("title"),
            detail=payload.get("detail"),
        )
    if "approved" in payload:
        updated = updated.with_approval(bool(payload.get("approved")))

    if "approved" in payload:
        action = "item_approve" if updated.approved else "item_unapprove"
        detail = ("項目を承認: " if updated.approved else "項目の承認を取消: ") + updated.title
    else:
        action = "item_edit"
        detail = "項目を修正: " + updated.title
    pipeline = pipeline.replaced(stage.with_item(updated)).recorded(
        action, stage_id, detail, _actor(), item_id
    )
    _save_pipeline(domain, pipeline)
    return {"domain": domain, **pipeline.to_dict()}


@bp.post("/api/autorun/stages/reset")
def api_reset_stages() -> tuple[dict, int] | dict:
    """段階状態を初期化する（作り直し）。"""
    payload = request.get_json(silent=True) or {}
    domain, error = _require_domain(str(payload.get("domain", "")))
    if error:
        return error
    pipeline = Pipeline.initial(is_rerun=_has_previous_snapshot(domain))
    _save_pipeline(domain, pipeline)
    return {"domain": domain, **pipeline.to_dict()}


@bp.post("/api/autorun/stages/suggest")
def api_suggest() -> tuple[dict, int] | dict:
    """段階に対する追加候補を LLM に問い合わせる（補助）。

    ルールベースの内容は変更しない。採否は人間が判断する。
    """
    payload = request.get_json(silent=True) or {}
    domain, error = _require_domain(str(payload.get("domain", "")))
    if error:
        return error
    stage_id = str(payload.get("stage_id", ""))

    pipeline = _load_pipeline(domain)
    stage = pipeline.get(stage_id)
    if stage is None:
        return {"error": f"未知の段階です: {stage_id}"}, 400

    obs = _observation(domain, str(payload.get("url", "")), payload)
    context = (
        f"対象: {obs.url or domain}\n"
        f"画面 {obs.screen_count} / フォーム {len(obs.forms)} / "
        f"入力項目 {obs.input_count}（必須 {obs.required_input_count}）/ "
        f"遷移 {obs.transition_count}"
    )
    result = suggest_additions(
        stage_name=stage.definition.name,
        purpose=stage.definition.purpose,
        context=context,
        existing_titles=[item.title for item in stage.items],
    )
    return {"domain": domain, "stage_id": stage_id, **result.to_dict()}


@bp.post("/api/autorun/stages/adopt")
def api_adopt_suggestion() -> tuple[dict, int] | dict:
    """LLM の提案を項目として採用する。出所は llm として残す。"""
    payload = request.get_json(silent=True) or {}
    domain, error = _require_domain(str(payload.get("domain", "")))
    if error:
        return error
    stage_id = str(payload.get("stage_id", ""))
    title = str(payload.get("title", "")).strip()
    detail = str(payload.get("detail", "")).strip()

    if not title:
        return {"error": "採用する項目の見出しが空です"}, 400

    pipeline = _load_pipeline(domain)
    stage = pipeline.get(stage_id)
    if stage is None:
        return {"error": f"未知の段階です: {stage_id}"}, 400

    item = StageItem(
        item_id=f"llm-{uuid.uuid4().hex[:10]}",
        title=title,
        detail=detail,
        source="llm",
    )
    pipeline = pipeline.replaced(replace(stage, items=stage.items + (item,))).recorded(
        "adopt_llm", stage_id, "LLM提案を採用: " + title, _actor(), item.item_id
    )
    _save_pipeline(domain, pipeline)
    return {"domain": domain, **pipeline.to_dict()}


@bp.post("/api/autorun/stages/proceed")
def api_proceed() -> tuple[dict, int] | dict:
    """段階承認を終えて、後続（Playwright化・実行）へ進む。

    全段階が承認（またはスキップ）されていなければ進ませない。
    実行は対象サイトへ実際に操作を行うため、ここは実質的な関門になる。
    """
    payload = request.get_json(silent=True) or {}
    domain, error = _require_domain(str(payload.get("domain", "")))
    if error:
        return error
    job_id = str(payload.get("job_id", "")).strip()

    pipeline = _load_pipeline(domain)

    # 仕様7〜14: 各段階で個別に提示・承認する。
    # ジョブが「いまどの段階で待っているか」を持つので、その段階だけを検査する。
    # 以前は設計段階1〜7を一括で要求していたため、開始した途端に全段階の
    # 内容が出てしまっていた（利用者の操作で発覚した重大な乖離）。
    from web.routes.auto_run import current_awaiting_stage, release_stage_gate

    awaiting = current_awaiting_stage(job_id, domain)
    if awaiting:
        required = (awaiting,)
    else:
        # 待機段階が特定できない場合（リロード等）は従来どおりの範囲で判定する。
        playwright = pipeline.get(STAGE_PLAYWRIGHT)
        at_design_gate = playwright is None or playwright.status == STATUS_PENDING
        required = DESIGN_STAGE_IDS if at_design_gate else STAGE_ORDER

    remaining = [
        s.definition.name
        for s in pipeline.stages
        if s.stage_id in required and s.status not in (STATUS_APPROVED, STATUS_SKIPPED)
    ]
    if remaining:
        return {
            "error": "まだ承認されていない段階があります。",
            "detail": "未承認: " + " / ".join(remaining),
            "remaining": remaining,
        }, 409

    released = release_stage_gate(job_id, domain)
    if released:
        detail = (
            f"{awaiting} を承認し次段階へ進行" if awaiting else "全段階の承認を確定し後続へ進行"
        )
        pipeline = pipeline.recorded("proceed", awaiting or "", detail, _actor())
        _save_pipeline(domain, pipeline)
    return {
        "domain": domain,
        "released": released,
        "detail": (
            "後続の Playwright 化へ進みます。"
            if released
            else "対象のジョブが承認待ちではありません（すでに進行済み、または別のジョブです）。"
        ),
        **pipeline.to_dict(),
    }


@bp.get("/api/autorun/stages/testcases")
def api_test_cases() -> tuple[dict, int] | dict | Response:
    """テストケースを QualityForward のカラム構成で返す（表 / CSV）。"""
    domain, error = _require_domain(request.args.get("domain", ""))
    if error:
        return error
    rows = test_case_rows(_load_pipeline(domain))

    if request.args.get("format") == "csv":
        return Response(
            to_csv(rows),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{domain}_testcases.csv"'},
        )
    return {"domain": domain, **to_table(rows)}
