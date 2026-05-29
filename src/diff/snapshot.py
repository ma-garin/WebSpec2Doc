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


def _page_from_dict(data: dict[str, Any]) -> PageData:
    from crawler.page_crawler import PageData

    return PageData(
        url=str(data.get("url", "")),
        title=str(data.get("title", "")),
        headings=tuple(str(item) for item in data.get("headings", ())),
        links=tuple(str(item) for item in data.get("links", ())),
        forms=tuple(_form_from_dict(item) for item in data.get("forms", ())),
        screenshot_path=data.get("screenshot_path"),
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
    )
