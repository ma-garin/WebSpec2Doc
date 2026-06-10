from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from crawler.page_crawler import FieldData, FormData, PageData

SNAPSHOTS_DIR_NAME = "snapshots"
SNAPSHOT_EXTENSION = ".json"
SNAPSHOT_TIME_FORMAT = "%Y%m%d-%H%M%S"
JSON_INDENT = 2


def save_snapshot(pages: list[PageData], output_dir: Path) -> Path:
    snapshots_dir = output_dir / SNAPSHOTS_DIR_NAME
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshots_dir / f"{_timestamp()}{SNAPSHOT_EXTENSION}"
    payload = [asdict(page) for page in pages]
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=JSON_INDENT),
        encoding="utf-8",
    )
    return snapshot_path


def load_snapshot(path: Path) -> list[PageData]:
    raw_pages = json.loads(path.read_text(encoding="utf-8"))
    return [_page_from_dict(item) for item in raw_pages]


def latest_snapshot(output_dir: Path) -> Path | None:
    snapshots_dir = output_dir / SNAPSHOTS_DIR_NAME
    if not snapshots_dir.is_dir():
        return None
    snapshots = sorted(snapshots_dir.glob(f"*{SNAPSHOT_EXTENSION}"))
    return snapshots[-1] if snapshots else None


def _timestamp() -> str:
    return datetime.now().strftime(SNAPSHOT_TIME_FORMAT)


def _to_int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _page_from_dict(data: dict[str, Any]) -> PageData:
    from crawler.page_crawler import PageData

    stack_raw = data.get("stack_info")
    stack_info = _stack_info_from_dict(stack_raw) if stack_raw is not None else None

    return PageData(
        url=str(data.get("url", "")),
        title=str(data.get("title", "")),
        headings=tuple(str(item) for item in data.get("headings", ())),
        links=tuple(str(item) for item in data.get("links", ())),
        forms=tuple(_form_from_dict(item) for item in data.get("forms", ())),
        screenshot_path=data.get("screenshot_path"),
        buttons=tuple(str(b) for b in data.get("buttons", ())),
        api_calls=tuple(_api_endpoint_from_dict(item) for item in data.get("api_calls", ())),
        stack_info=stack_info,
        state_id=str(data.get("state_id", "default")),
    )


def _form_from_dict(data: dict[str, Any]) -> FormData:
    from crawler.page_crawler import FormData

    return FormData(
        action=str(data.get("action", "")),
        method=str(data.get("method", "")),
        fields=tuple(_field_from_dict(item) for item in data.get("fields", ())),
    )


def _field_from_dict(data: dict[str, Any]) -> FieldData:
    from crawler.page_crawler import FieldData

    return FieldData(
        field_type=str(data.get("field_type", "")),
        name=str(data.get("name", "")),
        placeholder=str(data.get("placeholder", "")),
        required=bool(data.get("required", False)),
        maxlength=_to_int_or_none(data.get("maxlength")),
        minlength=_to_int_or_none(data.get("minlength")),
        min_value=str(data.get("min_value", "")),
        max_value=str(data.get("max_value", "")),
        pattern=str(data.get("pattern", "")),
        default=str(data.get("default", "")),
        options=tuple(str(o) for o in (data.get("options") or [])),
        element_id=str(data.get("element_id", "")),
    )


def _api_endpoint_from_dict(data: dict[str, Any]) -> Any:
    from crawler.page_crawler import ApiEndpoint

    return ApiEndpoint(
        method=str(data.get("method", "")),
        path=str(data.get("path", "")),
        status_code=int(data.get("status_code", 0)),
        content_type=str(data.get("content_type", "")),
        sample_fields=tuple(str(f) for f in (data.get("sample_fields") or [])),
    )


def _stack_info_from_dict(data: dict[str, Any]) -> Any:
    from analyzer.stack_detector import StackInfo

    return StackInfo(
        frontend_framework=str(data.get("frontend_framework", "")),
        rendering_mode=str(data.get("rendering_mode", "")),
        css_framework=str(data.get("css_framework", "")),
        state_management=str(data.get("state_management", "")),
        backend_hints=tuple(str(h) for h in (data.get("backend_hints") or [])),
        detected_libraries=tuple(str(lib) for lib in (data.get("detected_libraries") or [])),
    )
