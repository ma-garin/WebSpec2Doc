"""登録済みルートから OpenAPI 3.0 ドキュメントを組み立てる。

apispec 等の依存を追加せず、Flask の url_map から生成する。対象が /api/v1 の
十数ルートに限られるため、依存を1つ増やすより自前生成のほうが軽い。

主張境界: **実装済みのルートだけ**を列挙する。仕様書に載っているのに動かない
エンドポイントは、利用者にとって嘘になるため。
"""

from __future__ import annotations

import re
from typing import Any

from flask import Flask

API_PREFIX = "/api/v1"
OPENAPI_VERSION = "3.0.3"
API_VERSION = "1.0"

_ERROR_REF = {"$ref": "#/components/schemas/Error"}

# 全応答に共通する項目（web/services/api_v1_format.py が付与する）。
COMPONENTS: dict[str, Any] = {
    "schemas": {
        "Meta": {
            "type": "object",
            "description": "対象・版・出所。どの対象について、どの版の API が、どこから読んだ値か。",
            "required": ["target", "version", "source"],
            "properties": {
                "target": {"type": "string", "nullable": True, "description": "対象（サイト名またはジョブ ID）"},
                "version": {"type": "string", "description": "API の版", "example": API_VERSION},
                "source": {"type": "string", "description": "値の出所"},
            },
        },
        "Error": {
            "type": "object",
            "required": ["error"],
            "properties": {
                "error": {
                    "type": "object",
                    "required": ["code", "message"],
                    "properties": {
                        "code": {
                            "type": "string",
                            "enum": [
                                "bad_request", "unauthorized", "forbidden", "not_found",
                                "conflict", "too_large", "internal_error", "upstream_failed",
                            ],
                        },
                        "message": {"type": "string", "description": "利用者向けの日本語と次の行動"},
                    },
                },
                "meta": {"$ref": "#/components/schemas/Meta"},
            },
        },
        "Success": {
            "type": "object",
            "required": ["meta"],
            "properties": {"meta": {"$ref": "#/components/schemas/Meta"}},
            "additionalProperties": True,
        },
    }
}

_EXCLUDED_METHODS = frozenset({"HEAD", "OPTIONS"})
_PATH_PARAM_RE = re.compile(r"<(?:[^:<>]+:)?([^<>]+)>")

_TAG_RULES: tuple[tuple[str, str], ...] = (
    ("/schedule", "schedule"),
    ("/notifications", "notifications"),
    ("/jobs", "jobs"),
    ("/test-cases", "test-cases"),
    ("/snapshots", "snapshots"),
    ("/diff", "diff"),
    ("/crawl", "crawl"),
    ("/report", "report"),
    ("/sites", "sites"),
    ("/healthz", "system"),
    ("/openapi.json", "system"),
    ("/docs", "system"),
)


def build_openapi_spec(app: Flask) -> dict[str, Any]:
    """アプリに登録済みの /api/v1 ルートから仕様を生成する。"""
    paths: dict[str, dict[str, Any]] = {}
    for rule in app.url_map.iter_rules():
        path = str(rule.rule)
        if not path.startswith(API_PREFIX):
            continue
        methods = sorted((rule.methods or set()) - _EXCLUDED_METHODS)
        if not methods:
            continue
        entry = paths.setdefault(_to_openapi_path(path), {})
        for method in methods:
            entry[method.lower()] = _operation(app, rule.endpoint, path, method)

    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": "WebSpec2Doc API",
            "version": API_VERSION,
            "description": (
                "実装済みのエンドポイントのみを列挙する。"
                "本仕様に載っていない操作は提供していない。"
            ),
        },
        "servers": [{"url": "/"}],
        "tags": _tags(paths),
        "paths": dict(sorted(paths.items())),
        "components": COMPONENTS,
    }


def _operation(app: Flask, endpoint: str, path: str, method: str) -> dict[str, Any]:
    view = app.view_functions.get(endpoint)
    doc = (view.__doc__ or "").strip() if view else ""
    summary = doc.splitlines()[0] if doc else f"{method} {path}"
    operation: dict[str, Any] = {
        "operationId": endpoint.replace(".", "_"),
        "summary": summary,
        "tags": [_tag_for(path)],
        "responses": _responses(method, path),
    }
    parameters = _path_parameters(path)
    if parameters:
        operation["parameters"] = parameters
    if method in {"POST", "PUT", "PATCH"}:
        operation["requestBody"] = {
            "required": True,
            "content": {"application/json": {"schema": {"type": "object"}}},
        }
    return operation


def _err(description: str) -> dict[str, Any]:
    return {"description": description, "content": {"application/json": {"schema": _ERROR_REF}}}


def _responses(method: str, path: str = "") -> dict[str, Any]:
    if path.endswith("/openapi.json") or path.endswith("/docs"):
        return {"200": {"description": "成功"}}
    ok = {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Success"}}}}
    responses: dict[str, Any] = {
        ("202" if path.endswith("/crawl") else "200"): {"description": "成功", **ok},
        "400": _err("入力が不正"),
        "401": _err("認証が必要"),
    }
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        responses["403"] = _err("権限が不足している")
    responses["404"] = _err("対象が存在しない")
    if path.endswith("/crawl"):
        responses["409"] = _err("同じ対象のジョブが待機中または実行中")
    responses["500"] = _err("サーバ内部の失敗")
    return responses


def _path_parameters(path: str) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "in": "path",
            "required": True,
            "schema": {"type": "string"},
        }
        for name in _PATH_PARAM_RE.findall(path)
    ]


def _to_openapi_path(path: str) -> str:
    """Flask の <converter:name> を OpenAPI の {name} 記法へ変換する。"""
    return _PATH_PARAM_RE.sub(r"{\1}", path)


def _tag_for(path: str) -> str:
    for fragment, tag in _TAG_RULES:
        if fragment in path:
            return tag
    return "api"


def _tags(paths: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    names = sorted(
        {
            str(operation.get("tags", ["api"])[0])
            for methods in paths.values()
            for operation in methods.values()
        }
    )
    return [{"name": name} for name in names]
