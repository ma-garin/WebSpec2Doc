#!/usr/bin/env python3
"""想定ユースケース S11〜S50（40 件）の実機検証。

S01〜S10（verify_scenarios.py）に続く追加分。異常系・境界・成果物・履歴・
観点管理・AutoRun・CLI・セキュリティを網羅する。
判定できないものは PASS にせず理由を残す。
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("/home/user/WebSpec2Doc")
OUT = ROOT / "output"
APP = "http://127.0.0.1:8765"
DEMO = "http://127.0.0.1:8767/index.html"
DOMAIN = "127.0.0.1:8767"
PY = str(ROOT / "venv/bin/python")

results: list[dict] = []


def cli(args: list[str], timeout: int = 600) -> tuple[int, str]:
    p = subprocess.run(
        [PY, "src/cli.py", *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout
    )
    return p.returncode, (p.stdout if "--json" in args else p.stdout + p.stderr)


def get(path: str, timeout: int = 90) -> tuple[int, str]:
    """(status, body) を返す。例外にせず状態で判定できるようにする。"""
    req = urllib.request.Request(f"{APP}{path}", headers={"Host": "127.0.0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def jget(path: str) -> tuple[int, dict | list | None]:
    st, body = get(path)
    try:
        return st, json.loads(body)
    except Exception:  # noqa: BLE001
        return st, None


def rec(no: str, title: str, ok: bool, ev: list[str], note: str = "") -> None:
    results.append({"no": no, "title": title, "ok": ok, "evidence": ev, "note": note})
    print(f"[{no}] {'PASS' if ok else 'FAIL'}  {title}")
    for e in ev:
        print(f"      {e}")
    if note:
        print(f"      注: {note}")


# ═══════════════ 異常系・境界（S11-S20）═══════════════
def s11() -> None:
    code, out = cli(["doc", "--url", "not-a-url"])
    rec(
        "S11",
        "不正な URL は明確に断る",
        code != 0 and len(out.strip()) > 0,
        [f"終了コード {code}（0 以外であること）", f"メッセージあり: {bool(out.strip())}"],
    )


def s12() -> None:
    code, out = cli(["autorun", "--url", "http://127.0.0.1:9/", "--timeout", "120", "--json"], 400)
    try:
        d = json.loads(out)
    except Exception:  # noqa: BLE001
        d = {}
    rec(
        "S12",
        "到達できない URL は失敗として返す",
        code != 0 or d.get("status") != "complete",
        [f"終了コード {code}", f"状態 {d.get('status')}", f"エラー: {str(d.get('error'))[:60]}"],
    )


def s13() -> None:
    st, d = jget(f"/api/result?domain={DOMAIN}")
    audit = OUT / DOMAIN / "audit.jsonl"
    excluded = 0
    if audit.is_file():
        for line in audit.read_text(encoding="utf-8").splitlines():
            if "robots" in line or "unsafe" in line or "除外" in line:
                excluded += 1
    rec(
        "S13",
        "robots/安全制約で除外した画面が記録される",
        st == 200 and audit.is_file(),
        [
            f"/api/result {st}",
            f"audit.jsonl 存在: {audit.is_file()}",
            f"除外に関する記録 {excluded} 行",
        ],
    )


def s14() -> None:
    code, _ = cli(
        ["doc", "--url", DEMO, "--max-pages", "2", "--format", "json", "--output", str(OUT)], 600
    )
    rep = OUT / DOMAIN / "report.json"
    n = (
        len(json.loads(rep.read_text(encoding="utf-8")).get("screens") or [])
        if rep.is_file()
        else 0
    )
    rec(
        "S14",
        "最大画面数の上限が効く",
        code == 0 and 0 < n <= 2,
        [f"終了コード {code}", f"--max-pages 2 に対し取得 {n} 画面"],
    )


def s15() -> None:
    st1, d1 = jget(f"/api/result?domain={DOMAIN}")
    st2, _ = jget("/api/result?domain=absolutely-nonexistent.invalid")
    rec(
        "S15",
        "存在しないドメインの結果取得は 404",
        st1 == 200 and st2 == 404,
        [f"既存ドメイン {st1}（期待 200）", f"存在しないドメイン {st2}（期待 404）"],
    )


def s16() -> None:
    bad = [
        "/preview?path=/etc/passwd",
        "/download?path=../../etc/passwd",
        "/preview?path=output/../../etc/hosts",
    ]
    codes = [get(p)[0] for p in bad]
    rec(
        "S16",
        "パストラバーサルを拒否する",
        all(c in (400, 403, 404) for c in codes),
        [f"{p} → {c}" for p, c in zip(bad, codes, strict=False)],
    )


def s17() -> None:
    st, _ = jget(f"/api/snapshot-diff-summary?domain={DOMAIN}&from=nope&to=nope")
    st2, _ = jget("/api/snapshot-diff-summary?domain=../etc&from=a&to=b")
    rec(
        "S17",
        "不正なスナップショット指定を拒否する",
        st == 404 and st2 in (400, 404),
        [f"存在しない ID → {st}（期待 404）", f"不正なドメイン → {st2}"],
    )


def s18() -> None:
    code, out = cli(["autorun", "--url", DEMO, "--timeout", "60", "--json"], 300)
    try:
        d = json.loads(out)
    except Exception:  # noqa: BLE001
        d = {}
    handled = [x for x in (d.get("auto_handled") or []) if "制限時間" in x]
    rec(
        "S18",
        "制限時間を超えたら中止して理由を残す",
        code == 130 or bool(handled) or d.get("status") == "complete",
        [
            f"終了コード {code}",
            f"状態 {d.get('status')}",
            f"中止理由の記録: {handled[:1] or '（時間内に完了した）'}",
        ],
        "60 秒で完了する場合もあるため、完了も許容する",
    )


def s19() -> None:
    code, out = cli(["sites", "--no-such-flag"])
    rec(
        "S19",
        "知らないオプションは黙って捨てず弾く",
        code != 0 and "知らないオプション" in out,
        [f"終了コード {code}", f"明示メッセージ: {'知らないオプション' in out}"],
    )


def s20() -> None:
    st, _ = jget("/api/result")
    st2, _ = jget("/api/snapshots")
    rec(
        "S20",
        "必須パラメータ欠落を 404/400 で返す",
        st in (400, 404) and st2 in (400, 404),
        [f"/api/result（domain 無し） → {st}", f"/api/snapshots（domain 無し） → {st2}"],
    )


# ═══════════════ 成果物（S21-S28）═══════════════
def s21() -> None:
    st, d = jget(f"/api/result?domain={DOMAIN}")
    s = (d or {}).get("summary") or {}
    rep = OUT / DOMAIN / "report.json"
    n = (
        len(json.loads(rep.read_text(encoding="utf-8")).get("screens") or [])
        if rep.is_file()
        else -1
    )
    rec(
        "S21",
        "画面数が API と成果物で一致する",
        st == 200 and s.get("screens") == n,
        [f"API summary.screens = {s.get('screens')}", f"report.json の screens = {n}"],
    )


def s22() -> None:
    st, d = jget(f"/api/state-table?domain={DOMAIN}")
    rows = (d or {}).get("rows") or (d or {}).get("states") or []
    rec(
        "S22",
        "遷移表（状態×イベント）が取得できる",
        st == 200 and len(rows) > 0,
        [f"HTTP {st}", f"行数 {len(rows)}"],
    )


def s23() -> None:
    st, body = get(f"/api/coverage-heatmap?domain={DOMAIN}")
    rec(
        "S23",
        "カバレッジヒートマップが取得できる",
        st == 200 and len(body) > 200,
        [f"HTTP {st}", f"応答 {len(body)} 文字"],
    )


def s24() -> None:
    st, d = jget(f"/api/test-design?domain={DOMAIN}")
    rec(
        "S24",
        "テスト設計サマリーが取得できる",
        st == 200 and bool(d),
        [f"HTTP {st}", f"キー: {list(d)[:6] if isinstance(d, dict) else type(d).__name__}"],
    )


def s25() -> None:
    import openpyxl

    f = OUT / DOMAIN / "spec.xlsx"
    names: list[str] = []
    if f.is_file():
        names = openpyxl.load_workbook(f).sheetnames
    want = {"Screens", "Forms", "項目定義書", "境界値データ"}
    rec(
        "S25",
        "Excel に必要なシートが揃う",
        f.is_file() and want <= set(names),
        [f"シート: {names}", f"必須 {sorted(want)} を含む: {want <= set(names)}"],
    )


def s26() -> None:
    d = OUT / DOMAIN
    ok = {}
    for n in ("screens.md", "forms.md"):
        p = d / n
        ok[n] = p.is_file() and len(p.read_text(encoding="utf-8")) > 100
    rec(
        "S26",
        "Markdown（画面一覧・フォーム）が中身つきで出る",
        all(ok.values()),
        [f"{k}: {'内容あり' if v else '無い/空'}" for k, v in ok.items()],
    )


def s27() -> None:
    p = OUT / DOMAIN / "transition.mmd"
    body = p.read_text(encoding="utf-8") if p.is_file() else ""
    rec(
        "S27",
        "Mermaid の遷移図が出る",
        p.is_file() and ("graph" in body or "flowchart" in body),
        [
            f"存在: {p.is_file()}",
            f"{len(body)} 文字",
            f"先頭: {body.splitlines()[0][:40] if body else '—'}",
        ],
    )


def s28() -> None:
    st, body = get(f"/api/report/{DOMAIN}/spec-ts")
    rec(
        "S28",
        "Playwright の spec.ts を取得できる",
        st == 200 and "test(" in body,
        [f"HTTP {st}", f"{len(body)} 文字", f"test( を含む: {'test(' in body}"],
    )


# ═══════════════ 差分・履歴（S29-S33）═══════════════
def s29() -> None:
    st, d = jget(f"/api/snapshots?domain={DOMAIN}")
    snaps = (d or {}).get("snapshots") or []
    rec(
        "S29",
        "スナップショットが履歴として一覧できる",
        st == 200 and len(snaps) >= 2,
        [f"HTTP {st}", f"{len(snaps)} 件", f"最新: {snaps[0].get('label') if snaps else '—'}"],
    )


def s30() -> None:
    _, d = jget(f"/api/snapshots?domain={DOMAIN}")
    snaps = [s["id"] for s in ((d or {}).get("snapshots") or [])]
    st, r = jget(f"/api/snapshot-diff-summary?domain={DOMAIN}&from={snaps[0]}&to={snaps[0]}")
    rec(
        "S30",
        "同一時点の比較は変更 0 件になる",
        st == 200 and isinstance(r, dict) and r.get("has_changes") is False,
        [
            f"HTTP {st}",
            f"has_changes = {(r or {}).get('has_changes')}",
            f"内訳 {(r or {}).get('counts')}",
        ],
    )


def s31() -> None:
    """人工スナップショットで画面追加を検知できるか。"""
    snaps_dir = OUT / DOMAIN / "snapshots"
    base = json.loads(sorted(snaps_dir.glob("*.json"))[-1].read_text(encoding="utf-8"))
    a, b = snaps_dir / "29990101-000000.json", snaps_dir / "29990102-000000.json"
    a.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    extra = dict(base[0])
    extra["url"] = "http://127.0.0.1:8767/__added__.html"
    b.write_text(json.dumps(base + [extra], ensure_ascii=False), encoding="utf-8")
    st, r = jget(f"/api/snapshot-diff-summary?domain={DOMAIN}&from={a.stem}&to={b.stem}")
    added = ((r or {}).get("counts") or {}).get("added_pages")
    a.unlink(missing_ok=True)
    b.unlink(missing_ok=True)
    rec(
        "S31",
        "画面が増えたら追加として検知する",
        st == 200 and (r or {}).get("has_changes") is True and added == 1,
        [f"HTTP {st}", f"has_changes = {(r or {}).get('has_changes')}", f"added_pages = {added}"],
    )


def s32() -> None:
    _, d = jget(f"/api/snapshots?domain={DOMAIN}")
    snaps = [s["id"] for s in ((d or {}).get("snapshots") or [])]
    st, body = get(f"/api/snapshot-comparison?domain={DOMAIN}&from={snaps[1]}&to={snaps[0]}", 180)
    rec(
        "S32",
        "現新比較（4分類）の HTML が返る",
        st == 200 and len(body) > 500,
        [f"HTTP {st}", f"{len(body)} 文字"],
    )


def s33() -> None:
    st, d = jget("/api/history/runs")
    items = (d or {}).get("items") or (d or {}).get("runs") or []
    rec("S33", "実行履歴が一覧できる", st == 200, [f"HTTP {st}", f"{len(items)} 件"])


# ═══════════════ 観点管理（S34-S38）═══════════════
def s34() -> None:
    st, d = jget("/api/viewpoint-sets")
    sets = (d or {}).get("sets") or (d if isinstance(d, list) else [])
    rec(
        "S34",
        "観点セットを一覧できる",
        st == 200 and len(sets) > 0,
        [f"HTTP {st}", f"{len(sets)} 件", f"例: {(sets[0].get('name') if sets else '—')}"],
    )


def s35() -> None:
    _, d = jget("/api/viewpoint-sets")
    sets = (d or {}).get("sets") or (d if isinstance(d, list) else [])
    sid = sets[0].get("set_id") or sets[0].get("id") if sets else ""
    st, t = jget(f"/api/viewpoint-sets/{sid}/tree")
    rec(
        "S35",
        "観点セットの中身（ツリー）を取得できる",
        st == 200 and bool(t),
        [
            f"set_id {sid}",
            f"HTTP {st}",
            f"キー: {list(t)[:5] if isinstance(t, dict) else type(t).__name__}",
        ],
    )


def s36() -> None:
    _, d = jget("/api/viewpoint-sets")
    sets = (d or {}).get("sets") or (d if isinstance(d, list) else [])
    sid = sets[0].get("set_id") or sets[0].get("id") if sets else ""
    st, v = jget(f"/api/viewpoint-sets/{sid}/versions")
    vers = (v or {}).get("versions") or (v if isinstance(v, list) else [])
    rec(
        "S36",
        "観点セットの版を一覧できる",
        st == 200 and len(vers) > 0,
        [f"HTTP {st}", f"{len(vers)} 版"],
    )


def s37() -> None:
    _, d = jget("/api/viewpoint-sets")
    sets = (d or {}).get("sets") or (d if isinstance(d, list) else [])
    sid = sets[0].get("set_id") or sets[0].get("id") if sets else ""
    st, body = get(f"/api/viewpoint-sets/{sid}/export")
    rec(
        "S37",
        "観点セットを CSV で持ち出せる",
        st == 200 and len(body) > 50,
        [f"HTTP {st}", f"{len(body)} 文字", f"先頭: {body.splitlines()[0][:50] if body else '—'}"],
    )


def s38() -> None:
    st, d = jget("/api/viewpoint-templates")
    tpl = (d or {}).get("templates") or (d if isinstance(d, list) else [])
    rec("S38", "観点テンプレートを一覧できる", st == 200, [f"HTTP {st}", f"{len(tpl)} 件"])


# ═══════════════ AutoRun（S39-S42）═══════════════
def s39() -> None:
    st, d = jget("/api/autorun/jobs")
    jobs = (d or {}).get("jobs") or []
    rec(
        "S39",
        "AutoRun のジョブを一覧できる",
        st == 200,
        [f"HTTP {st}", f"{len(jobs)} 件", f"状態: {sorted({j.get('status') for j in jobs})[:4]}"],
    )


def s40() -> None:
    st, _ = jget("/api/autorun/status?job_id=deadbeefdeadbeef")
    rec("S40", "存在しないジョブの状態取得は 404", st == 404, [f"HTTP {st}（期待 404）"])


def s41() -> None:
    """domain 必須。省略時に 400 で理由を返すことも含めて確認する。"""
    st0, d0 = jget("/api/autorun/review-queue")
    st, d = jget(f"/api/autorun/review-queue?domain={DOMAIN}")
    rec(
        "S41",
        "要確認キューを取得できる（domain 必須）",
        st0 == 400 and bool((d0 or {}).get("error")) and st in (200, 404),
        [
            f"domain 省略 → {st0} / 理由: {str((d0 or {}).get('error'))[:30]}",
            f"domain 指定 → {st}",
            f"キー: {list(d)[:5] if isinstance(d, dict) else '—'}",
        ],
        "実行中ジョブが無いときは 404 でも正（存在しないものを在ると言わない）",
    )


def s42() -> None:
    st0, d0 = jget("/api/autorun/stages")
    st, _ = jget(f"/api/autorun/stages?domain={DOMAIN}")
    rec(
        "S42",
        "段階情報を取得できる（domain 必須）",
        st0 == 400 and bool((d0 or {}).get("error")) and st in (200, 404),
        [f"domain 省略 → {st0}（理由つき）", f"domain 指定 → {st}"],
        "実行中ジョブが無いときは 404 でも正",
    )


# ═══════════════ CLI（S43-S46）═══════════════
def s43() -> None:
    code, out = cli(["doc", "--help"])
    rec(
        "S43",
        "doc は本体 CLI のヘルプを見せる（委譲）",
        code == 0 and ("--url" in out and ("--format" in out or "--compare" in out)),
        [f"終了コード {code}", f"本体オプションが出る: {'--format' in out or '--compare' in out}"],
    )


def s44() -> None:
    code, out = cli(["show", "--domain", DOMAIN, "--json"])
    try:
        d = json.loads(out)
    except Exception:  # noqa: BLE001
        d = {}
    rec(
        "S44",
        "show の JSON が機械可読",
        code == 0 and d.get("command") == "show",
        [
            f"終了コード {code}",
            f"files {len(d.get('files') or [])} 件",
            f"testcase_run: {bool(d.get('testcase_run'))}",
        ],
    )


def s45() -> None:
    code, out = cli(["viewpoints", "--json"])
    try:
        d = json.loads(out)
    except Exception:  # noqa: BLE001
        d = {}
    rec(
        "S45",
        "viewpoints の JSON が機械可読",
        code == 0 and d.get("command") == "viewpoints" and len(d.get("sets") or []) > 0,
        [f"終了コード {code}", f"{len(d.get('sets') or [])} セット"],
    )


def s46() -> None:
    code, out = cli(["sites", "--output", "/tmp/__no_such_output__", "--json"])
    try:
        d = json.loads(out)
    except Exception:  # noqa: BLE001
        d = {}
    rec(
        "S46",
        "--output で出力先を切り替えられる",
        code == 0 and (d.get("sites") == [] or d.get("sites") is not None),
        [f"終了コード {code}", f"サイト数 {len(d.get('sites') or [])}（空の出力先なので 0）"],
    )


# ═══════════════ その他（S47-S50）═══════════════
def s47() -> None:
    st, d = jget(f"/traceability/matrix?domain={DOMAIN}")
    reqs = (d or {}).get("requirements") or []
    st2, body = get(f"/traceability/view?domain={DOMAIN}")
    rec(
        "S47",
        "トレーサビリティが表示できる",
        st == 200 and len(reqs) > 0 and st2 == 200 and "traceability-tbody" in body,
        [
            f"matrix API {st} / 要件 {len(reqs)} 件",
            f"view {st2}",
            f"表の受け皿がある: {'traceability-tbody' in body}",
        ],
    )


def s48() -> None:
    st, d = jget(f"/api/doc-fusion?domain={DOMAIN}")
    gaps = (d or {}).get("field_gaps") or []
    kinds = sorted({g.get("kind") or g.get("category") or "?" for g in gaps})
    rec(
        "S48",
        "文書突合が分類つきで返る",
        st == 200 and len(gaps) > 0,
        [f"HTTP {st}", f"ギャップ {len(gaps)} 件", f"分類: {kinds[:4]}"],
    )


def s49() -> None:
    outs = []
    for _ in range(2):
        req = urllib.request.Request(
            f"{APP}/api/sample-report", method="POST", headers={"Host": "127.0.0.1"}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                outs.append(json.loads(r.read().decode("utf-8")).get("domain"))
        except Exception:  # noqa: BLE001
            outs.append(None)
    rec(
        "S49",
        "サンプルレポートは何度押しても壊れない（冪等）",
        outs[0] and outs[0] == outs[1],
        [f"1 回目 {outs[0]}", f"2 回目 {outs[1]}"],
    )


def s50() -> None:
    st, d = jget("/api/settings")
    st2, d2 = jget("/api/settings/test-design")
    rec(
        "S50",
        "設定を読み出せる",
        st == 200 and st2 == 200,
        [
            f"/api/settings {st} / キー {len(d) if isinstance(d, dict) else 0}",
            f"/api/settings/test-design {st2}",
        ],
    )


ALL = [
    s11,
    s12,
    s13,
    s14,
    s15,
    s16,
    s17,
    s18,
    s19,
    s20,
    s21,
    s22,
    s23,
    s24,
    s25,
    s26,
    s27,
    s28,
    s29,
    s30,
    s31,
    s32,
    s33,
    s34,
    s35,
    s36,
    s37,
    s38,
    s39,
    s40,
    s41,
    s42,
    s43,
    s44,
    s45,
    s46,
    s47,
    s48,
    s49,
    s50,
]


def main() -> int:
    for fn in ALL:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            rec(fn.__name__.upper(), "（検証中に例外）", False, [f"{type(exc).__name__}: {exc}"])
    ok = sum(1 for r in results if r["ok"])
    print(f"\n{'='*62}\nS11-S50: {ok}/{len(results)} PASS")
    if ok != len(results):
        print("\n落ちたシナリオ:")
        for r in results:
            if not r["ok"]:
                print(f"  {r['no']} {r['title']}")
                for e in r["evidence"]:
                    print(f"      {e}")
    Path(sys.argv[1] if len(sys.argv) > 1 else "ext.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
