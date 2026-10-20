"""図モデルから静的 SVG を直接出力する描画器（ネットワーク・外部 JS 不要）。

階層レイアウトは Sugiyama 法の公開された手順（閉路除去 → 最長経路による層割り当て →
重心法による層内整列 → 座標割り当て）を独自に実装したもの。
モデル: {"nodes":[{id,label,shape,cls}], "edges":[{from,to,label}], "groups":[{id,label,members}]}
shape: box | round | diamond | cyl | para / cls: frontend | backend | db | user | (空)
"""

from __future__ import annotations

import hashlib
import html
import json
from collections import defaultdict
from typing import Any

SHAPES = ("box", "round", "diamond", "cyl", "para")
EMPTY_MESSAGE = "図に表示する項目がありません"

_FONT = 13
_CHAR_ASCII = 7.4
_CHAR_WIDE = 13.5
_LINE_H = 18
_PAD_X = 16
_PAD_Y = 10
_MIN_W = 72
_LAYER_GAP = 84
_NODE_GAP = 26
_MARGIN = 24
_GROUP_PAD = 14
_SWEEPS = 4

_COLORS = {
    "frontend": ("#EDF5FF", "#0F62FE", "#0043CE"),
    "backend": ("#DEFBE6", "#198038", "#0e6027"),
    "db": ("#FFF8E1", "#F59E0B", "#92400e"),
    "user": ("#F4F4F4", "#525252", "#161616"),
}
_DEFAULT_COLOR = ("#FFFFFF", "#8D8D8D", "#161616")


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _lines(label: str) -> list[str]:
    parts = str(label).replace("\\n", "\n").split("\n")
    return parts or [""]


def _text_width(text: str) -> float:
    return sum(_CHAR_WIDE if ord(c) > 0x2E7F else _CHAR_ASCII for c in text)


def _node_size(node: dict) -> tuple[float, float]:
    lines = _lines(node.get("label", ""))
    w = max(_text_width(line) for line in lines) + _PAD_X * 2
    h = _LINE_H * len(lines) + _PAD_Y * 2
    shape = node.get("shape")
    if shape == "diamond":
        w, h = w * 1.5, h * 1.6
    elif shape == "para":
        w += 16
    elif shape == "cyl":
        h += 12
    return max(w, _MIN_W), h


def _break_cycles(ids: list[str], succ: dict[str, list[str]]) -> set[tuple[str, str]]:
    """深さ優先で後退辺を求める（再帰なし）。"""
    state: dict[str, int] = {}
    back: set[tuple[str, str]] = set()
    for root in ids:
        if state.get(root):
            continue
        state[root] = 1
        stack = [(root, iter(succ[root]))]
        while stack:
            node, it = stack[-1]
            for nxt in it:
                st = state.get(nxt, 0)
                if st == 1:
                    back.add((node, nxt))
                elif st == 0:
                    state[nxt] = 1
                    stack.append((nxt, iter(succ[nxt])))
                    break
            else:
                state[node] = 2
                stack.pop()
    return back


def _assign_layers(ids: list[str], dag: dict[str, list[str]]) -> dict[str, int]:
    indeg = {i: 0 for i in ids}
    for s in ids:
        for t in dag[s]:
            indeg[t] += 1
    layer = {i: 0 for i in ids}
    queue = [i for i in ids if indeg[i] == 0]
    while queue:
        s = queue.pop(0)
        for t in dag[s]:
            layer[t] = max(layer[t], layer[s] + 1)
            indeg[t] -= 1
            if indeg[t] == 0:
                queue.append(t)
    return layer


def _order_layers(layers: list[list[str]], dag: dict[str, list[str]], pred: dict[str, list[str]]) -> None:
    pos = {n: i for layer in layers for i, n in enumerate(layer)}

    def bary(n: str, neighbors: list[str], fallback: float) -> float:
        vals = [pos[m] for m in neighbors if m in pos]
        return sum(vals) / len(vals) if vals else fallback

    for sweep in range(_SWEEPS):
        down = sweep % 2 == 0
        rng = range(1, len(layers)) if down else range(len(layers) - 2, -1, -1)
        for li in rng:
            layer = layers[li]
            keyed = [(bary(n, pred[n] if down else dag[n], pos[n]), pos[n], n) for n in layer]
            keyed.sort()
            layers[li] = [n for _, _, n in keyed]
            for i, n in enumerate(layers[li]):
                pos[n] = i


