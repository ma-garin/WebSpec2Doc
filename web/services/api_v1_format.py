"""/api/v1 の応答を共通の形に揃える（対象・版・出所の meta と、エラー形式）。

- 成功: 本体に ``meta: {target, version, source}`` を足す（既存キーは変えない）。
- 失敗: ``{"error": {"code", "message"}}`` に揃える。既存ルートの文字列エラーと、
  本文の無い 4xx（CSRF の 403 等）も after_request でこの形へ変換する。
"""

from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, Response, request

API_VERSION = "1.0"

# 共通 I/F（common-contract §3.1）の語彙。500 は語彙に無いため internal_error を使う。
STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "too_large",
    500: "internal_error",
    502: "upstream_failed",
}

DEFAULT_MESSAGES: dict[str, str] = {
    "bad_request": "入力が正しくありません。項目を見直して再送してください。",
    "unauthorized": "ログインが必要です。ログインしてから再度操作してください。",
    "forbidden": "この操作を行う権限がありません。管理者に依頼してください。",
    "not_found": "対象が見つかりません。一覧を再読込して対象を選び直してください。",
    "conflict": "同じ対象の処理が進行中です。終わるのを待ってから再度操作してください。",
    "too_large": "送信した内容が大きすぎます。量を減らして再送してください。",
    "internal_error": "サーバ内部で失敗しました。時間をおいて再試行し、続く場合は管理者に連絡してください。",
    "upstream_failed": "連携先の処理が失敗しました。時間をおいて再試行してください。",
}

# 既存ルートの英語メッセージを利用者向けの日本語へ寄せる（未登録の文言はそのまま残す）。
_MESSAGE_JA: dict[str, str] = {
    "invalid domain": "対象サイト名の形式が正しくありません。英数字・ドット・ハイフンで指定してください。",
    "report not found": "レポートがまだありません。先にクロールを実行してください。",
    "job not found": "ジョブが見つかりません。サーバの再起動で消えた可能性があります。一覧を再読込してください。",
    "failed to read report": "レポートを読み込めませんでした。再度クロールを実行してください。",
}

# 出所: その応答の値をどこから読んだか（利用者が裏を取るための手掛かり）。
_SOURCES: dict[str, str] = {
    "api_healthz": "サーバの稼働状態",
    "api_sites": "登録済みサイト台帳",
    "api_report": "最新のレポート（report.json）",
    "api_snapshots": "スナップショット履歴",
    "api_diff": "スナップショット間の差分計算",
    "api_crawl": "ジョブキュー（サーバのメモリ内・再起動で消える）",
    "api_job_status": "ジョブキュー（サーバのメモリ内・再起動で消える）",
    "api_domain_jobs": "ジョブキュー（サーバのメモリ内・再起動で消える）",
    "api_jobs": "ジョブキュー（サーバのメモリ内・再起動で消える）",
    "api_test_cases": "テスト候補（playwright_candidates.json）",
    "api_v1_schedule_get": "定期クロール設定",
    "api_v1_schedule_put": "定期クロール設定",
    "api_v1_schedule_delete": "定期クロール設定",
    "api_v1_schedules": "定期クロール設定",
    "api_v1_notifications_get": "通知設定",
    "api_v1_notifications_put": "通知設定",
}

_SKIP_ENDPOINTS = frozenset({"api_openapi_spec", "api_docs"})


def api_error(code: str, message: str = "", status: int | None = None, **extra: Any) -> tuple[dict, int]:
    """共通エラー形式の応答を作る。"""
    body: dict[str, Any] = {"code": code, "message": message or DEFAULT_MESSAGES.get(code, "")}
    body.update(extra)
    resolved = status or next((s for s, c in STATUS_CODES.items() if c == code), 400)
    return {"error": body}, resolved


def _normalize_error(data: dict[str, Any], status: int) -> dict[str, Any]:
    err = data.get("error")
    if isinstance(err, dict) and "code" in err:
        return data
    code = str(data.get("code") or STATUS_CODES.get(status, "bad_request"))
    if code == "forbidden_scope":
        code = "forbidden"
    raw = str(err) if err else ""
    message = _MESSAGE_JA.get(raw, raw) or DEFAULT_MESSAGES.get(code, "")
    rest = {k: v for k, v in data.items() if k not in {"error", "code"}}
    return {**rest, "error": {"code": code, "message": message}}


def _meta() -> dict[str, Any]:
    args = request.view_args or {}
    endpoint = (request.endpoint or "").rsplit(".", 1)[-1]
    target = args.get("domain") or args.get("job_id")
    return {
        "target": target,
        "version": API_VERSION,
        "source": _SOURCES.get(endpoint, "WebSpec2Doc API"),
    }


def shape_response(response: Response) -> Response:
    """after_request: meta の付与とエラー形式の統一。"""
    endpoint = (request.endpoint or "").rsplit(".", 1)[-1]
    if endpoint in _SKIP_ENDPOINTS:
        return response
    status = response.status_code
    data = response.get_json(silent=True) if response.is_json else None
    if data is None and status >= 400 and not response.get_data():
        data = {}
    if not isinstance(data, dict):
        return response
    shaped = _normalize_error(data, status) if status >= 400 else dict(data)
    shaped.setdefault("meta", _meta())
    response.set_data(json.dumps(shaped, ensure_ascii=False))
    response.mimetype = "application/json"
    return response


def install(bp: Blueprint) -> None:
    bp.after_request(shape_response)


# ── ジョブの状態 → 利用者向けの文言と次の行動 ──

_JOB_TEXT: dict[str, tuple[str, str]] = {
    "queued": ("待機中", "順番を待っています。数秒後に一覧を再読込してください。"),
    "running": ("実行中", "クロール中です。終わるまで同じサイトへの再投入はできません。"),
    "completed": ("完了", "結果のレポートを開いて内容を確認してください。"),
}


def job_view(job: dict[str, Any]) -> dict[str, str]:
    """ジョブ 1 件の表示用の状態・文言・次の行動を返す。"""
    status = str(job.get("status", ""))
    if status in _JOB_TEXT:
        label, action = _JOB_TEXT[status]
        return {"label": label, "reason": "", "next_action": action}
    if status != "failed":
        return {"label": "不明", "reason": "状態を判別できません。", "next_action": "一覧を再読込してください。"}
    log = str(job.get("log_tail", ""))
    if "BLOCKED" in log:
        reason = "クロール用のブラウザが起動できませんでした。"
        action = "サーバ管理者にブラウザの導入状況を確認してもらい、再投入してください。"
    elif job.get("exit_code") == -1:
        reason = "クロール処理を開始できませんでした。"
        action = "証跡のログ末尾を確認し、管理者に連絡してください。"
    else:
        reason = "対象サイトの解析が途中で失敗しました（接続できない URL の可能性があります）。"
        action = "URL が開けるかを確かめ、深さ・最大画面数を減らして再投入してください。"
    return {"label": "失敗", "reason": reason, "next_action": action}
