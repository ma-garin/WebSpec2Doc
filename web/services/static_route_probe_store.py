"""静的 route 候補の到達確認（System 03）の結果の保存・読み込み。

System 01 の reverse_analysis.json（静的候補）は書き換えない。到達確認は別ファイルに
「静的候補 id → 実測の到達結果」として持ち、System 02・09 はここから読む。

置き場所: <出力>/<domain>/reverse_analysis/route_probe.json
{
  "domain": str,
  "analysis_snapshot_sha256": str, # どのリバース解析結果（run.json）に対する確認か。不一致なら使わない（旧名 rea_snapshot_sha256 も読む）
  "started_at": ISO, "finished_at": ISO, "seconds": float,
  "items": [{
    "evidence_id": str,            # System 01 の静的 route 候補 id
    "route": str,                  # 候補の値（例 "settings", "article/:slug"）
    "url": str | null,             # 実際に開いた URL（開いていなければ null）
    "status": "observed" | "unreached" | "auth_required" | "ambiguous" | "failed",
    "reason": str,                 # 利用者向けの理由（1 文）
    "http_status": int | null,
    "final_url": str | null,       # 遷移後に留まった URL
    "observed_at": ISO | null,     # status == observed のときだけ
    "authenticated": bool,         # その結果が System 01 の保存済み認証状態付きの遷移によるものか
    "auth_attempted": bool,        # 認証状態付きで再探索したか
    "evidence": str,               # 観測した事実（1 文）
    "limitation": str              # この結果で言えないこと（observed は「正しさは未確認」）
  }]
}
observed は「GET の遷移でその URL に到達し、アプリがその URL に留まった」実測だけを指す。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from web.services import reverse_analysis_run as runner

PROBE_FILE = "route_probe.json"
AUTH_LABEL = "保存済みの認証状態で確認"  # 認証状態付きで observed になった item の GUI 表示用（STATUS_LABEL は変えない）
STATUSES = ("observed", "unreached", "auth_required", "ambiguous", "failed")
STATUS_LABEL = {
    "observed": "実測で到達",
    "unreached": "未到達",
    "auth_required": "認証等で未確認",
    "ambiguous": "曖昧（値が必要）",
    "failed": "確認失敗",
}


def probe_path(base: Path, domain: str) -> Path:
    return runner.site_dir(base, domain) / PROBE_FILE


def current_analysis_sha(base: Path, domain: str) -> str | None:
    run_path = runner.site_dir(base, domain) / runner.RUN_FILE
    if not run_path.is_file():
        return None
    return json.loads(run_path.read_text(encoding="utf-8")).get("snapshot_sha256")


def save(base: Path, domain: str, doc: dict[str, Any]) -> None:
    path = probe_path(base, domain)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def load(base: Path, domain: str) -> dict[str, Any] | None:
    """現在のリバース解析結果に対する到達確認だけを返す。別の結果に対するものは None（使わない）。"""
    path = probe_path(base, domain)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    saved = doc.get("analysis_snapshot_sha256") or doc.get("rea_snapshot_sha256")
    if doc.get("domain") != domain or saved != current_analysis_sha(base, domain):
        return None
    return doc


def by_evidence(doc: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """evidence_id → item。System 02・09 が静的 route 候補に実測結果を重ねるために使う。"""
    if not doc:
        return {}
    return {i["evidence_id"]: i for i in doc.get("items", []) if i.get("status") in STATUSES}


# 旧名の別名（既存の呼び出し元・テスト用）
current_rea_sha = current_analysis_sha
