#!/usr/bin/env python3
"""fetch 経路のエラー処理を静的に点検する（P0-3）。

通信は必ず失敗しうる。失敗したときに画面が黙って空のままになると、利用者は
「壊れた」のか「データが無い」のか判別できない。そこで `static/js/*.js` の
すべての `fetch(` について、次を機械的に確認する。

    1. 失敗を捕捉しているか          … 同じ関数内に catch / .catch がある
    2. 失敗が利用者に見えるか        … 捕捉した先で uiError / showToast /
                                       textContent 等の可視表示に落ちている

使い方:
    venv/bin/python scripts/check_fetch_error_handling.py
    venv/bin/python scripts/check_fetch_error_handling.py --markdown docs/design/x.md
    venv/bin/python scripts/check_fetch_error_handling.py --fail-on-missing

判定はヒューリスティックであり、構文解析ではない。誤判定を避けるため、
`# noqa: fetch-error` を含む行は「意図的に無視」として除外する。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JS_DIR = REPO_ROOT / "static" / "js"

# 捕捉の証跡
CATCH_PATTERN = re.compile(r"\bcatch\b|\.catch\s*\(")
# 利用者に見える形で失敗を伝えている証跡。
# アプリ固有のステータス表示関数（tcgSetStatus / setLoginStatus / _adminMessage 等）を
# 個別に列挙すると漏れるため、命名から役割を推定する一般パターンも併用する。
VISIBLE_PATTERNS = (
    re.compile(r"\buiError\s*\("),
    re.compile(r"\buiEmpty\s*\("),
    re.compile(r"\.textContent\s*="),
    re.compile(r"\.innerHTML\s*="),
    re.compile(r"\b\w*[Tt]oast\s*\("),
    re.compile(r"\b\w*[Ss]tatus\s*\("),
    re.compile(r"\b\w*(Message|Msg|message|msg)\s*\("),
    re.compile(r"\b\w*[Ee]rror\s*\("),
    re.compile(r"\balert\s*\("),
    re.compile(r"classList\.add\(['\"][^'\"]*error"),
)
# 意図的に無視する目印
IGNORE_MARKER = "noqa: fetch-error"
# 失敗処理を探す窓（行数）。catch は fetch より後ろに書かれるため後方を広く取る。
BACKWARD_LINES = 12
FORWARD_LINES = 45
# 関数の始まりらしき行（ブロック抽出のアンカー）
FUNCTION_START = re.compile(
    r"^\s*(async\s+)?function\b|^\s*(async\s+)?\w+\s*\([^)]*\)\s*\{|"
    r"=\s*(async\s+)?\([^)]*\)\s*=>\s*\{|=\s*(async\s+)?function\b"
)


@dataclass(frozen=True)
class FetchSite:
    """1 つの fetch 呼び出しとその周辺の判定結果。"""

    path: str
    line: int
    snippet: str
    has_catch: bool
    has_visible: bool
    ignored: bool

    @property
    def status(self) -> str:
        if self.ignored:
            return "ignored"
        if not self.has_catch:
            return "no_catch"
        if not self.has_visible:
            return "silent"
        return "ok"


def _block_bounds(lines: list[str], index: int) -> tuple[int, int]:
    """fetch の失敗処理が書かれうる範囲を返す（行番号は 0 始まり）。

    構文解析はしない。`try { await fetch(...) } catch {}` では catch が下に、
    `fetch().then().catch()` でも catch が下にあるため、**後方を広く**取る。
    関数の開始が近ければそこを起点にし、無ければ前方は狭く取る。
    """
    start = max(0, index - BACKWARD_LINES)
    for i in range(index, max(-1, index - BACKWARD_LINES), -1):
        if FUNCTION_START.search(lines[i]):
            start = i
            break
    return start, min(len(lines), index + FORWARD_LINES)


def scan_file(path: Path) -> list[FetchSite]:
    lines = path.read_text(encoding="utf-8").splitlines()
    sites: list[FetchSite] = []
    for index, line in enumerate(lines):
        if "fetch(" not in line:
            continue
        start, end = _block_bounds(lines, index)
        block = "\n".join(lines[start:end])
        sites.append(
            FetchSite(
                path=str(path.relative_to(REPO_ROOT)),
                line=index + 1,
                snippet=line.strip()[:88],
                has_catch=bool(CATCH_PATTERN.search(block)),
                has_visible=any(p.search(block) for p in VISIBLE_PATTERNS),
                # 行が長くなるのを避けて直前行に書けるよう、当該行と直前 2 行を見る
                ignored=any(IGNORE_MARKER in lines[k] for k in range(max(0, index - 2), index + 1)),
            )
        )
    return sites


def _format_markdown(sites: list[FetchSite]) -> str:
    counts = {
        key: sum(1 for s in sites if s.status == key)
        for key in ("ok", "silent", "no_catch", "ignored")
    }
    lines = [
        "# fetch 経路のエラー処理点検（P0-3）",
        "",
        f"- 対象: `static/js/*.js` の `fetch(` **{len(sites)} 経路**",
        "- 判定はヒューリスティック（構文解析ではない）。誤判定は "
        f"`{IGNORE_MARKER}` を行末に付けて除外できる。",
        "",
        "| 判定 | 件数 | 意味 |",
        "|---|---|---|",
        f"| ok | {counts['ok']} | 捕捉し、利用者に見える形で伝えている |",
        f"| silent | {counts['silent']} | 捕捉はするが画面に何も出さない |",
        f"| no_catch | {counts['no_catch']} | 捕捉していない（未処理の失敗） |",
        f"| ignored | {counts['ignored']} | 意図的に除外 |",
        "",
    ]
    for status, title in (
        ("no_catch", "## 捕捉していない経路"),
        ("silent", "## 捕捉するが画面に出ない経路"),
    ):
        target = [s for s in sites if s.status == status]
        lines.extend([title, ""])
        if not target:
            lines.extend(["（なし）", ""])
            continue
        lines.extend(["| 位置 | 呼び出し |", "|---|---|"])
        for s in target:
            lines.append(f"| `{s.path}:{s.line}` | `{s.snippet}` |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="fetch のエラー処理を点検する（P0-3）")
    parser.add_argument("--markdown", type=Path, help="結果を Markdown で書き出すパス")
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="no_catch / silent が 1 件でもあれば終了コード 1 を返す",
    )
    args = parser.parse_args()

    if not JS_DIR.is_dir():
        print(f"JS ディレクトリが見つかりません: {JS_DIR}", file=sys.stderr)
        return 2

    sites: list[FetchSite] = []
    for path in sorted(JS_DIR.glob("*.js")):
        sites.extend(scan_file(path))

    report = _format_markdown(sites)
    print(report)
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(report, encoding="utf-8")
        print(f"書き出しました: {args.markdown}")

    missing = [s for s in sites if s.status in ("no_catch", "silent")]
    if args.fail_on_missing and missing:
        print(f"エラー処理が不足している経路が {len(missing)} 件あります", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
