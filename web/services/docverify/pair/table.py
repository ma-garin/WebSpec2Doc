"""TABLE_MISMATCH の検出: 表どうし、または表と本文で値・桁・コード値が食い違う箇所。

3 つの見方を合わせる（標準ライブラリだけ・組ごとの固有値は持たない）。

1. 要件の表 ⇔ 設計の表: 鍵の列（文字の値の列）で行を対応づけ、見出しが似た列の数値が違えば指摘。
   鍵そのものに数値を含む表（金額帯など）は、数値を除いた骨格が一意なら行を対応づけ、鍵の数値も比べる。
2. 項目の桁: データ設計・画面項目の表（「項目」「桁」の列）と、本文の「X は N 桁／N 文字」を集め、
   同じ項目で多数派と違う表の行を指摘する。
3. コード値: 設計の表の「〜コード」列と、その行の鍵を挙げた本文の「〜コード NN」が違えば指摘する。
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

_NUM = re.compile(r"\d+(?:\.\d+)?")
_LEN_AFTER = re.compile(r"^[はのをが:：（(、]*[^。\n\d]{0,10}?(\d+)(?:桁|文字)")
_TOTAL = re.compile(r"計(\d+)(?:桁|文字)")
_WORD = re.compile(r"\w")
_BRACKET = re.compile(r"[（(][^）)]*[）)]")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"(?<=\d),(?=\d{3})", "", s)
    return re.sub(r"\s+", "", s)


def _nums(s: str) -> tuple[str, ...]:
    return tuple(str(float(n)) for n in _NUM.findall(_norm(s)))


def _is_text(cell: str) -> bool:
    c = _norm(cell)
    return bool(re.sub(r"[\d\W_]", "", c))


def _skeleton(cell: str) -> str:
    return _NUM.sub("#", _norm(cell))


def _sim(a: str, b: str) -> float:
    """見出しの類似度。括弧書きを除いて包含なら 1、それ以外は 2 文字組の Dice 係数。"""
    a, b = _BRACKET.sub("", _norm(a)), _BRACKET.sub("", _norm(b))
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    ga = {a[i:i + 2] for i in range(len(a) - 1)} or {a}
    gb = {b[i:i + 2] for i in range(len(b) - 1)} or {b}
    return 2 * len(ga & gb) / (len(ga) + len(gb))


def _tables(units) -> list[list]:
    groups: dict[int, list] = {}
    for u in units:
        if u.kind == "row" and u.table >= 0:
            groups.setdefault(u.table, []).append(u)
    return [rows for rows in groups.values() if rows]


def _key_col(rows) -> int:
    width = min(len(r.cells) for r in rows)
    for j in range(width):
        if all(_is_text(r.cells[j]) for r in rows):
            return j
    return -1


def _body(units) -> list:
    return [u for u in units if u.kind in ("item", "para")]


def _defect(req_lines, design_lines, reason: str) -> dict:
    return {"type": "TABLE_MISMATCH", "req_lines": req_lines,
            "design_lines": design_lines, "reason": reason}


def _span(lines: list[int]) -> list[int]:
    return [min(lines), max(lines)] if lines else []


# --- 1. 要件の表 ⇔ 設計の表 -------------------------------------------------

def _align_rows(r_rows, d_rows, kr: int, kd: int) -> list[tuple]:
    """鍵の一致で行を対応づけ、残りは数値を除いた骨格が両表で一意なら対応づける。"""
    d_by_key = {_norm(d.cells[kd]): d for d in d_rows}
    pairs, rest = [], []
    for r in r_rows:
        d = d_by_key.get(_norm(r.cells[kr]))
        (pairs.append((r, d, True)) if d else rest.append(r))
    used = {id(d) for _, d, _ in pairs}
    r_sk = Counter(_skeleton(r.cells[kr]) for r in r_rows)
    d_sk = Counter(_skeleton(d.cells[kd]) for d in d_rows)
    for r in rest:
        sk = _skeleton(r.cells[kr])
        if "#" not in sk or r_sk[sk] != 1 or d_sk[sk] != 1:
            continue
        d = next(d for d in d_rows if _skeleton(d.cells[kd]) == sk)
        if id(d) not in used:
            pairs.append((r, d, False))
    return pairs


def _col_map(r_head, d_head, kr: int, kd: int) -> dict[int, int]:
    out = {}
    for j, h in enumerate(r_head):
        if j == kr:
            continue
        best = max(((_sim(h, g), k) for k, g in enumerate(d_head) if k != kd), default=(0, -1))
        if best[0] >= 0.5:
            out[j] = best[1]
    return out


def _compare_tables(r_rows, d_rows) -> dict | None:
    kr, kd = _key_col(r_rows), _key_col(d_rows)
    if kr < 0 or kd < 0:
        return None
    pairs = _align_rows(r_rows, d_rows, kr, kd)
    exact = sum(1 for _, _, e in pairs if e)
    key_sim = _sim(r_rows[0].headers[kr], d_rows[0].headers[kd]) if r_rows[0].headers else 0
    if not pairs or (exact < 2 and key_sim < 0.5):
        return None
    cols = _col_map(r_rows[0].headers, d_rows[0].headers, kr, kd)
    hits, notes = [], []
    for r, d, exact_key in pairs:
        diff = [] if exact_key else [(r.cells[kr], d.cells[kd])]
        for j, k in cols.items():
            if j < len(r.cells) and k < len(d.cells):
                a, b = _nums(r.cells[j]), _nums(d.cells[k])
                if a and b and a != b:
                    diff.append((r.cells[j], d.cells[k]))
        if diff:
            hits.append((r.start, d.start))
            notes.append(f"{r.cells[kr]}: 要件「{diff[0][0]}」/設計「{diff[0][1]}」")
    if not hits:
        return None
    return _defect(_span([h[0] for h in hits]), _span([h[1] for h in hits]),
                   "表の値が要件と設計で食い違う（" + "、".join(notes[:3]) + "）。")


def _table_vs_table(req_units, design_units) -> list[dict]:
    out = []
    d_tables = _tables(design_units)
    for r_rows in _tables(req_units):
        for d_rows in d_tables:
            hit = _compare_tables(r_rows, d_rows)
            if hit:
                out.append(hit)
    return out


# --- 2. 項目の桁 -----------------------------------------------------------

def _len_cols(headers) -> tuple[int, int]:
    h = [_norm(x) for x in headers]
    lc = next((j for j, x in enumerate(h) if "桁" in x or "文字数" in x), -1)
    nc = next((j for j, x in enumerate(h) if "項目" in x), 0)
    return nc, lc


def _table_claims(units, side: str) -> list[tuple]:
    """(項目名, 桁, 側, 行) の列。表の「項目」「桁」の列から取る。"""
    out = []
    for rows in _tables(units):
        nc, lc = _len_cols(rows[0].headers)
        if lc < 0 or nc == lc:
            continue
        for r in rows:
            if max(nc, lc) < len(r.cells) and _is_text(r.cells[nc]):
                n = _nums(r.cells[lc])
                if len(n) == 1:
                    out.append((_norm(r.cells[nc]), n[0], side, r.start, "table"))
    return out


def _body_len(text: str, name: str) -> str | None:
    pos = text.find(name)
    while pos >= 0:
        prev_ok = pos == 0 or not _WORD.match(text[pos - 1])
        rest = text[pos + len(name):].split("。")[0]
        if prev_ok:
            total = _TOTAL.search(rest)
            m = total or _LEN_AFTER.match(rest)
            if m:
                return str(float(m.group(1)))
        pos = text.find(name, pos + 1)
    return None


def _body_claims(units, side: str, names: set[str]) -> list[tuple]:
    out = []
    for u in _body(units):
        text = _norm(u.text)
        for name in names:
            v = _body_len(text, name) if len(name) >= 2 else None
            if v:
                out.append((name, v, side, u.start, "body"))
    return out


def _majority(claims) -> str:
    score: Counter = Counter()
    for _, v, _, _, kind in claims:
        score[v] += 1.5 if kind == "body" else 1.0
    return score.most_common(1)[0][0]


def _partner(claims, value: str) -> tuple:
    order = {("req", "body"): 0, ("design", "body"): 1, ("req", "table"): 2, ("design", "table"): 3}
    cands = [c for c in claims if c[1] == value]
    return min(cands, key=lambda c: order[(c[2], c[4])])


def _field_lengths(req_units, design_units) -> list[dict]:
    tables = _table_claims(req_units, "req") + _table_claims(design_units, "design")
    names = {c[0] for c in tables}
    claims = tables + _body_claims(req_units, "req", names) + _body_claims(design_units, "design", names)
    by_name: dict[str, list] = {}
    for c in claims:
        by_name.setdefault(c[0], []).append(c)
    out = []
    for name, cs in by_name.items():
        if len({c[1] for c in cs}) < 2:
            continue
        major = _majority(cs)
        p = _partner(cs, major)
        for c in cs:
            if c[4] != "table" or c[2] != "design" or c[1] == major:
                continue
            req = [p[3], p[3]] if p[2] == "req" else []
            des = [c[3], c[3]] if p[2] == "req" else _span([c[3], p[3]])
            out.append(_defect(req, des, f"「{name}」の桁が表では {_fmt(c[1])}、"
                                         f"ほかの記述では {_fmt(major)} で食い違う。"))
    return out


def _fmt(v: str) -> str:
    return v[:-2] if v.endswith(".0") else v


# --- 3. コード値 -----------------------------------------------------------

def _code_claims(rows) -> list[tuple]:
    kc = _key_col(rows)
    head = rows[0].headers
    code_cols = [j for j, h in enumerate(head) if "コード" in _norm(h) and j != kc]
    if kc < 0 or not code_cols:
        return []
    cj = code_cols[0]
    return [(_norm(r.cells[kc]), _norm(head[cj]), _norm(r.cells[cj]), r)
            for r in rows if cj < len(r.cells) and kc < len(r.cells)]


def _code_values(design_units) -> list[dict]:
    out = []
    body = [(u, _norm(u.text)) for u in _body(design_units)]
    for rows in _tables(design_units):
        claims = _code_claims(rows)
        keys = {c[0] for c in claims}
        for key, head, val, row in claims:
            for u, text in body:
                for sent in text.split("。"):
                    if key not in sent or sum(k in sent for k in keys) > 1:
                        continue
                    m = re.search(re.escape(head) + r"([0-9A-Za-z]+)", sent)
                    if m and m.group(1) != val:
                        out.append(_defect([], _span([row.start, u.start]),
                                           f"「{key}」の{head}が表では {val}、"
                                           f"本文では {m.group(1)} で食い違う。"))
    return out


# --- 公開関数 ---------------------------------------------------------------

def detect(req_units, design_units) -> list[dict]:
    """要件・設計の全単位から TABLE_MISMATCH の指摘を返す。"""
    found = (_table_vs_table(req_units, design_units)
             + _field_lengths(req_units, design_units)
             + _code_values(design_units))
    seen, out = set(), []
    for d in found:
        key = (tuple(d["req_lines"]), tuple(d["design_lines"]))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out
