"""PostgreSQL の DDL を規則だけで読み、事実を根拠行付きで取り出す（LLM 不使用）。

1 事実 = 1 dict: {"kind","name","attrs","origin","source":{"file","line","text"}}
kind: table / column / constraint / relation / index / comment。
読めなかった文は黙って捨てず unread（別名 unparsed）に行番号付きで返す。
"""
import re

_KEYWORDS = (r"NOT\s+NULL|NULL|DEFAULT|PRIMARY\s+KEY|UNIQUE|CHECK|REFERENCES|"
             r"CONSTRAINT|GENERATED|COLLATE")
_KW_RE = re.compile(r"(?:%s)\b" % _KEYWORDS, re.I)
_IDENT = r'(?:"(?:[^"]|"")*"|[A-Za-z_][\w$]*)'
_QNAME = r"%s(?:\s*\.\s*%s)*" % (_IDENT, _IDENT)


def read_ddl(text, file):
    """DDL 全文を読み、{"facts": [...], "unread": [...], "unparsed": [...]} を返す。"""
    text = text or ""
    masked = _mask(text)
    starts = _line_starts(text)
    facts, unread = [], []
    for s, e in _statements(masked):
        stmt = masked[s:e]
        ctx = (text, starts, file, s, e, masked)
        try:
            got = _parse_statement(stmt, s, ctx)
        except ValueError as exc:
            got = None
            reason = str(exc)
        else:
            reason = "対応していない文です。内容を確認してください。"
        if got is None:
            unread.append({"file": file, "line": _line(starts, _first(masked, s)),
                           "reason": reason, "text": _squash(text[s:e])})
        else:
            facts.extend(got)
    return {"facts": facts, "unread": unread, "unparsed": unread}


# ---- 字句 ----------------------------------------------------------------
def _mask(text):
    """コメントを空白に置換（改行は保持）。文字列・引用識別子は残す。"""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i)); i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", text[i:j])); i = j
        elif c in "'\"" or c == "$":
            j = _skip_quoted(text, i)
            out.append(text[i:j]); i = j
        else:
            out.append(c); i += 1
    return "".join(out)


def _skip_quoted(s, i):
    """i が引用の開始なら終端の次の位置を返す。引用でなければ i+1。"""
    c = s[i]
    if c in "'\"":
        j = i + 1
        while j < len(s):
            if s[j] == c:
                if s.startswith(c, j + 1):
                    j += 2; continue
                return j + 1
            j += 1
        return len(s)
    m = re.compile(r"\$[A-Za-z_]*\$").match(s, i)
    if not m:
        return i + 1
    k = s.find(m.group(0), m.end())
    return len(s) if k < 0 else k + len(m.group(0))


def _scan(s, base=0):
    """引用の外の (位置, 文字, 括弧深さ) を順に返す。"""
    depth, i = 0, 0
    while i < len(s):
        c = s[i]
        if c in "'\"$":
            j = _skip_quoted(s, i)
            if j > i + 1 or c != "$":
                i = j; continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        yield base + i, c, depth
        i += 1


def _statements(masked):
    start = 0
    for pos, c, _ in _scan(masked):
        if c == ";":
            if masked[start:pos].strip():
                yield start, pos
            start = pos + 1
    if masked[start:].strip():
        yield start, len(masked)


def _split_top(s, base):
    """括弧の外のカンマで分割し、(開始, 終了) の絶対位置を返す。"""
    parts, start = [], 0
    for pos, c, depth in _scan(s):
        if c == "," and depth == 0:
            parts.append((base + start, base + pos)); start = pos + 1
    parts.append((base + start, base + len(s)))
    return [(a, b) for a, b in parts if s[a - base:b - base].strip()]


def _line_starts(text):
    return [0] + [m.end() for m in re.finditer(r"\n", text)]


def _line(starts, pos):
    lo, hi = 0, len(starts)
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if starts[mid] <= pos:
            lo = mid
        else:
            hi = mid
    return lo + 1


def _first(masked, s):
    m = re.compile(r"\S").search(masked, s)
    return m.start() if m else s


def _squash(t):
    return re.sub(r"\s+", " ", t).strip()


def _unq(name):
    parts = re.findall(_IDENT, name)
    return ".".join(p[1:-1].replace('""', '"') if p.startswith('"') else p.lower()
                    for p in parts)


def _cols(s):
    return [_unq(c) for c in re.findall(_IDENT, s)]


def _take_expr(s):
    """s の先頭から、括弧の外で次の制約語に当たるまでの式と残りを返す。"""
    s = s.lstrip()
    for pos, c, depth in _scan(s):
        if c.isspace() and depth == 0 and _KW_RE.match(s[pos:].lstrip()):
            return s[:pos].strip(), s[pos:]
    return s.strip(), ""


