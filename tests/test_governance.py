"""利用ガバナンス（レートリミット・クォータ・同時実行・プラン）と
デプロイWebhook・ドリフトトレンドのテスト。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.auto_run as auto_run_mod
import web.routes.history as history_mod
import web.summary as summary_mod
from web.services.governance import (
    PLAN_DEFAULTS,
    RateLimiter,
    check_crawl_allowed,
    effective_limits,
    monthly_crawl_usage,
    rate_limiter,
    register_stream_crawl,
    unregister_stream_crawl,
)

H = {"Host": "127.0.0.1"}


@pytest.fixture(autouse=True)
def _isolated_auth(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MODE", raising=False)
    for env in (
        "WEBSPEC2DOC_RATE_PER_MINUTE",
        "WEBSPEC2DOC_MONTHLY_CRAWLS",
        "WEBSPEC2DOC_CONCURRENT_JOBS",
    ):
        monkeypatch.delenv(env, raising=False)
    rate_limiter.reset()
    yield
    rate_limiter.reset()


def _client():
    return appmod.app.test_client()


def _setup_owner(client):
    return client.post(
        "/auth/setup",
        data={
            "tenant_name": "QA Team",
            "name": "Owner",
            "email": "owner@example.com",
            "password": "secret-pass-123",
            "password_confirm": "secret-pass-123",
        },
        headers=H,
    )


# ---------- effective_limits / RateLimiter 単体 ----------


def test_effective_limits_plan_defaults() -> None:
    assert effective_limits(None) == PLAN_DEFAULTS["standard"] | {"plan": "standard"}
    assert effective_limits({"plan": "pro"})["monthly_crawls"] == 1000


def test_effective_limits_tenant_override_and_env(monkeypatch) -> None:
    tenant = {"plan": "standard", "limits_json": json.dumps({"monthly_crawls": 5})}
    assert effective_limits(tenant)["monthly_crawls"] == 5
    monkeypatch.setenv("WEBSPEC2DOC_MONTHLY_CRAWLS", "7")
    assert effective_limits(tenant)["monthly_crawls"] == 7


def test_effective_limits_ignores_broken_json() -> None:
    tenant = {"plan": "standard", "limits_json": "{broken"}
    assert effective_limits(tenant)["monthly_crawls"] == PLAN_DEFAULTS["standard"]["monthly_crawls"]


def test_rate_limiter_blocks_after_burst() -> None:
    limiter = RateLimiter()
    results = [limiter.check("user-1", 3) for _ in range(4)]
    assert results[:3] == [None, None, None]
    assert results[3] is not None and results[3] > 0


def test_rate_limiter_zero_means_unlimited() -> None:
    limiter = RateLimiter()
    assert all(limiter.check("user-1", 0) is None for _ in range(100))


def test_rate_limiter_keys_are_independent() -> None:
    limiter = RateLimiter()
    for _ in range(3):
        assert limiter.check("a", 3) is None
    assert limiter.check("a", 3) is not None
    assert limiter.check("b", 3) is None


# ---------- 月次クォータ集計 ----------


def test_monthly_crawl_usage_counts_current_month(tmp_path: Path) -> None:
    from web.services.usage_tracker import record_usage

    record_usage(tmp_path, event="crawl", domain="a.com", screen_count=1)
    record_usage(tmp_path, event="autorun", domain="a.com")
    record_usage(tmp_path, event="ux_review", domain="a.com")  # 対象外イベント
    # 先月のレコードはカウントされない
    log = tmp_path / "usage_log.jsonl"
    log.write_text(
        log.read_text(encoding="utf-8")
        + json.dumps({"timestamp": "2000-01-01T00:00:00+00:00", "event": "crawl", "domain": "x"})
        + "\n",
        encoding="utf-8",
    )
    assert monthly_crawl_usage(tmp_path) == 2


# ---------- check_crawl_allowed ----------


def test_check_crawl_allowed_open_when_auth_disabled(tmp_path: Path) -> None:
    with appmod.app.test_request_context("/", headers=H):
        allowed, reason, _ = check_crawl_allowed(None, tmp_path)
    assert allowed and reason == ""


def test_stream_crawl_counts_toward_concurrency(tmp_path: Path) -> None:
    c = _client()
    _setup_owner(c)
    tenant = {"plan": "standard", "limits_json": json.dumps({"concurrent_jobs": 1})}
    register_stream_crawl("run-x", tmp_path)
    try:
        with appmod.app.test_request_context("/", headers=H):
            allowed, reason, usage = check_crawl_allowed(tenant, tmp_path)
        assert not allowed
        assert "同時実行数" in reason
        assert usage["running_jobs"] == 1
    finally:
        unregister_stream_crawl("run-x")


# ---------- rate_guard 統合 ----------


def test_rate_guard_returns_429_with_retry_after(monkeypatch) -> None:
    c = _client()
    _setup_owner(c)
    monkeypatch.setenv("WEBSPEC2DOC_RATE_PER_MINUTE", "2")
    rate_limiter.reset()
    codes = [c.get("/api/history", headers=H).status_code for _ in range(3)]
    assert codes[:2] == [200, 200]
    res = c.get("/api/history", headers=H)
    assert res.status_code == 429
    assert res.headers.get("Retry-After")
    assert res.get_json()["code"] == "rate_limited"


def test_rate_guard_inactive_when_auth_disabled(monkeypatch) -> None:
    monkeypatch.setenv("WEBSPEC2DOC_RATE_PER_MINUTE", "1")
    rate_limiter.reset()
    c = _client()
    codes = [c.get("/api/history", headers=H).status_code for _ in range(5)]
    assert codes == [200] * 5


# ---------- クロール起動点のクォータ拒否 ----------


def _exhaust_quota(client, tmp_path: Path, monkeypatch) -> None:
    """monthly_crawls=1 に絞り、実績1件を書き込んで上限到達状態を作る。"""
    from web.services.usage_tracker import record_usage
    from web.tenancy import TENANTS_DIR_NAME

    client.patch("/api/auth/tenant", json={"limits": {"monthly_crawls": 1}}, headers=H)
    tenant_dir = tmp_path / TENANTS_DIR_NAME / "qa-team"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    record_usage(tenant_dir, event="crawl", domain="example.com", screen_count=1)


def test_autorun_start_rejected_when_quota_exhausted(tmp_path: Path, monkeypatch) -> None:
    c = _client()
    _setup_owner(c)
    _exhaust_quota(c, tmp_path, monkeypatch)
    monkeypatch.setattr(auto_run_mod, "OUTPUT_DIR", tmp_path)
    res = c.post("/api/autorun/start", json={"url": "https://example.com"}, headers=H)
    assert res.status_code == 429
    assert res.get_json()["code"] == "quota_exceeded"


def test_run_stream_rejected_when_quota_exhausted(tmp_path: Path, monkeypatch) -> None:
    import web.routes.crawl as crawl_mod

    c = _client()
    _setup_owner(c)
    _exhaust_quota(c, tmp_path, monkeypatch)
    monkeypatch.setattr(crawl_mod, "OUTPUT_DIR", tmp_path)
    res = c.post("/run", data={"urls": "https://example.com"}, headers=H)
    assert res.status_code == 429
    assert "上限" in res.get_data(as_text=True)


def test_api_v1_crawl_rejected_when_quota_exhausted(tmp_path: Path, monkeypatch) -> None:
    import web.routes.api_v1 as api_v1_mod

    c = _client()
    _setup_owner(c)
    _exhaust_quota(c, tmp_path, monkeypatch)
    monkeypatch.setattr(api_v1_mod, "OUTPUT_DIR", tmp_path)
    res = c.post("/api/v1/sites/example.com/crawl", json={"url": "https://example.com"}, headers=H)
    assert res.status_code == 429


# ---------- デプロイWebhook ----------


def test_deploy_hook_queues_compare_crawl(monkeypatch) -> None:
    import web.services.job_queue as jq

    c = _client()
    _setup_owner(c)
    token = c.post("/api/auth/api-tokens", json={"name": "ci"}, headers=H).get_json()["token"]

    anon = _client()
    with patch.object(jq, "_run_job"):
        res = anon.post(
            "/api/v1/hooks/deploy",
            json={"url": "https://example.com"},
            headers={**H, "Authorization": f"Bearer {token['token']}"},
        )
    assert res.status_code == 202
    body = res.get_json()
    assert body["status"] == "queued" and body["compare"] is True and body["job_id"]


def test_deploy_hook_requires_auth_and_valid_url() -> None:
    c = _client()
    _setup_owner(c)
    token = c.post("/api/auth/api-tokens", json={"name": "ci"}, headers=H).get_json()["token"]
    anon = _client()
    assert (
        anon.post(
            "/api/v1/hooks/deploy", json={"url": "https://example.com"}, headers=H
        ).status_code
        == 401
    )
    bad = anon.post(
        "/api/v1/hooks/deploy",
        json={"url": "ftp://bad"},
        headers={**H, "Authorization": f"Bearer {token['token']}"},
    )
    assert bad.status_code == 400


# ---------- ドリフトトレンド ----------


def _write_snapshots(base: Path, domain: str = "example.com") -> Path:
    snaps = base / domain / "snapshots"
    snaps.mkdir(parents=True, exist_ok=True)

    def page(n: int) -> str:
        return json.dumps([{"forms": [{"fields": [1, 2]}], "buttons": ["a"]} for _ in range(n)])

    (snaps / "20260701-120000.json").write_text(page(3), encoding="utf-8")
    (snaps / "20260708-120000.json").write_text(page(5), encoding="utf-8")
    (snaps / "broken.json").write_text("{oops", encoding="utf-8")
    return base / domain


def test_snapshot_trend_and_summary(tmp_path: Path) -> None:
    from web.services.drift_trend import snapshot_trend, trend_summary

    domain_dir = _write_snapshots(tmp_path)
    points = snapshot_trend(domain_dir)
    assert [p["screens"] for p in points] == [3, 5]  # 壊れたファイルは除外
    summary = trend_summary(points)
    assert summary["delta"] == {"screens": 2, "forms": 2, "fields": 4, "buttons": 2}


def test_trend_empty_when_no_snapshots(tmp_path: Path) -> None:
    from web.services.drift_trend import snapshot_trend, trend_summary

    assert snapshot_trend(tmp_path / "nope") == []
    assert trend_summary([]) == {"points": 0}


def test_api_drift_trend_and_history_badge(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(history_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(summary_mod, "OUTPUT_DIR", tmp_path)
    _write_snapshots(tmp_path)
    c = _client()
    res = c.get("/api/drift-trend?domain=example.com", headers=H)
    assert res.status_code == 200
    assert len(res.get_json()["points"]) == 2
    assert c.get("/api/drift-trend?domain=../evil", headers=H).status_code == 404

    items = c.get("/api/history", headers=H).get_json()["items"]
    target = next(i for i in items if i["domain"] == "example.com")
    assert target["drift_delta"]["screens"] == 2


# ---------- 使用量API・プラン変更 ----------


def test_usage_api_and_account_card(tmp_path: Path) -> None:
    c = _client()
    _setup_owner(c)
    usage = c.get("/api/auth/usage", headers=H).get_json()
    assert usage["limits"]["plan"] == "standard"
    assert "monthly_crawls" in usage and "running_jobs" in usage
    html = c.get("/auth/account", headers=H).get_data(as_text=True)
    assert "使用量と上限" in html


def test_plan_change_owner_only() -> None:
    c = _client()
    _setup_owner(c)
    res = c.patch("/api/auth/tenant", json={"plan": "pro"}, headers=H)
    assert res.status_code == 200 and res.get_json()["tenant"]["plan"] == "pro"
    assert c.patch("/api/auth/tenant", json={"plan": "bogus"}, headers=H).status_code == 400

    c.post(
        "/api/auth/users",
        json={
            "email": "m@example.com",
            "name": "M",
            "password": "member-pass-123",
            "role": "member",
        },
        headers=H,
    )
    mc = _client()
    mc.post(
        "/auth/login", data={"email": "m@example.com", "password": "member-pass-123"}, headers=H
    )
    assert mc.patch("/api/auth/tenant", json={"plan": "pro"}, headers=H).status_code == 403
