"""テスト活動支援（テストデータ・手動実行・不具合・終了基準）の API。

読み書きはすべて `_out()`（テナントスコープ済み出力ディレクトリ）配下で完結させる。
domain を検証せずにパス要素へ渡すと `../` で他テナントの出力を読めてしまうため、
全エンドポイントで必須引数として検証してから services へ渡す。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from functools import wraps
from pathlib import Path
from typing import Any

from flask import Blueprint, request

from web.config import OUTPUT_DIR
from web.services import (
    completion_criteria,
    defect_store,
    manual_execution_store,
    process_gate,
    test_data_store,
)
from web.tenancy import scoped_output_dir
from web.validation import _valid_domain

bp = Blueprint("test_activity", __name__)
logger = logging.getLogger(__name__)

JsonResult = dict[str, Any] | tuple[dict[str, Any], int]

_MANUAL_RUN_LIMIT_MAX = 500
_CLOSED_STATE = "closed"  # defect_store.STATES の終端
_BLOCKER_SEVERITY = "critical"
# 自動実行の対象かどうかは testcase_spec_generator が「自動化判定 == 自動化可」で決めている。
# ここで別の判定（部分一致など）を持つと、実行される件数と数えた件数がずれるため同じ値を使う。
AUTOMATABLE_VALUE = "自動化可"
_NO_RESULT = {"", "—", "-", "?"}


class _BadRequest(ValueError):
    """利用者へそのまま提示してよい入力エラー。内部例外の文言とは区別する。"""


def _out() -> Path:
    """テナントスコープ済みの出力ディレクトリ（リクエスト毎に解決）。"""
    return scoped_output_dir(OUTPUT_DIR)


def _json_body() -> dict[str, Any]:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _api(fn: Callable[..., JsonResult]) -> Callable[..., JsonResult]:
    """例外を JSON 応答へ写像する。内部の例外文字列は返さない（実装詳細の漏えい防止）。"""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> JsonResult:
        try:
            return fn(*args, **kwargs)
        except (_BadRequest, process_gate.ProcessGateError) as exc:
            return {"error": str(exc)}, 400
        except ValueError as exc:
            logger.warning("test_activity: 入力を処理できません: %s", exc)
            return {"error": "リクエストを処理できません（入力内容を確認してください）"}, 400
        except Exception:
            logger.exception("test_activity: 想定外のエラー")
            return {"error": "内部エラーが発生しました"}, 500

    return wrapper


# ─────────────────────────── 引数検証 ───────────────────────────


def _require_domain(body: Mapping[str, Any] | None = None) -> str:
    raw = (
        request.args.get("domain")
        or request.form.get("domain")
        or str((body or {}).get("domain") or "")
    )
    domain = raw.strip()
    if not domain:
        raise _BadRequest("domain は必須です")
    if not _valid_domain(domain):
        raise _BadRequest("domain の形式が不正です")
    return domain


def _require_text(body: Mapping[str, Any], key: str, label: str) -> str:
    value = str(body.get(key) or "").strip()
    if not value:
        raise _BadRequest(f"{label}（{key}）は必須です")
    return value


def _require_id(raw: str, label: str) -> str:
    value = str(raw or "").strip()
    if not value or ".." in value or "/" in value or "\\" in value:
        raise _BadRequest(f"{label} が不正です")
    return value


# ─────────────────────────── テストデータ ───────────────────────────


@bp.get("/api/ta/datasets")
@_api
def api_ta_datasets_list() -> JsonResult:
    return {"items": test_data_store.list_datasets(_out(), _require_domain())}


@bp.post("/api/ta/datasets")
@_api
def api_ta_datasets_create() -> JsonResult:
    body = _json_body()
    domain = _require_domain(body)
    name = _require_text(body, "name", "データセット名")

    csv_text = str(body.get("csv") or "")
    if csv_text.strip():
        columns, rows = test_data_store.parse_csv(csv_text)
    else:
        columns = body.get("columns")
        rows = body.get("rows")
        if not isinstance(columns, list) or not isinstance(rows, list):
            raise _BadRequest("columns と rows は配列で指定してください（または csv を渡してください）")

    return {"item": test_data_store.save_dataset(_out(), domain, name, columns, rows)}


@bp.delete("/api/ta/datasets/<dataset_id>")
@_api
def api_ta_datasets_delete(dataset_id: str) -> JsonResult:
    domain = _require_domain(_json_body())
    test_data_store.delete_dataset(_out(), domain, _require_id(dataset_id, "dataset_id"))
    return {"ok": True}


# ─────────────────────────── 手動実行記録 ───────────────────────────


@bp.get("/api/ta/manual-runs")
@_api
def api_ta_manual_runs_list() -> JsonResult:
    domain = _require_domain()
    out = _out()
    limit = request.args.get("limit", type=int) or _MANUAL_RUN_LIMIT_MAX
    limit = max(1, min(limit, _MANUAL_RUN_LIMIT_MAX))
    metrics = _case_metrics(domain)
    return {
        "records": manual_execution_store.list_records(out, domain, limit=limit),
        "latest": manual_execution_store.latest_by_case(out, domain),
        "stats": manual_execution_store.stats(out, domain, total_cases=metrics["total_cases"]),
    }


@bp.post("/api/ta/manual-runs")
@_api
def api_ta_manual_runs_create() -> JsonResult:
    body = _json_body()
    domain = _require_domain(body)
    record = manual_execution_store.append_record(
        _out(),
        domain,
        _require_text(body, "case_id", "ケースID"),
        _require_text(body, "result", "実行結果"),
        note=str(body.get("note") or ""),
        evidence=str(body.get("evidence") or ""),
    )
    return {"record": record}


# ─────────────────────────── 不具合 ───────────────────────────


@bp.get("/api/ta/defects")
@_api
def api_ta_defects_list() -> JsonResult:
    domain = _require_domain()
    out = _out()
    return {"items": defect_store.list_defects(out, domain), "stats": defect_store.stats(out, domain)}


@bp.post("/api/ta/defects")
@_api
def api_ta_defects_create() -> JsonResult:
    body = _json_body()
    domain = _require_domain(body)
    item = defect_store.create_defect(
        _out(),
        domain,
        _require_text(body, "summary", "概要"),
        _require_text(body, "severity", "重大度"),
        case_id=str(body.get("case_id") or ""),
        detected_phase=str(body.get("detected_phase") or ""),
        injected_phase=str(body.get("injected_phase") or ""),
        odc_type=str(body.get("odc_type") or ""),
    )
    return {"item": item}


@bp.patch("/api/ta/defects/<defect_id>")
@_api
def api_ta_defects_update(defect_id: str) -> JsonResult:
    body = _json_body()
    domain = _require_domain(body)
    item = defect_store.update_state(
        _out(),
        domain,
        _require_id(defect_id, "defect_id"),
        _require_text(body, "state", "状態"),
    )
    return {"item": item}


# ─────────────────────────── 終了基準 ───────────────────────────


@bp.get("/api/ta/completion")
@_api
def api_ta_completion() -> JsonResult:
    domain = _require_domain()
    out = _out()
    metrics = _case_metrics(domain)
    blockers = [_blocker(d) for d in defect_store.list_defects(out, domain) if _is_blocker(d)]
    result = completion_criteria.evaluate(
        total_cases=metrics["total_cases"],
        executed_cases=_executed_cases(out, domain, metrics),
        critical_open=len(blockers),
        automatable_cases=metrics["automatable_cases"],
        automated_cases=metrics["automated_cases"],
    )
    return {
        "criteria": result["criteria"],
        "overall": result["overall"],
        "unmet_keys": result.get("unmet_keys", []),
        "blockers": blockers,
    }


def _testcase_rows(domain: str) -> list[dict[str, Any]]:
    """テストケース表の行。取得できない場合は空（終了基準の母数を推測で埋めない）。"""
    try:
        from web.services.qa.helpers import _load_report
        from web.services.testcase_table_store import compose

        try:
            from web.services.qa.helpers import _report_json_path
        except ImportError:  # 実体が routes 側にある配置でも動くようにする
            from web.routes.qa_process import _report_json_path

        report_path, error = _report_json_path(domain)
        if error or report_path is None:
            return []
        report = _load_report(report_path)
        if report is None:
            return []
        rows = compose(domain, report).get("rows") or []
    except Exception:
        logger.warning("test_activity: テストケース表を読めません domain=%s", domain, exc_info=True)
        return []
    return [row for row in rows if isinstance(row, dict)]


def _case_metrics(domain: str) -> dict[str, Any]:
    """ケース総数・自動化可能数・自動実行済み数を集める。表が無ければすべて 0。"""
    rows = _testcase_rows(domain)
    automated = {
        str(row.get("case_id") or "")
        for row in rows
        if str(row.get("result") or "").strip() not in _NO_RESULT
    }
    automated.discard("")
    return {
        "total_cases": len(rows),
        "automatable_cases": sum(1 for row in rows if _is_automatable(str(row.get("automation") or ""))),
        "automated_cases": len(automated),
        "automated_ids": frozenset(automated),
    }


def _is_automatable(value: str) -> bool:
    return value.strip() == AUTOMATABLE_VALUE


def _executed_cases(out: Path, domain: str, metrics: Mapping[str, Any]) -> int:
    """手動実行済みと自動実行済みの和。同一ケースを二重に数えない。"""
    manual_ids: set[str] = set()
    try:
        latest = manual_execution_store.latest_by_case(out, domain)
    except Exception:
        logger.warning("test_activity: 手動実行記録を読めません domain=%s", domain, exc_info=True)
        latest = None
    if isinstance(latest, Mapping):
        manual_ids = {str(key) for key in latest}
    elif isinstance(latest, list):
        manual_ids = {str(r.get("case_id") or "") for r in latest if isinstance(r, dict)}

    executed = manual_ids | set(metrics.get("automated_ids") or frozenset())
    executed.discard("")
    return len(executed)


def _is_blocker(defect: Mapping[str, Any]) -> bool:
    return (
        str(defect.get("severity") or "") == _BLOCKER_SEVERITY
        and str(defect.get("state") or "") != _CLOSED_STATE
    )


def _blocker(defect: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(defect.get("id") or defect.get("defect_id") or ""),
        "summary": str(defect.get("summary") or ""),
        "severity": str(defect.get("severity") or ""),
        "state": str(defect.get("state") or ""),
        "case_id": str(defect.get("case_id") or ""),
    }


# ---- 工程ゲート ----
# 工程は順番にしか進めない。ナビの無効化だけでは URL 直打ちで素通りできるため、
# 入場可否をサーバ側でも判定できる経路を用意する。


@bp.get("/api/ta/process")
@_api
def api_process_status() -> JsonResult:
    return process_gate.status(_out(), _require_domain())


@bp.post("/api/ta/process/complete")
@_api
def api_process_complete() -> JsonResult:
    body = _json_body()
    domain = _require_domain(body)
    phase = str(body.get("phase") or "").strip()
    if not phase:
        raise _BadRequest("完了する工程を指定してください")
    return process_gate.complete(_out(), domain, phase)


@bp.post("/api/ta/process/reopen")
@_api
def api_process_reopen() -> JsonResult:
    body = _json_body()
    domain = _require_domain(body)
    phase = str(body.get("phase") or "").strip()
    if not phase:
        raise _BadRequest("やり直す工程を指定してください")
    return process_gate.reopen(_out(), domain, phase)
