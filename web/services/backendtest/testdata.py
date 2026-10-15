"""段階 5: テストデータ仕様の作成・投入データの生成（Faker・seed 固定）・マスキング。

入力の dict は変更せず、新しい dict / list を返す。同じ seed なら同じ出力になる。
facts は intake_ddl.read_ddl の形（kind/name/attrs）と、基本設計 3.2 の形（kind/subject/value）の両方を読む。
"""
import csv
import hashlib
import io
import random
import re

from faker import Faker

MAX_ROWS = 1000          # 「最大件数」の既定（案件で変える場合は仕様の rows を直す）
DEFAULT_ROWS = 3
SURROGATE = "\U00020BB7"  # 𠮷（UTF-16 でサロゲートペアになる文字）
FULLWIDTH = "ＡＢＣｱｲｳ全角あいうえおアイウエオ１２３"
HALFWIDTH = "ABCabc123"
DATE_EDGES = ("2024-02-29", "2026-01-31", "2026-12-31", "2026-01-01", "1970-01-01", "9999-12-31")

# 条件名 → ケース本文から拾う正規表現（上から順に判定。重複は除く）
_RULES = (
    ("0件", r"(?<![0-9])0\s*件|ゼロ件|空(?:テーブル|表)|データ(?:が)?(?:無|な)い"),
    ("1件", r"(?<![0-9])1\s*件|1行|一件"),
    ("最大件数", r"最大(?:件数|行数)?|上限|大量"),
    ("NULL", r"NULL|ヌル"),
    ("空文字", r"空文字|空白文字|空欄"),
    ("桁あふれ", r"桁(?:あふれ|溢れ|超過)|長さ超過|最大長|オーバーフロー"),
    ("全半角", r"全角|半角|全半角"),
    ("サロゲートペア", r"サロゲート|絵文字|異体字|𠮷"),
    ("日付境界", r"日付境界|月末|うるう|閏|年末|年始|年度|締め日"),
)
_BOUNDARY = {"NULL", "空文字", "桁あふれ", "全半角", "サロゲートペア", "日付境界"}


# ---------- facts から列情報 ----------

def _split_type(tp):
    """'numeric(5,2)' → ('numeric', 5, 2)。桁が無ければ None。"""
    m = re.match(r"\s*([a-zA-Z_ ]+?)\s*(?:\(\s*(\d+)\s*(?:,\s*(\d+))?\s*\))?\s*(?:\[\])?\s*$", tp or "")
    if not m:
        return (tp or "").lower().strip(), None, None
    return (m.group(1).lower(), int(m.group(2)) if m.group(2) else None,
            int(m.group(3)) if m.group(3) else None)


def _column_of(f):
    """column 事実 1 件 → {table,name,type,not_null,unique,ref}。読めなければ None。"""
    a = f.get("attrs")
    if isinstance(a, dict) and a.get("table") and a.get("column"):
        ref = a.get("references") or {}
        return {"table": a["table"], "name": a["column"], "type": str(a.get("type") or ""),
                "not_null": bool(a.get("not_null")), "unique": bool(a.get("unique") or a.get("primary_key")),
                "ref": (ref.get("table"), (ref.get("columns") or [None])[0]) if ref.get("table") else None}
    subj, val = str(f.get("subject") or ""), str(f.get("value") or "")
    if "." not in subj:
        return None
    table, col = subj.rsplit(".", 1)
    low = val.lower()
    tm = re.match(r"\s*([a-zA-Z_]+(?: (?:varying|precision|with(?:out)? time zone))*\s*(?:\([\d,\s]+\))?)", val)
    return {"table": table, "name": col, "type": tm.group(1).strip() if tm else "",
            "not_null": "not null" in low or "primary key" in low,
            "unique": "unique" in low or "primary key" in low, "ref": None}


def _schema(facts):
    """facts → {table: [列 dict…]}（テーブルだけの事実も空リストで拾う）。"""
    out = {}
    for f in facts or []:
        if f.get("kind") == "table":
            out.setdefault(str(f.get("name") or f.get("subject") or ""), [])
    for f in facts or []:
        if f.get("kind") == "column":
            c = _column_of(f)
            if c:
                out.setdefault(c["table"], []).append(c)
    return {t: cols for t, cols in out.items() if t}


# ---------- 仕様の作成 ----------

def _case_text(case):
    steps = case.get("steps") or []
    parts = [case.get("pre"), case.get("expected"), case.get("basis"),
             " ".join(steps) if isinstance(steps, list) else steps]
    return " ".join(str(p) for p in parts if p)


def _tables_of(case, text, known):
    named = [t for t in ((case.get("oracle") or {}).get("tables") or []) if t in known]
    if named:
        return named
    low = text.lower()
    return [t for t in known if re.search(r"(?<![\w])%s(?![\w])" % re.escape(t.lower().split(".")[-1]), low)]


