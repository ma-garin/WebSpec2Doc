"""CI パイプライン向けの合否判定（ゲート）。

利用者のプロジェクトの CI から 1 コマンドで叩き、仕様ドリフトとテスト結果を
しきい値と突き合わせて「通す／落とす」を決めるための純粋な判定モジュール。

ネットワークにも Flask にも触れない。読むのは `output/<domain>/` 配下の
成果物だけで、結果は終了コード・JUnit XML・Markdown サマリとして返す。

終了コードは CLI の契約に揃える。
    0   合格
    1   完了したが失格（ドリフト検出・テスト失敗）
    2   実行エラー（判定材料が無い等）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

try:  # CLI 経由（src/ を sys.path に入れて実行）
    from ci_drift import DRIFT_SUMMARY_FILE_NAME
except ImportError:  # パッケージとして読むとき
    from src.ci_drift import DRIFT_SUMMARY_FILE_NAME  # type: ignore[no-redef]

# 判定を厳しくする順。fail_on はこの並びの「その段以上」を失格とする。
SEVERITY_ORDER: tuple[str, ...] = ("info", "warning", "breaking")
FAIL_ON_CHOICES: tuple[str, ...] = ("none", "info", "warning", "breaking", "any")

# テスト結果 JSON の候補。実在を確認したのは先頭 2 つ（output/<domain>/testcases/）。
# 残りは別経路で置かれることがある名前で、無ければ黙って次を試す。
TEST_RESULT_CANDIDATES: tuple[str, ...] = (
    "testcases/run_result.json",
    "testcases/playwright_report.json",
    "test_results.json",
    "run_result.json",
    "qa_process/run_result.json",
)

_STATUS_PASSED = "passed"
_STATUS_FAILED = "failed"
_STATUS_SKIPPED = "skipped"
_REASON_UNAVAILABLE = "未取得"


@dataclass(frozen=True)
class GateThresholds:
    """CI で落とす条件。既定は「破壊的変更とテスト失敗だけ落とす」。"""

    fail_on: str = "breaking"
    max_failed_tests: int = 0
    max_added_pages: int = -1  # -1 は無制限
    max_removed_pages: int = -1  # -1 は無制限


@dataclass(frozen=True)
class GateResult:
    """判定結果。生成後は書き換えない（出力側は読むだけ）。"""

    passed: bool
    exit_code: int
    reasons: tuple[str, ...] = ()
    counts: dict = field(default_factory=dict)
    checks: tuple[dict, ...] = ()


# ────────────────────────────── 読み込み ──────────────────────────────


def _read_json(path: Path) -> dict | None:
    """壊れた JSON や読めないファイルは「無かった」として扱う。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_drift_summary(output_dir: Path, domain: str) -> dict | None:
    """`output/<domain>/drift_summary.json` を読む。無ければ None。"""
    path = Path(output_dir) / domain / DRIFT_SUMMARY_FILE_NAME
    if not path.is_file():
        return None
    return _read_json(path)


def load_test_results(output_dir: Path, domain: str) -> dict | None:
    """テスト結果 JSON を候補順に探す。見つからなければ None（エラーにしない）。

    候補の中身は 2 系統ある。
      * `{"summary": {"passed": .., "failed": ..}}`（run_result.json）
      * 直下に `passed` / `failed` を持つ（playwright_report.json）
    どちらも同じ形へ正規化して返す。
    """
    base = Path(output_dir) / domain
    for name in TEST_RESULT_CANDIDATES:
        path = base / name
        if not path.is_file():
            continue
        data = _read_json(path)
        if data is None:
            continue
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else data
        if not any(k in summary for k in ("passed", "failed", "total")):
            continue
        return {
            "source": str(path),
            "ran_at": data.get("ran_at", ""),
            "passed": _as_int(summary.get("passed")),
            "failed": _as_int(summary.get("failed")),
            "skipped": _as_int(summary.get("skipped")),
            "total": _as_int(summary.get("total")),
            "error": str(summary.get("error") or ""),
        }
    return None


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


# ────────────────────────────── 判定 ──────────────────────────────


def _check(name: str, status: str, reason: str, **extra: object) -> dict:
    return {"name": name, "status": status, "reason": reason, **extra}


def _drift_failed(severity: dict, has_changes: bool, fail_on: str) -> tuple[bool, str]:
    """fail_on としきい値の突き合わせ。落とす理由の文言も併せて返す。"""
    if fail_on == "any":
        return (bool(has_changes), "仕様に変更を検出しました（--fail-on any）")
    if fail_on not in SEVERITY_ORDER:
        return (False, "")
    watched = SEVERITY_ORDER[SEVERITY_ORDER.index(fail_on) :]
    total = sum(_as_int(severity.get(level)) for level in watched)
    detail = " / ".join(f"{level}={_as_int(severity.get(level))}" for level in watched)
    return (total > 0, f"重大度 {fail_on} 以上の変更を検出しました（{detail}）")


