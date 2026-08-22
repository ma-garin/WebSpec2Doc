#!/usr/bin/env python3
"""進捗つきステータスライン。

タスク進行中（.claude/progress.json あり）: タスク名・ステップ・経過/見積・残りを表示。
待機中: 既存の ~/.claude/statusline.sh へ stdin を素通しして従来表示を保つ。
"""
import json
import os
import pathlib
import subprocess
import sys
import time

_FILE = pathlib.Path(__file__).resolve().parent.parent / "progress.json"
_FALLBACK = pathlib.Path.home() / ".claude" / "statusline.sh"


def _fmt(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def main() -> int:
    stdin_raw = sys.stdin.read()
    if _FILE.exists():
        try:
            d = json.loads(_FILE.read_text(encoding="utf-8"))
            elapsed = time.time() - d["started"]
            est = d["estimate_sec"]
            remain = est - elapsed
            tail = (f"残り {_fmt(remain)}" if remain >= 0
                    else f"残り 0:00（超過 +{_fmt(-remain)}）")
            print(f"⏱ {d['task']} [{d['step']}] 経過 {_fmt(elapsed)} / 見積 {_fmt(est)} ・ {tail}")
            return 0
        except (json.JSONDecodeError, KeyError, OSError):
            pass  # 壊れた進捗ファイルは無視して従来表示へ
    if _FALLBACK.exists():
        try:
            out = subprocess.run(
                ["bash", str(_FALLBACK)], input=stdin_raw, capture_output=True,
                text=True, timeout=5,
            )
            sys.stdout.write(out.stdout)
            return 0
        except (subprocess.TimeoutExpired, OSError):
            pass
    cwd = os.path.basename(os.getcwd())
    print(f"{cwd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
