"""宣言パターンから route 候補を作る（React Router・Vue Router・Next.js の規約パス）。

入力は ParsedFile の routes（生の JSX 要素・オブジェクトリテラル）と、ファイル path だけ。
JS は実行しない。認識できるのは次の宣言パターンに限り、規約外の書き方（自作の遷移関数など）は
候補にせず limitation で「未対応」と「0 件」を区別する。

- React Router: ``<Route path="/x">`` / ``<Route index>`` と、createBrowserRouter 系・useRoutes の配列
- Vue Router: ``routes: [{ path: '/x', component }]``（children の相対 path は親と連結）
- Next.js: ``pages/`` と ``app/**/page.*`` のファイル規約
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

EXPRESSION_MAX_CHARS = 256

CONF_HIGH = "high"
CONF_MEDIUM = "medium"
CONF_LOW = "low"

LIMIT_NO_ROUTE_PATTERN = "route_declarations_not_recognized"
LIMIT_RELATIVE_ASSUMED_ROOT = "route_relative_path_assumed_root"
LIMIT_PATH_DYNAMIC = "route_path_not_static"
LIMIT_ANCESTOR_DYNAMIC = "route_ancestor_path_not_static"
LIMIT_FRAMEWORK_GUESSED = "route_framework_inferred_from_properties"
LIMIT_NEXT_MARKER_ABSENT = "nextjs_project_marker_absent"
LIMIT_NEXT_SKIPPED = "nextjs_convention_skipped_router_declared"
LIMIT_NEXT_CHUNKS = "nextjs_build_chunks_not_mapped"
LIMIT_NEXT_INTERCEPT = "nextjs_special_segment_not_mapped"
LIMIT_OBJECTS_IGNORED = "route_like_objects_not_recognized"

_REACT_CONTEXTS = frozenset(
    {"createBrowserRouter", "createHashRouter", "createMemoryRouter", "createRoutesFromElements", "useRoutes"}
)
_VUE_CONTEXTS = frozenset({"routes", "createRouter", "VueRouter"})
_REACT_PROPS = frozenset({"element", "Component", "lazy", "loader", "errorElement", "action"})
_VUE_PROPS = frozenset({"component", "components", "redirect", "name", "meta", "beforeEnter"})
_SHARED_PROPS = frozenset({"children"})
_NEXT_EXTENSIONS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")
_BLOCKED_SEGMENTS = frozenset({"node_modules", ".git"})
_BUILD_SEGMENTS = frozenset({"_next", ".next"})


@dataclass(frozen=True)
class RouteCandidate:
    """route 候補。state は常に inferred（構文が実在しても route としての意味づけは推論）。"""

    path: str | None
    file: str
    line: int
    col: int
    end_line: int
    end_col: int
    confidence: str
    basis: str
    resolution: str  # exact | partial
    expression: str
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class RouteResult:
    candidates: tuple[RouteCandidate, ...]
    limitations: tuple[str, ...]


# ---------------------------------------------------------------- 宣言（JSX・オブジェクト）


def extract_declared_routes(parsed: Any) -> tuple[tuple[RouteCandidate, ...], int]:
    """1 ファイルの route 宣言を解釈する。戻り値は (候補, 認識しなかった route 風オブジェクト数)。"""
    found: list[RouteCandidate] = []
    ignored = 0
    for fact in parsed.routes:
        props = dict(fact.props)
        if fact.form == "jsx":
            if fact.tag != "Route":
                continue
            made = _build(fact, props, "react-router:jsx-route", CONF_HIGH, ())
        else:
            framework, guessed = _object_framework(fact, props)
            if framework is None:
                if "path" in props:
                    ignored += 1
                continue
            basis = f"{framework}:object-route"
            made = _build(fact, props, basis, CONF_MEDIUM if guessed else CONF_HIGH,
                          (LIMIT_FRAMEWORK_GUESSED,) if guessed else ())
        if made is not None:
            found.append(made)
    return tuple(found), ignored


def _object_framework(fact: Any, props: dict[str, str | None]) -> tuple[str | None, bool]:
    if fact.context in _REACT_CONTEXTS:
        return "react-router", False
    if fact.context in _VUE_CONTEXTS:
        return "vue-router", False
    if "path" not in props:
        return None, False
    names = set(props)
    if names & _REACT_PROPS:
        return "react-router", True
    if names & _VUE_PROPS:
        return "vue-router", True
    return None, False


def _build(
    fact: Any, props: dict[str, str | None], basis: str, confidence: str, limits: tuple[str, ...]
) -> RouteCandidate | None:
    if "path" in props:
        own = props["path"]
    elif "index" in props:
        own = ""  # index route: 親の path そのもの
    else:
        return None  # path も index も無い（layout route 等）は path 候補にしない
    path, extra, resolution = _join(fact.ancestors, own)
    if extra and confidence == CONF_HIGH:
        confidence = CONF_MEDIUM
    if resolution == "partial":
        confidence = CONF_LOW
    return RouteCandidate(
        path, fact.file, fact.line, fact.col, fact.end_line, fact.end_col, confidence, basis, resolution,
        (fact.expression or "")[:EXPRESSION_MAX_CHARS], tuple(dict.fromkeys((*limits, *extra))),
    )


def _join(ancestors: Sequence[str | None], own: str | None) -> tuple[str | None, tuple[str, ...], str]:
    """外側から path を連結する。静的に決まらない部分があれば path は出さない（推測しない）。"""
    chain = [*ancestors, own]
    parts: list[str] = []
    notes: list[str] = []
    for index, piece in enumerate(chain):
        if piece is None:
            notes.append(LIMIT_PATH_DYNAMIC if index == len(chain) - 1 else LIMIT_ANCESTOR_DYNAMIC)
            return None, tuple(notes), "partial"
        if piece.startswith("/"):
            parts = [piece]  # 絶対 path は親を打ち消す
        elif piece:
            if not parts and index == len(chain) - 1 and not ancestors:
                notes.append(LIMIT_RELATIVE_ASSUMED_ROOT)
            parts.append(piece)
    if len(chain) > 1 and any(a for a in ancestors):
        notes.append("route_path_composed_from_parents")
    joined = "/".join(p.strip("/") for p in parts)
    path = "/" + joined if joined else "/"
    return path, tuple(notes), "exact"


# ---------------------------------------------------------------- Next.js の規約パス


def nextjs_route_path(file_path: str) -> tuple[str | None, str | None]:
    """ファイル規約から route path を作る。戻り値は (path, 理由)。path が None なら route ではない。

    理由は None（対象外が普通の場合）か limitation 名。
    """
    segments = file_path.split("/")
    if _BLOCKED_SEGMENTS & set(segments):
        return None, None
    if _BUILD_SEGMENTS & set(segments):
        return (None, LIMIT_NEXT_CHUNKS) if {"pages", "app"} & set(segments) else (None, None)
    root = next((i for i, s in enumerate(segments[:-1]) if s in ("pages", "app")), None)
    if root is None:
        return None, None
    kind, rest = segments[root], segments[root + 1:]
    name = rest[-1]
    stem = next((name[: -len(ext)] for ext in _NEXT_EXTENSIONS if name.endswith(ext)), None)
    if stem is None:
        return None, None
    folders = rest[:-1]
    if kind == "pages":
        if (folders and folders[0] == "api") or stem.startswith("_"):
            return None, None
        pieces = [*folders, stem] if stem != "index" else list(folders)
    else:
        if stem != "page":
            return None, None
        pieces = list(folders)
    mapped: list[str] = []
    for piece in pieces:
        if kind == "app" and re.fullmatch(r"\(.*\)", piece) and not re.match(r"\(\.+\)", piece):
            continue  # route group: URL に出ない
        if kind == "app" and (piece.startswith("@") or re.match(r"\(\.+\)", piece)):
            return None, LIMIT_NEXT_INTERCEPT
        if kind == "app" and piece.startswith("_"):
            return None, None  # private folder
        mapped.append(_next_segment(piece))
    return "/" + "/".join(mapped), None


def _next_segment(piece: str) -> str:
    optional = re.fullmatch(r"\[\[\.\.\.(.+)\]\]", piece)
    if optional:
        return f":{optional.group(1)}*"
    catch_all = re.fullmatch(r"\[\.\.\.(.+)\]", piece)
    if catch_all:
        return f":{catch_all.group(1)}+"
    dynamic = re.fullmatch(r"\[(.+)\]", piece)
    return f":{dynamic.group(1)}" if dynamic else piece


# ---------------------------------------------------------------- 全体


def extract_routes(parsed_files: Iterable[Any]) -> RouteResult:
    """全 ParsedFile から route 候補をまとめる。0 件のときは「未対応の書き方」を limitation で明示する。"""
    files = sorted(parsed_files, key=lambda p: p.path)
    declared: list[RouteCandidate] = []
    ignored = 0
    for parsed in files:
        found, skipped = extract_declared_routes(parsed)
        declared.extend(found)
        ignored += skipped
    limitations: list[str] = []
    next_project = any(
        imp.specifier == "next" or imp.specifier.startswith("next/") for p in files for imp in p.imports
    )
    convention: list[RouteCandidate] = []
    for parsed in files:
        path, reason = nextjs_route_path(parsed.path)
        if reason:
            limitations.append(reason)
        if path is None:
            continue
        marker = (LIMIT_NEXT_MARKER_ABSENT,) if not next_project else ()
        convention.append(RouteCandidate(
            path, parsed.path, 1, 0, 1, 0, CONF_HIGH if next_project else CONF_LOW, "nextjs:file-convention",
            "exact", parsed.path[:EXPRESSION_MAX_CHARS], marker,
        ))
    if convention and declared and not next_project:
        limitations.append(LIMIT_NEXT_SKIPPED)  # React/Vue の宣言があり Next の印が無い pages/ は route にしない
        convention = []
    candidates = sorted(
        (*declared, *convention), key=lambda c: (c.file, c.line, c.col, c.path or "")
    )
    if ignored:
        limitations.append(f"{LIMIT_OBJECTS_IGNORED}:{ignored}")
    if not candidates:
        limitations.append(LIMIT_NO_ROUTE_PATTERN + ":react-router,vue-router,nextjs")
    return RouteResult(tuple(candidates), tuple(dict.fromkeys(limitations)))
