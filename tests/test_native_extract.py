from reverse_analysis.native.extract import classify_call, extract_api_candidates
from reverse_analysis.native.facts import CallFact, ParsedFile

SRC = '''const BASE = "/api/v1";
fetch("/api/users", {method: "POST"});
axios.get(BASE + "/a");
axios({url: "/api/b", method: "delete"});
const x = new XMLHttpRequest();
x.open("PUT", "/api/c/" + id);
$http.get("/api/d");
fetch(url);
window.open("/page", "_blank");
'''


def _calls(src):
    """行頭から呼び出し式を拾う簡易パーサ（テスト用。本物は R1 の parser_ts）。"""
    import re
    calls = []
    for ln, line in enumerate(src.splitlines(), 1):
        m = re.search(r"((?:[\w$]+\.)*[\w$]+)\((.*)\);", line)
        if m and m.group(1) not in ("XMLHttpRequest",) and "new " not in line:
            calls.append(CallFact(m.group(1), ln, m.start(1), ln, m.end() - 1, line[m.start(1):m.end() - 1]))
    return calls


def _run(tmp_path):
    (tmp_path / "a.js").write_text(SRC)
    pf = ParsedFile("a.js", "sha-a", calls=tuple(_calls(SRC)))
    return extract_api_candidates([pf], tmp_path)


def test_classify():
    assert classify_call("fetch") == ("fetch", None)
    assert classify_call("axios.post") == ("axios", "POST")
    assert classify_call("axios") == ("axios", None)
    assert classify_call("$http.delete") == ("$http", "DELETE")
    assert classify_call("x.open", 'x.open("GET", u)') == ("xhr", "GET")
    assert classify_call("window.open", 'window.open("/p", "_blank")') is None
    assert classify_call("console.log") is None


def test_extract_methods_paths_positions(tmp_path):
    cands, _ = _run(tmp_path)
    got = {(c.location.start_line, c.method, c.path or c.path_pattern) for c in cands}
    assert (2, "POST", "/api/users") in got
    assert (3, "GET", "/api/v1/a") in got
    assert (4, "DELETE", "/api/b") in got
    assert (6, "PUT", "/api/c/:param") in got
    assert (7, "GET", "/api/d") in got
    assert not any(c.location.start_line == 9 for c in cands)  # window.open は API ではない
    fetch2 = next(c for c in cands if c.location.start_line == 2)
    assert (fetch2.location.start_column, fetch2.location.end_line) == (0, 2)
    assert fetch2.expression.startswith('fetch("/api/users"')
    assert fetch2.kind == "api" and fetch2.artifact_sha256 == "sha-a"


def test_unresolved_is_partial_not_error(tmp_path):
    cands, _ = _run(tmp_path)
    c = next(c for c in cands if c.location.start_line == 8)  # fetch(url)
    assert c.resolution == "partial" and c.path is None and c.method in ("GET", "UNKNOWN")
    assert c.epistemic_state == "inferred"


def test_without_js_input_method_unknown():
    pf = ParsedFile("a.js", "s", calls=(CallFact("fetch", 1, 0, 1, 10, 'fetch("/x")'),
                                         CallFact("axios.put", 2, 0, 2, 12, 'axios.put("/y")')))
    cands, diags = extract_api_candidates([pf])
    assert [c.method for c in cands] == ["UNKNOWN", "PUT"] and diags == ()
