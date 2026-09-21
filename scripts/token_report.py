#!/usr/bin/env python3
"""セッションのトークン消費構造を実測する。依存なし・API キー不要・ネットワーク不要。

使い方:
    python3 scripts/token_report.py                # 最新セッションを集計
    python3 scripts/token_report.py --all          # プロジェクトの全セッションを一覧
    python3 scripts/token_report.py <path.jsonl>   # 指定セッションを集計

なぜ必要か:
INC-2026-002（2026-09-21・Fable 週間上限の枯渇）の原因分析は、1 回目が 160 倍、
2 回目が支配項の取り違えで外れた。どちらも「推測で語ったから」である。
規約の文章ではなく、この出力で判断すること。詳細は docs/process/token-economics.md。

読み方:
- cache_read が総消費のほぼ全量になる。これは「そのターンで新しく読んだ量」ではなく
  累積コンテキストを毎ターン読み直す費用。
- 自分（assistant）の出力は転写に残り、以後の全ターンで再読される。
  ターン k に X トークン出せば (N-k) 回読み直されるため、総量は 平均出力 x N^2/2 に比例する。
- したがって削るべき順序は (1) 1 ターンの出力量 (2) ターン数 (3) 常時ロードのファイル (4) 設定。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
# 常時ロードされ、毎ターン固定費になるファイル（存在するものだけ集計する）
ALWAYS_LOADED = [
    "CLAUDE.md",
    ".claude/rules/speed-harness.md",
    ".claude/rules/functional-integrity.md",
]
CHARS_PER_TOKEN = 2.0  # 日英混在の実測比。概算であることを明示して使う


def find_sessions(explicit: str | None) -> list[Path]:
    if explicit:
        p = Path(explicit)
        return [p] if p.exists() else []
    if not PROJECTS.is_dir():
        return []
    files = [f for d in PROJECTS.iterdir() if d.is_dir() for f in d.glob("*.jsonl")]
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


def collect(path: Path) -> dict:
    turns: list[tuple[int, int, int]] = []  # (cache_read, output, line_no)
    totals = {"cache_read": 0, "cache_write": 0, "output": 0, "input": 0}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            usage = (rec.get("message") or {}).get("usage")
            if not usage:
                continue
            cr = usage.get("cache_read_input_tokens", 0)
            out = usage.get("output_tokens", 0)
            totals["cache_read"] += cr
            totals["cache_write"] += usage.get("cache_creation_input_tokens", 0)
            totals["output"] += out
            totals["input"] += usage.get("input_tokens", 0)
            turns.append((cr, out, n))
    return {"path": path, "totals": totals, "turns": turns}


def reread_of_own_output(turns: list[tuple[int, int, int]]) -> int:
    """自分の出力が後続ターンで再読される総量。sum_k(それまでの累積出力)。"""
    acc = total = 0
    for _cr, out, _n in turns:
        total += acc
        acc += out
    return total


def fixed_cost(root: Path, n_turns: int) -> tuple[list[tuple[str, int, int]], int]:
    rows, per_turn = [], 0
    for rel in ALWAYS_LOADED:
        f = root / rel
        if not f.exists():
            continue
        tok = int(f.stat().st_size / CHARS_PER_TOKEN)
        per_turn += tok
        rows.append((rel, tok, tok * n_turns))
    return rows, per_turn


def fmt(n: float) -> str:
    return f"{int(n):,}"


def report(data: dict, root: Path) -> None:
    t, turns = data["totals"], data["turns"]
    n = len(turns)
    if n == 0:
        print(f"{data['path']}: usage を持つターンがない")
        return
    grand = t["cache_read"] + t["cache_write"] + t["output"] + t["input"]
    reread = reread_of_own_output(turns)
    rows, per_turn = fixed_cost(root, n)

    print(f"session : {data['path']}")
    print(f"turns   : {n}")
    print()
    print("  項目           総量            全体比    1ターン平均")
    for k, label in [("cache_read", "cache_read"), ("cache_write", "cache_write"),
                     ("output", "output"), ("input", "input(非キャッシュ)")]:
        share = 100 * t[k] / grand if grand else 0
        print(f"  {label:<18} {fmt(t[k]):>14}  {share:6.2f}%  {fmt(t[k] / n):>10}")
    print(f"  {'合計':<18} {fmt(grand):>14}")
    print()
    print("支配項の内訳（cache_read を 100% とした比率）")
    print(f"  自分の出力の再読(平均出力 x N^2/2)  {fmt(reread):>14}  "
          f"{100 * reread / t['cache_read'] if t['cache_read'] else 0:6.1f}%")
    if rows:
        tot_fixed = sum(r[2] for r in rows)
        print(f"  常時ロードの規約ファイル            {fmt(tot_fixed):>14}  "
              f"{100 * tot_fixed / t['cache_read'] if t['cache_read'] else 0:6.1f}%"
              f"   ({fmt(per_turn)} tok/turn)")
        for rel, tok, total in rows:
            print(f"      {rel:<38} {fmt(tok):>7} tok/turn -> {fmt(total):>12}")
    print("  (再読の近似は microcompact による tool_result の自動削除を考慮しないため"
          " 100% を超えうる)")
    print()

    avg_out = t["output"] / n
    for target in (800, 600, 400):
        if avg_out <= target:
            continue
        saved = reread * (1 - target / avg_out)
        print(f"  平均出力 {fmt(avg_out)} -> {target} tok にすると "
              f"約 {fmt(saved)} tok 削減（総消費の {100 * saved / grand:.0f}%）")
    print(f"  ターン数を半減すると再読項は 1/4（約 {fmt(reread * 0.75)} tok 削減）")
    print()

    worst = sorted(turns, key=lambda x: -x[1])[:5]
    print("出力が大きかったターン（そのぶん最後まで再読され続ける）")
    for cr, out, line in worst:
        idx = [x[2] for x in turns].index(line)
        print(f"  jsonl 行 {line:>6}  出力 {fmt(out):>7} tok  "
              f"残り {n - idx - 1} ターン分の再読 = 約 {fmt(out * (n - idx - 1))} tok")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", nargs="?", help="セッション JSONL のパス（省略時は最新）")
    ap.add_argument("--all", action="store_true", help="見つかったセッションを一覧表示する")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]),
                    help="常時ロードファイルを数えるリポジトリルート")
    args = ap.parse_args()

    sessions = find_sessions(args.session)
    if not sessions:
        print("セッション JSONL が見つからない。"
              f"探索先: {args.session or PROJECTS}", file=sys.stderr)
        return 1

    if args.all:
        print(f"{'サイズ':>10}  セッション")
        for s in sessions[:30]:
            print(f"{s.stat().st_size:>10,}  {s}")
        return 0

    report(collect(sessions[0]), Path(args.root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
