"""段階 4: ケース表。採用された観点に 29119-4 の技法を当ててケースへ展開する（FR-08-034）。

期待値方式と state は BD-008 7 章の判定表に従う。機械判定できるもの（冪等性・回復・不変・スキーマ）だけ
state="auto"、業務判断を含むものは state="unconfirmed"（シニア QA が確定するまで合格に数えない）。
入力の viewpoints / facts は変更しない。ソース由来の事実は根拠（basis・req_ids）に入れない（3.2 規則 3）。
"""
import calendar
import re
from datetime import date

from web.services.backendtest.catalog import LEVEL_DEFAULTS
from web.services.backendtest.viewpoints import _normalize_level

USED = ("emit", "adopted", "edited")
_AUTO_METHOD = {"rerun": "db_diff", "recovery": "db_diff", "invariance": "db_diff", "schema": "schema"}
_BASE_YEAR = 2026
_DATE_WORDS = ("date", "time", "日付", "日時", "年月")
_UNCONFIRMED = "期待値は未確定です。シニア QA が確定するまで合格に数えません"
_NO_KEY = "突合キーが決まっていません。対象の読み取りで主キーを確かめてください"


def _v(variant, pre, steps, expected, summary, kind=None, facts=()):
    """展開した 1 ケース分の中身。kind は判定表の自動確定の種類（None なら人が確定）。"""
    return {"variant": variant, "pre": pre, "steps": list(steps), "expected": expected,
            "summary": summary, "kind": kind, "facts": list(facts)}


# --- 事実の読み取り（ソース由来は除く） ---

def _usable(facts):
    return [f for f in facts if f.get("origin") != "source"]


def _text(f):
    return f"{f.get('subject', '')} {f.get('value', '')}".lower()


def _context(facts):
    """突合キー・対象テーブル・有無だけ比べる列（採番・時刻）を事実から拾う。"""
    tables, key, mask = [], [], []
    for f in facts:
        subj, val = str(f.get("subject", "")), str(f.get("value", "")).lower()
        if f.get("kind") == "table" and subj and subj not in tables:
            tables.append(subj)
        m = re.search(r"primary key\s*\(([^)]*)\)", val)
        if m:
            key += [c.strip() for c in m.group(1).split(",") if c.strip() and c.strip() not in key]
        elif f.get("kind") == "column" and "primary key" in val:
            key.append(subj.split(".")[-1])
        if f.get("kind") == "column" and re.search(r"created_at|updated_at|serial|identity|now\(\)", _text(f)):
            mask.append(subj.split(".")[-1])
    return {"tables": tables, "key": key, "mask": mask}


def _date_subjects(facts, level):
    out = [f for f in facts if f.get("kind") == "date_rule"
           or (f.get("kind") == "column" and any(w in _text(f) for w in _DATE_WORDS))]
    out = out or [{"id": None, "subject": "業務日付"}]
    return out[:1] if level == "acceptance" else out


def _length_columns(facts):
    out = []
    for f in facts:
        m = re.search(r"(?:char|varchar|character varying)\s*\((\d+)\)", str(f.get("value", "")).lower())
        if f.get("kind") == "column" and m:
            out.append((f, int(m.group(1))))
    return out


# --- 日付の境界（月末・年度末・閏年） ---

def _year(leap):
    y = _BASE_YEAR
    while calendar.isleap(y) != leap:
        y += 1
    return y


def _iso(y, m, d):
    return date(y, m, d).isoformat()


def _month_end_points():
    ny, ly = _year(False), _year(True)
    return [
        (_iso(ny, 2, 28), "平年の 2 月末", True), (_iso(ny, 3, 1), "平年の 2 月末の翌日", False),
        (_iso(ly, 2, 28), "閏年の 2 月末の前日", False), (_iso(ly, 2, 29), "閏年の 2 月末", True),
        (_iso(ly, 3, 1), "閏年の 2 月末の翌日", False), (_iso(2100, 2, 28), "100 で割り切れる平年の 2 月末", False),
        (_iso(ny, 4, 30), "30 日の月の月末", False), (_iso(ny, 1, 31), "31 日の月の月末", False),
    ]


