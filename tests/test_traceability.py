"""トレーサビリティマトリクス サービスのテスト"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from web.services.traceability import (
    RequirementLink,
    TraceabilityMatrix,
    build_matrix,
    matrix_to_dict,
)


# ──────────────────────────────────────────────
# ヘルパー
# ──────────────────────────────────────────────

def _make_report(screens: list[dict]) -> dict:
    return {"screens": screens}


def _make_candidates(entries: list[dict]) -> list[dict]:
    """entries は [{"id": ..., "steps": [{"url": ...}, ...]}] のリスト。"""
    return entries


# ──────────────────────────────────────────────
# build_matrix
# ──────────────────────────────────────────────

def test_build_matrix_covered_when_url_matches() -> None:
    """candidates に URL が完全一致する場合 covered になる。"""
    report = _make_report([{"url": "https://example.com/login", "title": "ログイン"}])
    candidates = _make_candidates(
        [{"id": "TC001", "steps": [{"url": "https://example.com/login"}]}]
    )

    matrix = build_matrix("example.com", report, candidates)

    assert matrix.total_requirements == 1
    assert matrix.requirements[0].coverage == "covered"
    assert "TC001" in matrix.requirements[0].test_ids


def test_build_matrix_uncovered_when_no_match() -> None:
    """candidates が空なら全件 uncovered。"""
    report = _make_report(
        [
            {"url": "https://example.com/", "title": "トップ"},
            {"url": "https://example.com/about", "title": "概要"},
        ]
    )

    matrix = build_matrix("example.com", report, [])

    assert matrix.total_requirements == 2
    assert all(r.coverage == "uncovered" for r in matrix.requirements)
    assert matrix.covered_count == 0
    assert matrix.coverage_rate == 0.0


def test_build_matrix_coverage_rate() -> None:
    """2 要件のうち 1 件が covered → coverage_rate = 0.5。"""
    report = _make_report(
        [
            {"url": "https://example.com/a", "title": "A"},
            {"url": "https://example.com/b", "title": "B"},
        ]
    )
    candidates = _make_candidates(
        [{"id": "TC001", "steps": [{"url": "https://example.com/a"}]}]
    )

    matrix = build_matrix("example.com", report, candidates)

    assert matrix.coverage_rate == 0.5
    assert matrix.covered_count == 1
    assert matrix.total_requirements == 2


def test_build_matrix_partial_when_prefix_match() -> None:
    """URL が前方一致（完全一致なし）の場合は partial になる。"""
    report = _make_report([{"url": "https://example.com/items", "title": "一覧"}])
    candidates = _make_candidates(
        [{"id": "TC002", "steps": [{"url": "https://example.com/items/123"}]}]
    )

    matrix = build_matrix("example.com", report, candidates)

    assert matrix.requirements[0].coverage == "partial"
    assert "TC002" in matrix.requirements[0].test_ids


def test_build_matrix_assigns_req_ids_sequentially() -> None:
    """REQ-001, REQ-002, ... と連番が振られる。"""
    screens = [{"url": f"https://example.com/p{i}", "title": f"P{i}"} for i in range(3)]
    matrix = build_matrix("example.com", _make_report(screens), [])

    ids = [r.req_id for r in matrix.requirements]
    assert ids == ["REQ-001", "REQ-002", "REQ-003"]


def test_build_matrix_empty_screens_returns_zero_coverage_rate() -> None:
    """screens が空のとき coverage_rate は 0.0（ゼロ除算しない）。"""
    matrix = build_matrix("example.com", _make_report([]), [])

    assert matrix.total_requirements == 0
    assert matrix.coverage_rate == 0.0


def test_build_matrix_multiple_candidates_same_url() -> None:
    """同じ URL を参照する候補が複数あるとき、両方の ID が test_ids に含まれる。"""
    report = _make_report([{"url": "https://example.com/top", "title": "トップ"}])
    candidates = _make_candidates(
        [
            {"id": "TC-A", "steps": [{"url": "https://example.com/top"}]},
            {"id": "TC-B", "steps": [{"url": "https://example.com/top"}]},
        ]
    )

    matrix = build_matrix("example.com", report, candidates)

    req = matrix.requirements[0]
    assert req.coverage == "covered"
    assert "TC-A" in req.test_ids
    assert "TC-B" in req.test_ids


# ──────────────────────────────────────────────
# matrix_to_dict
# ──────────────────────────────────────────────

def test_matrix_to_dict_serializable() -> None:
    """dict 変換後に json.dumps できる（JSON シリアライズ可能）。"""
    report = _make_report([{"url": "https://example.com/", "title": "トップ"}])
    candidates = _make_candidates(
        [{"id": "TC001", "steps": [{"url": "https://example.com/"}]}]
    )
    matrix = build_matrix("example.com", report, candidates)

    d = matrix_to_dict(matrix)
    serialized = json.dumps(d)  # 例外が出なければ OK

    parsed = json.loads(serialized)
    assert parsed["domain"] == "example.com"
    assert parsed["total_requirements"] == 1
    assert parsed["covered_count"] == 1
    assert abs(parsed["coverage_rate"] - 1.0) < 1e-9


def test_matrix_to_dict_structure() -> None:
    """返却 dict のキー・型を検証する。"""
    report = _make_report([{"url": "https://example.com/x", "title": "X"}])
    matrix = build_matrix("example.com", report, [])

    d = matrix_to_dict(matrix)

    assert "domain" in d
    assert "generated_at" in d
    assert "requirements" in d
    assert isinstance(d["requirements"], list)
    req = d["requirements"][0]
    assert req["req_id"] == "REQ-001"
    assert req["coverage"] == "uncovered"
    assert isinstance(req["test_ids"], list)


def test_matrix_to_dict_test_ids_is_list() -> None:
    """test_ids が tuple ではなく list として返る。"""
    report = _make_report([{"url": "https://example.com/", "title": "T"}])
    candidates = _make_candidates(
        [{"id": "TC-X", "steps": [{"url": "https://example.com/"}]}]
    )
    matrix = build_matrix("example.com", report, candidates)

    d = matrix_to_dict(matrix)
    assert isinstance(d["requirements"][0]["test_ids"], list)


# ──────────────────────────────────────────────
# RequirementLink / TraceabilityMatrix dataclass
# ──────────────────────────────────────────────

def test_requirement_link_is_frozen() -> None:
    """RequirementLink は frozen dataclass（イミュータブル）。"""
    req = RequirementLink(
        req_id="REQ-001",
        req_title="テスト",
        test_ids=("TC001",),
        page_url="https://example.com/",
        coverage="covered",
    )
    try:
        req.req_id = "REQ-999"  # type: ignore[misc]
        assert False, "FrozenInstanceError が発生するはず"
    except Exception:
        pass  # frozen なので変更不可


def test_traceability_matrix_is_frozen() -> None:
    """TraceabilityMatrix は frozen dataclass。"""
    matrix = TraceabilityMatrix(
        domain="example.com",
        generated_at="2026-06-10T00:00:00+00:00",
        requirements=(),
        total_requirements=0,
        covered_count=0,
        coverage_rate=0.0,
    )
    try:
        matrix.domain = "other.com"  # type: ignore[misc]
        assert False, "FrozenInstanceError が発生するはず"
    except Exception:
        pass
