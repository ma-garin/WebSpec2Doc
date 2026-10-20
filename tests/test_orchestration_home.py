"""指揮ホーム（/api/home/summary）: キー・null の扱い・未登録と言わない・partial・view。"""

from __future__ import annotations

import json

import pytest
from web.services.orchestration import home_summary

COUNT_KEYS = {
    "sites", "ok", "running", "failed", "human_action", "awaiting_approval", "unverified",
    "unanalyzed", "changes_today", "tests_today", "fixes_today", "reports_today",
}
SITE_KEYS = {
    "domain", "label", "status", "stage", "last_run", "evidence", "human_action",
    "latest_change", "latest_failure", "links",
}


def _make_site(out, domain="example.com"):
    d = out / domain
    d.mkdir(parents=True)
    (d / "report.json").write_text(json.dumps({"title": domain, "pages": []}), encoding="utf-8")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import app

    monkeypatch.setattr("web.routes.orchestration._out", lambda: tmp_path)
    app.config["TESTING"] = True
    return app.test_client()


def test_zero_sites_keys_and_counts(tmp_path):
    res = home_summary.build(tmp_path)
    assert set(res["counts"]) == COUNT_KEYS
    assert res["counts"]["sites"] == 0
    assert res["sites"] == [] and res["partial_errors"] == []
    # 集計源が無い指標は 0 ではなく null
    assert res["counts"]["changes_today"] is None
    assert res["counts"]["unverified"] is None


def test_site_without_run_is_not_unregistered(tmp_path):
    _make_site(tmp_path)
    res = home_summary.build(tmp_path)
    site = res["sites"][0]
    assert SITE_KEYS <= set(site)
    assert site["domain"] == "example.com"
    assert site["status"] == "not_started"
    assert site["last_run"] is None and site["evidence"] is None
    assert site["latest_change"] is None
    assert "未登録" not in json.dumps(res, ensure_ascii=False)
    assert site["links"]["s01"] == "/sites/example.com/spec"
    assert site["links"]["s03"] == "/auto-run?site=example.com"  # 入口でサイトを選び直させない
    assert set(site["links"]) == {"s01", "s02", "s03", "s09", "s05"}
    assert res["counts"]["sites"] == 1 and res["counts"]["failed"] == 0


def test_partial_errors_and_null_dependent_counts(tmp_path, monkeypatch):
    _make_site(tmp_path)

    def boom(*_a, **_k):
        raise RuntimeError("x")

    monkeypatch.setattr("web.services.orchestration.home_summary.report_doc.list_reports", boom)
    monkeypatch.setattr("web.services.orchestration.workflow_view._awaiting_reports", boom)
    monkeypatch.setattr(home_summary._Sources, "projects", lambda self: {"example.com": "p1"})
    res = home_summary.build(tmp_path)
    assert "reports" in res["partial_errors"]
    assert res["counts"]["reports_today"] is None
    assert res["counts"]["awaiting_approval"] is None


def test_sites_source_failure_nulls_all_counts(tmp_path, monkeypatch):
    def boom(_out):
        raise OSError("x")

    monkeypatch.setattr("web.services.orchestration.workflow_view._list_sites", boom)
    res = home_summary.build(tmp_path)
    assert res["partial_errors"] == ["sites"]
    assert all(v is None for v in res["counts"].values())


def test_failure_and_view_filter(tmp_path, monkeypatch):
    _make_site(tmp_path, "a.com")
    _make_site(tmp_path, "b.com")
    monkeypatch.setattr(
        home_summary._Sources, "failures", lambda self, d: 2 if d == "a.com" else 0)
    monkeypatch.setattr(
        home_summary, "_site_evidence",
        lambda d: ({"fact": 1, "inference": 2, "unverified": 3} if d == "b.com" else None, False))
    res = home_summary.build(tmp_path)
    assert res["counts"]["failed"] == 1
    assert res["counts"]["unverified"] == 3
    assert [s["domain"] for s in home_summary.build(tmp_path, "failed")["sites"]] == ["a.com"]
    # 根拠の結果が無い a.com も「未確認（解析結果なし）」なので未確認ビューに入る
    assert sorted(s["domain"] for s in home_summary.build(tmp_path, "unverified")["sites"]) == ["a.com", "b.com"]
    assert res["counts"]["unanalyzed"] == 1
    assert home_summary.build(tmp_path, "human")["sites"] == []
    # 未知の view は all
    assert len(home_summary.build(tmp_path, "zzz")["sites"]) == 2
    assert home_summary.build(tmp_path, "zzz")["view"] == "all"


def test_classify_evidence():
    got = home_summary.classify_evidence(
        [{"state": "observed"}, {"state": "static"}, {"state": "inferred"}, {"state": "?"},
         {"state": "document"}, {"state": "ambiguous"}])
    # 区分は WS2D.evidence.category と同じ（文書=推論・曖昧=未確認）
    assert got == {"fact": 1, "inference": 3, "unverified": 2}


def test_api_and_page_modes(client, tmp_path):
    res = client.get("/api/home/summary?view=failed")
    assert res.status_code == 200
    body = res.get_json()
    assert body["view"] == "failed" and set(body["counts"]) == COUNT_KEYS
    home = client.get("/orchestration").get_data(as_text=True)
    assert 'data-mode="home"' in home and 'id="ch-kpis"' in home
    detail = client.get("/orchestration?site=example.com").get_data(as_text=True)
    assert 'data-mode="detail"' in detail and 'id="ch-kpis"' not in detail
    assert "指揮ホーム" in detail
