"""System05: 不具合なし（直す対象が無い）の実行から PR を作らない。空のブランチを外部へ push させない。"""
from __future__ import annotations

from pathlib import Path

import pytest
from web.services.healing import orchestrator
from web.services.healing.types import HealingError, HealingRun


def test_no_defects_run_refuses_pull_request(monkeypatch, tmp_path: Path):
    run = HealingRun(run_id="heal-x", project_id="p1", status="no_defects", branch="healing/heal-x")
    monkeypatch.setattr(orchestrator, "get_run", lambda out_dir, run_id: run)

    def must_not_reach(*args, **kwargs):  # 接続先の解決（＝push の準備）まで進んではいけない
        raise AssertionError("no_defects の実行で PR 作成の処理に進んだ")

    monkeypatch.setattr(orchestrator.project_store, "get_project", must_not_reach)
    with pytest.raises(HealingError, match="不具合なし"):
        orchestrator.create_pull_request_for_run(tmp_path, "heal-x")


def test_settings_ui_does_not_offer_pr_for_no_defects():
    js = (Path(__file__).resolve().parent.parent / "static/js/healing-run.js").read_text(encoding="utf-8")
    # 不具合なし、および修正が 1 件も無い失敗の実行には PR を出さない
    assert "map['hl-create-pr'] = !hasPr && run.status !== 'no_defects' && !(run.status === 'failed' && !(run.fixed_count > 0));" in js
