"""記録セッション → テスト資産の逆生成（キャプチャ Phase 2: リバース）。

テスターの探索セッション（sessions/session_*.jsonl）から、実演由来の
テストケース（手順＋観察結果）とビジネスフロー（confidence 1.0）を
逆生成する。LLM は使わず、記録されたイベント列をそのままテスト資産の
形式に変換するだけ（evidence-only 原則: 推定・言い換えをしない）。

セッション JSONL にはタイムスタンプが無いため、順序は行順のみが正。
「action の直後の state/visit」は同一セッション内で次に現れたイベントを
割り当てる近似であり、観察された事実として記録する（因果を断定しない）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from capture.session_recorder import normalize_footprint_path
from graph.transition_graph import BUSINESS_SCREEN_LABELS, PRIORITY_HIGH

logger = logging.getLogger(__name__)

RECORDED_ASSETS_FILE_NAME = "recorded_assets.json"
RECORDED_CANDIDATES_FILE_NAME = "recorded_candidates.json"
_UNMATCHED_NOTE = "クロール済みインベントリ未登録（未確認）"
_ACTION_VERBS = {"click": "クリック", "input": "入力"}


@dataclass(frozen=True)
class RecordedStep:
    """記録された 1 操作手順（実測 evidence 相当）。"""

    order: int
    description: str
    selector: str
    url: str
    observed: str = ""


@dataclass(frozen=True)
class RecordedTestCase:
    """1 探索セッションから逆生成された 1 テストケース。"""

    case_id: str
    session: str
    title: str
    steps: tuple[RecordedStep, ...]
    page_ids: tuple[str, ...]
    first_url: str = ""
    confidence: float = 1.0


def generate_recorded_assets(
    report: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    """セッションイベントからテストケースと記録フローを逆生成する。

    report は report.json の dict（screens の url/page_id/forms を
    画面照合・業務画面分類の入力に使う）。
    """
    screens = report.get("screens") or []
    path_index, screen_type_by_path = _build_screen_indices(screens)

    sessions: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        sessions.setdefault(str(event.get("session") or ""), []).append(event)

    test_cases: list[RecordedTestCase] = []
    flows: list[dict[str, Any]] = []
    for session_name in sorted(sessions):
        session_events = sessions[session_name]
        case = _build_case(session_name, session_events, path_index, len(test_cases) + 1)
        if case is None:
            logger.warning("visit イベントの無いセッションをスキップしました: %s", session_name)
            continue
        test_cases.append(case)
        flow = _build_flow(session_name, session_events, screen_type_by_path, len(flows) + 1)
        if flow is not None:
            flows.append(flow)

    return {
        "test_cases": [_case_to_dict(case) for case in test_cases],
        "flows": flows,
        "candidates": [_to_candidate(case) for case in test_cases],
    }


def save_recorded_assets(assets: dict[str, Any], output_dir: Path, domain: str = "") -> None:
    """recorded_assets.json と recorded_candidates.json を出力する。

    domain 省略時は出力先ディレクトリ名を使う（クロール出力の慣例と同じ）。
    """
    import json

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / RECORDED_ASSETS_FILE_NAME).write_text(
        json.dumps(
            {"test_cases": assets["test_cases"], "flows": assets["flows"]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / RECORDED_CANDIDATES_FILE_NAME).write_text(
        json.dumps(
            {"domain": domain or output_dir.name, "candidates": assets["candidates"]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _build_screen_indices(
    screens: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """report.json の screens から (正規化パス→画面dict) と (正規化パス→画面種別) を構築する。"""
    from llm.screen_classifier import classify_screen_by_rules

    path_index: dict[str, dict[str, Any]] = {}
    screen_type_by_path: dict[str, str] = {}
    for screen in screens:
        path = normalize_footprint_path(str(screen.get("url") or ""))
        path_index.setdefault(path, screen)
        title = str(screen.get("title") or "")
        headings = tuple(str(h) for h in screen.get("headings") or [])
        field_names = [
            str(field.get("name") or "")
            for form in screen.get("forms") or []
            for field in form.get("fields") or []
            if field.get("name")
        ]
        classification = classify_screen_by_rules(title, headings, field_names)
        screen_type_by_path.setdefault(path, classification.screen_type)
    return path_index, screen_type_by_path


def _build_case(
    session_name: str,
    session_events: list[dict[str, Any]],
    path_index: dict[str, dict[str, Any]],
    case_index: int,
) -> RecordedTestCase | None:
    steps: list[RecordedStep] = []
    page_ids: list[str] = []
    visited_paths: list[str] = []
    first_url = ""
    order = 0
    pending: RecordedStep | None = None
    has_visit = False

    for event in session_events:
        kind = event.get("kind")
        path = str(event.get("path") or "")
        if kind == "visit":
            has_visit = True
            if not first_url:
                first_url = str(event.get("url") or "")
            visited_paths.append(path)
            screen = path_index.get(path)
            if screen is not None:
                pid = str(screen.get("page_id") or "")
                if pid and pid not in page_ids:
                    page_ids.append(pid)
            if pending is not None:
                note = "" if screen is not None else f"（{_UNMATCHED_NOTE}）"
                addition = f"→ {path} へ遷移が観測された{note}"
                pending = replace(
                    pending,
                    observed=f"{pending.observed}; {addition}" if pending.observed else addition,
                )
                steps.append(pending)
                pending = None
        elif kind == "action":
            if pending is not None:
                steps.append(pending)
            order += 1
            selector = str(event.get("selector") or "")
            verb = _ACTION_VERBS.get(str(event.get("action_type") or ""), "操作")
            pending = RecordedStep(
                order=order,
                description=f"「{selector}」を{verb}",
                selector=selector,
                url=str(event.get("url") or ""),
            )
        elif kind == "state":
            state_id = str(event.get("state_id") or "")
            if pending is not None:
                addition = f"画面状態 {state_id} の出現が観測された"
                pending = replace(
                    pending,
                    observed=f"{pending.observed}; {addition}" if pending.observed else addition,
                )

    if pending is not None:
        steps.append(pending)

    if not has_visit:
        return None

    unique_paths = list(dict.fromkeys(visited_paths))
    title = (
        f"記録フロー: {' → '.join(unique_paths)}" if unique_paths else f"記録フロー: {session_name}"
    )
    return RecordedTestCase(
        case_id=f"RC{case_index:03d}",
        session=session_name,
        title=title,
        steps=tuple(steps),
        page_ids=tuple(page_ids),
        first_url=first_url,
    )


def _build_flow(
    session_name: str,
    session_events: list[dict[str, Any]],
    screen_type_by_path: dict[str, str],
    flow_index: int,
) -> dict[str, Any] | None:
    visit_events = [e for e in session_events if e.get("kind") == "visit"]
    business_types: list[str] = []
    for event in visit_events:
        screen_type = screen_type_by_path.get(str(event.get("path") or ""), "")
        if screen_type in BUSINESS_SCREEN_LABELS:
            if not business_types or business_types[-1] != screen_type:
                business_types.append(screen_type)
    if not business_types:
        return None
    flow_name = "→".join(BUSINESS_SCREEN_LABELS[t] for t in business_types)
    nodes = list(dict.fromkeys(str(e.get("url") or "") for e in visit_events))
    return {
        "flow_name": flow_name,
        "path_id": f"RCF-{flow_index:03d}",
        "nodes": nodes,
        "screen_types": business_types,
        "priority": PRIORITY_HIGH,
        "source": "recorded",
        "confidence": 1.0,
        "session": session_name,
    }


def _case_to_dict(case: RecordedTestCase) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "session": case.session,
        "title": case.title,
        "steps": [
            {
                "order": step.order,
                "description": step.description,
                "selector": step.selector,
                "url": step.url,
                "observed": step.observed,
            }
            for step in case.steps
        ],
        "page_ids": list(case.page_ids),
        "confidence": case.confidence,
    }


def _to_candidate(case: RecordedTestCase) -> dict[str, Any]:
    """RecordedTestCase を _pw_candidate 互換の dict に変換する。

    web/services/qa/advanced_html.py::_pw_candidate と同一キー構成
    （id/title/trace_id/automation_status/steps/expected/locator_strategy/
    review_status）にする。src 層から web 層へは依存しない方針
    （CONVENTIONS §1-1）のため、ヘルパー関数は複製せずここで直接組み立てる。
    """
    steps: list[str] = []
    if case.first_url:
        steps.append(f"page.goto('{case.first_url}')")
    steps.extend(step.description for step in case.steps)
    expected = case.steps[-1].observed if case.steps and case.steps[-1].observed else ""
    return {
        "id": case.case_id,
        "title": case.title,
        "trace_id": case.case_id,
        "automation_status": "auto" if case.steps else "manual-review",
        "steps": steps,
        "expected": expected,
        "locator_strategy": "記録されたセレクタをそのまま使用（実測・selector 変更時は要更新）",
        "review_status": "レビュー待ち",
    }
