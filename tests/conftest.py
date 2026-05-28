from __future__ import annotations

import sys
from pathlib import Path

# src/ をパスに追加してモジュールを import できるようにする
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from crawler.page_crawler import FieldData, FormData, PageData


SAMPLE_SITE_DIR = Path(__file__).parent / "fixtures" / "sample_site"


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
    field_message = FieldData(field_type="textarea", name="message", placeholder="メッセージ", required=False)
    return FormData(action="/send", method="post", fields=(field_required_text, field_email, field_message))


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
