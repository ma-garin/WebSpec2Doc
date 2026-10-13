"""ケース設計。読み取った事実（parse.analyze）と仕様書の文から、ISO/IEC/IEEE 29119-4 の技法でケースを作る。

技法: 同値分割（正常・異常の代表値）・境界値分析（年月・日付の端）・状態遷移（再実行・二重起動）。
期待結果の根拠がスクリプトにも仕様書にも無いものは、推測で埋めず ask=True（要確認）にして案だけ添える。
"""
from __future__ import annotations

import re

_USAGE = r"使い方|usage|引数|指定して|必要です|required"
_FORMAT = r"不正|形式|正しく|invalid|format|範囲"
_MISSING = r"ありません|見つかりません|存在しません|not\s*found|no\s*such|入力"
_LOCKED = r"実行中|二重|起動中|lock|running"


def _sample_value(arg: dict, samples: list[str]) -> str:
    fmt = arg.get("format")
    digits = {"yyyymm": 6, "yyyymmdd": 8}.get(fmt or "")
    if digits:
        for name in samples:
            m = re.search(r"(?<!\d)(20\d{%d})(?!\d)" % (digits - 2), name)
            if m:
                return m.group(1)
        return "202601" if digits == 6 else "20260115"
    return f"sample{arg['pos']}"


class _Ctx:
    def __init__(self, facts: dict, spec: list[dict], files: list[dict], command: str):
        self.facts, self.spec, self.files = facts, spec, files
        self.command = command
        self.samples = [f["name"] for f in files if f["kind"] == "input"]
        self.has_expected = any(f["kind"] == "expected" for f in files)
        self.values = {a["name"]: _sample_value(a, self.samples) for a in facts["args"]}

    def code_for(self, pattern: str, extra: str = "") -> tuple[int | None, str]:
        """意味の文言が pattern に合う終了コード。見つかれば (コード, 根拠)。"""
        pat = re.compile(pattern + (("|" + re.escape(extra)) if extra else ""), re.I)
        for c in self.facts["exit_codes"]:
            for m in c.get("meanings") or [{"text": c.get("meaning", ""), "line": c["line"]}]:
                if m["text"] and pat.search(m["text"]):
                    return int(c["code"]), f"スクリプト {m['line']} 行"
        return None, ""

    def spec_ref(self, pattern: str) -> str:
        pat = re.compile(pattern, re.I)
        for p in self.spec:
            if pat.search(p["text"]):
                return f"{p.get('file', '仕様書')} {p.get('location', '')}".strip()
        return ""

    def spec_code(self, pattern: str) -> tuple[int | None, str]:
        """仕様書の「終了コード N」「戻り値 N」のうち、同じ文に pattern があるもの。"""
        pat = re.compile(pattern, re.I)
        for p in self.spec:
            if not pat.search(p["text"]):
                continue
            m = re.search(r"(?:終了コード|戻り値|リターンコード|exit\s*code|errorlevel)\D{0,6}(\d+)", p["text"], re.I)
            if m:
                return int(m.group(1)), f"{p.get('file', '仕様書')} {p.get('location', '')}".strip()
        return None, ""

    def argv(self, override: dict | None = None, drop_from: int | None = None, extra: list[str] | None = None) -> list[str]:
        vals = {**self.values, **(override or {})}
        out = [vals[a["name"]] for a in self.facts["args"] if drop_from is None or a["pos"] < drop_from]
        return out + (extra or [])

    def run_text(self, argv: list[str]) -> str:
        head = re.split(r"\s+\{", self.command, maxsplit=1)[0].strip() or self.facts["script"]
        return " ".join([head, *argv]).strip()


def _code_text(code: int | None) -> str:
    return f"終了コード {code}" if code is not None else ""


