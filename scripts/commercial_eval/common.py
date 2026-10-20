"""商用品質の精度評価（quality/commercial_eval/）で共有する採点の道具。

正解は各データセットの expected.json だけから読む。製品の判定ロジックは import しない
（製品の出力ファイルを読むだけ）。
"""
from __future__ import annotations

import re


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    rnd = lambda v: None if v is None else round(v, 3)  # noqa: E731
    return {"precision": rnd(p), "recall": rnd(r), "f1": rnd(f1), "tp": tp, "fp": fp, "fn": fn}


def norm_path(path: str) -> str:
    """route/API の正規形: クエリ・末尾スラッシュを除き、動的セグメントを :param に寄せる。"""
    p = (path or "").split("?", 1)[0].split("#", 1)[0].strip()
    p = re.sub(r"\$\{[^}]+\}", ":param", p)
    p = re.sub(r"/:[A-Za-z_][\w]*", "/:param", p)
    p = re.sub(r"/\d+(?=/|$)", "/:param", p)
    if len(p) > 1:
        p = p.rstrip("/")
    return p


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()
