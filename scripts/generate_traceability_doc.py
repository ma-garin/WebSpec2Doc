#!/usr/bin/env python3
"""要件⇔実装⇔テストのトレーサビリティマトリクスを機械生成する。

`quality/feature_contracts.yml`（要件 = feature_id、17 件）を単一の真実源とし、
UI / route / core 実装ファイル・シンボル・異常系・必須テスト種別と、テストの実在
状況（GAP）を Markdown 表に落とす。GAP は隠さず列に明示する。

使い方:
    python scripts/generate_traceability_doc.py            # 標準出力へ表を出力
    python scripts/generate_traceability_doc.py --write    # WS2D-TM-001 へ埋め込み

as-built 原則: 生成物は「現実のコード/テスト」を走査した結果であり、手書きしない。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

TM_DOC = Path("docs/sdlc/40_test/WS2D-TM-001_トレーサビリティマトリクス.md")
_MARK_BEGIN = "<!-- AUTO-GENERATED:BEGIN -->"
_MARK_END = "<!-- AUTO-GENERATED:END -->"


def load_contracts(path: Path) -> list[dict]:
    """feature_contracts.yml を読み、feature のリストを返す。"""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    features = data.get("features", []) if isinstance(data, dict) else []
    return [f for f in features if isinstance(f, dict) and f.get("feature_id")]


def _impl_files(feature: dict) -> list[str]:
    files: list[str] = []
    for key in ("ui_files", "route_files", "core_files"):
        files.extend(feature.get(key) or [])
    return files


def _iter_test_files(repo_root: Path) -> list[Path]:
    tests_dir = repo_root / "tests"
    if not tests_dir.exists():
        return []
    return sorted(tests_dir.rglob("test_*.py"))


def find_tests_for(feature: dict, repo_root: Path, _cache: dict[Path, str] | None = None) -> list[str]:
    """feature を参照するテストファイル（相対パス）を返す。

    判定は「feature_id か symbol か core/route ファイルの stem が
    テストソースに文字列出現するか」。素朴だが as-built の実在確認として十分。
    """
    needles: set[str] = {feature["feature_id"]}
    for sym in feature.get("symbols") or []:
        needles.add(sym)
    for f in (feature.get("route_files") or []) + (feature.get("core_files") or []):
        needles.add(Path(f).stem)
    hits: list[str] = []
    for path in _iter_test_files(repo_root):
        text = _cache.get(path) if _cache is not None else None
        if text is None:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if _cache is not None:
                _cache[path] = text
        if any(n and n in text for n in needles):
            hits.append(str(path.relative_to(repo_root)))
    return hits


def build_rows(contracts: list[dict], repo_root: Path) -> list[dict]:
    """各機能を要件行に変換する（テスト実在・欠落ファイルの判定込み）。"""
    cache: dict[Path, str] = {}
    rows: list[dict] = []
    for f in contracts:
        impl = _impl_files(f)
        missing = [rel for rel in impl if not (repo_root / rel).exists()]
        tests = find_tests_for(f, repo_root, cache)
        rows.append(
            {
                "feature_id": f["feature_id"],
                "name": f.get("name", ""),
                "risk_level": f.get("risk_level", ""),
                "impl_files": impl,
                "missing_files": missing,
                "required_tests": f.get("required_tests") or [],
                "failure_modes": f.get("failure_modes") or [],
                "tests": tests,
                "gap": not tests,
            }
        )
    return rows


def to_markdown(rows: list[dict]) -> str:
    """要件行を Markdown 表にする。GAP は列で明示する。"""
    covered = sum(1 for r in rows if not r["gap"])
    lines: list[str] = []
    lines.append(f"要件総数: **{len(rows)}** / テスト紐付けあり: **{covered}** / GAP: **{len(rows) - covered}**")
    lines.append("")
    lines.append("| 要件ID | 名称 | リスク | 実装ファイル | 必須テスト | 異常系 | 紐付くテスト | GAP |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        impl = "<br>".join(f"`{p}`" for p in r["impl_files"]) or "—"
        if r["missing_files"]:
            impl += "<br>⚠️欠落: " + ", ".join(r["missing_files"])
        req = ", ".join(r["required_tests"]) or "—"
        fm = ", ".join(r["failure_modes"]) or "—"
        tests = "<br>".join(f"`{p}`" for p in r["tests"][:6]) or "—"
        if len(r["tests"]) > 6:
            tests += f"<br>… 他 {len(r['tests']) - 6} 件"
        gap = "❌ **GAP**" if r["gap"] else "✅"
        lines.append(
            f"| `{r['feature_id']}` | {r['name']} | {r['risk_level']} | {impl} | {req} | {fm} | {tests} | {gap} |"
        )
    return "\n".join(lines)


def _write_into_doc(repo_root: Path, table_md: str) -> bool:
    doc = repo_root / TM_DOC
    if not doc.exists():
        return False
    text = doc.read_text(encoding="utf-8")
    if _MARK_BEGIN not in text or _MARK_END not in text:
        return False
    head, _, rest = text.partition(_MARK_BEGIN)
    _, _, tail = rest.partition(_MARK_END)
    new = f"{head}{_MARK_BEGIN}\n{table_md}\n{_MARK_END}{tail}"
    doc.write_text(new, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="トレーサビリティマトリクスを生成する")
    parser.add_argument("--write", action="store_true", help=f"{TM_DOC} へ埋め込む")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    contracts = load_contracts(repo_root / "quality" / "feature_contracts.yml")
    rows = build_rows(contracts, repo_root)
    table = to_markdown(rows)

    if args.write:
        ok = _write_into_doc(repo_root, table)
        if not ok:
            print(f"[WARN] {TM_DOC} に AUTO-GENERATED マーカーが見つからず未書込み", file=sys.stderr)
            print(table)
            return 1
        print(f"[OK] {TM_DOC} を更新しました（要件 {len(rows)} 件）")
    else:
        print(table)
    gaps = [r["feature_id"] for r in rows if r["gap"]]
    if gaps:
        print(f"[GAP] テスト未紐付け: {', '.join(gaps)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
