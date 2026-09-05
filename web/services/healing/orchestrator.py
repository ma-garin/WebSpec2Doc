"""オートヒーリング（System 05）のループエンジン。

AutoRun（web/services/auto_run_job.py）と同じ方式を踏襲する:
「グローバル dict + Lock + daemon スレッド + ログ追記」で状態を持ち、
画面はポーリングでこれを読む。リクエストコンテキストはスレッドから見えないため、
out_dir は常に引数で持ち回る。

依存モジュール（project_store / run_store / git_ops / github_client /
verification / agents）は並行実装中で、import は通っても呼び出し時に
例外や属性欠落が起きる可能性がある。そのため _run_loop 全体を
try/except で包み、失敗しても run.status="failed" として必ず保存する
（「動いているはずのループが黙って消える」事態を避けるため）。
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from web.services.healing import agents as healing_agents
from web.services.healing import report as healing_report
from web.services.healing import report_doc
from web.services.healing import (
    git_ops,
    github_client,
    localization,
    project_store,
    risk,
    run_store,
    verification,
)
from web.services.healing.types import (
    AgentTask,
    Defect,
    FixProposal,
    HealingError,
    HealingIteration,
    HealingProject,
    HealingRun,
    PullRequestRef,
    TERMINAL_RUN_STATUSES,
    VerifyResult,
)

#: record_decision が受け付ける操作。これ以外は HealingError にする。
logger = logging.getLogger(__name__)

DECISION_ACTIONS = ("approve", "reject", "rerun", "merge")

#: バックグラウンドのループがまだ動いている状態。ここに居る run に対して
#: 人の操作（再検証・マージ）を許すと、ループと同じ worktree を同時に触ることになる。
ACTIVE_STATUSES = frozenset(
    {"queued", "preparing", "verifying", "analyzing", "fixing", "reverifying"}
)

#: worktree とブランチを残しておく実行の数（プロジェクトごと）。
#: 人が差分を見に来るため直近は残すが、無制限に増やさない。
KEEP_RUN_ARTIFACTS = 5

# ─────────────────────────── 実行中の状態 ───────────────────────────

#: 実行中・実行直後の Run。サーバ再起動で消えるため、get_run は
#: メモリに無ければ run_store（永続化）へフォールバックする。
_RUNS: dict[str, HealingRun] = {}
_RUNS_LOCK = threading.RLock()

#: cancel_run が入れる集合。ループは各段階の頭でここを見て自発的に止まる。
#: 実行中のサブプロセス（検証コマンド・エージェント CLI）を強制終了する
#: 仕組みは持たない。timeout はエージェント側・verification 側に委ねる。
_CANCEL: set[str] = set()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _add_log(run: HealingRun, message: str) -> None:
    run.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
    if len(run.log) > 500:
        del run.log[: len(run.log) - 500]


def _update(out_dir: Path, run: HealingRun, *, status: str | None = None, step_label: str = "", note: str = "") -> None:
    """状態遷移を 1 か所に集約する。

    画面はポーリングでしか進捗を知れないため、保存しない進捗は
    存在しないのと同じ。ここを通した遷移は必ず save_run するまでが 1 セット。
    """
    with _RUNS_LOCK:
        if run.status == "cancelled" and status not in (None, "cancelled"):
            # 中止は人が下した最終決定。バックグラウンドのループがまだ走っていて
            # あとから succeeded / failed を書き込むと、中止が黙って無かったことになる。
            # 中止から他の状態へは戻さない（ログにだけ痕跡を残す）。
            _add_log(run, f"中止済みのため状態変更を無視しました: {status}")
            _RUNS[run.run_id] = run
            run_store.save_run(out_dir, run)
            return
        if status is not None:
            run.status = status
        if step_label:
            run.step_label = step_label
        message = note or step_label
        if message:
            _add_log(run, message)
        if status in TERMINAL_RUN_STATUSES:
            run.finished_at = run.finished_at or _now_iso()
        _RUNS[run.run_id] = run
    run_store.save_run(out_dir, run)


def _cancelled(run_id: str) -> bool:
    with _RUNS_LOCK:
        return run_id in _CANCEL


# ─────────────────────────── 公開 API ───────────────────────────


def start_run(
    *,
    out_dir: Path,
    project: HealingProject,
    actor: str = "",
    extra_instructions: str = "",
    defects: Sequence[Defect] | None = None,
) -> HealingRun:
    """ヒーリングを 1 本起こす。

    defects を渡すと、検証コマンドの失敗から欠陥を切り出す代わりにそれを使う。
    E2E（02/03）の失敗や、差し戻しで同じ欠陥を直させる経路がこれを通る。
    渡した場合も検証は実行する（修正前後の比較に要るため）。
    """
    run_id = f"heal-{uuid.uuid4().hex[:12]}"
    run = HealingRun(
        run_id=run_id,
        project_id=project.project_id,
        project_name=project.name,
        status="queued",
        step_label="受付",
        base_branch=project.default_branch,
        started_at=_now_iso(),
    )
    _add_log(run, f"受付しました（actor={actor or '不明'}）")
    with _RUNS_LOCK:
        _RUNS[run_id] = run
    run_store.save_run(out_dir, run)

    # 古い実行の作業ツリーとブランチを片付ける。実行のたびに増え続けるものなので、
    # 「増やした側」が減らす責任を持つ。片付けに失敗しても新しい実行は止めない。
    try:
        _cleanup_old_run_artifacts(out_dir, project)
    except Exception:  # noqa: BLE001 - 後片付けの失敗で実行を止めない
        logger.warning("古い実行の後片付けに失敗しました", exc_info=True)

    thread = threading.Thread(
        target=_run_loop,
        args=(out_dir, run, project, extra_instructions, list(defects or [])),
        name=f"healing-{run_id}",
        daemon=True,
    )
    thread.start()
    return run


def _cleanup_old_run_artifacts(out_dir: Path, project: HealingProject) -> None:
    """直近 KEEP_RUN_ARTIFACTS 件より古い実行の worktree と統合ブランチを消す。

    差分は人が後から見に来るので直近は残す。ただし残し続けると、
    実行のたびに worktree（ディスク）とブランチ（対象リポジトリ）が積もる。

    統合ブランチを消すのは **PR を出していない実行だけ**にする。PR を出した実行の
    ブランチを消すと GitHub 側の PR が壊れる。判断が付かないものは残す（安全側）。
    """
    import shutil

    repo = Path(project.repo_path)
    runs = run_store.list_runs(out_dir, project.project_id, limit=200)
    stale = [r for r in runs[KEEP_RUN_ARTIFACTS:] if r.status not in ACTIVE_STATUSES]
    if not stale:
        return

    root = project_store.worktree_root()
    removed = 0
    for old in stale:
        workdir = root / old.run_id
        if workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)
            removed += 1
        # 競合などでマージできなかった欠陥ブランチは、その場では消せない
        # （未マージのものを消さないのが安全側の判断）。ただし実行が古くなれば
        # 中身は統合ブランチにも PR にも入っておらず、残しても使い道がない。
        # 実行 ID を接頭辞に持つブランチはその実行専用なので、ここでまとめて消す。
        for leftover in git_ops.list_branches(repo, prefix=f"healing/{old.run_id}-"):
            git_ops.delete_branch(repo, leftover)

        # PR を出していて、まだ open のものは統合ブランチを残す（消すと PR が壊れる）。
        pr = old.pull_request
        if pr is not None and pr.state not in ("merged", "closed"):
            continue
        if old.branch:
            git_ops.delete_branch(repo, old.branch)
    git_ops.prune_worktrees(repo)
    if removed:
        logger.info("古い実行の作業ツリーを %d 件片付けました", removed)


def get_run(out_dir: Path, run_id: str) -> HealingRun | None:
    with _RUNS_LOCK:
        run = _RUNS.get(run_id)
    if run is not None:
        return run
    return run_store.load_run(out_dir, run_id)


def list_run_summaries(out_dir: Path, project_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
    stored = run_store.list_runs(out_dir, project_id=project_id, limit=limit)
    with _RUNS_LOCK:
        merged: dict[str, HealingRun] = {run.run_id: run for run in stored}
        for run_id, run in _RUNS.items():
            if project_id and run.project_id != project_id:
                continue
            merged[run_id] = run  # メモリ側が最新なので永続化分を上書きする
    ordered = sorted(merged.values(), key=lambda r: r.started_at or "", reverse=True)[:limit]
    return [run_store.run_summary(run) for run in ordered]


def cancel_run(run_id: str) -> bool:
    with _RUNS_LOCK:
        if run_id not in _RUNS:
            return False
        _CANCEL.add(run_id)
    return True


def record_decision(out_dir: Path, run_id: str, *, action: str, note: str = "", actor: str = "") -> HealingRun:
    if action not in DECISION_ACTIONS:
        raise HealingError(f"不正な操作です: {action}")

    run = get_run(out_dir, run_id)
    if run is None:
        raise HealingError(f"実行 {run_id} が見つかりません")

    with _RUNS_LOCK:
        run.decisions.append({"action": action, "note": note, "actor": actor, "at": _now_iso()})
        _RUNS[run.run_id] = run

    if action == "approve":
        # マージは別操作。ここでは状態を変えず、承認の事実だけ記録する。
        _add_log(run, f"{actor or '人'} が承認しました" + (f"（{note}）" if note else ""))
        run_store.save_run(out_dir, run)
        return run

    if action == "reject":
        # 走っている最中の却下は、まずループへ中止を伝える。これをしないと
        # ループが次の段階へ進んで状態を上書きし、却下が無かったことになる。
        if run.status in ACTIVE_STATUSES:
            cancel_run(run_id)
        _update(out_dir, run, status="cancelled", note=f"{actor or '人'} が却下しました" + (f"（{note}）" if note else ""))
        return run

    if action == "rerun":
        return rerun_verification(out_dir, run_id)

    # action == "merge"
    if run.status in ACTIVE_STATUSES:
        raise HealingError("実行中はマージできません。終わるまで待つか、中止してください")
    project = project_store.get_project(out_dir, run.project_id)
    if project is None:
        raise HealingError(f"プロジェクト {run.project_id} が見つかりません")
    if run.pull_request is None:
        raise HealingError("PR がまだ作成されていません")

    cfg = github_client.github_config_from_env(project.github_repo)
    pr_ref: PullRequestRef = github_client.merge_pull_request(
        cfg, repo_path=Path(project.repo_path), number=run.pull_request.number
    )
    with _RUNS_LOCK:
        run.pull_request = pr_ref
        _RUNS[run.run_id] = run
    _update(
        out_dir,
        run,
        status="succeeded",
        note=f"{actor or '人'} が PR #{pr_ref.number} をマージしました",
    )
    return run


def rerun_verification(out_dir: Path, run_id: str) -> HealingRun:
    run = get_run(out_dir, run_id)
    if run is None:
        raise HealingError(f"実行 {run_id} が見つかりません")
    project = project_store.get_project(out_dir, run.project_id)
    if project is None:
        raise HealingError(f"プロジェクト {run.project_id} が見つかりません")
    if not run.branch:
        raise HealingError("統合ブランチが未作成のため再検証できません")
    if run.status in ACTIVE_STATUSES:
        # ループ自身が同じ worktree で検証コマンドを走らせている最中に、
        # 手動の再検証を重ねると同じディレクトリで 2 本のテストが同時に動く。
        raise HealingError("実行中は再検証できません。終わるまで待つか、中止してください")

    integration_dir = (project_store.worktree_root() / run.run_id / "integration").resolve()
    if not integration_dir.exists():
        raise HealingError("統合 worktree が見つかりません（後片付け済みの可能性があります）")

    index = len(run.iterations) + 1
    iteration = HealingIteration(index=index, started_at=_now_iso())
    with _RUNS_LOCK:
        run.iterations.append(iteration)

    _update(out_dir, run, status="verifying", step_label=f"再検証（{index} 周目・手動）")
    verify_result = verification.run_verification(
        repo=integration_dir, command=project.verify_command, timeout_sec=project.verify_timeout_sec
    )
    iteration.verify_before = verify_result
    iteration.verify_after = verify_result
    iteration.finished_at = _now_iso()

    if verify_result.ok:
        _update(out_dir, run, status="succeeded", step_label="再検証で緑になりました")
    else:
        run.unverified.append(f"{index} 周目（手動再検証）: 依然として検証が失敗しています")
        _update(out_dir, run, status="awaiting_human", step_label="人の判断待ち（再検証も失敗）")

    return run


def create_pull_request_for_run(out_dir: Path, run_id: str, *, draft: bool = False) -> HealingRun:
    run = get_run(out_dir, run_id)
    if run is None:
        raise HealingError(f"実行 {run_id} が見つかりません")
    if run.pull_request is not None:
        return run  # 既に PR がある run は作り直さず既存を返す

    project = project_store.get_project(out_dir, run.project_id)
    if project is None:
        raise HealingError(f"プロジェクト {run.project_id} が見つかりません")
    if not run.branch:
        raise HealingError("統合ブランチが未作成のため PR を作成できません")

    repo = Path(project.repo_path)
    github_repo = project.github_repo or git_ops.github_repo_from_remote(git_ops.remote_url(repo, project.remote))
    if not github_repo:
        raise HealingError("GitHub リポジトリが特定できません（project.github_repo または remote の設定を確認してください）")

    push_result = git_ops.push_branch(repo, run.branch, project.remote)
    if not push_result.ok:
        raise HealingError(f"ブランチの push に失敗しました: {push_result.stderr}")

    defects: list[Defect] = []
    proposals: list[FixProposal] = []
    verify_before: VerifyResult | None = None
    verify_after: VerifyResult | None = None
    for iteration in run.iterations:
        defects.extend(iteration.defects)
        proposals.extend(iteration.proposals)
        if verify_before is None:
            verify_before = iteration.verify_before
        verify_after = iteration.verify_after or verify_after

    cfg = github_client.github_config_from_env(github_repo)
    body = github_client.build_pr_body(
        run_id=run.run_id,
        project_name=project.name,
        defects=defects,
        proposals=proposals,
        verify_before=verify_before,
        verify_after=verify_after,
    )
    # 修正 1 件ごとの Markdown レポートを本文末尾に足す（github_client 側は触らない）。
    body = _append_reports(body, proposals)
    pr_ref: PullRequestRef = github_client.create_pull_request(
        cfg,
        repo_path=repo,
        head=run.branch,
        base=project.default_branch,
        title=f"[healing] {project.name}: {run.run_id}",
        body=body,
        draft=draft,
    )

    with _RUNS_LOCK:
        run.pull_request = pr_ref
        _RUNS[run.run_id] = run
    _add_log(run, f"PR #{pr_ref.number} を作成しました: {pr_ref.url}")
    run_store.save_run(out_dir, run)
    return run


# ─────────────────────────── ループ本体 ───────────────────────────


def _run_loop(
    out_dir: Path,
    run: HealingRun,
    project: HealingProject,
    extra_instructions: str,
    given_defects: list[Defect] | None = None,
) -> None:
    try:
        _run_loop_inner(out_dir, run, project, extra_instructions, given_defects or [])
    except Exception as exc:  # noqa: BLE001 - 依存モジュールの想定外の失敗でループ全体を落とさない最終防波堤
        run.status = "failed"
        run.error = f"想定外のエラーで停止しました: {exc}"
        _add_log(run, run.error)
        run.finished_at = _now_iso()
        with _RUNS_LOCK:
            _RUNS[run.run_id] = run
        try:
            run_store.save_run(out_dir, run)
        except Exception:  # noqa: BLE001 - 保存自体が失敗してもプロセスは落とさない
            pass
    finally:
        # 報告書はどの終わり方でも作る。直せなかった実行にも「事象と原因」の
        # 報告書は要る（対応欄だけを人が埋めて顧客に出す）。
        # ここは全ての return と例外を通るので、個別の遷移に挿し込むより漏れない。
        try:
            _write_reports(out_dir, run, project)
            run_store.save_run(out_dir, run)
        except Exception:  # noqa: BLE001 - 報告書の失敗で実行の記録を壊さない
            logger.warning("報告書の保存に失敗しました", exc_info=True)
        with _RUNS_LOCK:
            _CANCEL.discard(run.run_id)


def _run_loop_inner(
    out_dir: Path,
    run: HealingRun,
    project: HealingProject,
    extra_instructions: str,
    given_defects: list[Defect] | None = None,
) -> None:
    repo = Path(project.repo_path)

    # --- preparing ---
    _update(out_dir, run, status="preparing", step_label="準備")

    allowed, reason = verification.is_command_allowed(project.verify_command)
    if not allowed:
        run.error = f"検証コマンドが許可されていません: {reason}"
        _update(out_dir, run, status="failed", step_label="失敗")
        return

    if not git_ops.is_git_repo(repo):
        run.error = "対象パスは git リポジトリではありません"
        _update(out_dir, run, status="failed", step_label="失敗")
        return

    # 利用者の手元の状態を確認する。ただし**止めない**。
    #
    # ヒーリングは全ての作業を分離した worktree の中で行い、利用者の作業ツリーには
    # 一切触れない。またブランチは常にコミット済みの base から切るため、手元の
    # 未コミット変更は「壊れる」のではなく「検証対象に入らない」。
    # ここで中止にすると、__pycache__ のような生成物が 1 つあるだけで
    # 実行できなくなり、実運用ではほぼ毎回止まる（実測で確認）。
    # 正しい扱いは「入らない事実を証跡に残して進む」。不在を証明しない方針と同じ。
    #
    # 未追跡ファイル（生成物・新規ファイル）は検証結果に影響しないので数えない。
    status_result = git_ops.run_git(repo, ["status", "--porcelain", "--untracked-files=no"])
    if not status_result.ok:
        run.error = f"git status の取得に失敗しました: {status_result.stderr}"
        _update(out_dir, run, status="failed", step_label="失敗")
        return
    dirty = [line for line in status_result.stdout.splitlines() if line.strip()]
    if dirty:
        names = ", ".join(line[3:] for line in dirty[:5])
        more = f" ほか {len(dirty) - 5} 件" if len(dirty) > 5 else ""
        run.unverified.append(
            f"手元の未コミット変更（{names}{more}）は検証に含まれていません。"
            f"ヒーリングは {project.default_branch} のコミット済みの状態から始めます。"
        )
        _add_log(run, f"手元の未コミット変更 {len(dirty)} 件は検証対象に入りません")

    if _cancelled(run.run_id):
        _update(out_dir, run, status="cancelled", step_label="中止")
        return

    branch = git_ops.safe_branch_name(f"healing/{run.run_id}")
    branch_result = git_ops.create_branch(repo, branch, project.default_branch)
    if not branch_result.ok:
        run.error = f"統合ブランチの作成に失敗しました: {branch_result.stderr}"
        _update(out_dir, run, status="failed", step_label="失敗")
        return
    with _RUNS_LOCK:
        run.branch = branch
    _add_log(run, f"統合ブランチ {branch} を作成しました（base={project.default_branch} には一切コミットしない）")

    # 以降の検証・マージは全てこの worktree の中で行う。元の作業ツリーは触らない。
    # 以降この Path は検証コマンドの cwd にもなる。相対のままだと、サーバの
    # カレントディレクトリ次第で「存在しないディレクトリ」を指す。
    integration_dir = (
        project_store.worktree_root() / run.run_id / "integration"
    ).resolve()
    wt_result = git_ops.create_worktree(repo, branch, project.default_branch, integration_dir)
    if not wt_result.ok:
        run.error = f"統合用 worktree の作成に失敗しました: {wt_result.stderr}"
        _update(out_dir, run, status="failed", step_label="失敗")
        return

    applied_any = False
    previous_iteration: HealingIteration | None = None

    for i in range(1, project.max_iterations + 1):
        if _cancelled(run.run_id):
            _update(out_dir, run, status="cancelled", step_label="中止")
            return

        iteration = HealingIteration(index=i, started_at=_now_iso())
        with _RUNS_LOCK:
            run.iterations.append(iteration)

        # verifying / reverifying: この周回冒頭の verify が、前周の修正の再検証を兼ねる。
        verify_status = "verifying" if i == 1 else "reverifying"
        _update(out_dir, run, status=verify_status, step_label=f"検証（{i} 周目）")
        verify_result = verification.run_verification(
            repo=integration_dir, command=project.verify_command, timeout_sec=project.verify_timeout_sec
        )
        iteration.verify_before = verify_result
        if previous_iteration is not None:
            previous_iteration.verify_after = verify_result

        # 中止の確認は「結果を採用する前」に置く。緑判定の後ろに置くと、
        # 検証中に中止しても、たまたま緑だったときだけ中止が無視される。
        if _cancelled(run.run_id):
            _update(out_dir, run, status="cancelled", step_label="中止")
            return

        if verify_result.ok:
            iteration.verify_after = verify_result
            iteration.finished_at = _now_iso()
            run.status = "no_defects" if i == 1 else "succeeded"
            _update(out_dir, run, status=run.status, step_label="検証が緑になりました")
            break

        # analyzing
        _update(out_dir, run, status="analyzing", step_label=f"欠陥の切り出し（{i} 周目）")
        if given_defects and i == 1:
            # 外から渡された欠陥（E2E の失敗・差し戻し）を使う。
            # 検証は「修正前の状態」を記録するために実行しており、
            # そこから欠陥を切り出し直すと画面 ID やスクリーンショットが失われる。
            defects = list(given_defects)
            _add_log(run, f"外部から {len(defects)} 件の欠陥を受け取りました")
        else:
            defects = verification.failures_to_defects(
                verify_result.failures, repo=integration_dir, source="verify"
            )
        # 「どこが怪しいか」をここで確定させ、以降の修正指示と PR レポートに載せる。
        defects = _localize_defects(run, defects, repo=repo)
        iteration.defects = list(defects)
        if not defects:
            # 「不在の証明」はしない: 原因を特定できなかった事実だけを記録して止まる。
            # 画面に出る文言なので「構造化」のような内部用語を使わない（2026-09-05）。
            run.unverified.append(
                f"{i} 周目: 検証は失敗しましたが、どのテストが原因かを特定できませんでした"
            )
            iteration.finished_at = _now_iso()
            run.error = (
                "検証は失敗しましたが、原因となるテストを特定できませんでした。"
                "検証コマンドの出力を実行ログで確認してください"
            )
            _update(out_dir, run, status="failed", step_label="失敗")
            return
        _add_log(run, f"{len(defects)} 件の欠陥を検出しました")

        if _cancelled(run.run_id):
            _update(out_dir, run, status="cancelled", step_label="中止")
            return

        # fixing
        _update(out_dir, run, status="fixing", step_label=f"修正（{i} 周目・{len(defects)} 件）")
        proposals = _fix_defects(out_dir, run, project, integration_dir, branch, i, defects, extra_instructions)
        iteration.proposals = list(proposals)
        iteration.finished_at = _now_iso()

        applied = [p for p in proposals if p.status == "applied"]
        if not applied:
            # 「1 件も適用できませんでした」だけでは、エージェントが修正不要と判断した（skipped）のか、
            # 落ちた（failed）のか、時間切れ（timeout）なのかが失われる。内訳を残す。
            counts: dict[str, int] = {}
            for proposal in proposals:
                counts[proposal.status] = counts.get(proposal.status, 0) + 1
            labels = {
                "skipped": "変更なし",
                "failed": "失敗",
                "timeout": "時間切れ",
                "proposed": "提案のみ（未適用）",
            }
            breakdown = "・".join(
                f"{labels.get(key, key)} {value} 件" for key, value in sorted(counts.items())
            )
            reasons = [p.error for p in proposals if p.error]
            run.error = f"修正が 1 件も適用されませんでした（{breakdown}）"
            if reasons:
                run.error += "。理由: " + " / ".join(dict.fromkeys(reasons))
            _update(out_dir, run, status="failed", step_label="失敗")
            return

        applied_any = True
        _add_log(run, f"{len(applied)} 件の修正を統合ブランチへ反映しました")
        previous_iteration = iteration
    else:
        # for-else: break せずにループを終えた = 上限に達した。
        #
        # ここで必ずもう 1 回検証する。ループは「検証 → 修正」の順なので、
        # 最終周回の修正のあとには検証が入らない。これを省くと、実際には
        # 緑になっていても「緑になっていません」と報告することになる
        # （実測: 欠陥 4 件のうち最後の 1 件を直した直後に打ち切り、
        #  統合ブランチは 4 passed だったのに失敗として報告していた）。
        # 成功を失敗として報告するのは、失敗を見逃すのと同じくらい悪い。
        final_result = None
        if applied_any and not _cancelled(run.run_id):
            _update(out_dir, run, status="reverifying", step_label="最終確認の検証")
            final_result = verification.run_verification(
                repo=integration_dir,
                command=project.verify_command,
                timeout_sec=project.verify_timeout_sec,
            )
            if previous_iteration is not None:
                previous_iteration.verify_after = final_result
                previous_iteration.finished_at = _now_iso()

        if _cancelled(run.run_id):
            _update(out_dir, run, status="cancelled", step_label="中止")
            return

        if final_result is not None and final_result.ok:
            run.status = "succeeded"
            _update(out_dir, run, status="succeeded", step_label="検証が緑になりました")
        else:
            run.unverified.append(
                f"検証は緑になっていません。{project.max_iterations} 周で打ち切りました"
            )
            _update(out_dir, run, status="awaiting_human", step_label="人の判断待ち（上限到達）")

    # PR は自動で出さない。適用済みの修正がある成功時は、人の判断待ちで止める。
    if run.status == "succeeded" and applied_any:
        _update(out_dir, run, status="awaiting_human", step_label="人の判断待ち（修正あり・PR未作成）")


def _fix_defects(
    out_dir: Path,
    run: HealingRun,
    project: HealingProject,
    integration_dir: Path,
    integration_branch: str,
    iteration_index: int,
    defects: list[Defect],
    extra_instructions: str,
) -> list[FixProposal]:
    """欠陥ごとに worktree を切り、エージェントを並列実行して統合ブランチへマージする。

    1 本のエージェント失敗・タイムアウト・マージ競合が全体を落とさないよう、
    each 単位で例外を握りつぶして FixProposal(status=failed/timeout) に変換する。
    """
    repo = Path(project.repo_path)
    agent = healing_agents.get_agent(project.agent)

    plan: dict[str, tuple[Defect, Path, str]] = {}
    for defect in defects:
        # 統合ブランチは `healing/<run_id>`。その配下に `healing/<run_id>/i1/<id>` を作ると、
        # git の ref は .git/refs/heads/ 下の実ファイルなので「同名のファイルとディレクトリ」に
        # なり、必ず作成に失敗する。入れ子にせず、区切りをハイフンにして並列に置く。
        branch = git_ops.safe_branch_name(
            f"healing/{run.run_id}-i{iteration_index}-{defect.defect_id}"
        )
        workdir = (
            project_store.worktree_root() / run.run_id / f"i{iteration_index}-{defect.defect_id}"
        ).resolve()
        plan[defect.defect_id] = (defect, workdir, branch)

    results: dict[str, FixProposal] = {}
    timeout_sec = project.agent_timeout_sec + 60

    with ThreadPoolExecutor(max_workers=max(1, project.max_parallel_agents)) as pool:
        futures: dict[Any, str] = {}
        for defect_id, (defect, workdir, branch) in plan.items():
            wt_result = git_ops.create_worktree(repo, branch, integration_branch, workdir)
            if not wt_result.ok:
                results[defect_id] = FixProposal(
                    defect_id=defect_id,
                    agent=project.agent,
                    status="failed",
                    error=f"worktree の作成に失敗しました: {wt_result.stderr}",
                )
                continue
            task = AgentTask(
                defect=defect,
                workdir=str(workdir),
                repo_root=str(repo),
                verify_command=project.verify_command,
                timeout_sec=project.agent_timeout_sec,
                extra_instructions=_instructions_with_locations(extra_instructions, defect),
            )
            futures[pool.submit(agent.propose_fix, task)] = defect_id

        for future, defect_id in futures.items():
            try:
                results[defect_id] = future.result(timeout=timeout_sec)
            except FuturesTimeoutError:
                results[defect_id] = FixProposal(
                    defect_id=defect_id, agent=project.agent, status="timeout", error="エージェントの応答が時間内に終わりませんでした"
                )
            except Exception as exc:  # noqa: BLE001 - 1 本の失敗で全体を落とさない
                results[defect_id] = FixProposal(
                    defect_id=defect_id, agent=project.agent, status="failed", error=f"エージェント実行中に例外が発生しました: {exc}"
                )

    ordered: list[FixProposal] = []
    for defect_id, (defect, workdir, branch) in plan.items():
        proposal = results.get(defect_id) or FixProposal(
            defect_id=defect_id, agent=project.agent, status="failed", error="修正結果を取得できませんでした"
        )

        if proposal.status == "applied":
            commit_result = git_ops.commit_all(workdir, f"fix: {defect.title}")
            if not commit_result.ok:
                proposal = _replace_status(proposal, status="failed", error=f"コミットに失敗しました: {commit_result.stderr}")
            else:
                merge_result = git_ops.merge_branch_into_worktree(integration_dir, branch)
                if not merge_result.ok:
                    # 競合の事実だけでは何と競合したのか分からず、直しようがない。
                    # git の出力を添える（2026-09-05 実測で原因を特定できなかった）。
                    detail = (merge_result.stderr or merge_result.stdout or "").strip()
                    proposal = _replace_status(
                        proposal,
                        status="failed",
                        error="他の修正と競合しました" + (f"（{detail[:200]}）" if detail else ""),
                    )
                else:
                    _add_log(run, f"欠陥 {defect_id} の修正を統合しました")

        if workdir.exists():
            remove_result = git_ops.remove_worktree(repo, workdir)
            if not remove_result.ok:
                _add_log(run, f"worktree の後片付けに失敗しました（{workdir}）: {remove_result.stderr}")

        # 統合ブランチへ取り込めた欠陥ブランチは、内容が統合側に残るので消してよい。
        # 残すと 1 実行あたり「欠陥数 × 周回数」本のブランチが対象リポジトリに永久に積もる。
        # マージできたかを git 自身に確認してから消す（自分の記録だけを根拠にしない）。
        if git_ops.branch_is_merged_into(repo, branch, integration_branch):
            delete_result = git_ops.delete_branch(repo, branch)
            if not delete_result.ok:
                _add_log(run, f"欠陥ブランチを削除できませんでした（{branch}）: {delete_result.stderr}")

        # リスクとレポートは最終状態が決まってから載せる（人の判断材料のため）。
        ordered.append(_enrich_proposal(run, defect, proposal))

    return ordered


def _replace_status(proposal: FixProposal, *, status: str, error: str) -> FixProposal:
    """FixProposal は frozen dataclass なので、状態変更は新しいコピーで行う（不変データ方針）。

    フィールドを列挙して作り直すと、後から足したフィールド（risks / report_md）が
    黙って落ちる。dataclasses.replace で「変える所だけ」を指定する。
    """
    return replace(proposal, status=status, error=error)


# ────────────── 限局・リスク・レポート（人が判断するための材料） ──────────────
#
# localization / risk / report は修正そのものではなく「判断材料」を作る。
# したがってここでの失敗はループを止めない。ただし握り潰さず、
# logger と run.log の両方へ日本語 1 行を必ず残す。


def _write_reports(out_dir: Path, run: HealingRun, project: HealingProject) -> None:
    """この実行の各欠陥について、保守対応報告書を作る（既にあれば更新する）。

    報告書はこのシステムの成果物そのもの。ただし報告書づくりが失敗しても
    修正と検証は成立しているので、ループは止めない（記録だけ残す）。
    """
    for iteration in run.iterations:
        by_defect = {p.defect_id: p for p in iteration.proposals}
        for defect in iteration.defects:
            try:
                fresh = report_doc.build_maintenance_report(
                    run=run,
                    iteration=iteration,
                    defect=defect,
                    proposal=by_defect.get(defect.defect_id),
                    project=project,
                )
                existing = report_doc.find_report(
                    out_dir, run_id=run.run_id, defect_id=defect.defect_id
                )
                report = (
                    report_doc.merge_report(existing, fresh) if existing else fresh
                )
                report_doc.save_report(out_dir, report)
                if report.report_id not in run.report_ids:
                    run.report_ids.append(report.report_id)
            except Exception:  # noqa: BLE001 - 報告書の失敗で修正の成果を捨てない
                logger.warning("報告書の作成に失敗しました", exc_info=True)
                _add_log(run, "報告書の作成に失敗しました。実行の結果には影響しません")


def _localize_defects(run: HealingRun, defects: Sequence[Defect], *, repo: Path) -> list[Defect]:
    """欠陥ごとに限局を求め、結果を載せた新しい Defect の一覧を返す（元は書き換えない）。"""
    located: list[Defect] = []
    for defect in defects:
        try:
            located.append(_with_locations(defect, localization.locate(defect, repo=repo)))
        except Exception as exc:  # noqa: BLE001 - 限局の失敗で修正ループを止めない
            logger.warning("欠陥 %s の限局に失敗しました: %s", defect.defect_id, exc, exc_info=True)
            _add_log(run, f"欠陥 {defect.defect_id} の限局に失敗しました（修正はそのまま続けます）")
            located.append(defect)
    return located


def _with_locations(defect: Defect, evidence: Sequence[Any]) -> Defect:
    """限局結果を dict 化して Defect に載せる。frozen なので新しいオブジェクトを返す。"""
    locations = tuple(
        {
            "path": str(getattr(item, "path", "") or ""),
            "reason": str(getattr(item, "reason", "") or ""),
            "score": float(getattr(item, "score", 0.0) or 0.0),
            "detail": str(getattr(item, "detail", "") or ""),
        }
        for item in evidence
    )
    locations = tuple(loc for loc in locations if loc["path"])
    if not locations:
        return defect
    # 既存の suspect_files を先頭に残したまま、限局で挙がったパスを重複なく足す。
    merged = list(defect.suspect_files) + [loc["path"] for loc in locations]
    return replace(
        defect,
        suspect_files=tuple(dict.fromkeys(path for path in merged if path)),
        locations=locations,
    )


def _instructions_with_locations(base: str, defect: Defect) -> str:
    """利用者の指示を保持したまま、限局の根拠を日本語 1〜5 行だけ追記する。"""
    lines: list[str] = []
    for loc in defect.locations[:5]:
        path = str(loc.get("path") or "")
        if not path:
            continue
        reason = str(loc.get("reason") or "根拠不明")
        try:
            score = float(loc.get("score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        percent = score * 100 if score <= 1.0 else score
        lines.append(f"- {path}（{reason}・確度 {percent:.0f}%）")
    if not lines:
        return base
    hint = "該当が疑われるファイル（自動限局・確度の高い順）:\n" + "\n".join(lines)
    return f"{base}\n\n{hint}" if base else hint


def _risk_signal_to_dict(signal: Any) -> dict[str, Any]:
    """RiskSignal を保存可能な dict にする。"""
    return {
        "code": str(getattr(signal, "code", "") or ""),
        "label": str(getattr(signal, "label", "") or ""),
        "detail": str(getattr(signal, "detail", "") or ""),
        "severity": str(getattr(signal, "severity", "") or ""),
    }


def _assess_risks(run: HealingRun, defect: Defect, proposal: FixProposal) -> tuple[Any, ...]:
    """修正案のリスク評価。失敗しても修正は捨てず、空のまま続行する。"""
    try:
        return tuple(risk.assess(proposal))
    except Exception as exc:  # noqa: BLE001 - リスク評価の失敗で修正を捨てない
        logger.warning("欠陥 %s のリスク評価に失敗しました: %s", defect.defect_id, exc, exc_info=True)
        _add_log(run, f"欠陥 {defect.defect_id} のリスク評価に失敗しました（修正は保持します）")
        return ()


def _location_evidence(defect: Defect) -> tuple[Any, ...]:
    """保存済みの dict を LocationEvidence へ戻す（レポート生成に渡すため）。"""
    try:
        return tuple(
            localization.LocationEvidence(
                path=str(loc.get("path") or ""),
                reason=str(loc.get("reason") or ""),
                score=float(loc.get("score") or 0.0),
                detail=str(loc.get("detail") or ""),
            )
            for loc in defect.locations
        )
    except Exception as exc:  # noqa: BLE001 - 復元できなくてもレポートは作る
        logger.warning("欠陥 %s の限局根拠を復元できませんでした: %s", defect.defect_id, exc)
        return ()


def _enrich_proposal(run: HealingRun, defect: Defect, proposal: FixProposal) -> FixProposal:
    """修正案にリスク評価と Markdown レポートを載せた新しい FixProposal を返す。"""
    signals = _assess_risks(run, defect, proposal)
    report_md = ""
    try:
        report_md = str(
            healing_report.build_report(
                defect, proposal, evidence=_location_evidence(defect), risks=signals
            )
            or ""
        )
    except Exception as exc:  # noqa: BLE001 - レポート生成の失敗で修正を捨てない
        logger.warning("欠陥 %s のレポート生成に失敗しました: %s", defect.defect_id, exc, exc_info=True)
        _add_log(run, f"欠陥 {defect.defect_id} のレポート生成に失敗しました（修正は保持します）")
    return replace(
        proposal,
        risks=tuple(_risk_signal_to_dict(signal) for signal in signals),
        report_md=report_md,
    )


def _append_reports(body: str, proposals: Sequence[FixProposal]) -> str:
    """PR 本文の末尾へ修正レポートを足す。失敗しても既存の本文は壊さない。"""
    reports = [p.report_md for p in proposals if p.report_md]
    if not reports:
        return body
    try:
        section = str(healing_report.build_pr_section(reports) or "")
    except Exception as exc:  # noqa: BLE001 - レポート追記の失敗で PR 作成を止めない
        logger.warning("PR 本文への修正レポート追記に失敗しました: %s", exc, exc_info=True)
        return body
    return f"{body}\n\n{section}" if section else body
