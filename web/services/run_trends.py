"""実行回をまたいだ集計（パス率推移・フレーキー・自己修復）。

1 回の実行結果だけでは「そのテストが不安定なのか、今回だけ落ちたのか」が分からない。
Autify / MagicPod 相当の運用にするには、実行回を横断して次を出す必要がある。

- パス率の推移: 品質が上がっているのか下がっているのか
- フレーキーランキング: リトライで通ったテスト。放置すると結果全体が信用されなくなる
- 継続失敗ランキング: 何回連続で落ちているか。1 回目と 10 回目では意味が違う
- 自己修復ランキング: 第 1 候補が効かなくなったロケータ。画面変更の早期警報

読み取り専用。`web/services/run_store.py` が保存した実行回だけを見る。
実行回に結果ファイルが無い場合は、その回を「集計対象外」として数え、
0 件として混ぜない（0% と「データ無し」を同じに見せない）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from web.services import run_store

# 1 回の集計で読む実行回の上限。増やすほど傾向は見やすくなるが、
# 実行回ごとに JSON を 1 つ開くため、応答時間と釣り合う範囲に収める。
DEFAULT_LIMIT = 30
_REPORT_RELATIVE = "qa_process/playwright_report.json"


def _read_report(output_root: Path, domain: str, run_id: str) -> dict[str, Any] | None:
    path = run_store.artifact_file(output_root, domain, run_id, _REPORT_RELATIVE)
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _pass_rate(passed: int, total: int) -> float | None:
    # 総数 0 を 0% と表示すると「全部落ちた」に見える。分からないものは None。
    if total <= 0:
        return None
    return round(passed / total * 100, 1)


def collect(
    output_root: Path, domain: str, limit: int = DEFAULT_LIMIT
) -> dict[str, Any]:
    """実行回を新しい順に読み、傾向をまとめる。"""
    metas = run_store.list_runs(output_root, domain)[: max(1, limit)]

    trend: list[dict[str, Any]] = []
    # テスト名 -> 集計
    per_test: dict[str, dict[str, Any]] = {}
    # (第1候補, 実際に使われた候補) -> 件数
    healing: dict[tuple[str, str], dict[str, Any]] = {}
    skipped_runs: list[str] = []

    for meta in metas:
        run_id = str(meta.get("run_id", ""))
        report = _read_report(output_root, domain, run_id)
        if report is None:
            skipped_runs.append(run_id)
            continue

        total = int(report.get("total", 0) or 0)
        passed = int(report.get("passed", 0) or 0)
        failed = int(report.get("failed", 0) or 0)
        flaky = int(report.get("flaky", 0) or 0)
        trend.append(
            {
                "run_id": run_id,
                "at": meta.get("created_at") or meta.get("at") or "",
                "event": meta.get("event", ""),
                "total": total,
                "passed": passed,
                "failed": failed,
                "flaky": flaky,
                "pass_rate": _pass_rate(passed, total),
                "duration_ms": int(report.get("duration_ms", 0) or 0),
                "projects": report.get("projects") or [],
            }
        )

        for test in report.get("tests") or []:
            title = str(test.get("title", "")).strip()
            if not title:
                continue
            agg = per_test.setdefault(
                title,
                {
                    "title": title,
                    "runs_seen": 0,
                    "failed_runs": 0,
                    "flaky_runs": 0,
                    "consecutive_failures": 0,
                    "streak_open": True,
                    "last_error": "",
                    "last_run_id": "",
                },
            )
            agg["runs_seen"] += 1
            is_failed = test.get("status") == "failed"
            if is_failed:
                agg["failed_runs"] += 1
                if not agg["last_error"]:
                    agg["last_error"] = str(test.get("error", ""))[:300]
                    agg["last_run_id"] = run_id
            if test.get("flaky"):
                agg["flaky_runs"] += 1
                if not agg["last_error"]:
                    agg["last_error"] = str(test.get("flaky_error", ""))[:300]
                    agg["last_run_id"] = run_id
            # metas は新しい順。先頭から連続で落ちている間だけ連続失敗を伸ばす。
            if agg["streak_open"]:
                if is_failed:
                    agg["consecutive_failures"] += 1
                else:
                    agg["streak_open"] = False

        for record in (report.get("self_healing") or {}).get("records") or []:
            primary = str(record.get("primary", ""))
            used = str(record.get("used", ""))
            if not primary or not used:
                continue
            key = (primary, used)
            entry = healing.setdefault(
                key,
                {
                    "primary": primary,
                    "used": used,
                    "count": 0,
                    "fields": [],
                    "last_run_id": "",
                },
            )
            entry["count"] += 1
            name = str(record.get("name", ""))
            if name and name not in entry["fields"]:
                entry["fields"].append(name)
            if not entry["last_run_id"]:
                entry["last_run_id"] = run_id

    for agg in per_test.values():
        agg.pop("streak_open", None)
        seen = agg["runs_seen"] or 1
        agg["failure_rate"] = round(agg["failed_runs"] / seen * 100, 1)
        agg["flaky_rate"] = round(agg["flaky_runs"] / seen * 100, 1)

    flaky_ranking = sorted(
        (a for a in per_test.values() if a["flaky_runs"] > 0),
        key=lambda a: (-a["flaky_runs"], -a["flaky_rate"], a["title"]),
    )
    failing_ranking = sorted(
        (a for a in per_test.values() if a["failed_runs"] > 0),
        key=lambda a: (-a["consecutive_failures"], -a["failed_runs"], a["title"]),
    )
    healing_ranking = sorted(
        healing.values(), key=lambda h: (-h["count"], h["primary"])
    )

    return {
        "domain": domain,
        "runs_analyzed": len(trend),
        "runs_skipped": skipped_runs,
        "trend": trend,
        "summary": _summary(trend, flaky_ranking, failing_ranking, healing_ranking),
        "flaky_ranking": flaky_ranking[:50],
        "failing_ranking": failing_ranking[:50],
        "healing_ranking": healing_ranking[:50],
    }


def _summary(
    trend: list[dict[str, Any]],
    flaky_ranking: list[dict[str, Any]],
    failing_ranking: list[dict[str, Any]],
    healing_ranking: list[dict[str, Any]],
) -> dict[str, Any]:
    latest = trend[0] if trend else None
    previous = trend[1] if len(trend) > 1 else None
    delta = None
    if latest and previous:
        a, b = latest.get("pass_rate"), previous.get("pass_rate")
        if a is not None and b is not None:
            delta = round(a - b, 1)
    return {
        "latest_run_id": latest["run_id"] if latest else "",
        "latest_pass_rate": latest.get("pass_rate") if latest else None,
        "pass_rate_delta": delta,
        "unstable_tests": len(flaky_ranking),
        "persistently_failing": sum(
            1 for a in failing_ranking if a["consecutive_failures"] >= 2
        ),
        "healed_locators": len(healing_ranking),
    }
