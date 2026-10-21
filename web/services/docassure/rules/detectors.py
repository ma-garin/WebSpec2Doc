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
                out.hits.append(Hit(ln.no, f"「別紙{m.group(1)}」が文書内にも他文書にも無い", 0.8, ("別紙の照合",)))
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


def detect_term_variance(ctx: Ctx) -> Outcome:
    p = ctx.params
    out = Outcome()
    markers = p.get("term_define_markers", [])
    for group in p.get("term_groups", []):
        rxs = [(g, re.compile(g)) for g in group]
        first, defined = {}, set()
        for ln in ctx.lines:
            for g, rx in rxs:
                m = rx.search(ln.text)
                if m:
                    first.setdefault(g, ln.no)
                    if any(mk in ln.text[m.end():m.end() + 6] for mk in markers):
                        defined.add(g)
        if not first:
            continue
        out.checked += 1
        if len(first) < 2 or len(defined) >= 2:
            continue  # 1 語のみ、または各語が用語定義で区別されている
        order = sorted(first.items(), key=lambda kv: kv[1])
        out.hits.append(Hit(order[1][1], "表記揺れ候補: " + "・".join(f"「{g}」(初出 行{n})" for g, n in order), 0.4,
                            ("同一グループの語が混在",), ("同義とは断定できない。別の対象を指す可能性",)))
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


def detect_number_range(ctx: Ctx) -> Outcome:
    u = ctx.unit_re
    n = r"(?<![A-Za-z0-9._\-/:])(\d[\d,]*(?:\.\d+)?)\s*(%s)?" % u
    tilde = re.compile(n + r"\s*(?:〜|~|～|から)\s*(\d[\d,]*(?:\.\d+)?)\s*(%s)?" % u)
    upper = re.compile(n + r"\s*以上[^。\d]{0,12}?(\d[\d,]*(?:\.\d+)?)\s*(%s)?\s*(?:以下|未満)" % u)
    out = Outcome()
    for ln in ctx.lines:
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
    if out.checked == 0:
        out.skip = "範囲表現（A〜B・A以上B以下）が文書に無い"
    return out


def detect_required_items(ctx: Ctx) -> Outcome:
    items = ctx.params.get("required_items", [])
    if not items:
        return Outcome(skip="必須項目が未設定（extra で指定する）")
    text = "\n".join(ln.text for ln in ctx.lines)
    out = Outcome(checked=len(items))
    for it in items:
        names = it if isinstance(it, list) else [it]
        if not any(n in text for n in names):
            out.hits.append(Hit(1, f"必須項目「{names[0]}」が文書に無い", 0.8, ("語の有無",)))
    return out


DETECTORS = {
    "ambiguity": detect_ambiguity, "tbd": detect_tbd, "placeholder": detect_placeholder,
    "broken_ref": detect_broken_ref, "id_duplicate": detect_id_duplicate, "id_gap": detect_id_gap,
    "id_format": detect_id_format, "id_orphan": detect_id_orphan, "term_variance": detect_term_variance,
    "number_unit": detect_number_unit, "number_range": detect_number_range, "required_items": detect_required_items,
}
