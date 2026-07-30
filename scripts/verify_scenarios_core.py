#!/usr/bin/env python3
"""想定ユースケース 10 件を実機で検証する。

各シナリオは「QA エンジニアが実際にやること」を 1 つずつ通し、
受入条件を数字で判定する。判定できない場合は PASS にせず理由を残す。
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/home/user/WebSpec2Doc")
OUT = ROOT / "output"
DEMO = "http://127.0.0.1:8767/index.html"
DOMAIN = "127.0.0.1:8767"
APP = "http://127.0.0.1:8765"
PY = str(ROOT / "venv/bin/python")

results: list[dict] = []


def run(cmd: list[str], timeout: int = 900) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    # --json 指定時は stdout が JSON だけになる（ログは stderr）。混ぜて読むと壊れる。
    if "--json" in cmd:
        return p.returncode, p.stdout
    return p.returncode, (p.stdout + p.stderr)


def api(path: str) -> dict | list | None:
    import urllib.request

    req = urllib.request.Request(f"{APP}{path}", headers={"Host": "127.0.0.1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def record(no: str, title: str, who: str, ok: bool, evidence: list[str], note: str = "") -> None:
    results.append(
        {"no": no, "title": title, "who": who, "ok": ok, "evidence": evidence, "note": note}
    )
    mark = "PASS" if ok else "FAIL"
    print(f"\n[{no}] {mark}  {title}")
    for e in evidence:
        print(f"      {e}")
    if note:
        print(f"      注: {note}")


# ─────────────────────────────────────────────────────────────
def s01_new_site_spec() -> None:
    """S01 引き継ぎ資料の無いサイトを仕様化する。"""
    code, out = run(
        [
            PY,
            "src/cli.py",
            "doc",
            "--url",
            DEMO,
            "--format",
            "md,html,json,excel",
            "--depth",
            "2",
            "--max-pages",
            "10",
        ]
    )
    d = OUT / DOMAIN
    rep = d / "report.json"
    screens = 0
    if rep.is_file():
        screens = len(json.loads(rep.read_text(encoding="utf-8")).get("screens") or [])
    made = [
        n
        for n in (
            "report.html",
            "report.json",
            "spec.xlsx",
            "screens.md",
            "forms.md",
            "transition.mmd",
        )
        if (d / n).is_file()
    ]
    record(
        "S01",
        "引き継ぎ資料の無いサイトを仕様化する",
        "QA / 保守担当",
        code == 0 and screens > 0 and len(made) >= 5,
        [
            f"終了コード {code}",
            f"取得画面 {screens} 件",
            f"生成物 {len(made)}/6: {', '.join(made)}",
        ],
    )


def s02_login_wall() -> None:
    """S02 ログインが要る画面をどう扱うかが分かる。"""
    code, out = run(
        [
            PY,
            "src/cli.py",
            "autorun",
            "--url",
            DEMO,
            "--depth",
            "2",
            "--max-pages",
            "10",
            "--timeout",
            "900",
            "--json",
        ]
    )
    try:
        data = json.loads(out[out.index("{") : out.rindex("}") + 1])
    except ValueError:
        data = {}
    auto = data.get("auto_handled") or []
    unver = data.get("unverified") or []
    skipped = any("スキップ" in x for x in auto)
    stated = any("認証" in x or "ログイン" in x for x in unver)
    record(
        "S02",
        "ログインが要る画面の扱いが分かる",
        "QA / セキュリティ確認",
        skipped and stated,
        [
            f"スキップした旨を出力: {skipped}",
            f"未確認として記録: {stated}",
            *[f"  - {x[:76]}" for x in unver[:2]],
        ],
        "資格情報を渡さない場合。渡せば認証後も観測する（--login-user/--login-pass）",
    )


def s03_drift() -> None:
    """S03 再解析で仕様のズレを検知する。"""
    before = len(list((OUT / DOMAIN / "snapshots").glob("*.json")))
    run(
        [
            PY,
            "src/cli.py",
            "doc",
            "--url",
            DEMO,
            "--format",
            "json",
            "--compare",
            "--depth",
            "2",
            "--max-pages",
            "10",
        ]
    )
    snaps = sorted(p.stem for p in (OUT / DOMAIN / "snapshots").glob("*.json"))
    after = len(snaps)
    summary = (
        api(f"/api/snapshot-diff-summary?domain={DOMAIN}" f"&from={snaps[-2]}&to={snaps[-1]}")
        if after >= 2
        else None
    )
    has = summary.get("has_changes") if isinstance(summary, dict) else None
    record(
        "S03",
        "再解析で仕様のズレ（ドリフト）を検知する",
        "QA / リリース担当",
        after > before and has is not None,
        [
            f"スナップショット {before} → {after} 件",
            f"比較 {snaps[-2]} → {snaps[-1]}",
            f"変更あり: {has}（False なら『前回から変更はありません』と明示）",
            f"内訳: {summary.get('counts') if isinstance(summary, dict) else '—'}",
        ],
    )


def s04_doc_fusion() -> None:
    """S04 既存の仕様書と実装のギャップを洗い出す。"""
    code, out = run(
        [
            PY,
            "src/main.py",
            "--url",
            DEMO,
            "--format",
            "json",
            "--reference-doc",
            "demo/verify_docs/画面仕様書.md",
            "--depth",
            "2",
            "--max-pages",
            "10",
            "--output",
            "output",
        ]
    )
    f = OUT / DOMAIN / "doc_fusion.json"
    gaps = matched = 0
    if f.is_file():
        d = json.loads(f.read_text(encoding="utf-8"))
        gaps = len(d.get("field_gaps") or d.get("gaps") or [])
        matched = len(d.get("screen_matches") or d.get("matches") or [])
    record(
        "S04",
        "既存の仕様書と実装のギャップを洗い出す",
        "QA / 移行・リプレース担当",
        f.is_file() and (gaps > 0 or matched > 0),
        [
            f"終了コード {code}",
            f"doc_fusion.json 生成: {f.is_file()}",
            f"画面の対応づけ {matched} 件 / 項目ギャップ {gaps} 件",
        ],
    )


def s05_test_design() -> None:
    """S05 テスト条件を根拠つきで受け取る。"""
    d = api(f"/api/test-design/by-screen?domain={DOMAIN}&page_id=P003")
    conds = (d or {}).get("conditions") or []
    with_src = [c for c in conds if c.get("source_kind") or c.get("source_name")]
    with_tech = [c for c in conds if c.get("technique")]
    record(
        "S05",
        "テスト条件を「なぜ出たか」つきで受け取る",
        "テスト設計者",
        len(conds) > 0 and len(with_src) == len(conds) and len(with_tech) > 0,
        [
            f"P003 のテスト条件 {len(conds)} 件",
            f"由来が付いている条件 {len(with_src)} 件",
            f"導出技法が付いている条件 {len(with_tech)} 件",
            f"例: {conds[0].get('condition', '')[:52] if conds else '—'}",
        ],
    )


def s06_testcases() -> None:
    """S06 テストケースを生成し、その場で実行する。"""
    code, out = run([PY, "src/cli.py", "test", "--domain", DOMAIN, "--json"], timeout=1200)
    try:
        data = json.loads(out[out.index("{") : out.rindex("}") + 1])
    except ValueError:
        data = {}
    record(
        "S06",
        "テストケースを生成し、その場で実行する",
        "テスト実行担当",
        data.get("total", 0) > 0 and data.get("failed", 1) == 0 and code == 0,
        [
            f"終了コード {code}",
            f"実行 {data.get('total')} 件 / PASS {data.get('passed')} / FAIL {data.get('failed')}",
            f"所要 {round((data.get('duration_ms') or 0)/1000,1)} 秒",
        ],
    )


def s07_autorun() -> None:
    """S07 受領から実行完了まで自動で通す。"""
    code, out = run(
        [
            PY,
            "src/cli.py",
            "autorun",
            "--url",
            DEMO,
            "--depth",
            "2",
            "--max-pages",
            "10",
            "--timeout",
            "1200",
            "--json",
        ],
        timeout=1500,
    )
    try:
        data = json.loads(out[out.index("{") : out.rindex("}") + 1])
    except ValueError:
        data = {}
    record(
        "S07",
        "受領から実行完了まで自動で通す（AutoRun）",
        "QA リーダー",
        data.get("status") == "complete" and code == 0,
        [
            f"終了コード {code}",
            f"状態 {data.get('status')}",
            f"所要 {data.get('elapsed_sec')} 秒",
            f"自動で通した判断 {len(data.get('auto_handled') or [])} 件（全て出力される）",
        ],
    )


def s08_ci() -> None:
    """S08 CI に組み込んで成否で止める。"""
    c1, _ = run([PY, "src/cli.py", "show", "--domain", DOMAIN])
    c2, o2 = run([PY, "src/cli.py", "show", "--domain", "no-such-site.invalid"])
    c3, o3 = run([PY, "src/cli.py", "sites", "--json"])
    machine = False
    try:
        machine = json.loads(o3).get("command") == "sites"
    except Exception:
        pass
    record(
        "S08",
        "CI に組み込み、終了コードで成否を判定する",
        "CI / SRE 担当",
        c1 == 0 and c2 == 2 and c3 == 0 and machine,
        [
            f"正常時の終了コード {c1}（期待 0）",
            f"対象が無いときの終了コード {c2}（期待 2）",
            f"--json が機械可読: {machine}",
        ],
    )


def s09_zero_wait() -> None:
    """S09 導入検討者が待たずに成果物を見る。"""
    import urllib.request

    req = urllib.request.Request(
        f"{APP}/api/sample-report", method="POST", headers={"Host": "127.0.0.1"}
    )
    ok, dom = False, ""
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode("utf-8"))
            dom, ok = d.get("domain", ""), True
    except Exception:
        pass
    elapsed = time.monotonic() - t0
    res = api(f"/api/result?domain={dom}") if dom else None
    is_sample = (res or {}).get("is_sample")
    hist = api("/api/history") or {}
    leaked = any(dom == i.get("domain") for i in (hist.get("items") or []))
    record(
        "S09",
        "導入検討者が待たずに成果物を見る（ゼロ待ちサンプル）",
        "導入検討者 / 営業",
        ok and elapsed < 5 and is_sample is True and not leaked,
        [
            f"応答 {elapsed:.2f} 秒（実解析は約 21 秒）",
            f"サンプルとして識別: {is_sample}",
            f"解析履歴に混入しない: {not leaked}",
        ],
    )


def s10_export() -> None:
    """S10 成果物を配布形式で持ち出す。"""
    import urllib.request

    d = OUT / DOMAIN
    files = {
        n: (d / n).is_file()
        for n in (
            "report.html",
            "report.json",
            "spec.xlsx",
            "screens.md",
            "forms.md",
            "transition.mmd",
            "doc_fusion.md",
        )
    }
    size = 0
    try:
        req = urllib.request.Request(
            f"{APP}/download-zip?domain={DOMAIN}", headers={"Host": "127.0.0.1"}
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            size = len(r.read())
    except Exception:
        pass
    record(
        "S10",
        "成果物を配布形式で持ち出す",
        "QA / 顧客提出担当",
        sum(files.values()) >= 6 and size > 10_000,
        [
            f"個別ファイル {sum(files.values())}/{len(files)} 件: "
            + ", ".join(k for k, v in files.items() if v),
            f"ZIP 一括ダウンロード {size/1024:.0f} KB",
        ],
    )


def main() -> int:
    for fn in (
        s01_new_site_spec,
        s02_login_wall,
        s03_drift,
        s04_doc_fusion,
        s05_test_design,
        s06_testcases,
        s07_autorun,
        s08_ci,
        s09_zero_wait,
        s10_export,
    ):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            record(
                fn.__doc__.split("\n")[0][:60],
                "（検証中に例外）",
                "—",
                False,
                [f"{type(exc).__name__}: {exc}"],
            )
    ok = sum(1 for r in results if r["ok"])
    print(f"\n{'='*60}\n合計 {ok}/{len(results)} シナリオが PASS")
    Path(sys.argv[1] if len(sys.argv) > 1 else "scenarios.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
