"""import / export / dynamic import の有向グラフ（標準の dict だけ。外部依存なし）。

エッジの confidence: 静的で解決できたもの 1.0、外部パッケージ 1.0、相対だが
ファイルが見つからないもの 0.6、動的 import の引数が静的文字列でない候補は
0.3（部分的に決まる式は 0.4）。後者は `edges` に混ぜず `dynamic_candidates` に分ける。
"""

from __future__ import annotations

import posixpath
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from reverse_analysis.native.facts import RES_PARTIAL, RES_STATIC, ParsedFile

CONF_RESOLVED = 1.0
CONF_UNRESOLVED_RELATIVE = 0.6
CONF_DYNAMIC_PARTIAL = 0.4
CONF_DYNAMIC_UNKNOWN = 0.3

_EXTS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")


@dataclass(frozen=True)
class ModuleEdge:
    source: str  # 参照元ファイル（ParsedFile.path）
    specifier: str | None
    target: str | None  # 解決できたファイル。外部・未解決・動的候補は None
    kind: str  # "import" | "require" | "reexport" | "dynamic"
    external: bool
    confidence: float
    line: int
    col: int
    expression: str = ""  # 動的候補の引数原文


@dataclass(frozen=True)
class ModuleGraph:
    nodes: tuple[str, ...]
    edges: tuple[ModuleEdge, ...]  # 静的に決まるもの（動的でも引数が静的文字列ならここ）
    dynamic_candidates: tuple[ModuleEdge, ...]  # 引数が静的に決まらない import()/require()

    def imports_of(self, path: str) -> tuple[ModuleEdge, ...]:
        return tuple(e for e in self.edges if e.source == path)

    def importers_of(self, path: str) -> tuple[ModuleEdge, ...]:
        return tuple(e for e in self.edges if e.target == path)

    def reachable(self, start: str) -> frozenset[str]:
        """start から静的エッジで辿れるファイル（start を含む）。"""
        adj: dict[str, list[str]] = {}
        for e in self.edges:
            if e.target is not None:
                adj.setdefault(e.source, []).append(e.target)
        seen, queue = {start}, deque([start])
        while queue:
            for nxt in adj.get(queue.popleft(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return frozenset(seen)


def _resolve(source: str, spec: str, known: frozenset[str]) -> str | None:
    base = posixpath.normpath(posixpath.join(posixpath.dirname(source), spec))
    if base in known:
        return base
    for ext in _EXTS:
        if base + ext in known:
            return base + ext
    for ext in _EXTS:
        idx = posixpath.join(base, "index" + ext)
        if idx in known:
            return idx
    return None


def build_module_graph(files: Iterable[ParsedFile]) -> ModuleGraph:
    parsed = sorted(files, key=lambda f: f.path)
    known = frozenset(f.path for f in parsed)
    edges: list[ModuleEdge] = []
    candidates: list[ModuleEdge] = []

    def add(f: ParsedFile, spec: str | None, kind: str, line: int, col: int, resolution: str, expr: str = "") -> None:
        if spec is None:
            conf = CONF_DYNAMIC_PARTIAL if resolution == RES_PARTIAL else CONF_DYNAMIC_UNKNOWN
            candidates.append(ModuleEdge(f.path, None, None, kind, False, conf, line, col, expr))
            return
        if spec.startswith((".", "/")):
            target = _resolve(f.path, spec, known) if spec.startswith(".") else None
            edges.append(ModuleEdge(
                f.path, spec, target, kind, False,
                CONF_RESOLVED if target else CONF_UNRESOLVED_RELATIVE, line, col))
        else:
            edges.append(ModuleEdge(f.path, spec, None, kind, True, CONF_RESOLVED, line, col))

    for f in parsed:
        for i in f.imports:
            add(f, i.specifier, i.kind, i.line, i.col, i.resolution)
        for d in f.dynamic_imports:
            add(f, d.specifier if d.resolution == RES_STATIC else None, "dynamic", d.line, d.col, d.resolution, d.expression)
    return ModuleGraph(tuple(sorted(known)), tuple(edges), tuple(candidates))
