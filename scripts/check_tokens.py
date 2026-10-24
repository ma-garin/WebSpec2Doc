#!/usr/bin/env python3
"""G-6 静的検査（仕様 §7.7）。ブラウザ不要。

使い方:
    venv/bin/python scripts/check_tokens.py                 # git diff origin/main の追加行
    venv/bin/python scripts/check_tokens.py --all a.css ...  # 指定ファイル全体
出力 `NG <ファイル>:<行>: 内容`。1 件でもあれば終了コード 1。static/tokens.css は除外。
"""
from __future__ import annotations

import re
import subprocess
import sys

EXCLUDE = ("static/tokens.css",)
RULES = (
    ("生の色", re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\(")),
    ("生の px", re.compile(r"(?:font-size|padding|margin|gap|border-radius)[a-z-]*\s*:[^;{}]*\b\d+(?:\.\d+)?px")),
    ("状態色トークンの文字色", re.compile(r"color\s*:\s*var\(\s*--color-(?:high|medium|warning|success|error|info|critical)\s*\)")),
)


def scan_line(text: str) -> list[str]:
    return [label for label, rx in RULES if rx.search(text)]


def _excluded(path: str) -> bool:
    return any(path.endswith(e) for e in EXCLUDE)


def scan_files(paths: list[str]) -> list[str]:
    out = []
    for p in paths:
        if _excluded(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    out += [f"NG {p}:{i}: {m}: {line.strip()[:100]}" for m in scan_line(line)]
        except OSError as e:
            out.append(f"NG {p}:0: 読めない: {e.strerror}")
    return out


def scan_diff() -> list[str]:
    r = subprocess.run(["git", "diff", "origin/main", "-U0", "--", "static/", "templates/"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return [f"NG -:0: git diff に失敗: {r.stderr.strip()[:100]}"]
    out, cur, ln = [], None, 0
    for raw in r.stdout.splitlines():
        if raw.startswith("+++ "):
            cur = raw[6:] if raw.startswith("+++ b/") else None
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            ln = int(m.group(1)) if m else 0
        elif raw.startswith("+") and cur and not _excluded(cur):
            out += [f"NG {cur}:{ln}: {m}: {raw[1:].strip()[:100]}" for m in scan_line(raw[1:])]
            ln += 1
    return out


def main() -> int:
    a = sys.argv[1:]
    ngs = scan_files(a[a.index("--all") + 1:]) if "--all" in a else scan_diff()
    for n in ngs:
        print(n)
    print(f"check_tokens: {len(ngs)} 件")
    return 1 if ngs else 0


if __name__ == "__main__":
    sys.exit(main())
