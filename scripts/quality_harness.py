from __future__ import annotations

import json
import re
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
    "src/cli_args.py",  # CLI 引数の宣言のみ（分岐・処理を持たない）
    # LLM 補完は任意経路。未設定時はルールベースで全機能が成立するため、
    # 単独の機能ではなく差し替え可能なアダプタとして扱う。
    "src/llm/openai_client.py",
    "src/llm/activity_log.py",  # LLM 呼び出しの横断アクティビティログ（best-effort）
    "src/llm/prompt_guard.py",  # 全LLM経路共有の原則＋injection対策（横断部品）
    "src/llm/screen_classifier.py",
    "src/llm/industry_template.py",
    "web/services/openai_qa.py",
    "src/doctor.py",  # 環境診断CLI（製品機能ではない）
    "src/crawler/playwright_runtime.py",  # ブラウザ実行環境の解決（全機能の土台）
}
# ── 未実装 UI（WIP）の検出 ────────────────────────────────────────────────
# 「画面にボタンはあるが中身は無い」を機械検出するための唯一の正規マーカー。
# 日本語の「準備中」「未実装」は製品ドメインの語彙でもあり（例: レポートの
# 「未実装疑い」分類、実行状態ラベルの「準備中」）、文字列検索では区別できない。
# そのため *属性* を正規マーカーとし、契約側の wip_ui 宣言と 1:1 で突き合わせる。
#
# 経緯: 2026-08-24。_validate_no_unimplemented_user_paths の探索語が英語のみで、
# このリポジトリが実際に使っている data-wip / 準備中 を 1 件も検出できず、
# 未実装 UI を 22 箇所抱えた機能が status="implemented" のまま PASS していた。
WIP_TAG_RE = re.compile(r'<[^>]*\bdata-wip\s*=\s*"[^"]*"[^>]*>', re.S)
WIP_ID_RE = re.compile(r'\bid\s*=\s*"([^"]+)"')
WIP_ACTION_RE = re.compile(r'\bdata-ta-action\s*=\s*"([^"]+)"')

# JS 側の「未実装」ユーザー可視メッセージ。HTML の data-wip と違い宣言と
# 突き合わせられないため、既存分を凍結して**増加のみ**を失敗させる（ラチェット）。
# scripts/check_e2e_conventions.py と同じ方式。減らしたらこの値も下げること。
#
# 現在の 3 件:
#   static/js/ta-codefix.js      対象ファイル特定（コード連携が未接続）
#   static/js/ta-completion.js   承認の記録（バックエンド未実装）
#   static/js/ta-implementation.js  ケース一覧の取り込み（対応API無し）
WIP_MESSAGE_RE = re.compile(r"ta-wip-note|準備中です|未実装です|準備中（")
WIP_MESSAGE_BASELINE = 3

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

    if status in {"implemented", "partial"}:
        has_execution_path = bool(feature.get("route_files")) or bool(feature.get("core_files"))
        if not has_execution_path:
            errors.append(f"{feature_id}: {status} feature lacks route_files/core_files")

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


def _wip_control_key(tag: str) -> str | None:
    """data-wip が付いた要素の識別子を返す。id を優先し、無ければ data-ta-action。

    どちらも無い要素は契約と突き合わせられないため、呼び出し側でエラーにする。
    """
    match = WIP_ID_RE.search(tag)
    if match:
        return match.group(1)
    match = WIP_ACTION_RE.search(tag)
    if match:
        return f"action:{match.group(1)}"
    return None


