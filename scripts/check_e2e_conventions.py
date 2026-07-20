#!/usr/bin/env python3
"""E2E テストの規約チェック（ラチェット方式）。

**固定待機を禁止する。** `time.sleep()` や `wait_for_timeout()` は
「N秒何もせず待つ」だけの純粋な遅延であり、遅くしたうえに不安定にする。

根拠（docs/research/test-speedup-survey.md）:
- Luo et al. FSE 2014 — flaky の最大要因は非同期待ち（async wait）
- SAP HANA の実証（arXiv:2402.05223, 2024）— タイムアウト由来 flaky は10年後も残る
- Parry et al. EASE 2025 — flaky は共起する。根本原因を1つ潰すと複数治る

代わりに、状態が整ったことを示す**肯定的な目印（positive landmark）**を待つこと:

    NG:  page.wait_for_timeout(2000)
    OK:  expect(page.locator("#result")).to_be_visible()
    OK:  page.wait_for_selector("#result", state="visible")

既存分は BASELINE として凍結し、**増加のみ**を失敗させる。減らす分には常に通る。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

E2E_DIR = Path("tests/e2e")

# 固定待機の検出パターン
PATTERNS = (
    re.compile(r"\btime\.sleep\s*\("),
    re.compile(r"\bwait_for_timeout\s*\("),
)

# 既存の固定待機の件数。**この値を増やす変更は許可しない。**
# 減らしたら、この値も一緒に下げること（ラチェットを締める）。
BASELINE = 9


def find_violations() -> list[tuple[Path, int, str]]:
    hits: list[tuple[Path, int, str]] = []
    for path in sorted(E2E_DIR.rglob("*.py")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            if line.lstrip().startswith("#"):
                continue
            if any(p.search(line) for p in PATTERNS):
                hits.append((path, lineno, line.strip()))
    return hits


def main() -> int:
    if not E2E_DIR.is_dir():
        print(f"[skip] {E2E_DIR} が見つかりません")
        return 0

    hits = find_violations()
    count = len(hits)

    if count > BASELINE:
        print("E2E 規約違反: 固定待機が増えています\n")
        for path, lineno, text in hits:
            print(f"  {path}:{lineno}: {text}")
        print(
            f"\n固定待機 {count} 件（許容 {BASELINE} 件）。"
            "\n`time.sleep` / `wait_for_timeout` は使わず、"
            "肯定的な目印を待ってください:"
            '\n  expect(page.locator("#result")).to_be_visible()'
        )
        return 1

    if count < BASELINE:
        print(
            f"固定待機 {count} 件（許容 {BASELINE} 件）。減っています。"
            f"\nscripts/check_e2e_conventions.py の BASELINE を {count} に下げてください。"
        )
        return 0

    print(f"E2E 規約チェック PASS（固定待機 {count} 件 / 許容 {BASELINE} 件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
