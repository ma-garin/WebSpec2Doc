"""段階 2「対象の読み取り」の取りまとめ（規則ベース・LLM 不使用）。

ジョブ定義・仕様書・ソース・DDL（intake_ddl）から事実を根拠行付きで抜き出し、基本設計書 3.2 の形
``{id, kind, subject, value, origin, source{file,line,text}, confirmed}`` に揃える。読めなかった行・
資料間の食い違いは questions に回し黙って捨てない。本文は読む前に伏せ字にする。入力の job は変更しない。
"""
from __future__ import annotations

import re
from pathlib import Path

from web.services.backendtest import intake_ddl, redact, store

_BINARY_SUFFIXES = (".xlsx", ".xls", ".docx", ".doc", ".pdf", ".pptx")
_COMMENT = re.compile(r"^\s*(?:--|#(?!!)|//|/?\*|REM\b)", re.I)


def _squash(t):
    return re.sub(r"\s+", " ", t or "").strip()[:200]


def _fact(kind, subject, value, origin, file, line, text):
    return {"id": "", "kind": kind, "subject": subject, "value": _squash(value),
            "origin": origin, "source": {"file": file, "line": line, "text": _squash(text)},
            "confirmed": False}


def _question(text, file, line, src=""):
    return {"id": "", "text": text,
            "source": {"file": file, "line": line, "text": _squash(src)}, "answer": None}


def _redact(text, extra_values=()):
    """伏せ字にした本文と検出結果を返す。行番号がずれないよう、伏せた範囲の改行は残す。"""
    text = text or ""
    hits = redact.scan(text, extra_values)
    out, cursor = [], 0
    for h in sorted(hits, key=lambda x: x["start"]):
        if h["start"] < cursor:
            continue
        out.append(text[cursor:h["start"]])
        out.append("[伏せ字:%s]" % h["rule"] + "\n" * text.count("\n", h["start"], h["end"]))
        cursor = h["end"]
    out.append(text[cursor:])
    return "".join(out), hits


def _numbered(items, prefix):
    return [{**x, "id": "%s%03d" % (prefix, i)} for i, x in enumerate(items, 1)]


def _dedupe(facts):
    seen, out = set(), []
    for f in facts:
        key = (f["kind"], f["subject"], f["value"], f["origin"], f["source"]["file"])
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def _lines(text):
    return [(no, line) for no, line in enumerate(text.splitlines(), 1)
            if not re.fullmatch(r"[-=*_|:#+\s]*", line)]


_SEP = r"\s*[:：=]\s*"
_JOB_KEYS = (
    ("command", r"(?:cmd|command|コマンド|実行コマンド|script|スクリプト|実行ファイル)"),
    ("args", r"(?:args?|arguments?|引数|パラメータ|parameters?)"),
    ("input", r"(?:input|in|入力|入力ファイル|入力元)"),
    ("output", r"(?:output|out|出力|出力ファイル|出力先)"),
    ("schedule", r"(?:schedule|スケジュール|起動|起動条件|起動日時|実行日時|cron|実行タイミング)"),
    ("before", r"(?:先行|先行ジョブ|前提ジョブ|after|depends?(?:_on)?|predecessors?)"),
    ("after", r"(?:後続|後続ジョブ|next|successors?|then)"),
    ("commit", r"(?:commit|コミット|コミット単位|commit_interval)"),
)
_JOB_RE = tuple((k, re.compile(r"^\s*-?\s*%s%s(.+)$" % (p, _SEP), re.I)) for k, p in _JOB_KEYS)
_RC_LINE = re.compile(r"\brc\b|return\s*code|exit\s*code|終了コード|リターンコード|戻り値", re.I)
_RC_PAIR = re.compile(r"(\d+)\s*[=:：]\s*([^\s,、;／/]+)")
_CRON = re.compile(r"^\s*(?:[\d*/,\-]+\s+){4}[\d*/,\-]+(?:\s|$)")
_ARG_TOKEN = re.compile(r"(--?[A-Za-z][\w-]*)(?:[=\s]+(?!-)(\S+))?|(\{[^{}\s]+\}|\$\{?\w+\}?)")


