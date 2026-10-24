#!/usr/bin/env python3
"""タイポと色のトークン置換（U01-02）。冪等。使い方: codemod_tokens.py [--dry-run] <file>...

(1) font-size:<n>px -> var(--text-*)  (CSS と HTML の style 属性)
(2) color: var(--color-(high|medium|warning|success|error|info)) -> -tx（background / border は触らない）
"""
import difflib
import re
import sys

FS = re.compile(r"(font-size\s*:\s*)(\d+(?:\.\d+)?)px")
COLOR = re.compile(r"(?<![\w-])(color\s*:\s*var\(\s*--color-(?:high|medium|warning|success|error|info))(\s*[,)])")


def token(n: float) -> str:
    if n <= 12:
        return "xs"
    if n <= 13.5:
        return "sm"
    if n <= 15:
        return "base"
    if n <= 18:
        return "md"
    return "xl"


def convert(text: str) -> tuple[str, int]:
    count = 0

    def fs(m):
        nonlocal count
        count += 1
        return f"{m.group(1)}var(--text-{token(float(m.group(2)))})"

    def col(m):
        nonlocal count
        count += 1
        return f"{m.group(1)}-tx{m.group(2)}"

    return COLOR.sub(col, FS.sub(fs, text)), count


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    files = [a for a in argv if a != "--dry-run"]
    if not files:
        print("使い方: codemod_tokens.py [--dry-run] <file>...", file=sys.stderr)
        return 2
    for path in files:
        with open(path, encoding="utf-8") as f:
            old = f.read()
        new, n = convert(old)
        if dry and n:
            sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True), path, path + " (after)"))
        elif n:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new)
        print(f"{path}: {n} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
