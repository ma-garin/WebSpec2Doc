from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crawler.page_crawler import FieldData, PageData

CHANGE_ADDED = "added"
CHANGE_REMOVED = "removed"
CHANGE_MODIFIED = "modified"


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
class DiffResult:
    added_pages: tuple[PageChange, ...]
    removed_pages: tuple[PageChange, ...]
    field_changes: tuple[FieldChange, ...]
    link_changes: tuple[LinkChange, ...]
    title_changes: tuple[TitleChange, ...]
    has_changes: bool


def compute_diff(old: list[PageData], new: list[PageData]) -> DiffResult:
    old_pages = _pages_by_url(old)
    new_pages = _pages_by_url(new)
    added_pages = _page_changes(new_pages, old_pages, CHANGE_ADDED)
    removed_pages = _page_changes(old_pages, new_pages, CHANGE_REMOVED)
    common_urls = tuple(url for url in old_pages if url in new_pages)
    field_changes = _field_changes(common_urls, old_pages, new_pages)
    link_changes = _link_changes(common_urls, old_pages, new_pages)
    title_changes = _title_changes(common_urls, old_pages, new_pages)
    has_changes = any((added_pages, removed_pages, field_changes, link_changes, title_changes))
    return DiffResult(
        added_pages=added_pages,
        removed_pages=removed_pages,
        field_changes=field_changes,
        link_changes=link_changes,
        title_changes=title_changes,
        has_changes=has_changes,
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
    )


def _link_changes(
    urls: tuple[str, ...],
    old_pages: dict[str, PageData],
    new_pages: dict[str, PageData],
) -> tuple[LinkChange, ...]:
    changes: list[LinkChange] = []
    for url in urls:
        old_links = set(old_pages[url].links)
        new_links = set(new_pages[url].links)
        changes.extend(LinkChange(url, link, CHANGE_ADDED) for link in sorted(new_links - old_links))
        changes.extend(LinkChange(url, link, CHANGE_REMOVED) for link in sorted(old_links - new_links))
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