def _rows_for(conds):
    if "0件" in conds:
        return 0
    if "最大件数" in conds:
        return MAX_ROWS
    if "1件" in conds:
        return 1
    return DEFAULT_ROWS


def spec_from_cases(cases, facts):
    """ケースの前提・期待値からデータ仕様（DataSpec）を作る。対象テーブルが分からないケースは作らない。"""
    known = _schema(facts)
    out = []
    for case in cases or []:
        text = _case_text(case)
        tables = _tables_of(case, text, list(known))
        conds = [name for name, rx in _RULES if re.search(rx, text, re.I)]
        if "0件" in conds:
            conds = ["0件"]
        for table in tables:
            out.append({
                "id": "D%03d" % (len(out) + 1), "case": case.get("id", ""), "table": table,
                "conditions": conds or ["通常"], "rows": _rows_for(conds), "encoding": "utf-8",
                "mask_cols": _pii_cols(known.get(table, [])),
                "basis": "ケース %s の前提・期待値から（%s）" % (case.get("id", ""), "、".join(conds) or "通常データ"),
            })
    return out


spec = spec_from_cases  # 基本設計の公開名


def affected_tables(specs):
    """書き込みを伴う実行の確認で示す、影響テーブルと操作。"""
    seen = {}
    for s in specs or []:
        ops = ["DELETE"] + ([] if int(s.get("rows") or 0) == 0 else ["INSERT"])
        cur = seen.setdefault(s.get("table", ""), [])
        seen[s.get("table", "")] = cur + [o for o in ops if o not in cur]
    return [{"table": t, "ops": o} for t, o in seen.items() if t]


# ---------- 値の生成 ----------

_PII = (("name", r"name|氏名|名前|shimei|kana|カナ"), ("tel", r"tel|phone|電話|fax"),
        ("mail", r"mail|メール"), ("addr", r"addr|住所|zip|postal|郵便"))


def _pii_kind(col):
    for kind, rx in _PII:
        if re.search(rx, col, re.I):
            return kind
    return None


def _pii_cols(cols):
    return [c["name"] for c in cols if _pii_kind(c["name"])]


def _rng(*parts):
    h = hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def _fit(text, n):
    return text if n is None else text[:n]


def _text(col, n, idx, fake):
    kind = _pii_kind(col["name"])
    if col["unique"] and kind != "mail":
        return _fit("%s%d" % (col["name"][:3].upper(), idx), n) if (n or 99) > len(str(idx)) else str(idx)[-n:]
    if kind == "name":
        return _fit(fake.name(), n)
    if kind == "tel":
        return _fit(fake.phone_number(), n)
    if kind == "mail":
        return _fit("u%d_%s" % (idx, fake.email()), n)
    if kind == "addr":
        return _fit(fake.address().replace("\n", " "), n)
    return _fit(fake.word() + str(idx), n)


def _normal(col, idx, fake, parents):
    base, n, s = _split_type(col["type"])
    ref = col.get("ref")
    if ref and parents.get(ref[0]):
        pr = parents[ref[0]]
        return pr[idx % len(pr)].get(ref[1]) if ref[1] in pr[0] else idx + 1
    if base in ("integer", "int", "int4", "bigint", "int8", "smallint", "int2", "serial", "bigserial", "smallserial"):
        return idx + 1
    if base in ("numeric", "decimal"):
        p = n or 10
        return round(min(idx + 1, 10 ** (p - (s or 0)) - 1) + (0.5 if s else 0) * (1 if (s or 0) > 0 else 0), s or 0) if s else min(idx + 1, 10 ** p - 1)
    if base in ("real", "float4", "double precision", "float8", "float"):
        return float(idx + 1)
    if base in ("boolean", "bool"):
        return idx % 2 == 0
    if base == "date":
        return fake.date_between(start_date="-3y", end_date="today").isoformat()
    if base.startswith("timestamp"):
        return fake.date_time_between(start_date="-3y", end_date="now").strftime("%Y-%m-%d %H:%M:%S")
    return _text(col, n, idx, fake)


def _edge(col, cond, idx, fake, edge_i):
    """列 1 つぶんの境界値。該当しない列・条件では None を返さず (False, 値なし) を返す。"""
    base, n, _ = _split_type(col["type"])
    is_text = base in ("varchar", "character varying", "char", "character", "text", "bpchar")
    if cond == "NULL":
        return (not col["not_null"] and not col["unique"], None)
    if cond == "空文字":
        return (is_text, "")
    if cond == "桁あふれ":
        return (is_text and n is not None, ("あ" if _pii_kind(col["name"]) else "x") * (n + 1) if n else "")
    if cond == "全半角":
        return (is_text, _fit((FULLWIDTH if edge_i % 2 == 0 else HALFWIDTH) * 3, n))
    if cond == "サロゲートペア":
        return (is_text, _fit(SURROGATE * (n or 3), n) if n is None or n >= 1 else "")
    if cond == "日付境界":
        d = DATE_EDGES[edge_i % len(DATE_EDGES)]
        return (base == "date" or base.startswith("timestamp"),
                d if base == "date" else d + " 23:59:59")
    return (False, None)