def _date_variants(vp, subjects, level):
    ny, ly = _year(False), _year(True)
    vid = vp["id"]
    if vid == "A-4-01":
        points = _month_end_points()
    elif vid == "A-4-02":
        points = [(f"{_iso(ny, 1, 31)} の 1 か月後", "平年の 1 月 31 日に 1 か月を足す", True),
                  (f"{_iso(ly, 1, 31)} の 1 か月後", "閏年の 1 月 31 日に 1 か月を足す", True),
                  (f"{_iso(ny, 3, 31)} の 1 か月後", "3 月 31 日に 1 か月を足す（4 月 31 日は無い）", False)]
    elif vid == "A-4-04":
        points = [(_iso(ny + 1, 3, 30), "年度末の前日", False), (_iso(ny + 1, 3, 31), "年度末", True),
                  (_iso(ny + 1, 4, 1), "翌年度の初日", True), (_iso(ny, 9, 30), "上期末", False),
                  ("年度末が休日の年", "年度末が休日のときの営業日の扱い", False)]
    else:
        points = [(f"{_iso(ny, 12, 31)} 23:59:59 → 翌日 00:00:00", "年をまたぐ瞬間", True),
                  ("処理中に 0 時をまたぐ", "実行中の日付またぎ", False),
                  ("UTC 15:00（日本時間の翌日 0 時）", "タイムゾーンの差で日付が変わる", False),
                  ("23:59:60 の時刻", "うるう秒の入力", False)]
    if level == "acceptance":
        points = [p for p in points if p[2]]
    out = []
    for f in subjects:
        for value, label, _core in points:
            out.append(_v(
                f"{f['subject']}={value}",
                f"{f['subject']} が {value}（{label}）になるデータを用意する",
                [f"業務日付を {value} にしてジョブを実行する", "出力と DB の結果を記録する"],
                f"{label}の{vp['name']}の扱いが仕様どおりである",
                f"{f['subject']}が{label}のとき、{vp['name']}の扱いが仕様どおりかを確かめます。",
                facts=[f["id"]] if f.get("id") else []))
    return out


# --- 観点ごとの展開（判定表に載る観点） ---

def _rerun(vp, label="同じ引数で 2 回続けて実行する"):
    return _v("再実行", "1 回目が正常終了した直後の DB を記録しておく",
              ["ジョブを実行し、終わったら DB を記録する", label, "2 回目の後の DB を記録して 1 回目の後と比べる"],
              "2 回目の実行で DB に差分が出ない",
              f"{vp['name']}: もう一度実行してもデータが増えたり変わったりしないことを確かめます。", "rerun")


def _recovery(vp, name):
    return _v(name, "正常に 1 回実行した後の DB を基準として記録しておく",
              ["同じ入力でジョブを途中で止める", "再実行（またはリスタート）して最後まで流す",
               "回復後の DB を基準と比べる"],
              "回復後の DB が、正常に 1 回実行した後と差分なしで一致する",
              f"{vp['name']}: 途中で止まってもやり直せば、正常に 1 回流したのと同じ結果になることを確かめます。",
              "recovery")


def _invariance(vp, step):
    return _v("不変", "対象外のテーブルと列を実行前に記録しておく", [step, "実行後に対象外のテーブルと列を比べる"],
              "対象外のテーブル・除外列以外に差分が出ない",
              f"{vp['name']}: 変わってはいけないデータが変わっていないことを確かめます。", "invariance")


def _schema(vp, variant="スキーマ", what="出力の型・桁・必須・一意"):
    return _v(variant, "テーブル定義（DDL）とファイル規約を読み取り済みにする",
              ["ジョブを実行する", f"{what}を定義と 1 行ずつ照らす"], "定義への違反が 0 件",
              f"{vp['name']}: {what}が定義どおりかを機械で確かめます。", "schema")


def _human(variant, pre, steps, expected, summary, facts=()):
    return _v(variant, pre, steps, expected, summary, None, facts)


def _specific(vp, facts, level):
    """判定表（自動確定できる種類）に当たる観点の展開。該当しなければ境界側へ回す。"""
    vid, name = vp["id"], vp["name"]
    if vid in ("A-1-01", "A-9-01"):
        return [_rerun(vp)]
    if vid == "A-1-02":
        return [_recovery(vp, "途中失敗からの回復"),
                _human("不正な遷移", "ジョブが異常終了した状態にしておく", ["失敗状態のまま後続の処理を起動する"],
                       "起動が拒否され、理由が記録される", f"{name}: 失敗したまま先へ進めないことを確かめます。")]
    if vid == "A-1-06":
        return [_rerun(vp, "同じパラメータでもう一度起動する"),
                _human("別パラメータ", "1 回目が正常終了している", ["別のパラメータで起動する"],
                       "別パラメータの実行は受け付けられ、仕様どおりの結果になる",
                       f"{name}: パラメータが違えば実行できることを確かめます。")]
    if vid == "A-1-07":
        return [_recovery(vp, "リスタート")]
    if vid in ("A-7-03", "A-7-05"):
        return [_invariance(vp, "開始時点と完了時点の DB を記録してジョブを実行する")]
    if vid == "A-8-03":
        return [_invariance(vp, "ドライランの指定でジョブを実行する")]
    if vid == "A-7-01":
        return [_schema(vp, "スキーマ", "出力テーブルの型・桁・必須・一意"),
                _human("行数", "入力の件数を記録しておく", ["ジョブを実行する", "出力の行数を数える"],
                       "出力の行数が承認済みの件数式を満たす",
                       f"{name}: 出力の行数が決めた式どおりかを確かめます（式は人が決めます）。")]
    if vid in ("A-6-01", "A-6-03", "A-9-10", "A-10-03"):
        return [_schema(vp, "スキーマ", "出力ファイル・応答の項目・桁・改行・文字コード")]
    return _specific_bounds(vp, facts, level)


