from __future__ import annotations

import csv
import io
import sqlite3
import uuid
from typing import Any

from web.services.viewpoint_store import (
    AUTOMATION_VALUES,
    ConflictError,
    ImmutableVersionError,
    NotFoundError,
    ViewpointStoreBase,
    ViewpointStoreError,
    _canonical,
    _checksum,
    _json,
    _key_for,
    _now,
    rule_matches,
    validate_rule,
)


class ViewpointStoreOperations(ViewpointStoreBase):
    def bulk_update(self, item_ids: list[str], changes: dict[str, Any]) -> list[dict[str, Any]]:
        allowed = {"enabled", "category", "risk_weight", "automation", "tags"}
        updates = {key: value for key, value in changes.items() if key in allowed}
        if not item_ids or not updates:
            raise ViewpointStoreError("対象観点と変更内容を指定してください。")
        unique_ids = list(dict.fromkeys(item_ids))
        now = _now()
        version_updates: dict[str, int] = {}
        with self._transaction() as conn:
            for item_id in unique_ids:
                row = conn.execute(
                    """SELECT i.*,v.id AS joined_version_id,v.set_id,v.version_number,
                              v.status AS version_status
                       FROM viewpoint_items i
                       JOIN viewpoint_versions v ON v.id=i.version_id
                       WHERE i.id=?""",
                    (item_id,),
                ).fetchone()
                if row is None or row["deleted_at"]:
                    raise NotFoundError("一括更新対象の観点が見つかりません。")
                if row["version_status"] != "draft":
                    raise ImmutableVersionError(
                        "公開済み版を含むため一括更新を中止しました。次版の下書きを作成してください。"
                    )
                current = self._item_dict(row, source_set_id=row["set_id"], inherited=False)
                item = self._normalize_item(
                    current | updates, persistent_key=current["persistent_key"]
                )
                conn.execute(
                    """UPDATE viewpoint_items SET name=?,category=?,purpose=?,trigger_rule=?,
                       recommended_checks=?,risk_weight=?,automation=?,standards=?,tags=?,enabled=?,
                       revision=revision+1,updated_at=? WHERE id=?""",
                    (
                        item["name"],
                        item["category"],
                        item["purpose"],
                        _canonical(item["trigger_rule"]),
                        item["recommended_checks"],
                        item["risk_weight"],
                        item["automation"],
                        item["standards"],
                        _canonical(item["tags"]),
                        int(item["enabled"]),
                        now,
                        item_id,
                    ),
                )
                version_id = str(row["joined_version_id"])
                version_updates[version_id] = version_updates.get(version_id, 0) + 1
            for version_id, increment in version_updates.items():
                conn.execute(
                    """UPDATE viewpoint_versions SET revision=revision+?,updated_at=?
                       WHERE id=?""",
                    (increment, now, version_id),
                )
        return [self.get_item(item_id) for item_id in unique_ids]

    def publish(
        self, set_id: str, version_number: int, *, revision: int | None, change_reason: str
    ) -> dict[str, Any]:
        version = self.get_version(set_id, version_number)
        self._assert_mutable(version)
        if revision is not None and int(revision) != int(version["revision"]):
            raise ConflictError(
                "公開対象が他の操作で更新されています。",
                details={"current": version, "submitted_revision": revision},
            )
        items = self.list_items(set_id, version_number, resolved=True)
        active = [item for item in items if item["enabled"] and not item["deleted_at"]]
        if not active:
            raise ViewpointStoreError("空の観点セットは公開できません。")
        duplicate_names = self._duplicate_names(active)
        if duplicate_names:
            raise ViewpointStoreError("同名の観点があります。", details=duplicate_names)
        for item in active:
            validate_rule(item["trigger_rule"])
        checksum = self._items_checksum(active)
        now = _now()
        with self._transaction() as conn:
            self._assert_no_cycle(conn, set_id)
            assignment_rows = conn.execute(
                "SELECT rule FROM viewpoint_assignments WHERE set_id=? AND deleted_at IS NULL AND enabled=1",
                (set_id,),
            ).fetchall()
            for row in assignment_rows:
                validate_rule(_json(row["rule"], {}))
            conn.execute(
                "UPDATE viewpoint_versions SET status='archived',updated_at=? WHERE set_id=? AND status='published'",
                (now, set_id),
            )
            conn.execute(
                """UPDATE viewpoint_versions SET status='published',change_reason=?,checksum=?,published_at=?,
                   revision=revision+1,updated_at=? WHERE id=?""",
                (change_reason.strip(), checksum, now, now, version["id"]),
            )
        return self.get_version(set_id, version_number)

    def rollback(self, set_id: str, source_version_number: int, reason: str) -> dict[str, Any]:
        source = self.get_version(set_id, source_version_number)
        if source["status"] not in {"published", "archived"}:
            raise ViewpointStoreError("公開履歴のある版だけをロールバックできます。")
        now = _now()
        with self._transaction() as conn:
            if conn.execute(
                "SELECT 1 FROM viewpoint_versions WHERE set_id=? AND status='draft'", (set_id,)
            ).fetchone():
                raise ConflictError("下書きが存在するため、先に公開または破棄してください。")
            next_number = int(
                conn.execute(
                    "SELECT MAX(version_number)+1 FROM viewpoint_versions WHERE set_id=?", (set_id,)
                ).fetchone()[0]
            )
            version_id = uuid.uuid4().hex
            conn.execute(
                """INSERT INTO viewpoint_versions
                   (id,set_id,version_number,status,change_reason,checksum,based_on_version_id,published_at,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    version_id,
                    set_id,
                    next_number,
                    "published",
                    reason.strip() or f"v{source_version_number} へロールバック",
                    source["checksum"],
                    source["id"],
                    now,
                    now,
                    now,
                ),
            )
            conn.execute(
                "UPDATE viewpoint_versions SET status='archived',updated_at=? WHERE set_id=? AND status='published' AND id<>?",
                (now, set_id, version_id),
            )
            conn.execute(
                """INSERT INTO viewpoint_items
                   (id,version_id,persistent_key,name,category,purpose,trigger_rule,recommended_checks,risk_weight,
                    automation,standards,tags,enabled,revision,deleted_at,created_at,updated_at)
                   SELECT lower(hex(randomblob(16))), ?, persistent_key,name,category,purpose,trigger_rule,
                    recommended_checks,risk_weight,automation,standards,tags,enabled,1,deleted_at,?,?
                   FROM viewpoint_items WHERE version_id=?""",
                (version_id, now, now, source["id"]),
            )
        return self.get_version(set_id, next_number)

    def version_diff(
        self, set_id: str, from_version: int, to_version: int
    ) -> dict[str, list[dict[str, Any]]]:
        before = {i["persistent_key"]: i for i in self.list_items(set_id, from_version)}
        after = {i["persistent_key"]: i for i in self.list_items(set_id, to_version)}
        added = [after[key] for key in after.keys() - before.keys()]
        removed = [before[key] for key in before.keys() - after.keys()]
        changed = []
        for key in before.keys() & after.keys():
            left = self._checksum_item(before[key])
            right = self._checksum_item(after[key])
            if left != right:
                changed.append({"before": before[key], "after": after[key]})
        return {"added": added, "removed": removed, "changed": changed}

    def list_assignments(self, set_id: str) -> list[dict[str, Any]]:
        self.get_set(set_id)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM viewpoint_assignments WHERE set_id=? AND deleted_at IS NULL ORDER BY priority DESC",
                (set_id,),
            ).fetchall()
        return [self._assignment_dict(row) for row in rows]

    def create_assignment(self, set_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.get_set(set_id)
        rule = validate_rule(payload.get("rule"))
        assignment_id = uuid.uuid4().hex
        now = _now()
        with self._transaction() as conn:
            conn.execute(
                """INSERT INTO viewpoint_assignments
                   (id,set_id,rule,priority,enabled,created_at,updated_at) VALUES (?,?,?,?,?,?,?)""",
                (
                    assignment_id,
                    set_id,
                    _canonical(rule),
                    int(payload.get("priority", 0)),
                    int(bool(payload.get("enabled", True))),
                    now,
                    now,
                ),
            )
        return self.get_assignment(assignment_id)

    def get_assignment(self, assignment_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM viewpoint_assignments WHERE id=? AND deleted_at IS NULL",
                (assignment_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("適用ルールが見つかりません。")
        return self._assignment_dict(row)

    def update_assignment(self, assignment_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_assignment(assignment_id)
        self._check_revision(current, payload)
        rule = validate_rule(payload.get("rule", current["rule"]))
        with self._transaction() as conn:
            conn.execute(
                """UPDATE viewpoint_assignments SET rule=?,priority=?,enabled=?,revision=revision+1,updated_at=?
                   WHERE id=?""",
                (
                    _canonical(rule),
                    int(payload.get("priority", current["priority"])),
                    int(bool(payload.get("enabled", current["enabled"]))),
                    _now(),
                    assignment_id,
                ),
            )
        return self.get_assignment(assignment_id)

    def delete_assignment(self, assignment_id: str) -> None:
        self.get_assignment(assignment_id)
        with self._transaction() as conn:
            conn.execute(
                "UPDATE viewpoint_assignments SET deleted_at=?,revision=revision+1,updated_at=? WHERE id=?",
                (_now(), _now(), assignment_id),
            )

    def select_snapshot(
        self,
        context: dict[str, Any],
        *,
        set_id: str | None = None,
        version_number: int | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        reason = "利用者が公開版を指定"
        if set_id:
            selected_set = self.get_set(set_id)
        else:
            selected_set = self._auto_select_set(context)
            set_id = selected_set["id"]
            reason = selected_set.pop("_selection_reason", "既定公開版を自動選択")
        if set_id is None:
            raise ViewpointStoreError("観点セットを選択できませんでした。")
        version = self.get_version(set_id, version_number, status="published")
        items = [
            item
            for item in self.list_items(set_id, version["version_number"], resolved=True)
            if item["enabled"] and not item["deleted_at"]
        ]
        if not items:
            raise ConflictError("適用できる公開済み観点が0件です。既定公開版へ切り替えてください。")
        snapshot_checksum = self._items_checksum(items)
        return {
            "set_id": set_id,
            "set_name": selected_set["name"],
            "version": version["version_number"],
            "version_id": version["id"],
            "checksum": snapshot_checksum,
            "version_checksum": version["checksum"],
            "selection_reason": reason,
            "viewpoint_count": len(items),
            "locked_at": _now(),
            "items": items,
        }

    def _auto_select_set(self, context: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT a.*,s.name,s.is_default,s.priority AS set_priority
                   FROM viewpoint_assignments a JOIN viewpoint_sets s ON s.id=a.set_id
                   WHERE a.deleted_at IS NULL AND a.enabled=1 AND s.deleted_at IS NULL
                   ORDER BY a.priority DESC,s.priority DESC"""
            ).fetchall()
            for row in rows:
                if rule_matches(_json(row["rule"], {}), context):
                    result = self.get_set(row["set_id"])
                    result["_selection_reason"] = "URL・業種・画面条件に一致する適用ルール"
                    return result
            row = conn.execute(
                """SELECT s.* FROM viewpoint_sets s
                   WHERE s.deleted_at IS NULL AND s.is_default=1
                   AND EXISTS(SELECT 1 FROM viewpoint_versions v WHERE v.set_id=s.id AND v.status='published')
                   ORDER BY s.priority DESC LIMIT 1"""
            ).fetchone()
        if row is None:
            raise ConflictError("既定の公開済み観点セットがありません。")
        result = dict(row)
        result["_selection_reason"] = "既定公開版を自動選択"
        return result

    def apply_snapshot_to_report(
        self, snapshot: dict[str, Any], report: dict[str, Any]
    ) -> dict[str, Any]:
        contexts = self._report_contexts(report)
        selected = []
        for item in snapshot.get("items", []):
            rule = item.get("trigger_rule") or {}
            matched = not rule or any(rule_matches(rule, context) for context in contexts)
            if matched:
                selected.append(item)
        if not selected:
            raise ConflictError(
                "画面分類後に適用観点が0件になりました。既定公開版へ切り替えてください。"
            )
        result = {key: value for key, value in snapshot.items() if key != "items"}
        result["viewpoint_count"] = len(selected)
        result["items"] = selected
        result["applied_at"] = _now()
        result["adoption_results"] = [
            {"persistent_key": item["persistent_key"], "name": item["name"], "adopted": True}
            for item in selected
        ]
        return result

    def _report_contexts(self, report: dict[str, Any]) -> list[dict[str, Any]]:
        contexts: list[dict[str, Any]] = []
        screens = report.get("screens", []) if isinstance(report.get("screens"), list) else []
        for screen in screens:
            if not isinstance(screen, dict):
                continue
            forms = screen.get("forms", []) if isinstance(screen.get("forms"), list) else []
            fields = [
                field
                for form in forms
                if isinstance(form, dict)
                for field in (
                    form.get("fields", []) if isinstance(form.get("fields"), list) else []
                )
                if isinstance(field, dict)
            ]
            title = str(screen.get("title", "")).lower()
            screen_type = "form" if forms else "content"
            if any(token in title for token in ("login", "ログイン", "sign in")):
                screen_type = "authentication"
            base = {
                "url": str(screen.get("url", "")),
                "screen_type": screen_type,
                "has_forms": bool(forms),
                "method": [str(form.get("method", "GET")).upper() for form in forms],
            }
            contexts.append(base)
            for field in fields:
                contexts.append(
                    base | {"input_type": str(field.get("field_type") or field.get("type") or "")}
                )
        return contexts or [{"url": "", "screen_type": "unknown", "has_forms": False}]

    def list_proposals(self, set_id: str) -> list[dict[str, Any]]:
        self.get_set(set_id)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM viewpoint_proposals WHERE set_id=? ORDER BY created_at DESC",
                (set_id,),
            ).fetchall()
        return [self._proposal_dict(row) for row in rows]

    def save_proposals(
        self, set_id: str, proposals: list[dict[str, Any]], *, version_id: str | None = None
    ) -> list[dict[str, Any]]:
        existing = self.list_items(set_id)
        existing_by_name = {
            item["name"].strip().lower(): item["persistent_key"] for item in existing
        }
        created_ids: list[str] = []
        now = _now()
        with self._transaction() as conn:
            for raw in proposals[:20]:
                payload = self._normalize_item(raw)
                proposal_id = uuid.uuid4().hex
                duplicate = existing_by_name.get(payload["name"].lower(), "")
                confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.5))))
                conn.execute(
                    """INSERT INTO viewpoint_proposals
                       (id,set_id,version_id,payload,rationale,confidence,duplicate_key,status,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        proposal_id,
                        set_id,
                        version_id,
                        _canonical(payload),
                        str(raw.get("rationale", "")).strip(),
                        confidence,
                        duplicate,
                        "pending",
                        now,
                        now,
                    ),
                )
                created_ids.append(proposal_id)
        return [self.get_proposal(proposal_id) for proposal_id in created_ids]

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM viewpoint_proposals WHERE id=?", (proposal_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("AI提案が見つかりません。")
        return self._proposal_dict(row)

    def decide_proposal(self, proposal_id: str, decision: str) -> dict[str, Any]:
        if decision not in {"adopted", "rejected"}:
            raise ViewpointStoreError("提案は adopted または rejected に更新してください。")
        proposal = self.get_proposal(proposal_id)
        self._check_revision(proposal, {"revision": proposal["revision"]})
        item = None
        if decision == "adopted":
            if proposal["duplicate_key"]:
                raise ConflictError("重複候補があるため、内容を確認してから採用してください。")
            item = self.create_item(proposal["set_id"], proposal["payload"])
        with self._transaction() as conn:
            conn.execute(
                "UPDATE viewpoint_proposals SET status=?,revision=revision+1,updated_at=? WHERE id=?",
                (decision, _now(), proposal_id),
            )
        result = self.get_proposal(proposal_id)
        if item:
            result["adopted_item"] = item
        return result

    def export_csv(self, set_id: str, version_number: int | None = None) -> str:
        items = self.list_items(set_id, version_number, resolved=True)
        out = io.StringIO()
        fields = [
            "persistent_key",
            "name",
            "category",
            "purpose",
            "trigger_rule",
            "recommended_checks",
            "risk_weight",
            "automation",
            "standards",
            "tags",
            "enabled",
        ]
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    key: (
                        _canonical(item[key])
                        if key in {"trigger_rule", "tags"}
                        else int(item[key]) if key == "enabled" else item[key]
                    )
                    for key in fields
                }
            )
        return out.getvalue()

    def import_csv(self, set_id: str, text: str) -> dict[str, Any]:
        try:
            rows = list(csv.DictReader(io.StringIO(text.lstrip("\ufeff"))))
        except csv.Error as exc:
            raise ViewpointStoreError(f"CSVを解析できません: {exc}") from exc
        if not rows:
            raise ViewpointStoreError("CSVに観点がありません。")
        self.get_set(set_id)
        normalized = []
        errors = []
        for index, row in enumerate(rows, 2):
            try:
                normalized.append(self._normalize_import_row(row, index=index))
            except ViewpointStoreError as exc:
                errors.append({"row": index, "error": str(exc)})
        if errors:
            raise ViewpointStoreError(
                "CSVに不正な行があるため、1件も取り込みませんでした。", details=errors
            )

        now = _now()
        try:
            with self._transaction() as conn:
                version = conn.execute(
                    "SELECT * FROM viewpoint_versions WHERE set_id=? AND status='draft'",
                    (set_id,),
                ).fetchone()
                if version is None:
                    source = conn.execute(
                        """SELECT * FROM viewpoint_versions WHERE set_id=? AND status='published'
                           ORDER BY version_number DESC LIMIT 1""",
                        (set_id,),
                    ).fetchone()
                    version_number = int(
                        conn.execute(
                            "SELECT COALESCE(MAX(version_number),0)+1 FROM viewpoint_versions WHERE set_id=?",
                            (set_id,),
                        ).fetchone()[0]
                    )
                    version_id = uuid.uuid4().hex
                    conn.execute(
                        """INSERT INTO viewpoint_versions
                           (id,set_id,version_number,status,based_on_version_id,created_at,updated_at)
                           VALUES (?,?,?,?,?,?,?)""",
                        (
                            version_id,
                            set_id,
                            version_number,
                            "draft",
                            source["id"] if source else None,
                            now,
                            now,
                        ),
                    )
                    if source:
                        conn.execute(
                            """INSERT INTO viewpoint_items
                               (id,version_id,persistent_key,name,category,purpose,trigger_rule,recommended_checks,
                                risk_weight,automation,standards,tags,enabled,revision,deleted_at,created_at,updated_at)
                               SELECT lower(hex(randomblob(16))), ?, persistent_key,name,category,purpose,trigger_rule,
                                recommended_checks,risk_weight,automation,standards,tags,enabled,1,deleted_at,?,?
                               FROM viewpoint_items WHERE version_id=?""",
                            (version_id, now, now, source["id"]),
                        )
                else:
                    version_id = str(version["id"])
                    version_number = int(version["version_number"])
                for item in normalized:
                    self._insert_item(conn, version_id, item, now)
                conn.execute(
                    """UPDATE viewpoint_versions SET revision=revision+?,updated_at=?
                       WHERE id=?""",
                    (len(normalized), now, version_id),
                )
        except sqlite3.IntegrityError as exc:
            raise ConflictError(
                "CSV内または既存下書きに同じ永続キーがあるため、1件も取り込みませんでした。"
            ) from exc
        return {"version": version_number, "imported": len(normalized)}

    def _normalize_import_row(self, row: dict[str, Any], *, index: int) -> dict[str, Any]:
        name = str(row.get("name") or "").strip()
        old_category = str(row.get("summary_type") or "").strip()
        category = str(row.get("category") or old_category or "一般").strip()
        tags = _json(row.get("tags"), [])
        if not isinstance(tags, list):
            tags = []
        if old_category and old_category not in tags:
            tags.append(old_category)
        return self._normalize_item(
            {
                "persistent_key": row.get("persistent_key") or _key_for(name, str(index)),
                "name": name,
                "category": category,
                "purpose": row.get("purpose") or f"{name}に関する品質リスクを確認する",
                "trigger_rule": _json(row.get("trigger_rule"), {}),
                "recommended_checks": row.get("recommended_checks") or name,
                "risk_weight": row.get("risk_weight") or 3,
                "automation": row.get("automation") or "manual",
                "standards": row.get("standards") or "ISO/IEC 25010:2023",
                "tags": tags,
                "enabled": str(row.get("enabled", "1")).lower() not in {"0", "false", "off"},
            }
        )

    def _normalize_item(
        self, payload: dict[str, Any], *, persistent_key: str | None = None
    ) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        category = str(payload.get("category", "")).strip()
        if not name or not category:
            raise ViewpointStoreError("観点名とカテゴリは必須です。")
        try:
            risk = int(payload.get("risk_weight", 3))
        except (TypeError, ValueError) as exc:
            raise ViewpointStoreError("リスク重みは1〜5で指定してください。") from exc
        if not 1 <= risk <= 5:
            raise ViewpointStoreError("リスク重みは1〜5で指定してください。")
        automation = str(payload.get("automation", "manual"))
        if automation not in AUTOMATION_VALUES:
            raise ViewpointStoreError("自動化区分が不正です。")
        tags = payload.get("tags", [])
        if isinstance(tags, str):
            parsed = _json(tags, None)
            tags = (
                parsed if isinstance(parsed, list) else [part.strip() for part in tags.split(",")]
            )
        tags = list(dict.fromkeys(str(tag).strip() for tag in tags if str(tag).strip()))[:20]
        return {
            "persistent_key": persistent_key
            or str(payload.get("persistent_key") or _key_for(name, uuid.uuid4().hex[:6])).strip(),
            "name": name,
            "category": category,
            "purpose": str(payload.get("purpose", "")).strip(),
            "trigger_rule": validate_rule(payload.get("trigger_rule")),
            "recommended_checks": str(payload.get("recommended_checks", "")).strip(),
            "risk_weight": risk,
            "automation": automation,
            "standards": str(payload.get("standards", "")).strip(),
            "tags": tags,
            "enabled": bool(payload.get("enabled", True)),
        }

    def _insert_item(
        self, conn: sqlite3.Connection, version_id: str, item: dict[str, Any], now: str
    ) -> str:
        item_id = uuid.uuid4().hex
        conn.execute(
            """INSERT INTO viewpoint_items
               (id,version_id,persistent_key,name,category,purpose,trigger_rule,recommended_checks,risk_weight,
                automation,standards,tags,enabled,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item_id,
                version_id,
                item["persistent_key"],
                item["name"],
                item["category"],
                item["purpose"],
                _canonical(item["trigger_rule"]),
                item["recommended_checks"],
                item["risk_weight"],
                item["automation"],
                item["standards"],
                _canonical(item["tags"]),
                int(item["enabled"]),
                now,
                now,
            ),
        )
        return item_id

    def _item_dict(
        self, row: sqlite3.Row, *, source_set_id: str, inherited: bool
    ) -> dict[str, Any]:
        result = dict(row)
        result["trigger_rule"] = _json(result.get("trigger_rule"), {})
        result["tags"] = _json(result.get("tags"), [])
        result["enabled"] = bool(result.get("enabled"))
        result["source_set_id"] = source_set_id
        result["inherited"] = inherited
        return result

    def _assignment_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["rule"] = _json(result.get("rule"), {})
        result["enabled"] = bool(result.get("enabled"))
        return result

    def _proposal_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["payload"] = _json(result.get("payload"), {})
        return result

    def _check_revision(self, current: dict[str, Any], payload: dict[str, Any]) -> None:
        submitted = payload.get("revision")
        if submitted is None:
            raise ViewpointStoreError("revision は必須です。")
        if int(submitted) != int(current["revision"]):
            diff = {
                key: {"submitted": value, "current": current.get(key)}
                for key, value in payload.items()
                if key != "revision" and value != current.get(key)
            }
            raise ConflictError(
                "他の操作で更新されています。最新内容を確認してください。",
                details={"current": current, "diff": diff},
            )

    def _assert_mutable(self, version: dict[str, Any]) -> None:
        if version["status"] != "draft":
            raise ImmutableVersionError(
                "公開済み版は変更できません。次版の下書きを作成してください。"
            )

    def _assert_no_cycle(self, conn: sqlite3.Connection, start_set_id: str) -> None:
        current: str | None = start_set_id
        seen: set[str] = set()
        while current:
            if current in seen:
                raise ConflictError("観点セットの継承が循環しています。")
            seen.add(current)
            row = conn.execute(
                "SELECT parent_set_id FROM viewpoint_sets WHERE id=?", (current,)
            ).fetchone()
            current = row["parent_set_id"] if row else None

    def _duplicate_names(self, items: list[dict[str, Any]]) -> list[str]:
        counts: dict[str, int] = {}
        labels: dict[str, str] = {}
        for item in items:
            key = item["name"].strip().lower()
            counts[key] = counts.get(key, 0) + 1
            labels[key] = item["name"]
        return [labels[key] for key, count in counts.items() if count > 1]

    def _checksum_item(self, item: dict[str, Any]) -> str:
        fields = {
            key: item.get(key)
            for key in (
                "persistent_key",
                "name",
                "category",
                "purpose",
                "trigger_rule",
                "recommended_checks",
                "risk_weight",
                "automation",
                "standards",
                "tags",
                "enabled",
            )
        }
        return _checksum(fields)

    def _items_checksum(self, items: list[dict[str, Any]]) -> str:
        ordered = sorted(
            ({"key": item["persistent_key"], "hash": self._checksum_item(item)} for item in items),
            key=lambda item: item["key"],
        )
        return _checksum(ordered)
