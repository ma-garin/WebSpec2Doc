#!/usr/bin/env python3
"""進捗つきステータスライン。

タスク進行中（.claude/progress.json あり）: 進捗（タスク名・ステップ・経過/見積・残り）を
従来表示（~/.claude/statusline.sh）の前に連結して出す。従来表示は常に消さない。
待機中: 従来表示のみ。
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


def _progress_part() -> str:
    """進行中タスクの進捗文字列。無ければ空文字。"""
    if not _FILE.exists():
        return ""
    try:
        d = json.loads(_FILE.read_text(encoding="utf-8"))
        elapsed = time.time() - d["started"]
        est = d["estimate_sec"]
        remain = est - elapsed
        tail = (f"残り {_fmt(remain)}" if remain >= 0
                else f"残り 0:00（超過 +{_fmt(-remain)}）")
        return f"⏱ {d['task']} [{d['step']}] {_fmt(elapsed)}/{_fmt(est)} {tail}"
    except (json.JSONDecodeError, KeyError, OSError):
        return ""  # 壊れた進捗ファイルは無視して従来表示のみ


def _fallback_part(stdin_raw: str) -> str:
    """従来のステータスライン出力。常に表示し続ける。"""
    if _FALLBACK.exists():
        try:
            out = subprocess.run(
                ["bash", str(_FALLBACK)], input=stdin_raw, capture_output=True,
                text=True, timeout=5,
            )
            return out.stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            pass
    return os.path.basename(os.getcwd())


def main() -> int:
    stdin_raw = sys.stdin.read()
    progress = _progress_part()
    base = _fallback_part(stdin_raw)
    print(f"{progress} ｜ {base}" if progress else base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
