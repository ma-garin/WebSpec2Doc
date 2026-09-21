#!/usr/bin/env python3
"""進捗つき・トークン消費つきステータスライン。

表示は最大 3 部を「｜」で連結する。従来表示は常に消さない。

1. 進捗（`.claude/progress.json` がある時だけ）: タスク名・ステップ・経過/見積・残り
2. 消費（常時）: 累計トークン・1 ターンあたり平均出力・ターン数
3. 従来表示（`~/.claude/statusline.sh`）

消費表示を入れる理由（INC-2026-002）:
実測で cache_read が全消費の 95% を占め、その実質すべてが「自分の過去出力の再読」だった
（再読総量 ≒ 平均出力 × ターン数² / 2）。平均出力が膨らむと、そのぶん残り全ターンに乗る。
**消費はターンを使わずに見えている必要がある。**私に尋ねること自体がターンを 1 つ増やし、
1 回あたり数十万トークンかかるため。詳細は docs/process/token-economics.md。

実装上の制約: 5 秒ごとに呼ばれるので、転写 JSONL は**前回位置からの差分だけ**を読む。
状態は ~/.claude/.token_state.json に置く（リポジトリを汚さないため）。
どこで失敗しても従来表示だけは必ず出す。
"""
import json
import os
import pathlib
import subprocess
import sys
import time

_FILE = pathlib.Path(__file__).resolve().parent.parent / "progress.json"
_FALLBACK = pathlib.Path.home() / ".claude" / "statusline.sh"
_STATE = pathlib.Path.home() / ".claude" / ".token_state.json"

# 平均出力がこれを超えたら警告を出す（実測 1,331 に対し、400 まで下げると総消費 78% 減）
_WARN_AVG_OUTPUT = 800


def _fmt(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def _si(n: float) -> str:
    """トークン数を短く表す。"""
    for unit, div in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if n >= div:
            return f"{n / div:.1f}{unit}"
    return str(int(n))


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


def _load_state(key: str, ident: str) -> dict:
    try:
        allst = json.loads(_STATE.read_text(encoding="utf-8"))
        st = allst.get(key)
        if st and st.get("ident") == ident:
            return st
    except (json.JSONDecodeError, OSError):
        pass
    return {"ident": ident, "offset": 0, "turns": 0,
            "cache_read": 0, "cache_write": 0, "output": 0}


def _save_state(key: str, st: dict) -> None:
    try:
        try:
            allst = json.loads(_STATE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            allst = {}
        allst[key] = st
        if len(allst) > 20:  # 古いセッションの状態を溜めない
            allst = dict(list(allst.items())[-20:])
        tmp = _STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(allst), encoding="utf-8")
        os.replace(tmp, _STATE)
    except OSError:
        pass


def _tokens_part(stdin_raw: str) -> str:
    """転写 JSONL を差分読みして累計消費を返す。失敗したら空文字。"""
    try:
        payload = json.loads(stdin_raw) if stdin_raw.strip() else {}
    except json.JSONDecodeError:
        return ""
    path = payload.get("transcript_path")
    if not path:
        return ""
    p = pathlib.Path(path)
    try:
        stat = p.stat()
    except OSError:
        return ""

    key = str(p)
    ident = f"{stat.st_ino}:{stat.st_dev}"
    st = _load_state(key, ident)
    if stat.st_size < st["offset"]:      # 切り詰められた -> 最初から
        st = {"ident": ident, "offset": 0, "turns": 0,
              "cache_read": 0, "cache_write": 0, "output": 0}

    if stat.st_size > st["offset"]:
        try:
            with p.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(st["offset"])
                for line in fh:
                    if not line.endswith("\n"):   # 書き込み途中の行は次回に回す
                        break
                    st["offset"] += len(line.encode("utf-8", "replace"))
                    try:
                        u = (json.loads(line).get("message") or {}).get("usage")
                    except ValueError:
                        continue
                    if not u:
                        continue
                    st["turns"] += 1
                    st["cache_read"] += u.get("cache_read_input_tokens", 0)
                    st["cache_write"] += u.get("cache_creation_input_tokens", 0)
                    st["output"] += u.get("output_tokens", 0)
        except OSError:
            return ""
        _save_state(key, st)

    if st["turns"] == 0:
        return ""
    total = st["cache_read"] + st["cache_write"] + st["output"]
    avg_out = st["output"] / st["turns"]
    mark = "⚠ " if avg_out > _WARN_AVG_OUTPUT else ""
    return f"{mark}Σ{_si(total)} 出力{int(avg_out):,}/t {st['turns']}t"


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
    try:
        tokens = _tokens_part(stdin_raw)
    except Exception:       # ステータスラインは何があっても落とさない
        tokens = ""
    parts = [x for x in (_progress_part(), tokens, _fallback_part(stdin_raw)) if x]
    print(" ｜ ".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
