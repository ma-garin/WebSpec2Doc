"""環境ドクター — ローカル実行環境の不一致を一発診断する。

「リモートや CI では動くのにローカルで取得に失敗する」場合の原因は
ほぼ次のどれかに集約されるため、まとめて検査して修正コマンドを提示する:

1. Python バージョン不一致（playwright 1.44 は 3.11〜3.12 のみ対応）
2. 依存パッケージのバージョン不一致（requirements.txt のピンとずれ）
3. Chromium ランタイム不一致（playwright の要求バージョンと違う実体）
4. ローカル URL ガード（WEBSPEC2DOC_ALLOW_LOCAL 未設定で 127.0.0.1 拒否）

使い方: `make doctor` または `venv/bin/python src/doctor.py`
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

# playwright 1.44.0 の wheel が提供される範囲（3.13 以降は wheel なし）
SUPPORTED_PYTHON_MIN = (3, 11)
SUPPORTED_PYTHON_MAX_EXCLUSIVE = (3, 13)

# ディストリビューション名 → import 名（検査対象は取得系の中核依存のみ）
_DIST_TO_IMPORT = {
    "playwright": "playwright",
    "networkx": "networkx",
    "jinja2": "jinja2",
    "openpyxl": "openpyxl",
    "flask": "flask",
    "python-dotenv": "dotenv",
    "pypdf": "pypdf",
    "PyYAML": "yaml",
    "defusedxml": "defusedxml",
}


@dataclass(frozen=True)
class CheckResult:
    """1 検査項目の結果。fix は失敗時にユーザーが打つべきコマンド・対処。"""

    name: str
    ok: bool
    detail: str
    fix: str = ""


def check_python_version(version: tuple[int, int, int] | None = None) -> CheckResult:
    """Python バージョンが対応範囲（3.11〜3.12）か検査する。"""
    current = version or sys.version_info[:3]
    label = ".".join(str(part) for part in current)
    if SUPPORTED_PYTHON_MIN <= current[:2] < SUPPORTED_PYTHON_MAX_EXCLUSIVE:
        return CheckResult(name="Python バージョン", ok=True, detail=f"{label}（対応範囲内）")
    low = ".".join(str(p) for p in SUPPORTED_PYTHON_MIN)
    return CheckResult(
        name="Python バージョン",
        ok=False,
        detail=f"{label} は未対応（playwright 1.44 の対応範囲は {low}〜3.12）",
        fix=(
            "Python 3.12 で venv を作り直してください: "
            "`python3.12 -m venv venv && venv/bin/pip install -r requirements-dev.txt`"
            "（macOS: `brew install python@3.12`）"
        ),
    )


def parse_requirement_pins(requirements_text: str) -> dict[str, str]:
    """requirements.txt から `name==version` のピンを抽出する。"""
    pins: dict[str, str] = {}
    for line in requirements_text.splitlines():
        line = line.split("#", 1)[0].strip()
        match = re.match(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.]+)$", line)
        if match:
            pins[match.group(1)] = match.group(2)
    return pins


def check_dependency_pins(pins: dict[str, str]) -> list[CheckResult]:
    """導入済みパッケージのバージョンがピンと一致するか検査する。"""
    results: list[CheckResult] = []
    for dist_name, pinned in pins.items():
        if dist_name not in _DIST_TO_IMPORT:
            continue
        try:
            installed = metadata.version(dist_name)
        except metadata.PackageNotFoundError:
            results.append(
                CheckResult(
                    name=f"依存: {dist_name}",
                    ok=False,
                    detail="未インストール",
                    fix="`venv/bin/pip install -r requirements-dev.txt` を実行してください",
                )
            )
            continue
        if installed == pinned:
            results.append(CheckResult(name=f"依存: {dist_name}", ok=True, detail=f"{installed}"))
        else:
            results.append(
                CheckResult(
                    name=f"依存: {dist_name}",
                    ok=False,
                    detail=f"導入 {installed} ≠ ピン {pinned}",
                    fix=(
                        f"`venv/bin/pip install {dist_name}=={pinned}` "
                        "（まとめて直すなら `venv/bin/pip install -r requirements-dev.txt`）"
                    ),
                )
            )
    return results


def check_virtualenv() -> CheckResult:
    """リポジトリ配下の venv を使っているか検査する（グローバル実行は事故のもと）。"""
    prefix = Path(sys.prefix).resolve()
    if (ROOT / "venv").resolve() == prefix or prefix.is_relative_to(ROOT):
        return CheckResult(name="仮想環境", ok=True, detail=str(prefix))
    return CheckResult(
        name="仮想環境",
        ok=False,
        detail=f"リポジトリ外の Python を使用中: {prefix}",
        fix="`venv/bin/python src/doctor.py` のように venv の Python で実行してください",
    )


def check_chromium_runtime() -> CheckResult:
    """playwright が要求する Chromium が実起動できるか検査する。"""
    try:
        from crawler.playwright_runtime import (
            PlaywrightRuntimeError,
            verify_playwright_runtime,
        )
    except Exception as exc:  # noqa: BLE001  # playwright 未導入等もここで表面化する
        return CheckResult(
            name="Chromium ランタイム",
            ok=False,
            detail=f"検査モジュールを読み込めません: {exc}",
            fix="`venv/bin/pip install -r requirements-dev.txt` を実行してください",
        )
    try:
        info = verify_playwright_runtime()
    except PlaywrightRuntimeError as exc:
        return CheckResult(
            name="Chromium ランタイム",
            ok=False,
            detail=str(exc),
            fix="`make setup-runtime`（対応 Chromium をリポジトリ配下へ導入）",
        )
    return CheckResult(
        name="Chromium ランタイム",
        ok=True,
        detail=f"Chromium {info.chromium_version}（{info.browsers_path}）",
    )


def check_local_target_guard() -> CheckResult:
    """ローカル URL を対象にする場合のガード設定を通知する（常に情報表示）。"""
    enabled = os.environ.get("WEBSPEC2DOC_ALLOW_LOCAL", "") == "1"
    if enabled:
        return CheckResult(
            name="ローカルURLガード",
            ok=True,
            detail="WEBSPEC2DOC_ALLOW_LOCAL=1（ローカル対象を許可）",
        )
    return CheckResult(
        name="ローカルURLガード",
        ok=True,
        detail=(
            "未設定（既定）。127.0.0.1 や社内プライベート IP を対象にすると"
            "SSRF 保護で取得が拒否されます"
        ),
        fix="ローカル/社内サイトを対象にする場合のみ `WEBSPEC2DOC_ALLOW_LOCAL=1` を設定",
    )


def run_all_checks() -> list[CheckResult]:
    """全検査を実行する。"""
    results = [check_python_version(), check_virtualenv()]
    requirements = ROOT / "requirements.txt"
    if requirements.exists():
        results.extend(
            check_dependency_pins(parse_requirement_pins(requirements.read_text(encoding="utf-8")))
        )
    results.append(check_chromium_runtime())
    results.append(check_local_target_guard())
    return results


def main() -> int:
    results = run_all_checks()
    failed = [r for r in results if not r.ok]
    width = max(len(r.name) for r in results)
    for result in results:
        mark = "PASS" if result.ok else "FAIL"
        print(f"[{mark}] {result.name.ljust(width)}  {result.detail}")
        if result.fix and not result.ok:
            print(f"       └ 対処: {result.fix}")
    # 情報系の fix（ローカルガード）は PASS でも表示する
    for result in results:
        if result.ok and result.fix:
            print(f"[NOTE] {result.name}: {result.fix}")
    if failed:
        print(
            f"\n{len(failed)} 件の問題があります。上記の対処を実行後、再度 `make doctor` を実行してください。"
        )
        return 1
    print(
        "\n環境は正常です。取得に失敗する場合は対象サイト側の要因"
        "（ログインウォール・robots・レート制限）を audit.jsonl とログで確認してください。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
