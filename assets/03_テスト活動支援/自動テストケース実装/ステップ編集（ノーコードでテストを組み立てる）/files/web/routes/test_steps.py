"""ステップ編集（ノーコード）の API。

編集の正本は output/<domain>/qa_process/test_steps.json。
spec.ts は常にそこから生成する（生成物を直接編集させない）。

全エンドポイントで domain を検証してから services へ渡す。検証せずにパス要素へ
渡すと `../` で他テナントの出力を読めてしまうため。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, request

from web.config import OUTPUT_DIR
from web.services import test_step_store
from web.services.test_step_store import StepValidationError
from web.tenancy import scoped_output_dir
from web.validation import _valid_domain

logger = logging.getLogger(__name__)

bp = Blueprint("test_steps", __name__)

# 生成した spec の置き場。実行系が読む場所と揃える。
_SPEC_RELATIVE = "qa_process/edited.spec.ts"


def _out() -> Path:
    return scoped_output_dir(Path(OUTPUT_DIR))


@bp.get("/api/test-steps/actions")
def api_actions() -> dict:
    """編集画面が使う動作の語彙。画面側にハードコードさせない。

    語彙を両側に書くと、片方だけ増えたときに「選べるのに保存できない」が起きる。
    """
    return {
        "actions": [
            {
                "action": key,
                "label": spec["label"],
                "needs_target": spec["needs_target"],
                "needs_value": spec["needs_value"],
            }
            for key, spec in test_step_store.ACTIONS.items()
        ]
    }


@bp.get("/api/test-steps/sites")
def api_sites() -> dict:
    """ステップ編集の対象になりうるサイト。

    「解析済み（候補がある）」か「すでにステップを保存済み」のどちらか。
    実行履歴や実行回とは別の条件で、まだ一度も実行していないサイトでも編集できる。
    """
    root = _out()
    sites: list[dict[str, Any]] = []
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if not child.is_dir() or not _valid_domain(child.name):
                continue
            has_steps = test_step_store.store_path(root, child.name).is_file()
            has_candidates = (child / "qa_process" / "playwright_candidates.json").is_file()
            if has_steps or has_candidates:
                sites.append(
                    {"domain": child.name, "has_steps": has_steps, "has_candidates": has_candidates}
                )
    return {"sites": sites, "total": len(sites)}


@bp.get("/api/test-steps/<domain>")
def api_get_steps(domain: str) -> dict | tuple[dict, int]:
    """保存済みのステップ。未作成なら空で返す（404 にしない）。"""
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    try:
        document = test_step_store.load(_out(), domain)
    except StepValidationError as exc:
        return {"error": str(exc)}, 409
    return {
        "document": document,
        "saved": test_step_store.store_path(_out(), domain).is_file(),
    }


@bp.put("/api/test-steps/<domain>")
def api_put_steps(domain: str) -> dict | tuple[dict, int]:
    """ステップを保存する。検証に落ちたら、どこが悪いかを本文で返す。"""
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    body = request.get_json(silent=True)
    if body is None:
        return {"error": "JSON 本文が必要です。"}, 400
    try:
        path = test_step_store.save(_out(), domain, body)
    except StepValidationError as exc:
        # 400 で理由を返す。保存できない理由を画面に出せないと直しようがない。
        return {"error": str(exc)}, 400
    document = test_step_store.load(_out(), domain)
    return {"saved": True, "path": str(path), "tests": len(document.get("tests", []))}


@bp.post("/api/test-steps/<domain>/import")
def api_import_steps(domain: str) -> dict | tuple[dict, int]:
    """クローラの候補からステップの叩き台を作る。

    白紙のエディタを出しても人は書けない。実測済みの画面・項目から作る。
    既存の編集を消さないよう、保存はせず候補だけ返す（保存は利用者の操作）。
    """
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    candidates_path = _out() / domain / "qa_process" / "playwright_candidates.json"
    if not candidates_path.is_file():
        return {
            "error": "クローラの候補がありません。先に解析を実行してください。",
            "looked_at": str(candidates_path),
        }, 404
    try:
        data = json.loads(candidates_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"候補ファイルを読めません: {exc}"}, 409
    document = test_step_store.import_from_candidates(
        data.get("candidates") or [], domain
    )
    return {"document": document, "tests": len(document["tests"])}


@bp.post("/api/test-steps/<domain>/generate")
def api_generate_spec(domain: str) -> dict | tuple[dict, int]:
    """保存済みステップから spec.ts を生成する。"""
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    try:
        document = test_step_store.load(_out(), domain)
    except StepValidationError as exc:
        return {"error": str(exc)}, 409
    if not document.get("tests"):
        return {"error": "ステップがまだありません。保存してから生成してください。"}, 400

    body = request.get_json(silent=True) or {}
    source = test_step_store.to_spec_ts(
        document,
        self_healing=bool(body.get("self_healing", True)),
        egress_gateway=bool(body.get("egress_gateway", True)),
    )
    path = _out() / domain / _SPEC_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    enabled = [t for t in document["tests"] if t.get("enabled", True)]
    return {
        "generated": True,
        "path": str(path),
        "tests": len(enabled),
        "skipped": len(document["tests"]) - len(enabled),
        "lines": len(source.splitlines()),
        "preview": source[:4000],
    }
