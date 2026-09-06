"""毎日きまった時刻に 02 のテストを回し、落ちていたら報告書を下書きする。

ここが「壊れたら直る」を成立させる最後の一片。

人がテストを回すまで、壊れていることは誰も知らない。知ったときには
原因が増えているし、その日の予定も崩れる。保守の実務で高くつくのは
修正そのものではなく、いつ壊れたか分からないまま調べる時間である。

だから人を待たずに回し、落ちていたら報告書の下書きまで進めておく。
人がやるのは「出してよいか」の判断だけになる。

流儀は web/services/scheduler.py に合わせた（daemon スレッド・60 秒間隔・
threading.Event で止める）。別方式を持ち込むと、止め方が 2 通りになる。
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path

from web.services.healing import project_store
from web.services.healing.types import HealingProject
from web.services.orchestration import conductor
from web.services.orchestration.run_store import ConductorRun

logger = logging.getLogger(__name__)

#: 見に行く間隔。scheduler.py と同じ。
MONITOR_POLL_INTERVAL = 60

_stop_event = threading.Event()
_started_lock = threading.Lock()
_monitor_started = False


# ─────────────────────────────────────────────────────────────────────────
# デーモン
# ─────────────────────────────────────────────────────────────────────────


def start_monitor(output_root: Path) -> None:
    """アプリ起動時に一度だけデーモンスレッドを起動する。"""
    global _monitor_started
    with _started_lock:
        if _monitor_started:
            return
        _monitor_started = True
    _stop_event.clear()
    thread = threading.Thread(
        target=_loop,
        args=(Path(output_root),),
        daemon=True,
        name="WebSpec2Doc-HealingMonitor",
    )
    thread.start()
    logger.info(
        "ヒーリング監視デーモンを起動しました (poll_interval=%ds)", MONITOR_POLL_INTERVAL
    )


def stop_monitor() -> None:
    """テスト・シャットダウン用。"""
    global _monitor_started
    _stop_event.set()
    with _started_lock:
        _monitor_started = False


def _loop(output_root: Path) -> None:
    while not _stop_event.is_set():
        try:
            _tick(output_root)
        except Exception:  # noqa: BLE001 - 1 回の失敗でデーモンを止めない
            logger.warning("ヒーリング監視の巡回に失敗しました", exc_info=True)
        _stop_event.wait(MONITOR_POLL_INTERVAL)


def _out_dirs(output_root: Path) -> list[Path]:
    """接続先を持ちうる出力ディレクトリ。テナント有効時は各テナント配下。"""
    dirs = [output_root]
    tenants = output_root / "tenants"
    if tenants.is_dir():
        dirs.extend(p for p in sorted(tenants.iterdir()) if p.is_dir())
    return dirs


def _tick(output_root: Path) -> None:
    for out_dir in _out_dirs(output_root):
        try:
            projects = project_store.list_projects(out_dir)
        except Exception:  # noqa: BLE001 - 1 テナントの失敗で他を止めない
            logger.warning("接続先の読み込みに失敗しました: %s", out_dir, exc_info=True)
            continue
        for project in projects:
            if not is_due(project):
                continue
            try:
                run_now(out_dir, project)
            except Exception:  # noqa: BLE001 - 1 件の失敗で他を止めない
                logger.warning(
                    "監視実行に失敗しました: %s", project.project_id, exc_info=True
                )


# ─────────────────────────────────────────────────────────────────────────
# 判定と実行
# ─────────────────────────────────────────────────────────────────────────


def is_due(project: HealingProject, *, now: datetime | None = None) -> bool:
    """今この接続先を回すべきか。

    「その日の指定時刻を過ぎていて、その日はまだ回していない」ときだけ。
    アプリが落ちていて時刻を跨いだ場合も、起動後の最初の巡回で回る。
    """
    if not getattr(project, "monitor_enabled", False):
        return False
    monitor_time = str(getattr(project, "monitor_time", "") or "")
    if not monitor_time:
        return False
    current = now or datetime.now()
    if current.strftime("%H:%M") < monitor_time:
        return False
    return str(getattr(project, "monitor_last_run_on", "") or "") != current.strftime(
        "%Y-%m-%d"
    )


def _mark_ran(out_dir: Path, project: HealingProject, now: datetime) -> None:
    """その日は回した、と記録する。失敗しても実行そのものは成立している。"""
    try:
        project_store.update_project(
            out_dir,
            project.project_id,
            {"monitor_last_run_on": now.strftime("%Y-%m-%d")},
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "監視の実行日を記録できませんでした: %s", project.project_id, exc_info=True
        )


def run_now(out_dir: Path, project: HealingProject) -> ConductorRun | None:
    """1 接続先ぶんの監視を今すぐ起こす。指揮が始まらなければ None を返す。

    テストを回すのも、落ちた分から報告書を下書きするのも指揮者の段が行う。
    ここが自分で Playwright を回していた頃は同じ手順が 2 か所にあり、
    片方だけ直る形になっていた（起こす側は「起こす」だけを持つ）。

    その日は回した、という記録は指揮を起こせたときだけ付ける。起こせなかった
    日に記録すると、翌日まで監視が動かない。
    """
    domain = str(getattr(project, "domain", "") or "")
    now = datetime.now()
    if not domain:
        logger.info("監視: サイトが未設定のため飛ばします (%s)", project.project_id)
        return None

    # 確認と開始が一体になった関数で起こす。監視・画面・API は別スレッドから
    # 呼ぶので、確認と開始が分かれていると同じサイトの指揮が二重に立つ。
    run = conductor.start_if_idle(
        out_dir=out_dir,
        domain=domain,
        goal="daily",
        project_id=project.project_id,
        actor="monitor",
    )
    if run is None:
        logger.info(
            "監視: まだ終わっていない実行があるため飛ばします (%s)", project.project_id
        )
        return None

    _mark_ran(out_dir, project, now)
    logger.info("監視: %s の指揮を始めました (%s)", domain, run.run_id)
    return run
