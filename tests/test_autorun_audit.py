"""段階承認の記録（いつ・何を承認したか）のテスト。

承認フローを持つ以上、状態だけでなく**経緯**を残さないと後から検証できない。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.autorun_stages as stages_mod
from autorun.stages import Pipeline

DOMAIN = "example.com"

REPORT = {
    "screens": [
        {
            "page_id": "P001",
            "url": "https://example.com/",
            "title": "トップ",
            "forms": [{"fields": [{"name": "q", "required": True}]}],
            "transitions": {"to": [], "from": []},
        }
    ]
}


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    (tmp_path / DOMAIN / "qa_process").mkdir(parents=True)
    (tmp_path / DOMAIN / "report.json").write_text(
        json.dumps(REPORT, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(stages_mod, "scoped_output_dir", lambda _root: tmp_path)
    return tmp_path


@pytest.fixture()
def client(workspace):
    return appmod.app.test_client()


def _post(client, path, payload):
    return client.post(path, json=payload)


def _audit(client) -> list[dict]:
    return client.get(f"/api/autorun/stages?domain={DOMAIN}").get_json()["audit"]


class TestPipelineAudit:
    def test_starts_empty(self) -> None:
        assert Pipeline.initial().audit == ()

    def test_recorded_returns_new_pipeline(self) -> None:
        """不変。元のオブジェクトは変わらない。"""
        p = Pipeline.initial()
        q = p.recorded("approve", "test_objective", "4項目を承認")
        assert p.audit == ()
        assert len(q.audit) == 1

    def test_entry_has_timestamp_and_action(self) -> None:
        entry = Pipeline.initial().recorded("approve", "test_plan", "8項目").audit[0]
        assert entry.action == "approve"
        assert entry.stage_id == "test_plan"
        assert entry.at, "時刻が記録されること"

    def test_audit_survives_serialisation(self) -> None:
        p = Pipeline.initial().recorded("approve", "features", "3項目を承認")
        restored = Pipeline.from_dict(p.to_dict())
        assert len(restored.audit) == 1
        assert restored.audit[0].detail == "3項目を承認"


class TestApiRecordsHistory:
    def test_generate_is_recorded(self, client) -> None:
        _post(client, "/api/autorun/stages/generate",
              {"domain": DOMAIN, "stage_id": "test_objective"})
        entries = _audit(client)
        assert entries and entries[0]["action"] == "generate"
        assert "項目を生成" in entries[0]["detail"]

    def test_approval_is_recorded(self, client) -> None:
        _post(client, "/api/autorun/stages/generate",
              {"domain": DOMAIN, "stage_id": "test_objective"})
        _post(client, "/api/autorun/stages/approve",
              {"domain": DOMAIN, "stage_id": "test_objective"})
        actions = [e["action"] for e in _audit(client)]
        assert "approve" in actions

    def test_plan_approval_notes_assumptions(self, client) -> None:
        """前提を含む承認は、その件数を記録に残す。"""
        _post(client, "/api/autorun/stages/generate", {"domain": DOMAIN, "stage_id": "test_plan"})
        _post(client, "/api/autorun/stages/approve", {"domain": DOMAIN, "stage_id": "test_plan"})
        approve = [e for e in _audit(client) if e["action"] == "approve"][-1]
        assert "前提" in approve["detail"]

    def test_item_approval_and_edit_are_distinguished(self, client) -> None:
        body = _post(client, "/api/autorun/stages/generate",
                     {"domain": DOMAIN, "stage_id": "features"}).get_json()
        stage = next(s for s in body["stages"] if s["stage_id"] == "features")
        item_id = stage["items"][0]["item_id"]

        _post(client, "/api/autorun/stages/item",
              {"domain": DOMAIN, "stage_id": "features", "item_id": item_id, "approved": True})
        _post(client, "/api/autorun/stages/item",
              {"domain": DOMAIN, "stage_id": "features", "item_id": item_id, "title": "書換"})

        actions = [e["action"] for e in _audit(client)]
        assert "item_approve" in actions
        assert "item_edit" in actions

    def test_unapproval_is_recorded(self, client) -> None:
        body = _post(client, "/api/autorun/stages/generate",
                     {"domain": DOMAIN, "stage_id": "features"}).get_json()
        item_id = next(s for s in body["stages"]
                       if s["stage_id"] == "features")["items"][0]["item_id"]
        _post(client, "/api/autorun/stages/item",
              {"domain": DOMAIN, "stage_id": "features", "item_id": item_id, "approved": True})
        _post(client, "/api/autorun/stages/item",
              {"domain": DOMAIN, "stage_id": "features", "item_id": item_id, "approved": False})
        assert "item_unapprove" in [e["action"] for e in _audit(client)]

    def test_adopting_llm_suggestion_is_recorded(self, client) -> None:
        _post(client, "/api/autorun/stages/generate",
              {"domain": DOMAIN, "stage_id": "test_objective"})
        _post(client, "/api/autorun/stages/adopt",
              {"domain": DOMAIN, "stage_id": "test_objective", "title": "セキュリティ観点"})
        adopt = [e for e in _audit(client) if e["action"] == "adopt_llm"]
        assert adopt and "セキュリティ観点" in adopt[0]["detail"]

    def test_history_is_ordered_and_persisted(self, client, workspace) -> None:
        for stage_id in ("test_objective", "test_plan"):
            _post(client, "/api/autorun/stages/generate",
                  {"domain": DOMAIN, "stage_id": stage_id})
            _post(client, "/api/autorun/stages/approve",
                  {"domain": DOMAIN, "stage_id": stage_id})

        entries = _audit(client)
        assert [e["action"] for e in entries] == [
            "generate", "approve", "generate", "approve",
        ]
        saved = json.loads(
            (workspace / DOMAIN / "qa_process" / "stages.json").read_text(encoding="utf-8")
        )
        assert len(saved["audit"]) == 4, "ファイルにも残ること"


class TestProgressSummary:
    def test_reports_approved_count_for_history_view(self, client) -> None:
        """過去履歴で「8段階中いくつ承認済みか」を出すための集計。"""
        body = client.get(f"/api/autorun/stages?domain={DOMAIN}").get_json()
        assert body["approved_stage_count"] == 0
        assert body["stage_total"] == 8

        _post(client, "/api/autorun/stages/generate",
              {"domain": DOMAIN, "stage_id": "test_objective"})
        _post(client, "/api/autorun/stages/approve",
              {"domain": DOMAIN, "stage_id": "test_objective"})
        assert client.get(
            f"/api/autorun/stages?domain={DOMAIN}"
        ).get_json()["approved_stage_count"] == 1