def _paren(s):
    """先頭が ( の文字列から対応する ) までの中身と残りを返す。"""
    for pos, c, depth in _scan(s):
        if c == ")" and depth == 0:
            return s[1:pos], s[pos + 1:]
    raise ValueError("括弧が閉じていません。対象の文を確認してください。")


# ---- 文の解析 -------------------------------------------------------------
def _fact(kind, name, attrs, ctx, a, b=None):
    text, starts, file, _s, _e, masked = ctx
    b = a if b is None else b
    first = _first(masked, a)
    return {"kind": kind, "name": name, "attrs": attrs, "origin": "ddl",
            "source": {"file": file, "line": _line(starts, first),
                       "text": _squash(text[a:b])}}


def _parse_statement(stmt, s, ctx):
    head = stmt.strip()
    m = re.match(r"CREATE\s+(?:(?:GLOBAL|LOCAL)\s+)?(?:(?:UNLOGGED|TEMP|TEMPORARY)\s+)?"
                 r"TABLE\s+(IF\s+NOT\s+EXISTS\s+)?(%s)\s*\(" % _QNAME, head, re.I)
    if m:
        return _create_table(stmt, s, ctx, _unq(m.group(2)), bool(m.group(1)))
    m = re.match(r"CREATE\s+(UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?"
                 r"(%s)?\s*ON\s+(?:ONLY\s+)?(%s)\s*(?:USING\s+(\w+))?\s*\(" % (_IDENT, _QNAME),
                 head, re.I)
    if m:
        return _create_index(head, ctx, m)
    m = re.match(r"COMMENT\s+ON\s+(TABLE|COLUMN|INDEX|CONSTRAINT)\s+(%s)\s+IS\s+"
                 r"('(?:[^']|'')*'|NULL)\s*$" % (_QNAME + r"(?:\s+ON\s+" + _QNAME + ")?"),
                 head, re.I | re.S)
    if m:
        t = m.group(3)
        text = None if t.upper() == "NULL" else t[1:-1].replace("''", "'")
        return [_fact("comment", _unq(m.group(2).split()[0]),
                      {"target_kind": m.group(1).lower(), "text": text}, ctx, s, ctx[4])]
    m = re.match(r"ALTER\s+TABLE\s+(?:ONLY\s+)?(?:IF\s+EXISTS\s+)?(%s)\s+ADD\s+(CONSTRAINT\s.*|"
                 r"PRIMARY\s.*|UNIQUE\s.*|FOREIGN\s.*|CHECK\s.*)$" % _QNAME, head, re.I | re.S)
    if m:
        got = _table_constraint(_unq(m.group(1)), m.group(2), ctx, s, ctx[4])
        if got:
            return got
        raise ValueError("ALTER TABLE の制約を読めませんでした。制約の書き方を確認してください。")
    return None


def _create_table(stmt, s, ctx, table, if_not_exists):
    open_i = stmt.index("(", re.match(r"\s*CREATE.*?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?%s\s*" % _QNAME,
                                      stmt, re.I | re.S).end())
    inner, _rest = _paren(stmt[open_i:])
    facts = [_fact("table", table, {"if_not_exists": if_not_exists}, ctx, s, ctx[4])]
    base = s + open_i + 1
    for a, b in _split_top(inner, base):
        item = ctx[0][a:b]
        masked_item = inner[a - base:b - base]
        got = _table_constraint(table, masked_item.strip(), ctx, a, b) \
            if re.match(r"\s*(CONSTRAINT|PRIMARY|UNIQUE|CHECK|FOREIGN)\b", masked_item, re.I) \
            else _column(table, masked_item.strip(), ctx, a, b)
        if got is None:
            raise ValueError("%s の定義を読めませんでした。書き方を確認してください。"
                             % _squash(item)[:40])
        facts.extend(got)
    return facts


