#!/usr/bin/env python3
"""SDLC 文書の整合性を機械で点検する。

文書を人手で書き足していくと、必ず次の 3 つが壊れる。

1. **陳腐化した数値** — 「機能 19 件」「エンドポイント 121 本」のように、
   実装が変わったのに文書だけ古い値のまま残る。
2. **リンク切れ** — 参照先の文書名が変わった、まだ作っていない。
3. **相互参照の食い違い** — ある文書が「未作成」と書いている文書が実在する。

いずれも読めば分かるが、37 文書を毎回人が読み直すのは続かない。機械で回す。

使い方:
    venv/bin/python scripts/check_doc_consistency.py

終了コード 0 = 問題なし、1 = 要確認あり。CI やリリース前チェックに組み込める。
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SDLC_DIR = ROOT / "docs" / "sdlc"
ASBUILT_DIR = SDLC_DIR / "_asbuilt"

# 改訂履歴や「旧版は N だった」という記述では旧値が正しく登場する。
# 経緯を記録した行まで警告すると誤検知だらけになるので除外する。
_HISTORICAL_MARKERS = (
    "旧版",
    "旧文書",
    "参考値",
    "当時",
    "前版",
    "初版",
    "改訂",
    "から",
    "→",
    "時点",
    "未追随",
    "要再測定",
    "計測日",
    "まま",
    "前提とし",
    "止まって",
    "是正",
    "修正",
    "旧値",
    "比較できない",
    "構成とは異な",
    "母数",
)

# 「19 件」のような数字は、機能要件数以外の文脈でも普通に出る（未割当19件など）。
# 数字の近くに主語があるときだけ陳腐化とみなす。
_NUMBER_CONTEXT = {
    "機能要件数": ("機能要件", "機能契約", "feature_contract", "validated_features", "要件数"),
    "エンドポイント数": ("エンドポイント", "endpoint", "routes.json", "API"),
    "Blueprint 数": ("Blueprint", "blueprint"),
    "テスト関数総数": ("テスト関数", "def test_"),
    "非E2Eファイル数": ("非E2E", "tests/test_", "テストファイル"),
    "E2Eファイル数": ("E2E", "tests/e2e"),
}


def _iter_docs() -> list[Path]:
    return sorted(p for p in SDLC_DIR.rglob("*.md") if "_asbuilt" not in p.parts)


def _load_asbuilt() -> dict[str, int]:
    """機械抽出の実測値。文書に書かれるべき「正しい数」の基準になる。"""
    values: dict[str, int] = {}
    routes = ASBUILT_DIR / "routes.json"
    modules = ASBUILT_DIR / "modules.json"
    licenses = ASBUILT_DIR / "licenses.json"

    if routes.exists():
        data = json.loads(routes.read_text(encoding="utf-8"))
        values["endpoints"] = len(data)
        values["blueprints"] = len({r["blueprint"] for r in data if r["blueprint"]})
    if modules.exists():
        values["modules"] = len(json.loads(modules.read_text(encoding="utf-8")))
    if licenses.exists():
        values["licenses"] = len(json.loads(licenses.read_text(encoding="utf-8")))

    contracts = ROOT / "quality" / "feature_contracts.yml"
    if contracts.exists():
        values["features"] = contracts.read_text(encoding="utf-8").count("feature_id")

    return values


def check_stale_numbers(docs: list[Path], current: dict[str, int]) -> list[str]:
    """実測と食い違う数値が、経緯の記述以外の場所に残っていないか。"""
    findings: list[str] = []

    # (説明, 現在値のキー, 陳腐化した値の正規表現)
    patterns = [
        ("機能要件数", "features", r"(?<![\d,])19\s*件"),
        ("エンドポイント数", "endpoints", r"(?<![\d,])121\s*本"),
        ("エンドポイント数", "endpoints", r"(?<![\d,])196\s*本"),
        ("Blueprint 数", "blueprints", r"(?<![\d,])17\s*(?:個の\s*)?Blueprint"),
        ("テスト関数総数", None, r"1,?985"),
        ("非E2Eファイル数", None, r"108\s*(?:本|ファイル)"),
        ("E2Eファイル数", None, r"(?<![\d,])32\s*(?:本|ファイル)"),
    ]

    for path in docs:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(marker in line for marker in _HISTORICAL_MARKERS):
                continue  # 経緯・参考値としての言及は正当
            for label, key, pattern in patterns:
                if not re.search(pattern, line):
                    continue
                # 数字だけの一致は誤検知が多い。同じ行に主語があるときだけ拾う
                context = _NUMBER_CONTEXT.get(label, ())
                if context and not any(word in line for word in context):
                    continue
                now = f"（現在: {current[key]}）" if key and key in current else ""
                findings.append(
                    f"{path.relative_to(SDLC_DIR)}:{lineno} 陳腐化した{label}の可能性{now}\n"
                    f"    {line.strip()[:110]}"
                )
    return findings


def check_links(docs: list[Path]) -> list[str]:
    """文書間リンクの参照先が存在するか。"""
    findings: list[str] = []
    for path in docs:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", text):
            target = match.group(2).split("#")[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (path.parent / target).resolve().exists():
                findings.append(
                    f"{path.relative_to(SDLC_DIR)} リンク切れ: "
                    f"[{match.group(1)[:30]}]({target[:70]})"
                )
    return findings


def check_missing_claims(docs: list[Path]) -> list[str]:
    """「未作成」と書かれている文書が、実は存在していないか。

    並行して文書を書くと、A が「B は未作成」と書いた後に B ができる。
    この食い違いは読んでも気づきにくいので機械で拾う。
    """
    findings: list[str] = []
    existing_ids = {m.group(1) for p in docs if (m := re.match(r"(WS2D-[A-Z]{2}-\d+)", p.stem))}

    for path in docs:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not re.search(r"未作成|未整備|存在しない", line):
                continue
            # 改訂履歴（「誤って未作成と記載していたが修正」）は正当な記録
            if any(marker in line for marker in ("改訂", "修正", "是正", "誤って")):
                continue
            # 「構築未完了」のように、文書ではなく環境や状態を指す文
            if re.search(r"(構築|環境|セットアップ|インストール)(が)?未", line):
                continue
            for doc_id in re.findall(r"WS2D-[A-Z]{2}-\d+", line):
                if doc_id in existing_ids:
                    findings.append(
                        f"{path.relative_to(SDLC_DIR)}:{lineno} "
                        f"{doc_id} を未作成と書いているが実在する\n"
                        f"    {line.strip()[:110]}"
                    )
    return findings


def check_office_freshness(docs: list[Path]) -> list[str]:
    """Word が正本 Markdown より古くないか。古ければ再生成漏れ。"""
    findings: list[str] = []
    for path in docs:
        docx = path.with_suffix(".docx")
        if not docx.exists():
            findings.append(f"{path.relative_to(SDLC_DIR)} に対応する .docx がない")
        elif docx.stat().st_mtime < path.stat().st_mtime:
            findings.append(
                f"{docx.relative_to(SDLC_DIR)} が正本より古い"
                "（scripts/build_delivery_docs.py で再生成が必要）"
            )
    return findings


def check_cycles() -> list[str]:
    """循環依存が残っていないか。設計文書の主張と実装を突き合わせる。

    経路数だけ見ると、逆依存を 1 本残して 2 本消しても件数が変わらない。
    実際に直すべき import を名指しして、改善が数字に出るようにする。
    """
    path = ASBUILT_DIR / "dependency_cycles.json"
    if not path.exists():
        return ["dependency_cycles.json がない（extract_asbuilt.py を実行すること）"]

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):  # 旧形式（経路のリストのみ）
        return [f"循環依存の経路: {' -> '.join(c)}" for c in data]

    offenders = data.get("offending_modules", [])
    findings = [f"循環の原因 import: {o['module']} -> {o['imports']}" for o in offenders]
    if findings:
        findings.append(
            f"（経路数 {len(data.get('cycles', []))} は原因 import が 1 本でも残ると変わらない。"
            "上の import 本数で進捗を見ること）"
        )
    return findings


def check_uncommitted_docs() -> list[str]:
    """文書に未コミットの変更がないか。納品直前の取りこぼしを防ぐ。"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "docs/sdlc"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    changed = [line for line in result.stdout.splitlines() if line.strip()]
    if changed:
        return [f"未コミットの文書変更が {len(changed)} 件ある"]
    return []


def main() -> int:
    docs = _iter_docs()
    current = _load_asbuilt()

    sections = [
        ("陳腐化した数値", check_stale_numbers(docs, current)),
        ("リンク切れ", check_links(docs)),
        ("実在する文書を未作成と記載", check_missing_claims(docs)),
        ("Word の再生成漏れ", check_office_freshness(docs)),
        ("循環依存", check_cycles()),
        ("未コミットの変更", check_uncommitted_docs()),
    ]

    print(f"点検対象: {len(docs)} 文書")
    if current:
        print("実測値: " + " / ".join(f"{k}={v}" for k, v in sorted(current.items())))
    print()

    total = 0
    for label, findings in sections:
        mark = "OK" if not findings else f"{len(findings)} 件"
        print(f"[{mark:>7}] {label}")
        for finding in findings[:20]:
            print(f"          {finding}")
        if len(findings) > 20:
            print(f"          ... 他 {len(findings) - 20} 件")
        total += len(findings)

    print()
    if total:
        print(f"要確認: {total} 件")
        return 1
    print("すべて整合している")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
