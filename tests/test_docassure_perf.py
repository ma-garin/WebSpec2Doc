"""DocAssure の性能テスト。合成した日本語仕様書で analyze の所要時間に上限を置く。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_DOMAINS = [
    ("受注", "注文", "出荷指示"), ("会員", "会員登録", "退会"), ("決済", "請求", "返金"),
    ("在庫", "入庫", "棚卸"), ("配送", "配送依頼", "再配達"), ("ポイント", "付与", "失効"),
    ("通知", "メール送信", "再送"), ("権限", "ロール", "承認"),
]


def make_doc(lines: int, seed: int = 0, prefix: str = "REQ") -> str:
    """見出し・箇条書き・表・REQ ID 付き要件文を繰り返す合成文書（約 lines 行）。"""
    out: list[str] = ["# 仕様書", ""]
    n = 0
    sec = 0
    while len(out) < lines:
        dom, noun, act = _DOMAINS[(sec + seed) % len(_DOMAINS)]
        sec += 1
        out += [f"## {sec}. {dom}機能{sec}", ""]
        for _ in range(4):
            n += 1
            lim = 5 + (n * 7 + seed) % 90
            out.append(f"{prefix}-{n:04d}: システムは{noun}{n}の{act}時に{lim}件までを処理し、{lim + 3}秒以内に応答しなければならない。")
        out += ["", f"- {dom}担当者は{noun}{sec}の一覧を参照できる。",
                f"- 管理者は{act}の結果をCSVで出力できること。",
                f"- 状態は「受付」「処理中」「完了」の順に遷移する。", ""]
        out += ["| 項目 | 型 | 必須 |", "|---|---|---|",
                f"| {noun}ID | 数値 | 必須 |", f"| {act}日 | 日付 | 任意 |", ""]
    return "\n".join(out[:lines])


_CHILD = (
    "import sys,time,json;from tests.test_docassure_perf import make_doc;from web.services.docassure import pipeline;"
    "t=time.monotonic();r=pipeline.analyze([{'id':'D1','name':'a','type':'spec','text':make_doc(int(sys.argv[1]))}]);"
    "print(json.dumps({'sec':time.monotonic()-t,'req':r['counts']['requirements']}))"
)


def _run(lines: int, limit: float) -> float:
    """分析を子プロセスで実行し、limit 秒（+余裕 10 秒）で確実に kill する。終了後に子を残さない。"""
    proc = subprocess.Popen([sys.executable, "-c", _CHILD, str(lines)], cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    try:
        out, err = proc.communicate(timeout=limit + 10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise AssertionError(f"{lines:,} 行: {limit + 10:.0f} 秒で終わらず強制終了（上限 {limit} 秒）")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    assert proc.returncode == 0, err[-500:]
    r = json.loads(out.strip().splitlines()[-1])
    assert r["req"] > 0
    return r["sec"]


def test_perf_2000_lines_within_20s():
    sec = _run(2000, 20)
    assert sec <= 20, f"2,000 行: {sec:.1f} 秒（上限 20 秒）"


def test_perf_10000_lines_within_120s():
    sec = _run(10000, 120)
    assert sec <= 120, f"10,000 行: {sec:.1f} 秒（上限 120 秒）"
