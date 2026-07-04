"""同梱デモサイト（demo/demo_site.py）の配信テスト。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "demo"))

from demo_site import SITE_DIR, app  # noqa: E402

_EXPECTED_PAGES = (
    "index.html",
    "login.html",
    "checkout.html",
    "contact.html",
    "products.html",
    "dashboard.html",
    "spa.html",
    "admin.html",
    "robots.txt",
    "style.css",
)


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


class TestDemoSiteFiles:
    def test_all_expected_pages_exist(self) -> None:
        for name in _EXPECTED_PAGES:
            assert (SITE_DIR / name).is_file(), f"デモサイトのファイルが欠落: {name}"


class TestDemoSiteServing:
    def test_index_served(self, client) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "DemoMart" in response.get_data(as_text=True)

    def test_robots_txt_has_crawl_delay_and_disallow(self, client) -> None:
        response = client.get("/robots.txt")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Crawl-delay: 2" in body
        assert "Disallow: /admin.html" in body

    def test_clean_url_resolves_to_html(self, client) -> None:
        response = client.get("/login")
        assert response.status_code == 200
        assert "ログイン" in response.get_data(as_text=True)

    def test_checkout_is_payment_screen(self, client) -> None:
        body = client.get("/checkout.html").get_data(as_text=True)
        assert "お支払い・決済" in body
        assert 'action="/payment/confirm"' in body
        assert "required" in body

    def test_contact_has_required_fields(self, client) -> None:
        body = client.get("/contact.html").get_data(as_text=True)
        assert body.count("required") >= 3
        assert 'maxlength="500"' in body

    def test_dashboard_has_modal_tabs_accordion(self, client) -> None:
        body = client.get("/dashboard.html").get_data(as_text=True)
        assert 'role="dialog"' in body
        assert 'role="tab"' in body
        assert "<details" in body

    def test_spa_page_uses_push_state(self, client) -> None:
        body = client.get("/spa.html").get_data(as_text=True)
        assert "history.pushState" in body

    def test_login_page_classified_as_auth(self, client) -> None:
        """デモの見せ場: ログイン画面が SCREEN_AUTH に分類されるキーワードを持つ。"""
        from llm.screen_classifier import SCREEN_AUTH, classify_screen_by_rules

        body = client.get("/login.html").get_data(as_text=True)
        assert 'type="password"' in body
        classification = classify_screen_by_rules(
            "DemoMart - ログイン", ("ログイン",), ["email", "password"]
        )
        assert classification.screen_type == SCREEN_AUTH

    def test_checkout_page_classified_as_payment(self, client) -> None:
        """デモの見せ場: 決済画面が SCREEN_PAYMENT に分類されるキーワードを持つ。"""
        from llm.screen_classifier import SCREEN_PAYMENT, classify_screen_by_rules

        classification = classify_screen_by_rules(
            "DemoMart - お支払い・決済", ("お支払い・決済",), ["card_number", "amount"]
        )
        assert classification.screen_type == SCREEN_PAYMENT
