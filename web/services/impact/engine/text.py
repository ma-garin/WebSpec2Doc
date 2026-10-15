"""文字列の正規化・語の切り出し・文字 n-gram の類似度（analyze.py から移植）。"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

# 壊れたときの害が大きい語。当たったら影響度を「致命」に上げる候補にする。
HARM = ("金額", "料金", "決済", "支払", "請求", "課金", "税", "ポイント", "個人情報", "パスワード", "認証",
        "ログイン", "権限", "削除", "消失", "一括", "取込", "取り込み", "バッチ", "移行", "連携", "停止", "排他",
        "セキュリティ", "暗号", "在庫", "締め")
# 同じ部品・同じ規則を使い回していることを示す語。間接の影響を拾う。
SHARED = ("共通", "共用", "流用", "同じ", "同一", "参照", "準拠", "準ずる", "引き継", "連動")
STOP = {"こと", "もの", "ため", "場合", "とき", "これ", "それ", "以下", "以上", "未満", "について", "および",
        "または", "する", "される", "できる", "ある", "なる", "行う", "変更", "追加", "削除", "修正", "対応",
        "画面", "項目", "機能", "処理", "表示", "入力", "仕様", "設計", "概要", "備考", "なし", "あり"}
# 変わった語と同じ規則を別の言い方で書いた語。
SYN = {"必須": ("未入力", "空欄", "省略", "入力必須"), "任意": ("未入力", "空欄", "省略"),
       "桁": ("桁数", "文字数", "長さ"), "文字": ("文字数", "桁数", "長さ"), "上限": ("最大", "以内", "超え"),
       "下限": ("最小", "以上", "未満"), "表示": ("非表示", "表記"), "削除": ("論理削除", "物理削除")}

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{1,}|[ァ-ヶー]{2,}|[一-龥々]{2,}|[0-9]+ ?(?:桁|文字|件|円|日|%)")
_WS = re.compile(r"\s+")


def norm(s: str | None) -> str:
    """NFKC で正規化し、連続する空白を 1 つにする。"""
    return _WS.sub(" ", unicodedata.normalize("NFKC", s or "")).strip()


def tokens(s: str | None) -> list[str]:
    seen, out = set(), []
    for t in _TOKEN.findall(norm(s)):
        t = t.strip(".").replace(" ", "")
        if len(t) < 2 or t in STOP or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def expand(words: list[str]) -> list[str]:
    """差分の語に言い換えを足す。"""
    out = list(words)
    for t in words:
        for key, syn in SYN.items():
            if key in t:
                out += [w for w in syn if w not in out]
    return out


def ngrams(s: str | None, n: int = 2) -> Counter:
    t = _WS.sub("", norm(s))
    if len(t) < n:
        return Counter([t]) if t else Counter()
    return Counter(t[i:i + n] for i in range(len(t) - n + 1))


def cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def clip(s: str | None, n: int = 120) -> str:
    t = norm(s)
    return t if len(t) <= n else t[:n] + "…"
