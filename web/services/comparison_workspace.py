"""現新比較ワークスペース用のデータ整形（P2-2 第2弾）。

`comparison.html` は自己完結の静的レポートで、アプリ内から操作できない。
画面ペアを選び、差分を辿り、根拠を確認する——という一連の操作を画面上で
行えるようにするため、比較結果をペア単位に組み直して JSON で返す。

分類は既存の 5 分類（generator/comparison_reporter._CATEGORY_LABELS）をそのまま使う。
デザイン案には「構造変更」等の別語彙があったが、新設すると分類器
（diff/comparison.py）の判定まで変更が及ぶため採らない。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

# ペアの状態。追加・削除・未対応は「比較できなかった」ことを表し、
# 指摘が 0 件であることと区別する（不在を証明しない）。
PAIR_STATE_MATCHED = "matched"
PAIR_STATE_ADDED = "added"
PAIR_STATE_REMOVED = "removed"

# 重大度の並び。フィルタと「最も重い指摘」の判定に使う。
SEVERITY_ORDER: tuple[str, ...] = ("high", "medium", "low")


def _severity_rank(severity: str) -> int:
    try:
        return SEVERITY_ORDER.index(severity)
    except ValueError:
        return len(SEVERITY_ORDER)


def _preview_path(path: str, out_dir: Path) -> str:
    """/preview?path= に渡せる形にする。出力先の外を指すなら空文字。

    /preview の _safe_output_path は **カレントディレクトリ基準**でパスを解決するため、
    出力先からの相対パス（"example.com/..."）では通らない。保存されている形
    （"output/example.com/..."）をそのまま渡す。

    範囲外を空にするのは、出力先の外にあるファイルを画面から引けないようにするため
    （/preview 側でも弾くが、URL を作る時点で落とす）。
    """
    if not path:
        return ""
    try:
        resolved = Path(path).resolve()
        out_resolved = out_dir.resolve()
    except (ValueError, OSError):
        return ""
    if resolved != out_resolved and out_resolved not in resolved.parents:
        return ""
    return path


def _shots_by_page(diffs: list[Mapping[str, Any]], out_dir: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for d in diffs:
        page_id = str(d.get("page_id") or "")
        if not page_id:
            continue
        index[page_id] = {
            "before": _preview_path(str(d.get("before_path") or ""), out_dir),
            "after": _preview_path(str(d.get("after_path") or ""), out_dir),
            "diff": _preview_path(str(d.get("diff_image_path") or ""), out_dir),
            "diff_ratio": float(d.get("diff_ratio") or 0.0),
            "is_significant": bool(d.get("is_significant")),
            "structural_similarity": float(d.get("structural_similarity") or 1.0),
        }
    return index


def _findings_by_pair(findings: list[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """指摘を現行側 page_id で束ねる。ペアに紐付かない指摘は "" に入れる。"""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for index, finding in enumerate(findings):
        pair = finding.get("page_pair") or {}
        key = str(pair.get("old_page_id") or "") if isinstance(pair, Mapping) else ""
        grouped.setdefault(key, []).append(dict(finding, index=index))
    for items in grouped.values():
        items.sort(key=lambda f: (_severity_rank(str(f.get("severity") or "")), f["index"]))
    return grouped


def build_workspace(
    comparison: Mapping[str, Any],
    out_dir: Path,
    *,
    from_label: str = "",
    to_label: str = "",
) -> dict[str, Any]:
    """comparison_result_to_dict() の結果を、画面が描ける形に組み直す。

    ペアごとに「指摘・画像・最も重い分類」をまとめる。画面側で毎回
    findings を走査させると、フィルタや選択のたびに同じ集計を繰り返すことになる。
    """
    findings = list(comparison.get("findings") or [])
    grouped = _findings_by_pair(findings)
    shots = _shots_by_page(list(comparison.get("screenshot_diffs") or []), out_dir)

    pairs: list[dict[str, Any]] = []
    for pair in comparison.get("pairs") or []:
        old_id = str(pair.get("old_page_id") or "")
        items = grouped.get(old_id, [])
        top = items[0] if items else None
        pairs.append(
            {
                "state": PAIR_STATE_MATCHED,
                "old_page_id": old_id,
                "new_page_id": str(pair.get("new_page_id") or ""),
                "url": str(pair.get("url") or pair.get("old_url") or ""),
                "title": str(pair.get("title") or old_id),
                "finding_count": len(items),
                "top_category": str(top.get("category")) if top else "",
                "top_severity": str(top.get("severity")) if top else "",
                "findings": items,
                "screenshots": shots.get(old_id, {}),
            }
        )

    # 追加・削除は比較そのものができない。指摘 0 件と同じ見た目にしない。
    for page_id in comparison.get("added_page_ids") or []:
        pairs.append(_unmatched(PAIR_STATE_ADDED, str(page_id), "新側にのみ存在し、比較対象がありません"))
    for page_id in comparison.get("removed_page_ids") or []:
        pairs.append(
            _unmatched(PAIR_STATE_REMOVED, str(page_id), "現行側にのみ存在し、比較対象がありません")
        )

    return {
        "from": from_label,
        "to": to_label,
        "coverage": dict(comparison.get("coverage_summary") or {}),
        "pairs": pairs,
        "counts": _counts(pairs),
    }


def _unmatched(state: str, page_id: str, reason: str) -> dict[str, Any]:
    return {
        "state": state,
        "old_page_id": page_id if state == PAIR_STATE_REMOVED else "",
        "new_page_id": page_id if state == PAIR_STATE_ADDED else "",
        "url": "",
        "title": page_id,
        "finding_count": 0,
        "top_category": "",
        "top_severity": "",
        "unmatched_reason": reason,
        "findings": [],
        "screenshots": {},
    }


def _counts(pairs: list[dict[str, Any]]) -> dict[str, int]:
    matched = [p for p in pairs if p["state"] == PAIR_STATE_MATCHED]
    return {
        "pairs": len(pairs),
        "matched": len(matched),
        "added": sum(1 for p in pairs if p["state"] == PAIR_STATE_ADDED),
        "removed": sum(1 for p in pairs if p["state"] == PAIR_STATE_REMOVED),
        "with_findings": sum(1 for p in matched if p["finding_count"]),
        "findings": sum(p["finding_count"] for p in matched),
    }
