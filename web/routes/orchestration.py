"""指揮者（O2）の API。

5 つのシステムを 1 本の実行として束ねる入口。書き方は healing.py に揃える
（_out / require_admin / _body / _record_audit / _error_response / ID の検証）。
状態機械そのものは web/services/orchestration/conductor.py が持ち、ここは
入力の検証と、結果を JSON にして返すことだけを行う。
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import Blueprint, g, render_template, request
from jinja2 import TemplateNotFound

from web.audit_context import record_admin_event
from web.auth import require_admin
from web.config import OUTPUT_DIR
from web.services.orchestration import (
    conductor,
    goals,
    home_summary,
    onboarding,
    run_store,
    workflow_actions,
    workflow_view,
)
from web.services.orchestration.workflow_actions import ActionError
from web.tenancy import scoped_output_dir
from web.validation import _domain_of

bp = Blueprint("orchestration", __name__)

logger = logging.getLogger(__name__)

#: 監査ログの置き場。他ルート（healing.py / settings.py）と同じ規約。
INSTANCE_DIR = Path("instance")

#: run_id は指揮者が作る形だけを受け付ける（ファイル名に直結するため）。
_ID_RE = re.compile(r"^cond-[0-9a-f]{12}$")
#: ポート付き（localhost:3000 等）も受ける。開発中のサイトを保守下に置くのは
#: 「初めてのサイト」の主戦場で、ここで弾くと API から一切 onboard できない。
_DOMAIN_RE = re.compile(r"^[0-9a-zA-Z][0-9a-zA-Z._-]{0,252}(?::\d{1,5})?$")
_PROJECT_ID_RE = re.compile(r"^[0-9a-zA-Z_-]{1,64}$")

_BUSY = "このサイトの指揮はまだ終わっていません"

#: 段へ渡す params で受け付けるキーと境界。それ以外のキーは黙って捨てる。
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_MAX_URL_LEN = 2000
_MAX_REPO_LEN = 1000
_MAX_VERIFY_LEN = 500


def _out() -> Path:
    """テナントスコープ済みの出力ディレクトリ（リクエスト毎に解決）。"""
    return scoped_output_dir(OUTPUT_DIR)


def _body() -> dict[str, Any]:
    data: dict[str, Any] = {}
    if request.form:
        data.update(request.form.to_dict())
    json_data = request.get_json(silent=True)
    if isinstance(json_data, dict):
        data.update(json_data)
    return data


def _actor() -> str:
    """実行を起こした人。認証オフなら空（記録は「不明」と読める）。"""
    user = getattr(g, "auth_user", None)
    if not isinstance(user, dict):
        return ""
    return str(user.get("email") or user.get("name") or "")


def _record_audit(action: str, detail: dict[str, Any]) -> None:
    """管理操作の証跡を残す。記録できなくても本処理は止めない（黙って落とさない）。"""
    target_type = action.split(".")[1] if len(action.split(".")) >= 2 else "orchestration"
    target_id = str(detail.get("run_id") or detail.get("domain") or "current")
    try:
        record_admin_event(
            INSTANCE_DIR, action=action, target_type=target_type,
            target_id=target_id, detail=detail,
        )
    except Exception:
        logger.warning(
            "orchestration: 監査ログの記録に失敗しました (action=%s target=%s/%s)",
            action, target_type, target_id, exc_info=True,
        )


_HOME_PATHS: tuple[str, ...] = tuple(
    dict.fromkeys(
        p for p in (str(Path.home()).rstrip("/"), str(Path.home().resolve()).rstrip("/")) if p
    )
)
_HOME_USER: str = Path.home().name


def _error_response(exc: Exception) -> tuple[dict[str, Any], int]:
    """利用者へ返す 400 応答。理由は残しつつ実パスと利用者名だけを伏せる。"""
    masked = str(exc)
    for home in _HOME_PATHS:
        masked = masked.replace(home, "~")
    if len(_HOME_USER) >= 3:
        masked = masked.replace(_HOME_USER, "~")
    return {"error": masked}, 400


def _clean_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _strict_int(value: Any) -> int | None:
    """範囲外・型違いは None（呼び出し側が 400 にする。既定値へ丸めない）。"""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_params(data: dict[str, Any], domain: str) -> tuple[dict[str, Any], str]:
    """段へ渡す params を検証する。合格した params と、不合格なら理由（日本語）を返す。

    受け付けるキーは url / depth / max_pages だけ。それ以外は黙って捨てる
    （docs_agent.DEFAULT_DEPTH / DEFAULT_MAX_PAGES がそのまま既定値になる）。
    """
    raw = data.get("params")
    if not isinstance(raw, Mapping):
        return {}, ""
    params: dict[str, Any] = {}
    if "url" in raw:
        url = str(raw.get("url") or "").strip()
        if not url or not _URL_RE.match(url) or len(url) > _MAX_URL_LEN:
            return {}, "url は http:// か https:// で始まる 2000 字以内で指定してください。"
        if _domain_of(url) != domain:
            return {}, "URL のサイトと domain が一致しません。"
        params["url"] = url
    if "depth" in raw:
        depth = _strict_int(raw.get("depth"))
        if depth is None or not (1 <= depth <= 3):
            return {}, "depth は 1〜3 の整数で指定してください。"
        params["depth"] = depth
    if "max_pages" in raw:
        max_pages = _strict_int(raw.get("max_pages"))
        if max_pages is None or not (1 <= max_pages <= 50):
            return {}, "max_pages は 1〜50 の整数で指定してください。"
        params["max_pages"] = max_pages
    return params, ""


#: 画面は 2 つ。b = 指揮（一覧・既定）、d = サイト別の記録。
_VARIANTS: tuple[str, ...] = ("b", "d")

#: /orchestration は必ずこれを出す。A/B の振り分けと cookie は廃止した。
_DEFAULT_VARIANT = "b"

#: ?site= のサイト名。保守対象は "127.0.0.1:8765" のように :port を持つ。
_SITE_RE = re.compile(r"^[0-9a-zA-Z][0-9a-zA-Z._-]{0,252}(?::[0-9]{1,5})?$")

#: 計測イベント。増やすときはここへ 1 つ足す（画面と API の 2 か所に散らさない）。
_AB_EVENTS: tuple[str, ...] = ("first_action", "view")
_AB_MAX_MS = 600_000
_AB_MAX_TARGET = 80
_AB_LOG = INSTANCE_DIR / "ab_events.jsonl"


def _site_arg() -> str:
    """?site= のサイト名。形が違えば空にする（画面は先頭のサイトを開く）。"""
    site = str(request.args.get("site", "")).strip()
    return site if _SITE_RE.match(site) else ""


def _render_variant(variant: str, site: str = "") -> str:
    """画面のテンプレートをそのまま描画する。リダイレクトしない。

    site は案 D（サイト別の記録）が最初に開くサイト。空なら画面が先頭を選ぶ。
    """
    return render_template(f"orchestration_{variant}.html", variant=variant, site=site)


@bp.get("/orchestration")
def orchestration_page():
    """指揮の入口。ワークフロー画面（6 工程のステッパー）を出す。

    旧案（b / 一覧・d / サイト別記録）は /orchestration/<variant> にまだ残る
    （開発・比較用）。ここは新画面のテンプレートが無ければ 404 を返す
    （別担当が同時に作っているため）。
    """
    site = _site_arg()
    # ?site= か ?mode=detail があれば個別実行詳細（5 工程）、無ければ日常運用ホーム。
    mode = "detail" if (site or request.args.get("mode") == "detail") else "home"
    try:
        return render_template("orchestration.html", site=site, mode=mode)
    except TemplateNotFound:
        return {"error": "画面がまだありません。"}, 404


@bp.get("/api/home/summary")
def api_home_summary():
    """指揮ホーム用の全サイト集計（読み取りのみ）。?view= は all/human/failed/unverified。"""
    view = str(request.args.get("view", "all")).strip().lower()
    try:
        return home_summary.build(_out(), view)
    except Exception:  # noqa: BLE001
        logger.exception("orchestration: ホーム集計に失敗しました")
        return {"error": "ホームの集計を読み込めませんでした。", "code": "summary_failed"}, 500


@bp.get("/orchestration/<variant>")
def orchestration_variant_page(variant: str):
    """画面を名指しで開く。d は ?site= でそのサイトの記録を開く。"""
    key = str(variant or "").strip().lower()
    if key not in _VARIANTS:
        return {"error": "その案はありません。"}, 404
    return _render_variant(key, _site_arg())


@bp.post("/api/orchestration/ab")
def api_ab_event():
    """A/B の計測を 1 行足す。閲覧できる人なら誰でも記録できる（管理者に限らない）。"""
    data = _body()
    variant = str(data.get("variant") or "").strip().lower()
    event = str(data.get("event") or "").strip()
    target = str(data.get("target") or "")
    ms = _strict_int(data.get("ms"))
    if variant not in _VARIANTS:
        return {"error": "案の指定が不正です。"}, 400
    if event not in _AB_EVENTS:
        return {"error": "計測の種類が不正です。"}, 400
    if ms is None or not (0 <= ms <= _AB_MAX_MS):
        return {"error": "経過時間の指定が不正です。"}, 400
    if len(target) > _AB_MAX_TARGET:
        return {"error": "対象の名前が長すぎます。"}, 400
    record = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "variant": variant, "event": event, "ms": ms,
        "target": target, "user": _actor(),
    }
    try:
        INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
        with _AB_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("orchestration: A/B の記録に失敗しました")
        return {"error": "処理に失敗しました"}, 500
    return {"ok": True}


@bp.get("/api/orchestration/goals")
def api_list_goals():
    """目標の一覧。まだ通せない目標も理由つきで返す。"""
    try:
        return {"goals": goals.catalog()}
    except Exception:
        logger.exception("orchestration: 目標一覧の作成に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.get("/api/orchestration/runs")
def api_list_runs():
    domain = str(request.args.get("domain", "")).strip()
    if domain and not _DOMAIN_RE.match(domain):
        return {"error": "サイトの指定が不正です。"}, 400
    limit = _clean_int(request.args.get("limit"), 50, 1, 200)
    try:
        out_dir = _out()
        reaped = conductor.reap_orphans(out_dir)
        if reaped:
            logger.info("orchestration: 止まった指揮を %d 件片付けました (%s)",
                        len(reaped), ", ".join(reaped))
        return {"runs": conductor.list_summaries(out_dir, domain=domain, limit=limit)}
    except Exception:
        logger.exception("orchestration: list_summaries に失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.post("/api/orchestration/runs")
def api_start_run():
    """指揮を 1 本起こす。同じサイトで 2 本は走らせない（409）。"""
    guard = require_admin()
    if guard is not None:
        return guard
    data = _body()
    domain = str(data.get("domain") or "").strip()
    goal = str(data.get("goal") or "").strip()
    project_id = str(data.get("project_id") or "").strip()
    if goal not in goals.AVAILABLE_GOALS:
        return {"error": "目標を指定してください（daily か onboard）"}, 400
    if project_id and not _PROJECT_ID_RE.match(project_id):
        return {"error": "project_id が不正です。"}, 400

    raw_params = data.get("params")
    raw_params = raw_params if isinstance(raw_params, Mapping) else {}
    rounds_value = data.get("rounds", raw_params.get("rounds"))
    rounds = 1
    if rounds_value is not None:
        rounds = _strict_int(rounds_value)
        if rounds is None or not (1 <= rounds <= 5):
            return {"error": "rounds は 1〜5 の整数で指定してください。"}, 400

    out_dir = _out()
    created_project = False

    # 初めてのサイトは url から接続先を用意する。順序が肝心——検証を全部
    # 済ませてから作る。作ってから検証すると、400 を返したあとにも接続先
    # （GitHub なら clone 済みのコード）だけが残り、サイト一覧に「選ぶと必ず
    # エラーになる項目」として並び続ける。
    repo = str(data.get("repo") or "")
    verify_command = str(data.get("verify_command") or "")
    params: dict[str, Any] | None = None
    if goal == "onboard" and (not domain or repo or verify_command):
        url = str(raw_params.get("url") or "").strip()
        if len(repo) > _MAX_REPO_LEN:
            return {"error": f"コードの場所は {_MAX_REPO_LEN} 字以内で指定してください。"}, 400
        if len(verify_command) > _MAX_VERIFY_LEN:
            return {"error": f"verify_command は {_MAX_VERIFY_LEN} 字以内で指定してください。"}, 400
        if not url or not _URL_RE.match(url) or len(url) > _MAX_URL_LEN:
            return {"error": "url は http:// か https:// で始まる 2000 字以内で指定してください。"}, 400
        derived = _domain_of(url)
        if not derived or not _DOMAIN_RE.match(derived):
            return {"error": "サイトの指定が不正です。"}, 400
        if domain and domain != derived:
            return {"error": "URL のサイトと domain が一致しません。"}, 400
        if conductor.has_active_run(out_dir, derived):
            return {"error": _BUSY}, 409
        # depth / max_pages の検査も接続先を作る前に済ませる（再検証で判明）
        params, params_error = _clean_params(data, derived)
        if params_error:
            return {"error": params_error}, 400
        try:
            plan = onboarding.prepare(
                out_dir, url=url, repo=repo, verify_command=verify_command,
                rounds=rounds, actor=_actor(),
            )
        except ValueError as exc:
            return _error_response(exc)
        except OSError:  # 長すぎる名前など OS 由来の失敗。500 にしない
            logger.warning("orchestration: 接続先を用意できませんでした", exc_info=True)
            return {"error": "コードの場所を確認できませんでした。指定を見直してください。"}, 400
        domain = plan.domain
        project_id = project_id or plan.project_id
        created_project = plan.created_project

    if not _DOMAIN_RE.match(domain):
        return {"error": "サイトの指定が不正です。"}, 400
    if params is None:
        params, params_error = _clean_params(data, domain)
        if params_error:
            return {"error": params_error}, 400
    params["rounds"] = rounds

    try:
        run = conductor.start_if_idle(
            out_dir=out_dir, domain=domain, goal=goal,
            project_id=project_id, actor=_actor(), params=params,
        )
    except ValueError as exc:  # 未知・未対応の目標。理由をそのまま返す
        return _error_response(exc)
    except Exception:
        logger.exception("orchestration: start_if_idle に失敗しました")
        return {"error": "処理に失敗しました"}, 500
    if run is None:
        return {"error": _BUSY}, 409
    _record_audit(
        "orchestration.run.start",
        {"run_id": run.run_id, "domain": domain, "goal": goal, "project_id": project_id},
    )
    return {
        "run": run_store.run_to_dict(run),
        "project_id": project_id,
        "created_project": created_project,
    }, 202


@bp.get("/api/orchestration/runs/<run_id>")
def api_get_run(run_id: str):
    if not _ID_RE.match(run_id):
        return {"error": "run_id が不正です。"}, 400
    try:
        run = conductor.get(_out(), run_id)
    except Exception:
        logger.exception("orchestration: get に失敗しました")
        return {"error": "処理に失敗しました"}, 500
    if run is None:
        return {"error": "実行が見つかりません。"}, 404
    return {"run": run_store.run_to_dict(run)}


@bp.post("/api/orchestration/runs/<run_id>/cancel")
def api_cancel_run(run_id: str):
    """中止を伝える。走っている段そのものは止めない（次の確認で止まる）。"""
    if not _ID_RE.match(run_id):
        return {"error": "run_id が不正です。"}, 400
    guard = require_admin()
    if guard is not None:
        return guard
    try:
        out_dir = _out()
        cancelled = conductor.cancel(out_dir, run_id)
        run = conductor.get(out_dir, run_id)
    except Exception:
        logger.exception("orchestration: cancel に失敗しました")
        return {"error": "処理に失敗しました"}, 500
    if run is None:
        return {"error": "実行が見つかりません。"}, 404
    _record_audit("orchestration.run.cancel", {"run_id": run_id, "cancelled": bool(cancelled)})
    return {"run": run_store.run_to_dict(run), "cancelled": bool(cancelled)}


# ─────────────────────────── ワークフロー画面（新 UI） ───────────────────────────


@bp.get("/api/orchestration/workflow")
def api_workflow_state():
    """ワークフロー画面 1 画面分の状態。domain が空なら最初のサイトを開く。"""
    site = str(request.args.get("site", "")).strip()
    if site and not _DOMAIN_RE.match(site):
        return {"error": "サイトの指定が不正です。"}, 400
    try:
        return workflow_view.build(_out(), site)
    except Exception:
        logger.exception("orchestration: workflow の組み立てに失敗しました")
        return {"error": "処理に失敗しました"}, 500


@bp.post("/api/orchestration/workflow/actions")
def api_workflow_action():
    """ワークフロー画面のボタン 1 つを実行し、最新の状態を返す。"""
    guard = require_admin()
    if guard is not None:
        return guard
    data = _body()
    site = str(data.get("site") or "").strip()
    if site and not _DOMAIN_RE.match(site):
        return {"error": "サイトの指定が不正です。"}, 400
    kind = str(data.get("kind") or "").strip()
    try:
        result = workflow_actions.perform(_out(), site, kind, data, _actor())
    except ActionError as exc:
        return {"error": str(exc)}, 400
    except Exception:
        logger.exception("orchestration: workflow アクションに失敗しました (kind=%s)", kind)
        return {"error": "処理に失敗しました"}, 500
    _record_audit("orchestration.workflow.action", {"domain": site, "kind": kind})
    return result
