#!/usr/bin/env python3
"""タスク進捗の記録（statusline が読む .claude/progress.json を管理する）。

使い方（既存の bash コマンドに && で連結する。追加の往復を作らない）:
  python3 .claude/hooks/progress.py start "タスク名" <見積秒>
  python3 .claude/hooks/progress.py step "2/5 配線"
  python3 .claude/hooks/progress.py done
"""
import json
import pathlib
import sys
import time

_FILE = pathlib.Path(__file__).resolve().parent.parent / "progress.json"


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    cmd = sys.argv[1]
    if cmd == "start":
        data = {
            "task": sys.argv[2],
            "estimate_sec": int(sys.argv[3]),
            "started": time.time(),
            "step": "開始",
            "updated": time.time(),
        }
        _FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    elif cmd == "step":
        if not _FILE.exists():
            return 0
        data = json.loads(_FILE.read_text(encoding="utf-8"))
        data["step"] = sys.argv[2]
        data["updated"] = time.time()
        _FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    elif cmd == "done":
        if _FILE.exists():
            _FILE.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
