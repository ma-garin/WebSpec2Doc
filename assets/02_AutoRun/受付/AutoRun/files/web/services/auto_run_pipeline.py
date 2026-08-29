"""AutoRun パイプライン本体（実行フェーズ群）。

段階承認の待機・ログイン入力待ち・観測(discover/crawl)・QA成果物生成・
Playwright化・テスト実行・失敗分析までの一連の処理をここに置く。

元は web/routes/auto_run.py に実装されていたが、web/services/cli_runner.py
（CLIモードのランナー）が _run_job を呼ぶ必要があり、実体が routes 側にしか
無かったため services -> routes の逆依存（唯一残っていた循環依存の原因）に
なっていた。このパイプラインは Flask のリクエストコンテキスト
（request / session / g / current_app 等）に一切依存していないため、
本来の置き場である services 層へそのまま移設した。

web/routes/auto_run.py は後方互換のため、ここから同名で re-export している
（外部テスト・既存呼び出し元を壊さないため）。
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from web.config import DISCOVER_TIMEOUT_SEC
from web.services.auto_run_job import AutoRunJob, _job_out, logger
from web.services.document_autorun import candidate_filename, run_document_autorun_phase
from web.services.evidence_pack_service import attach_evidence_pack
from web.services.failure_classifier import (
    classify_failure,
    classify_failures,
    summarize_classifications,
)
from web.services.playwright_executor import run_playwright
from web.services.qa.advanced_generator import _generate_advanced_outputs
from web.services.qa.doc_generator import _generate_outputs
from web.services.qa.helpers import _load_report, use_output_dir, use_viewpoint_snapshot
from web.services.spec_ts_generator import compute_filter_counts, generate_spec_ts
from web.services.viewpoint_store import ViewpointStoreError, get_viewpoint_store
from web.validation import _domain_of

#: 段階承認の待機上限。人の確認を待つので長め（無期限にはしない）。
#: 時間切れでも実行は止めないが、job.unverified に必ず記録して成果物へ出す。
STAGE_APPROVAL_TIMEOUT_SEC = 7200
#: ログイン情報入力の待機上限。
LOGIN_INPUT_TIMEOUT_SEC = 1800


def _fmt_timeout(seconds: float) -> str:
    """待機上限を人が読める単位で返す（テストで短縮値を差し込めるよう秒も扱う）。"""
    if seconds >= 3600:
        return f"{seconds / 3600:.0f}時間"
    if seconds >= 60:
        return f"{seconds / 60:.0f}分"
    return f"{seconds:g}秒"


def _ensure_stage_content(job: AutoRunJob, stage_id: str) -> None:
    """関門到達時に、その段階の内容を生成して保存する（提示のための準備）。

    仕様は「テスト目的の**提示**・承認」であり、利用者に「内容を生成」を
    押させることではない。また、同一ドメインの過去実行で保存された
    stages.json が残っていると古い内容がそのまま提示されるため、
    実行のたびに生成し直す。

    失敗しても実行は止めない（利用者が手動生成できる余地を残す）。
    """
    from autorun.stages import Observation, Pipeline, build_stage, observation_from_report

    qa_dir = _job_out(job) / job.domain / "qa_process"
    stages_path = qa_dir / "stages.json"
    try:
        pipeline = (
            Pipeline.from_dict(json.loads(stages_path.read_text(encoding="utf-8")))
            if stages_path.is_file()
            else Pipeline.initial()
        )
        if pipeline.get(stage_id) is None:
            return

        report = _read_json_file(_job_out(job) / job.domain / "report.json")
        obs = (
            observation_from_report(
                report,
                url=job.url,
                document_driven=job.mode == "document",
                viewpoint_set_name=job.viewpoint_set_name,
            )
            if report
            else Observation(url=job.url)
        )
        automation = _read_json_file(qa_dir / "automation_coverage.json")
        stage = build_stage(stage_id, obs, pipeline, automation)
        pipeline = pipeline.replaced(stage).recorded(
            "generate", stage_id, f"{len(stage.items)}項目を提示", "system"
        )
        # 実行条件を確定済みなら、生成し直した内容もその確定に含める。
        # 再生成が承認済みステータスを上書きし、一括承認したのに
        # 「承認済み 1 / 8」と表示される食い違いが起きていた（実測で発覚）。
        if job.stages_all_released:
            from autorun.stages import STATUS_APPROVED

            approved = stage
            if stage.definition.requires_item_approval:
                for item in stage.items:
                    if not item.approved:
                        approved = approved.with_item(replace(item, approved=True))
            pipeline = pipeline.replaced(approved.with_status(STATUS_APPROVED)).recorded(
                "approve", stage_id, "実行条件の確定により承認", "system"
            )
        qa_dir.mkdir(parents=True, exist_ok=True)
        stages_path.write_text(
            json.dumps(pipeline.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        job.add_log(f"{stage.definition.name}: {len(stage.items)}項目を提示しました。")
    except Exception as exc:
        # 失敗を黙って空にすると、画面では「まだ生成されていない」未着手と
        # 区別がつかない。失敗した事実を未確認事項として残す。
        job.add_unverified(
            f"{stage_id} の内容を生成できませんでした（この段階は人の確認も経ていません）: {exc}"
        )


def _format_crawl_event(line: str) -> str:
    """CRAWL_EVENT 行を、人が読める1行へ整える。

    取得できた件数だけでなく、スキップ・失敗も理由つきで出す。
    「取得できなかった」を隠して空欄で通さないため。
    """
    if not line.startswith("CRAWL_EVENT:"):
        return ""
    try:
        event = json.loads(line[len("CRAWL_EVENT:") :])
    except (ValueError, TypeError):
        return ""
    if not isinstance(event, dict):
        return ""

    kind = str(event.get("event", ""))
    url = str(event.get("url", ""))
    path = _short_path(url)

    if kind == "crawl_started":
        return f"観測開始: 最大 {event.get('total', '?')} 画面 / 並列 {event.get('parallelism', 1)}"
    if kind == "page_started":
        return f"取得中  {path}（{event.get('index', '?')} / {event.get('total', '?')}）"
    if kind == "page_completed":
        detail = f"フォーム{event.get('forms', 0)}件"
        required = event.get("required_inputs", 0)
        if required:
            detail += f"（必須{required}）"
        detail += f" ・ リンク{event.get('links', 0)}件"
        return (
            f"取得済み {path} — {detail}"
            f"（{event.get('completed', '?')} / {event.get('total', '?')}）"
        )
    if kind == "page_skipped":
        return f"スキップ {path} — {event.get('reason', '理由不明')}"
    if kind == "checkpoint_saved":
        return f"途中保存: {event.get('saved_count', 0)}件"
    if kind == "crawl_completed":
        return f"観測完了: {event.get('completed', 0)} / {event.get('total', '?')} 画面"
    return ""


def _short_path(url: str) -> str:
    """ログに出す用に、URL をパスだけへ縮める。"""
    if not url:
        return "(URL不明)"
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")


#: 段階ごとの関門メッセージ（仕様7〜14: 各段階で個別に提示・承認する）。
#
# 以前は設計段階1〜7を "design" という単一の関門でまとめて承認させていた。
# しかし仕様では各段階が独立した提示・承認点であり、開始した途端に
# 1〜7の内容が一度に出てしまう問題があった（利用者の操作で発覚）。
# ここでは段階IDごとに関門を持ち、1段階ずつ止まる。
_GATE_MESSAGES = {
    "test_objective": (
        "テスト目的の承認待ち",
        "この対象に対するテスト目的・方針を提示しました。確認し、承認すると"
        "テスト計画へ進みます。",
        "テスト目的",
    ),
    "test_plan": (
        "テスト計画の承認待ち",
        "テスト目的に対する進め方・範囲・前提を提示しました。確認し、承認すると"
        "フィーチャー分析へ進みます。",
        "テスト計画",
    ),
    "features": (
        "テストフィーチャー分析の承認待ち",
        "実測した画面からフィーチャーを切り出しました。すべてのフィーチャーを"
        "確認・承認すると観点分析へ進みます。",
        "フィーチャー",
    ),
    "viewpoints": (
        "テスト観点分析の承認待ち",
        "フィーチャーごとのテスト観点を提示しました。確認し、承認すると"
        "テスト基本設計へ進みます。",
        "テスト観点",
    ),
    "basic_design": (
        "テスト基本設計の承認待ち",
        "観点へ適用する技法と、実測項目へ技法を適用した具体値を提示しました。"
        "確認し、承認すると詳細設計へ進みます。",
        "テスト基本設計",
    ),
    "detail_design": (
        "テスト詳細設計の承認待ち",
        "ハイレベルテストケースを提示しました。確認し、承認すると" "テストケース作成へ進みます。",
        "テスト詳細設計",
    ),
    "test_cases": (
        "テストケースの承認待ち",
        "ローレベルテストケースを提示しました。確認し、承認すると" "Playwright 化へ進みます。",
        "テストケース",
    ),
    "playwright": (
        "Playwright 自動化の承認待ち",
        "スクリプトを生成しました。承認済みケースとの対応・未自動化のケースを"
        "確認し、承認するとテストを実行します。",
        "自動化の内容",
    ),
}


def _await_stage_approval(job: AutoRunJob, gate: str) -> None:
    """段階承認（仕様7〜14）が済むまで待つ。

    実行は対象サイトへ実際に操作を行うため、人が確認・承認するまで進めない。
    タイムアウト時は「未承認のまま進めた」ことを記録し、黙って進んだように見せない。
    """
    label, message, subject = _GATE_MESSAGES[gate]

    if not job.require_stage_approval:
        # 人が承認できない文脈（自動実行など）。飛ばした事実を必ず残す。
        job.add_unverified(f"{subject}: 自動実行のため段階承認を行わず、人の確認を経ていません。")
        return

    # 仕様7〜14は「提示・承認」。利用者に「内容を生成」を押させるのではなく、
    # 関門に到達した時点で内容を用意して提示する。
    # （過去の実行で保存された古い stages.json が残っていると、新しい生成規則が
    #  反映されないまま提示される問題もここで解消する。）
    _ensure_stage_content(job, gate)

    # 実行条件を一括確定済みなら、以降の段階では止めない。
    # 生成済みのものを7回に分けて承認させる理由がないため（利用者の指摘）。
    if job.stages_all_released:
        job.add_log(f"{subject}は実行条件の確定により承認済みです。")
        return

    job._stages_event.clear()
    job.status = "awaiting_stages"
    job.step_label = label
    # いまどの段階で待っているかをUIへ伝える（1段階ずつ提示するために必須）。
    job.awaiting_stage_id = gate
    # 期限を状態として持つ。画面に残り時間を出さないと、時間切れは
    # 「黙って承認された」のと区別がつかない。
    job.awaiting_deadline_epoch = time.time() + STAGE_APPROVAL_TIMEOUT_SEC
    job.add_log(message)

    approved = job._stages_event.wait(timeout=STAGE_APPROVAL_TIMEOUT_SEC)
    job.awaiting_stage_id = ""
    job.awaiting_deadline_epoch = 0.0
    if job._cancelled:
        return
    if not approved:
        job.add_unverified(
            f"{subject}: 承認待ちがタイムアウト（{_fmt_timeout(STAGE_APPROVAL_TIMEOUT_SEC)}）し、"
            "人の確認を経ないまま後続へ進みました。"
        )


def _run_job(job: AutoRunJob, depth: int, max_pages: int) -> None:
    try:
        _phase_discover(job, depth, max_pages)
        if job.status in ("failed", "cancelled"):
            return

        # ログイン入力待ち（最大 30 分）
        if job.status == "awaiting_input":
            job.awaiting_deadline_epoch = time.time() + LOGIN_INPUT_TIMEOUT_SEC
            job._input_event.wait(timeout=LOGIN_INPUT_TIMEOUT_SEC)
            job.awaiting_deadline_epoch = 0.0
            if job._cancelled:
                return
            if not job._input_data:
                job.add_unverified(
                    "ログイン情報の入力がタイムアウト"
                    f"（{_fmt_timeout(LOGIN_INPUT_TIMEOUT_SEC)}）し、"
                    "未ログインで到達できる範囲だけを対象にしました。"
                )

            if job._input_data.get("type") == "login" and not job._input_data.get("skip"):
                _do_login(job)
                if job.status == "failed":
                    return

        _phase_crawl(job, depth, max_pages)
        if job.status in ("failed", "cancelled"):
            return
        _phase_generate_qa(job)
        if job.status in ("failed", "cancelled"):
            return
        if job.mode == "document":
            _phase_generate_document_mbt(job)
            if job.status in ("failed", "cancelled"):
                return

        # 仕様7〜13: 設計段階を**1段階ずつ**提示し、それぞれ承認を得る。
        # 以前は1〜7を1つの関門でまとめて承認させており、開始した途端に
        # 全段階の内容が一度に出てしまっていた（利用者の操作で発覚した重大な乖離）。
        from autorun.stages import DESIGN_STAGE_IDS

        for stage_gate in DESIGN_STAGE_IDS:
            _await_stage_approval(job, stage_gate)
            if job.status in ("failed", "cancelled"):
                return

        _phase_generate_scripts(job)
        if job.status in ("failed", "cancelled"):
            return

        # 関門2: 段階8（Playwright 自動化）。生成したスクリプトと未自動化を
        # 提示し、承認を得るまでテストを実行しない。
        #
        # 以前はこの後さらに「テスト実行の承認」という第3の関門（awaiting_approval /
        # /api/autorun/approve）があった。8フェーズすべてを承認し切った直後に
        # もう一度確認を挟む理由が画面から読み取れず、実際の検証でも3回停止することが
        # 確認された（監査で発覚・是正）。段階8の承認＝実行方針の承認として統合し、
        # ここで直接テスト実行へ進む。実行方針のカスタマイズは既定値（全件・PC・30秒）を使う。
        _await_stage_approval(job, "playwright")
        if job.status in ("failed", "cancelled"):
            return
        _execute_tests(job)
        if job._cancelled:
            return
        # L0/L4: 観測の完全性と非機能の合否判定。既存成果物のみを読むため
        # 対象サイトへの追加アクセスは発生しない。失敗しても本体結果は壊さない。
        _run_nonfunctional_analysis(job)
        # L3: 失敗の原因特定。失敗が無ければ何もしない。
        _run_failure_triage(job)
    except Exception as exc:
        if job._cancelled:
            return
        _mark_job_failed(job, str(exc))
        job.add_log(f"予期しないエラー: {exc}")


def _run_child_process(
    job: AutoRunJob, cmd: list[str], timeout: int, input_text: str | None = None
) -> str:
    """ジョブに登録した子プロセスとして CLI を実行し stdout を返す。

    subprocess.run はプロセスハンドルを外へ出さず、中止（cancel）から
    子プロセスを終了させられない。到達確認・ログインが止められなかった原因。
    呼び出し元は戻った直後に job._cancelled を確認して打ち切ること。
    """
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    job.register_proc(proc)
    try:
        stdout, _ = proc.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise
    finally:
        job._proc = None
    return stdout


def _phase_discover(job: AutoRunJob, depth: int, max_pages: int) -> None:
    """画面リスト取得 + ログイン壁検知。"""
    job.status = "discovering"
    job.step_label = "到達確認中"
    # 語彙は「到達確認 → 観測」に統一する。以前は「画面分析」「クロール」「解析」が
    # 混在し、別工程なのか言い換えなのかログから判別できなかった。
    job.add_log(f"到達確認開始: {job.url}")

    cmd = [
        sys.executable,
        "src/main.py",
        "--discover",
        "--url",
        job.url,
        "--depth",
        str(depth),
        "--max-pages",
        str(max_pages),
    ]
    if job.auth_path:
        cmd += ["--auth", job.auth_path]

    try:
        stdout = _run_child_process(job, cmd, DISCOVER_TIMEOUT_SEC)
        if job._cancelled:
            return
        data = json.loads(stdout.strip() or "{}")
        pages: list[dict[str, Any]] = data.get("pages", [])
    except subprocess.TimeoutExpired:
        job.add_log("到達確認タイムアウト。そのまま観測を続行します。")
        return
    except Exception as exc:
        if job._cancelled:
            return
        job.add_log(f"到達確認エラー: {exc}。そのまま観測を続行します。")
        return

    login_pages = [p for p in pages if p.get("login_required")]
    job.step_data["discover"] = {"pages": len(pages), "login_required": len(login_pages)}
    job.add_log(
        f"到達確認完了: {len(pages)}画面を検出"
        + (
            f"（うち要ログイン {len(login_pages)}画面。認証しなければ観測対象外）"
            if login_pages
            else ""
        )
    )

    if login_pages:
        login_url = login_pages[0].get("login_url") or job.url
        login_fields = login_pages[0].get("login_fields", [])
        job.status = "awaiting_input"
        job.step_label = "ログイン情報の入力待ち"
        job.input_request = {
            "type": "login",
            "login_url": login_url,
            "login_fields": login_fields,
            "domain": _domain_of(job.url),
            "message": f"{len(login_pages)}件のページにログインが必要です。認証情報を入力するかスキップしてください。",
        }
        job.add_log("ログインが必要なページが検出されました。認証情報の入力を待っています。")


def _do_login(job: AutoRunJob) -> None:
    input_data = job._input_data
    login_url = (job.input_request or {}).get("login_url") or job.url
    username = input_data.get("username", "")
    password = input_data.get("password", "")
    domain = _domain_of(job.url)

    job.add_log(f"ログイン試行: {login_url}")

    auth_path = _job_out(job) / domain / "auth.json"
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    creds_json = json.dumps({"username": username, "password": password})
    cmd = [
        sys.executable,
        "src/main.py",
        "--login-simple",
        "--login-simple-url",
        login_url,
        "--auth",
        str(auth_path),
    ]
    try:
        stdout = _run_child_process(job, cmd, 60, input_text=creds_json)
        if job._cancelled:
            return
        data = json.loads(stdout.strip() or "{}")
        if data.get("success"):
            job.auth_path = str(auth_path.resolve())
            job.add_log(f"ログイン成功。auth.json を保存しました: {job.auth_path}")
        else:
            job.add_log(
                f"ログインに失敗しました: {data.get('error', '不明なエラー')}。スキップして続行します。"
            )
    except subprocess.TimeoutExpired:
        job.add_log("ログインタイムアウト。スキップして続行します。")
    except Exception as exc:
        job.add_log(f"ログインエラー: {exc}。スキップして続行します。")


def _phase_crawl(job: AutoRunJob, depth: int, max_pages: int) -> None:
    job.status = "crawling"
    job.step_label = "仕様書を生成中"
    job.add_log(f"観測開始: {job.url}（深さ{depth} / 最大{max_pages}画面）")

    cmd = [
        sys.executable,
        "src/main.py",
        "--url",
        job.url,
        "--depth",
        str(depth),
        "--max-pages",
        str(max_pages),
        "--format",
        "json,md,html",
        "--output",
        str(_job_out(job)),
    ]
    if job.auth_path:
        cmd += ["--auth", job.auth_path]
    if job.mode == "document":
        for doc_path in job._reference_docs:
            cmd += ["--reference-doc", doc_path]

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        job._proc = proc
        for line in proc.stdout or []:
            if job._cancelled:
                proc.terminate()
                return
            line = line.rstrip()
            if not line:
                continue
            # クロールの進捗イベントは、いま何を取得しているか・何が取れたかを
            # その場で見せる形に整える。生ログのままだと中身が読み取れない。
            readable = _format_crawl_event(line)
            if readable:
                job.add_log(readable)
                continue
            # それ以外の生出力は開発者向け（UIでは既定非表示、トグルで表示）。
            job.add_log(f"[cli] {line}")
        proc.wait(timeout=600)
        job._proc = None
    except subprocess.TimeoutExpired:
        if proc:
            proc.kill()
        _mark_job_failed(job, "観測タイムアウト")
        return
    except Exception as exc:
        _mark_job_failed(job, f"観測エラー: {exc}")
        return

    if job._cancelled:
        return

    domain = _domain_of(job.url)
    job.domain = domain
    report_json = _job_out(job) / domain / "report.json"
    if not report_json.is_file():
        # 内部ファイル名をそのまま出しても、利用者は次に何をすればよいか分からない。
        _mark_job_failed(
            job,
            "観測結果を保存できませんでした。対象サイトへ到達できているか、"
            "出力先の書き込み権限があるかを確認してください。",
        )
        return

    job.outputs["report_json"] = str(report_json.resolve())
    report_html = _job_out(job) / domain / "report.html"
    if report_html.is_file():
        job.outputs["report_html"] = str(report_html.resolve())
    try:
        rj = json.loads(report_json.read_text(encoding="utf-8"))
        screens = rj.get("screens", [])
        job.step_data["crawl"] = {
            "screens": len(screens),
            "forms": sum(len(s.get("forms", [])) for s in screens),
            "domain": domain,
        }
    except Exception:
        job.step_data["crawl"] = {"domain": domain}
        screens = []

    # 1画面も観測できていないなら、以降の成果物はすべて中身の無い雛形になる。
    # 「完了」として進めると、空のテスト設計が正常な成果物に見えてしまう。
    if not screens:
        _mark_job_failed(
            job,
            "1画面も観測できませんでした。URL・到達可否・robots制限・ログイン要否を確認してください。",
        )
        return

    # 到達確認の件数と観測できた画面数がずれるのは正常（要ログイン等で対象外になる）。
    # 差を書かないと、どちらが対象範囲の真の値か分からず、カバレッジを誤読する。
    detected = int((job.step_data.get("discover") or {}).get("pages") or 0)
    gap = detected - len(screens)
    job.add_log(
        f"観測完了: {domain} {len(screens)}画面"
        + (f"（到達確認 {detected}画面のうち {gap}画面は対象外）" if gap > 0 else "")
    )


def _phase_generate_qa(job: AutoRunJob) -> None:
    if job._cancelled:
        return
    job.status = "generating_qa"
    job.step_label = "QA成果物を生成中"
    job.add_log("QAプロセス成果物を生成しています…")

    out_dir = _job_out(job)
    report_path = out_dir / job.domain / "report.json"
    report = _load_report(report_path)
    if report is None:
        _mark_job_failed(job, "report.json の読み込みに失敗しました")
        return

    try:
        snapshot = get_viewpoint_store().apply_snapshot_to_report(job._viewpoint_snapshot, report)
        job.viewpoint_count = int(snapshot["viewpoint_count"])
        snapshot_path = out_dir / job.domain / "qa_process" / "viewpoint_snapshot.json"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        job.outputs["viewpoint_snapshot"] = str(snapshot_path.resolve())
        report_with_snapshot = report | {
            "viewpoint_snapshot": {key: value for key, value in snapshot.items() if key != "items"}
        }
        # スレッド内はリクエストコンテキストが無いため、出力先を明示的に固定する
        with use_output_dir(out_dir), use_viewpoint_snapshot(snapshot["items"]):
            outputs = _generate_outputs(job.domain, report_with_snapshot)
            outputs |= _generate_advanced_outputs(job.domain, report_with_snapshot)
    except (ViewpointStoreError, OSError, ValueError) as exc:
        _mark_job_failed(
            job,
            f"観点スナップショット生成エラー: {exc}。既定公開版へ切り替えるか再試行してください。",
        )
        return
    except Exception as exc:
        _mark_job_failed(job, f"QA成果物生成エラー: {exc}")
        return

    for key, path in outputs.items():
        if path.is_file():
            job.outputs[key] = str(path.resolve())
    job.step_data["qa"] = {
        "count": len(outputs),
        "viewpoint_set": job.viewpoint_set_name,
        "viewpoint_version": job.viewpoint_version,
        "viewpoint_count": job.viewpoint_count,
    }
    job.add_log(
        f"QA成果物生成完了: {len(outputs)}件 / 適用観点: "
        f"{job.viewpoint_set_name} v{job.viewpoint_version} ({job.viewpoint_count}件)"
    )


def _phase_generate_document_mbt(job: AutoRunJob) -> None:
    run_document_autorun_phase(job, _job_out(job), _mark_job_failed)


def _apply_automation_plan(job: AutoRunJob, candidates_path: Path, spec_dir: Path) -> Path:
    """承認済みテストケースで自動化対象を絞り、使用する候補ファイルのパスを返す。

    承認済みケースが無い / 突合できない場合は元の候補をそのまま使う
    （段階承認を使わない実行を壊さない）。判断はログと成果物に残す。
    """
    from autorun.automation_plan import build_plan
    from autorun.stages import Pipeline

    stages_path = spec_dir / "stages.json"
    if not stages_path.is_file():
        return candidates_path

    try:
        pipeline = Pipeline.from_dict(json.loads(stages_path.read_text(encoding="utf-8")))
        raw = json.loads(candidates_path.read_text(encoding="utf-8"))
        plan = build_plan(pipeline, list(raw.get("candidates") or []))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        job.add_log(f"自動化対象の絞り込みをスキップしました（{exc}）。全候補を使います。")
        return candidates_path

    for line in plan.summary_lines():
        job.add_log(line)

    # 対応関係を成果物として残す（未自動化のケースを追跡できるようにする）
    coverage_path = spec_dir / "automation_coverage.json"
    try:
        coverage_path.write_text(
            json.dumps(plan.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        job.outputs["automation_coverage"] = str(coverage_path.resolve())
    except OSError as exc:
        job.add_log(f"自動化カバレッジを保存できませんでした: {exc}")

    if plan.unfiltered:
        return candidates_path

    selected_path = spec_dir / "approved_candidates.json"
    try:
        selected_path.write_text(
            json.dumps({"candidates": list(plan.selected)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        job.add_log(f"絞り込んだ候補を保存できませんでした（{exc}）。全候補を使います。")
        return candidates_path
    return selected_path


def _phase_generate_scripts(job: AutoRunJob) -> None:
    if job._cancelled:
        return
    job.status = "generating_scripts"
    job.step_label = "Playwright スクリプトを生成中"
    job.add_log("Playwright .spec.ts を生成しています…")

    candidates_filename = candidate_filename(job.mode)
    candidates_path = _job_out(job) / job.domain / "qa_process" / candidates_filename
    if not candidates_path.is_file():
        _mark_job_failed(job, f"{candidates_filename} が見つかりません")
        return

    spec_dir = _job_out(job) / job.domain / "qa_process"
    spec_path = spec_dir / "autorun.spec.ts"

    # 仕様14: 承認済みのローレベルテストケースを自動化の入力にする。
    # 対応づく候補だけを対象にし、対応の無いケースは「未自動化」として残す。
    source_path = _apply_automation_plan(job, candidates_path, spec_dir)

    try:
        # 実行条件で「送信まで実行」が選ばれた場合のみ、送信手順を生成する。
        generate_spec_ts(
            job.domain,
            source_path,
            spec_path,
            allow_submit=bool(job.run_policy.get("allow_submit")),
        )
    except Exception as exc:
        _mark_job_failed(job, f"スクリプト生成エラー: {exc}")
        return

    try:
        raw = json.loads(candidates_path.read_text(encoding="utf-8"))
        job.step_data["scripts"] = compute_filter_counts(raw.get("candidates", []))
    except Exception:
        job.step_data["scripts"] = {}
    job.outputs["spec_ts"] = str(spec_path.resolve())
    job.add_log(f"スクリプト生成完了: {spec_path.name}")
    _run_mutation_self_check(job, spec_path, spec_dir)
    _publish_playwright_stage(job, spec_dir)


def _run_nonfunctional_analysis(job: AutoRunJob) -> None:
    """L0 観測の完全性 ＋ L4 非機能の合否判定（設計計画 rev.3 / Phase 1）。

    どちらも既存の成果物のみを読む。**対象サイトへの追加アクセスはゼロ**。

    背景: a11y 違反は既に 635 件観測されていたのに、実行結果には
    「アクセシビリティ自動確認 1件 skipped」としか出ていなかった。
    観測はしているが判定へ接続していない、という欠落を埋める。
    """
    from web.services import nonfunctional_judge, observation_coverage

    base = _job_out(job) / job.domain
    qa = base / "qa_process"
    try:
        report = _read_json_file(base / "report.json")

        coverage = observation_coverage.analyze(report, job_log=list(job.log))
        (qa / "observation_coverage.json").write_text(
            json.dumps(coverage.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        job.outputs["observation_coverage"] = str((qa / "observation_coverage.json").resolve())
        if coverage.gaps:
            job.add_log(
                f"観測範囲: {coverage.observed_pages}ページ。"
                f"未観測の領域が {len(coverage.gaps)} 種類あります（未検証として記録）。"
            )
            # 未観測は「問題なし」ではない。承認まわりの未確認と同じ一覧へ集約し、
            # レポートを見た人が「確認済み」と誤読しないようにする。
            for gap in coverage.gaps:
                job.add_unverified(f"未観測の領域: {gap.kind}（{gap.count}件） — {gap.reason}")
        else:
            job.add_log(f"観測範囲: {coverage.observed_pages}ページ。未観測の領域は検出されず。")

        judged_path = qa / "nonfunctional_judgement.json"
        baseline = _read_json_file(judged_path)  # 前回の判定＝基準線
        judgement = nonfunctional_judge.judge_all(
            report=report,
            accessibility=_read_json_file(base / "accessibility_audit.json"),
            technical_health=_read_json_file(base / "technical_health.json"),
            baseline=baseline,
        )
        judged_path.write_text(
            json.dumps(judgement, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        job.outputs["nonfunctional_judgement"] = str(judged_path.resolve())
        for item in judgement["judgements"]:
            job.add_log(f"非機能[{item['area']}] {item['verdict']}: {item['summary']}")
    except Exception as exc:  # 付加価値であり、本体結果を壊さない
        job.add_log(f"非機能判定・観測範囲の分析に失敗しました（実行結果は保持）: {exc}")


def _run_failure_triage(job: AutoRunJob) -> None:
    """L3 失敗の原因特定（設計計画 rev.3 / Phase 2）。

    「Timeout」「expected true, received false」で終わらせず、原因候補を示す。
    仮説カタログは、本セッションで人が実サイト検証で突き止めた実在の原因
    （既存値連結・ロケール書式・オーバーレイ遮断・条件付きdisabled・
    兄弟項目の制約違反）を知識化したもの。
    """
    from web.services import failure_hypothesis

    qa = _job_out(job) / job.domain / "qa_process"
    try:
        report = _read_json_file(qa / "playwright_report.json") or {}
        failures = [t for t in (report.get("tests") or []) if t.get("status") == "failed"]
        if not failures:
            return
        result = failure_hypothesis.triage(failures)
        (qa / "failure_hypotheses.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        job.outputs["failure_hypotheses"] = str((qa / "failure_hypotheses.json").resolve())
        explained = len(result["triaged"])
        unexplained = result["unexplained_count"]
        job.add_log(
            f"失敗の原因特定: {explained}件に原因候補を提示、{unexplained}件は未特定"
            "（未特定＝原因が無いという意味ではありません）"
        )
    except Exception as exc:  # 付加価値であり、本体結果を壊さない
        job.add_log(f"失敗の原因特定に失敗しました（実行結果は保持）: {exc}")


def _read_json_file(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _run_mutation_self_check(job: AutoRunJob, spec_path: Path, spec_dir: Path) -> None:
    """生成したテストが実際に欠陥を検出できるかを自己検証する（ミューテーションテスト）。

    対象サイトへは一切アクセスしない（page.route で全リクエストをローカルの
    壊れた応答に差し替える）。以前は、生成テストが expect(body).toBeVisible() のみで
    実質的な検証をしておらず、対象を完全に破壊してもテストが全件PASSする
    （ミューテーションスコア0%）欠陥を、人が別途スクリプトを書いて初めて発見していた。
    この自己検証により、AutoRun自身がそれを毎回の実行で確認する。
    """
    from web.services.mutation_verifier import run_self_check

    job.add_log("自己検証（ミューテーションテスト）を実行しています…")
    try:
        result = run_self_check(spec_path, spec_dir, add_log=job.add_log)
    except Exception as exc:
        job.add_log(f"自己検証を実行できませんでした: {exc}")
        return

    result_path = spec_dir / "mutation_verification.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if not result.get("applicable", True):
        job.add_log(f"自己検証: {result.get('note', '対象がありません')}")
        return
    if not result.get("ok"):
        job.add_log(f"自己検証を実行できませんでした: {result.get('error', '')}")
        return

    score = result.get("score", 0)
    survivor_count = result.get("survivor_count", 0)
    if survivor_count:
        job.add_log(
            f"自己検証: スコア {score}%（{survivor_count}件が、対象を破壊しても"
            "合格してしまう弱いテストとして検出されました。承認前にご確認ください）"
        )
    else:
        job.add_log(f"自己検証: スコア {score}%（全テストが対象の破壊を正しく検出）")


def _publish_playwright_stage(job: AutoRunJob, spec_dir: Path) -> None:
    """段階8（Playwright 自動化）の内容を生成して保存する。

    生成結果を人が確認できるようにするため、関門2で待つ前に用意しておく。
    自己検証（ミューテーションテスト）の結果があれば、承認前に見える形で提示する。
    """
    from dataclasses import replace

    from autorun.stages import STAGE_PLAYWRIGHT, Observation, Pipeline, StageItem, build_stage

    stages_path = spec_dir / "stages.json"
    if not stages_path.is_file():
        return
    try:
        pipeline = Pipeline.from_dict(json.loads(stages_path.read_text(encoding="utf-8")))
        coverage_path = spec_dir / "automation_coverage.json"
        automation = (
            json.loads(coverage_path.read_text(encoding="utf-8"))
            if coverage_path.is_file()
            else None
        )
        stage = build_stage(STAGE_PLAYWRIGHT, Observation(), pipeline, automation)

        mutation_path = spec_dir / "mutation_verification.json"
        if mutation_path.is_file():
            mutation = json.loads(mutation_path.read_text(encoding="utf-8"))
            if mutation.get("applicable", True) and mutation.get("ok"):
                score = mutation.get("score", 0)
                survivors = mutation.get("survivors") or []
                detail = (
                    f"対象を完全に破壊しても検出できるかを自己検証しました。\n"
                    f"スコア: {score}%（{mutation.get('detected', 0)}"
                    f"/{mutation.get('total', 0)}件が正しく検出）"
                )
                if survivors:
                    listed = "\n".join(f"・{title}" for title in survivors[:20])
                    detail += (
                        f"\n\n以下 {len(survivors)} 件は、対象を破壊しても合格して"
                        f"しまう弱いテストです。承認前にご確認ください。\n{listed}"
                    )
                mutation_item = StageItem(
                    item_id="pw-self-check",
                    title=f"自己検証（ミューテーションテスト）: {score}%",
                    detail=detail,
                    assumed=bool(survivors),
                )
                stage = replace(stage, items=stage.items + (mutation_item,))

        pipeline = pipeline.replaced(stage).recorded(
            "generate", STAGE_PLAYWRIGHT, f"{len(stage.items)}項目を生成"
        )
        # 段階8も、実行条件を確定済みならその確定に含める。
        # ここだけ別経路で生成しているため、承認が反映されず
        # 「承認済み 7 / 8」と表示される食い違いが残っていた。
        if job.stages_all_released:
            from autorun.stages import STATUS_APPROVED

            pipeline = pipeline.replaced(
                pipeline.get(STAGE_PLAYWRIGHT).with_status(STATUS_APPROVED)
            ).recorded("approve", STAGE_PLAYWRIGHT, "実行条件の確定により承認", "system")
        stages_path.write_text(
            json.dumps(pipeline.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        job.add_log(f"段階8の内容を用意できませんでした: {exc}")


def _execute_tests(job: AutoRunJob) -> None:
    if job._cancelled:
        return
    job.status = "running_tests"
    job.step_label = "Playwright テストを実行中"
    job.add_log("Playwright テスト実行を開始します…")

    spec_path_str = job.outputs.get("spec_ts", "")
    if not spec_path_str:
        _mark_job_failed(job, "spec.ts が見つかりません")
        return

    spec_path = Path(spec_path_str)
    report_dir = _job_out(job) / job.domain / "qa_process"

    # ポリシーに基づいてスクリプトを再生成（フィルター適用）
    filter_mode = job.run_policy.get("filter_mode", "all")
    per_test_timeout_sec = int(job.run_policy.get("per_test_timeout_sec", 30))
    device = job.run_policy.get("device", "pc")
    if device not in ("pc", "mobile"):
        device = "pc"
    # 出力形式（フラット / Page Object）。既定はフラットで後方互換。
    page_object = bool(job.run_policy.get("page_object", False))
    if filter_mode != "all" or page_object:
        candidates_path = _job_out(job) / job.domain / "qa_process" / candidate_filename(job.mode)
        if candidates_path.is_file():
            try:
                generate_spec_ts(
                    job.domain,
                    candidates_path,
                    spec_path,
                    filter_mode=filter_mode,
                    generate_page_object=page_object,
                    allow_submit=bool(job.run_policy.get("allow_submit")),
                )
                detail = f"フィルター '{filter_mode}'" + (
                    "・Page Object形式" if page_object else ""
                )
                job.add_log(f"{detail} を適用したスクリプトを再生成しました。")
            except Exception as exc:
                job.add_log(f"スクリプト再生成時エラー（元スクリプトで続行）: {exc}")

    try:
        # ローカル対象の許可はクロールと実行で揃える。実行側へ渡していなかったため、
        # 設定でローカルを許可していても全テストが private_address で拒否されていた。
        from crawler.url_safety import _local_targets_allowed
        from web.services.egress_gateway import EgressPolicy

        result = run_playwright(
            spec_path,
            report_dir,
            per_test_timeout_sec=per_test_timeout_sec,
            add_log=job.add_log,
            device=device,
            egress_policy=EgressPolicy(allow_local=_local_targets_allowed()),
            browser=str(job.run_policy.get("browser", "chromium")),
            # 中止からPlaywrightプロセスを終了させるための登録。
            # 未登録だと「中止する」を押しても最後の1件まで走り続ける。
            on_proc=job.register_proc,
        )
    except Exception as exc:
        _mark_job_failed(job, f"テスト実行エラー: {exc}")
        return
    finally:
        job._proc = None

    if job._cancelled:
        job.add_log(
            "中止により、テスト実行をここで打ち切りました（部分結果はファイルに残ります）。"
        )
        return

    job.test_results = result
    if (report_dir / "playwright_report.json").is_file():
        job.outputs["playwright_report_json"] = str(
            (report_dir / "playwright_report.json").resolve()
        )
    # 既定は自前の日本語サマリレポート（非エンジニアにも読める・ライト基調）。
    # Playwright ネイティブ HTML レポート（英語・スクショ/トレース付き）は
    # 開発者向けの副導線として playwright_native_html に別キーで残す（R3-03/04/05）。
    ja_report = report_dir / "playwright_report.html"
    native_report = report_dir / "playwright-report" / "index.html"
    if ja_report.is_file():
        job.outputs["playwright_report_html"] = str(ja_report.resolve())
    if native_report.is_file():
        job.outputs["playwright_native_html"] = str(native_report.resolve())

    passed = result.get("passed", 0)
    failed = result.get("failed", 0)
    total = result.get("total", 0)
    result_error = result.get("error", "")
    interrupted = bool(result.get("interrupted"))

    if result_error or interrupted:
        # evidence-only: 実行が異常終了（解析失敗・タイムアウト中断・未セットアップ等）した
        # 場合に「完了」を偽装しない。0/0/0 を無言で成功扱いにしていた過去の実装が、
        # AutoRun で188件承認・実行したのに結果が全件0で表示される致命的UX破綻の原因だった。
        if interrupted and total > 0:
            job.add_log(
                f"テスト実行が中断されました（部分結果を回収）: "
                f"PASS={passed} FAIL={failed} TOTAL={total}"
            )
        else:
            job.add_log(f"テスト実行が異常終了しました: {result_error or '中断されました'}")
        _mark_job_failed(job, result_error or "テスト実行が中断されました（部分結果なし）")
        _update_failure_classification(job, result)
        # 中断でも「どこまで実行したか」は検収上の証跡になるため生成する。
        attach_evidence_pack(job, _job_out(job))
        return

    job.status = "complete"
    job.step_label = "完了"
    job.finished_at = _now_iso()
    job.add_log(f"テスト実行完了: PASS={passed} FAIL={failed} TOTAL={total}")
    _update_failure_classification(job, result)
    attach_evidence_pack(job, _job_out(job))
    _record_autorun_usage_safely(job)


# ─────────────────────────── ユーティリティ ───────────────────────────


def _update_failure_classification(
    job: AutoRunJob,
    result: dict[str, Any] | None = None,
) -> None:
    """AutoRunの失敗要因をUI表示用に分類して保存する。"""
    result = result or {}
    failures: list[dict[str, Any]] = []
    for idx, test in enumerate(result.get("tests") or [], start=1):
        if test.get("status") != "failed":
            continue
        failures.append(
            {
                "test_id": test.get("id") or test.get("title") or f"TC{idx:03d}",
                "status": "failed",
                "error": test.get("error")
                or result.get("error")
                or result.get("stderr_snippet", ""),
            }
        )

    if not failures and (result.get("error") or job.error):
        failures.append(
            {
                "test_id": "AutoRun",
                "status": "failed",
                "error": result.get("error") or job.error,
            }
        )

    if not failures:
        job.failure_classifications = []
        job.failure_summary = {}
        return

    classifications = classify_failures(failures)
    job.failure_classifications = [asdict(item) for item in classifications]
    job.failure_summary = summarize_classifications(classifications)


def _mark_job_failed(job: AutoRunJob, error: str) -> None:
    # 中止済みを「失敗」で上書きしない。中止直後は子プロセスの異常終了が
    # 必ず観測されるため、ここで弾かないと停止表示が失敗表示へ化ける。
    if job._cancelled:
        return
    job.status = "failed"
    job.error = error
    job.finished_at = _now_iso()
    classification = classify_failure("AutoRun", error)
    job.failure_classifications = [asdict(classification)]
    job.failure_summary = summarize_classifications([classification])
    _record_autorun_usage_safely(job)


def _record_autorun_usage_safely(job: AutoRunJob) -> None:
    """成果物を実行回ごとに退避し、実行履歴へAutoRun実績を記録する。

    記録・退避の失敗は応答を妨げない（成果物は従来どおり output/<domain>/ に残る）。
    """
    try:
        from web.services.run_store import snapshot_run
        from web.services.usage_tracker import record_autorun

        test_results = job.test_results or {}
        out_root = _job_out(job)
        run_id = snapshot_run(
            out_root,
            job.domain,
            event="autorun",
            status=job.status,
            summary={
                "passed": int(test_results.get("passed", 0)),
                "failed": int(test_results.get("failed", 0)),
                "total": int(test_results.get("total", 0)),
                "duration_sec": job.elapsed_sec(),
            },
        )
        record_autorun(
            out_root,
            job.domain,
            status=job.status,
            passed=int(test_results.get("passed", 0)),
            failed=int(test_results.get("failed", 0)),
            total=int(test_results.get("total", 0)),
            duration_sec=job.elapsed_sec(),
            run_id=run_id or "",
        )
    except Exception:  # noqa: BLE001
        logger.warning("AutoRun実績の記録に失敗しました（応答は継続）", exc_info=True)


def _report_html_path(job: AutoRunJob) -> str:
    path_str = job.outputs.get("playwright_report_html", "")
    if path_str and Path(path_str).is_file():
        return path_str
    return job.outputs.get("qa_process_report", "")


def _now_iso() -> str:
    return datetime.now().isoformat()


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
