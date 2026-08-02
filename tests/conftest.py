from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

# src/ をパスに追加してモジュールを import できるようにする
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from crawler.page_crawler import FieldData, FormData, PageData

SAMPLE_SITE_DIR = Path(__file__).parent / "fixtures" / "sample_site"


@pytest.fixture(autouse=True, scope="session")
def isolate_auth_db_for_session(tmp_path_factory) -> Iterator[None]:
    """セッション全体の既定として、認証DBを実環境から切り離す。

    module スコープの fixture（例: test_ui_contract の spa）は function スコープの
    fixture より先に作られるため、function スコープの隔離だけでは間に合わない。
    """
    key = "WEBSPEC2DOC_AUTH_DB"
    previous = os.environ.get(key)
    os.environ[key] = str(tmp_path_factory.mktemp("auth-session") / "auth.db")
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


@pytest.fixture(autouse=True)
def isolate_auth_db(tmp_path, monkeypatch) -> None:
    """認証DBを実環境（instance/auth.db）から切り離す。

    開発サーバーを一度起動すると instance/auth.db に初期管理者ができる。
    認証は「ユーザー0人なら無効」なので、切り離さないと全ページが認証必須になり、
    それを前提にしていないテストが一斉にログイン壁へ落ちる（実測 341 failed）。
    テスト側で独自に WEBSPEC2DOC_AUTH_DB を設定するモジュールは、そちらが勝つ。
    """
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_DB", str(tmp_path / "auth-isolated.db"))


@pytest.fixture(autouse=True)
def isolate_allow_local_environment() -> Iterator[None]:
    """ローカルクロール許可が別テストへ漏れてSSRF前提を変えないよう隔離する。"""
    key = "WEBSPEC2DOC_ALLOW_LOCAL"
    previous = os.environ.pop(key, None)
    try:
        yield
    finally:
        os.environ.pop(key, None)
        if previous is not None:
            os.environ[key] = previous


@pytest.fixture()
def field_text() -> FieldData:
    return FieldData(field_type="text", name="q", placeholder="キーワードを入力", required=False)


@pytest.fixture()
def field_email() -> FieldData:
    return FieldData(field_type="email", name="email", placeholder="メールアドレス", required=True)


@pytest.fixture()
def field_required_text() -> FieldData:
    return FieldData(field_type="text", name="name", placeholder="お名前", required=True)


@pytest.fixture()
def form_search(field_text: FieldData) -> FormData:
    return FormData(action="/search", method="get", fields=(field_text,))


@pytest.fixture()
def form_contact(field_required_text: FieldData, field_email: FieldData) -> FormData:
    field_message = FieldData(
        field_type="textarea", name="message", placeholder="メッセージ", required=False
    )
    return FormData(
        action="/send", method="post", fields=(field_required_text, field_email, field_message)
    )


@pytest.fixture()
def page_top(form_search: FormData) -> PageData:
    return PageData(
        url="https://example.com/",
        title="テストサイト - トップ",
        headings=("テストサイト", "ようこそ"),
        links=("https://example.com/about.html", "https://example.com/contact.html"),
        forms=(form_search,),
        screenshot_path=None,
    )


@pytest.fixture()
def page_about() -> PageData:
    return PageData(
        url="https://example.com/about.html",
        title="テストサイト - 会社概要",
        headings=("会社概要", "私たちについて"),
        links=("https://example.com/",),
        forms=(),
        screenshot_path=None,
    )


@pytest.fixture()
def page_contact(form_contact: FormData) -> PageData:
    return PageData(
        url="https://example.com/contact.html",
        title="テストサイト - お問い合わせ",
        headings=("お問い合わせ",),
        links=("https://example.com/",),
        forms=(form_contact,),
        screenshot_path=None,
    )