def layout(model: dict, direction: str = "TD") -> dict:
    """座標付きの配置結果を返す。{"pos": {id: (cx, cy, w, h)}, "width", "height", "back": set}"""
    nodes = {str(n["id"]): n for n in model.get("nodes", [])}
    ids = list(nodes)
    groups = {str(g["id"]): [str(m) for m in g.get("members", [])] for g in model.get("groups", [])}
    succ: dict[str, list[str]] = {i: [] for i in ids}
    for e in model.get("edges", []):
        for s in _expand_endpoint(str(e["from"]), nodes, groups):
            for t in _expand_endpoint(str(e["to"]), nodes, groups):
                if s != t and t not in succ[s]:
                    succ[s].append(t)
    back = _break_cycles(ids, succ)
    dag = {i: [t for t in succ[i] if (i, t) not in back] for i in ids}
    pred: dict[str, list[str]] = {i: [] for i in ids}
    for s in ids:
        for t in dag[s]:
            pred[t].append(s)
    layer_of = _assign_layers(ids, dag)
    layers: list[list[str]] = [[] for _ in range(max(layer_of.values()) + 1)]
    for i in ids:
        layers[layer_of[i]].append(i)
    _order_layers(layers, dag, pred)

    horizontal = direction == "LR"
    sizes = {i: _node_size(nodes[i]) for i in ids}

    def main(i: str) -> float:
        return sizes[i][0] if horizontal else sizes[i][1]

    def cross(i: str) -> float:
        return sizes[i][1] if horizontal else sizes[i][0]

    totals = [sum(cross(n) for n in layer) + _NODE_GAP * (len(layer) - 1) for layer in layers]
    widest = max(totals)
    pos: dict[str, tuple[float, float, float, float]] = {}
    offset = _MARGIN
    for layer, total in zip(layers, totals):
        extent = max(main(n) for n in layer)
        c = _MARGIN + (widest - total) / 2
        for n in layer:
            m_center = offset + extent / 2
            c_center = c + cross(n) / 2
            c += cross(n) + _NODE_GAP
            cx, cy = (m_center, c_center) if horizontal else (c_center, m_center)
            pos[n] = (cx, cy, sizes[n][0], sizes[n][1])
        offset += extent + _LAYER_GAP
    main_total = offset - _LAYER_GAP + _MARGIN
    cross_total = widest + _MARGIN * 2
    w, h = (main_total, cross_total) if horizontal else (cross_total, main_total)
    return {"pos": pos, "width": w, "height": h, "back": back, "layer": layer_of, "horizontal": horizontal}


def _shape_svg(node: dict, cx: float, cy: float, w: float, h: float) -> str:
    fill, stroke, _ = _COLORS.get(str(node.get("cls") or ""), _DEFAULT_COLOR)
    x, y = cx - w / 2, cy - h / 2
    attrs = f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"'
    shape = node.get("shape")
    if shape == "round":
        return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{h / 2:.1f}" {attrs}/>'
    if shape == "diamond":
        pts = f"{cx:.1f},{y:.1f} {x + w:.1f},{cy:.1f} {cx:.1f},{y + h:.1f} {x:.1f},{cy:.1f}"
        return f'<polygon points="{pts}" {attrs}/>'
    if shape == "para":
        s = 10
        pts = f"{x + s:.1f},{y:.1f} {x + w:.1f},{y:.1f} {x + w - s:.1f},{y + h:.1f} {x:.1f},{y + h:.1f}"
        return f'<polygon points="{pts}" {attrs}/>'
    if shape == "cyl":
        ry = 6
        d = (
            f"M{x:.1f},{y + ry:.1f} a{w / 2:.1f},{ry} 0 0 1 {w:.1f},0 v{h - 2 * ry:.1f} "
            f"a{w / 2:.1f},{ry} 0 0 1 -{w:.1f},0 z "
            f"M{x:.1f},{y + ry:.1f} a{w / 2:.1f},{ry} 0 0 0 {w:.1f},0"
        )
        return f'<path d="{d}" {attrs}/>'
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4" {attrs}/>'


