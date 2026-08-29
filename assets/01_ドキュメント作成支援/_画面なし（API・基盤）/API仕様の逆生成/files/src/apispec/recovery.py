"""観測した API 呼び出しを「画面↔API 対応表」と OpenAPI 雛形へ変換する。

雛形と呼ぶのは、観測から分かるのが「どの画面から何が呼ばれ、どんな形が返ったか」
までで、パラメータの必須性・型の網羅・エラー仕様までは分からないため。
埋められない箇所は空欄のまま残し、推測で埋めない。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from crawler.page_crawler import PageData

CLAIM_SCOPE = "observed_calls_only"

CLAIM_NOTICE = (
    "本書はクロール中に実際に発火した API 呼び出しのみの記録であり、"
    "APIの網羅を主張するものではない。"
)

OPENAPI_VERSION = "3.0.3"

# 数値・UUID・日付など、値が変わっても同じ経路とみなせるものをパラメータ化する。
_PATH_PARAM_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^\d+$"), "id"),
    (
        re.compile(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        ),
        "uuid",
    ),
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "date"),
    (re.compile(r"^[0-9a-fA-F]{24,}$"), "hash"),
)


def build_screen_api_map(pages: list[PageData]) -> dict[str, Any]:
    """画面ごとに、そこで観測した API 呼び出しを対応付ける。"""
    screens: list[dict[str, Any]] = []
    for page in pages:
        calls = [
            {
                "method": str(call.method).upper(),
                "path": str(call.path),
                "template": templatize_path(str(call.path)),
                "status_code": int(call.status_code),
                "content_type": str(call.content_type),
                "sample_fields": list(call.sample_fields),
            }
            for call in getattr(page, "api_calls", ())
        ]
        if calls:
            screens.append(
                {
                    "page_url": str(page.url),
                    "title": str(page.title),
                    "calls": sorted(calls, key=lambda c: (c["template"], c["method"])),
                }
            )
    return {
        "meta": {"claim_scope": CLAIM_SCOPE, "claim_notice": CLAIM_NOTICE},
        "screens": screens,
        "summary": {
            "screens_with_api": len(screens),
            "observed_calls": sum(len(screen["calls"]) for screen in screens),
        },
    }


def templatize_path(path: str) -> str:
    """`/users/42/orders/7` → `/users/{id}/orders/{id}` のように正規化する。"""
    raw_path = urlsplit(path).path or path
    segments = raw_path.split("/")
    normalized: list[str] = []
    for segment in segments:
        normalized.append(_templatize_segment(segment))
    return "/".join(normalized) or "/"


def _templatize_segment(segment: str) -> str:
    if not segment:
        return segment
    for pattern, name in _PATH_PARAM_RULES:
        if pattern.match(segment):
            return f"{{{name}}}"
    return segment


def build_openapi_draft(pages: list[PageData], title: str = "観測ベースAPI雛形") -> dict[str, Any]:
    """観測結果から OpenAPI 雛形を組み立てる。推測で埋めない。"""
    paths: dict[str, dict[str, Any]] = {}
    for page in pages:
        for call in getattr(page, "api_calls", ()):
            template = templatize_path(str(call.path))
            method = str(call.method).lower()
            operation = paths.setdefault(template, {}).setdefault(
                method,
                {
                    "summary": "",
                    "description": (
                        "クロール中に観測した呼び出し。パラメータの必須性・"
                        "エラー仕様は未観測のため空欄。"
                    ),
                    "x-observed-from": [],
                    "responses": {},
                },
            )
            sources = operation["x-observed-from"]
            if str(page.url) not in sources:
                sources.append(str(page.url))
            operation["responses"][str(int(call.status_code))] = _response_schema(call)
            parameters = _path_parameters(template)
            if parameters:
                operation["parameters"] = parameters

    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": title,
            "version": "draft",
            "description": CLAIM_NOTICE,
        },
        "paths": dict(sorted(paths.items())),
    }


def _response_schema(call: Any) -> dict[str, Any]:
    fields = [str(field) for field in getattr(call, "sample_fields", ()) if str(field)]
    content_type = str(getattr(call, "content_type", "")) or "application/json"
    schema: dict[str, Any] = {"type": "object"}
    if fields:
        # 観測できたのはキーの存在まで。型は決めつけない。
        schema["properties"] = {field: {} for field in sorted(set(fields))}
    return {
        "description": "観測された応答（形は実測のキーのみ）",
        "content": {content_type.split(";")[0].strip(): {"schema": schema}},
    }


def _path_parameters(template: str) -> list[dict[str, Any]]:
    names = re.findall(r"\{([^}]+)\}", template)
    seen: list[str] = []
    parameters: list[dict[str, Any]] = []
    for index, name in enumerate(names):
        unique = name if name not in seen else f"{name}{index}"
        seen.append(unique)
        parameters.append(
            {
                "name": unique,
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
            }
        )
    return parameters
