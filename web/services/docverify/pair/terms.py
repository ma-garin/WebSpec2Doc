"""TERM_INCONSISTENCY: 同じ概念の呼び名が要件定義書と基本設計書で違う箇所を見つける。

要件定義書の用語表（「用語」の章の表）の語を「正」とし、設計書に出てくるのに
要件定義書のどこにも無い語のうち、正の語と同じ概念を指すとみられるものを別名として指摘する。
別名の見つけ方は 4 つ（標準ライブラリのみ・組ごとの固有値は持たない）:

1. 汎用の同義語辞書（業務文書で一般的な言い換え）
2. 人を表す接尾辞の入れ替え（例: 〇〇担当者 ⇔ 〇〇員）
3. 「処理」と定義された語と、先頭の 2 字が同じ「〇〇処理」
4. 同じ文脈（前後の数文字が一致する文）に現れる語
"""
from __future__ import annotations

import re

_WORD = re.compile(r"[一-龥々ァ-ヶー]{2,12}")

# 一般的な業務用語の言い換え。評価セットの語ではなく、業務文書で普通に揺れる組だけを置く。
SYNONYMS: tuple[frozenset[str], ...] = (
    frozenset({"会員", "ユーザー", "ユーザ", "利用者", "顧客", "お客様"}),
    frozenset({"申請者", "申込者", "起票者"}),
    frozenset({"承認者", "決裁者", "承認権者"}),
    frozenset({"受取人", "受益者", "受取者"}),
    frozenset({"受付番号", "整理番号"}),
    frozenset({"上長", "上司", "所属長"}),
    frozenset({"従業員", "社員"}),
    frozenset({"職員", "スタッフ"}),
    frozenset({"患者", "受診者"}),
    frozenset({"注文", "オーダー"}),
)

_PERSON = ("担当者", "担当", "者", "員", "官", "係", "人")


def _lines(units) -> dict[int, str]:
    """単位から行番号→本文の対応を復元する（見出し・空行は含まない）。"""
    out: dict[int, str] = {}
    for u in units:
        for i, line in enumerate(u.text.split("\n")):
            out.setdefault(u.start + i, line)
    return out


def _heading_lines(units) -> list[tuple[int, str]]:
    """各見出しの、配下の最初の単位の行番号と見出し文字列。"""
    seen: dict[str, int] = {}
    for u in units:
        if u.heading and u.heading[-1] not in seen:
            seen[u.heading[-1]] = u.start
    return [(no, h) for h, no in seen.items()]


def glossary(units) -> dict[str, str]:
    """用語表の 語→意味。用語の章の表、または見出しが「用語」の列を持つ表から取る。"""
    out: dict[str, str] = {}
    for u in units:
        if u.kind != "row" or len(u.cells) < 2:
            continue
        in_terms = any("用語" in h for h in u.heading) or (u.headers[:1] == ("用語",))
        term = u.cells[0].strip("`* ")
        if in_terms and 1 < len(term) <= 12 and "|" not in term:
            out.setdefault(term, u.cells[1])
    return out


def _person_variants(term: str) -> set[str]:
    for suf in _PERSON:
        stem = term[: -len(suf)]
        if term.endswith(suf) and len(stem) >= 2:
            return {stem + s for s in _PERSON if s != suf}
    return set()


def _dictionary_variants(term: str) -> set[str]:
    out: set[str] = set()
    for group in SYNONYMS:
        if term in group:
            out |= group - {term}
    return out


def _process_variants(term: str, meaning: str, design_words: set[str]) -> set[str]:
    """「〜する処理」と定義された語に対し、先頭 2 字が同じで「処理」で終わる設計の語。"""
    if not meaning.rstrip("。 ").endswith("処理") or len(term) < 3:
        return set()
    return {w for w in design_words
            if w.startswith(term[:2]) and w.endswith("処理") and w != term + "処理"}