def _job_args(cmdline, file, no, line):
    return [_fact("jobarg", m.group(1), m.group(2) or "値なし（フラグ）", "jobdef", file, no, line)
            if m.group(1) else _fact("jobarg", m.group(3), "置き換え引数", "jobdef", file, no, line)
            for m in _ARG_TOKEN.finditer(cmdline)]


def _job_key_facts(key, val, file, no, line):
    if key == "command":
        return [_fact("jobarg", "コマンド", val, "jobdef", file, no, line)] + _job_args(val, file, no, line)
    if key == "args":
        return _job_args(val, file, no, line) or [_fact("jobarg", "引数", val, "jobdef", file, no, line)]
    if key in ("input", "output"):
        label = "入力" if key == "input" else "出力"
        return [_fact("io", label, p, "jobdef", file, no, line) for p in re.split(r"[,、;]", val) if p.strip()]
    if key == "schedule":
        return [_fact("date_rule", "スケジュール", val, "jobdef", file, no, line)]
    if key in ("before", "after"):
        label = "先行ジョブ" if key == "before" else "後続ジョブ"
        return [_fact("rule", label, j, "jobdef", file, no, line) for j in re.split(r"[,、;\s]+", val) if j]
    return [_fact("commit", "コミット", val, "jobdef", file, no, line)]


def _jobdef_line(line, file, no):
    for key, rx in _JOB_RE:
        m = rx.match(line)
        if m:
            return _job_key_facts(key, m.group(1).strip(), file, no, line)
    if _RC_LINE.search(line):
        return [_fact("rc", "終了コード %s" % c, mean, "jobdef", file, no, line)
                for c, mean in _RC_PAIR.findall(line)]
    if _CRON.match(line):
        return [_fact("date_rule", "スケジュール", line, "jobdef", file, no, line)]
    return []


def _parse_jobdef(text, file):
    facts, questions = [], []
    for no, line in _lines(text):
        if _COMMENT.match(line):
            continue
        got = _jobdef_line(line, file, no)
        if got:
            facts.extend(got)
        else:
            questions.append(_question("ジョブ定義のこの行を読み取れませんでした。"
                                       "何を指定している行か教えてください。", file, no, line))
    if not facts:
        questions.append(_question("ジョブ定義からコマンド・引数・終了コードを読み取れませんでした。"
                                   "書式を教えてください。", file, 0))
    return _dedupe(facts), questions


_HEADING = re.compile(r"^\s*(?:#{1,6}\s+(.+)|【(.+?)】\s*$|(第[\d一二三四五六七八九十]+[章節条].*)"
                      r"|\d+(?:\.\d+)*[.)．]?\s+(\S[^。]{0,28}))\s*$")
_DATE = re.compile(r"日付|営業日|休日|祝日|月末|月初|月次|日次|年次|締め|締日|期日|期限|前日|翌日|当日"
                   r"|年度|曜日|\d{4}[-/年]\d{1,2}|\d{1,2}月\d{1,2}日|\d{1,2}日(?:以内|前|後)")
_COUNT = re.compile(r"\d[\d,]*\s*件|件数|ゼロ件|上限|最大\s*\d|最小\s*\d|\d+\s*(?:行|レコード|records?)",
                    re.I)
_FORMULA = re.compile(r"計算式|算出|四捨五入|切り捨て|切り上げ|[×÷]|\w+\s*=\s*[\w.]+\s*[-+*/]")
_RULE = re.compile(r"場合|とき|時は|ならば|なければ|しない|してはならない|禁止|必ず|のみ|除外|対象"
                   r"|エラー|異常|正常|更新|削除|登録|出力|合計|\bmust\b|\bshall\b|\bif\b|\bwhen\b",
                   re.I)
_SPEC_KINDS = ((_DATE, "date_rule", "日付条件"), (_COUNT, "rule", "件数条件"),
               (_FORMULA, "formula", "計算"), (_RULE, "rule", "業務ルール"))


