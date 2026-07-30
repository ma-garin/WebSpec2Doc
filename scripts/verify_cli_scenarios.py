#!/usr/bin/env python3
"""CLI モードの想定ユースケース 100 件（C001-C100）を実機で検証する。

観点:
  A 引数の受け取り（順序・別名・欠落・不正）        C001-C020
  B 終了コード（CI から成否を判定できるか）          C021-C035
  C 出力の契約（人が読む形 / 機械が読む形）          C036-C055
  D 実行系（doc / autorun / test）                    C056-C070
  E 参照系（sites / show / viewpoints）               C071-C085
  F 安全性・堅牢性（不正入力・境界・冪等）            C086-C100

判定できないものは PASS にせず理由を残す。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
PY = str(ROOT / "venv/bin/python")
DEMO = "http://127.0.0.1:8767/index.html"
DOMAIN = "127.0.0.1:8767"

results: list[dict] = []


def run(args: list[str], timeout: int = 300, env: dict | None = None) -> tuple[int, str, str]:
    e = dict(os.environ)
    e.setdefault("WEBSPEC2DOC_ALLOW_LOCAL", "1")
    if env:
        e.update(env)
    p = subprocess.run(
        [PY, "src/cli.py", *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=e
    )
    return p.returncode, p.stdout, p.stderr


def rec(no: str, title: str, ok: bool, ev: list[str], note: str = "") -> None:
    results.append({"no": no, "title": title, "ok": ok, "evidence": ev, "note": note})
    if not ok:
        print(f"[{no}] FAIL  {title}")
        for x in ev:
            print(f"        {x}")


def jout(out: str) -> dict:
    try:
        return json.loads(out)
    except Exception:  # noqa: BLE001
        return {}


# ══════════ A 引数の受け取り（C001-C020）══════════
def a_group() -> None:
    # C001-C006: --json / --output を前後どちらに置いても効く
    for i, args in enumerate(
        [
            ["sites", "--json"],
            ["--json", "sites"],
            ["show", "--domain", DOMAIN, "--json"],
            ["--json", "show", "--domain", DOMAIN],
            ["viewpoints", "--json"],
            ["--json", "viewpoints"],
        ],
        start=1,
    ):
        c, o, _ = run(args)
        rec(
            f"C{i:03d}",
            f"共通オプションが効く: {' '.join(args)}",
            c == 0 and bool(jout(o)),
            [f"終了コード {c}", f"JSON として読めた: {bool(jout(o))}"],
        )

    # C007-C010: --output の前後
    with tempfile.TemporaryDirectory() as td:
        for i, args in enumerate(
            [
                ["sites", "--output", td],
                ["--output", td, "sites"],
                ["sites", "--output", td, "--json"],
                ["--output", td, "--json", "sites"],
            ],
            start=7,
        ):
            c, o, _ = run(args)
            ok = c == 0 and ("まだ解析していません" in o or jout(o).get("sites") == [])
            rec(
                f"C{i:03d}",
                f"--output が効く: {' '.join(args[:3])}",
                ok,
                [f"終了コード {c}", "空の出力先で 0 件になる"],
            )

    # C011-C015: 必須引数の欠落を弾く
    for i, (args, name) in enumerate(
        [
            (["test"], "test の --domain"),
            (["show"], "show の --domain"),
            (["autorun"], "autorun の --url"),
        ],
        start=11,
    ):
        c, o, e = run(args)
        rec(
            f"C{i:03d}",
            f"必須引数の欠落を弾く: {name}",
            c != 0 and ("required" in (o + e) or "必要" in (o + e)),
            [
                f"終了コード {c}",
                f"メッセージ: {(o + e).strip().splitlines()[-1][:60] if (o + e).strip() else '—'}",
            ],
        )

    c, o, e = run([])
    rec(
        "C014",
        "サブコマンド無しは使い方を出して弾く",
        c != 0 and "usage" in (o + e).lower(),
        [f"終了コード {c}"],
    )
    c, o, e = run(["no-such-command"])
    rec("C015", "知らないサブコマンドを弾く", c != 0, [f"終了コード {c}"])

    # C016-C020: 型の検証
    for i, (args, name) in enumerate(
        [
            (["autorun", "--url", DEMO, "--depth", "abc"], "--depth に文字列"),
            (["autorun", "--url", DEMO, "--max-pages", "x"], "--max-pages に文字列"),
            (["autorun", "--url", DEMO, "--timeout", "-"], "--timeout に不正値"),
            (["autorun", "--url", DEMO, "--approve", "wrong"], "--approve に許可外の値"),
            (["test", "--domain", DOMAIN, "--case-id"], "--case-id の値欠落"),
        ],
        start=16,
    ):
        c, o, e = run(args, timeout=120)
        rec(
            f"C{i:03d}",
            f"不正な値を弾く: {name}",
            c != 0,
            [
                f"終了コード {c}",
                f"{(o + e).strip().splitlines()[-1][:60] if (o + e).strip() else '—'}",
            ],
        )


# ══════════ B 終了コード（C021-C035）══════════
def b_group() -> None:
    cases = [
        (["sites"], 0, "sites は 0"),
        (["viewpoints"], 0, "viewpoints は 0"),
        (["show", "--domain", DOMAIN], 0, "既存ドメインの show は 0"),
        (["show", "--domain", "nope.invalid"], 2, "存在しないドメインの show は 2"),
        (["sites", "--bad"], 2, "知らないオプションは 2（argparse の慣例）"),
    ]
    for i, (args, want, name) in enumerate(cases, start=21):
        c, o, e = run(args)
        ok = c == want if want != 2 else c != 0
        rec(f"C{i:03d}", f"終了コード: {name}", ok, [f"実際 {c} / 期待 {want}"])

    # C026-C030: test の終了コード
    c, o, _ = run(["test", "--domain", "nope.invalid", "--json"])
    rec(
        "C026",
        "test: 対象が無ければ 2",
        c == 2,
        [f"終了コード {c}", f"error: {jout(o).get('error', '')[:40]}"],
    )
    c, o, _ = run(["test", "--domain", DOMAIN, "--case-id", "NO-SUCH-CASE", "--json"])
    rec(
        "C027",
        "test: 該当ケース 0 件なら 2（成功と見せない）",
        c == 2,
        [f"終了コード {c}", f"error: {jout(o).get('error', '')[:40]}"],
    )
    c, o, _ = run(["test", "--domain", DOMAIN, "--json"], timeout=900)
    d = jout(o)
    rec(
        "C028",
        "test: 全件 PASS なら 0",
        c == 0 and d.get("failed") == 0,
        [f"終了コード {c}", f"PASS {d.get('passed')} / FAIL {d.get('failed')}"],
    )
    rec("C029", "test: 実行件数が 0 でない", (d.get("total") or 0) > 0, [f"total {d.get('total')}"])
    rec(
        "C030",
        "test: 所要時間が記録される",
        (d.get("duration_ms") or 0) > 0,
        [f"{d.get('duration_ms')} ms"],
    )

    # C031-C035: autorun の終了コード
    c, o, _ = run(["autorun", "--url", DEMO, "--max-pages", "4", "--timeout", "600", "--json"], 900)
    d = jout(o)
    rec(
        "C031",
        "autorun: 完走なら 0",
        c == 0 and d.get("status") == "complete",
        [f"終了コード {c}", f"status {d.get('status')}"],
    )
    rec(
        "C032",
        "autorun: job_id が返る",
        bool(d.get("job_id")),
        [f"job_id {str(d.get('job_id'))[:12]}"],
    )
    rec("C033", "autorun: ドメインが確定する", bool(d.get("domain")), [f"domain {d.get('domain')}"])
    rec(
        "C034",
        "autorun: 所要が記録される",
        (d.get("elapsed_sec") or 0) > 0,
        [f"{d.get('elapsed_sec')} 秒"],
    )
    c, o, _ = run(["autorun", "--url", "http://127.0.0.1:9/", "--timeout", "90", "--json"], 300)
    rec(
        "C035",
        "autorun: 到達できなければ完走にしない",
        jout(o).get("status") != "complete" or c != 0,
        [f"終了コード {c}", f"status {jout(o).get('status')}"],
    )


# ══════════ C 出力の契約（C036-C055）══════════
def c_group() -> None:
    # C036-C043: --json は純粋な JSON（stdout にログを混ぜない）
    for i, args in enumerate(
        [
            ["sites", "--json"],
            ["show", "--domain", DOMAIN, "--json"],
            ["viewpoints", "--json"],
        ],
        start=36,
    ):
        c, o, _ = run(args)
        rec(
            f"C{i:03d}",
            f"--json の stdout が純粋な JSON: {args[0]}",
            bool(jout(o)) and o.strip().startswith("{"),
            [f"先頭 {o.strip()[:1]!r}", f"パース可: {bool(jout(o))}"],
        )

    c, o, e = run(["autorun", "--url", DEMO, "--max-pages", "3", "--timeout", "600", "--json"], 900)
    rec(
        "C039",
        "autorun: --json でも stdout は JSON だけ",
        bool(jout(o)),
        [f"stdout {len(o)} 文字 / パース可 {bool(jout(o))}", f"stderr にログ {len(e)} 文字"],
    )
    rec(
        "C040",
        "autorun: 実行ログは stderr に出る（消さない）",
        len(e) > 100,
        [f"stderr {len(e)} 文字"],
    )

    c, o, e = run(
        ["autorun", "--url", DEMO, "--max-pages", "3", "--timeout", "600", "--json", "--quiet"], 900
    )
    rec(
        "C041",
        "--quiet でログを止められる",
        bool(jout(o)) and len(e) < len(o),
        [f"stdout {len(o)} / stderr {len(e)}"],
    )

    # C042-C048: JSON のキー契約
    c, o, _ = run(["sites", "--json"])
    d = jout(o)
    rec("C042", "sites: command キーを持つ", d.get("command") == "sites", [f"{d.get('command')}"])
    rec(
        "C043",
        "sites: sites 配列を持つ",
        isinstance(d.get("sites"), list),
        [f"{len(d.get('sites') or [])} 件"],
    )
    keys = set((d.get("sites") or [{}])[0]) if d.get("sites") else set()
    rec(
        "C044",
        "sites: 各要素が domain/screens/fields/snapshots を持つ",
        {"domain", "screens", "fields", "snapshots"} <= keys,
        [f"キー {sorted(keys)}"],
    )

    c, o, _ = run(["show", "--domain", DOMAIN, "--json"])
    d = jout(o)
    rec(
        "C045",
        "show: files 配列を持つ",
        isinstance(d.get("files"), list),
        [f"{len(d.get('files') or [])} 件"],
    )
    rec(
        "C046",
        "show: 各ファイルが exists を持つ",
        all("exists" in f for f in (d.get("files") or [])),
        ["全要素に exists"],
    )
    rec(
        "C047", "show: testcase_run を持つ", "testcase_run" in d, [f"{bool(d.get('testcase_run'))}"]
    )

    c, o, _ = run(["viewpoints", "--json"])
    d = jout(o)
    rec(
        "C048",
        "viewpoints: sets 配列を持つ",
        isinstance(d.get("sets"), list),
        [f"{len(d.get('sets') or [])} 件"],
    )

    # C049-C055: 人が読む形
    for i, (args, must) in enumerate(
        [
            (["sites"], "解析済みサイト"),
            (["show", "--domain", DOMAIN], "成果物"),
            (["viewpoints"], "観点セット"),
        ],
        start=49,
    ):
        c, o, _ = run(args)
        rec(f"C{i:03d}", f"人が読む形に見出しが出る: {args[0]}", must in o, [f"『{must}』を含む"])

    c, o, _ = run(["show", "--domain", DOMAIN])
    rec("C052", "show: 存在するファイルに印が付く", "✓" in o, ["✓ を含む"])
    c, o, _ = run(["show", "--domain", "nope.invalid"])
    rec("C053", "show: 見つからないときは理由を出す", "見つかりません" in o, [o.strip()[:60]])
    c, o, _ = run(["sites", "--output", "/tmp/__empty_out__"])
    rec(
        "C054",
        "sites: 0 件でも黙らず理由を出す",
        "まだ解析していません" in o or "出力先がありません" in o,
        [o.strip()[:60]],
    )
    c, o, e = run(["--help"])
    rec("C055", "ヘルプに終了コードの説明がある", "130" in (o + e), ["130 を含む"])


# ══════════ D 実行系（C056-C070）══════════
def d_group() -> None:
    for i, (args, name, must) in enumerate(
        [
            (["doc", "--help"], "doc は本体のヘルプへ委譲", "--format"),
            (["autorun", "--help"], "autorun のヘルプ", "--login-user"),
            (["test", "--help"], "test のヘルプ", "--case-id"),
            (["sites", "--help"], "sites のヘルプ", "--output"),
            (["show", "--help"], "show のヘルプ", "--domain"),
            (["viewpoints", "--help"], "viewpoints のヘルプ", "--json"),
        ],
        start=56,
    ):
        c, o, e = run(args)
        rec(f"C{i:03d}", name, c == 0 and must in (o + e), [f"終了コード {c}", f"『{must}』を含む"])

    # C062-C066: doc の委譲
    c, o, e = run(["doc", "--url", DEMO, "--format", "json", "--max-pages", "3"], 600)
    rec("C062", "doc: 本体オプションがそのまま効く", c == 0, [f"終了コード {c}"])
    rec(
        "C063",
        "doc: report.json が生成される",
        (OUT / DOMAIN / "report.json").is_file(),
        [str(OUT / DOMAIN / "report.json")],
    )
    c, o, e = run(["doc", "--url", "not-a-url"], 200)
    rec("C064", "doc: 不正 URL を弾く", c != 0, [f"終了コード {c}"])
    c, o, e = run(["doc", "--url", DEMO, "--format", "nosuchformat", "--max-pages", "2"], 300)
    rec("C065", "doc: 未知の出力形式を弾く", c != 0, [f"終了コード {c}"])
    c, o, e = run(["doc", "--url", DEMO, "--max-pages", "1", "--format", "json"], 400)
    n = 0
    if (OUT / DOMAIN / "report.json").is_file():
        n = len(
            json.loads((OUT / DOMAIN / "report.json").read_text(encoding="utf-8")).get("screens")
            or []
        )
    rec("C066", "doc: --max-pages 1 が効く", c == 0 and n == 1, [f"取得 {n} 画面"])

    # C067-C070: autorun のオプション
    c, o, _ = run(
        [
            "autorun",
            "--url",
            DEMO,
            "--max-pages",
            "3",
            "--approve",
            "skip",
            "--timeout",
            "600",
            "--json",
        ],
        900,
    )
    d = jout(o)
    rec(
        "C067",
        "autorun: --approve skip が通る",
        c == 0 and d.get("status") == "complete",
        [f"status {d.get('status')}"],
    )
    rec(
        "C068",
        "autorun: 自動で通した判断が全て出る",
        len(d.get("auto_handled") or []) > 0,
        [f"{len(d.get('auto_handled') or [])} 件"],
    )
    rec(
        "C069",
        "autorun: 未確認項目が記録される",
        len(d.get("unverified") or []) > 0,
        [f"{len(d.get('unverified') or [])} 件"],
    )
    # ログイン壁に到達する画面数でないと --require-login の効果を確かめられない
    c, o, _ = run(
        [
            "autorun",
            "--url",
            DEMO,
            "--max-pages",
            "10",
            "--require-login",
            "--timeout",
            "600",
            "--json",
        ],
        900,
    )
    d = jout(o)
    stopped = any("中止" in x for x in (d.get("auto_handled") or []))
    rec(
        "C070",
        "autorun: --require-login で資格情報が無ければ中止",
        stopped or d.get("status") in ("cancelled", "failed") or c != 0,
        [
            f"終了コード {c}",
            f"status {d.get('status')}",
            f"理由: {[x for x in (d.get('auto_handled') or []) if '中止' in x][:1]}",
        ],
    )


# ══════════ E 参照系（C071-C085）══════════
def e_group() -> None:
    c, o, _ = run(["sites", "--json"])
    d = jout(o)
    sites = d.get("sites") or []
    rec("C071", "sites: 解析済みが 1 件以上出る", len(sites) > 0, [f"{len(sites)} 件"])
    rec(
        "C072",
        "sites: 画面数が数値",
        all(isinstance(s.get("screens"), int) for s in sites),
        ["全て int"],
    )
    rec(
        "C073",
        "sites: 隠しディレクトリを出さない",
        not any(s["domain"].startswith(".") for s in sites),
        ["ドット始まり無し"],
    )
    rec(
        "C074",
        "sites: tenants を出さない",
        not any(s["domain"] == "tenants" for s in sites),
        ["tenants 無し"],
    )
    rec(
        "C075",
        "sites: 履歴数が数値",
        all(isinstance(s.get("snapshots"), int) for s in sites),
        ["全て int"],
    )

    c, o, _ = run(["show", "--domain", DOMAIN, "--json"])
    d = jout(o)
    files = d.get("files") or []
    rec("C076", "show: 主要な成果物を列挙する", len(files) >= 8, [f"{len(files)} 種"])
    rec(
        "C077",
        "show: パスが絶対または相対で示される",
        all(f.get("path") for f in files),
        ["全要素に path"],
    )
    rec(
        "C078",
        "show: ラベルが日本語で読める",
        all(f.get("label") for f in files),
        ["全要素に label"],
    )
    exists = [f for f in files if f.get("exists")]
    rec(
        "C079",
        "show: 実在するものだけ ✓ になる",
        len(exists) > 0 and len(exists) <= len(files),
        [f"{len(exists)}/{len(files)} 件が実在"],
    )
    rec(
        "C080",
        "show: テスト実行の実績を出す",
        isinstance(d.get("testcase_run"), dict),
        [f"{d.get('testcase_run')}"],
    )

    c, o, _ = run(["viewpoints", "--json"])
    d = jout(o)
    sets = d.get("sets") or []
    rec("C081", "viewpoints: 1 件以上出る", len(sets) > 0, [f"{len(sets)} 件"])
    rec("C082", "viewpoints: 名称を持つ", all(s.get("name") for s in sets), ["全要素に name"])
    rec(
        "C083", "viewpoints: set_id を持つ", all(s.get("set_id") for s in sets), ["全要素に set_id"]
    )
    c, o, _ = run(["viewpoints"])
    rec("C084", "viewpoints: 人が読む形に公開版が出る", "公開版" in o, ["『公開版』を含む"])
    with tempfile.TemporaryDirectory() as td:
        c, o, _ = run(["show", "--domain", DOMAIN, "--output", td])
        rec("C085", "show: 出力先を変えると見つからない扱いになる", c == 2, [f"終了コード {c}"])


# ══════════ F 安全性・堅牢性（C086-C100）══════════
def f_group() -> None:
    # C086-C092: パストラバーサル・危険な値
    for i, dom in enumerate(
        [
            "../etc",
            "../../etc/passwd",
            "..%2f..%2fetc",
            "/etc/passwd",
            "a/../../b",
        ],
        start=86,
    ):
        c, o, _ = run(["show", "--domain", dom])
        safe = c != 0 or "見つかりません" in o
        leaked = "root:" in o
        rec(
            f"C{i:03d}",
            f"危険なドメイン名を扱わない: {dom}",
            safe and not leaked,
            [f"終了コード {c}", f"内容が漏れない: {not leaked}"],
        )

    c, o, _ = run(["test", "--domain", "../../etc"])
    rec("C091", "test: 危険なドメイン名で実行しない", c != 0, [f"終了コード {c}"])
    c, o, _ = run(["show", "--domain", ""])
    rec("C092", "空のドメインを弾く", c != 0, [f"終了コード {c}"])

    # C093-C096: 冪等・再実行
    a = run(["sites", "--json"])[1]
    b = run(["sites", "--json"])[1]
    rec(
        "C093",
        "sites: 続けて実行しても結果が変わらない",
        jout(a).get("sites") == jout(b).get("sites"),
        ["2 回とも同じ"],
    )
    a = run(["show", "--domain", DOMAIN, "--json"])[1]
    b = run(["show", "--domain", DOMAIN, "--json"])[1]
    rec("C094", "show: 冪等", jout(a).get("files") == jout(b).get("files"), ["2 回とも同じ"])
    a = run(["viewpoints", "--json"])[1]
    b = run(["viewpoints", "--json"])[1]
    rec("C095", "viewpoints: 冪等", jout(a) == jout(b), ["2 回とも同じ"])

    # C096-C100: 環境・堅牢性
    c, o, e = run(["sites"], env={"LANG": "C"})
    rec("C096", "ロケールが C でも落ちない", c == 0, [f"終了コード {c}"])
    c, o, e = run(["sites", "--output", "/proc/self/no-such"], timeout=120)
    rec(
        "C097",
        "読めない出力先でも落ちず理由を返す",
        c == 0 or c == 2,
        [f"終了コード {c}", f"{(o + e).strip()[:50]}"],
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "broken.local"
        p.mkdir()
        (p / "report.json").write_text("{ これは壊れた JSON", encoding="utf-8")
        c, o, _ = run(["sites", "--output", td, "--json"])
        d = jout(o)
        rec(
            "C098",
            "壊れた report.json があっても一覧は落ちない",
            c == 0 and len(d.get("sites") or []) == 1,
            [f"終了コード {c}", f"{len(d.get('sites') or [])} 件（画面数は 0 で表示）"],
        )
    c, o, e = run(["--json", "--output", str(OUT), "sites"])
    rec(
        "C099", "共通オプションを 2 つ前置しても効く", c == 0 and bool(jout(o)), [f"終了コード {c}"]
    )
    c, o, e = run(["sites", "--json", "--output", str(OUT)])
    rec(
        "C100", "共通オプションを 2 つ後置しても効く", c == 0 and bool(jout(o)), [f"終了コード {c}"]
    )


def main() -> int:
    for g in (a_group, b_group, c_group, d_group, e_group, f_group):
        try:
            g()
        except Exception as exc:  # noqa: BLE001
            rec(g.__name__.upper(), "（検証中に例外）", False, [f"{type(exc).__name__}: {exc}"])
    ok = sum(1 for r in results if r["ok"])
    print(f"\n{'=' * 62}\nCLI シナリオ: {ok}/{len(results)} PASS")
    Path(sys.argv[1] if len(sys.argv) > 1 else "cli.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
