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
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from web.services.healing import autorun_bridge, orchestrator, project_store
from web.services.healing.types import HealingProject, HealingRun

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


def _spec_path(out_dir: Path, domain: str) -> Path | None:
    """回すテストファイル。02 が作ったものを優先し、無ければ 03 のものを使う。"""
    for relative in (
        Path("testcases") / "testcases.spec.ts",
        Path("qa_process") / "autorun.spec.ts",
    ):
        candidate = out_dir / domain / relative
        if candidate.is_file():
            return candidate
    return None


def _has_active_run(out_dir: Path, project_id: str) -> bool:
    """まだ終わっていない実行があるか。二重に走らせない。

    判定そのものは orchestrator に置いてある。ここと指揮者アダプタに
    同じ判定を 2 つ持っていたため、「プロセスごと止まった実行の片付け」を
    足したときに片方だけ直る形になっていた。
    """
    return orchestrator.has_active_run(out_dir, project_id)


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


def run_now(out_dir: Path, project: HealingProject) -> HealingRun | None:
    """1 接続先ぶんの監視を今すぐ回す。失敗が無ければ None を返す。

    テストが全部通っていれば、報告書は作らない。出すものが無いのに
    報告書だけ増えると、承認待ちの一覧が意味を失う。
    """
    domain = str(getattr(project, "domain", "") or "")
    now = datetime.now()
    if not domain:
        logger.info("監視: サイトが未設定のため飛ばします (%s)", project.project_id)
        return None

    spec = _spec_path(out_dir, domain)
    if spec is None:
        logger.info("監視: 回せるテストがありません (%s / %s)", project.project_id, domain)
        _mark_ran(out_dir, project, now)
        return None

    if _has_active_run(out_dir, project.project_id):
        logger.info("監視: まだ終わっていない実行があるため飛ばします (%s)", project.project_id)
        return None

    # 実行結果は 03 と同じ場所へ置く。画面の「実行結果」からも同じものが見える。
    from web.services.playwright_executor import run_playwright

    output_dir = out_dir / domain / "qa_process"
    output_dir.mkdir(parents=True, exist_ok=True)
    run_playwright(spec_path=spec, output_dir=output_dir)

    defects = autorun_bridge.load_failures(out_dir, domain)
    _mark_ran(out_dir, project, now)
    if not defects:
        logger.info("監視: %s は全部通りました", domain)
        return None

    # 出どころを監視に付け替える。autorun_bridge は 02/03 の画面から
    # 押されたときと同じ Defect を作るので、そのままだと報告書の
    # 「事象」欄に「人が押した」と読める記録が残る。
    defects = [replace(d, source="monitor") for d in defects]

    logger.info("監視: %s", autorun_bridge.summarize_failures(defects))
    # 上の _has_active_run から時間が経っている（テストを 1 本走らせている）。
    # その間に画面や指揮者から実行が起きうるので、確認と開始が一体になった
    # start_run_if_idle で起こす。
    run = orchestrator.start_run_if_idle(
        out_dir=out_dir, project=project, actor="monitor", defects=defects
    )
    if run is None:
        logger.info(
            "監視: まだ終わっていない実行があるため飛ばします (%s)", project.project_id
        )
    return run
