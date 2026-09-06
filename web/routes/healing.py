"""System 05 オートヒーリングの Flask ルート層。

このモジュールは HTTP の境界だけを持つ。判断・処理はすべて
web.services.healing 配下（project_store / orchestrator / run_store / agents）
に委ねる。ここでは入力検証・認可（require_admin）・監査ログ・エラー整形のみ行う。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, render_template, request, send_file

from web.audit_context import record_admin_event
from web.auth import require_admin
from web.config import OUTPUT_DIR
from web.services.healing import agents as healing_agents
from web.services.healing import (
    autorun_bridge,
    orchestrator,
    project_store,
    report_doc,
    run_store,
    verification,
)
from web.services.healing import (
    monitor as healing_monitor,
)
from web.services.healing.orchestrator import DECISION_ACTIONS, REPORT_ACTIONS
from web.services.healing.types import HealingError
from web.tenancy import scoped_output_dir

bp = Blueprint("healing", __name__)

logger = logging.getLogger(__name__)

#: 監査ログの置き場。他ルート（settings.py / admin.py / review.py）と同じ規約。
INSTANCE_DIR = Path("instance")

_ID_RE = re.compile(r"^[0-9a-zA-Z_-]{1,64}$")
_GITHUB_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

#: 監視の時刻。境界で弾く（値の検証は保存の直前ではなく入口で行う）。
_MONITOR_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

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


def _audit_target(action: str, detail: dict[str, Any]) -> tuple[str, str]:
    """監査ログの対象（種類・ID）を action と detail から決める。

    action は "healing.<対象>.<動作>" の形なので 2 語目がそのまま対象の種類になる。
    ID は detail が持つ識別子を優先する（無い操作＝一覧・探索は "current"）。
    """
    parts = action.split(".")
    target_type = parts[1] if len(parts) >= 2 and parts[1] else "healing"
    for key in ("project_id", "run_id", "report_id"):
        value = detail.get(key)
        if value:
            return target_type, str(value)
    return target_type, "current"


def _record_audit(action: str, detail: dict[str, Any]) -> None:
    """管理操作の証跡を残す。

    証跡が無いと「誰が何を直したか」を後から示せない。本処理は止めないが、
    記録できなかったことは必ずログに残す（黙って落とすと欠落に気づけない）。
    """
    target_type, target_id = _audit_target(action, detail)
    try:
        record_admin_event(
            INSTANCE_DIR,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
    except Exception:
        logger.warning(
            "healing: 監査ログの記録に失敗しました (action=%s target=%s/%s)",
            action,
            target_type,
            target_id,
            exc_info=True,
        )


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
    # 対象サイトと報告先。E2E 起点の実行と画面仕様との照合に要る。
    if "domain" in data:
        updates["domain"] = _clean_short_text(data.get("domain"), "")
    if "report_org" in data:
        updates["report_org"] = _clean_short_text(data.get("report_org"), "")
    if "monitor_enabled" in data:
        updates["monitor_enabled"] = bool(data.get("monitor_enabled"))
    if "monitor_time" in data:
        updates["monitor_time"] = _clean_monitor_time(data.get("monitor_time"))
    return updates


def _clean_monitor_time(value: Any) -> str:
    """監視の時刻。"HH:MM" 以外は受け取らない（空にして監視を止める）。"""
    text = str(value or "").strip()
    if not _MONITOR_TIME_RE.match(text):
        return ""
    hour, minute = text.split(":")
    if int(hour) > 23 or int(minute) > 59:
        return ""
    return text


def _project_dict(project: Any) -> dict[str, Any]:
    data = project.to_dict()
    # github_repo_effective: 現状は project_store 側に推測ロジックが無いため
    # github_repo をそのまま採用する（将来 git remote から推測する余地を残す）。
    data["github_repo_effective"] = project.github_repo
    return data


# ─────────────────────────── 画面 ───────────────────────────


@bp.get("/healing")
def healing_page():
    """入口は報告書。毎日見るのは「今日出す報告書があるか」だけ。"""
    return render_template("healing_reports.html")


@bp.get("/healing/settings")
def healing_settings_page():
    """接続先と実行の設定。月に一度しか触らないので、入口からは外す。"""
    return render_template(
        "healing.html",
        agents=healing_agents.describe_agents(),
        allowed_roots=[str(p) for p in project_store.allowed_roots()],
        focus_run_id=None,
    )


@bp.get("/healing/reports/<report_id>")
def healing_report_page(report_id: str):
    """報告書 1 件。読んで、承認するかを決める画面。"""
    if not _ID_RE.match(report_id):
        abort(404)
    return render_template("healing_report.html", report_id=report_id)


@bp.get("/healing/reports/<report_id>/print")
def healing_report_print(report_id: str):
    """印刷用。サイドバーもトップバーも無い A4 の様式。

    PDF はブラウザの「PDF に保存」で出す。専用ライブラリを足さない
    （src/generator/pdf_reporter.py は Playwright を起動するため、
    画面から同期で呼ぶには重い）。
    """
    if not _ID_RE.match(report_id):
        abort(404)
    report = report_doc.load_report(_out(), report_id)
    if report is None:
        abort(404)
    return render_template("healing_report_print.html", report=report_doc.to_dict(report))


@bp.get("/api/healing/reports/<report_id>/screenshot")
def api_report_screenshot(report_id: str):
    """報告書に添える画面のスクリーンショット。

    パスは報告書が持っているものだけを配信する。クエリで受け取った値を
    そのままファイルパスにすると、任意のファイルを読み出せてしまう。
    """
    if not _ID_RE.match(report_id):
        abort(404)
    requested = str(request.args.get("path", "")).strip()
    try:
        out_dir = _out()
        report = report_doc.load_report(out_dir, report_id)
        if report is None:
            abort(404)
        allowed = {report.incident_screenshot, report.action_screenshot} - {""}
        if requested not in allowed:
            abort(404)
        target = (Path(out_dir) / requested).resolve()
        if not str(target).startswith(str(Path(out_dir).resolve())) or not target.is_file():
            abort(404)
        return send_file(target)
    except HealingError:
        abort(404)


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


@bp.post("/api/healing/projects/<project_id>/monitor/run-now")
def api_monitor_run_now(project_id: str):
    """毎日の見張りを、待たずに今すぐ 1 回だけ回す。

    設定した時刻を待たずに動作を確かめられないと、監視は
    「設定したが動いているか分からない」状態のまま放置される。
    """
    if not _ID_RE.match(project_id):
        return {"error": "project_id が不正です。"}, 400
    guard = require_admin()
    if guard is not None:
        return guard
    try:
        out_dir = _out()
        project = project_store.get_project(out_dir, project_id)
        if project is None:
            return {"error": "プロジェクトが見つかりません。"}, 404
        if not project.domain:
            return {
                "error": "対象サイトが設定されていません。接続先の「サイト」を設定してください。"
            }, 400
        run = healing_monitor.run_now(out_dir, project)
        _record_audit(
            "healing.monitor.run_now",
            {"project_id": project_id, "run_id": run.run_id if run else ""},
        )
        if run is None:
            return {"run": None, "message": "テストは全部通りました。報告書は作りません。"}
        return {"run": run_store.run_summary(run)}, 202
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: monitor/run-now に失敗しました")
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


#: サイト一覧から外す出力先。報告書・実行の保存先とテナント分離用で、
#: どちらも「01 が解析したサイト」ではない。
_SITE_EXCLUDE_DIRS = frozenset({".healing", "tenants"})


def _site_dict(entry: Path) -> dict[str, Any] | None:
    """1 サイト分の要約。読めない report.json は一覧から外す（画面を落とさない）。"""
    report = entry / "report.json"
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except Exception:
        logger.warning(
            "healing: 読めない report.json をサイト一覧から除きます (%s)",
            entry.name,
            exc_info=True,
        )
        return None
    raw = data.get("screens") if isinstance(data, dict) else None
    screens = raw if isinstance(raw, list) else []
    title = ""
    if screens and isinstance(screens[0], dict):
        title = _clean_short_text(screens[0].get("title"), "")
    try:
        updated_at = datetime.fromtimestamp(report.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        updated_at = ""
    return {
        "domain": entry.name,
        "title": title,
        "screens": len(screens),
        "updated_at": updated_at,
    }


@bp.get("/api/healing/sites")
def api_list_sites():
    """01 が解析したサイトを列挙する（接続先の「サイト」欄の候補）。

    手入力させると綴りのずれで毎日の見張りも画面仕様との照合も静かに効かなく
    なるため、実在するものだけを選ばせる。選ぶだけの一覧なので閲覧権限で返す。
    """
    try:
        out_dir = _out()
        sites: list[dict[str, Any]] = []
        if out_dir.is_dir():
            for entry in sorted(out_dir.iterdir(), key=lambda p: p.name):
                if not entry.is_dir():
                    continue
                if entry.name.startswith(".") or entry.name in _SITE_EXCLUDE_DIRS:
                    continue
                if not (entry / "report.json").is_file():
                    continue
                site = _site_dict(entry)
                if site is not None:
                    sites.append(site)
        return {"sites": sites}
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: サイト一覧の取得に失敗しました")
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


@bp.post("/api/healing/runs/from-autorun")
def api_start_run_from_autorun():
    """02/03 の失敗から報告書を起こす。

    「壊れたら直る」の入口。検証コマンドの結果から欠陥を切り出すのではなく、
    E2E が落ちた事実（画面 ID・URL・スクリーンショット）を保ったまま渡す。
    """
    guard = require_admin()
    if guard is not None:
        return guard
    data = _body()
    project_id = _clean_short_text(data.get("project_id"), "", 64)
    domain = _clean_short_text(data.get("domain"), "", 253)
    run_id = _clean_short_text(data.get("run_id"), "", 64)
    if not _ID_RE.match(project_id):
        return {"error": "project_id が不正です。"}, 400
    if not domain:
        return {"error": "domain を指定してください。"}, 400
    raw_ids = data.get("test_ids") or []
    test_ids = [_clean_short_text(t, "", 64) for t in raw_ids if isinstance(t, str)][:50]

    try:
        out_dir = _out()
        project = project_store.get_project(out_dir, project_id)
        if project is None:
            return {"error": "接続先が見つかりません"}, 404
        # domain は接続先に紐づける。次回からは指定しなくてよい。
        if project.domain != domain:
            project = project_store.update_project(
                out_dir, project_id, {"domain": domain}
            )

        defects = autorun_bridge.load_failures(
            out_dir, domain, run_id=run_id, test_ids=test_ids
        )
        if not defects:
            return {"error": "失敗したテストがありません"}, 400

        run = orchestrator.start_run(
            out_dir=out_dir,
            project=project,
            actor="autorun",
            defects=defects,
        )
        _record_audit(
            "healing.run.from_autorun",
            {"project_id": project_id, "domain": domain, "defects": len(defects)},
        )
        return {"run": run_store.run_to_dict(run), "defects": len(defects)}, 202
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: AutoRun からの実行開始に失敗しました")
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


# ─────────────────────────── API: 報告書 ───────────────────────────
#
# 報告書はこのシステムの成果物そのもの。実行（run）は報告書を作るための工程で、
# 画面の主語は報告書になる。ルートの登録順に注意: /reports/count は
# /reports/<report_id> より前に置く（count が ID として解釈されないように）。


def _report_summary(report: report_doc.MaintenanceReport) -> dict[str, Any]:
    """一覧に出す最小限。差分や根拠は詳細でしか返さない（一覧を重くしない）。"""
    attention = list(report.attention)
    return {
        "report_id": report.report_id,
        "run_id": report.run_id,
        "project_id": report.project_id,
        "project_name": report.project_name,
        "target_url": report.target_url,
        "title": report.title,
        "status": report.status,
        "verify_after": report.verify_after,
        "verify_after_ok": report.verify_after_ok,
        "attention_count": len(attention),
        "attention_high": sum(1 for a in attention if a.get("severity") == "high"),
        "action_empty": not report.action_text,
        "incident_source": report.incident_source,
        "incident_screen_id": report.incident_screen_id,
        "incident_screen_name": report.incident_screen_name,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
        "fix_target": report.fix_target,
    }


@bp.get("/api/healing/reports/count")
def api_count_reports():
    status = _clean_short_text(request.args.get("status"), "", 32)
    try:
        reports = report_doc.list_reports(_out(), status=status, limit=1000)
        return {"count": len(reports)}
    except Exception:
        logger.exception("healing: 報告書の件数取得に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.get("/api/healing/reports")
def api_list_reports():
    status = _clean_short_text(request.args.get("status"), "", 32)
    project_id = str(request.args.get("project_id", "")).strip()
    if project_id and not _ID_RE.match(project_id):
        return {"error": "project_id が不正です。"}, 400
    limit = _clean_int(request.args.get("limit"), 100, 1, 500)
    try:
        reports = report_doc.list_reports(
            _out(), status=status, project_id=project_id, limit=limit
        )
        return {"reports": [_report_summary(r) for r in reports]}
    except Exception:
        logger.exception("healing: 報告書の一覧取得に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.get("/api/healing/reports/<report_id>")
def api_get_report(report_id: str):
    if not _ID_RE.match(report_id):
        abort(404)
    try:
        out_dir = _out()
        report = report_doc.load_report(out_dir, report_id)
        if report is None:
            return {"error": "報告書が見つかりません"}, 404
        run = orchestrator.get_run(out_dir, report.run_id)
        proposal = _proposal_of(run, report.defect_id)
        return {
            "report": report_doc.to_dict(report),
            "proposal": proposal,
            "run": run_store.run_summary(run) if run is not None else None,
        }
    except Exception:
        logger.exception("healing: 報告書の取得に失敗しました")
        return {"error": "処理に失敗しました"}, 500


def _proposal_of(run: Any, defect_id: str) -> dict[str, Any] | None:
    """報告書に対応する修正案。差分と根拠は折りたたみの中でしか使わない。"""
    if run is None:
        return None
    for iteration in run.iterations:
        for proposal in iteration.proposals:
            if proposal.defect_id != defect_id:
                continue
            locations: list[dict[str, Any]] = []
            for defect in iteration.defects:
                if defect.defect_id == defect_id:
                    locations = [dict(loc) for loc in defect.locations]
                    break
            return {
                "diff": proposal.diff,
                "files_changed": list(proposal.files_changed),
                "rationale": proposal.rationale,
                "agent": proposal.agent,
                "status": proposal.status,
                "locations": locations,
            }
    return None


@bp.patch("/api/healing/reports/<report_id>")
def api_update_report(report_id: str):
    """人が対応欄・原因欄を書き足す。自動では直せなかった報告書で使う。"""
    guard = require_admin()
    if guard is not None:
        return guard
    if not _ID_RE.match(report_id):
        abort(404)
    data = _body()
    try:
        from dataclasses import replace as _replace

        out_dir = _out()
        report = report_doc.load_report(out_dir, report_id)
        if report is None:
            return {"error": "報告書が見つかりません"}, 404
        changes: dict[str, Any] = {}
        if "action_text" in data:
            changes["action_text"] = _clean_note(data.get("action_text"))
        if "cause_text" in data:
            changes["cause_text"] = _clean_note(data.get("cause_text"))
        if not changes:
            return {"error": "更新する項目がありません"}, 400
        # 中身が変わったときだけ最終更新日時を進める。同じ値で保存し直しただけの
        # PATCH で日時が動くと「いつ人が手を入れたか」の証跡として読めなくなる。
        touched = any(getattr(report, key) != value for key, value in changes.items())
        updated_at = (
            datetime.now().isoformat(timespec="seconds") if touched else report.updated_at
        )
        report = _replace(report, **changes, updated_at=updated_at)
        report_doc.save_report(out_dir, report)
        _record_audit("healing.report.update", {"report_id": report_id})
        return {"report": report_doc.to_dict(report)}
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: 報告書の更新に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.post("/api/healing/reports/<report_id>/decision")
def api_decide_report(report_id: str):
    """承認・差し戻し・却下。承認したときだけ PR を作る。"""
    guard = require_admin()
    if guard is not None:
        return guard
    if not _ID_RE.match(report_id):
        abort(404)
    data = _body()
    action = _clean_short_text(data.get("action"), "", 16)
    if action not in REPORT_ACTIONS:
        return {"error": f"不正な操作です: {action}"}, 400
    try:
        note = _clean_note(data.get("note"))
        actor = _clean_short_text(data.get("actor"), "", 64)
        report = orchestrator.decide_report(
            _out(), report_id, action=action, note=note, actor=actor
        )
        _record_audit(
            "healing.report.decision",
            {"report_id": report_id, "action": action, "actor": actor},
        )
        return {"report": report_doc.to_dict(report)}
    except HealingError as exc:
        return _error_response(exc)
    except Exception:
        logger.exception("healing: 報告書の判断に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.get("/api/healing/reports/<report_id>/export")
def api_export_report(report_id: str):
    """顧客に出す形で書き出す。承認前でも下書きとして出せる。"""
    if not _ID_RE.match(report_id):
        abort(404)
    fmt = _clean_short_text(request.args.get("format"), "md", 8)
    try:
        report = report_doc.load_report(_out(), report_id)
        if report is None:
            return {"error": "報告書が見つかりません"}, 404
        if fmt == "json":
            return {"report": report_doc.to_dict(report)}
        if fmt == "md":
            body = report_doc.render_markdown(report)
            return body, 200, {"Content-Type": "text/markdown; charset=utf-8"}
        if fmt == "html":
            return render_template(
                "healing_report_print.html", report=report_doc.to_dict(report)
            )
        return {"error": f"未対応の形式です: {fmt}"}, 400
    except Exception:
        logger.exception("healing: 報告書の書き出しに失敗しました")
        return {"error": "処理に失敗しました"}, 500
