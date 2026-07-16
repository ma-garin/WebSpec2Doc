"""利用実績の記録と削減工数（ROI）の集計。

クロール・文書生成・AutoRun 実行のたびに 1 行 JSON を追記し、
そこから「手作業なら何時間かかったか」を係数ベースで推定する。
係数は evidence-only 原則（quality/feature_contracts）に従い明示・設定可能とし、
推定値であることを明記して出力する。
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

USAGE_LOG_FILE_NAME = "usage_log.jsonl"

# ---- 削減工数の推定係数（1件あたりの手作業想定・分）----
# 実測ではなく業務想定に基づく推定値。環境変数で上書き可能（脚注で明示する）。
MINUTES_PER_SCREEN_SPEC = 45.0  # 画面仕様1枚を手作業で起こす想定
MINUTES_PER_TEST_CONDITION = 10.0  # テスト条件1件を手作業で設計する想定
MINUTES_PER_DIFF_REVIEW = 30.0  # 仕様差分1回を手作業で突き合わせる想定
MINUTES_PER_COMPARE_SCREEN = 20.0  # 現新比較: 画面ペア1組の手動突き合わせ想定
MINUTES_PER_UX_FINDING = 15.0  # UX レビュー: 所見1件の手動レビュー想定

# 時間単価（円）: 削減額換算用。実際の単価は組織により異なるため設定可能。
DEFAULT_HOURLY_RATE_YEN = 5000.0

_ENV_MIN_SCREEN = "WEBSPEC2DOC_MIN_PER_SCREEN"
_ENV_MIN_CONDITION = "WEBSPEC2DOC_MIN_PER_CONDITION"
_ENV_MIN_DIFF = "WEBSPEC2DOC_MIN_PER_DIFF"
_ENV_MIN_COMPARE_SCREEN = "WEBSPEC2DOC_MIN_PER_COMPARE_SCREEN"
_ENV_MIN_UX_FINDING = "WEBSPEC2DOC_MIN_PER_UX_FINDING"
_ENV_HOURLY_RATE = "WEBSPEC2DOC_HOURLY_RATE_YEN"

# usage_log.jsonl の新キー（compare_screen_count/finding_count）を書き込む対象イベント。
# CONVENTIONS §2 のオプトイン方針を usage_log にも適用し、既存イベント（crawl 等）の
# 行は従来どおり 6 キーのまま保つ（既存行との diff・後方互換を壊さない）。
_EVENT_COMPARISON = "comparison"
_EVENT_UX_REVIEW = "ux_review"
_EVENTS_WITH_EXTRA_KEYS = frozenset({_EVENT_COMPARISON, _EVENT_UX_REVIEW})


@dataclass(frozen=True)
class SavingCoefficients:
    """削減工数の推定係数（分）と時間単価（円）。"""

    minutes_per_screen: float = MINUTES_PER_SCREEN_SPEC
    minutes_per_condition: float = MINUTES_PER_TEST_CONDITION
    minutes_per_diff: float = MINUTES_PER_DIFF_REVIEW
    minutes_per_compare_screen: float = MINUTES_PER_COMPARE_SCREEN
    minutes_per_ux_finding: float = MINUTES_PER_UX_FINDING
    hourly_rate_yen: float = DEFAULT_HOURLY_RATE_YEN


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s の値が不正です（%r）。既定値 %s を使用します。", name, raw, default)
        return default
    return value if value >= 0 else default


def load_coefficients() -> SavingCoefficients:
    """環境変数を反映した係数を返す（未設定なら既定値）。"""
    return SavingCoefficients(
        minutes_per_screen=_env_float(_ENV_MIN_SCREEN, MINUTES_PER_SCREEN_SPEC),
        minutes_per_condition=_env_float(_ENV_MIN_CONDITION, MINUTES_PER_TEST_CONDITION),
        minutes_per_diff=_env_float(_ENV_MIN_DIFF, MINUTES_PER_DIFF_REVIEW),
        minutes_per_compare_screen=_env_float(_ENV_MIN_COMPARE_SCREEN, MINUTES_PER_COMPARE_SCREEN),
        minutes_per_ux_finding=_env_float(_ENV_MIN_UX_FINDING, MINUTES_PER_UX_FINDING),
        hourly_rate_yen=_env_float(_ENV_HOURLY_RATE, DEFAULT_HOURLY_RATE_YEN),
    )


def record_usage(
    output_root: Path,
    *,
    event: str,
    domain: str,
    screen_count: int = 0,
    test_condition_count: int = 0,
    document_count: int = 0,
    diff_run: bool = False,
    compare_screen_count: int = 0,
    finding_count: int = 0,
) -> Path | None:
    """利用実績を output_root/usage_log.jsonl に 1 行追記する。

    compare_screen_count / finding_count は現新比較（event="comparison"）・
    UX レビュー（event="ux_review"）専用の新キーで、該当イベントの時のみ
    JSONL 行に書き込む（オプトイン。既存イベントの行は従来どおり 6 キーのまま
    — CONVENTIONS §2 の方針を usage_log にも適用し、既存行との diff・
    後方互換を壊さない）。compare_screen_count は現新比較の画面ペア数、
    または UX レビューの対象画面数を表す（screen_count は crawl 専用のまま）。

    書き込み失敗はアプリ動作を妨げない（None を返す）。
    """
    entry: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "event": event,
        "domain": domain,
        "screen_count": int(screen_count),
        "test_condition_count": int(test_condition_count),
        "document_count": int(document_count),
        "diff_run": bool(diff_run),
    }
    if event in _EVENTS_WITH_EXTRA_KEYS:
        entry["compare_screen_count"] = int(compare_screen_count)
        entry["finding_count"] = int(finding_count)
    log_path = output_root / USAGE_LOG_FILE_NAME
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("利用実績の記録に失敗しました: %s (%s)", log_path, exc)
        return None
    return log_path


def record_crawl_from_report(
    output_root: Path,
    domain: str,
    *,
    diff_run: bool = False,
) -> Path | None:
    """クロール完了後、生成された report.json から実績を集計して記録する。

    report.json が無い場合は screen_count=0 で記録する（=クロール自体は計上）。
    """
    report_path = output_root / domain / "report.json"
    screen_count = 0
    condition_count = 0
    document_count = 0
    if report_path.is_file():
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("report.json の読み込みに失敗しました: %s (%s)", report_path, exc)
            data = {}
        screens = [s for s in data.get("screens", []) if s.get("is_canonical", True)]
        screen_count = data.get("meta", {}).get("screen_count", len(screens))
        condition_count = sum(
            len(field.get("test_conditions", []))
            for screen in screens
            for form in screen.get("forms", [])
            for field in form.get("fields", [])
        )
        # 生成された成果物ファイル数（report.html/json/spec.xlsx など）
        document_count = sum(
            1
            for name in ("report.html", "report.json", "spec.xlsx", "report.pdf", "screens.md")
            if (output_root / domain / name).is_file()
        )
    return record_usage(
        output_root,
        event="crawl",
        domain=domain,
        screen_count=screen_count,
        test_condition_count=condition_count,
        document_count=document_count,
        diff_run=diff_run,
    )


def record_comparison_from_report(
    output_root: Path,
    domain: str,
    comparison_json_path: Path,
) -> Path | None:
    """現新比較完了後、生成された comparison.json から実績を集計して記録する（AC-1）。

    comparison.json（generator.comparison_reporter.save_comparison_outputs の出力）が
    無い/壊れている場合は記録自体をスキップする（比較が実行されていない可能性が
    高く、実績を捏造しないため）。呼び出し側（route / 出力フェーズ）は
    ``web/routes/crawl.py::_record_usage_safely`` と同じベストエフォート方針で
    呼ぶこと（記録失敗はクロール/比較結果の配信を妨げない）。
    """
    if not comparison_json_path.is_file():
        logger.warning(
            "comparison.json が見つかりません（実績記録をスキップ）: %s", comparison_json_path
        )
        return None
    try:
        data = json.loads(comparison_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "comparison.json の読み込みに失敗しました（実績記録をスキップ）: %s (%s)",
            comparison_json_path,
            exc,
        )
        return None
    pair_count = len(data.get("pairs") or [])
    finding_count = len(data.get("findings") or [])
    return record_usage(
        output_root,
        event="comparison",
        domain=domain,
        compare_screen_count=pair_count,
        finding_count=finding_count,
    )


def record_ux_review_from_report(
    output_root: Path,
    domain: str,
    ux_review_json_path: Path,
) -> Path | None:
    """UX レビュー完了後、生成された ux_review.json から実績を集計して記録する（AC-2）。

    ux_review.json（generator.ux_reporter.save_ux_outputs の出力）が無い/壊れている
    場合は記録自体をスキップする。指摘数は axe 違反とニールセン所見の合計。
    """
    if not ux_review_json_path.is_file():
        logger.warning(
            "ux_review.json が見つかりません（実績記録をスキップ）: %s", ux_review_json_path
        )
        return None
    try:
        data = json.loads(ux_review_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "ux_review.json の読み込みに失敗しました（実績記録をスキップ）: %s (%s)",
            ux_review_json_path,
            exc,
        )
        return None
    screens = data.get("screens") or []
    screen_count = len(screens)
    finding_count = sum(
        len(screen.get("axe_violations") or []) + len(screen.get("ux_findings") or [])
        for screen in screens
    )
    return record_usage(
        output_root,
        event="ux_review",
        domain=domain,
        compare_screen_count=screen_count,
        finding_count=finding_count,
    )


def record_autorun(
    output_root: Path,
    domain: str,
    *,
    status: str,
    passed: int = 0,
    failed: int = 0,
    total: int = 0,
    duration_sec: int = 0,
) -> Path | None:
    """AutoRunの終端状態（complete/failed/cancelled）で実行結果を1行追記する。

    実行履歴（GET /api/history/runs）の一般化（R2-27）のため、AutoRun専用の
    キー（status/passed/failed/total/duration_sec）を持つ独立イベントとして記録する。
    書き込み失敗はAutoRunの完了応答を妨げない（None を返す）。
    """
    entry: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "event": "autorun",
        "domain": domain,
        "status": status,
        "passed": int(passed),
        "failed": int(failed),
        "total": int(total),
        "duration_sec": int(duration_sec),
    }
    log_path = output_root / USAGE_LOG_FILE_NAME
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("AutoRun実績の記録に失敗しました: %s (%s)", log_path, exc)
        return None
    return log_path


_RUN_TYPE_LABELS = {
    "crawl": "解析",
    "comparison": "現新比較",
    "ux_review": "UXレビュー",
    "autorun": "AutoRun",
    "schedule": "スケジュール",
}


def _existing_path(path: Path) -> str:
    return str(path.resolve()) if path.is_file() else ""


def _run_from_record(output_root: Path, record: dict) -> dict:
    """usage_log.jsonl の1行を実行履歴エントリへ正規化する。"""
    event = str(record.get("event", "crawl"))
    domain = str(record.get("domain", ""))
    domain_dir = output_root / domain
    if event == "autorun":
        status = str(record.get("status") or "complete")
        summary = {
            "passed": int(record.get("passed", 0)),
            "failed": int(record.get("failed", 0)),
            "total": int(record.get("total", 0)),
            "duration_sec": int(record.get("duration_sec", 0)),
        }
        link = _existing_path(domain_dir / "qa_process" / "playwright_report.html") or (
            _existing_path(domain_dir / "qa_process" / "qa_process_report.html")
        )
    elif event in ("comparison", "ux_review"):
        status = "complete"
        summary = {
            "compare_screen_count": int(record.get("compare_screen_count", 0)),
            "finding_count": int(record.get("finding_count", 0)),
        }
        filename = "comparison.html" if event == "comparison" else "ux_review.html"
        link = _existing_path(domain_dir / filename)
    else:
        status = "complete"
        summary = {
            "screen_count": int(record.get("screen_count", 0)),
            "test_condition_count": int(record.get("test_condition_count", 0)),
            "document_count": int(record.get("document_count", 0)),
        }
        link = _existing_path(domain_dir / "report.html")
    return {
        "type": event,
        "type_label": _RUN_TYPE_LABELS.get(event, event),
        "domain": domain,
        "timestamp": str(record.get("timestamp", "")),
        "status": status,
        "summary": summary,
        "link": link,
        "source": "log",
    }


def _run_from_job(job: dict) -> dict:
    """実行中（未終端）AutoRunジョブを実行履歴エントリへ正規化する。"""
    test_results = job.get("test_results") or {}
    return {
        "type": "autorun",
        "type_label": _RUN_TYPE_LABELS["autorun"],
        "domain": str(job.get("domain", "")),
        "timestamp": str(job.get("started_at", "")),
        "status": str(job.get("status", "")),
        "summary": {
            "passed": int(test_results.get("passed", 0)),
            "failed": int(test_results.get("failed", 0)),
            "total": int(test_results.get("total", 0)),
            "duration_sec": int(job.get("elapsed_sec", 0)),
        },
        "link": "",
        "source": "running",
        "job_id": str(job.get("job_id", "")),
    }


def _schedule_runs(output_root: Path) -> list[dict]:
    runs: list[dict] = []
    if not output_root.is_dir():
        return runs
    for domain_dir in output_root.iterdir():
        if (
            not domain_dir.is_dir()
            or domain_dir.name.startswith(".")
            or domain_dir.name == "tenants"
        ):
            continue
        history_path = domain_dir / "schedule_history.jsonl"
        if not history_path.is_file():
            continue
        recent: deque[dict] = deque(maxlen=100)
        try:
            with history_path.open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(record, dict):
                        recent.append(record)
        except OSError as exc:
            logger.warning("スケジュール履歴を読み込めませんでした: %s (%s)", history_path, exc)
            continue
        for record in recent:
            domain = str(record.get("domain") or domain_dir.name)
            runs.append(
                {
                    "type": "schedule",
                    "type_label": _RUN_TYPE_LABELS["schedule"],
                    "domain": domain,
                    "timestamp": str(record.get("started_at", "")),
                    "status": str(record.get("status", "failed")),
                    "summary": {
                        "attempts": int(record.get("attempts", 0)),
                        "duration_sec": float(record.get("duration_sec", 0)),
                        "error": str(record.get("error", "")),
                    },
                    "link": _existing_path(domain_dir / "report.html"),
                    "source": "schedule",
                    "run_id": str(record.get("run_id", "")),
                }
            )
    return runs


def build_run_history(output_root: Path, running_jobs: list[dict] | None = None) -> list[dict]:
    """usage_log.jsonl の実績と実行中ジョブをマージし、新しい順の実行履歴を返す。

    種別（crawl/comparison/ux_review/autorun）を問わず一般化して扱う（R2-27）。
    リンクはファイルの実在を確認できたものだけを含める（実在検証・捏造しない）。
    """
    runs = [_run_from_record(output_root, record) for record in load_usage(output_root)]
    runs.extend(_schedule_runs(output_root))
    for job in running_jobs or []:
        if str(job.get("status", "")) not in ("complete", "failed", "cancelled"):
            runs.append(_run_from_job(job))
    runs.sort(key=lambda run: str(run.get("timestamp", "")), reverse=True)
    return runs


def load_usage(output_root: Path) -> list[dict]:
    """usage_log.jsonl を読み込んでレコードのリストを返す（無ければ空）。"""
    log_path = output_root / USAGE_LOG_FILE_NAME
    if not log_path.is_file():
        return []
    records: list[dict] = []
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("利用実績ログの行を解釈できませんでした: %s", line[:80])
    except OSError as exc:
        logger.warning("利用実績ログの読み込みに失敗しました: %s (%s)", log_path, exc)
    return records


def summarize_usage(
    records: list[dict],
    coefficients: SavingCoefficients | None = None,
) -> dict:
    """利用実績から累計値と推定削減工数（時間・円）を集計して返す。"""
    coef = coefficients or load_coefficients()
    total_crawls = sum(1 for r in records if r.get("event") == "crawl")
    total_screens = sum(int(r.get("screen_count", 0)) for r in records)
    total_conditions = sum(int(r.get("test_condition_count", 0)) for r in records)
    total_documents = sum(int(r.get("document_count", 0)) for r in records)
    total_diffs = sum(1 for r in records if r.get("diff_run"))
    # comparison / ux_review 専用の新キー。旧形式の行（キー無し）は get の既定値 0 で
    # 例外なく集計され、既存イベントの集計値には一切影響しない（AC-3）。
    total_compare_screens = sum(int(r.get("compare_screen_count", 0)) for r in records)
    total_findings = sum(int(r.get("finding_count", 0)) for r in records)

    saved_minutes = (
        total_screens * coef.minutes_per_screen
        + total_conditions * coef.minutes_per_condition
        + total_diffs * coef.minutes_per_diff
        + total_compare_screens * coef.minutes_per_compare_screen
        + total_findings * coef.minutes_per_ux_finding
    )
    saved_hours = round(saved_minutes / 60.0, 1)
    saved_yen = int(saved_hours * coef.hourly_rate_yen)

    return {
        "total_crawls": total_crawls,
        "total_screens": total_screens,
        "total_test_conditions": total_conditions,
        "total_documents": total_documents,
        "total_diff_runs": total_diffs,
        "total_compare_screens": total_compare_screens,
        "total_findings": total_findings,
        "estimated_saved_hours": saved_hours,
        "estimated_saved_yen": saved_yen,
        "coefficients": {
            "minutes_per_screen": coef.minutes_per_screen,
            "minutes_per_condition": coef.minutes_per_condition,
            "minutes_per_diff": coef.minutes_per_diff,
            "minutes_per_compare_screen": coef.minutes_per_compare_screen,
            "minutes_per_ux_finding": coef.minutes_per_ux_finding,
            "hourly_rate_yen": coef.hourly_rate_yen,
        },
        "disclaimer": (
            "削減工数・削減額は手作業時間の想定係数に基づく推定値です"
            "（実測ではありません）。係数は環境変数で調整できます。"
        ),
    }
