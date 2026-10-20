from __future__ import annotations

import ast
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from reverse_analysis.native.facts import ParsedFile  # noqa: E402
from reverse_analysis.native.module_graph import build_module_graph  # noqa: E402
from reverse_analysis.native.parser import get_parser, set_parser  # noqa: E402


def parse(src: str, path: str = "a.js") -> ParsedFile:
    return get_parser().parse(path, src.encode())


def test_modern_js_and_jsx():
    p = parse(
        'import d, {a as b} from "./x";\nimport * as ns from "lib";\n'
        'export default function f(){}\nexport const z = 1;\nexport * from "./y";\n'
        'class C { #p = 1; static s = 2 }\nconst v = o?.p ?? await fetch("/api/users", {method:"POST"});\n'
        'const el = <Route path="/users/:id" element={<U/>}><Route index element={<I/>}/></Route>;\n'
        '//# sourceMappingURL=a.js.map\n'
    )
    assert p.complete and not p.limitations
    assert [(i.specifier, i.kind, i.names) for i in p.imports] == [
        ("./x", "import", ("default", "b")), ("lib", "import", ("*",)), ("./y", "reexport", ())]
    assert {(e.name, e.kind) for e in p.exports} == {("default", "default"), ("z", "named"), ("*", "all")}
    c = next(c for c in p.calls if c.callee == "fetch")
    assert (c.line, c.col) == (7, 25)
    assert c.args[0].string_value == "/api/users" and c.args[0].resolution == "static"
    assert {pr.key: pr.value.string_value for pr in c.args[1].properties} == {"method": "POST"}
    assert [(r.kind, r.tag, r.parent) for r in p.routes] == [("jsx", "Route", None), ("jsx", "Route", 0)]
    assert p.routes[0].properties[0].value.string_value == "/users/:id"
    assert p.routes[1].properties[0].value is None  # <Route index />
    assert p.source_map_ref.url == "a.js.map" and not p.source_map_ref.inline


def test_object_routes_and_dynamic_args():
    p = parse(
        'const r = createBrowserRouter([{path:"/a", children:[{path:"b"}]}]);\n'
        'axios.get(BASE + "/a"); fetch(`/x/${id}`); import("./m"); import(name); require("w"); require(n);\n'
    )
    assert [(r.parent, r.container) for r in p.routes] == [(None, "createBrowserRouter"), (0, "createBrowserRouter")]
    byc = {c.callee: c for c in p.calls}
    assert byc["axios.get"].args[0].resolution == "partial"
    assert byc["fetch"].args[0].resolution == "partial" and byc["fetch"].args[0].string_value is None
    assert [(d.specifier, d.resolution) for d in p.dynamic_imports] == [("./m", "static"), (None, "dynamic")]
    assert [(i.specifier, i.kind) for i in p.imports] == [("w", "require"), (None, "require")]


def test_minified_input():
    src = 'var a=function(){return fetch("/api/a").then(function(r){return r.json()})};!function(e){e.get("/b")}(axios);' * 200
    p = parse(src)
    assert p.complete and len([c for c in p.calls if c.callee == "fetch"]) == 200


def test_syntax_error_gives_partial_result():
    p = parse('import x from "./ok";\nfetch("/api/ok");\nfoo(;\nlet = = 1;\n')
    assert not p.complete
    assert any(l.code == "syntax_error" and l.line for l in p.limitations)
    assert p.imports[0].specifier == "./ok"
    assert any(c.callee == "fetch" for c in p.calls)


def test_inline_sourcemap_and_never_raises():
    p = parse("x();\n//# sourceMappingURL=data:application/json;base64,e30=\n")
    assert p.source_map_ref.inline
    assert parse("").complete
    assert len(parse("a", "b.js").sha256) == 64


def test_parser_is_swappable():
    stub = type("S", (), {"parse": lambda self, path, source: ParsedFile(path=path, sha256="0" * 64)})()
    try:
        set_parser(stub)
        assert get_parser().parse("q.js", b"").path == "q.js"
    finally:
        set_parser(None)


def test_tree_sitter_imported_only_in_parser_ts():
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "reverse_analysis"
    for f in root.rglob("*.py"):
        if f.name == "parser_ts.py":
            continue
        tree = ast.parse(f.read_text())
        for n in ast.walk(tree):
            names = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""] if isinstance(n, ast.ImportFrom) else []
            assert not any(x.split(".")[0].startswith("tree_sitter") for x in names), f


def test_module_graph():
    a = parse('import x from "./b"; import("./c"); import(name); import("./nope"); import r from "react"; require("./d/");', "src/a.js")
    b = parse("export default 1", "src/b.js")
    c = parse("", "src/c.jsx")
    d = parse("", "src/d/index.js")
    g = build_module_graph([a, b, c, d])
    by = {(e.specifier): e for e in g.edges}
    assert by["./b"].target == "src/b.js" and by["./b"].confidence == 1.0
    assert by["./c"].target == "src/c.jsx" and by["./c"].kind == "dynamic"
    assert by["./nope"].target is None and by["./nope"].confidence < 1.0
    assert by["react"].external
    assert len(g.dynamic_candidates) == 1 and g.dynamic_candidates[0].confidence < 0.5
    assert g.dynamic_candidates[0].expression == "name"
    assert g.reachable("src/a.js") >= {"src/a.js", "src/b.js", "src/c.jsx"}
    assert [e.source for e in g.importers_of("src/b.js")] == ["src/a.js"]
