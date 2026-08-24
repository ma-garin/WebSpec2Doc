from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_FILE = ROOT / "quality" / "feature_contracts.yml"


def _contracts() -> dict:
    return json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))


def test_quality_harness_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/quality_harness.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Functional Integrity Harness: PASS" in result.stdout


def test_feature_contracts_are_readable() -> None:
    contracts = _contracts()

    assert contracts["version"] == 1
    assert isinstance(contracts["features"], list)
    assert contracts["features"]


def test_critical_features_have_failure_modes_and_required_tests() -> None:
    critical_features = [
        feature for feature in _contracts()["features"] if feature["risk_level"] == "critical"
    ]

    assert critical_features
    for feature in critical_features:
        assert feature["failure_modes"], feature["feature_id"]
        assert feature["required_tests"], feature["feature_id"]


def test_no_ui_only_features_are_registered() -> None:
    statuses = {feature["status"] for feature in _contracts()["features"]}

    assert "ui-only" not in statuses


def test_governance_documents_exist() -> None:
    assert (ROOT / ".claude" / "rules" / "functional-integrity.md").exists()
    assert (ROOT / "docs" / "process" / "functional-integrity-gate.md").exists()
    assert CONTRACT_FILE.exists()


# ── 未実装 UI（data-wip）の検出ゲート ────────────────────────────────────
#
# 2026-08-24 の欠陥: ハーネスの探索語が英語（"UI only" 等）のみで、このリポジトリが
# 実際に使う data-wip / 準備中 を 1 件も検出できず、未実装 UI を 22 箇所抱えた機能が
# status="implemented" のまま PASS していた。以下は検出器そのものの回帰テスト。


def _harness():
    sys.path.insert(0, str(ROOT / "scripts"))
    import quality_harness

    return quality_harness


def _feature(**overrides) -> dict:
    base = {
        "feature_id": "demo",
        "ui_files": ["templates/partials/view-demo.html"],
        "status": "partial",
        "wip_ui": [{"control": "demo-btn", "reason": "API 未実装"}],
    }
    base.update(overrides)
    return base


def _run_wip_ui(monkeypatch, feature: dict, detected: dict[str, list[str]]) -> list[str]:
    harness = _harness()
    monkeypatch.setattr(harness, "_scan_wip_controls", lambda errors: detected)
    errors: list[str] = []
    harness._validate_wip_ui([feature], errors)
    return errors


def test_wip_control_forbids_implemented_status(monkeypatch) -> None:
    errors = _run_wip_ui(
        monkeypatch,
        _feature(status="implemented"),
        {"templates/partials/view-demo.html": ["demo-btn"]},
    )

    assert any("status='implemented'" in e for e in errors), errors


def test_undeclared_wip_control_is_rejected(monkeypatch) -> None:
    errors = _run_wip_ui(
        monkeypatch,
        _feature(wip_ui=[]),
        {"templates/partials/view-demo.html": ["demo-btn"]},
    )

    assert any("未宣言の未実装 UI 'demo-btn'" in e for e in errors), errors


def test_stale_wip_declaration_is_rejected(monkeypatch) -> None:
    """実装したのに wip_ui の宣言を消し忘れた場合を検出する（残骸を許さない）。"""
    errors = _run_wip_ui(monkeypatch, _feature(), {})

    assert any("'demo-btn' に対応する data-wip が画面に無い" in e for e in errors), errors


def test_wip_declaration_requires_reason(monkeypatch) -> None:
    errors = _run_wip_ui(
        monkeypatch,
        _feature(wip_ui=[{"control": "demo-btn"}]),
        {"templates/partials/view-demo.html": ["demo-btn"]},
    )

    assert any("reason" in e for e in errors), errors


def test_wip_control_outside_any_feature_is_rejected(monkeypatch) -> None:
    errors = _run_wip_ui(
        monkeypatch,
        _feature(ui_files=[]),
        {"templates/partials/view-orphan.html": ["orphan-btn"]},
    )

    assert any("unowned WIP control" in e for e in errors), errors


def test_partial_status_must_declare_what_is_unfinished(monkeypatch) -> None:
    errors = _run_wip_ui(monkeypatch, _feature(wip_ui=[]), {})

    assert any("partial_reason" in e for e in errors), errors


def test_scanner_finds_real_wip_controls() -> None:
    """正規表現が実テンプレートに当たり続けることを保証する（検出器の腐り防止）。"""
    harness = _harness()
    errors: list[str] = []

    detected = harness._scan_wip_controls(errors)

    assert not errors, errors
    assert detected, "data-wip を 1 件も検出できていない。検出器が壊れている可能性がある"
    assert all(keys for keys in detected.values())


def test_every_real_wip_control_is_declared_in_contracts() -> None:
    harness = _harness()
    errors: list[str] = []
    detected = harness._scan_wip_controls(errors)
    declared = {
        entry["control"]
        for feature in _contracts()["features"]
        for entry in feature.get("wip_ui", [])
    }

    found = {key for keys in detected.values() for key in keys}

    assert found <= declared, f"未宣言の未実装 UI: {sorted(found - declared)}"
    assert declared <= found, f"実装済みなのに残った宣言: {sorted(declared - found)}"