def _specific_bounds(vp, facts, level):
    """日付・件数・値の境界と、業務規則・デシジョンテーブルの観点。該当しなければ None。"""
    vid, name = vp["id"], vp["name"]
    if vid.startswith("A-4-") and vid != "A-4-03":
        return _date_variants(vp, _date_subjects(facts, level), level)
    if vid == "A-5-01":
        return [_human(f"{n}件", f"入力を {n} 件用意する", ["ジョブを実行する", "出力と DB の件数を数える"],
                       f"入力 {n} 件のときの出力件数が仕様どおりである",
                       f"入力が{n}件のときに正しく処理されるかを確かめます。")
                for n in ("0", "1", "最大", "最大+1")]
    if vid == "A-5-02":
        return _value_bounds(vp, facts)
    if vid == "A-7-02":
        return _aggregate(vp, facts)
    if vid == "A-1-03":
        return _table(vp, [(a, b) for a in ("全件やり直し", "処理済みスキップ")
                           for b in ("処理済みデータあり", "処理済みデータなし")])
    if vid == "A-8-02":
        rcs = [f for f in facts if f.get("kind") == "rc"]
        if rcs:
            return [_human(f"RC {f.get('value', '')}", f"{f.get('subject', '')} になる入力を用意する",
                           ["ジョブを実行する", "終了コードと通知を記録する"],
                           f"終了コード {f.get('value', '')} と完了通知が仕様どおりである",
                           f"{f.get('subject', '')}のとき決められた終了コードで終わるかを確かめます。", [f.get("id")])
                    for f in rcs]
        return _table(vp, [(a, b) for a in ("正常", "警告", "異常") for b in ("通知あり",)])
    return None


def _value_bounds(vp, facts):
    out = [_human(n, f"{n}のレコードを用意する", ["ジョブを実行する", "出力を記録する"],
                  f"{n}のレコードが仕様どおりに処理される", f"{n}のデータが正しく処理されるかを確かめます。")
           for n in ("必須項目のみ", "全項目あり", "0 と NULL")]
    cols = _length_columns(facts) or [({"id": None, "subject": "各項目"}, None)]
    for f, n in cols:
        for v, label in ((n, "最大長ちょうど"), ((n or 0) + 1 if n else None, "最大長+1")):
            size = f"{v} 文字" if v else label
            out.append(_human(f"{f['subject']}={label}", f"{f['subject']} を {size}にしたレコードを用意する",
                              ["ジョブを実行する", "出力と DB を記録する"],
                              f"{f['subject']} が{label}のときの扱いが仕様どおりである",
                              f"{f['subject']}が{label}のときに正しく扱われるかを確かめます。",
                              [f["id"]] if f.get("id") else []))
    return out


def _aggregate(vp, facts):
    rules = [f for f in facts if f.get("kind") in ("rule", "formula")]
    rules = rules or [{"id": None, "subject": "出力の集計値", "value": ""}]
    return [_human(f"集計:{f['subject']}", "集計の元になる入力を用意する",
                   ["ジョブを実行する", f"{f['subject']} を別の SQL で計算して出力と突き合わせる"],
                   f"{f['subject']} が仕様の規則どおりの値になる",
                   f"{f['subject']}を別の計算で求め、出力と一致するかを確かめます（計算式は人が承認します）。",
                   [f["id"]] if f.get("id") else [])
            for f in rules]


def _table(vp, rules):
    return [_human(f"規則{i}", f"条件「{'・'.join(r)}」になるデータを用意する",
                   ["ジョブを実行する", "結果を記録する"], f"条件「{'・'.join(r)}」の結果が仕様どおりである",
                   f"{vp['name']}: 条件が「{'・'.join(r)}」のときの動きを確かめます。")
            for i, r in enumerate(rules, start=1)]


# --- 技法ごとの既定の展開 ---

