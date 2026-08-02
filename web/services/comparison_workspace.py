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

# ペアの状態。追加・削除は「比較できなかった」ことを表し、
# 指摘が 0 件であることと区別する（不在を証明しない）。
#
# **既知の欠落**: デザイン案（docs/design/old-new-comparison-proto.html）は
# 「未対応（画面対応付けが確立できません）」を第 4 の状態として持つが、実装していない。
# match_page_pairs（src/diff/pair_matcher.py:78-80）が返すのは pairs / removed / added の
# 3 つだけで、対応付けに失敗した画面は removed / added に混ざる。
# 「消えた画面」と「対応先が分からなかった画面」を画面上で区別できていない。
# 分けるには pair_matcher の戻り値を増やす必要があり、ここだけでは直せない。
PAIR_STATE_MATCHED = "matched"
PAIR_STATE_ADDED = "added"
PAIR_STATE_REMOVED = "removed"


def _severity_order() -> tuple[str, ...]:
    """重大度の並び（重い順）。値の出所は src/diff/differ.py の 1 箇所だけにする。

    以前ここで high/medium/low という実在しない値を再定義しており、
    並べ替えとフィルタが黙って効かない状態になっていた。再定義しない。
    """
    from diff.differ import SEVERITY_BREAKING, SEVERITY_INFO, SEVERITY_WARNING

    return (SEVERITY_BREAKING, SEVERITY_WARNING, SEVERITY_INFO)


# 画面に出す日本語ラベル。JS 側で再定義せず、この API の応答に載せて配る
# （JS は Python を import できないため、値ではなく表示物として渡す）。
SEVERITY_LABELS: dict[str, str] = {"breaking": "高", "warning": "中", "info": "低"}
SEVERITY_ORDER: tuple[str, ...] = _severity_order()


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
        before_raw = str(d.get("before_path") or "")
        after_raw = str(d.get("after_path") or "")
        index[page_id] = {
            "before": _preview_path(before_raw, out_dir),
            "after": _preview_path(after_raw, out_dir),
            "diff": _preview_path(str(d.get("diff_image_path") or ""), out_dir),
            "diff_ratio": float(d.get("diff_ratio") or 0.0),
            "is_significant": bool(d.get("is_significant")),
            "structural_similarity": float(d.get("structural_similarity") or 1.0),
            # 世代別スクリーンショットを保存する前に取ったスナップショットは、
            # 両世代が同じ最新画像を指す。並べても同じ絵になるので、
            # 「変化が無い」ではなく「比較できない」と分かる形で伝える。
            "same_capture": bool(before_raw) and before_raw == after_raw,
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
    page_info: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """comparison_result_to_dict() の結果を、画面が描ける形に組み直す。

    ペアごとに「指摘・画像・最も重い分類」をまとめる。画面側で毎回
    findings を走査させると、フィルタや選択のたびに同じ集計を繰り返すことになる。

    page_info は page_id → {"title", "url"}。ScreenPair は page_id しか持たないため、
    一覧に出す名前は呼び出し側から渡す（P001 だけ並ぶと、どの画面か分からない）。
    """
    findings = list(comparison.get("findings") or [])
    grouped = _findings_by_pair(findings)
    shots = _shots_by_page(list(comparison.get("screenshot_diffs") or []), out_dir)
    info = page_info or {}

    pairs: list[dict[str, Any]] = []
    for pair in comparison.get("pairs") or []:
        old_id = str(pair.get("old_page_id") or "")
        new_id = str(pair.get("new_page_id") or "")
        items = grouped.get(old_id, [])
        top = items[0] if items else None
        # 名前は新側を優先する。比較の関心は「今どうなっているか」にあるため。
        pairs.append(
            _pair_record(
                PAIR_STATE_MATCHED,
                old_id=old_id,
                new_id=new_id,
                meta=info.get(new_id) or info.get(old_id) or {},
                fallback_title=old_id,
                findings=items,
                top=top,
                screenshots=shots.get(old_id, {}),
            )
        )

    # 追加・削除は比較そのものができない。指摘 0 件と同じ見た目にしない。
    for page_id in comparison.get("added_page_ids") or []:
        pairs.append(
            _unmatched(
                PAIR_STATE_ADDED, str(page_id), "新側にのみ存在し、比較対象がありません", info
            )
        )
    for page_id in comparison.get("removed_page_ids") or []:
        pairs.append(
            _unmatched(
                PAIR_STATE_REMOVED, str(page_id), "現行側にのみ存在し、比較対象がありません", info
            )
        )

    return {
        "from": from_label,
        "to": to_label,
        "coverage": dict(comparison.get("coverage_summary") or {}),
        "pairs": pairs,
        "counts": _counts(pairs),
        # 語彙は Python 側の 1 箇所が持つ。JS で再定義すると、段階を増減したとき
        # 片方だけ直して並べ替えと表示が食い違う（実際に起きた）。
        "severity": {"order": list(SEVERITY_ORDER), "labels": dict(SEVERITY_LABELS)},
    }


def _pair_record(
    state: str,
    *,
    old_id: str = "",
    new_id: str = "",
    meta: Mapping[str, str] | None = None,
    fallback_title: str = "",
    findings: list[dict[str, Any]] | None = None,
    top: Mapping[str, Any] | None = None,
    screenshots: Mapping[str, Any] | None = None,
    unmatched_reason: str = "",
) -> dict[str, Any]:
    """画面が読む 1 ペア分のレコード。matched も未対応も同じ形で作る。

    形を 2 箇所で組み立てると、フィールドを増やしたとき片方でキーが欠ける。
    """
    meta = meta or {}
    items = findings or []
    return {
        "state": state,
        "old_page_id": old_id,
        "new_page_id": new_id,
        "url": str(meta.get("url") or ""),
        "title": str(meta.get("title") or fallback_title),
        "finding_count": len(items),
        "top_category": str(top.get("category")) if top else "",
        "top_severity": str(top.get("severity")) if top else "",
        "findings": items,
        "screenshots": dict(screenshots or {}),
        "unmatched_reason": unmatched_reason,
    }


def _unmatched(
    state: str, page_id: str, reason: str, info: Mapping[str, Mapping[str, str]] | None = None
) -> dict[str, Any]:
    return _pair_record(
        state,
        old_id=page_id if state == PAIR_STATE_REMOVED else "",
        new_id=page_id if state == PAIR_STATE_ADDED else "",
        meta=(info or {}).get(page_id) or {},
        fallback_title=page_id,
        unmatched_reason=reason,
    )


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
