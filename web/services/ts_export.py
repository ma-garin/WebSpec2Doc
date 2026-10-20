"""TypeScript エクスポート成果物の状態（generated / executed / verified）。

TS は製品内では実行しない。画面とファイルには次の 3 区分を常に分けて示す。
- generated: 生成した（ファイルがある）
- executed : 製品内で実行した → 常に False（実行は Python spec のみ）
- verified : 結果を検証した   → 常に False
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

TS_EXPORT_STATE: Final = {"generated": True, "executed": False, "verified": False}

#: 画面表示用の 3 区分（バッジ文言）。
TS_EXPORT_LABELS: Final = {
    "generated": "生成済み",
    "executed": "未実行",
    "verified": "未検証",
}


def merge_meta(meta_path: Path, update: Mapping[str, Any]) -> dict[str, Any]:
    """既存の `.meta.json`（Python 側が先に書いた同名ファイル）を上書きせず merge する。

    ``tests`` は既存があればそれを優先する（Python 版と TS 版でテスト ID は一致する前提）。
    """
    current: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            loaded = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current = loaded
        except (OSError, json.JSONDecodeError):
            current = {}
    merged = dict(current)
    for key, value in update.items():
        if key == "tests" and current.get("tests"):
            continue
        merged[key] = value
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def ts_export_status(meta: Mapping[str, Any] | None, ts_exists: bool) -> dict[str, Any]:
    """画面向けの TS エクスポート状態。実行・検証済みを偽らず、常に 3 区分を返す。

    旧 run（meta に ts_export が無い・TS のみ）は「旧形式（Node 実行）」と注記する。
    """
    raw = (meta or {}).get("ts_export")
    legacy = ts_exists and not isinstance(raw, Mapping)
    state = {
        "generated": bool(ts_exists),
        "executed": False,
        "verified": False,
    }
    return {
        **state,
        "legacy": legacy,
        "note": "旧形式（Node 実行）" if legacy else "",
        "labels": [
            TS_EXPORT_LABELS["generated"] if state["generated"] else "未生成",
            TS_EXPORT_LABELS["executed"],
            TS_EXPORT_LABELS["verified"],
        ],
    }


#: TS ファイル先頭に入れる 3 区分の明示（ファイルでも状態を区別する）。
TS_EXPORT_HEADER: Final = (
    "// WebSpec2Doc TypeScript エクスポート: generated（生成済み）/ not executed（未実行）/"
    " not verified（未検証）\n"
    "// 製品内の実行は Python spec のみ。この TypeScript は実行も検証もされていません。\n"
)


def add_header(path: Path) -> None:
    """TS エクスポートの先頭へ 3 区分の注記を（無ければ）付ける。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    if text.startswith("// WebSpec2Doc TypeScript エクスポート"):
        return
    path.write_text(TS_EXPORT_HEADER + text, encoding="utf-8")
