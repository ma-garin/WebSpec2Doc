"""実行環境（dev / stg / prod）管理の API。

環境定義の正本は output/<domain>/environments.json。
実行系は env_id を 1 つ受け取り、base_url と storage state をここから解決する。

全エンドポイントで domain を検証してから services へ渡す。検証せずにパス要素へ
渡すと `../` で他テナントの出力を読めてしまうため。
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, request

from web.config import OUTPUT_DIR
from web.services import environment_store
from web.services.environment_store import EnvironmentValidationError
from web.tenancy import scoped_output_dir
from web.validation import _valid_domain

logger = logging.getLogger(__name__)

bp = Blueprint("environments", __name__)


def _out() -> Path:
    """テナントスコープ済みの出力ディレクトリ（リクエスト毎に解決）。"""
    return scoped_output_dir(Path(OUTPUT_DIR))


@bp.get("/api/environments/<domain>")
def api_get_environments(domain: str) -> dict | tuple[dict, int]:
    """保存済みの環境定義。未作成なら空で返す（404 にしない）。

    「まだ 1 件も登録していない」は異常ではなく初期状態であり、画面はそのまま
    新規登録フォームを出せる必要がある。
    """
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    root = _out()
    try:
        document = environment_store.load(root, domain)
    except EnvironmentValidationError as exc:
        # 壊れたファイルは 409。空で返すと利用者が上書き保存して定義を失う。
        return {"error": str(exc)}, 409
    return {
        "document": document,
        "saved": environment_store.store_path(root, domain).is_file(),
    }


@bp.put("/api/environments/<domain>")
def api_put_environments(domain: str) -> dict | tuple[dict, int]:
    """環境定義を保存する。検証に落ちたら、どこが悪いかを本文で返す。"""
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    body = request.get_json(silent=True)
    if body is None:
        return {"error": "JSON 本文が必要です。"}, 400
    root = _out()
    try:
        path = environment_store.save(root, domain, body)
    except EnvironmentValidationError as exc:
        # 400 で理由を返す。保存できない理由を画面に出せないと直しようがない。
        return {"error": str(exc)}, 400
    document = environment_store.load(root, domain)
    return {
        "saved": True,
        "path": str(path),
        "document": document,
        "environments": len(document.get("environments", [])),
    }
