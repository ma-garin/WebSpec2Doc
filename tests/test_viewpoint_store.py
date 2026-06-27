from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from web.services.viewpoint_store import (
    ConflictError,
    ImmutableVersionError,
    ViewpointStore,
    ViewpointStoreError,
    rule_matches,
    validate_rule,
)


@pytest.fixture()
def store(tmp_path: Path) -> ViewpointStore:
    seed = tmp_path / "seed.csv"
    seed.write_text(
        "summary_type,name,count\n"
        "category_l2,必須項目の未入力,1\n"
        "category_l2,境界値の入力,1\n",
        encoding="utf-8",
    )
    result = ViewpointStore(tmp_path / "viewpoints.db", seed)
    result.initialize()
    return result


def test_initial_csv_import_is_idempotent(store: ViewpointStore) -> None:
    first = store.list_sets()
    store.initialize()
    reopened = ViewpointStore(store.db_path, store.seed_csv)
    reopened.initialize()

    assert len(first) == 1
    assert len(reopened.list_sets()) == 1
    assert reopened.list_sets()[0]["item_count"] == 2


def test_migration_creates_backup(tmp_path: Path) -> None:
    db = tmp_path / "viewpoints.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE legacy (id INTEGER)")
        conn.execute("INSERT INTO legacy VALUES (1)")
    seed = tmp_path / "seed.csv"
    seed.write_text("summary_type,name,count\ncategory_l2,観点,1\n", encoding="utf-8")

    ViewpointStore(db, seed).initialize()

    assert list(tmp_path.glob("viewpoints.db.bak-*"))


def test_published_version_is_immutable_and_edit_creates_next_draft(
    store: ViewpointStore,
) -> None:
    standard = store.list_sets()[0]
    published = store.get_version(standard["id"], status="published")

    with pytest.raises(ImmutableVersionError):
        store.create_item(
            standard["id"],
            {"name": "追加", "category": "機能", "automation": "manual"},
            version_number=published["version_number"],
        )

    draft = store.ensure_draft(standard["id"])
    assert draft["version_number"] == published["version_number"] + 1
    assert len(store.list_items(standard["id"], draft["version_number"])) == 2


def test_optimistic_lock_returns_current_and_diff(store: ViewpointStore) -> None:
    standard = store.list_sets()[0]
    draft = store.ensure_draft(standard["id"])
    item = store.list_items(standard["id"], draft["version_number"], resolved=False)[0]
    updated = store.update_item(
        item["id"], item | {"purpose": "更新", "revision": item["revision"]}
    )

    with pytest.raises(ConflictError) as exc_info:
        store.update_item(item["id"], item | {"purpose": "競合", "revision": item["revision"]})

    assert exc_info.value.details["current"]["revision"] == updated["revision"]
    assert "purpose" in exc_info.value.details["diff"]


def test_publish_diff_and_rollback_create_new_versions(store: ViewpointStore) -> None:
    standard = store.list_sets()[0]
    draft = store.ensure_draft(standard["id"])
    store.create_item(
        standard["id"],
        {
            "name": "二重送信防止",
            "category": "フォーム",
            "purpose": "重複登録を防ぐ",
            "recommended_checks": "送信ボタンを連続操作する",
            "risk_weight": 4,
            "automation": "semi_automated",
        },
        version_number=draft["version_number"],
    )
    draft = store.get_version(standard["id"], draft["version_number"])
    published = store.publish(
        standard["id"], draft["version_number"], revision=draft["revision"], change_reason="追加"
    )
    diff = store.version_diff(standard["id"], 1, published["version_number"])

    rolled_back = store.rollback(standard["id"], 1, "初版へ戻す")

    assert len(diff["added"]) == 1
    assert rolled_back["version_number"] == published["version_number"] + 1
    assert rolled_back["status"] == "published"
    assert len(store.list_items(standard["id"], rolled_back["version_number"])) == 2


def test_inheritance_overrides_by_persistent_key(store: ViewpointStore) -> None:
    parent = store.list_sets()[0]
    child = store.create_set({"name": "EC向け", "parent_set_id": parent["id"]})
    draft = store.ensure_draft(child["id"])
    inherited = store.list_items(child["id"], draft["version_number"])[0]
    store.create_item(
        child["id"],
        {
            "persistent_key": inherited["persistent_key"],
            "name": inherited["name"],
            "category": "EC",
            "purpose": "子セットで上書き",
            "automation": "automated",
        },
        version_number=draft["version_number"],
    )

    resolved = store.list_items(child["id"], draft["version_number"])

    assert len(resolved) == 2
    assert (
        next(item for item in resolved if item["persistent_key"] == inherited["persistent_key"])[
            "category"
        ]
        == "EC"
    )


