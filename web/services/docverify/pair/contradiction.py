"""要件定義書と基本設計書の対から、数値・条件・順序の食い違い（CONTRADICTION）を検出する。

対応する要件と設計の対（links）ごとに「量」（数値＋単位）と「比較」（以上・以下・まで など）を
取り出し、同じ種類の量（単位が同じで、前後の語が似ている）の値か比較が食い違えば指摘する。
あわせて「A した後に B」の順序が設計で逆になっているものを指摘する。標準ライブラリだけを使う。
"""
from __future__ import annotations

import re
import unicodedata

from .segment import Unit

_KANJI_DIGIT = {"〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                "六": 6, "七": 7, "八": 8, "九": 9}
_KANJI_UNIT = {"十": 10, "百": 100, "千": 1000, "万": 10000}
_UNITS = ("営業日", "日間", "日後", "日前", "日", "時間", "時", "分間", "分", "秒",
          "件", "円", "桁", "回", "%", "文字", "か月", "ヶ月", "カ月", "ヵ月", "ケ月",
          "週間", "年", "人", "名", "歳", "個", "点", "倍", "MB", "GB", "KB", "行", "ページ")
_UNIT_ALIAS = {"日間": "日", "分間": "分", "ヶ月": "か月", "カ月": "か月", "ヵ月": "か月",
               "ケ月": "か月", "週間": "週"}
_NUM = r"[0-9][0-9,]*(?:\.[0-9]+)?|[〇一二三四五六七八九十百千万]+"
_QTY_RE = re.compile(r"(" + _NUM + r")\s*(" + "|".join(map(re.escape, _UNITS)) + r")")
_CMP_RE = re.compile(r"^\s*(以上|以下|未満|を?超え|超|まで|以内|から|より前|より後)")
_SKIP = re.compile(r"[\s、。,，「」『』（）()・:：*`|]")
_ORDER_RE = re.compile(r"([^、。]{2,16}?)(?:た|て)(?:後|あと)に、?([^、。]{2,24})")
_RUN_RE = re.compile(r"[一-龥ァ-ヴー]{2,}")
_THEN = ("場合に", "後に", "あとに", "てから", "次に")
_MIN_SIM = 0.25


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def _kanji_num(s: str) -> float | None:
    total, cur = 0, 0
    for ch in s:
        if ch in _KANJI_DIGIT:
            cur = _KANJI_DIGIT[ch]
        elif ch in _KANJI_UNIT:
            total += (cur or 1) * _KANJI_UNIT[ch]
            cur = 0
        else:
            return None
    return float(total + cur)


def _value(s: str) -> float | None:
    if s[0].isdigit():
        try:
            return float(s.replace(",", ""))
        except ValueError:
            return None
    return _kanji_num(s)


def _grams(s: str) -> set[str]:
    s = _SKIP.sub("", s)
    return {s[i:i + 2] for i in range(len(s) - 1)} or ({s} if s else set())


def _dice(a: set[str], b: set[str]) -> float:
    return 2 * len(a & b) / (len(a) + len(b)) if a and b else 0.0


def _quantities(unit: Unit) -> list[dict]:
    """単位の文から量を取り出す。各量は値・単位・比較・前後の文脈・行番号を持つ。"""
    text = _norm(unit.text).replace("無料", "0円")  # 同じ長さなので行番号はずれない
    out = []
    for m in _QTY_RE.finditer(text):
        val = _value(m.group(1))
        if val is None:
            continue
        cmp_m = _CMP_RE.match(text[m.end():])
        left = text[max(0, m.start() - 12):m.start()]
        right = text[m.end():m.end() + 6]
        line = unit.start + text.count("\n", 0, m.start())
        out.append({"value": val, "unit": _UNIT_ALIAS.get(m.group(2), m.group(2)),
                    "cmp": cmp_m.group(1).lstrip("を") if cmp_m else "",
                    "ctx": _grams(left) | _grams(right), "left": _grams(left),
                    "line": min(line, unit.end), "raw": m.group(0)})
    return out


def _conflict(rq: dict, dq: dict) -> bool:
    if rq["value"] != dq["value"]:
        return True
    return bool(rq["cmp"] and dq["cmp"]) and rq["cmp"] != dq["cmp"] \
        and {rq["cmp"], dq["cmp"]} != {"まで", "以内"}


def _qty_pairs(r: Unit, d: Unit) -> list[tuple[dict, dict, float]]:
    """同じ種類の量の組で、値か比較が食い違うもの。"""
    rqs, dqs = _quantities(r), _quantities(d)
    r_keys = {(q["value"], q["unit"], q["cmp"]) for q in rqs}
    d_keys = {(q["value"], q["unit"], q["cmp"]) for q in dqs}
    dqs = [q for q in dqs if (q["value"], q["unit"], q["cmp"]) not in r_keys]  # 要件のどこかに同じ記述がある
    found = []
    for rq in rqs:
        if (rq["value"], rq["unit"], rq["cmp"]) in d_keys:  # 設計に同じ記述がある
            continue
        same = [dq for dq in dqs if dq["unit"] == rq["unit"]]
        r_alone = sum(1 for q in rqs if q["unit"] == rq["unit"]) == 1
        for dq in same:
            sim = _dice(rq["ctx"], dq["ctx"])
            alone = r_alone and len(same) == 1
            if _conflict(rq, dq) and (sim >= _MIN_SIM or (alone and sim > 0)):
                found.append((rq, dq, sim))
    return found


def _first(text: str, runs: list[str]) -> int:
    pos = [text.find(run[:2]) for run in runs if run[:2] in text]
    return min(pos) if pos else -1


def _order_conflict(r: Unit, d: Unit) -> tuple[int, int] | None:
    """要件の「A した後に B」が、設計では「B の後に A」になっていれば行番号の対を返す。"""
    rt = _norm(r.text)
    for m in _ORDER_RE.finditer(rt):
        a_runs, b_runs = _RUN_RE.findall(m.group(1)), _RUN_RE.findall(m.group(2))
        if not a_runs or not b_runs:
            continue
        for no, line in enumerate(_norm(d.text).split("\n")):
            pa, pb = _first(line, a_runs[:1]), _first(line, b_runs)
            if pa < 0 or pb < 0 or pb >= pa:
                continue
            if any(t in line[pb:pa] for t in _THEN):
                return r.start + rt.count("\n", 0, m.start()), d.start + no
    return None


def _defect(r_line: int, d_line: int, reason: str) -> dict:
    return {"type": "CONTRADICTION", "req_lines": [r_line, r_line],
            "design_lines": [d_line, d_line], "reason": reason}


def detect(req_units: list[Unit], design_units: list[Unit],
           links: list[tuple[Unit, Unit, float]]) -> list[dict]:
    """links の対ごとに量・比較・順序の食い違いを調べ、CONTRADICTION の指摘を返す。

    1 つの要件の量につき、最も文脈の近い設計の量 1 件だけを指摘する。
    """
    del req_units, design_units  # 対は links から取る（引数は他の検出器と形を揃えるため）
    best: dict[tuple[int, str], tuple[float, dict]] = {}
    for r, d, score in links:
        for rq, dq, sim in _qty_pairs(r, d):
            key = (rq["line"], rq["raw"])
            rank = sim + 0.1 * score
            if key not in best or rank > best[key][0]:
                reason = (f"要件の「{rq['raw']}{rq['cmp']}」と設計の"
                          f"「{dq['raw']}{dq['cmp']}」で値または条件が食い違う。")
                best[key] = (rank, _defect(rq["line"], dq["line"], reason))
        hit = _order_conflict(r, d)
        if hit:
            key = (hit[0], "order")
            if key not in best:
                best[key] = (1.0, _defect(hit[0], hit[1], "要件と設計で処理の順序が逆になっている。"))
    out, seen = [], set()
    for _, item in sorted(best.values(), key=lambda x: -x[0]):
        pair = (item["req_lines"][0], item["design_lines"][0])
        if pair not in seen:
            seen.add(pair)
            out.append(item)
    return out


def _rough_links(req_units: list[Unit], design_units: list[Unit],
                 top: int = 3, min_score: float = 0.15) -> list[tuple[Unit, Unit, float]]:
    """試験用の簡易な候補対（ID 一致＋文字 2-gram の重なり）。公開しない。"""
    d_grams = [(d, _grams(_norm(d.text))) for d in design_units]
    links = []
    for r in req_units:
        rg = _grams(_norm(r.text))
        scored = []
        for d, dg in d_grams:
            s = _dice(rg, dg) + (1.0 if set(r.ids) & set(d.ids) else 0.0)
            if s >= min_score:
                scored.append((s, d))
        scored.sort(key=lambda x: -x[0])
        links.extend((r, d, s) for s, d in scored[:top])
    return links
