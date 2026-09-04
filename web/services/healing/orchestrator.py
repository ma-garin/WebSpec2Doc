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

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Any

from web.services.healing import agents as healing_agents
from web.services.healing import git_ops, github_client, project_store, run_store, verification
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
DECISION_ACTIONS = ("approve", "reject", "rerun", "merge")

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


def start_run(*, out_dir: Path, project: HealingProject, actor: str = "", extra_instructions: str = "") -> HealingRun:
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

    thread = threading.Thread(
        target=_run_loop,
        args=(out_dir, run, project, extra_instructions),
        name=f"healing-{run_id}",
        daemon=True,
    )
    thread.start()
    return run


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
        _update(out_dir, run, status="cancelled", note=f"{actor or '人'} が却下しました" + (f"（{note}）" if note else ""))
        return run

    if action == "rerun":
        return rerun_verification(out_dir, run_id)

    # action == "merge"
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


def _run_loop(out_dir: Path, run: HealingRun, project: HealingProject, extra_instructions: str) -> None:
    try:
        _run_loop_inner(out_dir, run, project, extra_instructions)
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
        with _RUNS_LOCK:
            _CANCEL.discard(run.run_id)


def _run_loop_inner(out_dir: Path, run: HealingRun, project: HealingProject, extra_instructions: str) -> None:
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

        if verify_result.ok:
            iteration.verify_after = verify_result
            iteration.finished_at = _now_iso()
            run.status = "no_defects" if i == 1 else "succeeded"
            _update(out_dir, run, status=run.status, step_label="検証が緑になりました")
            break

        if _cancelled(run.run_id):
            _update(out_dir, run, status="cancelled", step_label="中止")
            return

        # analyzing
        _update(out_dir, run, status="analyzing", step_label=f"欠陥の切り出し（{i} 周目）")
        defects = verification.failures_to_defects(verify_result.failures, repo=integration_dir, source="verify")
        iteration.defects = list(defects)
        if not defects:
            # 「不在の証明」はしない: 失敗を構造化できなかった事実だけを記録して止まる。
            run.unverified.append(f"{i} 周目: 検証は失敗しましたが、失敗を欠陥として構造化できませんでした")
            iteration.finished_at = _now_iso()
            run.error = "検証失敗を欠陥として構造化できませんでした"
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
            run.error = "修正案が 1 件も適用できませんでした"
            _update(out_dir, run, status="failed", step_label="失敗")
            return

        applied_any = True
        _add_log(run, f"{len(applied)} 件の修正を統合ブランチへ反映しました")
        previous_iteration = iteration
    else:
        # for-else: break せずにループを終えた = 上限に達しても緑にならなかった。
        run.unverified.append(f"検証は緑になっていません。{project.max_iterations} 周で打ち切りました")
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
                extra_instructions=extra_instructions,
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
                    # 黙って捨てず、競合の事実を proposal に残す。
                    proposal = _replace_status(proposal, status="failed", error="他の修正と競合しました")
                else:
                    _add_log(run, f"欠陥 {defect_id} の修正を統合しました")

        if workdir.exists():
            remove_result = git_ops.remove_worktree(repo, workdir)
            if not remove_result.ok:
                _add_log(run, f"worktree の後片付けに失敗しました（{workdir}）: {remove_result.stderr}")

        ordered.append(proposal)

    return ordered


def _replace_status(proposal: FixProposal, *, status: str, error: str) -> FixProposal:
    """FixProposal は frozen dataclass なので、状態変更は新しいコピーで行う（不変データ方針）。"""
    return FixProposal(
        defect_id=proposal.defect_id,
        agent=proposal.agent,
        status=status,
        summary=proposal.summary,
        rationale=proposal.rationale,
        diff=proposal.diff,
        files_changed=proposal.files_changed,
        log_tail=proposal.log_tail,
        duration_sec=proposal.duration_sec,
        error=error,
    )