def _parse_spec(text, file):
    facts, questions, heading = [], [], ""
    for no, line in _lines(text):
        m = _HEADING.match(line)
        if m:
            heading = next(g.strip() for g in m.groups() if g)
            facts.append(_fact("heading", "見出し", heading, "spec", file, no, line))
            continue
        hit = next(((k, lb) for rx, k, lb in _SPEC_KINDS if rx.search(line)), None)
        if hit:
            subject = "%s（%s）" % (hit[1], heading) if heading else hit[1]
            facts.append(_fact(hit[0], subject, line.strip(" |\t"), "spec", file, no, line))
        else:
            questions.append(_question("仕様書のこの記述から条件を読み取れませんでした。"
                                       "テストで確かめる決まりがあれば教えてください。", file, no, line))
    return _dedupe(facts), questions


_Q = r'(?:"[^"]+"|[A-Za-z_][\w$]*)(?:\s*\.\s*(?:"[^"]+"|[A-Za-z_][\w$]*))?'
_WRITE = re.compile(
    r"\b(?:INSERT\s+INTO|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE(?:\s+TABLE)?)\s+(?:ONLY\s+)?(%s)"
    r"|\bUPDATE\s+(?:ONLY\s+)?(%s)(?=\s+(?:AS\s+)?(?:\w+\s+)?SET\b)"
    r"|\bCOPY\s+(%s)(?=\s*(?:\([^)]*\)\s*)?(?:FROM|TO)\b)" % (_Q, _Q, _Q), re.I)
