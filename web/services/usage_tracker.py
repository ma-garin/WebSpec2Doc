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

# 時間単価（円）: 削減額換算用。実際の単価は組織により異なるため設定可能。
DEFAULT_HOURLY_RATE_YEN = 5000.0

_ENV_MIN_SCREEN = "WEBSPEC2DOC_MIN_PER_SCREEN"
_ENV_MIN_CONDITION = "WEBSPEC2DOC_MIN_PER_CONDITION"
_ENV_MIN_DIFF = "WEBSPEC2DOC_MIN_PER_DIFF"
_ENV_HOURLY_RATE = "WEBSPEC2DOC_HOURLY_RATE_YEN"


@dataclass(frozen=True)
class SavingCoefficients:
    """削減工数の推定係数（分）と時間単価（円）。"""

    minutes_per_screen: float = MINUTES_PER_SCREEN_SPEC
    minutes_per_condition: float = MINUTES_PER_TEST_CONDITION
    minutes_per_diff: float = MINUTES_PER_DIFF_REVIEW
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
) -> Path | None:
    """利用実績を output_root/usage_log.jsonl に 1 行追記する。

    書き込み失敗はアプリ動作を妨げない（None を返す）。
    """
    entry = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "event": event,
        "domain": domain,
        "screen_count": int(screen_count),
        "test_condition_count": int(test_condition_count),
        "document_count": int(document_count),
        "diff_run": bool(diff_run),
    }
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

    saved_minutes = (
        total_screens * coef.minutes_per_screen
        + total_conditions * coef.minutes_per_condition
        + total_diffs * coef.minutes_per_diff
    )
    saved_hours = round(saved_minutes / 60.0, 1)
    saved_yen = int(saved_hours * coef.hourly_rate_yen)

    return {
        "total_crawls": total_crawls,
        "total_screens": total_screens,
        "total_test_conditions": total_conditions,
        "total_documents": total_documents,
        "total_diff_runs": total_diffs,
        "estimated_saved_hours": saved_hours,
        "estimated_saved_yen": saved_yen,
        "coefficients": {
            "minutes_per_screen": coef.minutes_per_screen,
            "minutes_per_condition": coef.minutes_per_condition,
            "minutes_per_diff": coef.minutes_per_diff,
            "hourly_rate_yen": coef.hourly_rate_yen,
        },
        "disclaimer": (
            "削減工数・削減額は手作業時間の想定係数に基づく推定値です"
            "（実測ではありません）。係数は環境変数で調整できます。"
        ),
    }
