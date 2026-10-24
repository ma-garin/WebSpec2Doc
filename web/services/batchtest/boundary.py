"""日付境界・冪等性・部分失敗の再開を、既定の観点としてケースにする。

会計・締め系のバッチで事故が集中する所（月末・年度末・うるう年・タイムゾーン・再実行・部分失敗）は、
スクリプトから読み取れなくても観点として必ず並べる。期待結果の根拠が仕様書に無いものは ask=True、
この画面の自動テストで再現できないもの（部分失敗の再開）は manual=True で「手動確認」にして名指しする。
"""
from __future__ import annotations

import re

_REQ = re.compile(r"\b(?:REQ|JOB|DES)-[A-Z]+-\d+|\bREQ-\d+")

# 観点名 → 仕様書を探す語
SPEC_PATTERNS = {
    "日付境界・月末": r"月末",
    "日付境界・うるう年": r"うるう|閏|2\s*月\s*29\s*日",
    "日付境界・年度末": r"3\s*月\s*31\s*日|4\s*月\s*1\s*日",
    "日付境界・タイムゾーン": r"JST|UTC|タイムゾーン|時差|日本時間",
    "冪等性": r"冪等|二重に計上|二重計上|同じ結果",
    "部分失敗・再開": r"一部.{0,20}失敗|失敗した.{0,10}のみ|再開",
}
DEFAULT_OBS = tuple(SPEC_PATTERNS)


def spec_ref(spec: list[dict], pattern: str) -> str:
    """仕様書の該当箇所を「ファイル 位置（要件ID）」で返す。無ければ空文字。"""
    pat = re.compile(pattern, re.I)
    for p in spec:
        if pat.search(p.get("text", "")):
            ids = sorted(set(_REQ.findall(p["text"])))
            where = f"{p.get('file', '仕様書')} {p.get('location', '')}".strip()
            return where + (f"（{'・'.join(ids[:3])}）" if ids else "")
    return ""


def _leap_year(base_year: int) -> tuple[str, str]:
    y = base_year
    while not (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        y += 1
    return str(y), str(y + 1)


def cases(ctx, ok_code: int, ok_src: str, bad_code: int | None, bad_src: str, has_out: bool) -> list[dict]:
    """design.add に渡す引数の辞書を返す。"""
    out: list[dict] = []
    spec = ctx.spec
    refs = {k: spec_ref(spec, v) for k, v in SPEC_PATTERNS.items()}
    ok_text = f"終了コード {ok_code}" + ("／出力ファイルを作る" if has_out else "")
    bad_text = (f"終了コード {bad_code}" if bad_code is not None else "") + "／出力ファイルを作らない"
    ok_expect = {"code": ok_code, "output": "exists" if has_out else None}
    bad_expect = {"code": bad_code, "output": "absent" if has_out else None}

    def add(obs, tech, pre, argv, exp, *, expect=None, setup=None, ask=False, proposal="", manual=False, src=None):
        out.append({"obs": obs, "tech": tech, "pre": pre, "argv": argv, "exp": exp,
                    "src": src if src is not None else (refs.get(obs) or ok_src),
                    "expect": expect or {}, "setup": setup or {}, "ask": ask, "proposal": proposal,
                    "manual": manual})

    date_args = [a for a in ctx.facts["args"] if a.get("format") in ("yyyymm", "yyyymmdd")]
    for a in date_args:
        name, base = a["name"], ctx.values[a["name"]]
        y = int(base[:4])
        leap, plain = _leap_year(y)
        if a["format"] == "yyyymmdd":
            month_end = [(f"{y}0131", "31 日の月末"), (f"{y}0430", "30 日の月末"), (f"{y}1231", "年末")]
            leap_ok, leap_ng = (f"{leap}0229", "うるう年の 2 月 29 日"), (f"{plain}0229", "平年の 2 月 29 日（存在しない日）")
            fy = [(f"{y}0331", "年度末（3 月 31 日）"), (f"{y}0401", "年度初日（4 月 1 日）")]
        else:
            month_end = [(f"{y}01", "31 日で終わる月"), (f"{y}04", "30 日で終わる月")]
            leap_ok, leap_ng = (f"{leap}02", "うるう年の 2 月（29 日まで）"), None
            fy = [(f"{y}03", "年度末の月（3 月）"), (f"{y}04", "年度初めの月（4 月）")]
        for v, label in month_end:
            add("日付境界・月末", "境界値分析", f"{name} = {v}（{label}）", ctx.argv({name: v}), ok_text, expect=ok_expect)
        add("日付境界・うるう年", "境界値分析", f"{name} = {leap_ok[0]}（{leap_ok[1]}）", ctx.argv({name: leap_ok[0]}),
            ok_text, expect=ok_expect)
        if leap_ng:
            add("日付境界・うるう年", "境界値分析", f"{name} = {leap_ng[0]}（{leap_ng[1]}）", ctx.argv({name: leap_ng[0]}),
                bad_text, expect=bad_expect, ask=bad_code is None, src=bad_src or refs["日付境界・うるう年"],
                proposal="0 以外で終わり、出力を作らない")
        for v, label in fy:
            ref = refs["日付境界・年度末"]
            add("日付境界・年度末", "境界値分析", f"{name} = {v}（{label}）", ctx.argv({name: v}), ok_text,
                expect=ok_expect, ask=not ref, src=ref, proposal="年度の区切りで繰越・集計が正しく分かれる")
    if not date_args:
        for obs in ("日付境界・月末", "日付境界・うるう年", "日付境界・年度末"):
            add(obs, "境界値分析", "業務日付を引数で渡さないスクリプト", ctx.argv(), "", ask=True, src=refs[obs] or "—",
                proposal="業務日付をどこから決めるか（引数・システム日付・設定）を確かめ、月末・年度末・2 月 29 日で実行する")

    tz_ref = refs["日付境界・タイムゾーン"]
    add("日付境界・タイムゾーン", "同値分割", "実行環境の時刻帯を UTC にして正常と同じ入力で実行", ctx.argv(),
        ok_text + "／業務日付が日本時間のまま変わらない", expect=ok_expect, setup={"env_set": {"TZ": "UTC"}},
        ask=not tz_ref, src=tz_ref, proposal="実行環境の時刻帯に関係なく、同じ業務日付で処理する")

    if has_out:
        ref = refs["冪等性"]
        add("冪等性", "状態遷移", "同じ引数で 2 回続けて実行（同じバッチの再実行）", ctx.argv(),
            f"終了コード {ok_code}／2 回目の出力が 1 回目と同じ（二重に計上しない）",
            expect={"code": ok_code, "output": "same"}, setup={"rerun": True}, ask=not ref, src=ref,
            proposal="2 回目も同じ出力で、件数・金額が増えない")

    ref = refs["部分失敗・再開"]
    add("部分失敗・再開", "状態遷移", "一部の単位（店舗など）だけ失敗させ、原因を直して再開する", ctx.argv(),
        "成功した単位の結果は確定したまま、失敗した単位だけを再処理する" if ref else "",
        ask=not ref, src=ref or "—", manual=True,
        proposal="成功済みの単位は再処理せず、失敗した単位だけを処理する")
    return out
