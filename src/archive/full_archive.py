"""完全アーカイブ（規制業種向け）。

保持ポリシーが消す対象も含め、ある時点の成果物一式を1つの書庫へ固める。
監査で「その時点で何を観測し、何を出力したか」を再提出できるようにする。

設計上の要点:
- **アーカイブ後も元データは消さない**。消す判断は保持ポリシー側の責務であり、
  ここで勝手に消すと二重の削除経路ができて事故になる。
- 書庫にマニフェスト（対象ファイルとSHA-256）を必ず同梱する。
  中身が後から差し替えられていないことを、受け取った側が検証できるようにするため。
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

MANIFEST_NAME = "MANIFEST.json"
CLAIM_SCOPE = "archived_outputs_only"

CLAIM_NOTICE = (
    "本書庫はアーカイブ時点で存在した成果物の写しであり、"
    "対象システムの品質や準拠性を証明するものではない。"
)

# 書庫に含めない一時生成物（再現可能・容量が大きい）
_EXCLUDED_DIR_NAMES = frozenset({"playwright-report", "__pycache__", ".playwright_env"})


@dataclass(frozen=True)
class ArchiveResult:
    archive_path: Path
    file_count: int
    total_bytes: int
    created_at: str


def create_full_archive(
    source_dir: Path,
    destination_dir: Path,
    *,
    label: str = "",
    created_at: datetime | None = None,
) -> ArchiveResult:
    """source_dir 配下の成果物を1つのZIPへ固め、マニフェストを同梱する。"""
    if not source_dir.is_dir():
        raise FileNotFoundError(f"アーカイブ対象がありません: {source_dir}")

    moment = created_at or datetime.now(ZoneInfo("Asia/Tokyo"))
    stamp = moment.strftime("%Y%m%d-%H%M%S")
    suffix = f"_{label}" if label else ""
    destination_dir.mkdir(parents=True, exist_ok=True)
    archive_path = destination_dir / f"archive_{stamp}{suffix}.zip"

    files = sorted(_collect_files(source_dir))
    entries: list[dict[str, Any]] = []
    total_bytes = 0

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            relative = path.relative_to(source_dir).as_posix()
            data = path.read_bytes()
            total_bytes += len(data)
            entries.append(
                {
                    "path": relative,
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
            bundle.writestr(relative, data)

        created_iso = moment.isoformat(timespec="seconds")
        manifest: dict[str, Any] = {
            "meta": {
                "created_at": created_iso,
                "source": str(source_dir),
                "label": label,
                "claim_scope": CLAIM_SCOPE,
                "claim_notice": CLAIM_NOTICE,
            },
            "summary": {"file_count": len(entries), "total_bytes": total_bytes},
            "files": entries,
        }
        bundle.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))

    return ArchiveResult(
        archive_path=archive_path,
        file_count=len(entries),
        total_bytes=total_bytes,
        created_at=created_iso,
    )


def verify_archive(archive_path: Path) -> dict[str, Any]:
    """書庫の中身がマニフェストと一致するか検証する。"""
    with zipfile.ZipFile(archive_path) as bundle:
        names = set(bundle.namelist())
        if MANIFEST_NAME not in names:
            return {"ok": False, "error": "マニフェストがありません", "mismatches": []}
        manifest = json.loads(bundle.read(MANIFEST_NAME).decode("utf-8"))

        mismatches: list[dict[str, str]] = []
        for entry in manifest.get("files", []):
            relative = str(entry.get("path", ""))
            if relative not in names:
                mismatches.append({"path": relative, "reason": "missing"})
                continue
            digest = hashlib.sha256(bundle.read(relative)).hexdigest()
            if digest != str(entry.get("sha256", "")):
                mismatches.append({"path": relative, "reason": "checksum_mismatch"})

    return {
        "ok": not mismatches,
        "file_count": len(manifest.get("files", [])),
        "mismatches": mismatches,
        "created_at": manifest.get("meta", {}).get("created_at", ""),
    }


def _collect_files(source_dir: Path) -> list[Path]:
    collected: list[Path] = []
    for path in source_dir.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        collected.append(path)
    return collected
