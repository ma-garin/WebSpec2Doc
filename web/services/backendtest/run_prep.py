"""System 08 段階 7 の前後処理。

- 実行前: 承認済みのテストコード（job.code.files）を案件の code/ に書き出す（runner と code.zip の元）
- 実行後: 段階 7 を生成済み（generated）にし、承認できるようにする（判定は段階 7 の承認後）
"""
from __future__ import annotations

import logging
from pathlib import Path

from . import codegen, runner, stages, store

RUN_STAGE = 7
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
    try:
        return stages.put_generated(job, RUN_STAGE, {"runs": list(job.get("runs") or [])}, actor)
    except store.StoreError as exc:
        _log.warning("段階 7 を生成済みにできません %s: %s", job.get("id"), exc)
        return job
