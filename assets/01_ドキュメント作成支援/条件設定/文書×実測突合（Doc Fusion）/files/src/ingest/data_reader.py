"""構造化データ（.yaml/.yml/.json）からの画面・項目抽出。

キー名のシノニム（日英）を許容し、以下のような柔軟な形を受け付ける:

    screens:                    # または 画面 / 画面一覧 / pages
      - name: ログイン画面      # または 画面名
        url: /login
        fields:                 # または 項目 / items
          - name: メールアドレス
            required: true
            max_length: 100
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from ingest.models import DocumentedField, DocumentedScreen, DocumentEvidence
from ingest.tables import parse_max_length, parse_required

_SCREENS_KEYS = ("screens", "pages", "画面", "画面一覧")
_FIELDS_KEYS = ("fields", "items", "項目", "項目一覧", "入力項目")
_NAME_KEYS = ("name", "画面名", "名称", "項目名", "label", "ラベル")
_ID_KEYS = ("id", "screen_id", "画面id", "画面ID")
_URL_KEYS = ("url", "path", "パス")
_PHYSICAL_KEYS = ("physical_name", "物理名", "field_name")
_TYPE_KEYS = ("type", "field_type", "型", "データ型")
_REQUIRED_KEYS = ("required", "必須")
_LENGTH_KEYS = ("max_length", "maxlength", "桁数", "最大文字数")
_NOTE_KEYS = ("note", "備考", "説明", "description")


def read_structured_data(path: Path) -> tuple[list[DocumentedScreen], list[DocumentedField]]:
    """YAML/JSON から画面・項目を抽出する。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    screens: list[DocumentedScreen] = []
    fields: list[DocumentedField] = []
    _collect(data, path.name, "$", "", screens, fields)
    return screens, fields


def _pick(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for raw_key, value in mapping.items():
        if str(raw_key).strip().lower() in keys:
            return value
    return None


def _collect(
    node: Any,
    file_name: str,
    location: str,
    screen_name: str,
    screens: list[DocumentedScreen],
    fields: list[DocumentedField],
) -> None:
    if isinstance(node, dict):
        for raw_key, value in node.items():
            key = str(raw_key).strip().lower()
            child_location = f"{location}.{raw_key}"
            if key in _SCREENS_KEYS and isinstance(value, list):
                for index, item in enumerate(value):
                    _collect_screen(item, file_name, f"{child_location}[{index}]", screens, fields)
            elif key in _FIELDS_KEYS and isinstance(value, list):
                for index, item in enumerate(value):
                    _collect_field(
                        item, file_name, f"{child_location}[{index}]", screen_name, fields
                    )
            elif isinstance(value, dict | list):
                _collect(value, file_name, child_location, screen_name, screens, fields)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _collect(item, file_name, f"{location}[{index}]", screen_name, screens, fields)


def _collect_screen(
    item: Any,
    file_name: str,
    location: str,
    screens: list[DocumentedScreen],
    fields: list[DocumentedField],
) -> None:
    if isinstance(item, str):
        if item.strip():
            screens.append(
                DocumentedScreen(
                    screen_id="",
                    name=item.strip(),
                    evidence=DocumentEvidence(file=file_name, location=location, quote=item),
                )
            )
        return
    if not isinstance(item, dict):
        return
    name = str(_pick(item, _NAME_KEYS) or "").strip()
    if not name:
        return
    screens.append(
        DocumentedScreen(
            screen_id=str(_pick(item, _ID_KEYS) or "").strip(),
            name=name,
            url_hint=str(_pick(item, _URL_KEYS) or "").strip(),
            note=str(_pick(item, _NOTE_KEYS) or "").strip(),
            evidence=DocumentEvidence(file=file_name, location=location, quote=name),
        )
    )
    # 画面配下にネストされた項目定義を、その画面に紐づけて回収する
    nested_fields = _pick(item, _FIELDS_KEYS)
    if isinstance(nested_fields, list):
        for index, field_item in enumerate(nested_fields):
            _collect_field(field_item, file_name, f"{location}.fields[{index}]", name, fields)


def _collect_field(
    item: Any,
    file_name: str,
    location: str,
    screen_name: str,
    fields: list[DocumentedField],
) -> None:
    if isinstance(item, str):
        if item.strip():
            fields.append(
                DocumentedField(
                    name=item.strip(),
                    screen_name=screen_name,
                    evidence=DocumentEvidence(file=file_name, location=location, quote=item),
                )
            )
        return
    if not isinstance(item, dict):
        return
    name = str(_pick(item, _NAME_KEYS) or "").strip()
    if not name:
        return
    raw_required = _pick(item, _REQUIRED_KEYS)
    required: bool | None
    if isinstance(raw_required, bool):
        required = raw_required
    elif raw_required is None:
        required = None
    else:
        required = parse_required(str(raw_required))
    raw_length = _pick(item, _LENGTH_KEYS)
    max_length: int | None
    if isinstance(raw_length, int):
        max_length = raw_length
    elif raw_length is None:
        max_length = None
    else:
        max_length = parse_max_length(str(raw_length))
    fields.append(
        DocumentedField(
            name=name,
            physical_name=str(_pick(item, _PHYSICAL_KEYS) or "").strip(),
            screen_name=str(_pick(item, ("screen", "画面", "画面名")) or screen_name).strip(),
            field_type=str(_pick(item, _TYPE_KEYS) or "").strip(),
            required=required,
            max_length=max_length,
            note=str(_pick(item, _NOTE_KEYS) or "").strip(),
            evidence=DocumentEvidence(file=file_name, location=location, quote=name),
        )
    )
