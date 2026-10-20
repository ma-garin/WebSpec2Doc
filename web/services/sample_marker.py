"""サンプル（試作の再生）で作った出力かどうかの判定。実サイトの解析結果と同じ見え方にしないために使う。

System01 app の試作（web/services/app_mock.py）は、実アプリを解析せずに demo/sample_report_app の
固定データを出力へ写す。写した report.json の meta に sample=True と source を書く。
それより前に作られた出力は印が無いので、試作の既定ホスト（app.sampleshop）で見分ける。
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SAMPLE_SOURCE = "system01_app_mock"
_LEGACY_SAMPLE_HOSTS = frozenset({"app.sampleshop"})  # app_mock の既定ホスト（印を書く前の出力）


def is_sample_report(report: Mapping[str, Any] | None) -> bool:
    meta = (report or {}).get("meta") or {}
    if meta.get("sample") is True:
        return True
    host = urlparse(str(meta.get("target_url") or "")).hostname or ""
    return host in _LEGACY_SAMPLE_HOSTS


def is_sample_dir(domain_dir: Path) -> bool:
    """出力ディレクトリの report.json がサンプル由来か。読めなければ False（推測しない）。"""
    try:
        return is_sample_report(json.loads((domain_dir / "report.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return False


def mark_report_json(path: Path) -> None:
    """写した report.json の meta にサンプルの印を書く。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data.setdefault("meta", {})
    meta["sample"] = True
    meta["source"] = SAMPLE_SOURCE
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