def _text_svg(node: dict, cx: float, cy: float) -> str:
    _, _, color = _COLORS.get(str(node.get("cls") or ""), _DEFAULT_COLOR)
    lines = _lines(node.get("label", ""))
    top = cy - (len(lines) - 1) * _LINE_H / 2
    spans = "".join(
        f'<tspan x="{cx:.1f}" y="{top + i * _LINE_H:.1f}">{_esc(line)}</tspan>' for i, line in enumerate(lines)
    )
    return f'<text text-anchor="middle" dominant-baseline="central" fill="{color}">{spans}</text>'


def _clip(cx: float, cy: float, w: float, h: float, tx: float, ty: float) -> tuple[float, float]:
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    sx = (w / 2) / abs(dx) if dx else float("inf")
    sy = (h / 2) / abs(dy) if dy else float("inf")
    k = min(sx, sy)
    return cx + dx * k, cy + dy * k


def _expand_endpoint(ref: str, nodes: dict, groups: dict[str, list[str]]) -> list[str]:
    if ref in nodes:
        return [ref]
    return [m for m in groups.get(ref, []) if m in nodes]


def _edge_svg(src, dst, label, lay, marker) -> tuple[str, tuple[float, float] | None]:
    sx, sy, sw, sh = src
    tx, ty, tw, th = dst
    horizontal = lay["horizontal"]
    if horizontal and tx - sx > (sw + tw) / 2:
        x1, y1, x2, y2 = sx + sw / 2, sy, tx - tw / 2, ty
        mid = (x1 + x2) / 2
        d = f"M{x1:.1f},{y1:.1f} C{mid:.1f},{y1:.1f} {mid:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"
        lp = (x1 + (x2 - x1) * 0.38, y1 + (y2 - y1) * 0.38)
    elif not horizontal and ty - sy > (sh + th) / 2:
        x1, y1, x2, y2 = sx, sy + sh / 2, tx, ty - th / 2
        mid = (y1 + y2) / 2
        d = f"M{x1:.1f},{y1:.1f} C{x1:.1f},{mid:.1f} {x2:.1f},{mid:.1f} {x2:.1f},{y2:.1f}"
        lp = (x1 + (x2 - x1) * 0.38, y1 + (y2 - y1) * 0.38)
    else:
        x1, y1 = _clip(sx, sy, sw, sh, tx, ty)
        x2, y2 = _clip(tx, ty, tw, th, sx, sy)
        d = f"M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}"
        lp = (x1 + (x2 - x1) * 0.38, y1 + (y2 - y1) * 0.38)
    path = f'<path d="{d}" fill="none" stroke="#525252" stroke-width="1.3" marker-end="url(#{marker})"/>'
    return path, lp


def _self_loop(src, marker) -> str:
    sx, sy, sw, sh = src
    x, y = sx + sw / 2, sy - sh / 4
    d = f"M{x:.1f},{y:.1f} C{x + 30:.1f},{y - 18:.1f} {x + 30:.1f},{y + sh / 2 + 18:.1f} {x:.1f},{y + sh / 2:.1f}"
    return f'<path d="{d}" fill="none" stroke="#525252" stroke-width="1.3" marker-end="url(#{marker})"/>'


