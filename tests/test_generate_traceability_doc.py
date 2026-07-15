"""generate_traceability_doc.py（要件⇔実装⇔テストのトレーサビリティ生成）のテスト。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import generate_traceability_doc as gen

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_load_contracts_returns_all_features() -> None:
    contracts = gen.load_contracts(REPO_ROOT / "quality" / "feature_contracts.yml")
    # 件数はデータ駆動（feature_contracts.yml の実数）。ハードコードしない。
    assert len(contracts) >= 17
    assert all("feature_id" in c for c in contracts)


def test_build_rows_covers_all_features() -> None:
    contracts = gen.load_contracts(REPO_ROOT / "quality" / "feature_contracts.yml")
    rows = gen.build_rows(contracts, REPO_ROOT)
    # 全 feature が 1 行ずつ要件行になる（漏れなし）。
    assert len(rows) == len(contracts)
    ids = {r["feature_id"] for r in rows}
    assert "discover" in ids and "ux_review" in ids
    # 各行は実装ファイル・テスト・GAP 判定を持つ
    for r in rows:
        assert "impl_files" in r and "tests" in r and "gap" in r


def test_gap_true_when_no_test_references_feature() -> None:
    """テストがどこからも参照しない架空機能は GAP=True になる。"""
    # リテラル文字列がこのテストファイル自身に残ると自己参照で誤検出するため、
    # 連結して「ソースに完全一致するリテラルを残さない」IDを生成する。
    fake_id = "zzz" + "phantomfeature" + "zzz"
    fake_sym = "zzz" + "phantomsymbol" + "zzz"
    fake = [
        {
            "feature_id": fake_id,
            "name": "架空",
            "risk_level": "low",
            "status": "implemented",
            "ui_files": [],
            "route_files": [],
            "core_files": [],
            "symbols": [fake_sym],
            "failure_modes": [],
            "required_tests": [],
        }
    ]
    rows = gen.build_rows(fake, REPO_ROOT)
    assert rows[0]["gap"] is True


def test_real_features_have_tests_no_gap() -> None:
    """実在機能（discover 等）はテストが存在し GAP=False。"""
    contracts = gen.load_contracts(REPO_ROOT / "quality" / "feature_contracts.yml")
    rows = gen.build_rows(contracts, REPO_ROOT)
    by_id = {r["feature_id"]: r for r in rows}
    assert by_id["discover"]["gap"] is False
    assert by_id["discover"]["tests"], "discover にテストが紐づいていない"


def test_to_markdown_includes_all_ids_and_gap_marker() -> None:
    contracts = gen.load_contracts(REPO_ROOT / "quality" / "feature_contracts.yml")
    rows = gen.build_rows(contracts, REPO_ROOT)
    md = gen.to_markdown(rows)
    for c in contracts:
        assert c["feature_id"] in md
    # 表ヘッダとカバレッジ集計を含む
    assert "要件ID" in md
    assert "GAP" in md


def test_missing_impl_file_is_flagged() -> None:
    """宣言された実装ファイルが実在しない場合は missing に載る。"""
    fake = [
        {
            "feature_id": "x",
            "name": "x",
            "risk_level": "low",
            "status": "implemented",
            "ui_files": ["templates/partials/__does_not_exist__.html"],
            "route_files": [],
            "core_files": [],
            "symbols": [],
            "failure_modes": [],
            "required_tests": [],
        }
    ]
    rows = gen.build_rows(fake, REPO_ROOT)
    assert "templates/partials/__does_not_exist__.html" in rows[0]["missing_files"]
