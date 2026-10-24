"""System 01: 対象サイトの版（クロール時点）を軸にした判定材料を組み立てる。

画面は件数ではなく「どの版の・何が・どこまで確かか」で判断させる。
- 版: snapshots/<時刻>.json を 1 版とする（新しい順）
- 今回の変更分: 最新版と 1 つ前の版の差分（compute_diff）を項目名で列挙する
- 区分: 観測（クロールで実際に取得）／推論（観測から生成）／未確認（取得できなかった）
- 失敗: audit.jsonl の記録を利用者向けの文と次の行動 1 行に置き換える
判定語は共通語彙（合格／不合格／判定不能／未判定）だけを使う。
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PASS, FAIL, UNDECIDABLE, UNJUDGED = "合格", "不合格", "判定不能", "未判定"

_FAILURE_TEXT: dict[str, tuple[str, str]] = {
    "login_wall": (
        "ログインが必要な画面のため、中身を取得できませんでした。",
        "ログイン情報を登録してから再解析してください。",
    ),
    "robots": (
        "サイトの公開ルールで解析が禁止されている画面です。",
        "対象から外すか、サイトの管理者に解析の許可を確認してください。",
    ),
    "unsafe_url": (
        "安全上の理由で解析できない宛先です。",
        "公開されている URL に変えて解析してください。",
    ),
    "failed": (
        "画面を開けませんでした（応答なし・時間切れなど）。",
        "サイトが開けることを確かめてから再解析してください。",
    ),
    "no_pages": (
        "解析できた画面が 1 件もありませんでした。",
        "入力した URL がブラウザで開けるか確かめ、再解析してください。",
    ),
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _last_run_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """audit.jsonl は追記式なので、最後の crawl_started 以降だけを最新の版の記録とみなす。"""
    starts = [i for i, r in enumerate(rows) if r.get("event") == "crawl_started"]
    return rows[starts[-1] :] if starts else rows


def _failure(kind: str, url: str = "") -> dict[str, str]:
    text, action = _FAILURE_TEXT[kind]
    return {"kind": kind, "url": url, "message": text, "next_action": action}


def collect_failures(domain_dir: Path) -> list[dict[str, str]]:
    events = _last_run_events(_read_jsonl(domain_dir / "audit.jsonl"))
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for ev in events:
        name = ev.get("event")
        items: list[tuple[str, str]] = []
        if name == "login_wall_detected":
            items.append(("login_wall", str(ev.get("url", ""))))
        elif name == "crawl_started":
            items += [("robots", str(u)) for u in ev.get("robots_skipped_urls") or []]
        elif name == "page_skipped":
            reason = str(ev.get("reason", ""))
            kind = reason if reason in ("robots", "unsafe_url") else "failed"
            items.append((kind, str(ev.get("url", ""))))
        elif name == "page_failed":
            items.append(("failed", str(ev.get("url", ""))))
        for item in items:
            if item not in seen:
                seen.add(item)
                out.append(_failure(*item))
    return out


def _http_failures(snapshot: Path | None, known: list[dict[str, str]]) -> list[dict[str, str]]:
    """取得はできたが応答がエラー（404・500 など）だった画面。中身はエラーページなので未確認に数える。"""
    if snapshot is None:
        return []
    try:
        pages = json.loads(snapshot.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    urls = {f["url"] for f in known}
    out = []
    for page in pages if isinstance(pages, list) else []:
        status = page.get("http_status") if isinstance(page, dict) else None
        if isinstance(status, int) and status >= 400 and page.get("url") not in urls:
            item = _failure("failed", str(page.get("url", "")))
            item["message"] = f"画面がエラー（{status}）を返したため、中身を取得できませんでした。"
            out.append(item)
    return out


def list_versions(domain_dir: Path) -> list[dict[str, Any]]:
    snaps = domain_dir / "snapshots"
    versions: list[dict[str, Any]] = []
    for f in sorted(snaps.glob("*.json"), reverse=True) if snaps.is_dir() else []:
        try:
            pages = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("版の読み込みに失敗しました: %s", f)
            continue
        stem = f.stem
        label = f"{stem[0:4]}-{stem[4:6]}-{stem[6:8]} {stem[9:11]}:{stem[11:13]}" if len(stem) >= 13 else stem
        versions.append({"id": stem, "label": label, "screens": len(pages), "path": f})
    return versions


def _diff_items(old: Path, new: Path) -> list[dict[str, str]]:
    src = str(Path("src").resolve())
    if src not in sys.path:
        sys.path.insert(0, src)
    from diff.differ import compute_diff
    from diff.snapshot import load_snapshot

    d = compute_diff(load_snapshot(old), load_snapshot(new))
    kind_ja = {"added": "追加", "removed": "削除", "modified": "変更"}
    items = [{"kind": "画面の追加", "where": p.url, "detail": ""} for p in d.added_pages]
    items += [{"kind": "画面の削除", "where": p.url, "detail": ""} for p in d.removed_pages]
    items += [
        {"kind": f"入力項目の{kind_ja.get(c.change_type, c.change_type)}", "where": c.page_url, "detail": c.field_name}
        for c in d.field_changes
    ]
    items += [{"kind": "画面名の変更", "where": t.url, "detail": f"{t.before} → {t.after}"} for t in d.title_changes]
    items += [
        {"kind": f"リンクの{kind_ja.get(c.change_type, c.change_type)}", "where": c.page_url, "detail": c.link}
        for c in d.link_changes
    ]
    items += [
        {"kind": f"API の{kind_ja.get(c.change_type, c.change_type)}", "where": c.page_url, "detail": f"{c.method} {c.path}"}
        for c in d.api_changes
    ]
    return items


def _provenance(report: dict[str, Any], failures: list[dict[str, str]]) -> list[dict[str, Any]]:
    screens = report.get("screens") or []
    fields = sum(len(fm.get("fields", [])) for s in screens for fm in s.get("forms", []))
    observed = len(screens)
    return [
        {"artifact": "画面一覧", "basis": "観測", "count": observed, "note": "クロールで実際に開いた画面"},
        {"artifact": "仕様書（入力項目）", "basis": "観測", "count": fields, "note": "画面の入力欄から取得"},
        {"artifact": "画面遷移", "basis": "観測", "count": sum(len((s.get("transitions") or {}).get("to", [])) for s in screens), "note": "画面内のリンクから取得"},
        {"artifact": "テストケース", "basis": "推論", "count": None, "note": "観測した画面と入力項目から生成。人の確認が必要"},
        {"artifact": "取得できなかった画面", "basis": "未確認", "count": len(failures), "note": "中身を見ていないため、仕様書に含まれていない"},
    ]


def build_site_versions(domain_dir: Path) -> dict[str, Any]:
    """版・今回の変更分・区分・失敗・判定帯をまとめて返す（読むだけ。何も書き込まない）。"""
    report: dict[str, Any] = {}
    try:
        report = json.loads((domain_dir / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = {}
    meta = report.get("meta") or {}
    failures = collect_failures(domain_dir)
    versions = list_versions(domain_dir)
    failures += _http_failures(versions[0]["path"] if versions else None, failures)
    if not report and not versions:
        fails = failures or [_failure("no_pages")]
        return {
            "state": "error",
            "target": "",
            "versions": [],
            "failures": fails,
            "verdict": {
                "overall": {"result": UNDECIDABLE, "named": [f["message"] for f in fails]},
                "change": {"result": UNJUDGED, "named": ["比較できる版がありません。"]},
            },
            "change_items": [],
            "provenance": [],
        }
    change_items: list[dict[str, str]] = []
    if len(versions) >= 2:
        try:
            change_items = _diff_items(versions[1]["path"], versions[0]["path"])
            change = (
                {"result": UNJUDGED, "named": [f"{i['kind']}: {i['detail'] or i['where']}" for i in change_items]}
                if change_items
                else {"result": PASS, "named": ["前回の版から変更はありません。"]}
            )
        except Exception:  # noqa: BLE001  # 壊れた版の形は事前に絞れない。「変更なし」と誤って言わない
            logger.exception("版の比較に失敗しました: %s", domain_dir)
            change = {"result": UNDECIDABLE, "named": ["前回の版と比較できませんでした。再解析してください。"]}
    else:
        change = {"result": UNJUDGED, "named": ["比較する前回の版がありません。もう一度解析すると差分が出ます。"]}
    overall = (
        {"result": UNDECIDABLE, "named": [f"未確認: {f['url'] or '対象'}（{f['message']}）" for f in failures]}
        if failures
        else {"result": PASS, "named": ["到達できた画面はすべて取得しました。"]}
    )
    return {
        "state": "normal",
        "target": str(meta.get("target_url", "")),
        "crawled_at": str(meta.get("crawled_at", "")),
        "versions": [{k: v for k, v in ver.items() if k != "path"} for ver in versions],
        "current_version": versions[0]["id"] if versions else "",
        "previous_version": versions[1]["id"] if len(versions) >= 2 else "",
        "failures": failures,
        "change_items": change_items,
        "provenance": _provenance(report, failures),
        "verdict": {"overall": overall, "change": change},
    }
