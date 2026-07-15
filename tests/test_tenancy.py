"""テナント分離（web/tenancy.py とデータ分離の実効性）のテスト。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.history as history_mod
import web.summary as summary_mod
from web.tenancy import (
    TENANTS_DIR_NAME,
    current_tenant,
    scoped_instance_path,
    scoped_output_dir,
)

H = {"Host": "127.0.0.1"}


@pytest.fixture(autouse=True)
def _isolated_auth_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MODE", raising=False)
    yield


def _client():
    return appmod.app.test_client()


# ---------- scoped_output_dir / scoped_instance_path 単体 ----------


def test_scoped_output_dir_without_context_returns_base(tmp_path: Path) -> None:
    assert scoped_output_dir(tmp_path) == tmp_path


def test_current_tenant_is_none_outside_request() -> None:
    assert current_tenant() is None


def test_scoped_output_dir_with_tenant_context(tmp_path: Path) -> None:
    with appmod.app.test_request_context("/"):
        from flask import g

        g.tenant = {"id": "t1", "slug": "qa-team", "name": "QA Team"}
        assert scoped_output_dir(tmp_path) == tmp_path / TENANTS_DIR_NAME / "qa-team"
        assert scoped_instance_path(tmp_path / "viewpoints.db") == (
            tmp_path / TENANTS_DIR_NAME / "qa-team" / "viewpoints.db"
        )


def test_scoped_output_dir_rejects_malicious_slug(tmp_path: Path) -> None:
    with appmod.app.test_request_context("/"):
        from flask import g

        g.tenant = {"id": "t1", "slug": "../evil", "name": "Evil"}
        with pytest.raises(ValueError):
            scoped_output_dir(tmp_path)


# ---------- テナント間のデータ分離（エンドツーエンド） ----------


def _make_two_tenants(client):
    """テナントA（セットアップ）+ テナントB（ストア直接作成）を用意し、
    それぞれのログイン済みクライアントを返す。"""
    from web.services.auth_store import get_auth_store

    client.post(
        "/auth/setup",
        data={
            "tenant_name": "Tenant A",
            "name": "A",
            "email": "a@example.com",
            "password": "secret-pass-123",
            "password_confirm": "secret-pass-123",
        },
        headers=H,
    )
    store = get_auth_store()
    tenant_b = store.create_tenant("Tenant B")
    store.create_user(tenant_b["id"], "b@example.com", "B", "secret-pass-123", role="owner")

    ca = _client()
    ca.post(
        "/auth/login",
        data={"email": "a@example.com", "password": "secret-pass-123"},
        headers=H,
    )
    cb = _client()
    cb.post(
        "/auth/login",
        data={"email": "b@example.com", "password": "secret-pass-123"},
        headers=H,
    )
    return ca, cb


def test_history_is_isolated_per_tenant(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(history_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(summary_mod, "OUTPUT_DIR", tmp_path)
    ca, cb = _make_two_tenants(_client())

    (tmp_path / TENANTS_DIR_NAME / "tenant-a" / "site-a.com").mkdir(parents=True)
    (tmp_path / TENANTS_DIR_NAME / "tenant-b" / "site-b.com").mkdir(parents=True)
    (tmp_path / "shared.com").mkdir()  # 共有領域（テナントからは見えない）

    domains_a = {i["domain"] for i in ca.get("/api/history", headers=H).get_json()["items"]}
    domains_b = {i["domain"] for i in cb.get("/api/history", headers=H).get_json()["items"]}
    assert domains_a == {"site-a.com"}
    assert domains_b == {"site-b.com"}


def test_shared_mode_history_excludes_tenants_dir(tmp_path: Path, monkeypatch) -> None:
    """認証オフ（ユーザーなし）の共有モードでは tenants/ をドメイン扱いしない。"""
    monkeypatch.setattr(history_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(summary_mod, "OUTPUT_DIR", tmp_path)
    (tmp_path / "example.com").mkdir()
    (tmp_path / TENANTS_DIR_NAME / "tenant-a" / "site-a.com").mkdir(parents=True)
    data = _client().get("/api/history", headers=H).get_json()
    domains = {i["domain"] for i in data["items"]}
    assert domains == {"example.com"}


def test_viewpoint_store_db_is_per_tenant(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIEWPOINTS_DB", str(tmp_path / "instance" / "viewpoints.db"))
    # config は import 時に env を読むため、モジュール属性も合わせて上書きする
    import web.config as config_mod
    from web.services.viewpoint_store import get_viewpoint_store

    monkeypatch.setattr(config_mod, "VIEWPOINTS_DB", tmp_path / "instance" / "viewpoints.db")

    ca, cb = _make_two_tenants(_client())

    with appmod.app.test_request_context("/"):
        from flask import g

        g.tenant = {"id": "ta", "slug": "tenant-a", "name": "Tenant A"}
        store_a = get_viewpoint_store()
        g.tenant = {"id": "tb", "slug": "tenant-b", "name": "Tenant B"}
        store_b = get_viewpoint_store()
        g.tenant = None
        store_shared = get_viewpoint_store()

    assert store_a.db_path != store_b.db_path
    assert TENANTS_DIR_NAME in str(store_a.db_path)
    assert store_shared.db_path == (tmp_path / "instance" / "viewpoints.db").resolve() or (
        store_shared.db_path == tmp_path / "instance" / "viewpoints.db"
    )


def test_reference_doc_upload_lands_in_tenant_dir(tmp_path: Path, monkeypatch) -> None:
    import io

    import web.routes.crawl as crawl_mod

    monkeypatch.setattr(crawl_mod, "OUTPUT_DIR", tmp_path)
    ca, _cb = _make_two_tenants(_client())
    res = ca.post(
        "/api/reference-docs",
        data={
            "domain": "example.com",
            "files": (io.BytesIO(b"# spec"), "spec.md"),
        },
        headers=H,
        content_type="multipart/form-data",
    )
    assert res.status_code == 200, res.get_data(as_text=True)
    saved = tmp_path / TENANTS_DIR_NAME / "tenant-a" / "example.com" / "reference_docs" / "spec.md"
    assert saved.is_file()