def _generic(vp):
    name, tech = vp["name"], vp["technique"]
    if tech.startswith("境界値"):
        pts = ("下限の直前", "下限", "上限", "上限の直後")
    elif tech.startswith("同値分割"):
        pts = ("有効な値の代表", "無効な値の代表")
    elif tech.startswith("デシジョン"):
        pts = ("条件が成り立つ", "条件が成り立たない")
    elif tech.startswith("状態遷移"):
        pts = ("正しい順の遷移", "許されない遷移")
    elif tech.startswith("シナリオ"):
        pts = ("基本の流れ", "異常の流れ")
    else:
        pts = ("代表",)
    return [_human(p, f"{name}の「{p}」に当たる状態とデータを用意する", ["ジョブを実行する", "結果を記録する"],
                   f"{name}の「{p}」の結果が仕様どおりである",
                   f"{name}について「{p}」の場合の動きを確かめます。")
            for p in pts]


# --- ケースの組み立て ---

def _method(vp, kind, level):
    if kind:
        return _AUTO_METHOD[kind]
    allowed = LEVEL_DEFAULTS[level]["oracles"]
    want = vp.get("oracle") or allowed[0]
    return want if want in allowed else allowed[0]


def _case(vp, body, level, ctx):
    kind = None if vp.get("human_oracle") else body["kind"]
    method = _method(vp, kind, level)
    warnings = [] if kind else [_UNCONFIRMED]
    if method == "db_diff" and not ctx["key"]:
        warnings.append(_NO_KEY)
    # 突合キーの無い前後比較は自動確定しない（冪等性は行全体の個数で比べられるので例外）
    auto = bool(kind) and (method != "db_diff" or bool(ctx["key"]) or kind == "rerun")
    oracle = {"method": method, "state": "auto" if auto else "unconfirmed", "tables": list(ctx["tables"]),
              "key": list(ctx["key"]), "exclude": [], "tolerance": {}, "mask": list(ctx["mask"]),
              "count_formula": None, "alt_sql": None, "alt_sql_ja": "", "golden": None,
              "confirmed_by": None, "warnings": warnings}
    return {"id": "", "viewpoint": vp["id"], "variant": body["variant"], "technique": vp.get("technique", ""),
            "level": level, "check": kind, "req_ids": [i for i in body["facts"] if i], "pre": body["pre"],
            "steps": body["steps"], "expected": body["expected"], "oracle": oracle,
            "basis": f"観点 {vp['id']}「{vp.get('name', '')}」 {vp.get('basis', '')}".strip(),
            "summary_ja": body["summary"], "origin": "generated", "history": []}


def build(viewpoints, facts, level):
    """採用された観点（emit / adopted / edited）ごとに技法を当ててケースを返す。"""
    lv = _normalize_level(level)
    usable = _usable(list(facts or []))
    ctx = _context(usable)
    out = []
    for vp in viewpoints or []:
        if vp.get("decision") not in USED:
            continue
        bodies = _specific(vp, usable, lv) or _generic(vp)
        out.extend(_case(vp, b, lv, ctx) for b in bodies)
    return renumber(out)


def renumber(cases):
    """並び順で C001 から振り直した新しいリストを返す。"""
    return [{**c, "id": f"C{i:03d}"} for i, c in enumerate(cases, start=1)]


def _slot(c):
    return (c.get("viewpoint"), c.get("variant"))


def _content(c):
    return (c.get("pre"), tuple(c.get("steps") or ()), c.get("expected"),
            (c.get("oracle") or {}).get("method"))


def merge(approved, fresh):
    """承認済みは壊さない。再生成で増えた・変わったケースは proposals に回す。"""
    approved, fresh = list(approved or []), list(fresh or [])
    if not approved:
        return {"cases": renumber(fresh), "proposals": []}
    by_slot = {_slot(c): c for c in approved}
    proposals = []
    for c in fresh:
        old = by_slot.get(_slot(c))
        if old is not None and _content(old) == _content(c):
            continue
        reason = "新しく出たケースです" if old is None else f"承認済みの {old.get('id')} と内容が違います"
        proposals.append({"id": f"P{len(proposals) + 1:03d}", "replaces": old.get("id") if old else None,
                          "case": dict(c), "reason": reason})
    return {"cases": [dict(c) for c in approved], "proposals": proposals}


def trace(cases, facts=None):
    """観点 → ケースの対応表と、どのケースにも結び付いていない業務規則・日付規則の事実 ID。"""
    rows, index = [], {}
    for c in cases or []:
        vid = c.get("viewpoint")
        if vid not in index:
            index[vid] = {"viewpoint": vid, "cases": [], "auto": 0, "unconfirmed": 0}
            rows.append(index[vid])
        row = index[vid]
        row["cases"].append(c.get("id"))
        state = (c.get("oracle") or {}).get("state")
        row["auto" if state == "auto" else "unconfirmed"] += 1
    covered = {i for c in cases or [] for i in c.get("req_ids") or []}
    reqs = [f.get("id") for f in _usable(list(facts or []))
            if f.get("kind") in ("rule", "formula", "date_rule") and f.get("id")]
    return {"rows": rows, "uncovered_reqs": [i for i in reqs if i not in covered]}
