import hashlib
import threading
from pathlib import Path

import pytest

from reverse_analysis.models import SourceLocation, StaticCandidate, static_candidate_id
from reverse_analysis.native import evidence
from reverse_analysis.native.facts import (
    CallFact, ImportFact, Limitation, ParsedFile, PropertyFact, RouteCandidateFact, SourceMapRef, ValueFact,
)
from reverse_analysis.native.sourcemap import SourceMap, SourceMapFinding, SourceMapResult

_POS = dict(line=1, col=1, end_line=1, end_col=9)


def _value(text):
    return ValueFact(file="x", expression=text, node_type="string", resolution="static", string_value=text, **_POS)


def _prop(key, text=None):
    return PropertyFact(file="x", key=key, value=_value(text) if text is not None else None, **_POS)


class FakeParser:
    """path ごとの facts を返す。bomb という名の JS は例外にする。"""

    def parse(self, path: str, source: bytes) -> ParsedFile:
        if path.endswith("bomb.js"):
            raise ValueError("boom")
        sha = hashlib.sha256(source).hexdigest()
        if path == "api.js":
            return ParsedFile(
                path=path, sha256=sha,
                imports=(ImportFact(file=path, specifier="./m", kind="import", **_POS),),
                calls=(CallFact(file=path, callee="fetch", args=(_value("/api/users"),), **_POS),),
                source_map_ref=SourceMapRef(file=path, url="api.js.map", **_POS),
            )
        if path == "router.js":
            return ParsedFile(path=path, sha256=sha, routes=(
                RouteCandidateFact(file=path, kind="jsx", tag="Route", properties=(_prop("path", "/users"),), **_POS),
                RouteCandidateFact(file=path, kind="object", container="createRouter",
                                   properties=(_prop("path", "/a"), _prop("component")), **_POS),
            ))
        if path == "partial.js":
            return ParsedFile(path=path, sha256=sha, complete=False,
                              limitations=(Limitation(code="syntax_error", message="x", file=path),))
        return ParsedFile(path=path, sha256=sha)


def fake_extract(parsed_files, js_input=None, root_label=""):
    out = []
    for parsed in parsed_files:
        for call in parsed.calls:
            loc = SourceLocation(parsed.path, "line_column_utf8", call.line, call.col, call.end_line, call.end_col)
            out.append(StaticCandidate(
                id=static_candidate_id(parsed.sha256, loc, "api"), kind="api", artifact_path=parsed.path,
                artifact_sha256=parsed.sha256, location=loc, resolution="exact", epistemic_state="inferred",
                authority="t", method="GET", path=call.args[0].string_value, expression=call.callee,
            ))
    return tuple(out), ()


def map_result(findings=(), maps=None):
    return SourceMapResult(maps or {}, tuple(findings), (), ())


def _write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def _run(root: Path, **kwargs):
    kwargs.setdefault("extract_fn", fake_extract)
    kwargs.setdefault("sourcemap_fn", lambda files, root: map_result())
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
    finding = SourceMapFinding("api.js", "map_parse_failed", "壊れています", "api.js.map")
    result = _run(site, sourcemap_fn=lambda files, root: map_result(findings=(finding,)))
    norm = result.normalization
    assert norm.status == "partial" and [f.finding for f in norm.source_map_findings] == ["map_parse_failed"]
    assert norm.source_map_findings[0].path == "api.js.map"


def test_resolved_source_map_adds_source_candidate(site):
    (site / "api.js.map").write_text("{}")
    smap = SourceMap(sources=("app.ts",), names=(), lines=(), source_root="src")
    result = _run(site, sourcemap_fn=lambda files, root: map_result(maps={"api.js": smap}))
    (source,) = [c for c in result.normalization.candidates if c.kind == "source"]
    assert source.path == "src/app.ts" and source.resolution == "partial"
    assert source.artifact_path == "api.js.map"
    assert "api.js.map" in {f.path for f in result.files}


def test_incomplete_parse_is_partial_with_limitation(site):
    _write(site, {"partial.js": "x"})
    result = _run(site)
    assert result.status == "partial"
    assert "parser_syntax_error:partial.js" in result.normalization.coverage.limitations


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


def test_integration_with_real_parser(tmp_path):
    """tree-sitter パーサ・抽出・module graph・source map を通した小さな入力群の通し確認。"""
    _write(tmp_path, {
        "src/app.js": (
            "import { helper } from './util';\n"
            "import('./lazy');\n"
            "fetch('/api/users', { method: 'POST' });\n"
            "const routes = [{ path: '/home', component: Home }];\n"
            "//# sourceMappingURL=app.js.map\n"
        ),
        "src/util.js": "export function helper() { return 1; }\n",
        "src/lazy.js": "export default 1;\n",
        "src/router.jsx": "const r = <Routes><Route path='/users/:id' element={<U/>} /></Routes>;\n",
        "src/app.js.map": '{"version":3,"sources":["../orig/app.ts"],"names":[],"mappings":"AAAA"}',
        "pages/about.js": "export default function About() { return null; }\n",
    })
    result = evidence.run_static_analysis(tmp_path)
    norm = result.normalization
    assert result.engine_version == f"webspec2doc-native/{evidence.NATIVE_VERSION}"
    assert result.status in ("complete", "partial")
    kinds = {}
    for cand in norm.candidates:
        kinds.setdefault(cand.kind, []).append(cand)
    assert any(c.path == "/api/users" and c.method == "POST" for c in kinds["api"])
    assert {"/home", "/users/:id"} <= {c.path for c in kinds["route"]}
    assert {c.artifact_path for c in kinds["module"]} >= {"src/app.js", "src/util.js", "src/lazy.js"}
    assert any(c.kind == "source" for c in norm.candidates)
    targets = {(e.source_node_id, e.target_node_id) for e in norm.dependency_edges}
    assert ("src/app.js", "src/util.js") in targets and ("src/app.js", "src/lazy.js") in targets
    digests = {f.path: f.sha256 for f in result.files}
    assert all(digests[c.artifact_path] == c.artifact_sha256 for c in norm.candidates if c.artifact_path in digests)
    # 規約外（router も無い入力）は「0 件」でなく未対応の limitation になる
    empty = tmp_path / "plain"
    _write(empty, {"a.js": "console.log(1);\n"})
    plain = evidence.run_static_analysis(empty).normalization
    assert not [c for c in plain.candidates if c.kind == "route"]
    assert any(lim.startswith("route_declarations_not_recognized") for lim in plain.coverage.limitations)
