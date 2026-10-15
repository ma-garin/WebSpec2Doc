"""System 08 段階 7 の前後処理。

- 実行前: 承認済みのテストコード（job.code.files）を案件の code/ に書き出す（runner と code.zip の元）
- 実行後: 段階 7 を生成済み（generated）にし、承認できるようにする（判定は段階 7 の承認後）
"""
from __future__ import annotations

import logging
from pathlib import Path

from . import codegen, dbconn, runner, stages, store

RUN_STAGE, REPORT_STAGE = 7, 8
_STALE_JUDGEMENT = "判定の後に新しい実行が終わりました。段階 7 を承認し直してから判定し直してください。"
_log = logging.getLogger(__name__)
_BUSY = "この案件のテストは実行中です。終わるのを待つか、止めてから実行してください。"


def _busy(job: dict) -> bool:
    """この案件の実行が、いまのプロセスで進行中か（再起動で残った記録は数えない）。"""
    for run in job.get("runs") or []:
        if run.get("status") not in runner.ACTIVE:
            continue
        try:
            if runner.status(str(run.get("id"))).get("status") in runner.ACTIVE:
                return True
        except KeyError:
            continue
    return False


def write_code(job: dict, dest: Path) -> int:
    """承認済みのテストコードを dest（案件の code/）に置く。実行中は置き換えない。"""
    if _busy(job):
        raise store.StoreError(_BUSY)
    return codegen.write_files(list((job.get("code") or {}).get("files") or []), dest)


def finish_stage(job: dict, run_status: str, actor: str) -> dict:
    """実行が終わったら段階 7 を生成済みにする。段階 7 を更新できなくても実行の記録は残す。"""
    if run_status in runner.ACTIVE:
        return job
    try:  # 承認済みでも新しい実行の結果で置き換え、段階 7 の承認を外す（段階 8 は stale になる。N4）
        new_job = stages.put_generated(job, RUN_STAGE, {"runs": list(job.get("runs") or [])}, actor, reopen=True)
    except store.StoreError as exc:
        _log.warning("段階 7 を生成済みにできません %s: %s", job.get("id"), exc)
        return job
    judgement = new_job.get("judgement")
    if isinstance(judgement, dict) and not judgement.get("stale"):
        new_job = {**new_job, "judgement": {**judgement, "stale": True, "stale_reason": _STALE_JUDGEMENT}}
    return new_job


def report_stale(job: dict) -> bool:
    """段階 8 が前段（新しい実行）の変更で stale か。stale なら判定のやり直しで承認を外して置き換える。"""
    return bool(((job.get("stages") or {}).get(str(REPORT_STAGE)) or {}).get("stale"))


def member_error(job: dict, actor: str, what: str = "実行") -> str | None:
    """実行・停止・判定はこの案件のメンバー（qa 以上）だけ。members が無い旧案件は確かめない（N6）。"""
    members = job.get("members") or {}
    if not members:
        return None
    role = members.get(actor) if isinstance(members, dict) else ("qa" if actor in members else None)
    if stages.ROLE_RANK.get(str(role or ""), 0) < stages.ROLE_RANK["qa"]:
        return f"この案件のメンバーではないため{what}できません。管理者にメンバー追加を依頼してください。"
    return None


def secret_of(data: dict) -> str:
    """実行時に入力された接続のパスワード（メモリ内のみ。保存しない）。"""
    return str(data.get("secret") or data.get("password") or "")


def preflight(env: dict, plan: dict, secret: str) -> str | None:
    """実行前の接続確認（N5）。到達不能・認証失敗・対象テーブルの権限不足なら理由と次の行動を返す。"""
    if plan.get("writes") and plan.get("read_only") and not plan.get("production"):
        return ("この接続先は書き込み不可に設定されています。データ投入やジョブ起動を含むケースは、"
                "書き込みできる接続先を選んで実行してください。")
    return dbconn.preflight(env, secret or None, list(plan.get("affected_tables") or []), bool(plan.get("writes")))


def cancel_note(rid: str, data: dict) -> str:
    """停止の監査に残す内容（実行 ID と、入力されていれば理由。N11）。"""
    reason = " ".join(str(data.get("reason") or "").split())[:200]
    return f"{rid} 理由={reason}" if reason else rid