_READ = re.compile(r"\b(?:FROM|JOIN|USING)\s+(?:ONLY\s+)?(%s)(?!\s*\()" % _Q, re.I)
_FUNC_FROM = re.compile(r"\b(?:extract|substring|trim|overlay|position)\s*\([^()]*$", re.I)
_DYNAMIC = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+[$%{]|\bEXECUTE\s+(?:IMMEDIATE\s+)?['\"(\w]"
                      r"|\bformat\s*\(\s*['\"][^'\"]*%I", re.I)
_NOT_TABLE = {"select", "lateral", "values", "where", "set", "only", "the", "a", "an"}
_ARG_RULES = (
    (re.compile(r"\$\{?([1-9])\}?"), "$%s", "位置引数 %s"),
    (re.compile(r"sys\.argv\[([1-9]\d*)\]"), "sys.argv[%s]", "位置引数 %s"),
    (re.compile(r"add_argument\(\s*['\"](--?[\w-]+)['\"]"), "%s", "名前付き引数"),
)
_BIND = re.compile(r"(?<![:\w]):([A-Za-z_]\w*)")
_COMMIT = re.compile(r"\bcommit\b", re.I)


def _unq(name):
    return ".".join(p.strip()[1:-1] if p.strip().startswith('"') else p.strip().lower()
                    for p in name.split("."))


def _where(text, lines, pos):
    no = redact.line_of(text, pos)
    return no, lines[no - 1] if no <= len(lines) else ""


def _in_select(text, pos):
    seg = text[max(0, pos - 3000):pos]
    seg = seg[seg.rfind(";") + 1:]
    return re.search(r"\bselect\b", seg, re.I) is not None and not _FUNC_FROM.search(seg[-80:])


def _table_facts(text, lines, file):
    out = []
    for rx, label, check in ((_WRITE, "更新", False), (_READ, "参照", True)):
        for m in rx.finditer(text):
            no, line = _where(text, lines, m.start())
            name = _unq(next(g for g in m.groups() if g))
            if _COMMENT.match(line) or name in _NOT_TABLE:
                continue
            if check and (re.match(r"\s*delete", text[max(0, m.start() - 7):m.start()], re.I)
                          or (m.group(0)[:4].lower() == "from" and not _in_select(text, m.start()))):
                continue
            out.append(_fact("table", name, label, "source", file, no, line))
    return out


def _arg_facts(text, lines, file):
    rules = list(_ARG_RULES)
    if file.lower().endswith(".sql"):
        rules.append((_BIND, ":%s", "SQL のバインド変数"))
    out = []
    for rx, subj, val in rules:
        for m in rx.finditer(text):
            no, line = _where(text, lines, m.start())
            if not _COMMENT.match(line):
                out.append(_fact("jobarg", subj % m.group(1),
                                 val % m.group(1) if "%s" in val else val, "source", file, no, line))
    return out


def _parse_source(text, file):
    lines = text.splitlines()
    facts = _table_facts(text, lines, file) + _arg_facts(text, lines, file)
    for m in _COMMIT.finditer(text):
        no, line = _where(text, lines, m.start())
        if not _COMMENT.match(line):
            facts.append(_fact("commit", "コミット", "コミットあり", "source", file, no, line))
    questions = []
    for m in _DYNAMIC.finditer(text):
        no, line = _where(text, lines, m.start())
        questions.append(_question("表名を実行時に組み立てています。実際に参照・更新するテーブルを"
                                   "教えてください。", file, no, line))
    if not any(f["kind"] == "table" for f in facts):
        questions.append(_question("参照・更新するテーブルを読み取れませんでした。"
                                   "対象のテーブルを教えてください。", file, 0))
    return _dedupe(facts), questions


_DDL_KIND = {"relation": "constraint", "index": "constraint"}
_DML_HEAD = re.compile(r"\s*(?:insert|update|delete|merge|select|with|truncate|copy|begin|commit"
                       r"|rollback|set|grant)\b", re.I)


def _column_value(a):
    ref = a.get("references") or {}
    parts = [a.get("type") or "型不明", "主キー" if a.get("primary_key") else
             ("NOT NULL" if a.get("not_null") else ""), "一意" if a.get("unique") else "",
             "" if a.get("default") is None else "既定値 %s" % a["default"],
             "CHECK %s" % a["check"] if a.get("check") else "",
             "参照先 %s" % ref.get("table", "") if ref else ""]
    return " / ".join(p for p in parts if p)


def _ddl_value(kind, a):
    if kind == "column":
        return _column_value(a)
    if kind == "table":
        return "テーブル定義"
    if kind == "relation":
        return "外部キー %s(%s) → %s(%s)" % (a.get("table", ""), ",".join(a.get("columns") or []),
                                           a.get("ref_table", ""), ",".join(a.get("ref_columns") or []))
    if kind == "index":
        return "%s索引 (%s)" % ("一意" if a.get("unique") else "", ", ".join(a.get("columns") or []))
    if kind == "comment":
        return "コメント: %s" % a.get("text", "")
    if a.get("type") == "check":
        return "CHECK %s" % a.get("expr", "")
    return "%s (%s)" % (a.get("type", ""), ", ".join(a.get("columns") or []))


def from_ddl(f):
    """intake_ddl の事実 1 件を 3.2 の形に変換した新しい dict を返す（attrs は写しを残す）。"""
    a, kind, src = f.get("attrs") or {}, f.get("kind", ""), f.get("source") or {}
    new_kind = (("column" if a.get("target_kind") == "column" else "table") if kind == "comment"
                else _DDL_KIND.get(kind, kind))
    return {"id": "", "kind": new_kind, "subject": f.get("name", ""), "value": _ddl_value(kind, a),
            "origin": "ddl", "source": {"file": src.get("file", ""), "line": src.get("line", 0),
                                        "text": _squash(src.get("text", ""))},
            "confirmed": False, "ddl_kind": kind, "attrs": dict(a)}


def _parse_ddl(text, file):
    got = intake_ddl.read_ddl(text, file)
    facts = [from_ddl(f) for f in got["facts"]]
    dml = [u for u in got["unread"] if _DML_HEAD.match(u.get("text", ""))]
    questions = [_question("DDL のこの文を読み取れませんでした。%s" % u.get("reason", ""),
                           file, u.get("line", 0), u.get("text", ""))
                 for u in got["unread"] if u not in dml]
    if dml:   # DDL ファイルに混じった更新文・照会文はソースとして読む
        src_facts, src_qs = _parse_source(text, file)
        facts += src_facts
        questions += [q for q in src_qs if q["source"]["line"]]
    return facts, questions


_PARSERS = {"ddl": _parse_ddl, "jobdef": _parse_jobdef, "spec": _parse_spec, "source": _parse_source}
_OTHER = "このファイルの種類が分かりません。DDL・ジョブ定義・仕様書・ソースのどれかを指定してください。"


def read_jobdef(text, file, extra_values=()):
    """ジョブ定義からコマンド・引数・終了コード・入出力・スケジュール・先行後続を事実にする。"""
    return _numbered(_parse_jobdef(_redact(text, extra_values)[0], file)[0], "F")


def read_spec(text, file, extra_values=()):
    """仕様書テキストから見出し・業務ルール・日付条件・件数条件・計算を事実にする。"""
    return _numbered(_parse_spec(_redact(text, extra_values)[0], file)[0], "F")


def read_source(text, file, extra_values=()):
    """スクリプト・SQL から参照テーブル・更新テーブル・引数・コミットを事実にする（origin="source"）。"""
    return _numbered(_parse_source(_redact(text, extra_values)[0], file)[0], "F")


def _load_text(job, name):
    try:
        data = store.file_path(job, name).read_bytes()
    except (OSError, ValueError):
        return "", "%s を開けませんでした。取り込み直してください。" % name
    if Path(name).suffix.lower() in _BINARY_SUFFIXES or b"\x00" in data[:4096]:
        return "", ("%s はこの形式のままでは読めません。テキスト（.txt・.md・.csv）に保存して"
                    "取り込み直してください。" % name)
    for enc in ("utf-8-sig", "cp932", "euc-jp"):
        try:
            return data.decode(enc), ""
        except UnicodeDecodeError:
            continue
    return "", "%s の文字コードが読めません。UTF-8 で保存して取り込み直してください。" % name


def _read_file(job, entry, extra_values):
    name, kind = entry.get("name", ""), entry.get("kind") or "other"
    empty = {"facts": [], "questions": [], "unread": [], "redactions": []}
    if kind in ("io", "golden"):   # データ・期待値のファイルは段階 5・7 で使う
        return empty
    text, problem = _load_text(job, name)
    if problem:
        return {**empty, "questions": [_question(problem, name, 0)],
                "unread": [{"file": name, "line": 0, "reason": problem}]}
    masked, hits = _redact(text, extra_values)
    parse = _PARSERS.get(kind, lambda _t, f: ([], [_question(_OTHER, f, 0)]))
    facts, questions = parse(masked, name)
    unread = [{"file": q["source"]["file"], "line": q["source"]["line"], "reason": q["text"]}
              for q in questions]
    return {"facts": facts, "questions": questions, "unread": unread,
            "redactions": redact.summarize(text, hits)}


def _cross_check(facts):
    """資料間の食い違いを問いにする（DDL に無いテーブル・終了コードの意味の不一致）。"""
    defined = {f["subject"].split(".")[-1] for f in facts if f["origin"] == "ddl" and f["kind"] == "table"}
    questions = []
    if defined:
        questions += [_question("%s を%sしていますが、取り込んだ DDL に定義がありません。定義の資料を"
                                "追加するか、対象外か教えてください。" % (f["subject"], f["value"]),
                                f["source"]["file"], f["source"]["line"], f["source"]["text"])
                      for f in facts if f["origin"] == "source" and f["kind"] == "table"
                      and f["subject"].split(".")[-1] not in defined]
    groups = {}
    for f in (f for f in facts if f["kind"] == "rc"):
        groups.setdefault(f["subject"], []).append(f)
    for subject, group in groups.items():
        meanings = sorted({g["value"] for g in group})
        if len(meanings) > 1:
            src = group[0]["source"]
            questions.append(_question("%s の意味が資料によって違います（%s）。正しい意味を教えてください。"
                                       % (subject, "・".join(meanings)), src["file"], src["line"], src["text"]))
    return questions


def read_all(job, extra_values=()):
    """取り込みファイルを種類で振り分けて読む。戻り値 {"facts", "questions", "unread",
    "redactions": {ファイル名: [{"rule","line"}]}}（redactions は files[].redactions 用・値なし）。"""
    facts, questions, unread, redactions = [], [], [], {}
    for entry in job.get("files") or []:
        got = _read_file(job, entry, extra_values)
        facts += got["facts"]
        questions += got["questions"]
        unread += got["unread"]
        if got["redactions"]:
            redactions[entry.get("name", "")] = got["redactions"]
    facts = _dedupe(facts)
    questions += _cross_check(facts)
    return {"facts": _numbered(facts, "F"), "questions": _numbered(questions, "Q"),
            "unread": unread, "redactions": redactions}


analyze = read_all   # 基本設計書 2 章の名前
