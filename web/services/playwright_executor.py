from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def run_playwright(spec_path: Path, output_dir: Path, timeout_sec: int = 300) -> dict[str, Any]:
    """
    npx playwright test でスペックを実行し、結果を返す。

    playwright / npx がない環境では即座に skip 結果を返す。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    json_report_path = output_dir / "playwright_report.json"
    html_report_path = output_dir / "playwright_report.html"

    if not _playwright_available():
        return _unavailable_result(spec_path, json_report_path, html_report_path)

    cmd = [
        "npx",
        "playwright",
        "test",
        str(spec_path),
        "--reporter=json",
        f"--output={output_dir / 'artifacts'}",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=str(spec_path.parent.parent),
        )
    except subprocess.TimeoutExpired:
        return _error_result("タイムアウト", json_report_path, html_report_path)
    except Exception as exc:
        return _error_result(str(exc), json_report_path, html_report_path)

    raw_json: dict[str, Any] = {}
    try:
        raw_json = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        pass

    result = _parse_results(raw_json, proc.stdout, proc.stderr, proc.returncode)
    json_report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    html_report_path.write_text(_build_html_report(result), encoding="utf-8")
    return result


def _playwright_available() -> bool:
    if not shutil.which("npx"):
        return False
    try:
        result = subprocess.run(
            ["node", "-e", "require.resolve('@playwright/test')"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _parse_results(
    raw: dict[str, Any], stdout: str, stderr: str, returncode: int
) -> dict[str, Any]:
    suites: list[dict[str, Any]] = raw.get("suites") or []
    stats = raw.get("stats") or {}

    tests: list[dict[str, Any]] = []
    for suite in suites:
        for spec in suite.get("specs") or []:
            for run in spec.get("tests") or []:
                status = _map_status(run.get("status", ""), run.get("results") or [])
                tests.append(
                    {
                        "title": spec.get("title", ""),
                        "status": status,
                        "duration_ms": sum(
                            (r.get("duration") or 0) for r in (run.get("results") or [])
                        ),
                        "error": _first_error(run.get("results") or []),
                    }
                )

    passed = sum(1 for t in tests if t["status"] == "passed")
    failed = sum(1 for t in tests if t["status"] == "failed")
    skipped = sum(1 for t in tests if t["status"] == "skipped")

    return {
        "ok": returncode == 0,
        "passed": passed or int(stats.get("expected", 0)),
        "failed": failed or int(stats.get("unexpected", 0)),
        "skipped": skipped or int(stats.get("skipped", 0)),
        "total": len(tests) or int(stats.get("total", 0)),
        "duration_ms": int(stats.get("duration", 0)),
        "tests": tests,
        "stdout": stdout[:4000] if stdout else "",
        "stderr": stderr[:2000] if stderr else "",
    }


def _map_status(raw_status: str, results: list[dict[str, Any]]) -> str:
    if raw_status in ("passed", "expected"):
        return "passed"
    if raw_status in ("failed", "unexpected"):
        return "failed"
    if raw_status in ("skipped", "pending"):
        return "skipped"
    for r in results:
        if r.get("status") in ("passed", "expected"):
            return "passed"
        if r.get("status") in ("failed", "unexpected"):
            return "failed"
    return raw_status or "unknown"


def _first_error(results: list[dict[str, Any]]) -> str:
    for r in results:
        for err in r.get("errors") or []:
            msg = err.get("message") or err.get("value") or ""
            if msg:
                return str(msg)[:400]
    return ""


def _unavailable_result(
    spec_path: Path, json_path: Path, html_path: Path
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "total": 0,
        "duration_ms": 0,
        "tests": [],
        "error": "npx / Playwright が見つかりません。`npm install -D @playwright/test && npx playwright install` を実行してください。",
        "unavailable": True,
    }
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_build_html_report(result), encoding="utf-8")
    return result


def _error_result(
    error: str, json_path: Path, html_path: Path
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "total": 0,
        "duration_ms": 0,
        "tests": [],
        "error": error,
    }
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_build_html_report(result), encoding="utf-8")
    return result


def _build_html_report(result: dict[str, Any]) -> str:
    import html as html_mod

    status_color = "#16a34a" if result.get("ok") else "#dc2626"
    status_text = "PASS" if result.get("ok") else "FAIL"
    error_section = ""
    if result.get("error"):
        error_section = f'<div class="err"><strong>エラー:</strong> {html_mod.escape(str(result["error"]))}</div>'

    rows = "".join(
        "<tr class='{cls}'><td>{title}</td><td>{status}</td><td>{dur}ms</td><td>{err}</td></tr>".format(
            cls="pass" if t["status"] == "passed" else ("skip" if t["status"] == "skipped" else "fail"),
            title=html_mod.escape(str(t.get("title", ""))),
            status=html_mod.escape(str(t.get("status", ""))),
            dur=t.get("duration_ms", 0),
            err=html_mod.escape(str(t.get("error") or "")[:120]),
        )
        for t in result.get("tests", [])
    )

    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>Playwright 実行レポート</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:28px;color:#111827}}
.badge{{display:inline-block;padding:4px 14px;border-radius:20px;font-weight:700;color:#fff;background:{status_color};font-size:18px}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}}
.card{{border:1px solid #e5e7eb;border-radius:8px;padding:12px;text-align:center}}
.num{{font-size:28px;font-weight:800}}
table{{border-collapse:collapse;width:100%;margin-top:14px}}
td,th{{border:1px solid #e5e7eb;padding:8px;font-size:13px;vertical-align:top}}
th{{background:#f1f5f9}}
tr.pass td:nth-child(2){{color:#16a34a;font-weight:600}}
tr.fail td:nth-child(2){{color:#dc2626;font-weight:600}}
tr.skip td:nth-child(2){{color:#9ca3af}}
.err{{background:#fef2f2;border:1px solid #fecaca;border-radius:6px;padding:12px;margin:14px 0;color:#dc2626;font-size:13px}}
pre{{background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;padding:12px;font-size:11px;white-space:pre-wrap;overflow-x:auto}}
</style></head>
<body>
<h1>Playwright 実行レポート</h1>
<span class="badge">{status_text}</span>
<div class="cards">
  <div class="card"><div class="num" style="color:#16a34a">{result.get('passed',0)}</div><div>PASS</div></div>
  <div class="card"><div class="num" style="color:#dc2626">{result.get('failed',0)}</div><div>FAIL</div></div>
  <div class="card"><div class="num" style="color:#9ca3af">{result.get('skipped',0)}</div><div>SKIP</div></div>
  <div class="card"><div class="num">{result.get('total',0)}</div><div>TOTAL</div></div>
</div>
{error_section}
<table><thead><tr><th>テスト</th><th>結果</th><th>時間</th><th>エラー</th></tr></thead><tbody>{rows}</tbody></table>
{"<h2>stdout</h2><pre>" + html_mod.escape(result.get("stdout","")[:3000]) + "</pre>" if result.get("stdout") else ""}
{"<h2>stderr</h2><pre>" + html_mod.escape(result.get("stderr","")[:2000]) + "</pre>" if result.get("stderr") else ""}
</body></html>"""
