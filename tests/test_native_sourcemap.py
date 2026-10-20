import base64
import json

import pytest

from reverse_analysis.native.facts import ParsedFile
from reverse_analysis.native.sourcemap import (SourceMapError, analyze_source_maps, decode_mappings,
                                               find_source_mapping_url, parse_source_map, vlq_decode, vlq_encode)


@pytest.mark.parametrize("text,expected", [
    ("A", [0]), ("C", [1]), ("D", [-1]), ("gB", [16]), ("hB", [-16]), ("2H", [123]), ("AAgBC", [0, 0, 16, 1]),
    ("+/////D", [2**31 - 1]),
])
def test_vlq_spec_examples(text, expected):
    assert vlq_decode(text) == expected


@pytest.mark.parametrize("n", [0, 1, -1, 15, 16, -16, 123, 1 << 20, -(1 << 20)])
def test_vlq_roundtrip(n):
    assert vlq_decode(vlq_encode(n)) == [n]


@pytest.mark.parametrize("bad", ["!", "g", "gggggggggggg"])
def test_vlq_invalid(bad):
    with pytest.raises(SourceMapError):
        vlq_decode(bad)


MAP = {"version": 3, "file": "out.js", "sources": ["src/a.ts"], "names": ["foo"], "sourceRoot": "",
       "mappings": "AAAA,SAASA;AACT"}


def test_decode_and_lookup():
    m = parse_source_map(json.dumps(MAP))
    assert [len(x) for x in m.lines] == [2, 1]
    p = m.lookup(1, 0)
    assert (p.source, p.line, p.column) == ("src/a.ts", 1, 0)
    p = m.lookup(1, 20)  # 2 つ目の断片: 列 9・元 0 行 9 列・名前 foo
    assert (p.line, p.column, p.name) == (1, 9, "foo")
    assert m.lookup(2, 0).line == 2
    assert m.lookup(5, 0) is None


def test_generated_only_segment_and_range_check():
    assert decode_mappings("A,C", 0, 0)[0][1].source is None
    with pytest.raises(SourceMapError):
        decode_mappings("ACAA", 1, 0)  # source 添字 +1 は sources 1 件の範囲外


@pytest.mark.parametrize("text,code", [
    ("{", "map_parse_failed"), ("[]", "map_parse_failed"),
    (json.dumps({**MAP, "version": 2}), "map_unsupported_version"),
    (json.dumps({"version": 3, "sections": []}), "map_unsupported_index_map"),
    (json.dumps({**MAP, "mappings": "AAAA,ZZ!"}), "map_parse_failed"),
    (json.dumps({**MAP, "sources": "x"}), "map_parse_failed"),
])
def test_parse_errors(text, code):
    with pytest.raises(SourceMapError) as e:
        parse_source_map(text)
    assert e.value.code == code


def test_find_url():
    assert find_source_mapping_url("a();\n//# sourceMappingURL=a.js.map\n") == "a.js.map"
    assert find_source_mapping_url("var s='//# sourceMappingURL=x';") is None


def test_analyze_external_data_and_failures(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "good.js.map").write_text(json.dumps(MAP))
    (tmp_path / "bad.map").write_text("{broken")
    data = "data:application/json;base64," + base64.b64encode(json.dumps(MAP).encode()).decode()
    pfs = [ParsedFile("sub/good.js", "s1", source_map_ref="good.js.map"),
           ParsedFile("inline.js", "s2", source_map_ref=data),
           ParsedFile("b.js", "s3", source_map_ref="bad.map"),
           ParsedFile("m.js", "s4", source_map_ref="missing.map"),
           ParsedFile("r.js", "s5", source_map_ref="https://cdn.example/a.map"),
           ParsedFile("e.js", "s6", source_map_ref="../outside.map"),
           ParsedFile("n.js", "s7")]
    r = analyze_source_maps(pfs, tmp_path)
    assert set(r.maps) == {"sub/good.js", "inline.js"}
    assert r.maps["inline.js"].lookup(1, 0).source == "src/a.ts"
    assert {(f.path, f.finding) for f in r.findings} == {
        ("b.js", "map_parse_failed"), ("m.js", "map_not-found"),
        ("r.js", "map_remote_not_fetched"), ("e.js", "map_path_rejected")}
    assert len(r.diagnostics) == 4 and len(r.limitations) == 4
    assert all("/tmp" not in d.message and str(tmp_path) not in d.message for d in r.diagnostics)
