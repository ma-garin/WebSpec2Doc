"""利用ガバナンス: レートリミット・月次クォータ・同時実行数制限・プラン。

商用/共有サーバ運用で「1テナントの暴走が全体を潰す・コストが青天井になる」
ことを防ぐ。認証が無効なローカル単独利用では一切制限しない。

制限の解決順序: プラン既定値 → テナント個別上書き（tenants.limits_json）
→ 環境変数によるインスタンス全体の上書き。値 0 は「無制限」を意味する。

レートリミットはプロセス内トークンバケット（現行はFlask単一プロセス運用の
ため十分。マルチワーカー化する際は共有ストアへの置換が必要）。
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

# プラン既定値。0 は無制限。
PLAN_DEFAULTS: dict[str, dict[str, int]] = {
    "standard": {"rate_per_minute": 120, "monthly_crawls": 100, "concurrent_jobs": 2},
    "pro": {"rate_per_minute": 300, "monthly_crawls": 1000, "concurrent_jobs": 5},
    "unlimited": {"rate_per_minute": 0, "monthly_crawls": 0, "concurrent_jobs": 0},
}
DEFAULT_PLAN = "standard"

# 環境変数によるインスタンス全体上書き（未設定ならプラン値を使う）
_ENV_OVERRIDES = {
    "rate_per_minute": "WEBSPEC2DOC_RATE_PER_MINUTE",
    "monthly_crawls": "WEBSPEC2DOC_MONTHLY_CRAWLS",
    "concurrent_jobs": "WEBSPEC2DOC_CONCURRENT_JOBS",
}

# クォータ集計の対象イベント（usage_log.jsonl の event キー）
_QUOTA_EVENTS = frozenset({"crawl", "autorun"})

# AutoRun ジョブのうち「実行スロットを消費している」状態。
# awaiting_approval は人の承認待ちでリソースを使わないため除外する。
_ACTIVE_AUTORUN_STATUSES = frozenset(
    {
        "discovering",
        "awaiting_input",
        "crawling",
        "generating_qa",
        "generating_scripts",
        "running_tests",
    }
)
_ACTIVE_CRAWLJOB_STATUSES = frozenset({"queued", "running"})


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        return None


def effective_limits(tenant: dict | None) -> dict[str, int]:
    """テナントの実効上限を返す。テナント無し（共有/ローカル）はプラン既定を使う。"""
    plan = str((tenant or {}).get("plan") or DEFAULT_PLAN)
    limits = dict(PLAN_DEFAULTS.get(plan, PLAN_DEFAULTS[DEFAULT_PLAN]))
    raw_overrides = (tenant or {}).get("limits_json") or "{}"
    try:
        overrides = json.loads(raw_overrides)
    except (TypeError, ValueError):
        overrides = {}
    for key in limits:
        if isinstance(overrides.get(key), int) and overrides[key] >= 0:
            limits[key] = overrides[key]
        env_value = _env_int(_ENV_OVERRIDES[key])
        if env_value is not None:
            limits[key] = env_value
    limits["plan"] = plan  # type: ignore[assignment]
    return limits


# --- レートリミット（トークンバケット） ---------------------------------


class RateLimiter:
    """プロセス内トークンバケット。key（ユーザーID等）ごとに毎分 limit 回まで。"""

    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_ts)
        self._lock = threading.Lock()

    def check(self, key: str, per_minute: int) -> float | None:
        """許可なら None、拒否なら再試行までの秒数を返す。per_minute=0 は無制限。"""
        if per_minute <= 0 or not key:
            return None
        now = time.monotonic()
        rate = per_minute / 60.0
        with self._lock:
            tokens, last = self._buckets.get(key, (float(per_minute), now))
            tokens = min(float(per_minute), tokens + (now - last) * rate)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                return None
            self._buckets[key] = (tokens, now)
            return max(0.5, (1.0 - tokens) / rate)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


rate_limiter = RateLimiter()


# --- 月次クォータ ---------------------------------------------------------


def monthly_crawl_usage(output_root: Path) -> int:
    """当月に成功したクロール/AutoRun実行数を usage_log.jsonl から数える。

    実行実績は成功時のみ記録されるため、失敗はクォータを消費しない（利用者に
    寛容な方向に倒す）。
    """
    from web.services.usage_tracker import load_usage

    month_prefix = datetime.now(UTC).strftime("%Y-%m")
    count = 0
    for record in load_usage(output_root):
        if str(record.get("event", "")) not in _QUOTA_EVENTS:
            continue
        if str(record.get("timestamp", "")).startswith(month_prefix):
            count += 1
    return count


# --- 同時実行数 -----------------------------------------------------------

# /run（ストリーミングクロール）はジョブレジストリを持たないため、ここで追跡する
_STREAM_CRAWLS: dict[str, str] = {}  # run_id -> str(output_dir)
_STREAM_LOCK = threading.Lock()


def register_stream_crawl(run_id: str, output_dir: Path) -> None:
    with _STREAM_LOCK:
        _STREAM_CRAWLS[run_id] = str(output_dir)


def unregister_stream_crawl(run_id: str) -> None:
    with _STREAM_LOCK:
        _STREAM_CRAWLS.pop(run_id, None)


def running_jobs_count(output_dir: Path) -> int:
    """このテナント出力先で実行中のジョブ数（AutoRun + REST + ストリーミング）。"""
    target = str(output_dir)
    count = 0
    try:
        from web.routes.auto_run import _JOBS as autorun_jobs
        from web.routes.auto_run import _JOBS_LOCK as autorun_lock

        with autorun_lock:
            for job in autorun_jobs.values():
                job_dir = getattr(job, "_output_dir", None)
                if job.status in _ACTIVE_AUTORUN_STATUSES and str(job_dir or "output") == target:
                    count += 1
    except Exception:  # noqa: BLE001 - 集計失敗で本体を止めない
        pass
    try:
        from web.services.job_queue import _JOBS as crawl_jobs
        from web.services.job_queue import _JOBS_LOCK as crawl_lock

        with crawl_lock:
            for cjob in crawl_jobs.values():
                if cjob.status in _ACTIVE_CRAWLJOB_STATUSES and (
                    str(cjob.output_dir or "output") == target
                ):
                    count += 1
    except Exception:  # noqa: BLE001
        pass
    with _STREAM_LOCK:
        count += sum(1 for v in _STREAM_CRAWLS.values() if v == target)
    return count


# --- クロール起動時の統合チェック ------------------------------------------


def check_crawl_allowed(tenant: dict | None, output_dir: Path) -> tuple[bool, str, dict]:
    """クォータ・同時実行数を検査する。(許可, 拒否理由, 使用状況) を返す。

    認証が無効（テナント無しのローカル利用）の場合は常に許可する。
    """
    from web.auth import auth_enabled

    usage = usage_snapshot(tenant, output_dir)
    if not auth_enabled():
        return True, "", usage
    limits = usage["limits"]
    if limits["concurrent_jobs"] and usage["running_jobs"] >= limits["concurrent_jobs"]:
        return (
            False,
            f"同時実行数の上限（{limits['concurrent_jobs']}件）に達しています。"
            "実行中のジョブが完了してから再試行してください。",
            usage,
        )
    if limits["monthly_crawls"] and usage["monthly_crawls"] >= limits["monthly_crawls"]:
        return (
            False,
            f"今月のクロール実行数の上限（{limits['monthly_crawls']}回）に達しています。"
            "プランの見直しか翌月までお待ちください。",
            usage,
        )
    return True, "", usage


def usage_snapshot(tenant: dict | None, output_dir: Path) -> dict:
    """アカウント画面等に表示する使用量サマリー。"""
    return {
        "limits": effective_limits(tenant),
        "monthly_crawls": monthly_crawl_usage(output_dir),
        "running_jobs": running_jobs_count(output_dir),
    }
