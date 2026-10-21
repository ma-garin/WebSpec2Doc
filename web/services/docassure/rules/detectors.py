"""決定論の検出器。語彙・閾値は pack の params から受け取り、ここには持たない。

各検出器は detect_xxx(ctx) -> Outcome。評価材料が無いときは skip を返し PASS にしない。
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_STRIP = re.compile(r"^[\s>#*\-+|_]+")
_SEC_NO = re.compile(r"^\s*(?:#{1,6}\s*)?(\d+(?:\.\d+)*)(?:[\s.．、）)]|$)")
_NUM = r"(?<![A-Za-z0-9._\-/:])(\d[\d,]*(?:\.\d+)?)"


@dataclass(frozen=True)
class Line:
    no: int
    text: str
    section: str


@dataclass(frozen=True)
class Hit:
    line: int
    reason: str
    confidence: float
    basis: tuple = ()
    counter: tuple = ()


@dataclass
class Outcome:
    hits: list = field(default_factory=list)
    checked: int = 0
    skip: str = ""          # 空でなければ NOT_EVALUATED の理由


class Ctx:
    def __init__(self, markdown: str, params: dict, other_docs: dict | None):
        self.params = params
        self.other_docs = other_docs or {}
        self.lines = _scan(markdown)
        self._ids = None

    @property
    def unit_re(self) -> str:
        units = sorted(self.params.get("units", {}), key=len, reverse=True)
        return "(?:" + "|".join(re.escape(u) + (r"(?![A-Za-z])" if u.isascii() and u.isalpha() else "") for u in units) + ")"

    def id_re(self) -> re.Pattern:
        pre = "|".join(re.escape(p) for p in self.params.get("id_prefixes", []))
        return re.compile(r"(?<![A-Za-z0-9])((?:%s))([-_]?)(\d{1,5})(?![A-Za-z0-9])" % pre, re.I)

    def ids(self, lines=None):
        """(定義, 参照) = ([(key, token, line, digits)], [(key, token, line)])。行頭の最初の ID だけが定義。"""
        pat = self.id_re()
        defs, refs = [], []
        for ln in (self.lines if lines is None else lines):
            body = _STRIP.sub("", ln.text)
            lead = len(ln.text) - len(body)
            for i, m in enumerate(pat.finditer(ln.text)):
                key = (m.group(1).upper(), int(m.group(3)))
                is_def = i == 0 and m.start() <= lead and not re.match(r"\s*(?:参照|see)", ln.text[m.end():], re.I)
                (defs if is_def else refs).append((key, m.group(0), ln.no, m.group(3), m.group(2), m.group(1)) if is_def else (key, m.group(0), ln.no))
        return defs, refs


def _scan(markdown: str) -> list[Line]:
    out, stack, fence = [], [], False
    for i, raw in enumerate((markdown or "").splitlines(), 1):
        if raw.strip().startswith("```"):
            fence = not fence
            continue
        if fence or not raw.strip():
            continue
        m = _HEADING.match(raw)
        if m:
            lv = len(m.group(1))
            stack = [s for s in stack if s[0] < lv] + [(lv, m.group(2))]
        out.append(Line(i, raw.rstrip(), " > ".join(t for _, t in stack)))
    return out


def _window_has_number(ctx: Ctx, text: str, s: int, e: int) -> bool:
    w = ctx.params.get("numeric_window", 12)
    seg = text[max(0, s - w): e + w]
    return bool(re.search(r"\d[\d,\.]*\s*" + ctx.unit_re, seg))


def detect_ambiguity(ctx: Ctx) -> Outcome:
    if not ctx.lines:
        return Outcome(skip="本文が空")
    terms = list(ctx.params.get("ambiguous_terms", []))
    comp = [(t, re.compile(t["pattern"], re.I if t.get("ignore_case") else 0)) for t in terms]
    out = Outcome(checked=len(ctx.lines))
    for ln in ctx.lines:
        for t, rx in comp:
            for m in rx.finditer(ln.text):
                s, e = m.span()
                if ln.text[max(0, s - 1):s] == "「" and ln.text[e:e + 1] == "」":
                    continue  # 語そのものを引用しているだけ
                if t.get("numeric_exempt") and _window_has_number(ctx, ln.text, s, e):
                    continue  # 近傍に数値と単位があり定義済み
                if any(ln.text.startswith(f, e) for f in t.get("follow_exempt", [])):
                    continue  # 画面名・モード名などの名称用法
                if any(h.line == ln.no for h in out.hits):
                    continue  # 同一行の 2 語目以降は同じ指摘として 1 件にまとめる
                out.hits.append(Hit(ln.no, f"曖昧語「{m.group(0)}」: {ln.text.strip()[max(0, s - 10):e + 10]}", 0.7,
                                    ("語彙一致", "近傍に数値定義なし"), ("文脈によっては許容される用法の可能性",)))
    return out


def _pattern_hits(ctx: Ctx, pats: list, label: str, conf: float) -> Outcome:
    if not ctx.lines:
        return Outcome(skip="本文が空")
    rx = [re.compile(p) for p in pats]
    out = Outcome(checked=len(ctx.lines))
    for ln in ctx.lines:
        for r in rx:
            m = r.search(ln.text)
            if m:
                out.hits.append(Hit(ln.no, f"{label}「{m.group(0)}」が残っている", conf, ("パターン一致",)))
                break
    return out


def detect_tbd(ctx: Ctx) -> Outcome:
    return _pattern_hits(ctx, ctx.params.get("tbd_patterns", []), "未決の印", 0.85)


def detect_placeholder(ctx: Ctx) -> Outcome:
    if not ctx.lines:
        return Outcome(skip="本文が空")
    out = Outcome(checked=len(ctx.lines))
    for ln in ctx.lines:
        for p in ctx.params.get("placeholder_patterns", []):
            for m in re.finditer(p["pattern"], ln.text):
                if any(ln.text.startswith(x, m.end()) for x in p.get("exempt_after", [])):
                    continue
                out.hits.append(Hit(ln.no, f"仮置き値「{m.group(0)}」({p['label']})が残っている", 0.75, ("パターン一致",)))
                break
    return out


def _section_numbers(lines) -> set:
    nums = set()
    for ln in lines:
        m = _SEC_NO.match(ln.text)
        if m:
            parts = m.group(1).split(".")
            nums.update(".".join(parts[:i]) for i in range(1, len(parts) + 1))
    return nums


def _is_appendix_def(text: str, name: str, pat: str) -> bool:
    return bool(re.match(pat.replace("([A-ZＡ-Ｚ0-9０-９]+)", re.escape(name)), _STRIP.sub("", text)))


def detect_broken_ref(ctx: Ctx) -> Outcome:
    p = ctx.params
    if not ctx.lines:
        return Outcome(skip="本文が空")
    other_lines = [ln for md in ctx.other_docs.values() for ln in _scan(md)]
    sec_nums = _section_numbers(ctx.lines)
    other_secs = _section_numbers(other_lines)
    app_pat = p["ref_appendix_pattern"]
    app_defs = {m.group(1) for ln in ctx.lines + other_lines
                if (m := re.match(app_pat, _STRIP.sub("", ln.text)))}
    own_defs, _ = ctx.ids()
    other_defs, _ = ctx.ids(other_lines)
    all_def_keys = {d[0] for d in own_defs} | {d[0] for d in other_defs}
    _, id_refs = ctx.ids()
    out, unresolvable = Outcome(), 0
    sec_rx = [re.compile(x) for x in p.get("ref_section_patterns", [])]
    for ln in ctx.lines:
        for rx in sec_rx:
            for m in rx.finditer(ln.text):
                if not sec_nums and not other_secs:
                    unresolvable += 1
                    continue
                out.checked += 1
                if m.group(1) not in sec_nums | other_secs:
                    out.hits.append(Hit(ln.no, f"「{m.group(0)}」の参照先（節 {m.group(1)}）が文書内に無い", 0.8, ("節番号の照合",)))
        for m in re.finditer(app_pat, ln.text):
            if re.match(app_pat, _STRIP.sub("", ln.text)) and re.match(app_pat, _STRIP.sub("", ln.text)).group(1) == m.group(1):
                continue  # 定義行そのもの
            out.checked += 1
            if m.group(1) not in app_defs:
                out.hits.append(Hit(ln.no, f"「{m.group(0).strip()}」が文書内にも他文書にも無い", 0.8, ("別紙の照合",)))
    if all_def_keys:
        for key, tok, no in id_refs:
            out.checked += 1
            if key not in all_def_keys:
                out.hits.append(Hit(no, f"参照先ID「{tok}」の定義が無い", 0.8, ("ID定義の照合",)))
    elif id_refs:
        unresolvable += len(id_refs)
    if out.checked == 0:
        out.skip = "参照表現が無い、または参照先を判定する材料（節番号・ID定義・他文書）が無い" if not unresolvable else "参照先を判定する材料（節番号・ID定義・他文書）が無い"
    return out


def detect_id_duplicate(ctx: Ctx) -> Outcome:
    defs, _ = ctx.ids()
    if not defs:
        return Outcome(skip="IDの定義が文書に無い")
    seen, out = defaultdict(list), Outcome(checked=len(defs))
    for d in defs:
        seen[d[0]].append(d[2])
    for key, nos in seen.items():
        if len(nos) > 1:
            out.hits.append(Hit(nos[1], f"ID「{key[0]}-{key[1]}」が {len(nos)} 箇所で定義（行 {', '.join(map(str, nos))}）", 0.8,
                                ("同一IDの定義行が複数",), ("トレーサビリティ表の再掲の可能性",)))
    return out


def detect_id_gap(ctx: Ctx) -> Outcome:
    defs, _ = ctx.ids()
    by = defaultdict(dict)
    for key, _t, no, *_ in defs:
        by[key[0]].setdefault(key[1], no)
    groups = {k: v for k, v in by.items() if len(v) >= 2}
    if not groups:
        return Outcome(skip="連番を判定できるIDが2件以上の接頭辞が無い")
    out = Outcome(checked=len(groups))
    for pre, nums in groups.items():
        ordered = sorted(nums)
        missing = [n for n in range(ordered[0], ordered[-1] + 1) if n not in nums]
        if missing:
            nxt = next(n for n in ordered if n > missing[0])
            out.hits.append(Hit(nums[nxt], f"{pre} に欠番: {', '.join(str(m) for m in missing[:5])}{' ほか' if len(missing) > 5 else ''}", 0.4,
                                ("連番の途中が抜けている",), ("意図的な欠番・他文書で定義の可能性",)))
    return out


def detect_id_format(ctx: Ctx) -> Outcome:
    defs, _ = ctx.ids()
    if not defs:
        return Outcome(skip="IDの定義が文書に無い")
    width = defaultdict(Counter)
    for key, _t, _n, digits, _sep, _pre in defs:
        width[key[0]][len(digits)] += 1
    out = Outcome(checked=len(defs))
    for key, tok, no, digits, sep, pre in defs:
        dom, cnt = width[key[0]].most_common(1)[0]
        why = []
        if sep != "-":
            why.append("区切りがハイフンでない")
        if pre != pre.upper():
            why.append("接頭辞が大文字でない")
        if len(digits) != dom and cnt * 2 > sum(width[key[0]].values()):
            why.append(f"桁数が多数派（{dom}桁）と異なる")
        if why:
            out.hits.append(Hit(no, f"ID「{tok}」: " + "・".join(why), 0.8, ("多数派の形式との比較",)))
    return out


def detect_id_orphan(ctx: Ctx) -> Outcome:
    if not ctx.other_docs:
        return Outcome(skip="参照元となる他文書（other_docs）が無く孤立を判定できない")
    defs, refs = ctx.ids()
    if not defs:
        return Outcome(skip="IDの定義が文書に無い")
    _, orefs = ctx.ids([ln for md in ctx.other_docs.values() for ln in _scan(md)])
    odefs, _ = ctx.ids([ln for md in ctx.other_docs.values() for ln in _scan(md)])
    used = {r[0] for r in refs} | {r[0] for r in orefs} | {d[0] for d in odefs}
    out = Outcome(checked=len(defs))
    for d in defs:
        if d[0] not in used:
            out.hits.append(Hit(d[2], f"ID「{d[1]}」はどの文書からも参照されていない", 0.5,
                                ("文書群内で被参照 0",), ("文書群に含まれない成果物から参照されている可能性",)))
    return out


_ACRO = re.compile(r"(?<![A-Za-z0-9_\-])([A-Z][A-Z0-9]{1,5}|[A-Z][bcdfghjklmnpqrstvwxz]{2,4})(?![A-Za-z0-9_\-])")


def _undefined_acronyms(ctx: Ctx) -> Outcome:
    """略語（BCP・KPI など）が初出までに定義されているか。定義＝「略語（…）」「…（略語）」「略語とは」等。"""
    p = ctx.params
    known = {a.upper() for a in p.get("known_acronyms", [])}
    known |= {x.upper() for x in p.get("id_prefixes", [])}
    known |= {u.upper() for u in p.get("units", {})}
    markers = p.get("term_define_markers", [])
    text = "\n".join(ln.text for ln in ctx.lines)
    glossary = re.compile(r"^[\s>#*\-+|_・●○\d.)）]*(?:[A-Z]{2,4}-\d+\s+)?([A-Za-z][A-Za-z0-9]{1,5})\s*(?:[:：|｜]|とは)", re.M)
    gloss_defs = {m.group(1) for m in glossary.finditer(text)}  # 用語表・用語節の定義は初出より後ろにあってもよい
    out, seen = Outcome(), set()
    for ln in ctx.lines:
        fresh = []
        for m in _ACRO.finditer(ln.text):
            ac = m.group(1)
            if ac in known or ac in seen or ac in gloss_defs or re.fullmatch(r"[A-Z]+\d+", ac) and re.sub(r"\d+$", "", ac) in known:
                continue  # 既知の接頭辞＋数字（REQ104 など）は ID の表記違いで、略語ではない
            seen.add(ac)
            out.checked += 1
            tail, head = ln.text[m.end():m.end() + 8], ln.text[max(0, m.start() - 2):m.start()]
            defined = (tail.lstrip().startswith(("（", "(")) or head.rstrip().endswith(("（", "(")) or "：" in tail[:1]
                       or any(mk in tail for mk in markers) or re.search(r"[|｜]\s*" + re.escape(ac) + r"\s*[|｜]", ln.text)
                       or re.search(re.escape(ac) + r"\s*[:：]", ln.text)
                       or re.search(r"[（(]\s*" + re.escape(ac) + r"\s*[）)]", text))
            if not defined:
                fresh.append(ac)
        if fresh:
            out.hits.append(Hit(ln.no, "略語「" + "」「".join(fresh) + "」が初出時に定義されていない", 0.5,
                                ("略語の初出に定義（括弧書き・「とは」）が無い",), ("業界で自明な略語の可能性",)))
    return out


def _term_variance(ctx: Ctx) -> Outcome:
    p = ctx.params
    out = Outcome()
    markers = p.get("term_define_markers", [])
    for group in p.get("term_groups", []):
        rxs = [(g, re.compile(g)) for g in group]
        first, defined, together = {}, set(), False
        for ln in ctx.lines:
            on_line = set()
            for g, rx in rxs:
                m = rx.search(ln.text)
                if m:
                    first.setdefault(g, ln.no)
                    on_line.add(g)
                    if any(mk in ln.text[m.end():m.end() + 6] for mk in markers):
                        defined.add(g)
            if len(on_line) >= 2:
                together = True  # 同じ文に並べて書く＝別の対象として区別している形跡
        if not first:
            continue
        out.checked += 1
        if len(first) < 2 or len(defined) >= 2 or together:
            continue  # 1 語のみ、各語が用語定義で区別されている、または同一文に併記されている
        order = sorted(first.items(), key=lambda kv: kv[1])
        out.hits.append(Hit(order[1][1], "表記揺れ候補: " + "・".join(f"「{g}」(初出 行{n})" for g, n in order), 0.4,
                            ("同一グループの語が混在",), ("同義とは断定できない。別の対象を指す可能性",)))
    return out


def detect_term_variance(ctx: Ctx) -> Outcome:
    if not ctx.lines:
        return Outcome(skip="本文が空")
    a, b = _term_variance(ctx), _undefined_acronyms(ctx)
    out = Outcome(hits=a.hits + b.hits, checked=a.checked + b.checked)
    if out.checked == 0:
        out.skip = "対象の用語が文書に無い"
    return out


def _factor(ctx: Ctx, unit: str | None):
    return ctx.params["units"].get(unit) if unit else None


def detect_number_unit(ctx: Ctx) -> Outcome:
    p = ctx.params
    ctxw = p.get("unit_required_context", [])
    if not ctxw:
        return Outcome(skip="単位必須の文脈語が未定義")
    cw = "|".join(re.escape(w) for w in ctxw)
    follow = re.compile(p["unit_missing_follow"])
    unit = re.compile(ctx.unit_re)
    rx = re.compile(r"(?:%s)[^。\d]{0,15}?%s" % (cw, _NUM))
    out = Outcome()
    for ln in ctx.lines:
        for m in rx.finditer(ln.text):
            rest = ln.text[m.end():]
            if unit.match(rest.lstrip()):
                out.checked += 1
            elif follow.match(rest.lstrip()) or not rest.strip():
                out.checked += 1
                out.hits.append(Hit(ln.no, f"数値「{m.group(1)}」に単位が無い: {ln.text.strip()[:60]}", 0.7, ("時間・容量系の文脈語の直後",)))
    if out.checked == 0:
        out.skip = "単位が必要な数値（応答時間・容量など）が文書に無い"
    return out


_NUMV = r"(\d[\d,]*(?:\.\d+)?)"
_UNITV = r"([^\d\s以未超〜~～,、.|:：]{0,3})"
_IV_TILDE = re.compile(_NUMV + _UNITV + r"\s*(?:〜|~|～)\s*" + _NUMV + _UNITV)
_IV_LOW = re.compile(_NUMV + _UNITV + r"\s*(以上|超)(?:\s*" + _NUMV + _UNITV + r"\s*(以下|未満))?")
_IV_HIGH = re.compile(_NUMV + _UNITV + r"\s*(以下|未満)")
_LIST_MARK = re.compile(r"^\s*(?:[-*+・●○]|\d+[.)）])\s+")


def _interval(cell: str):
    """区分の見出しセルを (下限, 下限を含む, 上限, 上限を含む, 単位) に。解釈できなければ None。"""
    c = cell.strip()
    inf = float("inf")
    f = lambda x: float(x.replace(",", ""))
    m = _IV_TILDE.match(c)
    if m:
        return f(m.group(1)), True, f(m.group(3)), True, m.group(2) or m.group(4)
    m = _IV_LOW.match(c)
    if m:
        lo_inc = m.group(3) == "以上"
        if m.group(4):
            return f(m.group(1)), lo_inc, f(m.group(4)), m.group(6) == "以下", m.group(2) or m.group(5)
        return f(m.group(1)), lo_inc, inf, False, m.group(2)
    m = _IV_HIGH.match(c)
    if m:
        return -inf, False, f(m.group(1)), m.group(3) == "以下", m.group(2)
    return None


def _range_rows(ctx: Ctx):
    """連続する表の行・箇条書きの先頭セルを区分として読み、(行番号, 区間) の塊に分ける。"""
    groups, cur, last = [], [], None
    for ln in ctx.lines:
        t = ln.text.strip()
        if t.startswith("|"):
            cells = [x for x in t.strip("|").split("|") if x.strip()]
            key = cells[0] if cells else ""
        elif _LIST_MARK.match(ln.text):
            key = re.split(r"[:：]", _LIST_MARK.sub("", ln.text), 1)[0]
        else:
            key = None
        if key is None or (last is not None and ln.no != last + 1):
            if len(cur) >= 2:
                groups.append(cur)
            cur = []
        last = ln.no
        iv = _interval(key) if key else None
        if iv:
            cur.append((ln.no, iv))
    if len(cur) >= 2:
        groups.append(cur)
    return groups


_IV_INLINE = re.compile(_NUMV + _UNITV + r"\s*(以上|超)\s*" + _NUMV + _UNITV + r"\s*(以下|未満)")


def _inline_groups(ctx: Ctx):
    """1 文中に「A以上B以下」型の区分が 2 つ以上並ぶ記述（表でなく文章で書かれた区分）を区分の塊として返す。"""
    groups = []
    for ln in ctx.lines:
        if ln.text.strip().startswith("|"):
            continue
        row = []
        f = lambda x: float(x.replace(",", ""))
        for m in _IV_LOW.finditer(ln.text):
            if m.group(4):
                row.append((ln.no, (f(m.group(1)), m.group(3) == "以上", f(m.group(4)), m.group(6) == "以下", m.group(2) or m.group(5))))
            elif row:  # 上限の無い末尾の区分（「9日以上は…」）は、区分が先に並んでいるときだけ数える
                row.append((ln.no, (f(m.group(1)), m.group(3) == "以上", float("inf"), False, m.group(2))))
        # 同じ単位の区分が 2 つ以上、かつ範囲の読点区切り（同一条件の並列）に限る
        if len(row) >= 2 and len({iv[4] for _, iv in row}) == 1 and any(iv[2] != float("inf") for _, iv in row):
            groups.append(row)
    return groups


def _range_gaps(ctx: Ctx) -> Outcome:
    """区分表の隣り合う区分の間に、どの区分にも入らない値が残っていないか。"""
    out = Outcome()
    for g in _range_rows(ctx) + _inline_groups(ctx):
        units = {iv[4] for _, iv in g if iv[4]}
        if len(units) > 1:
            continue
        out.checked += 1
        rows = sorted(g, key=lambda r: (r[1][0], r[1][2]))
        whole = all(float(x).is_integer() for _, iv in rows for x in (iv[0], iv[2]) if abs(x) != float("inf"))
        step = 1 if whole else 0
        _, (_, _, hi, hi_inc, _) = rows[0]
        for no, (lo, lo_inc, nhi, nhi_inc, _) in rows[1:]:
            if whole:
                top, bottom = (hi if hi_inc else hi - 1), (lo if lo_inc else lo + 1)
                gap = bottom > top + step
                missing = f"{top + 1:g}" if bottom - top == 2 else f"{top + 1:g}〜{bottom - 1:g}"
            else:
                gap = lo > hi or (lo == hi and not hi_inc and not lo_inc)
                missing = f"{hi:g} と {lo:g} の間"
            if gap:
                out.hits.append(Hit(no, f"区分の境界に抜け: 直前の区分との間（{missing}）がどの区分にも入らない", 0.7,
                                    ("隣り合う区分の上限・下限の比較",), ("該当値が入力として発生しない可能性",)))
            if hi < nhi or (hi == nhi and nhi_inc):
                hi, hi_inc = nhi, nhi_inc
    return out


def detect_number_range(ctx: Ctx) -> Outcome:
    u = ctx.unit_re
    n = r"(?<![A-Za-z0-9._\-/:])(\d[\d,]*(?:\.\d+)?)\s*(%s)?" % u
    tilde = re.compile(n + r"\s*(?:〜|~|～|から)\s*(\d[\d,]*(?:\.\d+)?)\s*(%s)?" % u)
    upper = re.compile(n + r"\s*以上[^。\d]{0,12}?(\d[\d,]*(?:\.\d+)?)\s*(%s)?\s*(?:以下|未満)" % u)
    both = re.compile(n + r"\s*(以下|未満)\s*(?:かつ|、かつ|であり、?かつ)\s*(\d[\d,]*(?:\.\d+)?)\s*(%s)?\s*(以上|超)" % u)
    unspec = re.compile(r"(?:%s)?\s*(?:〜|~|～)\s*\d[\d,]*(?:\.\d+)?\s*(?:%s)?[^。]{0,6}?の?(?:扱い|動作|挙動|料金|処理)は(?:定めない|未定義|記載しない|未記載|規定しない|不明)" % (u, u))
    fuzzy = re.compile(n + r"\s*(前後|付近|近辺)")
    out = Outcome()
    for ln in ctx.lines:
        for m in both.finditer(ln.text):
            a, b = float(m.group(1).replace(",", "")), float(m.group(4).replace(",", ""))
            out.checked += 1
            if b > a:
                out.hits.append(Hit(ln.no, f"条件が矛盾: 「{m.group(0).strip()}」（上限 {m.group(1)} 以下かつ下限 {m.group(4)} 以上で満たす値が無い）", 0.8, ("上限と下限の数値比較",)))
        for m in unspec.finditer(ln.text):
            out.checked += 1
            out.hits.append(Hit(ln.no, f"範囲の境界が未定義: 「{m.group(0).strip()}」", 0.6, ("範囲に対し扱いが定められていない旨の記述",), ("別の節で定義されている可能性",)))
        for m in fuzzy.finditer(ln.text):
            out.checked += 1
            out.hits.append(Hit(ln.no, f"境界の包含が不明: 「{m.group(0).strip()}」", 0.5, ("「前後・付近」は境界値を含むか決められない",), ("文脈上の目安にすぎない可能性",)))
        for rx in (tilde, upper):
            for m in rx.finditer(ln.text):
                a, ua, b, ub = float(m.group(1).replace(",", "")), m.group(2), float(m.group(3).replace(",", "")), m.group(4)
                fa, fb = _factor(ctx, ua), _factor(ctx, ub)
                if fa and fb:
                    if fa[0] != fb[0]:
                        continue
                    a, b = a * fa[1], b * fb[1]
                elif ua and ub and ua != ub:
                    continue  # 換算できない異単位は比較しない
                out.checked += 1
                if a > b:
                    out.hits.append(Hit(ln.no, f"範囲が逆転: 「{m.group(0).strip()}」", 0.85, ("数値比較（単位換算あり）",)))
    sub = _range_gaps(ctx)
    out.hits += sub.hits
    out.checked += sub.checked
    if out.checked == 0:
        out.skip = "範囲表現（A〜B・A以上B以下）が文書に無い"
    return out


_QUOTED_RUN = re.compile(r"(?:[「『][^」』]{1,12}[」』][、,・と及びや]*){1,}")
_STATE_WORD = re.compile(r"(?:状態|ステータス)")
_STATE_REF = re.compile(r"[「『]([^」』]{1,12})[」』](?=\s*(?:状態|から|へ|に遷移|になっ))")
_STATE_OMIT = re.compile(r"状態(?:の扱い)?は(?:未記載|記載しない|定めない|未定義|規定しない)")


def _state_list(ln_text: str) -> set:
    """「状態は「A」「B」」「「A」「B」の状態を持つ」のように、状態語に隣接した引用語の並びを状態一覧とみなす。"""
    found = set()
    for m in _QUOTED_RUN.finditer(ln_text):
        before, after = ln_text[max(0, m.start() - 8):m.start()], ln_text[m.end():m.end() + 8]
        if re.search(r"(?:状態|ステータス)(?:は|として|を|の一覧は)?\s*$", before) or re.match(r"\s*(?:の|が)?\s*(?:状態|ステータス)", after):
            found |= set(re.findall(r"[「『]([^」』]{1,12})[」』]", m.group(0)))
    return found


def _state_gaps(ctx: Ctx) -> Outcome:
    """簡易の状態欠落: 状態一覧に無い状態が遷移・状態として参照されている／状態の扱いが未記載と明記されている。
    一覧に欠けがあるのは一覧側の欠陥なので、一覧を書いた行に報告する（参照行は理由に書く）。"""
    defined, def_line = set(), None
    for ln in ctx.lines:
        got = _state_list(ln.text)
        if got:
            defined |= got
            def_line = def_line or ln.no
    out = Outcome()
    reported = set()
    for ln in ctx.lines:
        if defined:
            refs = [x for x in _STATE_REF.findall(ln.text)]
            out.checked += len(refs)
            miss = [x for x in dict.fromkeys(refs) if x not in defined and x not in reported]
            if miss:
                reported |= set(miss)
                at = def_line if def_line else ln.no
                out.hits.append(Hit(at, "状態の欠落: 状態一覧に無い状態「" + "」「".join(miss) + f"」が参照されている（行 {ln.no}）", 0.6,
                                    ("状態一覧・遷移の照合",), ("別の節で定義されている可能性",)))
        if _STATE_OMIT.search(ln.text):
            out.checked += 1
            out.hits.append(Hit(ln.no, "状態の欠落: 状態の扱いが未記載と明記されている", 0.6, ("状態一覧・遷移の照合",), ("別の節で定義されている可能性",)))
    return out


def _typed_required(ctx: Ctx) -> Outcome:
    """文書種別（認証・アップロード等）ごとの必須項目。種別を判定できなければ評価しない。"""
    text = "\n".join(ln.text for ln in ctx.lines)
    out = Outcome()
    for t in ctx.params.get("required_items_by_type", []):
        found = [w for w in t["triggers"] if w in text]
        if len(found) < t.get("min_triggers", 3):
            continue  # 種別を判定する材料が足りない
        first = next(ln.no for ln in ctx.lines if any(w in ln.text for w in found))
        for it in t["items"]:
            names = it if isinstance(it, list) else [it]
            out.checked += 1
            if not any(n in text for n in names):
                out.hits.append(Hit(first, f"{t['type']}の必須項目「{names[0]}」が文書に無い", 0.6,
                                    (f"種別判定語 {len(found)} 語（{'・'.join(found[:3])}）",), ("別文書で定義されている可能性",)))
    return out


def detect_required_items(ctx: Ctx) -> Outcome:
    if not ctx.lines:
        return Outcome(skip="本文が空")
    items = ctx.params.get("required_items", [])
    text = "\n".join(ln.text for ln in ctx.lines)
    out = Outcome(checked=len(items))
    for it in items:
        names = it if isinstance(it, list) else [it]
        if not any(n in text for n in names):
            out.hits.append(Hit(1, f"必須項目「{names[0]}」が文書に無い", 0.8, ("語の有無",)))
    for sub in (_typed_required(ctx), _state_gaps(ctx)):
        out.hits += sub.hits
        out.checked += sub.checked
    if out.checked == 0:
        out.skip = "必須項目が未設定、かつ文書種別・状態の記述から評価できない（extra で指定する）"
    return out


DETECTORS = {
    "ambiguity": detect_ambiguity, "tbd": detect_tbd, "placeholder": detect_placeholder,
    "broken_ref": detect_broken_ref, "id_duplicate": detect_id_duplicate, "id_gap": detect_id_gap,
    "id_format": detect_id_format, "id_orphan": detect_id_orphan, "term_variance": detect_term_variance,
    "number_unit": detect_number_unit, "number_range": detect_number_range, "required_items": detect_required_items,
}
