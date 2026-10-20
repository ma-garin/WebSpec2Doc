"""外部公開構成では既定の admin / password を自動作成しない。"""
import app


class _Store:
    def __init__(self) -> None:
        self.called = False

    def ensure_initial_admin(self):
        self.called = True
        return None


def _run(monkeypatch) -> bool:
    store = _Store()
    monkeypatch.setattr("web.services.auth_store.get_auth_store", lambda: store)
    app._bootstrap_initial_admin()
    return store.called


def test_external_bind_skips_default_admin(monkeypatch) -> None:
    monkeypatch.setenv("WEBSPEC2DOC_TRUSTED_HOSTS", "ws2d.example.com")
    monkeypatch.delenv(app.BOOTSTRAP_ADMIN_ENV, raising=False)
    assert _run(monkeypatch) is False


def test_explicit_bootstrap_wins_when_external(monkeypatch) -> None:
    monkeypatch.setenv("WEBSPEC2DOC_TRUSTED_HOSTS", "ws2d.example.com")
    monkeypatch.setenv(app.BOOTSTRAP_ADMIN_ENV, "1")
    assert _run(monkeypatch) is True


def test_local_default_still_bootstraps(monkeypatch) -> None:
    monkeypatch.delenv("WEBSPEC2DOC_TRUSTED_HOSTS", raising=False)
    monkeypatch.delenv(app.BOOTSTRAP_ADMIN_ENV, raising=False)
    assert _run(monkeypatch) is True
