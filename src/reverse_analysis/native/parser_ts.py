"""tree-sitter-javascript 実装。`tree_sitter` を import してよいのはこのファイルだけ。

JSX は同じ文法で処理される。走査は反復（巨大 minify バンドルで再帰が溢れない）。
構文エラーでも木は返るので、取れた事実は返し、complete=False と limitation を付ける。
"""

from __future__ import annotations

import hashlib
import re
from importlib import metadata

import tree_sitter_javascript as _tsj
from tree_sitter import Language, Node, Parser as _TsParser

from reverse_analysis.native.facts import (
    MAX_EXPRESSION_CHARS,
    RES_DYNAMIC,
    RES_PARTIAL,
    RES_STATIC,
    CallFact,
    DynamicImportFact,
    ExportFact,
    ImportFact,
    Limitation,
    ParsedFile,
    PropertyFact,
    RouteCandidateFact,
    SourceMapRef,
    ValueFact,
)

MAX_SYNTAX_LIMITATIONS = 20
_SOURCEMAP_RE = re.compile(r"[#@]\s*sourceMappingURL=(\S+)")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}
_ESC_RE = re.compile(r"\\(u\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)", re.S)
_ROUTE_ATTRS = frozenset({"path", "index"})


def _version() -> str:
    try:
        return "tree-sitter-javascript/" + metadata.version("tree-sitter-javascript")
    except metadata.PackageNotFoundError:  # pragma: no cover
        return "tree-sitter-javascript"


def _unescape(raw: str) -> str:
    def sub(m: re.Match[str]) -> str:
        s = m.group(1)
        if s[0] == "u" and len(s) > 1:
            return chr(int(s[2:-1] if s[1] == "{" else s[1:], 16))
        if s[0] == "x" and len(s) > 1:
            return chr(int(s[1:], 16))
        return _ESCAPES.get(s, s)

    try:
        return _ESC_RE.sub(sub, raw)
    except (ValueError, OverflowError):
        return raw


def _text(n: Node) -> str:
    return (n.text or b"").decode("utf-8", errors="replace")


class TreeSitterParser:
    def __init__(self) -> None:
        self._parser = _TsParser(Language(_tsj.language()))
        self._version = _version()

    def parse(self, path: str, source: bytes) -> ParsedFile:
        sha = hashlib.sha256(source).hexdigest()
        try:
            tree = self._parser.parse(source)
            return _Collector(path, sha, self._version).run(tree.root_node)
        except Exception as exc:  # 契約: 例外を投げない
            return ParsedFile(
                path=path,
                sha256=sha,
                parser=self._version,
                complete=False,
                limitations=(
                    Limitation(
                        code="parser_failure",
                        message=f"パーサが失敗しました: {type(exc).__name__}",
                        file=path,
                    ),
                ),
            )


