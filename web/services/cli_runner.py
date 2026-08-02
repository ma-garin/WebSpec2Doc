"""CLI モード（画面なし）から本体機能を実行するための Flask 非依存ランナー。

GUI では AutoRun もテスト実行も HTTP ルート越しに動かしており、端末からは到達できなかった。
パイプライン本体（`_run_job` と各 `_phase_*`）はリクエストコンテキストに依存していないため、
ここではジョブを組み立てて直接回し、GUI が担っていた「待ちの解除」だけを肩代わりする。

肩代わりする待ちは 2 つ:
  - ログイン情報の入力待ち（画面ではモーダル）
  - 段階承認の待ち（画面では承認ボタン）

どちらも CLI では対話しないため、指定に従って自動で投入・承認・スキップする。
何を自動で通したかは必ず戻り値に残す（黙って通したことを隠さない）。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from typing import Any

#: ログイン待ち・段階待ちを見張る間隔（秒）
_POLL_SEC = 0.5
#: パイプライン全体の既定上限（秒）。超えたら中止して理由を残す。
DEFAULT_TIMEOUT_SEC = 3600


@dataclass
class AutoRunResult:
    """CLI から見た AutoRun の実行結果。"""

    ok: bool
    status: str
    job_id: str
    url: str
    domain: str
    elapsed_sec: float
    #: 自動で肩代わりした待ち（人が判断していない箇所）
    auto_handled: list[str] = field(default_factory=list)
    #: 実行ログ（画面の実行ログと同じ内容）
    logs: list[str] = field(default_factory=list)
    #: 未確認として記録された項目
    unverified: list[str] = field(default_factory=list)
    error: str = ""

    def exit_code(self) -> int:
        """終了コード。0=正常 / 1=テスト失敗を含む完了 / 2=実行エラー / 130=中止。"""
        if self.status == "cancelled":
            return 130
        if self.status == "failed" or self.error:
            return 2
        return 0 if self.ok else 1


def _job_snapshot(url: str, set_id: str | None, version: int | None) -> dict[str, Any]:
    """観点セットを固定する（GUI と同じ選定ロジックを使う）。"""
    from web.services.viewpoint_store import get_viewpoint_store

    return get_viewpoint_store().select_snapshot(
        {"url": url}, set_id=set_id or None, version_number=version
    )


def run_autorun(
    url: str,
    *,
    output_dir: Path,
    depth: int = 2,
    max_pages: int = 30,
    auth_path: str = "",
    viewpoint_set_id: str = "",
    viewpoint_version: int | None = None,
    login_user: str = "",
    login_password: str = "",
    login_skip: bool = True,
    approve: str = "auto",
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    on_log: Callable[[str], None] | None = None,
) -> AutoRunResult:
    """AutoRun のパイプラインを端末から最後まで回す。

    引数:
        login_user / login_password: ログイン待ちになったときに投入する資格情報。
        login_skip: 資格情報が無いときにスキップして続行するか（False なら待たずに中止）。
        approve: 段階承認の扱い。'auto'（内容を生成して自動承認）/ 'skip'（関門を素通り）。
        on_log: 実行ログを逐次受け取るコールバック（CLI の標準出力用）。
    """
    # AutoRun パイプライン本体（_run_job）は web.routes.auto_run に実装がある。
    # 本来は services 層に置くべきだが、_phase_* 群（同ファイル内に約900行）と
    # 密結合しており、分離は大規模リファクタリングになるため今回の対象外とした。
    # services -> routes の循環 import になることを承知の上で、関数内に閉じた
    # 遅延 import として残す（モジュール読み込み時には発火しない）。
    from web.routes.auto_run import _run_job
    from web.services.auto_run_job import AutoRunJob

    started = time.monotonic()
    auto_handled: list[str] = []

    def _now_iso() -> str:
        from datetime import datetime

        return datetime.now(UTC).isoformat()

    try:
        snapshot = _job_snapshot(url, viewpoint_set_id, viewpoint_version)
    except Exception as exc:  # noqa: BLE001  観点DBの例外型は複数ある
        return AutoRunResult(
            ok=False,
            status="failed",
            job_id="",
            url=url,
            domain="",
            elapsed_sec=0.0,
            error=f"観点セットを固定できません: {exc}",
        )

    import uuid

    job = AutoRunJob(
        job_id=uuid.uuid4().hex,
        url=url,
        started_at=_now_iso(),
        viewpoint_set_id=snapshot["set_id"],
        viewpoint_set_name=snapshot["set_name"],
        viewpoint_version=int(snapshot["version"]),
        viewpoint_checksum=snapshot["checksum"],
        viewpoint_selection_reason=snapshot["selection_reason"],
        viewpoint_count=int(snapshot["viewpoint_count"]),
    )
    job._viewpoint_snapshot = snapshot
    job._output_dir = output_dir
    if auth_path:
        job.auth_path = auth_path
    job.add_log(
        f"観点セットを固定: {job.viewpoint_set_name} v{job.viewpoint_version} "
        f"({job.viewpoint_count}件 / {job.viewpoint_selection_reason})"
    )

    worker = threading.Thread(target=_run_job, args=(job, depth, max_pages), daemon=True)
    worker.start()

    seen_logs = 0
    deadline = time.monotonic() + timeout_sec
    while worker.is_alive():
        if on_log:
            lines = list(job.log)
            for line in lines[seen_logs:]:
                on_log(str(line))
            seen_logs = len(lines)

        if time.monotonic() > deadline:
            job.cancel()
            auto_handled.append(f"制限時間 {timeout_sec} 秒を超えたため中止した")
            break

        # ---- ログイン情報の入力待ちを肩代わりする ----
        if job.status == "awaiting_input" and not job._input_data:
            if login_user or login_password:
                job._input_data = {
                    "type": "login",
                    "username": login_user,
                    "password": login_password,
                    "skip": False,
                }
                job.input_request = None
                job.status = "crawling"
                job._input_event.set()
                auto_handled.append("ログイン情報を CLI 引数から投入した")
            elif login_skip:
                job._input_data = {"type": "login", "username": "", "password": "", "skip": True}
                job.input_request = None
                job.status = "crawling"
                job._input_event.set()
                auto_handled.append(
                    "ログイン情報を渡していないためスキップした（未ログイン範囲のみの結果になる）"
                )
            else:
                job.cancel()
                auto_handled.append("ログインが必要だが資格情報が無いため中止した")
                break

        # ---- 段階承認の待ちを肩代わりする ----
        if job.status == "awaiting_stages":
            job.add_log("CLI モードのため、実行条件を確定して次の段階へ進みます。")
            job.add_unverified("人の確認を経ずに実行へ進みました — CLI モードでの自動承認")
            job._stages_event.set()
            auto_handled.append(
                "段階承認を自動で通した（内容を生成して承認）"
                if approve == "auto"
                else "段階承認の関門を素通りした"
            )

        time.sleep(_POLL_SEC)

    worker.join(timeout=30)

    if on_log:
        for line in list(job.log)[seen_logs:]:
            on_log(str(line))

    status = str(job.status or "")
    return AutoRunResult(
        ok=status == "complete",
        status=status,
        job_id=job.job_id,
        url=url,
        domain=str(getattr(job, "domain", "") or ""),
        elapsed_sec=round(time.monotonic() - started, 1),
        auto_handled=auto_handled,
        logs=[str(x) for x in job.log],
        unverified=[str(x) for x in getattr(job, "unverified", []) or []],
        error=str(getattr(job, "error", "") or ""),
    )


@dataclass
class TestRunResult:
    """テストケース表からの実行結果。"""

    ok: bool
    domain: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_ms: int = 0
    error: str = ""

    def exit_code(self) -> int:
        if self.error:
            return 2
        return 0 if self.failed == 0 else 1


def run_testcases(
    domain: str,
    *,
    output_dir: Path,
    case_ids: list[str] | None = None,
) -> TestRunResult:
    """テストケース表から spec を生成し、その場で実行して結果を保存する。

    GUI の「表示中の N 件を実行」と同じ処理を端末から行う。
    """
    import json
    from datetime import datetime

    from crawler.url_safety import _local_targets_allowed
    from web.services.egress_gateway import EgressPolicy
    from web.services.playwright_executor import run_playwright
    from web.services.testcase_spec_generator import SpecGenerationError, generate_spec
    from web.services.testcase_table_store import compose, run_dir, save_run_result

    report_path = output_dir / domain / "report.json"
    if not report_path.is_file():
        return TestRunResult(
            ok=False, domain=domain, error=f"report.json がありません: {report_path}"
        )
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return TestRunResult(ok=False, domain=domain, error=f"report.json を読めません: {exc}")

    rows = compose(domain, report)["rows"]
    if case_ids:
        allow = {str(x) for x in case_ids}
        rows = [r for r in rows if r["case_id"] in allow]
    if not rows:
        return TestRunResult(ok=False, domain=domain, error="実行対象のテストケースがありません")

    out = Path(run_dir(domain))
    try:
        gen = generate_spec(rows, out)
    except SpecGenerationError as exc:
        return TestRunResult(ok=False, domain=domain, error=f"spec の生成に失敗しました: {exc}")

    spec_path = Path(gen.get("spec_path") or (out / "testcases.spec.ts"))
    # 送信先の許可方針は GUI と同じものを使う。これを渡さないとローカル宛が全て
    # 遮断され、96 件生成されているのに「0 件・成功」という誤報になる。
    result = run_playwright(
        spec_path,
        out,
        per_test_timeout_sec=20,
        egress_policy=EgressPolicy(allow_local=_local_targets_allowed()),
    )
    # run_playwright は summary を包まず、集計値をそのまま返す（GUI も同じ形で使う）
    summary = result or {}
    save_run_result(domain, result, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if not summary.get("total"):
        # 1 件も走っていないのに成功と見せない。原因を持ち帰る。
        return TestRunResult(
            ok=False,
            domain=domain,
            error=str(
                summary.get("stderr_snippet")
                or summary.get("error")
                or "テストを 1 件も実行できませんでした"
            ),
        )
    return TestRunResult(
        ok=bool(summary.get("ok")),
        domain=domain,
        total=int(summary.get("total") or 0),
        passed=int(summary.get("passed") or 0),
        failed=int(summary.get("failed") or 0),
        skipped=int(summary.get("skipped") or 0),
        duration_ms=int(summary.get("duration_ms") or 0),
        error=str(summary.get("error") or ""),
    )