def render_svg(model: dict, direction: str = "TD", title: str = "図") -> str:
    """モデルを SVG 文字列にする。ラベルは全て HTML エスケープする。"""
    nodes_list = model.get("nodes") or []
    if not nodes_list:
        return (
            '<svg class="wsd-diagram wsd-diagram-empty" xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 320 60" role="img" aria-label="{_esc(title)}">'
            f'<text x="160" y="30" text-anchor="middle" dominant-baseline="central" fill="#525252" '
            f'font-size="{_FONT}">{_esc(EMPTY_MESSAGE)}</text></svg>'
        )
    nodes = {str(n["id"]): n for n in nodes_list}
    groups = {str(g["id"]): [str(m) for m in g.get("members", [])] for g in model.get("groups", [])}
    lay = layout(model, direction)
    pos = lay["pos"]
    # Content-derived IDs keep repeated reports stable and distinguish diagrams.
    identity = json.dumps([model, direction, title], sort_keys=True, ensure_ascii=False)
    marker = "wsd-arrow-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]

    body: list[str] = []
    min_x = min_y = 0.0
    max_x, max_y = lay["width"], lay["height"]
    for g in model.get("groups", []):
        members = [m for m in groups[str(g["id"])] if m in pos]
        if not members:
            continue
        gx1 = min(pos[m][0] - pos[m][2] / 2 for m in members) - _GROUP_PAD
        gx2 = max(pos[m][0] + pos[m][2] / 2 for m in members) + _GROUP_PAD
        gy1 = min(pos[m][1] - pos[m][3] / 2 for m in members) - _GROUP_PAD - 16
        gy2 = max(pos[m][1] + pos[m][3] / 2 for m in members) + _GROUP_PAD
        min_x, min_y = min(min_x, gx1 - 4), min(min_y, gy1 - 4)
        max_x, max_y = max(max_x, gx2 + 4), max(max_y, gy2 + 4)
        body.append(
            f'<rect x="{gx1:.1f}" y="{gy1:.1f}" width="{gx2 - gx1:.1f}" height="{gy2 - gy1:.1f}" rx="6" '
            'fill="#F8F8F8" stroke="#C6C6C6" stroke-dasharray="5 3"/>'
            f'<text x="{gx1 + 8:.1f}" y="{gy1 + 12:.1f}" fill="#525252" font-size="12">{_esc(g.get("label", ""))}</text>'
        )

    edge_parts: list[str] = []
    label_parts: list[str] = []
    for e in model.get("edges", []):
        srcs = _expand_endpoint(str(e["from"]), nodes, groups)
        dsts = _expand_endpoint(str(e["to"]), nodes, groups)
        label = str(e.get("label") or "")
        first = True
        for s in srcs:
            for t in dsts:
                if s == t:
                    edge_parts.append(_self_loop(pos[s], marker))
                    continue
                path, lp = _edge_svg(pos[s], pos[t], label, lay, marker)
                edge_parts.append(path)
                if label and first and lp:
                    first = False
                    tw = _text_width(label.replace("\\n", " ")) * 0.9 + 8
                    lines = _lines(label)
                    lh = len(lines) * 15 + 4
                    spans = "".join(
                        f'<tspan x="{lp[0]:.1f}" y="{lp[1] - (len(lines) - 1) * 7.5 + i * 15:.1f}">{_esc(ln)}</tspan>'
                        for i, ln in enumerate(lines)
                    )
                    tw = max(_text_width(ln) for ln in lines) * 0.9 + 8
                    label_parts.append(
                        f'<rect x="{lp[0] - tw / 2:.1f}" y="{lp[1] - lh / 2:.1f}" width="{tw:.1f}" height="{lh:.1f}" '
                        'fill="#FFFFFF" fill-opacity="0.92"/>'
                        f'<text text-anchor="middle" dominant-baseline="central" fill="#393939" font-size="11">{spans}</text>'
                    )
    node_parts = []
    for nid, node in nodes.items():
        cx, cy, w, h = pos[nid]
        node_parts.append(
            f'<g class="wsd-node" data-node-id="{_esc(nid)}">{_shape_svg(node, cx, cy, w, h)}{_text_svg(node, cx, cy)}</g>'
        )
    vw, vh = max_x - min_x, max_y - min_y
    defs = (
        f'<defs><marker id="{marker}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
        'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#525252"/></marker></defs>'
    )
    return (
        f'<svg class="wsd-diagram" xmlns="http://www.w3.org/2000/svg" viewBox="{min_x:.1f} {min_y:.1f} {vw:.1f} {vh:.1f}" '
        f'width="{vw:.0f}" height="{vh:.0f}" style="max-width:100%;height:auto" role="img" '
        f'aria-label="{_esc(title)}" font-family="sans-serif" font-size="{_FONT}">'
        f"{defs}{''.join(body)}{''.join(edge_parts)}{''.join(node_parts)}{''.join(label_parts)}</svg>"
    )