def design(facts: dict, spec: list[dict], files: list[dict], command: str) -> list[dict]:
    ctx = _Ctx(facts, spec, files, command)
    cases: list[dict] = []

    def add(obs, tech, pre, argv, exp, src, *, setup=None, expect=None, ask=False, proposal=""):
        cases.append({
            "id": f"B-{len(cases) + 1:02d}", "obs": obs, "tech": tech, "pre": pre,
            "argv": argv, "run": ctx.run_text(argv),
            "exp": ("仕様に記載なし（案: " + proposal + "）") if ask else exp,
            "src": src or "—", "ask": ask, "origin": "auto",
            "setup": {"inputs": "sample", "unset_env": [], "lock": False, "rerun": False,
                      "outdir_missing": False, **(setup or {})},
            "expect": {"code": None, "output": None, "log": None, **(expect or {})},
        })

    sample = ctx.samples[0] if ctx.samples else "入力サンプル"
    ok_code, ok_src = ctx.code_for(r"正常")
    if ok_code is None:
        ok_code, ok_src = ctx.spec_code(r"正常|成功")
    if ok_code is None:
        ok_code, ok_src = 0, "OS の慣例（スクリプトに明記なし）"
    has_out = bool(facts["outputs"])
    out_expect = "match" if ctx.has_expected and has_out else ("exists" if has_out else None)
    out_text = "／出力が期待出力と一致" if out_expect == "match" else ("／出力ファイルを作る" if has_out else "")
    add("正常", "同値分割", f"{sample}", ctx.argv(), _code_text(ok_code) + out_text, ok_src,
        expect={"code": ok_code, "output": out_expect})

    for a in facts["args"]:
        if a["required"]:
            code, src = ctx.code_for(_USAGE)
            add("引数・必須", "同値分割", f"{a['name']} を省く", ctx.argv(drop_from=a["pos"]),
                _code_text(code) + "／使い方を表示", src, expect={"code": code, "output": "absent"},
                ask=code is None, proposal="0 以外で終わり、使い方を表示する")
        if a["format"] in ("yyyymm", "yyyymmdd"):
            base = ctx.values[a["name"]]
            y = base[:4]
            if a["format"] == "yyyymm":
                valid, invalid = [y + "01", y + "12"], [y + "00", y + "13"]
            else:
                valid, invalid = [base[:6] + "01", y + "0131"], [base[:6] + "00", y + "0132"]
            bad_code, bad_src = ctx.code_for(_FORMAT)
            for v in valid:
                add("引数・境界", "境界値分析", f"{a['name']} = {v}（有効の端）", ctx.argv({a["name"]: v}),
                    _code_text(ok_code), ok_src, expect={"code": ok_code})
            for v in invalid:
                add("引数・境界", "境界値分析", f"{a['name']} = {v}（無効の端）", ctx.argv({a["name"]: v}),
                    _code_text(bad_code) + "／出力ファイルを作らない", bad_src,
                    expect={"code": bad_code, "output": "absent" if has_out else None},
                    ask=bad_code is None, proposal="0 以外で終わり、出力を作らない")

    for f in facts["flags"]:
        argv = ctx.argv(extra=[f["name"]])
        if f["dry_run"]:
            add("フラグ", "同値分割", f"{sample}・{f['name']} を付ける", argv,
                _code_text(ok_code) + "／出力ファイルを作らない", f"スクリプト {f['line']} 行",
                expect={"code": ok_code, "output": "absent"})
        else:
            add("フラグ", "同値分割", f"{f['name']} を付ける", argv, "", "", ask=True,
                proposal=f"{f['name']} の効果が出力に表れる")

    if facts["inputs"] or ctx.samples:
        code, src = ctx.code_for(_MISSING)
        if code is None:
            code, src = ctx.spec_code(r"入力|ファイル.*(ない|無い|存在)")
        add("入力ファイル", "同値分割", "入力ファイルを置かない", ctx.argv(),
            _code_text(code) + "／出力ファイルを作らない", src,
            setup={"inputs": "missing"}, expect={"code": code, "output": "absent" if has_out else None},
            ask=code is None, proposal="0 以外で終わり、出力を作らない")
        ref = ctx.spec_ref(r"0\s*件|空の|ヘッダ(のみ|だけ)|データなし")
        add("入力ファイル", "境界値分析", "見出し行だけ（0 件）", ctx.argv(),
            "仕様の記述に従う（" + ref + "）" if ref else "", ref,
            setup={"inputs": "header_only"}, ask=not ref, proposal="終了コード 0 で、0 件の出力を作る")
        ref = ctx.spec_ref(r"形式.*(誤|不正)|フォーマット|列(数|が足りない)|項目数")
        add("入力ファイル", "同値分割", "列が足りない行を含む", ctx.argv(),
            "仕様の記述に従う（" + ref + "）" if ref else "", ref,
            setup={"inputs": "broken"}, ask=not ref, proposal="0 以外で終わり、行番号をログに書く")

    if has_out:
        ref = ctx.spec_ref(r"出力先|出力フォルダ|書き込めない")
        add("出力", "同値分割", "出力先のフォルダが無い", ctx.argv(),
            "仕様の記述に従う（" + ref + "）" if ref else "", ref,
            setup={"outdir_missing": True}, ask=not ref, proposal="0 以外で終わり、原因をログに書く")

    for lg in facts["logs"]:
        add("ログ", "同値分割", f"{sample}（正常と同じ）", ctx.argv(),
            f"{lg['path']} に追記される", f"スクリプト {lg['line']} 行",
            expect={"code": ok_code, "log": "appended"})
        break

    for env in facts["env_vars"]:
        code, src = ctx.code_for(re.escape(env["name"]) + r"|設定|環境")
        add("環境変数", "同値分割", f"{env['name']} を未設定にする", ctx.argv(),
            _code_text(code) + "／出力ファイルを作らない", src,
            setup={"unset_env": [env["name"]]}, expect={"code": code, "output": "absent" if has_out else None},
            ask=code is None, proposal="0 以外で終わり、設定が無いことを表示する")

    if has_out:
        ref = ctx.spec_ref(r"再実行|上書き|冪等|2\s*回")
        add("再実行", "状態遷移", "正常の実行のあと、同じ引数でもう一度", ctx.argv(),
            _code_text(ok_code) + "／出力が 1 回目と同じ（件数が増えない）", ref,
            setup={"rerun": True}, expect={"code": ok_code, "output": "same"},
            ask=not ref, proposal="2 回目も終了コード 0 で、出力が 1 回目と同じ")

    if facts["lock"]:
        code, src = ctx.code_for(_LOCKED)
        add("二重起動", "状態遷移", f"{facts['lock']['path']} が残っている", ctx.argv(),
            _code_text(code) + "／出力ファイルを作らない", src,
            setup={"lock": True}, expect={"code": code, "output": "absent" if has_out else None},
            ask=code is None, proposal="0 以外で終わり、実行中であることを表示する")
    return cases


def renumber(cases: list[dict]) -> list[dict]:
    return [{**c, "id": f"B-{i:02d}"} for i, c in enumerate(cases, start=1)]
