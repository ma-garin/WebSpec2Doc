"""System 05 オートヒーリングの Flask ルート層。

このモジュールは HTTP の境界だけを持つ。判断・処理はすべて
web.services.healing 配下（project_store / orchestrator / run_store / agents）
に委ねる。ここでは入力検証・認可（require_admin）・監査ログ・エラー整形のみ行う。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, render_template, request

from web.audit_context import record_admin_event
from web.auth import require_admin
from web.config import OUTPUT_DIR
from web.services.healing import agents as healing_agents
from web.services.healing import orchestrator, project_store, run_store, verification
from web.services.healing.orchestrator import DECISION_ACTIONS
from web.services.healing.types import HealingError
from web.tenancy import scoped_output_dir

bp = Blueprint("healing", __name__)

logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[0-9a-zA-Z_-]{1,64}$")
_GITHUB_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_PROJECT_DEFAULTS: dict[str, Any] = {
    "default_branch": "main",
    "verify_command": "",
    "remote": "origin",
    "github_repo": "",
    "agent": "claude",
    "max_iterations": 3,
    "max_parallel_agents": 3,
    "agent_timeout_sec": 900,
    "verify_timeout_sec": 1800,
}


def _out() -> Path:
    """テナントスコープ済みの出力ディレクトリ（リクエスト毎に解決）。"""
    return scoped_output_dir(OUTPUT_DIR)


def _record_audit(action: str, detail: dict[str, Any]) -> None:
    try:
        record_admin_event(action, detail)
    except Exception:
        logger.exception("healing: 監査ログの記録に失敗しました (action=%s)", action)


#: エラー文へ実パスが混ざったときに伏せる値（内部構造・利用者名の露出防止）。
_HOME_PATHS: tuple[str, ...] = tuple(
    dict.fromkeys(
        p for p in (str(Path.home()).rstrip("/"), str(Path.home().resolve()).rstrip("/")) if p
    )
)
_HOME_USER: str = Path.home().name


def _mask_home(text: str) -> str:
    """エラー文からホームディレクトリの実パスと利用者名を取り除く。"""
    masked = text
    for home in _HOME_PATHS:
        masked = masked.replace(home, "~")
    if len(_HOME_USER) >= 3:
        masked = masked.replace(_HOME_USER, "~")
    return masked


def _error_response(exc: Exception) -> tuple[dict[str, Any], int]:
    """利用者へ返す 400 応答。理由は残しつつ実パスだけを伏せる。"""
    return {"error": _mask_home(str(exc))}, 400


def _body() -> dict[str, Any]:
    data: dict[str, Any] = {}
    if request.form:
        data.update(request.form.to_dict())
    json_data = request.get_json(silent=True)
    if isinstance(json_data, dict):
        data.update(json_data)
    return data


def _strip_control(value: Any) -> str:
    return _CONTROL_CHARS_RE.sub("", str(value or ""))


def _clean_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _clean_name(value: Any) -> str:
    text = _strip_control(value).strip()
    if not (1 <= len(text) <= 120):
        raise HealingError("name は1〜120文字で指定してください。")
    return text


def _clean_repo_path(value: Any) -> str:
    text = str(value or "").strip()
    if not (1 <= len(text) <= 4096):
        raise HealingError("repo_path は1〜4096文字で指定してください。")
    return text


def _clean_verify_command(value: Any) -> str:
    """検証コマンドを整形し、危険なコマンドを「入口」で拒否する。

    repo_path を許可ルートで弾くのと同じく境界で検証する。実行直前の
    orchestrator 側チェックは最後の砦であって、入口の代わりではない。
    """
    text = _strip_control(value)
    if len(text) > 1000:
        raise HealingError("verify_command は1000文字以内で指定してください。")
    if not text.strip():
        return text
    allowed, reason = verification.is_command_allowed(text)
    if not allowed:
        _record_audit(
            "healing.project.verify_command.rejected",
            {"reason": reason, "command": text[:200]},
        )
        raise HealingError(f"verify_command を拒否しました: {reason}。")
    return text


def _clean_github_repo(value: Any) -> str:
    text = str(value or "").strip()
    if text and not _GITHUB_REPO_RE.match(text):
        raise HealingError("github_repo は 'owner/name' 形式で指定してください。")
    return text


def _clean_agent(value: Any, valid_names: set[str]) -> str:
    text = str(value or "").strip()
    if text and text not in valid_names:
        raise HealingError(
            f"agent は次のいずれかを指定してください: {', '.join(sorted(valid_names))}"
        )
    return text


def _clean_extra_instructions(value: Any) -> str:
    text = _strip_control(value)
    if len(text) > 4000:
        raise HealingError("extra_instructions は4000文字以内で指定してください。")
    return text


def _clean_note(value: Any) -> str:
    text = _strip_control(value)
    if len(text) > 4000:
        raise HealingError("note は4000文字以内で指定してください。")
    return text


def _clean_short_text(value: Any, default: str, max_len: int = 200) -> str:
    text = _strip_control(value).strip()
    if not text:
        return default
    return text[:max_len]


def _valid_agent_names() -> set[str]:
    return {a["name"] for a in healing_agents.describe_agents()}


def _project_create_fields(data: dict[str, Any], valid_agents: set[str]) -> dict[str, Any]:
    agent = _clean_agent(data.get("agent", _PROJECT_DEFAULTS["agent"]), valid_agents)
    return {
        "name": _clean_name(data.get("name")),
        "repo_path": _clean_repo_path(data.get("repo_path")),
        "default_branch": _clean_short_text(
            data.get("default_branch"), _PROJECT_DEFAULTS["default_branch"]
        ),
        "verify_command": _clean_verify_command(
            data.get("verify_command", _PROJECT_DEFAULTS["verify_command"])
        ),
        "remote": _clean_short_text(data.get("remote"), _PROJECT_DEFAULTS["remote"]),
        "github_repo": _clean_github_repo(
            data.get("github_repo", _PROJECT_DEFAULTS["github_repo"])
        ),
        "agent": agent or _PROJECT_DEFAULTS["agent"],
        "max_iterations": _clean_int(
            data.get("max_iterations"), _PROJECT_DEFAULTS["max_iterations"], 1, 10
        ),
        "max_parallel_agents": _clean_int(
            data.get("max_parallel_agents"), _PROJECT_DEFAULTS["max_parallel_agents"], 1, 8
        ),
        "agent_timeout_sec": _clean_int(
            data.get("agent_timeout_sec"), _PROJECT_DEFAULTS["agent_timeout_sec"], 60, 3600
        ),
        "verify_timeout_sec": _clean_int(
            data.get("verify_timeout_sec"), _PROJECT_DEFAULTS["verify_timeout_sec"], 60, 7200
        ),
    }


def _project_update_fields(data: dict[str, Any], valid_agents: set[str]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if "name" in data:
        updates["name"] = _clean_name(data.get("name"))
    if "repo_path" in data:
        updates["repo_path"] = _clean_repo_path(data.get("repo_path"))
    if "default_branch" in data:
        updates["default_branch"] = _clean_short_text(
            data.get("default_branch"), _PROJECT_DEFAULTS["default_branch"]
        )
    if "verify_command" in data:
        updates["verify_command"] = _clean_verify_command(data.get("verify_command"))
    if "remote" in data:
        updates["remote"] = _clean_short_text(data.get("remote"), _PROJECT_DEFAULTS["remote"])
    if "github_repo" in data:
        updates["github_repo"] = _clean_github_repo(data.get("github_repo"))
    if "agent" in data:
        agent = _clean_agent(data.get("agent"), valid_agents)
        if agent:
            updates["agent"] = agent
    if "max_iterations" in data:
        updates["max_iterations"] = _clean_int(
            data.get("max_iterations"), _PROJECT_DEFAULTS["max_iterations"], 1, 10
        )
    if "max_parallel_agents" in data:
        updates["max_parallel_agents"] = _clean_int(
            data.get("max_parallel_agents"), _PROJECT_DEFAULTS["max_parallel_agents"], 1, 8
        )
    if "agent_timeout_sec" in data:
        updates["agent_timeout_sec"] = _clean_int(
            data.get("agent_timeout_sec"), _PROJECT_DEFAULTS["agent_timeout_sec"], 60, 3600
        )
    if "verify_timeout_sec" in data:
        updates["verify_timeout_sec"] = _clean_int(
            data.get("verify_timeout_sec"), _PROJECT_DEFAULTS["verify_timeout_sec"], 60, 7200
        )
    return updates


def _project_dict(project: Any) -> dict[str, Any]:
    data = project.to_dict()
    # github_repo_effective: 現状は project_store 側に推測ロジックが無いため
    # github_repo をそのまま採用する（将来 git remote から推測する余地を残す）。
    data["github_repo_effective"] = project.github_repo
    return data


# ─────────────────────────── 画面 ───────────────────────────


@bp.get("/healing")
def healing_page():
    return render_template(
        "healing.html",
        agents=healing_agents.describe_agents(),
        allowed_roots=[str(p) for p in project_store.allowed_roots()],
        focus_run_id=None,
    )


@bp.get("/healing/runs/<run_id>")
def healing_page_with_run(run_id: str):
    if not _ID_RE.match(run_id):
        abort(404)
    return render_template(
        "healing.html",
        agents=healing_agents.describe_agents(),
        allowed_roots=[str(p) for p in project_store.allowed_roots()],
        focus_run_id=run_id,
    )


# ─────────────────────────── API: projects ───────────────────────────


@bp.get("/api/healing/projects")
def api_list_projects():
    try:
        out_dir = _out()
        projects = project_store.list_projects(out_dir)
        return {"projects": [_project_dict(p) for p in projects]}
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: list_projects に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.post("/api/healing/projects")
def api_create_project():
    guard = require_admin()
    if guard is not None:
        return guard
    try:
        out_dir = _out()
        fields = _project_create_fields(_body(), _valid_agent_names())
        project = project_store.create_project(out_dir, **fields)
        _record_audit(
            "healing.project.create",
            {"project_id": project.project_id, "name": project.name},
        )
        return {"project": _project_dict(project)}, 201
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: create_project に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.get("/api/healing/projects/<project_id>")
def api_get_project(project_id: str):
    if not _ID_RE.match(project_id):
        return {"error": "project_id が不正です。"}, 400
    try:
        out_dir = _out()
        project = project_store.get_project(out_dir, project_id)
        if project is None:
            return {"error": "プロジェクトが見つかりません。"}, 404
        return {"project": _project_dict(project)}
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: get_project に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.patch("/api/healing/projects/<project_id>")
def api_update_project(project_id: str):
    if not _ID_RE.match(project_id):
        return {"error": "project_id が不正です。"}, 400
    guard = require_admin()
    if guard is not None:
        return guard
    try:
        out_dir = _out()
        updates = _project_update_fields(_body(), _valid_agent_names())
        project = project_store.update_project(out_dir, project_id, updates)
        _record_audit(
            "healing.project.update",
            {"project_id": project_id, "fields": sorted(updates.keys())},
        )
        return {"project": _project_dict(project)}
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: update_project に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.delete("/api/healing/projects/<project_id>")
def api_delete_project(project_id: str):
    if not _ID_RE.match(project_id):
        return {"error": "project_id が不正です。"}, 400
    guard = require_admin()
    if guard is not None:
        return guard
    try:
        out_dir = _out()
        deleted = project_store.delete_project(out_dir, project_id)
        _record_audit(
            "healing.project.delete", {"project_id": project_id, "deleted": bool(deleted)}
        )
        return {"deleted": bool(deleted)}
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: delete_project に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.post("/api/healing/projects/<project_id>/check")
def api_check_project(project_id: str):
    if not _ID_RE.match(project_id):
        return {"error": "project_id が不正です。"}, 400
    try:
        out_dir = _out()
        project = project_store.get_project(out_dir, project_id)
        if project is None:
            return {"error": "プロジェクトが見つかりません。"}, 404
        checks = project_store.check_connection(project)
        checks_data = [
            {"key": c.key, "label": c.label, "ok": c.ok, "detail": c.detail} for c in checks
        ]
        return {"checks": checks_data, "ok": all(c.ok for c in checks)}
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: check_connection に失敗しました")
        return {"error": "処理に失敗しました"}, 500


def _discovered_dict(repo: project_store.DiscoveredRepo) -> dict[str, Any]:
    """探索結果を JSON 化する。display_path / root は表示用（ホームと利用者名を伏せ済み）。

    path だけは実パスを返す。登録は既存の POST /api/healing/projects が
    repo_path（実パス文字列）を要求しており、そのシグネチャを変えない方針のため。
    利用者名を伏せた表示用パスは expanduser で元へ戻せず、識別子だけを渡す設計にできない。
    この API は require_admin() 済みで、返す先は接続を作成できる管理者に限られる。
    """
    return {
        "path": repo.path,
        "display_path": repo.display_path,
        "name": repo.name,
        "root": repo.root,
        "branch": repo.branch,
        "remote": repo.remote,
        "github_repo": repo.github_repo,
        "suggested_command": repo.suggested_command,
        "already_connected": repo.already_connected,
    }


@bp.get("/api/healing/discover")
def api_discover_repos():
    """許可ルート配下の git リポジトリ候補を返す（絶対パスの手入力をなくすため）。"""
    guard = require_admin()
    if guard is not None:
        return guard
    try:
        limit = _clean_int(request.args.get("limit"), 200, 1, 500)
        repos = project_store.discover_repos(_out(), limit=limit)
        _record_audit("healing.project.discover", {"count": len(repos), "limit": limit})
        return {
            "repos": [_discovered_dict(r) for r in repos],
            "truncated": len(repos) >= limit,
        }
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: discover_repos に失敗しました")
        return {"error": "処理に失敗しました"}, 500


# ─────────────────────────── API: runs ───────────────────────────


@bp.get("/api/healing/runs")
def api_list_runs():
    project_id = str(request.args.get("project_id", "")).strip()
    if project_id and not _ID_RE.match(project_id):
        return {"error": "project_id が不正です。"}, 400
    limit = _clean_int(request.args.get("limit"), 50, 1, 200)
    try:
        out_dir = _out()
        runs = orchestrator.list_run_summaries(out_dir, project_id=project_id, limit=limit)
        return {"runs": runs}
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: list_run_summaries に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.post("/api/healing/runs")
def api_start_run():
    guard = require_admin()
    if guard is not None:
        return guard
    data = _body()
    project_id = str(data.get("project_id") or "").strip()
    if not _ID_RE.match(project_id):
        return {"error": "project_id が不正です。"}, 400
    try:
        extra_instructions = _clean_extra_instructions(data.get("extra_instructions", ""))
        out_dir = _out()
        project = project_store.get_project(out_dir, project_id)
        if project is None:
            return {"error": "プロジェクトが見つかりません。"}, 404
        run = orchestrator.start_run(
            out_dir=out_dir, project=project, extra_instructions=extra_instructions
        )
        _record_audit(
            "healing.run.start", {"run_id": run.run_id, "project_id": project_id}
        )
        return {"run": run_store.run_to_dict(run)}, 202
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: start_run に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.get("/api/healing/runs/<run_id>")
def api_get_run(run_id: str):
    if not _ID_RE.match(run_id):
        return {"error": "run_id が不正です。"}, 400
    try:
        out_dir = _out()
        run = orchestrator.get_run(out_dir, run_id)
        if run is None:
            return {"error": "実行が見つかりません。"}, 404
        return {"run": run_store.run_to_dict(run)}
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: get_run に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.post("/api/healing/runs/<run_id>/cancel")
def api_cancel_run(run_id: str):
    if not _ID_RE.match(run_id):
        return {"error": "run_id が不正です。"}, 400
    guard = require_admin()
    if guard is not None:
        return guard
    try:
        cancelled = orchestrator.cancel_run(run_id)
        _record_audit("healing.run.cancel", {"run_id": run_id, "cancelled": bool(cancelled)})
        return {"cancelled": bool(cancelled)}
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: cancel_run に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.post("/api/healing/runs/<run_id>/pull-request")
def api_create_pull_request(run_id: str):
    if not _ID_RE.match(run_id):
        return {"error": "run_id が不正です。"}, 400
    guard = require_admin()
    if guard is not None:
        return guard
    data = _body()
    draft = bool(data.get("draft", False))
    try:
        out_dir = _out()
        run = orchestrator.create_pull_request_for_run(out_dir, run_id, draft=draft)
        _record_audit("healing.run.pull_request", {"run_id": run_id, "draft": draft})
        return {"run": run_store.run_to_dict(run)}
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: create_pull_request_for_run に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.post("/api/healing/runs/<run_id>/decision")
def api_record_decision(run_id: str):
    if not _ID_RE.match(run_id):
        return {"error": "run_id が不正です。"}, 400
    guard = require_admin()
    if guard is not None:
        return guard
    data = _body()
    action = str(data.get("action") or "").strip()
    if action not in DECISION_ACTIONS:
        return {
            "error": f"action は次のいずれかを指定してください: {', '.join(DECISION_ACTIONS)}"
        }, 400
    try:
        note = _clean_note(data.get("note", ""))
        out_dir = _out()
        run = orchestrator.record_decision(out_dir, run_id, action=action, note=note)
        _record_audit(
            "healing.run.decision", {"run_id": run_id, "action": action}
        )
        return {"run": run_store.run_to_dict(run)}
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: record_decision に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.get("/api/healing/agents")
def api_list_agents():
    try:
        return {"agents": healing_agents.describe_agents()}
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: describe_agents に失敗しました")
        return {"error": "処理に失敗しました"}, 500