def _scan_wip_controls(errors: list[str]) -> dict[str, list[str]]:
    """templates 配下の data-wip 要素を {テンプレート相対パス: [識別子...]} で返す。"""
    found: dict[str, list[str]] = {}
    templates_root = ROOT / "templates"
    if not templates_root.is_dir():
        return found
    for path in sorted(templates_root.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = _rel(path)
        for match in WIP_TAG_RE.finditer(text):
            key = _wip_control_key(match.group(0))
            if key is None:
                errors.append(
                    f"unidentifiable WIP control: {rel} の data-wip 要素に id / data-ta-action が無い"
                    "（契約の wip_ui と突き合わせられないため、識別子を付けること）"
                )
                continue
            found.setdefault(rel, []).append(key)
    return found


def _validate_wip_ui(features: list[dict[str, Any]], errors: list[str]) -> None:
    """未実装 UI（data-wip）が契約で宣言され、status と整合することを確認する。

    これが無いと「UI だけ置いて中身は無い」機能を status="implemented" と
    宣言したままハーネスが PASS を返す（2026-08-24 に実際に発生していた。
    テスト活動支援が未実装 UI 22 箇所を抱えたまま実装済みと宣言されていた）。

    規則:
      1. data-wip を持つテンプレートは、いずれかの機能の ui_files に属すること
      2. 未実装 UI を持つ機能は status="partial"（"implemented" を名乗らせない）
      3. 検出した識別子はすべて wip_ui に理由付きで宣言すること
      4. wip_ui に宣言があるのに検出されない＝実装済みの残骸。宣言を消すこと
    """
    detected = _scan_wip_controls(errors)

    owner: dict[str, str] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for feature in features:
        if not isinstance(feature, dict):
            continue
        feature_id = str(feature.get("feature_id", "<missing>"))
        by_id[feature_id] = feature
        for path_text in feature.get("ui_files", []):
            owner[str(path_text)] = feature_id

    # 1. 所有者のいない未実装 UI
    detected_by_feature: dict[str, set[str]] = {}
    for rel, keys in detected.items():
        feature_id = owner.get(rel)
        if feature_id is None:
            errors.append(
                f"unowned WIP control: {rel} に data-wip があるが、どの機能の ui_files にも属していない"
                "（quality/feature_contracts.yml の ui_files へ登録すること）"
            )
            continue
        detected_by_feature.setdefault(feature_id, set()).update(keys)

    for feature_id, feature in by_id.items():
        status = feature.get("status")
        raw_entries = feature.get("wip_ui", [])
        if not isinstance(raw_entries, list):
            errors.append(f"{feature_id}: wip_ui はリストで宣言すること")
            raw_entries = []

        declared: set[str] = set()
        for entry in raw_entries:
            if not isinstance(entry, dict):
                errors.append(
                    f"{feature_id}: wip_ui の要素は control と reason を持つ object にすること"
                )
                continue
            control = entry.get("control")
            if not control:
                errors.append(f"{feature_id}: wip_ui の要素に control が無い")
                continue
            if not entry.get("reason"):
                errors.append(f"{feature_id}: wip_ui[{control}] に reason（未実装の理由）が無い")
            declared.add(str(control))

        found = detected_by_feature.get(feature_id, set())

        # 2. 未実装 UI を持つ機能は implemented を名乗れない
        if found and status == "implemented":
            errors.append(
                f"{feature_id}: 未実装 UI が {len(found)} 件あるのに status='implemented'"
                "（status を 'partial' にし、wip_ui へ理由付きで宣言すること）"
            )

        # 3. 未宣言の未実装 UI
        for control in sorted(found - declared):
            errors.append(
                f"{feature_id}: 未宣言の未実装 UI '{control}'"
                "（quality/feature_contracts.yml の wip_ui へ control と reason を追加すること）"
            )

        # 4. 実装済みなのに残った宣言
        for control in sorted(declared - found):
            errors.append(
                f"{feature_id}: wip_ui の '{control}' に対応する data-wip が画面に無い"
                "（実装済みなら宣言を削除すること。未実装 UI の宣言は残骸を許さない）"
            )

        # partial は「何が未完成か」を必ず示す
        if status == "partial" and not declared and not feature.get("partial_reason"):
            errors.append(
                f"{feature_id}: status='partial' には wip_ui か partial_reason が必要"
                "（どこが未完成かを宣言すること）"
            )


def _validate_wip_message_ratchet(errors: list[str]) -> None:
    """JS 側の「未実装」ユーザー可視メッセージを凍結し、増加のみ失敗させる。

    HTML の data-wip と違い宣言と 1:1 で突き合わせられないため、
    scripts/check_e2e_conventions.py と同じラチェット方式で増加だけを止める。
    """
    js_root = ROOT / "static" / "js"
    if not js_root.is_dir():
        return
    hits: list[str] = []
    for path in sorted(js_root.rglob("*.js")):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            if WIP_MESSAGE_RE.search(line):
                hits.append(f"{_rel(path)}:{lineno}")

    if len(hits) > WIP_MESSAGE_BASELINE:
        errors.append(
            f"未実装メッセージが JS に {len(hits)} 件（許容 {WIP_MESSAGE_BASELINE} 件）: "
            + ", ".join(hits)
            + "。新しい未実装経路を画面に足さないこと"
        )
    elif len(hits) < WIP_MESSAGE_BASELINE:
        errors.append(
            f"未実装メッセージが JS に {len(hits)} 件（許容 {WIP_MESSAGE_BASELINE} 件）。減っています。"
            f"scripts/quality_harness.py の WIP_MESSAGE_BASELINE を {len(hits)} に下げてください"
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
        _validate_wip_ui(features, errors)
    _validate_no_unimplemented_user_paths(errors)
    _validate_wip_message_ratchet(errors)

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