def _boundary_rows(spec_, cols, start, fake, parents):
    """境界条件ごとの行（該当する列だけ境界値、他は通常値）と、注記を返す。"""
    rows, notes = [], []
    for cond in [c for c in spec_.get("conditions", []) if c in _BOUNDARY]:
        n_edges = len(DATE_EDGES) if cond == "日付境界" else 2 if cond == "全半角" else 1
        for e in range(n_edges):
            row, hit = {}, False
            for c in cols:
                row[c["name"]] = _normal(c, start + len(rows), fake, parents)
                ok, val = _edge(c, cond, start + len(rows), fake, e)
                if ok:
                    row[c["name"]], hit = val, True
            if hit:
                rows.append(row)
                notes.append({"index": start + len(rows) - 1, "condition": cond})
    return rows, notes


def _order(specs, schema):
    """親テーブル（外部キー参照先）を先に並べる。循環は元の順のまま。"""
    names, rest, done = [], list(specs), set()
    while rest:
        nxt = [s for s in rest if all((c["ref"] or (None,))[0] in done or (c["ref"] or (None,))[0] not in
                                      {x["table"] for x in rest} for c in schema.get(s["table"], []))]
        pick = nxt[0] if nxt else rest[0]
        rest.remove(pick)
        done.add(pick["table"])
        names.append(pick)
    return names


def generate(specs, facts, seed):
    """仕様と DDL の型・桁に合う行を作る。同じ (specs, facts, seed) なら同じ結果。

    戻り値: {"tables": {table: [row]}, "files": [{name, encoding, content}],
             "by_spec": {spec_id: {table: [row]}}, "boundaries": {table: [{index, condition}]}}
    """
    schema = _schema(facts)
    tables, by_spec, notes = {}, {}, {}
    for s in _order([x for x in (specs or []) if x.get("table")], schema):
        cols = schema.get(s["table"])
        if cols is None:
            raise ValueError("テーブル「%s」の定義が読み取り結果にありません。DDL を取り込んでから、もう一度生成してください。" % s["table"])
        fake = Faker("ja_JP")
        fake.seed_instance(_rng(seed, s.get("id"), s["table"]).getrandbits(32))
        start = len(tables.get(s["table"], []))
        n = int(s.get("rows") or 0)
        rows = [{c["name"]: _normal(c, start + i, fake, tables) for c in cols} for i in range(n)]
        extra, note = _boundary_rows(s, cols, start + n, fake, tables) if n > 0 else ([], [])
        rows += extra
        tables[s["table"]] = tables.get(s["table"], []) + rows
        by_spec[s.get("id", "")] = {s["table"]: rows}
        notes.setdefault(s["table"], []).extend(note)
    files = []
    for s in specs or []:
        t = s.get("table")
        if t in tables and s.get("encoding", "utf-8").lower() not in ("utf-8", "utf8"):
            files.append(_csv_file(t, tables[t], s["encoding"]))
    return {"tables": tables, "files": files, "by_spec": by_spec, "boundaries": notes}


def _csv_file(table, rows, encoding):
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows([{k: "" if v is None else v for k, v in r.items()} for r in rows])
    return {"name": "%s.csv" % table.split(".")[-1], "encoding": encoding, "content": buf.getvalue()}


# ---------- マスキング ----------

_KANJI = "田中山川林森木村石井上下原野島田橋本佐藤鈴高渡辺伊藤加藤吉松清水斎藤太郎花子一二三京大阪東西南北"
_HIRA = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわ"
_KATA = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワ"


def _swap(ch, rng):
    """1 文字を同じ種類の別の文字へ。区切り記号・空白はそのまま。"""
    pools = ("0123456789", "０１２３４５６７８９", "abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
             _HIRA, _KATA, _KANJI)
    for pool in pools:
        if ch in pool:
            return rng.choice(pool.replace(ch, ""))
    if "一" <= ch <= "鿿":
        return rng.choice(_KANJI.replace(ch, ""))
    return ch


def _mask_value(value, column, seed):
    if value is None or isinstance(value, bool):
        return value
    rng = _rng(seed, column, value)
    if isinstance(value, (int, float)):
        text = str(value)
        out = "".join(_swap(c, rng) if c.isdigit() else c for c in text)
        if out.lstrip("-").startswith("0") and len(out.lstrip("-")) > 1:
            out = out.replace("0", "1", 1)
        return type(value)(out)
    return "".join(_swap(c, rng) for c in str(value))


def mask(rows, columns, seed):
    """指定列を、桁・区切り位置・文字種を保って置き換える。同じ値は同じ出力（seed 固定）。"""
    cols = set(columns or [])
    return [{k: (_mask_value(v, k, seed) if k in cols else v) for k, v in row.items()} for row in rows or []]
