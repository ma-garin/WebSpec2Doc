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


def _write_spec(
    domain: str,
    document: dict[str, Any],
    *,
    self_healing: bool = True,
    egress_gateway: bool = True,
) -> tuple[Path, str]:
    """ドキュメントから spec.ts を生成して書き出す。(パス, ソース) を返す。

    生成（/generate）と実行（/run）で同じ経路を通す。別々に書くと、片方だけ
    オプションが増えたときに「プレビューで見たコードと実行したコードが違う」が起きる。
    """
    source = test_step_store.to_spec_ts(
        document, self_healing=self_healing, egress_gateway=egress_gateway
    )
    path = _out() / domain / _SPEC_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path, source


@bp.post("/api/test-steps/<domain>/generate")
def api_generate_spec(domain: str) -> dict | tuple[dict, int]:
    """保存済みステップから spec.ts を生成する。

    実行（/run）とは別に残す。「実行せずコードだけ確認したい」導線を潰さないため。
    """
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    try:
        document = test_step_store.load(_out(), domain)
    except StepValidationError as exc:
        return {"error": str(exc)}, 409
    if not document.get("tests"):
        return {"error": "ステップがまだありません。保存してから生成してください。"}, 400

    body = request.get_json(silent=True) or {}
    path, source = _write_spec(
        domain,
        document,
        self_healing=bool(body.get("self_healing", True)),
        egress_gateway=bool(body.get("egress_gateway", True)),
    )
    enabled = [t for t in document["tests"] if t.get("enabled", True)]
    return {
        "generated": True,
        "path": str(path),
        "tests": len(enabled),
        "skipped": len(document["tests"]) - len(enabled),
        "lines": len(source.splitlines()),
        "preview": source[:4000],
    }


@bp.post("/api/test-steps/<domain>/run")
def api_run_steps(domain: str) -> dict | tuple[dict, int]:
    """編集したステップから spec を生成し、その場で実行キューへ積む。

    生成経路は /generate と同じ `_write_spec()` を通す。実行だけ別の生成に
    しないのは、「プレビューしたコードと実行されたコードが違う」を作らないため。

    body（すべて任意）:
        test_ids: 実行するテスト ID の配列（空なら有効なテスト全部）
        environment: 実行環境 ID（空なら既定環境。環境未登録なら従来の単一環境動作）
        retries / per_test_timeout_sec / update_snapshots / headed / self_healing

    Returns:
        202: {"job_id", "queued_position", "spec_path", "tests", "environment"}
        400: 実行対象 0 件、または指定された環境が存在しない
        409: 同一ドメインで実行中/待機中のジョブがある（running_job_id を返す）
    """
    from crawler.url_safety import _local_targets_allowed

    from web.services import environment_store, test_run_job
    from web.services.egress_gateway import EgressPolicy

    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    try:
        document = test_step_store.load(_out(), domain)
    except StepValidationError as exc:
        return {"error": str(exc)}, 409

    body = request.get_json(silent=True) or {}

    # ① 実行対象の絞り込み。無効なテストは常に除外する。
    tests = [t for t in document.get("tests", []) if t.get("enabled", True)]
    wanted = body.get("test_ids")
    if isinstance(wanted, list) and wanted:
        allow = {str(x) for x in wanted}
        tests = [t for t in tests if str(t.get("test_id")) in allow]
    if not tests:
        # 0 件で走らせると「成功 0 件」の実行回だけが残り、誤って合格に見える。
        return {"error": "実行対象のテストがありません。"}, 400

    target_doc = dict(document)
    target_doc["tests"] = tests

    # ② 環境の解決。指定した環境が無いときに既定へ倒すと、意図しない環境へ
    #    テストが流れる。倒さずに 400 で止める。
    env_id = str(body.get("environment") or "").strip()
    env = environment_store.resolve(_out(), domain, env_id)
    if env_id and env is None:
        return {"error": f"指定された環境が見つかりません: {env_id}"}, 400

    # ③ spec を書く（生成と同じ経路）。
    spec_path, _source = _write_spec(
        domain,
        target_doc,
        self_healing=bool(body.get("self_healing", True)),
        egress_gateway=True,
    )

    output_dir = _out() / domain / "qa_process"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 前回の進捗 NDJSON を消す。残すと、実行開始からレポーターが書き直すまでの
    # 数秒間、進捗 API が前回の完了状態を「今の進捗」として返してしまう。
    stale_progress = output_dir / "playwright_progress.ndjson"
    if stale_progress.is_file():
        try:
            stale_progress.unlink()
        except OSError:
            logger.warning("前回の進捗ファイルを削除できませんでした: %s", stale_progress)

    storage_state = environment_store.storage_state_path(_out(), domain, env)

    try:
        job = test_run_job.enqueue_test_run(
            domain=domain,
            kind="steps",
            spec_path=spec_path,
            output_dir=output_dir,
            output_root=_out(),
            environment=str((env or {}).get("env_id") or ""),
            per_test_timeout_sec=int(body.get("per_test_timeout_sec") or 30),
            retries=int(body.get("retries") if body.get("retries") is not None else 1),
            update_snapshots=bool(body.get("update_snapshots")),
            headed=bool(body.get("headed")),
            base_url=str((env or {}).get("base_url") or "") or None,
            storage_state=storage_state,
            # ローカル対象の許可は運用者の明示設定（WEBSPEC2DOC_ALLOW_LOCAL=1）にのみ従う
            egress_policy=EgressPolicy(allow_local=_local_targets_allowed()),
        )
    except test_run_job.DomainBusyError as exc:
        # どの実行とぶつかっているかを名指しで返す。「今は実行できません」だけでは
        # 待てばよいのか壊れたのか利用者が判断できない。
        return {"error": str(exc), "running_job_id": exc.job_id}, 409

    return {
        "job_id": job.job_id,
        "queued_position": test_run_job.queued_position(job.job_id),
        "spec_path": str(spec_path),
        "tests": len(tests),
        "environment": job.environment,
    }, 202
