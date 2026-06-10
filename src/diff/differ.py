from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crawler.page_crawler import ApiEndpoint, FieldData, PageData

CHANGE_ADDED = "added"
CHANGE_REMOVED = "removed"
CHANGE_MODIFIED = "modified"

SEVERITY_BREAKING = "breaking"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


@dataclass(frozen=True)
class FieldChange:
    page_url: str
    field_name: str
    change_type: str
    before: FieldData | None
    after: FieldData | None


@dataclass(frozen=True)
class PageChange:
    url: str
    title: str
    change_type: str


@dataclass(frozen=True)
class LinkChange:
    page_url: str
    link: str
    change_type: str


@dataclass(frozen=True)
class TitleChange:
    url: str
    before: str
    after: str


@dataclass(frozen=True)
class FieldAttributeDiff:
    """フィールドの属性レベルの差分（FieldChange の補完情報）。"""

    page_url: str
    field_name: str
    attribute: str  # "maxlength" / "pattern" / "options" / "required" / "field_type" など
    before: str
    after: str
    severity: str  # SEVERITY_BREAKING / SEVERITY_WARNING / SEVERITY_INFO


@dataclass(frozen=True)
class ApiChange:
    """API エンドポイントの追加・削除・変更。"""

    page_url: str
    method: str
    path: str
    change_type: str  # CHANGE_ADDED / CHANGE_REMOVED / CHANGE_MODIFIED


@dataclass(frozen=True)
class DiffResult:
    added_pages: tuple[PageChange, ...]
    removed_pages: tuple[PageChange, ...]
    field_changes: tuple[FieldChange, ...]
    link_changes: tuple[LinkChange, ...]
    title_changes: tuple[TitleChange, ...]
    has_changes: bool
    attribute_diffs: tuple[FieldAttributeDiff, ...] = ()
    api_changes: tuple[ApiChange, ...] = ()


def compute_diff(old: list[PageData], new: list[PageData]) -> DiffResult:
    old_pages = _pages_by_url(old)
    new_pages = _pages_by_url(new)
    added_pages = _page_changes(new_pages, old_pages, CHANGE_ADDED)
    removed_pages = _page_changes(old_pages, new_pages, CHANGE_REMOVED)
    common_urls = tuple(url for url in old_pages if url in new_pages)
    field_changes = _field_changes(common_urls, old_pages, new_pages)
    link_changes = _link_changes(common_urls, old_pages, new_pages)
    title_changes = _title_changes(common_urls, old_pages, new_pages)
    attribute_diffs = _collect_attribute_diffs(common_urls, old_pages, new_pages)
    api_changes = _api_changes(common_urls, old_pages, new_pages)
    has_changes = any((added_pages, removed_pages, field_changes, link_changes, title_changes))
    return DiffResult(
        added_pages=added_pages,
        removed_pages=removed_pages,
        field_changes=field_changes,
        link_changes=link_changes,
        title_changes=title_changes,
        has_changes=has_changes,
        attribute_diffs=attribute_diffs,
        api_changes=api_changes,
    )


def _pages_by_url(pages: list[PageData]) -> dict[str, PageData]:
    return {page.url: page for page in pages}


def _page_changes(
    base: dict[str, PageData],
    other: dict[str, PageData],
    change_type: str,
) -> tuple[PageChange, ...]:
    return tuple(
        PageChange(url=url, title=base[url].title, change_type=change_type)
        for url in base
        if url not in other
    )


def _field_changes(
    urls: tuple[str, ...],
    old_pages: dict[str, PageData],
    new_pages: dict[str, PageData],
) -> tuple[FieldChange, ...]:
    changes: list[FieldChange] = []
    for url in urls:
        old_fields = _fields_by_name(old_pages[url])
        new_fields = _fields_by_name(new_pages[url])
        changes.extend(_added_fields(url, old_fields, new_fields))
        changes.extend(_removed_fields(url, old_fields, new_fields))
        changes.extend(_modified_fields(url, old_fields, new_fields))
    return tuple(changes)


def _fields_by_name(page: PageData) -> dict[str, FieldData]:
    return {field.name: field for form in page.forms for field in form.fields}


def _added_fields(
    page_url: str,
    old_fields: dict[str, FieldData],
    new_fields: dict[str, FieldData],
) -> tuple[FieldChange, ...]:
    return tuple(
        FieldChange(page_url, name, CHANGE_ADDED, None, new_fields[name])
        for name in new_fields
        if name not in old_fields
    )


def _removed_fields(
    page_url: str,
    old_fields: dict[str, FieldData],
    new_fields: dict[str, FieldData],
) -> tuple[FieldChange, ...]:
    return tuple(
        FieldChange(page_url, name, CHANGE_REMOVED, old_fields[name], None)
        for name in old_fields
        if name not in new_fields
    )


def _modified_fields(
    page_url: str,
    old_fields: dict[str, FieldData],
    new_fields: dict[str, FieldData],
) -> tuple[FieldChange, ...]:
    return tuple(
        FieldChange(page_url, name, CHANGE_MODIFIED, old_fields[name], new_fields[name])
        for name in old_fields
        if name in new_fields and _field_modified(old_fields[name], new_fields[name])
    )


