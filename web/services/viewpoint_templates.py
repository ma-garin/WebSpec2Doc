from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from web.config import VIEWPOINT_TEMPLATES_DIR
from web.services.viewpoint_store import ViewpointStoreError, get_viewpoint_store


class TemplateNotFoundError(ViewpointStoreError):
    status_code = 404


def _templates_dir() -> Path:
    return VIEWPOINT_TEMPLATES_DIR


def _load_template_file(key: str) -> dict[str, Any]:
    path = _templates_dir() / f"{key}.json"
    if not path.is_file():
        raise TemplateNotFoundError(f"観点プリセットが見つかりません: {key}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TemplateNotFoundError(f"観点プリセットの読み込みに失敗しました: {key}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("folders"), list):
        raise TemplateNotFoundError(f"観点プリセットの形式が不正です: {key}")
    return data


def list_templates() -> list[dict[str, Any]]:
    """利用可能な観点プリセットの一覧をメタ情報付きで返す。"""
    directory = _templates_dir()
    if not directory.is_dir():
        return []
    templates: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = _load_template_file(path.stem)
        except TemplateNotFoundError:
            continue
        folders = data.get("folders", [])
        item_count = sum(len(folder.get("items", [])) for folder in folders)
        templates.append(
            {
                "key": path.stem,
                "name": data.get("name", path.stem),
                "description": data.get("description", ""),
                "folder_count": len(folders),
                "item_count": item_count,
            }
        )
    return templates


def apply_template(set_id: str, template_key: str) -> dict[str, Any]:
    """プリセットのフォルダ・観点アイテムを、指定セットの下書き版に投入する。

    フォルダ→アイテムの順に既存の create_folder/create_item を呼び出すだけで、
    バージョン管理・整合性検証は ViewpointStore 側の既存ロジックにそのまま乗る
    （プリセット投入専用の別経路を作らない）。"""
    data = _load_template_file(template_key)
    store = get_viewpoint_store()
    draft = store.ensure_draft(set_id)
    version_number = int(draft["version_number"])

    created_folders = 0
    created_items = 0
    for folder in data.get("folders", []):
        folder_name = str(folder.get("name", "")).strip()
        if not folder_name:
            continue
        folder_item = store.create_folder(
            set_id, {"name": folder_name}, version_number=version_number
        )
        created_folders += 1
        for item in folder.get("items", []):
            payload = {
                **item,
                "node_type": "viewpoint",
                "parent_key": folder_item["persistent_key"],
            }
            store.create_item(set_id, payload, version_number=version_number)
            created_items += 1

    return {
        "template_key": template_key,
        "template_name": data.get("name", template_key),
        "created_folders": created_folders,
        "created_items": created_items,
    }
