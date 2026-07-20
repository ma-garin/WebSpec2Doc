"""仕様8: 同じURLの2回目以降はテスト計画をSKIPできることのテスト。

「同じURLでやる場合（初回以外）ではSKIP可能」（利用者仕様 8番）。
初回はSKIPできず、再実行時のみSKIPできる。SKIPした事実は監査に残る。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.autorun_stages as stages_mod
from autorun.stages import STAGE_TEST_PLAN, STATUS_SKIPPED, Pipeline

DOMAIN = "example.com"


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    (tmp_path / DOMAIN / "qa_process").mkdir(parents=True)
    monkeypatch.setattr(stages_mod, "scoped_output_dir", lambda _root: tmp_path)
    return tmp_path


@pytest.fixture()
def client(workspace):
    return appmod.app.test_client()


def _save(workspace: Path, pipeline: Pipeline) -> None:
    path = workspace / DOMAIN / "qa_process" / "stages.json"
    path.write_text(json.dumps(pipeline.to_dict(), ensure_ascii=False), encoding="utf-8")


class TestSkipOnRerun:
    def test_only_test_plan_is_skippable(self) -> None:
        """SKIPできるのはテスト計画のみ（他段階は必ず承認が要る）。"""
        pipeline = Pipeline.initial()
        skippable = [s.stage_id for s in pipeline.stages if s.definition.skippable_on_rerun]
        assert skippable == [STAGE_TEST_PLAN]

    def test_first_run_cannot_skip(self, client, workspace) -> None:
        """初回はSKIPできない（計画を立てずに進ませない）。"""
        _save(workspace, Pipeline.initial(is_rerun=False))
        res = client.post(
            "/api/autorun/stages/skip",
            json={"domain": DOMAIN, "stage_id": STAGE_TEST_PLAN},
        )
        assert res.status_code >= 400

    def test_rerun_can_skip_test_plan(self, client, workspace) -> None:
        """再実行ならテスト計画をSKIPできる。"""
        _save(workspace, Pipeline.initial(is_rerun=True))
        res = client.post(
            "/api/autorun/stages/skip",
            json={"domain": DOMAIN, "stage_id": STAGE_TEST_PLAN},
        )
        assert res.status_code == 200
        saved = Pipeline.from_dict(
            json.loads((workspace / DOMAIN / "qa_process" / "stages.json").read_text())
        )
        assert saved.get(STAGE_TEST_PLAN).status == STATUS_SKIPPED

    def test_non_skippable_stage_is_rejected_even_on_rerun(self, client, workspace) -> None:
        """再実行でも、計画以外の段階はSKIPできない。"""
        _save(workspace, Pipeline.initial(is_rerun=True))
        res = client.post(
            "/api/autorun/stages/skip",
            json={"domain": DOMAIN, "stage_id": "test_objective"},
        )
        assert res.status_code >= 400

    def test_skip_is_recorded_in_audit(self, client, workspace) -> None:
        """SKIPした事実を隠さない（未承認のまま進んだと分かるようにする）。"""
        _save(workspace, Pipeline.initial(is_rerun=True))
        client.post(
            "/api/autorun/stages/skip",
            json={"domain": DOMAIN, "stage_id": STAGE_TEST_PLAN},
        )
        saved = Pipeline.from_dict(
            json.loads((workspace / DOMAIN / "qa_process" / "stages.json").read_text())
        )
        assert any(entry.action == "skip" for entry in saved.audit)

    def test_is_rerun_flag_is_exposed_to_ui(self, client, workspace) -> None:
        """UIがSKIPボタンの出し分けに使うフラグが返ること。"""
        _save(workspace, Pipeline.initial(is_rerun=True))
        body = client.get(f"/api/autorun/stages?domain={DOMAIN}").get_json()
        assert body["is_rerun"] is True
