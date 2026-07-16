from __future__ import annotations

import json
from pathlib import Path

from crawler.page_crawler import PageData
from health.technical_health import build_technical_health, save_technical_health


def _page(
    url: str,
    *,
    status: int = 200,
    links: tuple[str, ...] = (),
    console_errors: tuple[str, ...] = (),
    mixed_content: tuple[str, ...] = (),
) -> PageData:
    return PageData(
        url=url,
        title=url,
        headings=(),
        links=links,
        forms=(),
        screenshot_path=None,
        http_status=status,
        console_errors=console_errors,
        mixed_content=mixed_content,
    )


def test_build_technical_health_uses_only_observed_targets() -> None:
    pages = [
        _page(
            "https://example.com/",
            links=("https://example.com/missing", "https://external.example/not-crawled"),
            console_errors=("Uncaught TypeError",),
            mixed_content=("http://example.com/legacy.js",),
        ),
        _page("https://example.com/missing", status=404),
    ]
    health = build_technical_health(pages)

    assert health["summary"] == {
        "page_http_errors": 1,
        "broken_links": 1,
        "console_errors": 1,
        "mixed_content": 1,
    }
    root = health["screens"][0]
    assert root["broken_links"] == [{"url": "https://example.com/missing", "status_code": 404}]
    assert "external.example" not in json.dumps(health)
    assert health["claim_boundary"] == "クロール中に到達・観測できた対象のみ"


def test_build_technical_health_excludes_observed_external_http_errors() -> None:
    pages = [
        _page("https://example.com/", links=("https://external.example/missing",)),
        _page("https://external.example/missing", status=404),
    ]

    health = build_technical_health(pages)

    assert health["summary"]["page_http_errors"] == 1
    assert health["summary"]["broken_links"] == 0
    assert health["screens"][0]["broken_links"] == []


def test_save_technical_health_writes_independent_artifact(tmp_path: Path) -> None:
    payload = build_technical_health([_page("https://example.com/")])
    path = save_technical_health(payload, tmp_path)
    assert path == tmp_path / "technical_health.json"
    assert json.loads(path.read_text(encoding="utf-8"))["summary"]["broken_links"] == 0
