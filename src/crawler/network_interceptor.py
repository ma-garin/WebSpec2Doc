from __future__ import annotations

"""クロール中の XHR / fetch レスポンスを傍受して API エンドポイントを記録する。

NetworkCapture を crawl_page() の前後で attach/detach することで、
1 ページ分のリクエストのみを正確に収集する。
"""

import json
import logging
from collections.abc import Callable
from urllib.parse import urlparse

from playwright.sync_api import Page, Response

from crawler.page_crawler import ApiEndpoint

STATIC_EXTENSIONS = frozenset(
    {
        ".js",
        ".css",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp4",
        ".webp",
        ".map",
        ".txt",
        ".xml",
    }
)
MAX_RESPONSE_BODY_BYTES = 32_768
SAMPLE_FIELDS_LIMIT = 20

logger = logging.getLogger(__name__)


class NetworkCapture:
    """ページに attach して XHR/fetch レスポンスを収集する。

    Usage::

        capture = NetworkCapture()
        capture.attach(page)
        try:
            page.goto(url, ...)
            ...
        finally:
            capture.detach()
        endpoints = capture.finalize()
    """

    def __init__(self) -> None:
        self._raw: list[tuple[str, str, int, str, tuple[str, ...]]] = []
        self._page: Page | None = None
        self._handler: Callable[[Response], None] | None = None

    def attach(self, page: Page) -> None:
        """page の response イベントにリスナーを登録する。"""
        self._page = page

        def _handler(response: Response) -> None:
            try:
                self._record(response)
            except Exception as exc:
                logger.debug("レスポンス記録エラー: %s", exc)

        self._handler = _handler
        page.on("response", _handler)

    def detach(self) -> None:
        """登録したリスナーを解除する。attach() 前に呼んでも安全。"""
        if self._page is not None and self._handler is not None:
            try:
                self._page.remove_listener("response", self._handler)
            except Exception:
                pass
        self._page = None
        self._handler = None

    def finalize(self) -> tuple[ApiEndpoint, ...]:
        """収集結果を重複除去（method+path+status）して返す。"""
        seen: dict[tuple[str, str, int], ApiEndpoint] = {}
        for method, path, status, ct, fields in self._raw:
            key = (method, path, status)
            if key not in seen:
                seen[key] = ApiEndpoint(
                    method=method,
                    path=path,
                    status_code=status,
                    content_type=ct,
                    sample_fields=fields,
                )
        return tuple(seen.values())

    def _record(self, response: Response) -> None:
        url = response.url
        parsed = urlparse(url)
        path = parsed.path or "/"

        # 静的ファイルは除外
        last_segment = path.split("/")[-1]
        suffix = f".{last_segment.rsplit('.', 1)[-1].lower()}" if "." in last_segment else ""
        if suffix in STATIC_EXTENSIONS:
            return

        ct = response.headers.get("content-type", "")
        is_json = "json" in ct
        is_form = "form" in ct

        # HTML ナビゲーション（2xx）は除外し、API 応答のみ記録
        if response.status < 300 and not (is_json or is_form):
            return

        try:
            method = response.request.method.upper()
        except Exception:
            method = "GET"

        sample_fields: tuple[str, ...] = ()
        if is_json:
            sample_fields = _extract_response_fields(response)

        self._raw.append((method, path, response.status, ct.split(";")[0].strip(), sample_fields))


def _extract_response_fields(response: Response) -> tuple[str, ...]:
    """JSON レスポンスのトップレベルキーを最大 SAMPLE_FIELDS_LIMIT 個返す。"""
    try:
        body = response.body()
        if len(body) > MAX_RESPONSE_BODY_BYTES:
            return ()
        data = json.loads(body.decode("utf-8", errors="replace"))
        if isinstance(data, dict):
            return tuple(list(data.keys())[:SAMPLE_FIELDS_LIMIT])
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return tuple(list(data[0].keys())[:SAMPLE_FIELDS_LIMIT])
    except Exception:
        pass
    return ()
