from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FILE = ROOT / "quality" / "feature_contracts.yml"
REQUIRED_DOCS = [
    ROOT / ".claude" / "rules" / "functional-integrity.md",
    ROOT / "docs" / "process" / "functional-integrity-gate.md",
    CONTRACT_FILE,
]
RISK_LEVELS_REQUIRING_FAILURE_TESTS = {"critical", "high"}

# 機能実装が置かれるディレクトリ。ここに新設したモジュールは、いずれかの
# feature contract の core_files / route_files に現れなければならない。
FEATURE_SOURCE_ROOTS = ("src", "web/routes", "web/services")

# 機能ではなく基盤・共通部品のため、契約への登録を求めないもの。
# 追加する場合は「なぜ機能ではないか」を必ずコメントで残すこと。
UNREGISTERED_ALLOWLIST = {
    "web/config.py",  # 設定値の集約
    "web/auth.py",  # 認証基盤（各機能から利用される横断部品）
    "web/tenancy.py",  # テナント解決の横断部品
    "web/types.py",
    "web/security.py",
    "web/validation.py",
    "web/summary.py",
    "web/process.py",
    "web/env_store.py",
    "web/audit_context.py",
    "web/routes/pages.py",  # SPAシェルの配信のみ（機能ロジックを持たない）
    # LLM 補完は任意経路。未設定時はルールベースで全機能が成立するため、
    # 単独の機能ではなく差し替え可能なアダプタとして扱う。
    "src/llm/openai_client.py",
    "src/llm/screen_classifier.py",
    "src/llm/industry_template.py",
    "web/services/openai_qa.py",
    "src/doctor.py",  # 環境診断CLI（製品機能ではない）
    "src/crawler/playwright_runtime.py",  # ブラウザ実行環境の解決（全機能の土台）
}
ALLOWED_STATUS = {"implemented", "partial", "planned"}
FORBIDDEN_STATUS = {"ui-only"}


def _read_contracts() -> dict[str, Any]:
    if not CONTRACT_FILE.exists():
        raise AssertionError(f"missing contract file: {CONTRACT_FILE.relative_to(ROOT)}")
    try:
        return json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssertionError(f"feature contract must be JSON-compatible YAML: {exc}") from exc


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _require_path(path_text: str, errors: list[str]) -> None:
    path = ROOT / path_text
    if not path.exists():
        errors.append(f"missing referenced path: {path_text}")


def _file_text(path_text: str) -> str:
    path = ROOT / path_text
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _validate_feature(feature: dict[str, Any], errors: list[str]) -> None:
    feature_id = feature.get("feature_id", "<missing>")
    risk_level = feature.get("risk_level")
    status = feature.get("status")

    if not feature.get("feature_id"):
        errors.append("feature missing feature_id")
    if risk_level not in {"critical", "high", "medium", "low"}:
        errors.append(f"{feature_id}: invalid risk_level={risk_level!r}")
    if status in FORBIDDEN_STATUS:
        errors.append(f"{feature_id}: ui-only features are forbidden")
    if status not in ALLOWED_STATUS:
        errors.append(f"{feature_id}: invalid status={status!r}")

    for key in ("ui_files", "route_files", "core_files"):
        for path_text in feature.get(key, []):
            _require_path(path_text, errors)

    if status == "implemented":
        has_execution_path = bool(feature.get("route_files")) or bool(feature.get("core_files"))
        if not has_execution_path:
            errors.append(f"{feature_id}: implemented feature lacks route_files/core_files")

    if risk_level in RISK_LEVELS_REQUIRING_FAILURE_TESTS:
        if not feature.get("failure_modes"):
            errors.append(f"{feature_id}: {risk_level} feature lacks failure_modes")
        if not feature.get("required_tests"):
            errors.append(f"{feature_id}: {risk_level} feature lacks required_tests")

    for symbol in feature.get("symbols", []):
        if not any(symbol in _file_text(path_text) for path_text in feature.get("core_files", [])):
            errors.append(f"{feature_id}: symbol {symbol!r} not found in core_files")


def _validate_docs(errors: list[str]) -> None:
    for path in REQUIRED_DOCS:
        if not path.exists():
            errors.append(f"missing required governance file: {_rel(path)}")


def _validate_no_unimplemented_user_paths(errors: list[str]) -> None:
    scan_roots = [ROOT / "web" / "routes", ROOT / "static" / "js", ROOT / "templates" / "partials"]
    suspicious_terms = ["UI only", "ui-only", "not implemented", "dummy endpoint", "stub endpoint"]
    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".js", ".html"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for term in suspicious_terms:
                if term in text:
                    errors.append(
                        f"suspicious incomplete user path: {_rel(path)} contains {term!r}"
                    )


def _validate_all_modules_registered(features: list[dict[str, Any]], errors: list[str]) -> None:
    """機能ディレクトリの実装モジュールが、必ずどれかの契約に紐づくことを確認する。

    これが無いと「機能を足したが契約に登録し忘れる」を人の注意力に頼ることになり、
    ハーネスが素通しで PASS を返してしまう（2026-07-19 に実際に発生した）。
    """
    registered: set[str] = set()
    for feature in features:
        if not isinstance(feature, dict):
            continue
        for key in ("core_files", "route_files", "ui_files"):
            for path_text in feature.get(key, []):
                registered.add(str(path_text))

    for root_text in FEATURE_SOURCE_ROOTS:
        root = ROOT / root_text
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if path.name == "__init__.py" or "__pycache__" in path.parts:
                continue
            rel = _rel(path)
            if rel in registered or rel in UNREGISTERED_ALLOWLIST:
                continue
            errors.append(
                f"unregistered feature module: {rel} "
                "(quality/feature_contracts.yml のいずれかの機能へ登録するか、"
                "基盤部品なら UNREGISTERED_ALLOWLIST へ理由付きで追加すること)"
            )


def main() -> int:
    errors: list[str] = []
    _validate_docs(errors)
    contracts = _read_contracts()
    features = contracts.get("features", [])
    if not isinstance(features, list) or not features:
        errors.append("feature contracts must contain non-empty features list")
    else:
        for feature in features:
            if not isinstance(feature, dict):
                errors.append("feature entry must be an object")
                continue
            _validate_feature(feature, errors)

    if isinstance(features, list):
        _validate_all_modules_registered(features, errors)
    _validate_no_unimplemented_user_paths(errors)

    if errors:
        print("Functional Integrity Harness: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Functional Integrity Harness: PASS")
    print(f"validated_features={len(features)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
