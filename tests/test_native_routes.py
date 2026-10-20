"""native/routes.py: React Router・Vue Router・Next.js の宣言パターン認識。"""

from reverse_analysis.native.facts import ImportFact, ParsedFile, PropertyFact, RouteCandidateFact, ValueFact
from reverse_analysis.native.routes import extract_routes, nextjs_route_path


def _prop(key, value="__none__"):
    """value: 文字列 = 静的な文字列、None = 静的に決まらない式、省略 = 値なし属性。"""
    pos = dict(file="src/r.js", line=3, col=1, end_line=3, end_col=5)
    if value == "__none__":
        return PropertyFact(key=key, **pos)
    val = ValueFact(expression=str(value), node_type="string" if value else "identifier",
                    resolution="static" if value is not None else "dynamic", string_value=value, **pos)
    return PropertyFact(key=key, value=val, **pos)


def _route(kind="jsx", tag="Route", props=(), container="", parent=None, line=3):
    built = tuple(_prop(*p) if isinstance(p, tuple) else _prop(p) for p in props)
    return RouteCandidateFact(file="src/r.js", line=line, col=3, end_line=line, end_col=40, kind=kind,
                              tag=tag if kind == "jsx" else "", properties=built, parent=parent, container=container)


def _parsed(path="src/r.js", routes=(), imports=()):
    return ParsedFile(path=path, sha256="a" * 64, imports=tuple(imports), routes=tuple(routes))


def _import(specifier):
    return ImportFact(file="app.js", line=1, col=1, end_line=1, end_col=20, specifier=specifier, kind="import")


def test_react_router_jsx_route():
    result = extract_routes([_parsed(routes=[_route(props=[("path", "/users/:id")])])])
    (cand,) = result.candidates
    assert (cand.path, cand.resolution, cand.confidence) == ("/users/:id", "exact", "high")
    assert cand.basis == "react-router:jsx-route" and (cand.line, cand.col) == (3, 3)


def test_nested_jsx_route_composes_parent_path():
    parent = _route(props=[("path", "/account")], line=2)
    nested = _route(props=[("path", "settings")], parent=0)
    cands = extract_routes([_parsed(routes=[parent, nested])]).candidates
    assert [c.path for c in cands] == ["/account", "/account/settings"]
    assert cands[1].confidence == "medium"


def test_index_route_and_layout_route():
    routes = [_route(props=[("path", "/blog")]), _route(props=["index"], parent=0), _route(props=[("element", None)])]
    cands = extract_routes([_parsed(routes=routes)]).candidates
    assert [c.path for c in cands] == ["/blog", "/blog"]  # path も index も無い layout route は候補にしない


def test_dynamic_path_is_partial_without_guessing():
    (cand,) = extract_routes([_parsed(routes=[_route(props=[("path", None)])])]).candidates
    assert cand.path is None and cand.resolution == "partial" and cand.confidence == "low"
    assert "route_path_not_static" in cand.limitations


def test_vue_router_object_with_known_context():
    obj = _route("object", props=[("path", "/a"), ("component", None)], container="createRouter")
    (cand,) = extract_routes([_parsed(routes=[obj])]).candidates
    assert (cand.path, cand.basis, cand.confidence) == ("/a", "vue-router:object-route", "high")


def test_object_without_context_needs_router_properties():
    config = _route("object", props=[("path", "/tmp/out")])  # webpack 設定など
    guessed = _route("object", props=[("path", "/b"), ("element", None)])
    result = extract_routes([_parsed(routes=[config, guessed])])
    assert [c.path for c in result.candidates] == ["/b"]
    assert result.candidates[0].confidence == "medium"
    assert "route_like_objects_not_recognized:1" in result.limitations


def test_nextjs_file_conventions():
    cases = {
        "pages/about.js": "/about", "pages/index.js": "/", "src/pages/blog/[id].js": "/blog/:id",
        "app/dashboard/page.js": "/dashboard", "app/(shop)/cart/page.jsx": "/cart",
        "pages/docs/[...slug].js": "/docs/:slug+",
    }
    for file, expected in cases.items():
        assert nextjs_route_path(file) == (expected, None), file
    for file in ("pages/api/x.js", "pages/_app.js", "app/dashboard/layout.js", "node_modules/pages/a.js", "lib/util.js"):
        assert nextjs_route_path(file)[0] is None, file
    assert nextjs_route_path("_next/static/chunks/pages/about-abc.js")[1] == "nextjs_build_chunks_not_mapped"


def test_nextjs_candidate_confidence_depends_on_project_marker():
    page = _parsed("pages/about.js")
    (low,) = extract_routes([page]).candidates
    assert (low.path, low.confidence) == ("/about", "low") and "nextjs_project_marker_absent" in low.limitations
    marker = _parsed("app.js", imports=[_import("next/link")])
    (high,) = extract_routes([page, marker]).candidates
    assert high.confidence == "high"


def test_pages_dir_ignored_when_other_router_declared_without_next():
    declared = _parsed(routes=[_route(props=[("path", "/x")])])
    result = extract_routes([declared, _parsed("src/pages/Home.js")])
    assert [c.path for c in result.candidates] == ["/x"]
    assert "nextjs_convention_skipped_router_declared" in result.limitations


def test_zero_routes_is_distinguished_as_unsupported_pattern():
    result = extract_routes([_parsed("lib/nav.js")])
    assert result.candidates == ()
    assert any(lim.startswith("route_declarations_not_recognized") for lim in result.limitations)