class _Collector:
    def __init__(self, path: str, sha: str, version: str) -> None:
        self.path = path
        self.sha = sha
        self.version = version
        self.imports: list[ImportFact] = []
        self.exports: list[ExportFact] = []
        self.dynamic: list[DynamicImportFact] = []
        self.calls: list[CallFact] = []
        self.routes: list[RouteCandidateFact] = []
        self.limits: list[Limitation] = []
        self.smap: SourceMapRef | None = None
        self.route_by_node: dict[int, int] = {}
        self.syntax_errors = 0

    # --- 位置 -----------------------------------------------------------
    def _pos(self, n: Node) -> dict:
        (sl, sc), (el, ec) = n.start_point, n.end_point
        return {"file": self.path, "line": sl + 1, "col": sc + 1, "end_line": el + 1, "end_col": ec + 1}

    # --- 走査 -----------------------------------------------------------
    def run(self, root: Node) -> ParsedFile:
        stack = [root]
        while stack:
            n = stack.pop()
            t = n.type
            if t == "ERROR" or n.is_missing:
                self._syntax(n)
            elif t == "call_expression":
                self._call(n)
            elif t == "import_statement":
                self._import(n)
            elif t == "export_statement":
                self._export(n)
            elif t == "comment":
                self._comment(n)
            elif t in ("jsx_opening_element", "jsx_self_closing_element"):
                self._jsx(n)
            elif t == "object":
                self._object(n)
            stack.extend(reversed(n.children))
        return ParsedFile(
            path=self.path,
            sha256=self.sha,
            imports=tuple(self.imports),
            exports=tuple(self.exports),
            dynamic_imports=tuple(self.dynamic),
            calls=tuple(self.calls),
            routes=tuple(self.routes),
            source_map_ref=self.smap,
            limitations=tuple(self.limits),
            parser=self.version,
            complete=self.syntax_errors == 0,
        )

    def _syntax(self, n: Node) -> None:
        self.syntax_errors += 1
        if self.syntax_errors <= MAX_SYNTAX_LIMITATIONS:
            what = "欠けた構文" if n.is_missing else "解釈できない構文"
            self.limits.append(
                Limitation(
                    code="syntax_error",
                    message=f"{what}があります。その周辺の事実は欠けている可能性があります。",
                    file=self.path,
                    line=n.start_point[0] + 1,
                    col=n.start_point[1] + 1,
                )
            )
        elif self.syntax_errors == MAX_SYNTAX_LIMITATIONS + 1:
            self.limits.append(
                Limitation(code="syntax_error_truncated", message="構文エラーが多いため以降の記録を省きます。", file=self.path)
            )

    # --- 値 -------------------------------------------------------------
    def _string_value(self, n: Node) -> str | None:
        parts = []
        for c in n.children:
            if c.type == "string_fragment":
                parts.append(_text(c))
            elif c.type == "escape_sequence":
                parts.append(_unescape(_text(c)))
            elif c.type in ('"', "'", "`"):
                continue
            else:
                return None
        return "".join(parts)

    def _value(self, n: Node, with_props: bool = True) -> ValueFact:
        t = n.type
        text = _text(n)
        truncated = len(text) > MAX_EXPRESSION_CHARS
        if truncated:
            text = text[:MAX_EXPRESSION_CHARS]
        res, sv, props = RES_DYNAMIC, None, ()
        if t == "string":
            sv = self._string_value(n)
            res = RES_STATIC if sv is not None else RES_PARTIAL
        elif t == "template_string":
            subs = any(c.type == "template_substitution" for c in n.children)
            if subs:
                res = RES_PARTIAL
            else:
                sv = self._string_value(n)
                res = RES_STATIC if sv is not None else RES_PARTIAL
        elif t in ("binary_expression", "parenthesized_expression", "call_expression"):
            res = RES_PARTIAL if _has_string_literal(n) else RES_DYNAMIC
        elif t == "object" and with_props:
            props = self._pairs(n)
        elif t == "jsx_expression" and n.named_child_count == 1:
            inner = self._value(n.named_children[0], with_props)
            return ValueFact(**self._pos(n), expression=text, node_type=t, resolution=inner.resolution,
                             string_value=inner.string_value, truncated=truncated, properties=inner.properties)
        return ValueFact(**self._pos(n), expression=text, node_type=t, resolution=res,
                         string_value=sv, truncated=truncated, properties=props)

    def _key(self, k: Node) -> str:
        if k.type == "string":
            v = self._string_value(k)
            return v if v is not None else _text(k)
        return _text(k)

    def _pairs(self, obj: Node) -> tuple[PropertyFact, ...]:
        out = []
        for c in obj.children:
            if c.type == "pair":
                k, v = c.child_by_field_name("key"), c.child_by_field_name("value")
                if k is not None and v is not None:
                    out.append(PropertyFact(**self._pos(c), key=self._key(k), value=self._value(v, with_props=False)))
            elif c.type == "shorthand_property_identifier":
                out.append(PropertyFact(**self._pos(c), key=_text(c), value=None))
        return tuple(out)

    # --- 各構文 ---------------------------------------------------------
    def _call(self, n: Node) -> None:
        fn, args = n.child_by_field_name("function"), n.child_by_field_name("arguments")
        if fn is None:
            return
        arg_nodes = [c for c in (args.named_children if args is not None else []) if c.type != "comment"]
        if fn.type == "import":
            first = self._value(arg_nodes[0], False) if arg_nodes else None
            self.dynamic.append(DynamicImportFact(
                **self._pos(n),
                expression=first.expression if first else "",
                specifier=first.string_value if first and first.resolution == RES_STATIC else None,
                resolution=first.resolution if first else RES_DYNAMIC,
            ))
            return
        callee = _text(fn)
        ctrunc = len(callee) > MAX_EXPRESSION_CHARS
        values = tuple(self._value(a) for a in arg_nodes)
        self.calls.append(CallFact(**self._pos(n), callee=callee[:MAX_EXPRESSION_CHARS], args=values, callee_truncated=ctrunc))
        if fn.type == "identifier" and callee == "require" and values:
            v = values[0]
            self.imports.append(ImportFact(
                **self._pos(n), specifier=v.string_value if v.resolution == RES_STATIC else None,
                kind="require", resolution=v.resolution))

    def _import(self, n: Node) -> None:
        src = n.child_by_field_name("source")
        if src is None:
            return
        names: list[str] = []
        for c in n.children:
            if c.type != "import_clause":
                continue
            for d in c.children:
                if d.type == "identifier":
                    names.append("default")
                elif d.type == "namespace_import":
                    names.append("*")
                elif d.type == "named_imports":
                    for s in d.children:
                        if s.type == "import_specifier":
                            nm = s.child_by_field_name("name")
                            if nm is not None:
                                names.append(self._key(nm))
        self.imports.append(ImportFact(**self._pos(n), specifier=self._string_value(src), kind="import", names=tuple(names)))

    def _export(self, n: Node) -> None:
        pos = self._pos(n)
        src_n = n.child_by_field_name("source")
        source = self._string_value(src_n) if src_n is not None else None
        kids = [c.type for c in n.children]
        if source is not None:
            self.imports.append(ImportFact(**pos, specifier=source, kind="reexport"))
        if "*" in kids:
            self.exports.append(ExportFact(**pos, name="*", kind="all", source=source))
            return
        if "default" in kids:
            self.exports.append(ExportFact(**pos, name="default", kind="default", source=source))
            return
        for c in n.children:
            if c.type == "export_clause":
                for s in c.children:
                    if s.type == "export_specifier":
                        nm = s.child_by_field_name("alias") or s.child_by_field_name("name")
                        if nm is not None:
                            self.exports.append(ExportFact(**pos, name=self._key(nm), kind="named", source=source))
        decl = n.child_by_field_name("declaration")
        if decl is None:
            return
        if decl.type in ("function_declaration", "generator_function_declaration", "class_declaration"):
            nm = decl.child_by_field_name("name")
            if nm is not None:
                self.exports.append(ExportFact(**pos, name=_text(nm), kind="named"))
        elif decl.type in ("lexical_declaration", "variable_declaration"):
            for d in decl.children:
                nm = d.child_by_field_name("name") if d.type == "variable_declarator" else None
                if nm is not None and nm.type == "identifier":
                    self.exports.append(ExportFact(**pos, name=_text(nm), kind="named"))

    def _comment(self, n: Node) -> None:
        m = _SOURCEMAP_RE.search(_text(n))
        if m:
            url = m.group(1).rstrip("*/").strip() if _text(n).startswith("/*") else m.group(1)
            self.smap = SourceMapRef(**self._pos(n), url=url, inline=url.startswith("data:"))

    def _nearest_route(self, n: Node | None) -> int | None:
        steps = 0
        while n is not None and steps < 400:
            idx = self.route_by_node.get(n.id)
            if idx is not None:
                return idx
            n, steps = n.parent, steps + 1
        return None

    def _container(self, n: Node | None) -> str:
        steps = 0
        while n is not None and steps < 400:
            if n.type == "call_expression":
                fn = n.child_by_field_name("function")
                return _text(fn)[:200] if fn is not None else ""
            n, steps = n.parent, steps + 1
        return ""

    def _jsx(self, n: Node) -> None:
        attrs = []
        for c in n.children:
            if c.type != "jsx_attribute":
                continue
            kids = c.children
            if not kids:
                continue
            key = _text(kids[0])
            val = next((k for k in kids[1:] if k.type not in ("=",)), None)
            attrs.append(PropertyFact(**self._pos(c), key=key, value=self._value(val, False) if val is not None else None))
        if not any(a.key in _ROUTE_ATTRS for a in attrs):
            return
        name = n.child_by_field_name("name")
        if name is None:
            name = next((c for c in n.children if c.type in ("identifier", "member_expression", "nested_identifier", "jsx_namespace_name")), None)
        owner = n.parent if n.type == "jsx_opening_element" else n
        start = owner.parent if owner is not None else None
        parent = self._nearest_route(start)
        container = self._container(start)
        idx = len(self.routes)
        self.routes.append(RouteCandidateFact(
            **self._pos(owner if owner is not None else n), kind="jsx", tag=_text(name) if name is not None else "",
            properties=tuple(attrs), parent=parent, container=container))
        if owner is not None:
            self.route_by_node[owner.id] = idx

    def _object(self, n: Node) -> None:
        props = self._pairs(n)
        if not any(p.key == "path" for p in props):
            return
        parent = self._nearest_route(n.parent)
        idx = len(self.routes)
        self.routes.append(RouteCandidateFact(
            **self._pos(n), kind="object", properties=props, parent=parent, container=self._container(n.parent)))
        self.route_by_node[n.id] = idx


def _has_string_literal(n: Node) -> bool:
    stack, seen = [n], 0
    while stack and seen < 200:
        c = stack.pop()
        seen += 1
        if c.type in ("string", "template_string"):
            return True
        stack.extend(c.children)
    return False
