"""定数を直接 import して境界を検証するテスト（R-10）。

リテラルを再記載したテストは、定数を変えても赤くならないため境界の保護にならない。
本ファイルは全アサーションで定数そのものを参照し、定数を変更したら失敗する形にする。
境界は ISTQB の境界値分析に従い「内側・境界そのもの・外側」の 3 点を押さえる。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.robotparser import RobotFileParser

import main
from autorun.suggest import MAX_EXISTING_SHOWN, _prompt
from crawler.network_interceptor import (
    MAX_RESPONSE_BODY_BYTES,
    SAMPLE_FIELDS_LIMIT,
    _extract_response_fields,
)
from crawler.page_crawler import DEFAULT_DEPTH, DEFAULT_MAX_PAGES, crawl_site, known_total
from main import MAX_PARALLELISM
from mbt.pairwise import MAX_FACTORS, MIN_FACTORS, extract_factors, generate_pairwise_rows
from viewport.layout_failures import (
    COLLISION_MIN_OVERLAP_PX,
    PROTRUSION_TOLERANCE_PX,
    detect_element_collision,
    detect_viewport_protrusion,
)

# ---------------------------------------------------------------------------
# main.MAX_PARALLELISM (src/main.py:60)
# 使用箇所: max(1, min(int(args.parallelism), MAX_PARALLELISM))  (src/main.py:804/823)
# ---------------------------------------------------------------------------


def _captured_parallelism(monkeypatch, requested: int) -> int:
    """_do_crawl が crawl_urls へ渡す parallelism を捕捉する。"""
    captured: dict[str, int] = {}

    def _fake_crawl_urls(*_args, **kwargs):
        captured["parallelism"] = int(kwargs["parallelism"])
        return []

    monkeypatch.setattr(main, "crawl_urls", _fake_crawl_urls)
    main._do_crawl(
        argparse.Namespace(parallelism=requested),
        ["https://example.com/"],
        "https://example.com/",
        Path("."),
        None,
    )
    return captured["parallelism"]


def test_parallelism_below_max_is_not_clamped(monkeypatch) -> None:
    """境界の内側: 上限未満はそのまま通る。"""
    assert _captured_parallelism(monkeypatch, MAX_PARALLELISM - 1) == MAX_PARALLELISM - 1


def test_parallelism_at_max_is_accepted(monkeypatch) -> None:
    """境界そのもの: 上限ちょうどは許可される（off-by-one で弾かれない）。"""
    assert _captured_parallelism(monkeypatch, MAX_PARALLELISM) == MAX_PARALLELISM


def test_parallelism_above_max_is_clamped_to_max(monkeypatch) -> None:
    """境界の外側: 上限超過は上限へ丸められる。"""
    assert _captured_parallelism(monkeypatch, MAX_PARALLELISM + 1) == MAX_PARALLELISM
    assert _captured_parallelism(monkeypatch, MAX_PARALLELISM * 10) == MAX_PARALLELISM


def test_parallelism_lower_bound_is_one(monkeypatch) -> None:
    """下側の境界: 0 と負値は 1 へ引き上げられる（ワーカー 0 で無限待ちにしない）。"""
    assert _captured_parallelism(monkeypatch, 0) == 1
    assert _captured_parallelism(monkeypatch, -MAX_PARALLELISM) == 1


# ---------------------------------------------------------------------------
# crawler.page_crawler.DEFAULT_MAX_PAGES (src/crawler/page_crawler.py:44)
# 使用箇所: known_total() の頭打ち (同 :1286) / crawl_site の既定値 (同 :294)
# ---------------------------------------------------------------------------


def _known_total(completed: int, max_pages: int) -> int:
    return known_total(
        completed,
        0,
        (),
        set(),
        max_pages,
        max_depth=DEFAULT_DEPTH,
        robots=RobotFileParser(),
    )


def test_known_total_below_default_max_pages_is_untouched() -> None:
    """境界の内側: 既定上限未満は実数がそのまま出る。"""
    assert _known_total(DEFAULT_MAX_PAGES - 1, DEFAULT_MAX_PAGES) == DEFAULT_MAX_PAGES - 1


def test_known_total_at_default_max_pages_is_untouched() -> None:
    """境界そのもの: 既定上限ちょうどは丸められない。"""
    assert _known_total(DEFAULT_MAX_PAGES, DEFAULT_MAX_PAGES) == DEFAULT_MAX_PAGES


def test_known_total_above_default_max_pages_is_capped() -> None:
    """境界の外側: 既定上限超過は上限で頭打ちになる。"""
    assert _known_total(DEFAULT_MAX_PAGES + 1, DEFAULT_MAX_PAGES) == DEFAULT_MAX_PAGES


def test_known_total_never_reports_zero() -> None:
    """下側の境界: 進捗分母が 0 になると割り算側が壊れるため 1 が下限。"""
    assert _known_total(0, DEFAULT_MAX_PAGES) == 1


def test_crawl_site_default_max_pages_is_the_constant() -> None:
    """既定値の契約: 署名の既定が定数と切り離されていないこと。"""
    import inspect

    default = inspect.signature(crawl_site).parameters["max_pages"].default
    assert default == DEFAULT_MAX_PAGES


# ---------------------------------------------------------------------------
# viewport.layout_failures.PROTRUSION_TOLERANCE_PX (src/viewport/layout_failures.py:26)
# 使用箇所: right > viewport_width + PROTRUSION_TOLERANCE_PX (同 :34-37)
# ---------------------------------------------------------------------------

_VIEWPORT_WIDTH = 1280


def _protrusion_count(width: int) -> int:
    boxes = [{"selector": "#target", "x": 0, "y": 0, "w": width, "h": 10}]
    return len(detect_viewport_protrusion(boxes, _VIEWPORT_WIDTH))


def test_protrusion_inside_tolerance_is_not_reported() -> None:
    """境界の内側: 許容量に満たないはみ出しは故障にしない。"""
    assert _protrusion_count(_VIEWPORT_WIDTH + PROTRUSION_TOLERANCE_PX - 1) == 0


def test_protrusion_exactly_at_tolerance_is_not_reported() -> None:
    """境界そのもの: 許容量ちょうどは AA/border 由来として除外する。"""
    assert _protrusion_count(_VIEWPORT_WIDTH + PROTRUSION_TOLERANCE_PX) == 0


def test_protrusion_beyond_tolerance_is_reported() -> None:
    """境界の外側: 許容量を 1px でも超えたら記録する。"""
    assert _protrusion_count(_VIEWPORT_WIDTH + PROTRUSION_TOLERANCE_PX + 1) == 1


# ---------------------------------------------------------------------------
# viewport.layout_failures.COLLISION_MIN_OVERLAP_PX (src/viewport/layout_failures.py:25)
# 使用箇所: dx >= COLLISION_MIN_OVERLAP_PX and dy >= COLLISION_MIN_OVERLAP_PX (同 :61)
# ---------------------------------------------------------------------------


def _collision_count(overlap_px: int) -> int:
    side = 100
    boxes = [
        {"selector": "#a", "x": 0, "y": 0, "w": side, "h": side, "interactive": True},
        {
            "selector": "#b",
            "x": side - overlap_px,
            "y": side - overlap_px,
            "w": side,
            "h": side,
            "interactive": True,
        },
    ]
    return len(detect_element_collision(boxes))


def test_collision_below_min_overlap_is_not_reported() -> None:
    """境界の内側: 下限未満の重なりは故障にしない。"""
    assert _collision_count(COLLISION_MIN_OVERLAP_PX - 1) == 0


def test_collision_exactly_at_min_overlap_is_reported() -> None:
    """境界そのもの: 下限ちょうどは検出対象（判定は >= のため）。"""
    assert _collision_count(COLLISION_MIN_OVERLAP_PX) == 1


def test_collision_above_min_overlap_is_reported() -> None:
    """境界の外側: 下限超過は当然検出される。"""
    assert _collision_count(COLLISION_MIN_OVERLAP_PX + 1) == 1


# ---------------------------------------------------------------------------
# mbt.pairwise.MAX_FACTORS / MIN_FACTORS (src/mbt/pairwise.py:20-21)
# 使用箇所: factors[:MAX_FACTORS] (同 :45) / len(factors) < MIN_FACTORS (同 :57)
# ---------------------------------------------------------------------------


def _screen_with_fields(count: int) -> dict[str, object]:
    return {
        "forms": [
            {
                "fields": [
                    {
                        "name": f"field{index:03d}",
                        "field_type": "select",
                        "options": ["a", "b"],
                    }
                    for index in range(count)
                ]
            }
        ]
    }


def test_extract_factors_below_max_keeps_all() -> None:
    """境界の内側: 上限未満は 1 件も落とさない。"""
    factors = extract_factors(_screen_with_fields(MAX_FACTORS - 1))
    assert len(factors) == MAX_FACTORS - 1


def test_extract_factors_at_max_keeps_all() -> None:
    """境界そのもの: 上限ちょうどは切り捨てられない。"""
    factors = extract_factors(_screen_with_fields(MAX_FACTORS))
    assert len(factors) == MAX_FACTORS


def test_extract_factors_above_max_is_truncated() -> None:
    """境界の外側: 上限超過は上限件数へ切り捨てられる。"""
    factors = extract_factors(_screen_with_fields(MAX_FACTORS + 1))
    assert len(factors) == MAX_FACTORS


def _factors(count: int) -> list[dict[str, object]]:
    return [
        {"name": f"f{index}", "field_type": "select", "values": ["a", "b"]}
        for index in range(count)
    ]


def test_pairwise_below_min_factors_yields_no_rows() -> None:
    """境界の内側（下限側の外）: ペアが成立しない因子数では行を作らない。"""
    assert generate_pairwise_rows(_factors(MIN_FACTORS - 1)) == []


def test_pairwise_at_min_factors_yields_rows() -> None:
    """境界そのもの: 下限ちょうどでは行が生成される。"""
    rows = generate_pairwise_rows(_factors(MIN_FACTORS))
    assert rows
    assert all(len(row) == MIN_FACTORS for row in rows)


# ---------------------------------------------------------------------------
# crawler.network_interceptor.MAX_RESPONSE_BODY_BYTES / SAMPLE_FIELDS_LIMIT
# (src/crawler/network_interceptor.py:44-45)
# 使用箇所: len(body) > MAX_RESPONSE_BODY_BYTES (同 :266) / keys[:SAMPLE_FIELDS_LIMIT] (同 :270)
# ---------------------------------------------------------------------------


class _StubResponse:
    """_extract_response_fields が触るのは body() だけなので最小限を模す。"""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def body(self) -> bytes:
        return self._body


def _json_body_of_size(size: int) -> bytes:
    prefix = b'{"k": "'
    suffix = b'"}'
    return prefix + b"x" * (size - len(prefix) - len(suffix)) + suffix


def test_response_body_below_limit_is_parsed() -> None:
    """境界の内側: 上限未満のボディは解析される。"""
    body = _json_body_of_size(MAX_RESPONSE_BODY_BYTES - 1)
    assert len(body) == MAX_RESPONSE_BODY_BYTES - 1
    assert _extract_response_fields(_StubResponse(body)) == ("k",)


def test_response_body_exactly_at_limit_is_parsed() -> None:
    """境界そのもの: 上限ちょうどは捨てない（判定は > のため）。"""
    body = _json_body_of_size(MAX_RESPONSE_BODY_BYTES)
    assert len(body) == MAX_RESPONSE_BODY_BYTES
    assert _extract_response_fields(_StubResponse(body)) == ("k",)


def test_response_body_above_limit_is_skipped() -> None:
    """境界の外側: 上限超過は解析せず空を返す。"""
    body = _json_body_of_size(MAX_RESPONSE_BODY_BYTES + 1)
    assert len(body) == MAX_RESPONSE_BODY_BYTES + 1
    assert _extract_response_fields(_StubResponse(body)) == ()


def _fields_for_key_count(count: int) -> tuple[str, ...]:
    payload = {f"k{index:03d}": index for index in range(count)}
    return _extract_response_fields(_StubResponse(json.dumps(payload).encode("utf-8")))


def test_sample_fields_below_limit_keeps_all() -> None:
    """境界の内側: 上限未満のキーは全部返る。"""
    assert len(_fields_for_key_count(SAMPLE_FIELDS_LIMIT - 1)) == SAMPLE_FIELDS_LIMIT - 1


def test_sample_fields_at_limit_keeps_all() -> None:
    """境界そのもの: 上限ちょうどは切り捨てられない。"""
    assert len(_fields_for_key_count(SAMPLE_FIELDS_LIMIT)) == SAMPLE_FIELDS_LIMIT


def test_sample_fields_above_limit_is_truncated() -> None:
    """境界の外側: 上限超過は上限件数へ切り捨てられる。"""
    assert len(_fields_for_key_count(SAMPLE_FIELDS_LIMIT + 1)) == SAMPLE_FIELDS_LIMIT


# ---------------------------------------------------------------------------
# autorun.suggest.MAX_EXISTING_SHOWN (src/autorun/suggest.py:24)
# 使用箇所: existing[:MAX_EXISTING_SHOWN] (同 :78)
# ---------------------------------------------------------------------------


def _prompt_for_existing_count(count: int) -> str:
    existing = [f"既存項目{index:03d}" for index in range(count)]
    return _prompt("観点", "目的", "文脈", existing)


def test_existing_items_below_limit_are_all_listed() -> None:
    """境界の内側: 上限未満は全件がプロンプトに載る。"""
    prompt = _prompt_for_existing_count(MAX_EXISTING_SHOWN - 1)
    assert f"既存項目{MAX_EXISTING_SHOWN - 2:03d}" in prompt


def test_existing_items_at_limit_are_all_listed() -> None:
    """境界そのもの: 上限ちょうどの最後の 1 件も落ちない。"""
    prompt = _prompt_for_existing_count(MAX_EXISTING_SHOWN)
    assert f"既存項目{MAX_EXISTING_SHOWN - 1:03d}" in prompt


def test_existing_items_above_limit_are_dropped() -> None:
    """境界の外側: 上限超過分はプロンプトから落ちる。"""
    prompt = _prompt_for_existing_count(MAX_EXISTING_SHOWN + 1)
    assert f"既存項目{MAX_EXISTING_SHOWN - 1:03d}" in prompt
    assert f"既存項目{MAX_EXISTING_SHOWN:03d}" not in prompt