def _field_modified(before: FieldData, after: FieldData) -> bool:
    return (
        before.field_type != after.field_type
        or before.required != after.required
        or before.placeholder != after.placeholder
        or before.maxlength != after.maxlength
        or before.minlength != after.minlength
        or before.pattern != after.pattern
        or before.options != after.options
        or before.min_value != after.min_value
        or before.max_value != after.max_value
    )


# 属性ごとの重大度マッピング
_ATTRIBUTE_SEVERITY: dict[str, str] = {
    "field_type": SEVERITY_BREAKING,
    "required": SEVERITY_BREAKING,
    "maxlength": SEVERITY_WARNING,
    "pattern": SEVERITY_WARNING,
    "options": SEVERITY_WARNING,
    "placeholder": SEVERITY_INFO,
    "min_value": SEVERITY_INFO,
    "max_value": SEVERITY_INFO,
    "minlength": SEVERITY_INFO,
}

# 比較対象の属性名一覧（_ATTRIBUTE_SEVERITY の定義順に処理）
_COMPARED_ATTRIBUTES = tuple(_ATTRIBUTE_SEVERITY.keys())


def _attribute_diffs_for_field(
    page_url: str,
    field_name: str,
    before: FieldData,
    after: FieldData,
) -> list[FieldAttributeDiff]:
    diffs: list[FieldAttributeDiff] = []
    for attr in _COMPARED_ATTRIBUTES:
        b_val = getattr(before, attr)
        a_val = getattr(after, attr)
        if b_val != a_val:
            diffs.append(
                FieldAttributeDiff(
                    page_url=page_url,
                    field_name=field_name,
                    attribute=attr,
                    before=str(b_val),
                    after=str(a_val),
                    severity=_ATTRIBUTE_SEVERITY[attr],
                )
            )
    return diffs


def _collect_attribute_diffs(
    urls: tuple[str, ...],
    old_pages: dict[str, PageData],
    new_pages: dict[str, PageData],
) -> tuple[FieldAttributeDiff, ...]:
    diffs: list[FieldAttributeDiff] = []
    for url in urls:
        old_fields = _fields_by_name(old_pages[url])
        new_fields = _fields_by_name(new_pages[url])
        for name in old_fields:
            if name in new_fields and _field_modified(old_fields[name], new_fields[name]):
                diffs.extend(
                    _attribute_diffs_for_field(url, name, old_fields[name], new_fields[name])
                )
    return tuple(diffs)


def _api_changes(
    urls: tuple[str, ...],
    old_pages: dict[str, PageData],
    new_pages: dict[str, PageData],
) -> tuple[ApiChange, ...]:
    changes: list[ApiChange] = []
    for url in urls:
        old_apis = _api_endpoints_by_path(old_pages[url])
        new_apis = _api_endpoints_by_path(new_pages[url])
        changes.extend(_added_apis(url, old_apis, new_apis))
        changes.extend(_removed_apis(url, old_apis, new_apis))
        changes.extend(_modified_apis(url, old_apis, new_apis))
    return tuple(changes)


def _api_endpoints_by_path(page: PageData) -> dict[str, ApiEndpoint]:
    # 同一 path が複数あれば最後のものを使う（実運用上まれ）
    return {ep.path: ep for ep in page.api_calls}


def _added_apis(
    page_url: str,
    old_apis: dict[str, ApiEndpoint],
    new_apis: dict[str, ApiEndpoint],
) -> list[ApiChange]:
    return [
        ApiChange(page_url=page_url, method=new_apis[path].method, path=path, change_type=CHANGE_ADDED)
        for path in new_apis
        if path not in old_apis
    ]


def _removed_apis(
    page_url: str,
    old_apis: dict[str, ApiEndpoint],
    new_apis: dict[str, ApiEndpoint],
) -> list[ApiChange]:
    return [
        ApiChange(page_url=page_url, method=old_apis[path].method, path=path, change_type=CHANGE_REMOVED)
        for path in old_apis
        if path not in new_apis
    ]


def _modified_apis(
    page_url: str,
    old_apis: dict[str, ApiEndpoint],
    new_apis: dict[str, ApiEndpoint],
) -> list[ApiChange]:
    return [
        ApiChange(page_url=page_url, method=new_apis[path].method, path=path, change_type=CHANGE_MODIFIED)
        for path in old_apis
        if path in new_apis and _api_modified(old_apis[path], new_apis[path])
    ]


def _api_modified(before: ApiEndpoint, after: ApiEndpoint) -> bool:
    return before.method != after.method or before.status_code != after.status_code


def _link_changes(
    urls: tuple[str, ...],
    old_pages: dict[str, PageData],
    new_pages: dict[str, PageData],
) -> tuple[LinkChange, ...]:
    changes: list[LinkChange] = []
    for url in urls:
        old_links = set(old_pages[url].links)
        new_links = set(new_pages[url].links)
        changes.extend(
            LinkChange(url, link, CHANGE_ADDED) for link in sorted(new_links - old_links)
        )
        changes.extend(
            LinkChange(url, link, CHANGE_REMOVED) for link in sorted(old_links - new_links)
        )
    return tuple(changes)


def _title_changes(
    urls: tuple[str, ...],
    old_pages: dict[str, PageData],
    new_pages: dict[str, PageData],
) -> tuple[TitleChange, ...]:
    return tuple(
        TitleChange(url=url, before=old_pages[url].title, after=new_pages[url].title)
        for url in urls
        if old_pages[url].title != new_pages[url].title
    )