def test_rules_are_allowlisted_and_assignments_drive_auto_selection(store: ViewpointStore) -> None:
    standard = store.list_sets()[0]
    other = store.create_set({"name": "管理画面向け"})
    draft = store.get_version(other["id"], status="draft")
    store.create_item(
        other["id"],
        {"name": "権限確認", "category": "認可", "automation": "manual"},
        version_number=draft["version_number"],
    )
    draft = store.get_version(other["id"], draft["version_number"])
    store.publish(
        other["id"], draft["version_number"], revision=draft["revision"], change_reason="初版"
    )
    store.create_assignment(
        other["id"],
        {
            "rule": {"condition": {"field": "url", "operator": "contains", "value": "/admin"}},
            "priority": 200,
        },
    )

    snapshot = store.select_snapshot({"url": "https://example.com/admin/users"})

    assert snapshot["set_id"] == other["id"]
    assert "適用ルール" in snapshot["selection_reason"]
    assert rule_matches(
        {"all": [{"condition": {"field": "url", "operator": "contains", "value": "admin"}}]},
        {"url": "https://example.com/admin"},
    )
    with pytest.raises(ViewpointStoreError):
        validate_rule({"condition": {"field": "__code__", "operator": "eval", "value": "1"}})
    assert standard["is_default"] == 1


def test_snapshot_is_fixed_and_report_rules_filter_items(store: ViewpointStore) -> None:
    standard = store.list_sets()[0]
    draft = store.ensure_draft(standard["id"])
    store.create_item(
        standard["id"],
        {
            "name": "必須入力",
            "category": "フォーム",
            "automation": "automated",
            "trigger_rule": {
                "condition": {"field": "input_type", "operator": "eq", "value": "email"}
            },
        },
        version_number=draft["version_number"],
    )
    draft = store.get_version(standard["id"], draft["version_number"])
    store.publish(
        standard["id"], draft["version_number"], revision=draft["revision"], change_reason="条件"
    )
    snapshot = store.select_snapshot({"url": "https://example.com"})
    report = {
        "screens": [
            {
                "url": "https://example.com/form",
                "title": "入力",
                "forms": [{"method": "post", "fields": [{"field_type": "email"}]}],
            }
        ]
    }

    applied = store.apply_snapshot_to_report(snapshot, report)

    assert any(item["name"] == "必須入力" for item in applied["items"])
    assert len(applied["checksum"]) == 64


def test_csv_export_and_import(store: ViewpointStore) -> None:
    standard = store.list_sets()[0]
    exported = store.export_csv(standard["id"], 1)
    target = store.create_set({"name": "取込先"})

    result = store.import_csv(target["id"], exported)

    assert result["imported"] == 2
    assert len(store.list_items(target["id"], result["version"])) == 2


def test_bulk_update_rolls_back_all_items_when_one_target_is_immutable(
    store: ViewpointStore,
) -> None:
    standard = store.list_sets()[0]
    draft = store.ensure_draft(standard["id"])
    draft_item = store.list_items(standard["id"], draft["version_number"], resolved=False)[0]
    published = store.get_version(standard["id"], status="published")
    published_item = store.list_items(standard["id"], published["version_number"], resolved=False)[
        0
    ]

    with pytest.raises(ImmutableVersionError):
        store.bulk_update([draft_item["id"], published_item["id"]], {"category": "変更後"})

    reloaded = store.get_item(draft_item["id"])
    assert reloaded["category"] == draft_item["category"]
    assert reloaded["revision"] == draft_item["revision"]


def test_csv_import_rolls_back_all_rows_on_validation_error(
    store: ViewpointStore,
) -> None:
    target = store.create_set({"name": "原子取込先"})
    draft = store.get_version(target["id"], status="draft")
    before = store.list_items(target["id"], draft["version_number"], resolved=False)
    csv_text = (
        "persistent_key,name,category,risk_weight,automation\n"
        "valid-key,正常な観点,機能,3,manual\n"
        "invalid-key,不正な観点,機能,99,manual\n"
    )

    with pytest.raises(ViewpointStoreError, match="1件も取り込みませんでした"):
        store.import_csv(target["id"], csv_text)

    after = store.list_items(target["id"], draft["version_number"], resolved=False)
    assert after == before
