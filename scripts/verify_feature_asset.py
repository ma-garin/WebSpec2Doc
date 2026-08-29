#!/usr/bin/env python3
"""機能単位アセットのバンドルを検証する（送り側の出荷前 / 受け側の受け入れ時）。

`scripts/export_feature_asset.py` が出したバンドルに対して、次を機械的に確かめる。

    1. manifest の形式が読めるか
    2. 同梱ファイルが全部あるか（欠落・余剰）
    3. SHA-256 が manifest と一致するか（転送・展開の破損検出）
    4. 生成時の警告が残っていないか
    5. （--against 指定時）受け側リポジトリで同梱外依存が満たされているか

使い方:
    python3 scripts/verify_feature_asset.py dist/assets/diff_history/20260829-abc1234
    python3 scripts/verify_feature_asset.py <bundle.tar.gz>
    python3 scripts/verify_feature_asset.py <bundle> --against /path/to/other-repo

終了コード: 0=合格 / 1=不合格。警告のみの場合は --strict を付けたときだけ 1 になる。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = "webspec2doc/feature-asset@1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_bundle(target: Path, stack: list[Any]) -> Path:
    """ディレクトリならそのまま、tar.gz なら一時展開して中のバンドル直下を返す。"""
    if target.is_dir():
        return target
    if not target.is_file():
        raise SystemExit(f"対象が見つからない: {target}")
    if not tarfile.is_tarfile(target):
        raise SystemExit(f"ディレクトリでも tar でもない: {target}")
    tmp = tempfile.TemporaryDirectory()
    stack.append(tmp)
    with tarfile.open(target) as tar:
        tar.extractall(tmp.name)
    roots = [p for p in Path(tmp.name).iterdir() if p.is_dir()]
    for root in roots:
        if (root / "manifest.json").is_file():
            return root
    if (Path(tmp.name) / "manifest.json").is_file():
        return Path(tmp.name)
    raise SystemExit("tar の中に manifest.json が見つからない")


def verify_bundle(bundle: Path) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []

    manifest_path = bundle / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"manifest.json がない: {bundle}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"manifest.json が壊れている: {exc}") from exc

    if manifest.get("schema") != SCHEMA:
        errors.append(f"未知のスキーマ: {manifest.get('schema')!r}（期待: {SCHEMA!r}）")

    for name in ("INTEGRATION.md", "contract.json"):
        if not (bundle / name).is_file():
            errors.append(f"必須ファイルがない: {name}")

    files_dir = bundle / "files"
    if not files_dir.is_dir():
        raise SystemExit("files/ がない。バンドルとして成立していない")

    declared: set[str] = set()
    for entry in manifest.get("files", []):
        rel = entry["path"]
        declared.add(rel)
        path = files_dir / rel
        if not path.is_file():
            errors.append(f"同梱漏れ: {rel}")
            continue
        actual = _sha256(path)
        if actual != entry["sha256"]:
            errors.append(
                f"SHA-256 不一致: {rel}\n"
                f"      manifest={entry['sha256']}\n      実ファイル={actual}"
            )
        elif path.stat().st_size != entry["bytes"]:
            errors.append(f"サイズ不一致: {rel}")

    for path in files_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(files_dir))
        if rel not in declared:
            warnings.append(f"manifest に載っていない余剰ファイル: {rel}")

    for warning in manifest.get("warnings", []):
        warnings.append(f"生成時の警告: {warning}")

    verification = manifest.get("verification", {})
    not_run = [k for k, v in verification.items() if v == "not_run"]
    if not_run:
        warnings.append("送り側で未実行の検証: " + ", ".join(sorted(not_run)))

    return errors, warnings, manifest


def verify_against(manifest: dict[str, Any], target_root: Path) -> tuple[list[str], list[str]]:
    """受け側リポジトリで同梱外依存が満たされているかを見る。"""
    errors: list[str] = []
    warnings: list[str] = []
    deps = manifest.get("dependencies", {})

    if not target_root.is_dir():
        raise SystemExit(f"--against のパスがディレクトリでない: {target_root}")

    for rel in deps.get("internal_modules_not_bundled", []):
        if not (target_root / rel).exists():
            errors.append(f"受け側に内部モジュールがない: {rel}")

    for rel in deps.get("data_files", []):
        if not (target_root / rel).exists():
            warnings.append(f"受け側にデータファイルがない: {rel}")

    for rel in deps.get("template_includes_not_bundled", []):
        if not (target_root / "templates" / rel).exists():
            errors.append(f"受け側にテンプレートがない: templates/{rel}")

    for rel in deps.get("static_refs_not_bundled", []):
        if not (target_root / rel).exists():
            errors.append(f"受け側に静的ファイルがない: {rel}")

    # 既存ファイルの上書きになるものを事前に知らせる（黙って潰さない）
    for entry in manifest.get("files", []):
        rel = entry["path"]
        existing = target_root / rel
        if existing.is_file() and _sha256(existing) != entry["sha256"]:
            warnings.append(f"受け側の既存ファイルを上書きする（内容が異なる）: {rel}")

    consumed = deps.get("consumes_endpoints", [])
    if consumed:
        warnings.append(
            "呼び出す API の実在は静的には確認できない。受け側で疎通を確認すること: "
            + ", ".join(consumed)
        )
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="機能単位アセットのバンドルを検証する。")
    parser.add_argument("bundle", help="バンドルのディレクトリ、または tar.gz")
    parser.add_argument("--against", default=None, help="受け側リポジトリのルート（依存充足を確認）")
    parser.add_argument("--strict", action="store_true", help="警告も不合格として扱う")
    args = parser.parse_args(argv)

    stack: list[Any] = []
    bundle = _resolve_bundle(Path(args.bundle), stack)
    errors, warnings, manifest = verify_bundle(bundle)

    if args.against:
        extra_errors, extra_warnings = verify_against(manifest, Path(args.against))
        errors += extra_errors
        warnings += extra_warnings

    feature = manifest.get("feature", {})
    print(f"対象: {feature.get('feature_id', '?')} — {feature.get('name', '?')}")
    print(f"版  : {manifest.get('version', '?')} (生成元 {manifest.get('source', {}).get('revision', '?')})")
    print(f"件数: {len(manifest.get('files', []))} ファイル")
    print()

    for warning in warnings:
        print(f"[警告] {warning}")
    for error in errors:
        print(f"[NG]   {error}")

    print()
    if errors:
        print(f"結果: 不合格（NG {len(errors)} / 警告 {len(warnings)}）")
        return 1
    if warnings and args.strict:
        print(f"結果: 不合格（--strict・警告 {len(warnings)}）")
        return 1
    print(f"結果: 合格（警告 {len(warnings)}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
