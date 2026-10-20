import time

from generator.svg_diagram import render_svg


def _model(n, cyc=True):
    nodes = [{"id": f"N{i}", "label": f"画面{i}\n/p{i}"} for i in range(n)]
    edges = [{"from": f"N{i}", "to": f"N{i + 1}", "label": "go"} for i in range(n - 1)]
    if cyc and n > 2:
        edges.append({"from": f"N{n - 1}", "to": "N0", "label": "back"})
        edges.append({"from": "N1", "to": "N1", "label": ""})
    return {"nodes": nodes, "edges": edges, "groups": []}


def test_cyclic_graph_renders_all_nodes():
    svg = render_svg(_model(10), "LR")
    assert svg.startswith("<svg") and 'class="wsd-diagram"' in svg
    assert svg.count('class="wsd-node"') == 10
    assert svg.count("marker-end") >= 10


def test_labels_are_escaped():
    m = {
        "nodes": [{"id": "a", "label": "<script>alert(1)</script>"}, {"id": "b", "label": 'x"y&z'}],
        "edges": [{"from": "a", "to": "b", "label": "<img onerror=1>"}],
    }
    svg = render_svg(m)
    assert "<script>" not in svg and "<img" not in svg
    assert "&lt;script&gt;" in svg and "&quot;" in svg and "&amp;" in svg


def test_shapes_and_groups():
    m = {
        "nodes": [
            {"id": "a", "label": "A", "shape": s} for s in ("box", "round", "diamond", "cyl", "para")
        ],
        "edges": [{"from": "a", "to": "a"}],
        "groups": [],
    }
    m["nodes"] = [{"id": f"n{i}", "label": "x", "shape": n["shape"]} for i, n in enumerate(m["nodes"])]
    m["groups"] = [{"id": "G", "label": "群", "members": ["n0", "n1"]}]
    m["edges"] = [{"from": "G", "to": "n2", "label": "l"}]
    svg = render_svg(m)
    assert "<polygon" in svg and "<path" in svg and "stroke-dasharray" in svg


def test_empty_and_single_and_large():
    assert "wsd-diagram-empty" in render_svg({"nodes": [], "edges": []})
    assert render_svg(_model(1)).count('class="wsd-node"') == 1
    t = time.time()
    svg = render_svg(_model(200), "TD")
    assert time.time() - t < 1.0
    assert svg.count('class="wsd-node"') == 200


def test_marker_ids_are_stable_and_distinguish_diagrams():
    import re

    model = _model(3)
    first = render_svg(model, "LR", "Flow")
    render_svg(_model(5), "TD", "Other")
    assert render_svg(model, "LR", "Flow") == first
    changed = render_svg(model, "LR", "Other title")
    marker = re.search(r'<marker id="([^"]+)"', first).group(1)
    changed_marker = re.search(r'<marker id="([^"]+)"', changed).group(1)
    assert marker != changed_marker
    assert f'url(#{marker})' in first
    assert f'url(#{changed_marker})' in changed