def _column(table, item, ctx, a, b):
    m = re.match(r"(%s)\s+(.*)$" % _IDENT, item, re.S)
    if not m:
        return None
    col, rest = _unq(m.group(1)), m.group(2)
    tm = re.match(r"(.*?)(?=\s+%s|$)" % _KW_RE.pattern, rest, re.S | re.I)
    ctype = _squash(tm.group(1))
    rest = rest[tm.end():]
    attrs = {"table": table, "column": col, "type": ctype, "not_null": False,
             "primary_key": False, "unique": False, "default": None, "check": None,
             "references": None}
    extra = []
    while rest.strip():
        mm = re.match(r"\s*(CONSTRAINT\s+%s\s+)?(NOT\s+NULL|NULL|PRIMARY\s+KEY|UNIQUE|DEFAULT|CHECK|"
                      r"REFERENCES|GENERATED|COLLATE)\b" % _IDENT, rest, re.I)
        if not mm:
            return None
        kw, rest = _squash(mm.group(2)).upper(), rest[mm.end():]
        if kw == "NOT NULL":
            attrs["not_null"] = True
        elif kw == "PRIMARY KEY":
            attrs["primary_key"], attrs["not_null"] = True, True
        elif kw == "UNIQUE":
            attrs["unique"] = True
        elif kw == "DEFAULT":
            attrs["default"], rest = _take_expr(rest)
        elif kw == "CHECK":
            inner, rest = _paren(rest.lstrip())
            attrs["check"] = _squash(inner)
        elif kw == "REFERENCES":
            rm = re.match(r"\s*(%s)\s*(\()?" % _QNAME, rest)
            ref_cols = []
            rest = rest[rm.end():] if rm else rest
            if rm and rm.group(2):
                inner, rest = _paren("(" + rest)
                ref_cols = _cols(inner)
            attrs["references"] = {"table": _unq(rm.group(1)) if rm else "", "columns": ref_cols}
            rest, actions = _fk_actions(rest)
            attrs["references"].update(actions)
        elif kw in ("GENERATED", "COLLATE"):
            extra.append(kw.lower())
            rest = _take_expr(rest)[1]
    out = [_fact("column", "%s.%s" % (table, col), attrs, ctx, a, b)]
    if attrs["references"]:
        r = attrs["references"]
        out.append(_fact("relation", "%s.%s->%s" % (table, col, r["table"]),
                         {"table": table, "columns": [col], "ref_table": r["table"],
                          "ref_columns": r["columns"], "on_delete": r.get("on_delete"),
                          "on_update": r.get("on_update"), "constraint": None}, ctx, a, b))
    return out


def _fk_actions(rest):
    acts = {}
    for m in re.finditer(r"ON\s+(DELETE|UPDATE)\s+(NO\s+ACTION|RESTRICT|CASCADE|SET\s+NULL|"
                         r"SET\s+DEFAULT)", rest, re.I):
        acts["on_" + m.group(1).lower()] = _squash(m.group(2)).upper()
    cut = re.sub(r"ON\s+(?:DELETE|UPDATE)\s+(?:NO\s+ACTION|RESTRICT|CASCADE|SET\s+NULL|"
                 r"SET\s+DEFAULT)", " ", rest, flags=re.I)
    return cut, acts


def _table_constraint(table, item, ctx, a, b):
    cname = None
    m = re.match(r"CONSTRAINT\s+(%s)\s+" % _IDENT, item, re.I)
    if m:
        cname, item = _unq(m.group(1)), item[m.end():]
    m = re.match(r"(PRIMARY\s+KEY|UNIQUE|FOREIGN\s+KEY|CHECK)\s*(\(.*)$", item, re.I | re.S)
    if not m:
        return None
    kw = _squash(m.group(1)).upper()
    inner, rest = _paren(m.group(2))
    if kw == "CHECK":
        attrs = {"type": "check", "table": table, "expr": _squash(inner), "constraint": cname}
        return [_fact("constraint", cname or "%s.check" % table, attrs, ctx, a, b)]
    cols = _cols(inner)
    if kw != "FOREIGN KEY":
        t = "primary_key" if kw == "PRIMARY KEY" else "unique"
        attrs = {"type": t, "table": table, "columns": cols, "constraint": cname}
        return [_fact("constraint", cname or "%s.%s" % (table, t), attrs, ctx, a, b)]
    rm = re.match(r"\s*REFERENCES\s+(%s)\s*(\()?" % _QNAME, rest, re.I)
    if not rm:
        return None
    rest, ref_cols = rest[rm.end():], []
    if rm.group(2):
        rin, rest = _paren("(" + rest)
        ref_cols = _cols(rin)
    _rest, acts = _fk_actions(rest)
    ref = _unq(rm.group(1))
    attrs = {"table": table, "columns": cols, "ref_table": ref, "ref_columns": ref_cols,
             "on_delete": acts.get("on_delete"), "on_update": acts.get("on_update"),
             "constraint": cname}
    return [_fact("relation", cname or "%s(%s)->%s" % (table, ",".join(cols), ref),
                  attrs, ctx, a, b)]


def _create_index(head, ctx, m):
    inner, rest = _paren(head[m.end() - 1:])
    where = re.search(r"\bWHERE\s+(.*)$", rest, re.I | re.S)
    table = _unq(m.group(3))
    name = _unq(m.group(2)) if m.group(2) else "%s.idx" % table
    attrs = {"table": table, "unique": bool(m.group(1)), "method": (m.group(4) or "btree").lower(),
             "columns": [_squash(c) for c in _split_cols(inner)],
             "where": _squash(where.group(1)) if where else None}
    return [_fact("index", name, attrs, ctx, ctx[3], ctx[4])]


def _split_cols(s):
    return [s[a:b] for a, b in _split_top(s, 0)]
