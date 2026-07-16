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
WORK_DIR_NAME = "work"
CHECKPOINT_FILE_NAME = "current-checkpoint.json"


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


def save_partial_snapshot(
    pages: list[PageData], output_dir: Path, *, finalized: bool = False
) -> Path:
    """完了済みページを原子的に保存し、停止時はpartial snapshotとして確定する。"""
    payload = json.dumps([asdict(page) for page in pages], ensure_ascii=False, indent=JSON_INDENT)
    work_dir = output_dir / WORK_DIR_NAME
    work_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = work_dir / CHECKPOINT_FILE_NAME
    temp_path = checkpoint_path.with_suffix(".tmp")
    temp_path.write_text(payload, encoding="utf-8")
    temp_path.replace(checkpoint_path)
    if not finalized:
        return checkpoint_path

    snapshots_dir = output_dir / SNAPSHOTS_DIR_NAME
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    partial_path = snapshots_dir / f"{_timestamp()}-partial{SNAPSHOT_EXTENSION}"
    partial_temp = partial_path.with_suffix(".tmp")
    partial_temp.write_text(payload, encoding="utf-8")
    partial_temp.replace(partial_path)
    return partial_path


def load_snapshot(path: Path) -> list[PageData]:
    raw_pages = json.loads(path.read_text(encoding="utf-8"))
    return [_page_from_dict(item) for item in raw_pages]


def latest_snapshot(output_dir: Path) -> Path | None:
    snapshots_dir = output_dir / SNAPSHOTS_DIR_NAME
    if not snapshots_dir.is_dir():
        return None
    snapshots = sorted(
        path
        for path in snapshots_dir.glob(f"*{SNAPSHOT_EXTENSION}")
        if not path.stem.endswith("-partial")
    )
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
        a11y_issues=tuple(str(item) for item in data.get("a11y_issues", ())),
        # 以下は Layer 2 で追加されたフィールド（旧スナップショットは空で復元）
        page_states=tuple(_page_state_from_dict(item) for item in data.get("page_states", ())),
        validation_observations=tuple(
            _validation_observation_from_dict(item)
            for item in data.get("validation_observations", ())
        ),
        spa_transitions=tuple(
            _spa_transition_from_dict(item) for item in data.get("spa_transitions", ())
        ),
        http_status=int(data.get("http_status", 0)),
        console_errors=tuple(str(item) for item in data.get("console_errors", ())),
        mixed_content=tuple(str(item) for item in data.get("mixed_content", ())),
    )


def _page_state_from_dict(data: dict[str, Any]) -> Any:
    from crawler.page_crawler import PageState

    return PageState(
        state_id=str(data.get("state_id", "")),
        trigger_selector=str(data.get("trigger_selector", "")),
        kind=str(data.get("kind", "")),
        description=str(data.get("description", "")),
    )


def _validation_observation_from_dict(data: dict[str, Any]) -> Any:
    from crawler.page_crawler import ValidationObservation, evidence_from_dict

    return ValidationObservation(
        field_name=str(data.get("field_name", "")),
        message=str(data.get("message", "")),
        evidence=evidence_from_dict(data.get("evidence")),
        confidence=_to_float(data.get("confidence"), default=1.0),
    )


def _spa_transition_from_dict(data: dict[str, Any]) -> Any:
    from crawler.page_crawler import SpaTransition

    return SpaTransition(
        from_url=str(data.get("from_url", "")),
        to_url=str(data.get("to_url", "")),
        kind=str(data.get("kind", "")),
    )


def _form_from_dict(data: dict[str, Any]) -> FormData:
    from crawler.page_crawler import FormData

    return FormData(
        action=str(data.get("action", "")),
        method=str(data.get("method", "")),
        fields=tuple(_field_from_dict(item) for item in data.get("fields", ())),
    )


def _field_from_dict(data: dict[str, Any]) -> FieldData:
    from crawler.page_crawler import FieldData, evidence_from_dict

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
        aria_label=str(data.get("aria_label", "")),
        aria_required=bool(data.get("aria_required", False)),
        role=str(data.get("role", "")),
        has_visible_label=bool(data.get("has_visible_label", False)),
        # 旧スナップショット（evidence/confidence なし）とも後方互換
        evidence=evidence_from_dict(data.get("evidence")),
        confidence=_to_float(data.get("confidence"), default=1.0),
    )


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
