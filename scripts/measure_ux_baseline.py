#!/usr/bin/env python3
"""UX ベースライン計測（P0-1）。

主利用者の中核ループ「URL 入力 → 解析 → 成果物 → 再解析」の所要時間を実測し、
改善施策の効果を後から比較できる基準値を残す。体感ではなく実測値のみを扱う。

使い方:
    # 事前にデモサイトを起動しておく
    venv/bin/python demo/demo_site.py --port 8767 &

    venv/bin/python scripts/measure_ux_baseline.py
    venv/bin/python scripts/measure_ux_baseline.py --runs 5 --markdown docs/design/baseline.md

計測対象:
    discover      画面解析（リンク探索のみ・スクリーンショットなし）
    crawl         全画面クロール（成果物生成まで）
    design_api    GET /api/test-design/by-screen（画面別設計の応答）

いずれも中央値を採る。1 回目はディスクキャッシュ等の影響を受けるため、
`--runs` は 3 以上を推奨する（既定 3）。
"""

from __future__ import annotations

import argparse
import json
import statistics

# CLI 自身を計測対象として起動するため subprocess は必須。
import subprocess  # nosec B404
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEMO_URL = "http://127.0.0.1:8767/index.html"
DEFAULT_APP_URL = "http://127.0.0.1:8765"
DEFAULT_RUNS = 3
SUBPROCESS_TIMEOUT_SEC = 300
HTTP_TIMEOUT_SEC = 30


@dataclass(frozen=True)
class Measurement:
    """1 指標の計測結果。"""

    name: str
    label: str
    samples: tuple[float, ...]
    detail: str

    @property
    def median_sec(self) -> float:
        return statistics.median(self.samples) if self.samples else 0.0

    @property
    def min_sec(self) -> float:
        return min(self.samples) if self.samples else 0.0

    @property
    def max_sec(self) -> float:
        return max(self.samples) if self.samples else 0.0


def _run_cli(args: list[str]) -> tuple[float, str]:
    """CLI を 1 回実行し、所要秒と stdout を返す。"""
    started = time.monotonic()
    # 引数は本スクリプト内で組み立てた固定値のみで、外部入力を渡さない。
    proc = subprocess.run(  # nosec B603
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SEC,
        check=False,
    )
    elapsed = time.monotonic() - started
    if proc.returncode != 0:
        raise RuntimeError(f"CLI が失敗しました（exit {proc.returncode}）: {proc.stderr[-400:]}")
    return elapsed, proc.stdout


def measure_discover(url: str, runs: int) -> Measurement:
    """画面解析（discover）の所要時間。"""
    samples: list[float] = []
    page_count = 0
    for _ in range(runs):
        elapsed, stdout = _run_cli(
            ["src/main.py", "--discover", "--url", url, "--depth", "2", "--max-pages", "30"]
        )
        samples.append(elapsed)
        try:
            page_count = len(json.loads(stdout or "{}").get("pages", []))
        except json.JSONDecodeError:
            page_count = 0
    return Measurement(
        name="discover",
        label="画面解析（discover）",
        samples=tuple(samples),
        detail=f"{page_count} 画面",
    )


def measure_crawl(url: str, runs: int, output_dir: Path) -> Measurement:
    """全画面クロール（成果物生成まで）の所要時間。"""
    samples: list[float] = []
    for _ in range(runs):
        elapsed, _ = _run_cli(
            [
                "src/main.py",
                "--url",
                url,
                "--depth",
                "2",
                "--max-pages",
                "30",
                "--output",
                str(output_dir),
            ]
        )
        samples.append(elapsed)
    return Measurement(
        name="crawl",
        label="全画面クロール（成果物生成まで）",
        samples=tuple(samples),
        detail=f"出力先 {output_dir.name}",
    )


def measure_design_api(app_url: str, domain: str, runs: int) -> Measurement:
    """画面別設計 API の応答時間。アプリ未起動なら空の計測を返す。"""
    endpoint = f"{app_url}/api/test-design/by-screen?domain={domain}"
    samples: list[float] = []
    screen_count = 0
    for _ in range(runs):
        started = time.monotonic()
        try:
            # 宛先は引数で与えたローカルのアプリ URL のみ。
            with urllib.request.urlopen(endpoint, timeout=HTTP_TIMEOUT_SEC) as res:  # nosec B310
                payload = json.loads(res.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            return Measurement(
                name="design_api",
                label="画面別設計 API",
                samples=(),
                detail=f"未計測（アプリ未起動または未解析: {type(exc).__name__}）",
            )
        samples.append(time.monotonic() - started)
        screen_count = len(payload.get("screens", []))
    return Measurement(
        name="design_api",
        label="画面別設計 API",
        samples=tuple(samples),
        detail=f"{screen_count} 画面",
    )


def _format_markdown(measurements: list[Measurement], runs: int, url: str) -> str:
    lines = [
        "# UX ベースライン実測（P0-1）",
        "",
        f"- 対象: `{url}`",
        f"- 試行回数: {runs} 回（中央値を基準値とする）",
        "- 体感ではなく実測値のみ。改善施策の前後比較に用いる。",
        "",
        "| 指標 | 中央値 | 最小 | 最大 | 補足 |",
        "|---|---|---|---|---|",
    ]
    for m in measurements:
        if not m.samples:
            lines.append(f"| {m.label} | 未計測 | — | — | {m.detail} |")
            continue
        lines.append(
            f"| {m.label} | **{m.median_sec:.2f} 秒** | {m.min_sec:.2f} 秒 "
            f"| {m.max_sec:.2f} 秒 | {m.detail} |"
        )
    lines.extend(["", "## 生データ（秒）", ""])
    for m in measurements:
        raw = ", ".join(f"{s:.2f}" for s in m.samples) if m.samples else "（なし）"
        lines.append(f"- {m.label}: {raw}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="UX ベースラインを実測する（P0-1）")
    parser.add_argument("--url", default=DEFAULT_DEMO_URL, help="計測対象のデモサイト URL")
    parser.add_argument("--app-url", default=DEFAULT_APP_URL, help="本体アプリの URL")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help="試行回数（既定 3）")
    parser.add_argument("--markdown", type=Path, help="結果を Markdown で書き出すパス")
    parser.add_argument(
        "--skip-crawl",
        action="store_true",
        help="全画面クロールの計測を省く（時間がかかるため）",
    )
    args = parser.parse_args()

    if args.runs < 1:
        print("--runs は 1 以上を指定してください", file=sys.stderr)
        return 2

    domain = args.url.split("//", 1)[-1].split("/", 1)[0]
    output_dir = REPO_ROOT / "output" / domain

    measurements = [measure_discover(args.url, args.runs)]
    if not args.skip_crawl:
        measurements.append(measure_crawl(args.url, args.runs, output_dir))
    measurements.append(measure_design_api(args.app_url, domain, args.runs))

    report = _format_markdown(measurements, args.runs, args.url)
    print(report)
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(report, encoding="utf-8")
        print(f"書き出しました: {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
