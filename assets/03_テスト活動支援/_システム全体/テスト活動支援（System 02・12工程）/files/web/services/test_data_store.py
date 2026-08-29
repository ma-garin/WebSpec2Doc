"""データ駆動テスト用のテストデータセットを永続化する。

1 ドメインにつき 1 ファイルへまとめて保存する。データセットはテストケースが参照する
「入力の表」であり、1 ドメインで数十件・数千行に収まるため、ファイルを分割せず
単一の JSON で持つ（一覧と中身が読み出し 1 回で揃う）。

    output/<domain>/test_data/datasets.json   データセット一覧

壊れた JSON は例外にせず空一覧へフォールバックする。利用者に 500 を見せるより、
「データセットが無い」状態から作り直せる方が復旧が早い。
上限（行 10000 / 列 50）の超過だけは切り詰めず ValueError にする。黙って欠けた
データでテストが緑になる方が危険なため。
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MAX_ROWS = 10000
MAX_COLUMNS = 50
MAX_NAME_LENGTH = 200
MAX_CELL_LENGTH = 2000


class TestDataError(ValueError):
    """入力が不正でデータセットを保存できない場合に送出する。"""


# =========================================================================
# パス
# =========================================================================
def _safe_domain(domain: str) -> str:
    """ドメイン名をパス要素として使う前に検証する（パストラバーサル防止）。"""
    from web.validation import _valid_domain

    name = (domain or "").strip()
    if not _valid_domain(name):
        raise TestDataError(f"不正なドメイン名です: {domain!r}")
    return name


def _datasets_path(out_dir: Path, domain: str) -> Path:
    return Path(out_dir) / _safe_domain(domain) / "test_data" / "datasets.json"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _clip(value: Any, limit: int = MAX_CELL_LENGTH) -> str:
    return str(value if value is not None else "")[:limit]


# =========================================================================
# 読み書き
# =========================================================================
def _normalize(raw: Mapping[str, Any]) -> dict[str, Any]:
    """保存済みレコードを既定形へ整える（欠損・型崩れは既定値で埋める）。"""
    raw_columns = raw.get("columns")
    columns = [str(c) for c in raw_columns] if isinstance(raw_columns, list) else []
    raw_rows = raw.get("rows")
    rows = [dict(r) for r in raw_rows if isinstance(r, dict)] if isinstance(raw_rows, list) else []
    return {
        "id": str(raw.get("id") or ""),
        "name": str(raw.get("name") or ""),
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "created_at": str(raw.get("created_at") or ""),
        "updated_at": str(raw.get("updated_at") or ""),
    }


def _load(out_dir: Path, domain: str) -> list[dict[str, Any]]:
    path = _datasets_path(out_dir, domain)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    items = data.get("datasets") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [_normalize(item) for item in items if isinstance(item, dict)]


def _write(out_dir: Path, domain: str, datasets: Sequence[Mapping[str, Any]]) -> None:
    path = _datasets_path(out_dir, domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "datasets": [dict(d) for d in datasets]}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# =========================================================================
# 公開 API
# =========================================================================
def list_datasets(out_dir: Path, domain: str) -> list[dict[str, Any]]:
    """データセットを新しい順（更新日時の降順）で返す。"""
    items = _load(out_dir, domain)
    return sorted(items, key=lambda d: (d["updated_at"], d["created_at"], d["id"]), reverse=True)


def get_dataset(out_dir: Path, domain: str, dataset_id: str) -> dict[str, Any] | None:
    """id で 1 件取り出す。無ければ None。"""
    target = str(dataset_id or "")
    for item in _load(out_dir, domain):
        if item["id"] == target:
            return item
    return None


def _validate_columns(columns: list[str]) -> list[str]:
    if not isinstance(columns, list) or not columns:
        raise TestDataError("列が指定されていません")
    if len(columns) > MAX_COLUMNS:
        raise TestDataError(f"列数が上限（{MAX_COLUMNS}）を超えています: {len(columns)}")
    names = [_clip(c, MAX_NAME_LENGTH).strip() for c in columns]
    if any(not n for n in names):
        raise TestDataError("空の列名は使えません")
    if len(set(names)) != len(names):
        raise TestDataError("列名が重複しています")
    return names


def _validate_rows(rows: list[dict[str, Any]], columns: list[str]) -> list[dict[str, str]]:
    if not isinstance(rows, list):
        raise TestDataError("行の形式が不正です")
    if len(rows) > MAX_ROWS:
        raise TestDataError(f"行数が上限（{MAX_ROWS}）を超えています: {len(rows)}")
    normalized: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise TestDataError("行はオブジェクトである必要があります")
        normalized.append({col: _clip(row.get(col, "")) for col in columns})
    return normalized


def save_dataset(
    out_dir: Path,
    domain: str,
    name: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    dataset_id: str = "",
) -> dict[str, Any]:
    """データセットを新規保存または上書きし、保存後のレコードを返す。

    dataset_id を指定すればその 1 件を、指定しなければ同名のデータセットを上書きする。
    どちらも見つからなければ新規に採番する。既存レコードは書き換えず、新しい dict を作る。
    """
    label = _clip(name, MAX_NAME_LENGTH).strip()
    if not label:
        raise TestDataError("データセット名が空です")
    safe_columns = _validate_columns(columns)
    safe_rows = _validate_rows(rows, safe_columns)

    existing = _load(out_dir, domain)
    target_id = str(dataset_id or "")
    previous = next(
        (d for d in existing if (d["id"] == target_id if target_id else d["name"] == label)),
        None,
    )
    now = _now()
    record: dict[str, Any] = {
        "id": previous["id"] if previous else uuid.uuid4().hex,
        "name": label,
        "columns": safe_columns,
        "rows": safe_rows,
        "row_count": len(safe_rows),
        "created_at": previous["created_at"] if previous else now,
        "updated_at": now,
    }
    others = [d for d in existing if d["id"] != record["id"]]
    _write(out_dir, domain, [*others, record])
    return record


def delete_dataset(out_dir: Path, domain: str, dataset_id: str) -> bool:
    """1 件削除する。存在しなければ False。"""
    target = str(dataset_id or "")
    existing = _load(out_dir, domain)
    remaining = [d for d in existing if d["id"] != target]
    if len(remaining) == len(existing):
        return False
    _write(out_dir, domain, remaining)
    return True


# =========================================================================
# CSV 取り込み
# =========================================================================
def _unique_headers(raw: Sequence[str]) -> list[str]:
    """ヘッダを一意化する（空は列番号で補い、重複は末尾に連番を付ける）。"""
    seen: dict[str, int] = {}
    headers: list[str] = []
    for index, cell in enumerate(raw, start=1):
        base = _clip(cell, MAX_NAME_LENGTH).strip() or f"column_{index}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        headers.append(base if count == 1 else f"{base}_{count}")
    return headers


def parse_csv(text: str) -> tuple[list[str], list[dict[str, str]]]:
    """CSV テキストを 1 行目をヘッダとして columns / rows に分解する。

    空行は捨てる。ヘッダ数より短い行は空文字で埋め、長い行は余りを捨てる。
    """
    try:
        records = [
            row
            for row in csv.reader(io.StringIO(text or "", newline=""))
            if any((cell or "").strip() for cell in row)
        ]
    except csv.Error as exc:
        raise TestDataError(f"CSV を解釈できません: {exc}") from exc
    if not records:
        return [], []
    if len(records[0]) > MAX_COLUMNS:
        raise TestDataError(f"列数が上限（{MAX_COLUMNS}）を超えています: {len(records[0])}")
    if len(records) - 1 > MAX_ROWS:
        raise TestDataError(f"行数が上限（{MAX_ROWS}）を超えています: {len(records) - 1}")
    columns = _unique_headers(records[0])
    rows = [
        {col: _clip(record[i]) if i < len(record) else "" for i, col in enumerate(columns)}
        for record in records[1:]
    ]
    return columns, rows
