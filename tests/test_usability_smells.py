"""ユーザビリティスメル検出（第9弾 H）の契約。

守るべきは「実測イベントに根拠を持つこと」「改善提案をしないこと」
「兆候なしは検出しないこと」。
"""

from __future__ import annotations

from ux.usability_smells import (
    CLAIM_NOTICE,
    SMELL_EXCESSIVE_SCROLL,
    SMELL_FORM_ABANDON,
    SMELL_MISCLICK,
    SMELL_POGO_STICKING,
    detect_smells,
)


def _click(path, selector, reacted=False):
    e = {"session": "s1", "action_type": "click", "path": path, "selector": selector}
    if reacted:
        e["state_id"] = "modal-1"
    return e


def _nav(path):
    return {"session": "s1", "kind": "navigate", "path": path}


def _by_type(result, kind):
    return [s for s in result["smells"] if s["type"] == kind]


# ─────────────────── 誤クリック ───────────────────


def test_repeated_unreacting_clicks_are_flagged() -> None:
    events = [_click("/p", "#dead", reacted=False) for _ in range(3)]

    smells = _by_type(detect_smells(events), SMELL_MISCLICK)

    assert len(smells) == 1
    assert smells[0]["occurrences"] == 3


def test_reacting_clicks_are_not_misclicks() -> None:
    events = [_click("/p", "#ok", reacted=True) for _ in range(3)]

    assert _by_type(detect_smells(events), SMELL_MISCLICK) == []


def test_two_clicks_below_threshold() -> None:
    events = [_click("/p", "#x") for _ in range(2)]

    assert _by_type(detect_smells(events), SMELL_MISCLICK) == []


# ─────────────────── フォーム離脱 ───────────────────


def test_input_then_navigate_away_is_abandonment() -> None:
    events = [
        {"session": "s1", "action_type": "input", "path": "/form", "selector": "#email"},
        _nav("/other"),
    ]

    smells = _by_type(detect_smells(events), SMELL_FORM_ABANDON)

    assert len(smells) == 1
    assert smells[0]["path"] == "/form"


def test_input_then_submit_is_not_abandonment() -> None:
    events = [
        {"session": "s1", "action_type": "input", "path": "/form", "selector": "#email"},
        {"session": "s1", "action_type": "submit", "path": "/form"},
        _nav("/thanks"),
    ]

    assert _by_type(detect_smells(events), SMELL_FORM_ABANDON) == []


# ─────────────────── 行き来 ───────────────────


def test_a_b_a_navigation_is_pogo_sticking() -> None:
    events = [_nav("/a"), _nav("/b"), _nav("/a")]

    smells = _by_type(detect_smells(events), SMELL_POGO_STICKING)

    assert len(smells) == 1
    assert smells[0]["path"] == "/a"
    assert smells[0]["via"] == "/b"


def test_linear_navigation_is_not_pogo() -> None:
    events = [_nav("/a"), _nav("/b"), _nav("/c")]

    assert _by_type(detect_smells(events), SMELL_POGO_STICKING) == []


# ─────────────────── 過剰スクロール ───────────────────


def test_many_scrolls_before_action_flagged() -> None:
    events = [{"session": "s1", "action_type": "scroll", "path": "/long"} for _ in range(5)]
    events.append({"session": "s1", "action_type": "click", "path": "/long", "selector": "#cta"})

    smells = _by_type(detect_smells(events), SMELL_EXCESSIVE_SCROLL)

    assert len(smells) == 1
    assert smells[0]["occurrences"] == 5


def test_few_scrolls_not_flagged() -> None:
    events = [{"session": "s1", "action_type": "scroll", "path": "/p"} for _ in range(2)]
    events.append({"session": "s1", "action_type": "click", "path": "/p", "selector": "#x"})

    assert _by_type(detect_smells(events), SMELL_EXCESSIVE_SCROLL) == []


# ─────────────────── 全体 ───────────────────


def test_empty_events_yield_no_smells() -> None:
    result = detect_smells([])

    assert result["smells"] == []
    assert result["summary"]["total"] == 0


def test_claim_scope_and_no_suggestion_field() -> None:
    result = detect_smells([_click("/p", "#dead") for _ in range(3)])

    assert result["meta"]["claim_notice"] == CLAIM_NOTICE
    for smell in result["smells"]:
        assert "evidence" in smell
        assert "suggestion" not in smell and "fix" not in smell


def test_each_smell_carries_evidence() -> None:
    result = detect_smells([_click("/p", "#dead") for _ in range(4)])

    assert all(s.get("evidence") for s in result["smells"])
