"""DocAssure の性能テスト。合成した日本語仕様書で analyze の所要時間に上限を置く。"""
from __future__ import annotations

import time

from web.services.docassure import pipeline

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


def _run(docs: list[dict]) -> float:
    t = time.monotonic()
    r = pipeline.analyze(docs)
    assert r["counts"]["requirements"] > 0
    return time.monotonic() - t


def test_perf_2000_lines_within_20s():
    pipeline._EXTRACT_CACHE.clear()
    sec = _run([{"id": "D1", "name": "a", "type": "spec", "text": make_doc(2000)}])
    assert sec <= 20, f"2,000 行: {sec:.1f} 秒（上限 20 秒）"


def test_perf_10000_lines_within_120s():
    pipeline._EXTRACT_CACHE.clear()
    sec = _run([{"id": "D1", "name": "a", "type": "spec", "text": make_doc(10000)}])
    assert sec <= 120, f"10,000 行: {sec:.1f} 秒（上限 120 秒）"
