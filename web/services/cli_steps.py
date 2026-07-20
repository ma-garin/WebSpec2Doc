"""AutoRun の各工程を個別に CLI から実行するためのステップ関数群。

`--qa-process` / `--gen-spec` / `--run-tests` の実処理をここに集約する。
いずれも Flask リクエストコンテキスト外で呼ばれる前提で、出力先は
`web.services.qa.helpers.use_output_dir` の ContextVar で明示固定する。

前提: カレントディレクトリはリポジトリルート（`output/`・`output/.playwright_env`・
`instance/` 等が相対パスで解決されるため）。GUI が `src/main.py` を cwd=リポジトリ
ルートで subprocess 起動しているのと同じ条件。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

JSON_REPORT_FILE_NAME = "report.json"
QA_PROCESS_DIR = "qa_process"
SPEC_FILE_NAME = "autorun.spec.ts"


class CliStepError(RuntimeError):
    """CLI 工程の前提が満たされない場合に送出する（呼び出し側で exit 1）。"""


def run_qa_process(
    domain: str,
    output_dir: Path,
    *,
    viewpoint_set_id: str = "",
    viewpoint_version: int | None = None,
) -> dict[str, Path]:
    """クロール済み report.json から QA プロセス成果物一式を生成する。

    GUI の `_phase_generate_qa`（web/routes/auto_run.py）と同じ手順:
    観点スナップショットを固定 → report へ適用 → use_output_dir /
    use_viewpoint_snapshot の中で標準＋advanced成果物を生成する。
    """
    from web.routes.qa_process import (
        _generate_advanced_outputs,
        _generate_outputs,
        _load_report,
    )
    from web.services.qa.helpers import use_output_dir, use_viewpoint_snapshot
    from web.services.viewpoint_store import get_viewpoint_store

    report_path = output_dir / domain / JSON_REPORT_FILE_NAME
    report = _load_report(report_path)
    if report is None:
        raise CliStepError(
            f"クロール済みインベントリがありません: {report_path}"
            "（先に --format json でクロールしてください）"
        )

    store = get_viewpoint_store()
    selected = store.select_snapshot(
        {"url": f"https://{domain}"},
        set_id=viewpoint_set_id or None,
        version_number=int(viewpoint_version) if viewpoint_version else None,
    )
    applied = store.apply_snapshot_to_report(selected, report)

    snapshot_path = output_dir / domain / QA_PROCESS_DIR / "viewpoint_snapshot.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(applied, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    report_with_snapshot = report | {
        "viewpoint_snapshot": {key: value for key, value in applied.items() if key != "items"}
    }

    with use_output_dir(output_dir), use_viewpoint_snapshot(applied["items"]):
        outputs = _generate_outputs(domain, report_with_snapshot)
        outputs |= _generate_advanced_outputs(domain, report_with_snapshot)
    return outputs


def run_gen_spec(
    domain: str,
    output_dir: Path,
    *,
    mode: str = "url",
    filter_mode: str = "all",
    page_object: bool = False,
) -> Path:
    """QA 生成済みの候補 JSON から Playwright .spec.ts を生成する。"""
    from web.services.document_autorun import candidate_filename
    from web.services.spec_ts_generator import generate_spec_ts

    qa_dir = output_dir / domain / QA_PROCESS_DIR
    candidates_path = qa_dir / candidate_filename(mode)
    if not candidates_path.is_file():
        raise CliStepError(
            f"{candidates_path.name} が見つかりません: {candidates_path}"
            "（先に --qa-process を実行してください）"
        )
    spec_path = qa_dir / SPEC_FILE_NAME
    generate_spec_ts(
        domain,
        candidates_path,
        spec_path,
        filter_mode=filter_mode,
        generate_page_object=page_object,
    )
    return spec_path


def run_tests(
    domain: str,
    output_dir: Path,
    *,
    per_test_timeout_sec: int = 30,
    device: str = "pc",
    on_log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """生成済み .spec.ts を Playwright で実行して結果 dict を返す。

    Node/@playwright/test 環境（`output/.playwright_env`）とブラウザは
    playwright_executor が初回に自動導入する。npx/npm/playwright パッケージが
    前提。
    """
    from web.services.playwright_executor import run_playwright

    qa_dir = output_dir / domain / QA_PROCESS_DIR
    spec_path = qa_dir / SPEC_FILE_NAME
    if not spec_path.is_file():
        raise CliStepError(
            f"{SPEC_FILE_NAME} が見つかりません: {spec_path}"
            "（先に --gen-spec を実行してください）"
        )
    return run_playwright(
        spec_path,
        qa_dir,
        per_test_timeout_sec=per_test_timeout_sec,
        add_log=on_log,
        device=device,
    )
