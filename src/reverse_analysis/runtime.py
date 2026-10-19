"""既存 snapshot.json から API 観測を読み、出典へ戻れる RuntimeObservation にする。

snapshot は読み取りのみ。構造を厳密に検証してから既存の load_snapshot と
build_screen_api_map を再利用する。既存 snapshot は API の origin と query を
保存しないため、origin は null・query_scope は not_retained とし、
page_url の origin を API の接続先とみなさない。
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apispec.recovery import build_screen_api_map
from diff.snapshot import load_snapshot
from reverse_analysis.models import (
    LIMIT_OBSERVED_CALLS_ONLY,
    LIMIT_RUNTIME_ORIGIN_NOT_RECORDED,
    LIMIT_RUNTIME_QUERY_NOT_RETAINED,
    Coverage,
    Diagnostic,
    RuntimeObservation,
    make_id,
)

STAGE = "runtime_input"

RUNTIME_LIMITATIONS = (
    LIMIT_OBSERVED_CALLS_ONLY,
    LIMIT_RUNTIME_ORIGIN_NOT_RECORDED,
    LIMIT_RUNTIME_QUERY_NOT_RETAINED,
)

_CallKey = tuple[str, str, int, str, tuple[str, ...]]


@dataclass(frozen=True)
class RuntimeInput:
    """runtime 入力の読み取り結果。失敗時は observations が空で coverage が failed。"""

    snapshot_sha256: str | None
    observations: tuple[RuntimeObservation, ...]
    coverage: Coverage
    diagnostics: tuple[Diagnostic, ...]


class _SnapshotSchemaError(ValueError):
    def __init__(self, pointer: str, reason: str) -> None:
        super().__init__(f"{pointer or '/'}: {reason}")
        self.pointer = pointer
        self.reason = reason


def load_runtime_observations(snapshot_path: Path) -> RuntimeInput:
    """snapshot を検証し、API 観測を snapshot digest＋JSON pointer 付きで返す。"""
    label = snapshot_path.name
    try:
        raw_bytes = snapshot_path.read_bytes()
    except FileNotFoundError:
        return _failed(
            None,
            "runtime_snapshot_missing",
            f"指定した snapshot（{label}）が見つかりません。",
            "既存クロールで保存した snapshots/*.json のパスを指定してください。",
        )
    except OSError:
        return _failed(
            None,
            "runtime_snapshot_unreadable",
            f"snapshot（{label}）を読み取れません。",
            "ファイルの権限と種類（通常ファイルか）を確認してください。",
        )
    digest = hashlib.sha256(raw_bytes).hexdigest()
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _failed(
            digest,
            "runtime_snapshot_invalid_json",
            f"snapshot（{label}）が UTF-8 の JSON として読めません。",
            "WebSpec2Doc が保存した snapshot を壊さずに指定してください。",
        )
    try:
        _validate_snapshot(raw)
    except _SnapshotSchemaError as exc:
        return _failed(
            digest,
            "runtime_snapshot_invalid_schema",
            f"snapshot（{label}）の構造が不正です（{exc.pointer or '/'}: {exc.reason}）。",
            "WebSpec2Doc が保存した snapshot を指定してください。",
        )

    changed = _failed(
        digest,
        "runtime_snapshot_changed",
        f"読み取り中に snapshot（{label}）が変更または削除されました。",
        "書き込み中でない snapshot を指定して再実行してください。",
    )
    # 既存ローダーは最低限の検証外の属性（headings=null 等）で任意の例外を出し得る。
    # 例外の本文は絶対 path を含み得るため、型も本文も利用者に出さない。
    try:
        pages = load_snapshot(snapshot_path)
    except OSError:
        return changed
    except Exception:
        return _loader_failed(digest, label)
    try:
        reread = snapshot_path.read_bytes()
    except OSError:
        return changed
    if hashlib.sha256(reread).hexdigest() != digest:
        return changed
    try:
        observations = tuple(_observations(digest, raw, pages))
    except Exception:
        return _loader_failed(digest, label)
    return RuntimeInput(
        snapshot_sha256=digest,
        observations=observations,
        coverage=Coverage(
            status="complete",
            truncated=False,
            omitted_count=0,
            limitations=RUNTIME_LIMITATIONS,
        ),
        diagnostics=(),
    )


def resolve_json_pointer(document: Any, pointer: str) -> Any:
    """RFC 6901 の JSON pointer を解決する（出典の追跡確認用）。"""
    current = document
    if pointer == "":
        return current
    for token in pointer.lstrip("/").split("/"):
        key = token.replace("~1", "/").replace("~0", "~")
        current = current[int(key)] if isinstance(current, list) else current[key]
    return current


def _loader_failed(digest: str, label: str) -> RuntimeInput:
    return _failed(
        digest,
        "runtime_snapshot_invalid_schema",
        f"snapshot（{label}）の構造が不正で、既存の読み込み処理で読めません。",
        "WebSpec2Doc が保存した snapshot を指定してください。",
    )


def _failed(digest: str | None, code: str, message: str, next_action: str) -> RuntimeInput:
    return RuntimeInput(
        snapshot_sha256=digest,
        observations=(),
        coverage=Coverage(
            status="failed",
            truncated=False,
            omitted_count=None,
            limitations=RUNTIME_LIMITATIONS,
        ),
        diagnostics=(
            Diagnostic(
                code=code,
                severity="error",
                stage=STAGE,
                message=message,
                next_action=next_action,
            ),
        ),
    )


def _validate_snapshot(raw: Any) -> None:
    if not isinstance(raw, list):
        raise _SnapshotSchemaError("", "トップレベルはページの配列である必要があります")
    for page_index, page in enumerate(raw):
        pointer = f"/{page_index}"
        if not isinstance(page, dict):
            raise _SnapshotSchemaError(pointer, "ページはオブジェクトである必要があります")
        if not isinstance(page.get("url"), str):
            raise _SnapshotSchemaError(f"{pointer}/url", "文字列である必要があります")
        if "title" in page and not isinstance(page["title"], str):
            raise _SnapshotSchemaError(f"{pointer}/title", "文字列である必要があります")
        calls = page.get("api_calls", [])
        if not isinstance(calls, list):
            raise _SnapshotSchemaError(f"{pointer}/api_calls", "配列である必要があります")
        for call_index, call in enumerate(calls):
            _validate_call(f"{pointer}/api_calls/{call_index}", call)


def _validate_call(pointer: str, call: Any) -> None:
    if not isinstance(call, dict):
        raise _SnapshotSchemaError(pointer, "API 呼び出しはオブジェクトである必要があります")
    method = call.get("method")
    if not isinstance(method, str) or not method.strip():
        raise _SnapshotSchemaError(f"{pointer}/method", "空でない文字列である必要があります")
    if not isinstance(call.get("path"), str):
        raise _SnapshotSchemaError(f"{pointer}/path", "文字列である必要があります")
    status = call.get("status_code")
    if isinstance(status, bool) or not isinstance(status, int):
        raise _SnapshotSchemaError(f"{pointer}/status_code", "整数である必要があります")
    if not isinstance(call.get("content_type", ""), str):
        raise _SnapshotSchemaError(f"{pointer}/content_type", "文字列である必要があります")
    fields_value = call.get("sample_fields")
    if fields_value is not None and (
        not isinstance(fields_value, list)
        or not all(isinstance(item, str) for item in fields_value)
    ):
        raise _SnapshotSchemaError(f"{pointer}/sample_fields", "文字列の配列である必要があります")


def _observations(digest: str, raw: list[Any], pages: list[Any]) -> list[RuntimeObservation]:
    observations: list[RuntimeObservation] = []
    for page_index, page in enumerate(pages):
        screen_map = build_screen_api_map([page])
        if not screen_map["screens"]:
            continue
        screen = screen_map["screens"][0]
        indices = _raw_indices_by_key(raw[page_index].get("api_calls", []))
        for call in screen["calls"]:
            key = _call_key(
                call["method"],
                call["path"],
                call["status_code"],
                call["content_type"],
                call["sample_fields"],
            )
            call_index = indices[key].pop(0)
            pointer = f"/{page_index}/api_calls/{call_index}"
            observations.append(
                RuntimeObservation(
                    id=make_id("ro", digest, pointer, "runtime_api"),
                    snapshot_sha256=digest,
                    json_pointer=pointer,
                    page_url=str(screen["page_url"]),
                    method=call["method"],
                    path=call["path"],
                    status_code=call["status_code"],
                    content_type=call["content_type"],
                    sample_fields=tuple(call["sample_fields"]),
                )
            )
    return sorted(observations, key=_pointer_order)


def _raw_indices_by_key(calls: list[dict[str, Any]]) -> dict[_CallKey, list[int]]:
    indices: dict[_CallKey, list[int]] = defaultdict(list)
    for call_index, call in enumerate(calls):
        key = _call_key(
            str(call["method"]).upper(),
            call["path"],
            call["status_code"],
            call.get("content_type", ""),
            call.get("sample_fields") or [],
        )
        indices[key].append(call_index)
    return indices


def _call_key(
    method: str, path: str, status: int, content_type: str, sample_fields: list[str]
) -> _CallKey:
    return (method, path, status, content_type, tuple(sample_fields))


def _pointer_order(observation: RuntimeObservation) -> tuple[int, ...]:
    return tuple(int(part) for part in observation.json_pointer.split("/")[1::2])
