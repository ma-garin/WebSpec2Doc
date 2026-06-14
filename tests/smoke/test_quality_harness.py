from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_FILE = ROOT / "quality" / "feature_contracts.yml"


def _contracts() -> dict:
    return json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))


def test_quality_harness_passes() -> None:
    result = subprocess.run(
        ["python", "scripts/quality_harness.py"],
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
