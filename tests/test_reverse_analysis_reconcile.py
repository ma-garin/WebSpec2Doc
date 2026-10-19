"""reverse analysis の限定突合の契約。

method/path の一致は同一性の証明ではない。既存 snapshot には API の origin が
無いため、一意に一致しても inferred に留め、matched を出さない。
複数候補・動的式・query 依存は候補と理由を落とさずに ambiguous / unknown にする。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crawler.page_crawler import ApiEndpoint, PageData
from diff.snapshot import save_snapshot
from reverse_analysis.models import (
    Relation,
    RuntimeObservation,
    SourceLocation,
    StaticCandidate,
    static_candidate_id,
    to_json_value,
)
from reverse_analysis.reconcile import reconcile, summarize
from reverse_analysis.runtime import load_runtime_observations

_DIGEST = "a" * 64


def _candidate(
    line: int,
    method: str | None = "GET",
    path: str | None = "/api/orders",
    *,
    kind: str = "api",
    resolution: str = "exact",
    origin: str | None = None,
    query_dependent: bool = False,
) -> StaticCandidate:
    location = SourceLocation("src/app.js", "line_column_utf16", line, 0, line, 10)
    return StaticCandidate(
        id=static_candidate_id(_DIGEST, location, kind),
        kind=kind,
        artifact_path="src/app.js",
        artifact_sha256=_DIGEST,
        location=location,
        resolution=resolution,
        epistemic_state="observed",
        authority="static_syntax",
        method=method,
        origin=origin,
        path=path,
        expression=None,
        query_dependent=query_dependent,
    )


def _observation(
    index: int, method: str = "GET", path: str = "/api/orders", status: int = 200
) -> RuntimeObservation:
    return RuntimeObservation(
        id=f"ro-{index:04d}",
        snapshot_sha256="b" * 64,
        json_pointer=f"/0/api_calls/{index}",
        page_url="https://app.example.com/orders",
        method=method,
        path=path,
        status_code=status,
        content_type="application/json",
        sample_fields=(),
    )


def _only(relations: tuple[Relation, ...], classification: str) -> list[Relation]:
    return [r for r in relations if r.classification == classification]


def test_method_path一意一致でもmatchedにせずinferredと欠測理由を残す() -> None:
    candidate = _candidate(1)
    observation = _observation(0)

    relations = reconcile([candidate], [observation])

    assert len(relations) == 1
    relation = relations[0]
    assert relation.classification == "inferred"
    assert relation.epistemic_state == "inferred"
    assert relation.basis == "method_path_only"
    assert "runtime_origin_not_recorded" in relation.limitations
    assert relation.static_ids == (candidate.id,)
    assert relation.runtime_ids == (observation.id,)
    assert summarize([candidate], [observation], relations).matched_relations == 0


def test_既存snapshot由来の観測ではmatchedが0件になる(tmp_path: Path) -> None:
    """実ファイル→load_snapshot→build_screen_api_map の経路で origin 欠測を確かめる。"""
    page = PageData(
        url="https://app.example.com/orders",
        title="注文",
        headings=(),
        links=(),
        forms=(),
        screenshot_path=None,
        api_calls=(
            ApiEndpoint("GET", "/api/orders", 200, "application/json", ("id",)),
            ApiEndpoint("DELETE", "/api/orders/1", 204, "", ()),
        ),
    )
    runtime = load_runtime_observations(save_snapshot([page], tmp_path))
    candidates = [
        _candidate(1, "get", "/api/orders", origin="https://app.example.com"),
        _candidate(2, "DELETE", "/api/orders/1"),
    ]

    relations = reconcile(candidates, runtime.observations)
    summary = summarize(candidates, runtime.observations, relations)

    assert summary.matched_relations == 0
    assert summary.inferred_relations == 2
    assert summary.observed_api_records == 2
    assert all(r.classification != "matched" for r in relations)


def test_複数候補はambiguousで候補IDを全て保持する() -> None:
    first = _candidate(1, origin="https://a.example")
    second = _candidate(2, origin="https://b.example")
    observation = _observation(0)

    relations = reconcile([first, second], [observation])

    assert len(relations) == 1
    assert relations[0].classification == "ambiguous"
    assert set(relations[0].static_ids) == {first.id, second.id}
    assert relations[0].runtime_ids == (observation.id,)
    assert "multiple_static_candidates" in relations[0].limitations


def test_status違いの複数観測を一件へ潰さずambiguousにする() -> None:
    candidate = _candidate(1)
    observations = [_observation(0, status=200), _observation(1, status=500)]

    relations = reconcile([candidate], observations)

    assert len(relations) == 1
    assert relations[0].classification == "ambiguous"
    assert relations[0].runtime_ids == ("ro-0000", "ro-0001")
    assert "multiple_runtime_observations" in relations[0].limitations


@pytest.mark.parametrize(
    ("candidate", "basis"),
    [
        (_candidate(1, resolution="partial"), "dynamic_expression"),
        (_candidate(1, path="/api/orders/${id}"), "dynamic_expression"),
        (_candidate(1, method=None), "method_missing"),
        (_candidate(1, method=""), "method_missing"),
        (_candidate(1, query_dependent=True), "query_dependent"),
        (_candidate(1, path="/api/orders?page=1"), "query_dependent"),
        (_candidate(1, path=None), "path_unresolved"),
    ],
)
def test_動的式_method欠損_query依存はunknownで候補と理由を残す(
    candidate: StaticCandidate, basis: str
) -> None:
    """method 欠損を GET と推定して GET の観測へ寄せない。"""
    observation = _observation(0)

    relations = reconcile([candidate], [observation])

    unknown_static = [r for r in relations if r.static_ids == (candidate.id,)]
    assert len(unknown_static) == 1
    assert unknown_static[0].classification == "unknown"
    assert unknown_static[0].epistemic_state == "unknown"
    assert unknown_static[0].basis == basis
    assert unknown_static[0].runtime_ids == ()
    runtime_only = [r for r in relations if r.runtime_ids == (observation.id,)]
    assert runtime_only[0].basis == "runtime_only"


@pytest.mark.parametrize("path", ["/api/orders/", "/api/%6Frders", "/v1/api/orders"])
def test_pathを正規化や補完で一致させない(path: str) -> None:
    relations = reconcile([_candidate(1, path=path)], [_observation(0)])

    assert _only(relations, "ambiguous") == []
    assert [r.basis for r in _only(relations, "inferred")] == ["static_only"]
    assert [r.basis for r in _only(relations, "unknown")] == ["runtime_only"]


def test_静的のみは未観測の推論で実測のみはobserved記録を保ちunknown() -> None:
    candidate = _candidate(1, "POST", "/api/export")
    observation = _observation(0, "GET", "/api/health")

    relations = reconcile([candidate], [observation])

    static_only = [r for r in relations if r.basis == "static_only"]
    runtime_only = [r for r in relations if r.basis == "runtime_only"]
    assert static_only[0].classification == "inferred"
    assert "not_observed_in_runtime_snapshot" in static_only[0].limitations
    assert runtime_only[0].classification == "unknown"
    assert runtime_only[0].runtime_ids == (observation.id,)
    assert observation.epistemic_state == "observed"


def test_未観測の同一method_path候補を一件へ潰さない() -> None:
    first = _candidate(1, origin="https://a.example")
    second = _candidate(2, origin="https://b.example")

    relations = reconcile([first, second], [])

    assert sorted(r.static_ids for r in relations) == sorted([(first.id,), (second.id,)])


def test_API以外の候補はruntimeと比較しない() -> None:
    route = _candidate(1, "GET", "/api/orders", kind="route")

    relations = reconcile([route], [_observation(0)])

    # route は関係不明（unknown）として残すが、runtime の API 観測とは結び付けない
    route_relations = [r for r in relations if route.id in r.static_ids]
    assert [(r.classification, r.runtime_ids) for r in route_relations] == [("unknown", ())]


def test_候補の推論状態を書き換えない() -> None:
    candidate = _candidate(1)
    before = to_json_value(candidate)

    reconcile([candidate], [_observation(0)])

    assert to_json_value(candidate) == before
    assert candidate.epistemic_state == "observed"


def test_入力順に関係なくIDと順序とJSONが同じ() -> None:
    candidates = [_candidate(1), _candidate(2, "POST", "/api/x"), _candidate(3, method=None)]
    observations = [_observation(0), _observation(1, "GET", "/api/y")]

    first = reconcile(candidates, observations)
    second = reconcile(list(reversed(candidates)), list(reversed(observations)))

    assert first == second
    assert json.dumps(to_json_value(first)) == json.dumps(to_json_value(second))


def test_候補IDは出典digestと位置とkindだけで決まる() -> None:
    assert _candidate(1).id == _candidate(1).id
    assert _candidate(1).id != _candidate(2).id
    assert _candidate(1).id != _candidate(1, kind="route").id


def test_重複IDの入力は拒否する() -> None:
    with pytest.raises(ValueError):
        reconcile([_candidate(1), _candidate(1)], [])


def test_位置の単位を混ぜたSourceLocationは作れない() -> None:
    with pytest.raises(ValueError):
        SourceLocation("a.js", "byte_range", start_line=1, start_byte=0, end_byte=3)
    with pytest.raises(ValueError):
        SourceLocation("a.js", "unknown")
