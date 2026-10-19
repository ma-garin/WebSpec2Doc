"""指揮（workflow）の setup 状態: 観測済みサイトがあるのに「未登録」と言わない。"""

from __future__ import annotations

import json

import pytest
from web.services.orchestration import workflow_view


def _make_site(out, domain="example.com"):
    d = out / domain
    d.mkdir(parents=True)
    (d / "report.json").write_text(
        json.dumps({"title": domain, "pages": []}, ensure_ascii=False), encoding="utf-8")


def test_no_sites_says_unregistered(tmp_path):
    state = workflow_view.build(tmp_path, "")
    assert state["sites"] == []
    assert state["current"]["key"] == "setup"
    assert "まだサイトが登録されていません" in state["current"]["text"]


def test_observed_site_without_project_is_not_unregistered(tmp_path):
    _make_site(tmp_path)
    state = workflow_view.build(tmp_path, "")
    assert [s["domain"] for s in state["sites"]] == ["example.com"]
    cur = state["current"]
    assert cur["key"] == "setup"
    assert "まだサイトが登録されていません" not in cur["text"]
    assert "example.com" in cur["text"] and "プロジェクト" in cur["text"]
    assert cur["action"]["kind"] == "start"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import app

    monkeypatch.setattr("web.routes.orchestration._out", lambda: tmp_path)
    app.config["TESTING"] = True
    return app.test_client()


def test_workflow_action_denied_for_non_admin(client, monkeypatch):
    from flask import jsonify

    def deny():
        resp = jsonify({"error": "この操作には管理者権限が必要です。", "code": "forbidden"})
        resp.status_code = 403
        return resp

    monkeypatch.setattr("web.routes.orchestration.require_admin", deny)
    res = client.post("/api/orchestration/workflow/actions", json={"kind": "start"})
    assert res.status_code == 403