def _evaluate_drift(drift: dict | None, thresholds: GateThresholds) -> tuple[list[dict], list[str]]:
    """ドリフト側の check とリーズンを組み立てる。"""
    name = "spec_drift"
    if drift is None:
        return ([_check(name, _STATUS_SKIPPED, _REASON_UNAVAILABLE)], [])
    if thresholds.fail_on == "none":
        return ([_check(name, _STATUS_SKIPPED, "--fail-on none のため判定しません")], [])
    if bool(drift.get("first_run")):
        return (
            [_check(name, _STATUS_SKIPPED, "初回実行のため比較対象がありません")],
            [],
        )

    severity = drift.get("severity_counts") or {}
    failed, message = _drift_failed(severity, bool(drift.get("has_changes")), thresholds.fail_on)
    checks = [
        _check(
            name,
            _STATUS_FAILED if failed else _STATUS_PASSED,
            message if failed else f"--fail-on {thresholds.fail_on} のしきい値内です",
            severity_counts=dict(severity),
        )
    ]
    reasons = [message] if failed else []

    counts = drift.get("counts") or {}
    for key, limit, label in (
        ("added_pages", thresholds.max_added_pages, "追加画面"),
        ("removed_pages", thresholds.max_removed_pages, "削除画面"),
    ):
        if limit < 0:
            checks.append(_check(f"drift_{key}", _STATUS_SKIPPED, "上限を指定していません"))
            continue
        actual = _as_int(counts.get(key))
        over = actual > limit
        text = f"{label} {actual} 件（上限 {limit} 件）"
        checks.append(_check(f"drift_{key}", _STATUS_FAILED if over else _STATUS_PASSED, text))
        if over:
            reasons.append(text)
    return (checks, reasons)


def _evaluate_tests(tests: dict | None, thresholds: GateThresholds) -> tuple[list[dict], list[str]]:
    """テスト結果側の check とリーズンを組み立てる。"""
    name = "test_results"
    if tests is None:
        return ([_check(name, _STATUS_SKIPPED, _REASON_UNAVAILABLE)], [])
    failed = _as_int(tests.get("failed"))
    over = failed > thresholds.max_failed_tests
    text = (
        f"失敗 {failed} 件 / 全 {_as_int(tests.get('total'))} 件"
        f"（許容 {thresholds.max_failed_tests} 件）"
    )
    checks = [
        _check(
            name,
            _STATUS_FAILED if over else _STATUS_PASSED,
            text,
            source=tests.get("source", ""),
        )
    ]
    return (checks, [text] if over else [])


def evaluate(
    drift: dict | None, tests: dict | None, thresholds: GateThresholds
) -> GateResult:
    """ドリフトとテスト結果を突き合わせ、CI の合否を決める。

    判定に使えなかった項目は必ず `skipped` として checks に残す。黙って合格に
    すると「見ていない」と「問題なし」が CI 上で区別できなくなるため。
    """
    drift_checks, drift_reasons = _evaluate_drift(drift, thresholds)
    test_checks, test_reasons = _evaluate_tests(tests, thresholds)
    checks = tuple(drift_checks + test_checks)
    reasons = list(drift_reasons + test_reasons)

    counts: dict = {
        "drift": dict(drift.get("counts") or {}) if drift else {},
        "severity": dict(drift.get("severity_counts") or {}) if drift else {},
        "tests": {
            key: _as_int(tests.get(key)) for key in ("passed", "failed", "skipped", "total")
        }
        if tests
        else {},
        "checks_skipped": sum(1 for c in checks if c["status"] == _STATUS_SKIPPED),
    }

    if drift is None and tests is None:
        return GateResult(
            passed=False,
            exit_code=2,
            reasons=("判定材料がありません",),
            counts=counts,
            checks=checks,
        )
    if reasons:
        return GateResult(
            passed=False, exit_code=1, reasons=tuple(reasons), counts=counts, checks=checks
        )
    ok_reason = "しきい値を超える差分・失敗はありません"
    return GateResult(
        passed=True, exit_code=0, reasons=(ok_reason,), counts=counts, checks=checks
    )


# ────────────────────────────── 出力 ──────────────────────────────


def write_junit_xml(result: GateResult, path: Path, *, suite_name: str = "webspec2doc") -> None:
    """JUnit XML を書き出す。check 1 件が testcase 1 件に対応する。

    エスケープ漏れを避けるため、文字列連結ではなく ElementTree で組む。
    """
    checks = result.checks
    suite = ET.Element(
        "testsuite",
        {
            "name": suite_name,
            "tests": str(len(checks)),
            "failures": str(sum(1 for c in checks if c["status"] == _STATUS_FAILED)),
            "skipped": str(sum(1 for c in checks if c["status"] == _STATUS_SKIPPED)),
            "errors": "1" if result.exit_code == 2 else "0",
        },
    )
    for check in checks:
        case = ET.SubElement(
            suite, "testcase", {"classname": suite_name, "name": str(check.get("name", ""))}
        )
        reason = str(check.get("reason", ""))
        if check["status"] == _STATUS_FAILED:
            failure = ET.SubElement(case, "failure", {"message": reason})
            failure.text = reason
        elif check["status"] == _STATUS_SKIPPED:
            ET.SubElement(case, "skipped", {"message": reason})
    suites = ET.Element("testsuites", {"name": suite_name})
    suites.append(suite)

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suites).write(target, encoding="utf-8", xml_declaration=True)


def write_step_summary(result: GateResult, path: Path) -> None:
    """GitHub Actions の `$GITHUB_STEP_SUMMARY` へ Markdown を追記する。"""
    verdict = "PASS" if result.passed else "FAIL"
    lines = [
        "## WebSpec2Doc CI ゲート",
        "",
        f"- 判定: **{verdict}**（終了コード {result.exit_code}）",
        f"- 理由: {' / '.join(result.reasons) or '—'}",
        "",
        "| チェック | 状態 | 内容 |",
        "| --- | --- | --- |",
    ]
    lines += [
        f"| {check.get('name', '')} | {check.get('status', '')} | "
        f"{str(check.get('reason', '')).replace('|', '/')} |"
        for check in result.checks
    ]
    lines.append("")

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fp:
        fp.write("\n".join(lines) + "\n")
