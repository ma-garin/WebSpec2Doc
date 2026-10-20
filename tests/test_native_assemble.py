"""native/evidence.py: 小さな JS 入力群から StaticNormalization が組み上がること。

パーサは差し替え、facts は手で用意する（解析器の正しさは別のテスト。ここは組立だけを見る）。
"""

import hashlib
import threading
from pathlib import Path

import pytest

from reverse_analysis.native import evidence
from reverse_analysis.native.facts import CallFact, ImportFact, ParsedFile, RouteFact
from reverse_analysis.normalize import SourceMapFinding


class FakeParser:
    """path ごとの facts を返す。bomb という名の JS は例外にする。"""

    def parse(self, path: str, source: bytes) -> ParsedFile:
        if path.endswith("bomb.js"):
            raise ValueError("boom")
        sha = hashlib.sha256(source).hexdigest()
        if path == "api.js":
            return ParsedFile(
                path, sha, imports=(ImportFact(path, 1, 0, 1, 24, "import x from './m'", "exact", "./m"),),
                calls=(CallFact(path, 2, 0, 2, 26, "fetch('/api/users')", "exact", "fetch", ("/api/users",)),),
                source_map_ref="api.js.map",
            )
        if path == "router.js":
            return ParsedFile(path, sha, routes=(
                RouteFact(path, 4, 2, 4, 30, "<Route path='/users'/>", "exact", "jsx", "Route", (("path", "/users"),)),
                RouteFact(path, 9, 2, 9, 30, "{path:'/a'}", "exact", "object", None,
                          (("path", "/a"), ("component", None)), "routes"),
            ))
        return ParsedFile(path, sha)


class FakeMapResult:
    def __init__(self, findings=(), map_path=None, map_sha256=None, sources=()):
        self.findings, self.map_path, self.map_sha256, self.sources = findings, map_path, map_sha256, sources


def _write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def _run(root: Path, **kwargs):
    return evidence.analyze(root, parser=FakeParser(), **kwargs)


@pytest.fixture
def site(tmp_path):
    _write(tmp_path, {
        "api.js": "import x from './m';\nfetch('/api/users')\n", "m.js": "export const a = 1;\n",
        "router.js": "// routes\n", "pages/about.js": "export default 1;\n", "notes.txt": "ignored",
    })
    return tmp_path


def test_assembles_api_route_module_and_graph(site):
    result = _run(site)
    norm = result.normalization
    assert result.status == "complete" and norm.status == "complete"
    by_kind = {}
    for cand in norm.candidates:
        by_kind.setdefault(cand.kind, []).append(cand)
    assert [c.path for c in by_kind["api"]] == ["/api/users"]
    assert sorted(c.path for c in by_kind["route"]) == ["/a", "/users"]  # Next の印が無いので pages/ は route にしない
    assert "nextjs_convention_skipped_router_declared" in norm.coverage.limitations
    assert {c.artifact_path for c in by_kind["module"]} == {"api.js", "m.js", "router.js", "pages/about.js"}
    assert all(c.epistemic_state == "inferred" for c in by_kind["route"])
    assert [e.relation for e in norm.dependency_edges] == ["imports"]


def test_candidate_digests_match_verified_files(site):
    result = _run(site)
    digests = {f.path: f.sha256 for f in result.files if f.status == "verified"}
    assert set(digests) == {"api.js", "m.js", "router.js", "pages/about.js"}
    for cand in result.normalization.candidates:
        assert digests[cand.artifact_path] == cand.artifact_sha256
        assert cand.artifact_sha256 == hashlib.sha256((site / cand.artifact_path).read_bytes()).hexdigest()
    assert {a.path for a in result.normalization.artifacts} == set(digests)


def test_provider_and_commitment_are_stable(site):
    first, second = _run(site), _run(site)
    assert first.engine_version == second.engine_version == f"webspec2doc-native/{evidence.NATIVE_VERSION}"
    assert first.evidence_id == second.evidence_id and len(first.evidence_id) == 64
    assert all(a.producer == "webspec2doc-native" for a in first.normalization.artifacts)
    assert {p.candidate_id for p in first.normalization.provenance} <= {c.id for c in first.normalization.candidates}
    (site / "m.js").write_text("export const a = 2;\n")
    assert _run(site).evidence_id != first.evidence_id


def test_route_limitations_surface_when_no_router_found(tmp_path):
    _write(tmp_path, {"lib.js": "x"})
    result = _run(tmp_path)
    assert not [c for c in result.normalization.candidates if c.kind == "route"]
    assert any(lim.startswith("route_declarations_not_recognized") for lim in result.normalization.coverage.limitations)


def test_source_map_findings_make_result_partial(site):
    finding = SourceMapFinding("n1", "source-map", "api.js.map", "map_parse_failed", "unknown", "failed", ())
    result = _run(site, sourcemap_fn=lambda parsed, root: FakeMapResult(findings=(finding,)))
    norm = result.normalization
    assert norm.status == "partial" and norm.source_map_findings == (finding,)
    assert any(d.code == "source_map_map_parse_failed" for d in norm.diagnostics)


def test_resolved_source_map_adds_source_candidate(site):
    (site / "api.js.map").write_text("{}")
    mapped = FakeMapResult(map_path="api.js.map", map_sha256="b" * 64, sources=("src/app.ts",))
    result = _run(site, sourcemap_fn=lambda parsed, root: mapped)
    (source,) = [c for c in result.normalization.candidates if c.kind == "source"]
    assert source.path == "src/app.ts" and source.resolution == "partial"


def test_parse_failure_in_one_file_is_partial_not_fatal(site):
    _write(site, {"bomb.js": "x"})
    result = _run(site)
    assert result.status == "partial"
    assert any(d.code == "static_parse_failed" for d in result.diagnostics)
    assert any(c.kind == "api" for c in result.normalization.candidates)


def test_cancelled_before_start(site):
    event = threading.Event()
    event.set()
    result = _run(site, cancel_event=event)
    assert result.status == "cancelled" and result.normalization.status == "cancelled"
    assert result.normalization.candidates == ()


def test_invalid_or_empty_input_is_unavailable(tmp_path):
    assert evidence.analyze(tmp_path / "missing", parser=FakeParser()).status == "unavailable"
    empty = _run(tmp_path)
    assert empty.status == "unavailable"
    assert empty.diagnostics[0].code == "static_input_no_javascript"
    assert empty.normalization.coverage.status == "unavailable"


def test_node_modules_is_not_read(tmp_path):
    _write(tmp_path, {"a.js": "x", "node_modules/dep/index.js": "x"})
    result = _run(tmp_path)
    assert {f.path for f in result.files} == {"a.js"}