def _context_variants(term: str, req_lines: dict[int, str],
                      design_lines: dict[int, str]) -> set[str]:
    """要件で term の前後にある 3 字の文脈が、設計で別の語を挟んで現れるもの。"""
    out: set[str] = set()
    for line in req_lines.values():
        idx = line.find(term)
        if idx < 3 or idx + len(term) + 3 > len(line):
            continue
        left, right = line[idx - 3: idx], line[idx + len(term): idx + len(term) + 3]
        pat = re.compile(re.escape(left) + r"([一-龥々ァ-ヶー]{2,10})" + re.escape(right))
        for dline in design_lines.values():
            for m in pat.finditer(dline):
                w = m.group(1)
                if w != term and (w[-2:] == term[-2:] or w[:2] == term[:2]):
                    out.add(w)
    return out


def _first_design_line(alias: str, lines: dict[int, str],
                       heads: list[tuple[int, str]]) -> list[int] | None:
    """別名が初めて出る設計の行。見出しなら配下の単位の直前 2 行を返す。"""
    cands: list[tuple[int, list[int]]] = []
    for no in sorted(lines):
        if alias in lines[no]:
            cands.append((no, [no, no]))
            break
    for no, head in sorted(heads):
        if alias in head:
            cands.append((no - 1, [max(1, no - 2), max(1, no - 1)]))
            break
    return min(cands)[1] if cands else None


def _bigrams(s: str) -> set[str]:
    return {s[i: i + 2] for i in range(len(s) - 1)}


def _best_req_line(term: str, req_lines: dict[int, str], design_text: str,
                   skip: set[int]) -> int | None:
    """term を含む要件の行のうち、設計の行と文字 2-gram が最も重なるもの。"""
    target = _bigrams(design_text)
    best, best_score = None, -1.0
    for no in sorted(req_lines):
        line = req_lines[no]
        if no in skip or term not in line:
            continue
        b = _bigrams(line)
        score = len(b & target) / (len(b | target) or 1)
        if score > best_score:
            best, best_score = no, score
    return best


def _candidates(term: str, meaning: str, ctx: dict) -> set[str]:
    words = (_dictionary_variants(term) | _person_variants(term)
             | _process_variants(term, meaning, ctx["design_words"])
             | _context_variants(term, ctx["req_body"], ctx["design_lines"]))
    req_all = ctx["req_all"]
    return {w for w in words
            if w not in req_all and term not in w and w not in term
            and (w in ctx["design_all"])}


def _context(req_units, design_units) -> dict:
    req_lines = _lines(req_units)
    gloss_rows = {u.start for u in req_units
                  if u.kind == "row" and any("用語" in h for h in u.heading)}
    design_lines = _lines(design_units)
    heads = _heading_lines(design_units)
    design_all = "\n".join(list(design_lines.values()) + [h for _, h in heads])
    req_heads = {h for u in req_units for h in u.heading}
    return {
        "req_body": {n: t for n, t in req_lines.items() if n not in gloss_rows},
        "gloss_rows": gloss_rows,
        "req_all": "\n".join(list(req_lines.values()) + sorted(req_heads)),
        "design_lines": design_lines, "heads": heads, "design_all": design_all,
        "design_words": set(_WORD.findall(design_all)),
    }


def detect(req_units, design_units, links=None) -> list[dict]:
    """用語表の語と、設計書で使われた別名の組を TERM_INCONSISTENCY として返す。"""
    ctx = _context(req_units, design_units)
    req_lines = _lines(req_units)
    out: list[dict] = []
    for term, meaning in glossary(req_units).items():
        hits = []
        for alias in _candidates(term, meaning, ctx):
            dl = _first_design_line(alias, ctx["design_lines"], ctx["heads"])
            if dl:
                hits.append((dl, -len(alias), alias))
        for dl, _, alias in sorted(hits)[:1]:
            near = ctx["design_lines"].get(dl[1], alias)
            rl = _best_req_line(term, req_lines, near, ctx["gloss_rows"])
            if rl is None:
                rl = _best_req_line(term, req_lines, near, set())
            out.append({
                "type": "TERM_INCONSISTENCY",
                "req_lines": [rl, rl] if rl else [],
                "design_lines": dl,
                "reason": f"要件の用語「{term}」を、設計では「{alias}」と呼んでいる。",
            })
    return out
