"""レイアウト故障検知（第8弾 B）の契約。

守るべきは「包含を衝突と誤検知しないこと」「微小接触を故障と呼ばないこと」
「観測に留めバグ断定しないこと」。
"""

from __future__ import annotations

from viewport.layout_failures import (
    CLAIM_NOTICE,
    build_layout_failure_report,
    detect_element_collision,
    detect_viewport_protrusion,
)


def _box(selector, x, y, w, h, interactive=False):
    return {"selector": selector, "x": x, "y": y, "w": w, "h": h, "interactive": interactive}


# ─────────────────── Viewport Protrusion ───────────────────


def test_element_overflowing_viewport_is_detected() -> None:
    boxes = [_box("#wide", 0, 0, 500, 40)]

    result = detect_viewport_protrusion(boxes, viewport_width=390)

    assert len(result) == 1
    assert result[0]["overflow_px"] == 110.0


def test_element_within_viewport_is_clean() -> None:
    boxes = [_box("#ok", 0, 0, 380, 40)]

    assert detect_viewport_protrusion(boxes, viewport_width=390) == []


def test_two_pixel_overflow_is_tolerated() -> None:
    boxes = [_box("#edge", 0, 0, 391, 40)]  # 391 <= 390+2

    assert detect_viewport_protrusion(boxes, viewport_width=390) == []


# ─────────────────── Element Collision ───────────────────


def test_overlapping_interactive_elements_collide() -> None:
    boxes = [
        _box("#btn1", 0, 0, 100, 40, interactive=True),
        _box("#btn2", 50, 0, 100, 40, interactive=True),
    ]

    collisions = detect_element_collision(boxes)

    assert len(collisions) == 1
    assert collisions[0]["overlap_px2"] == 2000.0  # 50 x 40


def test_containment_is_not_a_collision() -> None:
    """ボタンがコンテナに含まれるのは正常。"""
    boxes = [
        _box("#container", 0, 0, 200, 100, interactive=True),
        _box("#inner-btn", 10, 10, 80, 30, interactive=True),
    ]

    assert detect_element_collision(boxes) == []


def test_tiny_touch_is_not_a_collision() -> None:
    """1-2px の接触（AA/border 由来）は故障と呼ばない。"""
    boxes = [
        _box("#a", 0, 0, 100, 40, interactive=True),
        _box("#b", 99, 0, 100, 40, interactive=True),  # 1px 重なり
    ]

    assert detect_element_collision(boxes) == []


def test_non_interactive_overlaps_are_ignored() -> None:
    boxes = [
        _box("#bg1", 0, 0, 100, 40, interactive=False),
        _box("#bg2", 50, 0, 100, 40, interactive=False),
    ]

    assert detect_element_collision(boxes) == []


# ─────────────────── レポート ───────────────────


def test_report_aggregates_per_viewport_with_claim_scope() -> None:
    observations = {
        "mobile": {
            "viewport_width": 390,
            "horizontal_overflow": True,
            "boxes": [_box("#wide", 0, 0, 500, 40)],
        },
        "desktop": {
            "viewport_width": 1366,
            "horizontal_overflow": False,
            "boxes": [_box("#ok", 0, 0, 1200, 40)],
        },
    }

    report = build_layout_failure_report(observations)

    assert report["meta"]["claim_notice"] == CLAIM_NOTICE
    assert report["summary"]["protrusions"] == 1
    mobile = next(v for v in report["viewports"] if v["viewport"] == "mobile")
    assert mobile["horizontal_overflow"] is True


def test_empty_observations_yield_zero_summary() -> None:
    report = build_layout_failure_report({})

    assert report["summary"] == {"protrusions": 0, "collisions": 0}


# ─────────────────── runner 統合 ───────────────────


def test_runner_produces_layout_failure_report(tmp_path) -> None:
    from crawler.page_crawler import PageData
    from viewport.runner import run_multi_viewport

    def _page(url, boxes, overflow):
        return PageData(
            url=url,
            title="T",
            headings=(),
            links=(),
            forms=(),
            screenshot_path="",
            element_boxes=tuple(boxes),
            horizontal_overflow=overflow,
        )

    def fake_crawl(url, *, depth, max_pages, output_dir, auth_state, viewport):
        if viewport.name == "mobile":
            return [_page(url, [_box("#wide", 0, 0, 800, 40)], True)]
        return [_page(url, [_box("#ok", 0, 0, 1000, 40)], False)]

    report = run_multi_viewport(
        "https://e.com/", tmp_path, viewports=["desktop", "mobile"], crawl_fn=fake_crawl
    )

    layout = report["layout_failures"]
    assert layout["summary"]["protrusions"] >= 1
    mobile = next(v for v in layout["viewports"] if v["viewport"] == "mobile")
    assert mobile["horizontal_overflow"] is True
