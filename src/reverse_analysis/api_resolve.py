"""API 候補の呼び出し先と HTTP method を、配布済み JS の原文から有界に補う。

Native 解析は呼び出し位置（call 式の範囲）を返すが、ベース URL の定数・ヘルパー関数経由の呼び出し・
options の method を解決しない。ここでは次の範囲だけを静的に読む（JS は実行しない）:

- 静的な文字列の定数（const / let / var の初期値が文字列・テンプレート・連結だけのもの）。
  同じファイルの宣言を優先し、無ければ入力全体で 1 つだけの宣言を使う（ブラウザの script は大域を共有する）。
  再代入される変数・循環・2 つ以上の宣言は解決しない。
- 呼び出し先が fetch / XMLHttpRequest#open / axios.<method> と、それらへ引数をそのまま渡すヘルパー関数（3 段まで）。
- 構文上到達しないコード（if (false) の中・return の後）の候補は外す。どこからも呼ばれない関数は、
  HTML のイベント属性などから呼ばれうるので外さない。

解決できない部分は :param、先頭（ベース URL）が解決できなければ path を出さない。不明な method は UNKNOWN。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

from reverse_analysis.models import Diagnostic, SourceLocation, StaticCandidate, static_candidate_id

MAX_WRAPPER_DEPTH = 3
MAX_CONST_DEPTH = 8
AUTHORITY = "webspec2doc-bounded-static-resolution"
_ID = r"[A-Za-z_$][\w$]*"
_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
_NETWORK = re.compile(r"(?:^|\.)(?:fetch|open)$|^(?:axios|\$|jQuery)(?:\.(?:get|post|put|patch|delete|head|request|ajax))?$")
_DECL = re.compile(rf"\b(const|let|var)\s+({_ID})\s*=\s*")
_FUNC_DEFS = (
    re.compile(rf"\bfunction\s+({_ID})\s*\(([^)]*)\)\s*\{{"),
    re.compile(rf"(?<![\w$.])({_ID})\s*[:=]\s*function\s*(?:{_ID})?\s*\(([^)]*)\)\s*\{{"),
    re.compile(rf"(?<![\w$.])({_ID})\s*=\s*\(([^)]*)\)\s*=>\s*\{{"),
)
# 本体が式のアロー関数（const req = (m, u) => fetch(u, ...)）
_ARROW_EXPR = re.compile(rf"(?<![\w$.])({_ID})\s*=\s*(?:\(([^)]*)\)|({_ID}))\s*=>\s*(?!\{{)")


# ---------------------------------------------------------------- 字句の下ごしらえ

def mask_comments(src: str) -> str:
    """コメントを同じ長さの空白にする（改行は残す）。文字列・テンプレートの中は触らない。"""
    out, i, n = list(src), 0, len(src)
    while i < n:
        c = src[i]
        if c in "'\"`":
            i = _skip_string(src, i)
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            out[i:j] = " " * (j - i)
            i = j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out[i:j] = [ch if ch == "\n" else " " for ch in src[i:j]]
            i = j
            continue
        i += 1
    return "".join(out)


def _skip_string(src: str, i: int) -> int:
    """src[i] の引用符で始まる文字列の直後の位置。テンプレートの ${} は入れ子を数える。"""
    q, i, n = src[i], i + 1, len(src)
    while i < n:
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if q == "`" and src.startswith("${", i):
            i = _match(src, i + 1, "{", "}") + 1
            continue
        if c == q:
            return i + 1
        if c == "\n" and q != "`":
            return i + 1
        i += 1
    return n


def _match(src: str, i: int, open_: str, close: str) -> int:
    """src[i] == open_ に対応する close の位置。見つからなければ末尾。"""
    depth, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "'\"`":
            i = _skip_string(src, i)
            continue
        if c == open_:
            depth += 1
        elif c == close:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def _split_top(text: str, sep: str) -> list[str]:
    """括弧・文字列の外にある sep で分ける。"""
    parts, depth, start, i, n = [], 0, 0, 0, len(text)
    while i < n:
        c = text[i]
        if c in "'\"`":
            i = _skip_string(text, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return [p.strip() for p in parts]


def _strip_parens(text: str) -> str:
    t = text.strip()
    while t.startswith("(") and _match(t, 0, "(", ")") == len(t) - 1:
        t = t[1:-1].strip()
    return t


def _unescape(s: str) -> str:
    return re.sub(r"\\(.)", r"\1", s)


# ---------------------------------------------------------------- 入力

@dataclass
class _File:
    path: str
    text: str           # コメントを空白にした原文（位置は元のまま）
    line_starts: list[int]

    def offset(self, line: int | None, col: int | None) -> int | None:
        if not line or col is None or line > len(self.line_starts):
            return None
        return self.line_starts[line - 1] + col

    def line_col(self, off: int) -> tuple[int, int]:
        lo, hi = 0, len(self.line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.line_starts[mid] <= off:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1, off - self.line_starts[lo]


def _load(js_input: Path, root_label: str) -> dict[str, _File]:
    files: dict[str, _File] = {}
    for p in sorted(js_input.rglob("*")):
        if p.suffix.lower() not in (".js", ".mjs", ".cjs") or not p.is_file() or p.is_symlink():
            continue
        try:
            raw = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        text = mask_comments(raw)
        starts = [0] + [m.end() for m in re.finditer(r"\n", text)]
        rel = p.relative_to(js_input).as_posix()
        rel = f"{root_label}/{rel}" if root_label else rel
        files[rel] = _File(rel, text, starts)
    return files


# ---------------------------------------------------------------- 値の解決

_UNKNOWN = None  # 解決できない部分
_MARK = "\u0000"  # ヘルパー判定のために引数へ入れる目印


class _Resolver:
    def __init__(self, files: dict[str, _File]):
        self.files = files
        self.at: tuple[str, int] | None = None  # 解決中の呼び出しの位置（局所変数の宣言を選ぶため）
        self.decls: dict[str, list[tuple[str, str, str, int]]] = {}   # name -> [(path, kind, init, pos)]
        self.assigned: set[str] = set()
        self.funcs: dict[str, list[tuple[str, list[str], int, int]]] = {}  # name -> [(path, params, body_start, body_end)]
        for f in files.values():
            for m in _DECL.finditer(f.text):
                end = _statement_end(f.text, m.end())
                self.decls.setdefault(m.group(2), []).append((f.path, m.group(1), f.text[m.end():end].strip(), m.start()))
            for m in re.finditer(rf"(?<![\w$.])({_ID})\s*(?:[+\-*/]?=)(?!=|>)", f.text):
                before = f.text[max(0, m.start() - 6):m.start()]
                if not re.search(r"(?:const|let|var)\s+$", before):
                    self.assigned.add(m.group(1))
            for rx in _FUNC_DEFS:
                for m in rx.finditer(f.text):
                    brace = m.end() - 1
                    close = _match(f.text, brace, "{", "}")
                    params = [p.split("=")[0].strip() for p in m.group(2).split(",") if p.strip()]
                    self.funcs.setdefault(m.group(1), []).append((f.path, params, brace + 1, close))
            for m in _ARROW_EXPR.finditer(f.text):
                raw = m.group(2) if m.group(2) is not None else m.group(3)
                params = [p.split("=")[0].strip() for p in raw.split(",") if p.strip()]
                self.funcs.setdefault(m.group(1), []).append((f.path, params, m.end(), _statement_end(f.text, m.end())))

    # ---- 定数
    def const(self, name: str, path: str, depth: int) -> list | None:
        """静的な文字列定数の値（区切りのリスト）。解決できなければ None。"""
        ds = self.decls.get(name) or []
        if depth > MAX_CONST_DEPTH or not ds:
            return None
        same = [d for d in ds if d[0] == path]
        pick = same if same else ds
        if len(pick) != 1 and self.at is not None and self.at[0] == path:
            # 同じ名前の局所変数が複数あるときは、使う位置を囲む関数の中で、その位置より前の宣言だけを見る
            scope = self.scope_of(path, self.at[1])
            pick = [d for d in same if scope and scope[0] <= d[3] < self.at[1] <= scope[1]][-1:]
        if len(pick) != 1:
            return None
        dpath, kind, init, pos = pick[0]
        if kind != "const" and name in self.assigned:
            return None
        segs = self.segments(init, dpath, {}, depth + 1)
        if not segs:
            return None
        if all(s is not _UNKNOWN for s in segs):
            return segs
        # 関数の中の局所変数は、引数などが入る部分を :param のまま使う（先頭が分かるときだけ）
        local = self.scope_of(dpath, pos) is not None
        return segs if local and segs[0] is not _UNKNOWN else None

    # ---- 式
    def segments(self, expr: str, path: str, env: dict, depth: int) -> list:
        """式を文字列の区切りにする。分からない部分は _UNKNOWN。"""
        if depth > MAX_CONST_DEPTH + MAX_WRAPPER_DEPTH:
            return [_UNKNOWN]
        t = _strip_parens(expr)
        if not t:
            return [_UNKNOWN]
        parts = _split_top(t, "+")
        if len(parts) > 1:
            out: list = []
            for p in parts:
                out += self.segments(p, path, env, depth + 1)
            return out
        if len(t) >= 2 and t[0] in "'\"" and t[-1] == t[0] and _skip_string(t, 0) == len(t):
            return [_unescape(t[1:-1])]
        if len(t) >= 2 and t[0] == "`" and t[-1] == "`" and _skip_string(t, 0) == len(t):
            return self._template(t[1:-1], path, env, depth)
        if re.fullmatch(_ID, t):
            if t in env:
                arg, apath, aenv = env[t]
                return self.segments(arg, apath, aenv, depth + 1)
            c = self.const(t, path, depth)
            return c if c is not None else [_UNKNOWN]
        return [_UNKNOWN]

    def _template(self, body: str, path: str, env: dict, depth: int) -> list:
        out, i, buf = [], 0, ""
        while i < len(body):
            if body.startswith("${", i):
                j = _match(body, i + 1, "{", "}")
                out += [_unescape(buf)] if buf else []
                buf = ""
                out += self.segments(body[i + 2:j], path, env, depth + 1)
                i = j + 1
                continue
            if body[i] == "\\" and i + 1 < len(body):
                buf += body[i:i + 2]
                i += 2
                continue
            buf += body[i]
            i += 1
        if buf:
            out.append(_unescape(buf))
        return out

    def literal(self, expr: str, path: str, env: dict) -> str | None:
        segs = self.segments(expr, path, env, 0)
        return "".join(segs) if segs and all(s is not _UNKNOWN for s in segs) else None

    # ---- 呼び出し
    def call_info(self, call: str, path: str, env: dict, depth: int, offset: int | None = None):
        """call 式から (url の区切り, method)。ネットワーク呼び出しに辿れなければ None。"""
        m = re.match(rf"\s*((?:{_ID}\s*\.\s*)*{_ID})\s*\(", call)
        if not m:
            return None
        callee = re.sub(r"\s+", "", m.group(1))
        open_at = m.end() - 1
        args = _split_top(call[open_at + 1:_match(call, open_at, "(", ")")], ",")
        args = [a for a in args if a]
        name = callee.split(".")[-1]
        if depth == 0:
            self.at = (path, offset) if offset is not None else None
        if _NETWORK.search(callee):
            if name == "open":  # XMLHttpRequest#open(method, url)。window.open(url) は画面を開くだけ
                lit = self.literal(args[0], path, env) if args else None
                lit = None if lit is not None and _MARK in lit else lit  # ヘルパー判定中の引数は不明扱い
                if len(args) < 2 or callee.startswith("window.") or (lit is not None and lit.upper() not in _HTTP_METHODS):
                    return None
                return self.segments(args[1], path, env, 0), self._method(args[0], path, env)
            if name in ("get", "post", "put", "patch", "delete", "head") and "." in callee:
                return (self.segments(args[0], path, env, 0), name.upper()) if args else None
            if not args:
                return None
            if args[0].startswith("{"):  # axios({ url, method }) / $.ajax({ url, type })
                return self._from_options(args[0], path, env, offset, url_key=True)
            method = "GET"
            if len(args) > 1:
                method = self._options_method(args[1], path, env, offset) or "UNKNOWN"
            return self.segments(args[0], path, env, 0), method
        if depth >= MAX_WRAPPER_DEPTH:
            return None
        defs = self.funcs.get(name) or []
        if len(defs) != 1:
            return None
        dpath, params, b0, b1 = defs[0]
        inner_env = {p: (args[i], path, env) for i, p in enumerate(params) if i < len(args)}
        for p in params[len(args):]:
            inner_env[p] = ("undefined", path, {})
        body = self.files[dpath].text
        for cm in re.finditer(rf"(?<![\w$])((?:{_ID}\s*\.\s*)*{_ID})\s*\(", body[b0:b1]):
            if re.match(r"(?:if|for|while|switch|return|function|catch)$", cm.group(1)):
                continue
            start = b0 + cm.start(1)
            end = _match(body, b0 + cm.end() - 1, "(", ")") + 1
            info = self.call_info(body[start:end], dpath, inner_env, depth + 1, start)
            if info is not None:
                return info
        return None

    def wrappers(self) -> set[str]:
        """呼び出し先の url が引数で決まる関数（ヘルパー）の名前。"""
        out = set()
        for name, defs in self.funcs.items():
            if len(defs) != 1 or not defs[0][1]:
                continue
            args = ", ".join(f'"{_MARK}"' for _ in defs[0][1])
            info = self.call_info(f"{name}({args})", defs[0][0], {}, 0)
            segs = info[0] if info is not None else []
            at = next((i for i, x in enumerate(segs) if isinstance(x, str) and _MARK in x), None)
            if at is None:
                continue
            # 引数が URL そのもの・path の続き（API + path）ならヘルパー。「/items/」の後ろの id は path パラメータ
            before = segs[at - 1] if at else None
            if at == 0 or segs[at].index(_MARK) > 0 or not (isinstance(before, str) and before.endswith("/")):
                out.add(name)
        return out

    def scope_of(self, path: str, off: int) -> tuple[int, int] | None:
        """off を含むいちばん内側の関数本体の範囲。"""
        best = None
        for defs in self.funcs.values():
            for dpath, _params, b0, b1 in defs:
                if dpath == path and b0 <= off <= b1 and (best is None or b0 > best[0]):
                    best = (b0, b1)
        return best

    def enclosing_function(self, path: str, off: int) -> str | None:
        """off を含む関数定義の名前（いちばん内側）。"""
        best = None
        for name, defs in self.funcs.items():
            for dpath, _params, b0, b1 in defs:
                if dpath == path and b0 <= off <= b1 and (best is None or b0 > best[1]):
                    best = (name, b0)
        return best[0] if best else None

    def _method(self, expr: str, path: str, env: dict) -> str:
        lit = self.literal(expr, path, env)
        return lit.upper() if lit and lit.upper() in _HTTP_METHODS else "UNKNOWN"

    def _options_method(self, expr: str, path: str, env: dict, offset: int | None) -> str | None:
        obj = self._object_text(expr, path, env, offset)
        if obj is None:
            return None
        value = _object_key(obj, ("method", "type"))
        return "GET" if value is None else self._method(value, path, env)

    def _from_options(self, expr: str, path: str, env: dict, offset: int | None, url_key: bool):
        obj = self._object_text(expr, path, env, offset)
        url = _object_key(obj or "", ("url",))
        if url is None:
            return None
        value = _object_key(obj, ("method", "type"))
        return self.segments(url, path, env, 0), ("GET" if value is None else self._method(value, path, env))

    def _object_text(self, expr: str, path: str, env: dict, offset: int | None) -> str | None:
        t = _strip_parens(expr)
        if t.startswith("{"):
            return t
        if re.fullmatch(_ID, t):
            if t in env:
                arg, apath, aenv = env[t]
                return self._object_text(arg, apath, aenv, None)
            text = self.files[path].text if path in self.files else ""
            limit = offset if offset is not None else len(text)
            found = [m for m in re.finditer(rf"\b(?:const|let|var)\s+{re.escape(t)}\s*=\s*\{{", text[:limit])]
            if len(found) == 1:
                b = found[0].end() - 1
                return text[b:_match(text, b, "{", "}") + 1]
        return None


def _statement_end(text: str, i: int) -> int:
    depth, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "'\"`":
            i = _skip_string(text, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif depth == 0 and c in ";\n,":
            return i
        i += 1
    return n


def _object_key(obj: str, keys: tuple[str, ...]) -> str | None:
    """オブジェクトリテラルの最上位のキーの値の式。省略記法（{ method }）も扱う。"""
    inner = obj.strip()[1:-1] if obj.strip().startswith("{") else ""
    for part in _split_top(inner, ","):
        m = re.match(rf"""\s*['"]?({_ID})['"]?\s*(?::\s*(.*))?$""", part, re.S)
        if m and m.group(1) in keys:
            return m.group(2).strip() if m.group(2) is not None else m.group(1)
    return None


# ---------------------------------------------------------------- 到達しないコード

def _enclosing_braces(text: str, off: int) -> list[int]:
    """off を囲む '{' の位置（内側から）。"""
    stack, i = [], 0
    while i < off:
        c = text[i]
        if c in "'\"`":
            i = _skip_string(text, i)
            continue
        if c == "{":
            stack.append(i)
        elif c == "}" and stack:
            stack.pop()
        i += 1
    return stack[::-1]


def dead_reason(files: dict[str, _File], path: str, off: int) -> str | None:
    f = files.get(path)
    if f is None:
        return None
    text = f.text
    braces = _enclosing_braces(text, off)
    for b in braces:
        if re.search(r"\bif\s*\(\s*(?:false|0)\s*\)\s*$", text[:b]):
            return "if (false) の中"
    if braces and _returned_before(text, braces[0] + 1, off):
        return "return の後"
    return None


def _returned_before(text: str, start: int, off: int) -> bool:
    """同じブロックで、off より前に終わった return 文があるか。"""
    depth, i, in_return = 0, start, False
    while i < off:
        c = text[i]
        if c in "'\"`":
            i = _skip_string(text, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0:
            if text.startswith("return", i) and not re.match(r"[\w$]", text[i - 1:i]) and not re.match(r"[\w$]", text[i + 6:i + 7]):
                in_return = True
                i += 6
                continue
            if in_return and c == ";":
                return True
        i += 1
    return False


# ---------------------------------------------------------------- 候補の補正

def _path_of(segs: list) -> tuple[str | None, str | None, bool]:
    """区切りから (origin, path, query 依存)。先頭が不明なら path は出さない。"""
    if not segs or segs[0] is _UNKNOWN:
        return None, None, False
    text = "".join(":param" if s is _UNKNOWN else s for s in segs)
    origin = None
    m = re.match(r"(https?:)?//([^/?#]+)", text)
    if m:
        origin = f"{m.group(1) or ''}//{m.group(2)}"
        text = text[m.end():] or "/"
    if not text.startswith("/"):
        return origin, None, False  # 相対 URL は文書の場所が分からないので解決しない
    path, _, query = text.partition("?")
    return origin, path, bool(query)


def refine(candidates: tuple[StaticCandidate, ...], js_input: Path, root_label: str,
           artifact_sha: dict[str, str] | None = None) -> tuple[tuple[StaticCandidate, ...], tuple[Diagnostic, ...]]:
    """API 候補の path・origin・method を補い、ヘルパー経由の呼び出しを加え、到達しないコードの候補を外す。"""
    try:
        files = _load(js_input, root_label)
    except OSError:
        return candidates, ()
    if not files:
        return candidates, ()
    res = _Resolver(files)
    wrappers = res.wrappers()
    out: list[StaticCandidate] = []
    inner: list[tuple[str, StaticCandidate, str, int]] = []
    expanded: set[str] = set()
    seen: set[tuple[str, int]] = set()
    dead: list[str] = []
    sha = {**(artifact_sha or {}), **{c.artifact_path: c.artifact_sha256 for c in candidates}}
    for c in candidates:
        f = files.get(c.artifact_path)
        loc = c.location
        start = f.offset(loc.start_line, loc.start_column) if f else None
        end = f.offset(loc.end_line, loc.end_column) if f else None
        if c.kind != "api" or f is None or start is None or end is None:
            out.append(c)
            continue
        seen.add((c.artifact_path, start))
        why = dead_reason(files, c.artifact_path, start)
        if why:
            dead.append(f"{c.artifact_path}:{loc.start_line}（{why}）")
            continue
        owner = res.enclosing_function(c.artifact_path, start)
        if owner in wrappers:
            inner.append((owner, c, f.text[start:end], start))  # 呼び出し位置を展開できたかで扱いを決める
            continue
        out.append(_apply(c, res.call_info(f.text[start:end], c.artifact_path, {}, 0, start)))
    # ヘルパー関数（引数を呼び出し先へ渡す関数）の呼び出し位置を、解析が出していなければ加える
    # 解析が出さなかったネットワーク呼び出し（fetch・XMLHttpRequest#open・axios.<method>）も同じ方法で加える
    names = [rf"(?<![\w$]){re.escape(n)}" for n in sorted(wrappers)]  # obj.method( の呼び出しも含む
    names += [r"(?<![\w$.])fetch", r"\.open", r"(?<![\w$.])axios(?:\.(?:get|post|put|patch|delete|head))?"]
    for pattern in names:
        for f in files.values():
            for m in re.finditer(rf"{pattern}\s*\(", f.text):
                if re.search(r"function\s*$", f.text[max(0, m.start() - 12):m.start()]):
                    continue
                start = m.start()
                if pattern == r"\.open":
                    start = _callee_start(f.text, start)
                if pattern in names[:len(wrappers)] and f.text[start - 1:start] == ".":
                    start = _callee_start(f.text, start - 1)
                if (f.path, start) in seen or res.enclosing_function(f.path, start) in wrappers:
                    continue
                end = _match(f.text, m.end() - 1, "(", ")") + 1
                info = res.call_info(f.text[start:end], f.path, {}, 0, start)
                if info is None or _path_of(info[0])[1] is None:
                    continue
                seen.add((f.path, start))
                if pattern in names[:len(wrappers)]:
                    expanded.add(sorted(wrappers)[names.index(pattern)])
                if dead_reason(files, f.path, start):
                    dead.append(f"{f.path}:{f.line_col(start)[0]}（到達しないコード）")
                    continue
                out.append(_wrapper_candidate(f, start, end, info, sha.get(f.path, ""),
                                              "called_through_helper_function" if pattern in names[:len(wrappers)]
                                              else "found_by_bounded_static_scan"))
    for owner, c, call, start in inner:
        if owner in expanded:
            # 呼び出し位置ごとの候補で表したので、ヘルパーの中の呼び出しは値を出さない
            out.append(replace(c, limitations=tuple(dict.fromkeys((*c.limitations, "url_from_helper_caller")))))
        else:
            out.append(_apply(c, res.call_info(call, c.artifact_path, {}, 0, start)))
    diags: tuple[Diagnostic, ...] = ()
    if dead:
        diags = (Diagnostic(
            "api_unreachable_excluded", "info", "static",
            f"構文上到達しないコード（if (false) の中・return の後）にある API 呼び出し {len(dead)} 件を候補から外しました: " + "、".join(dead[:10]),
            "外した呼び出しが実際に使われるなら、その画面を操作して実測で確かめてください。"),)
    return tuple(out), diags


def _callee_start(text: str, dot: int) -> int:
    """「xhr.open(」の「.」から、受け手（xhr）の先頭へ戻る。"""
    i = dot
    while i > 0 and re.match(r"[\w$.]", text[i - 1]):
        i -= 1
    return i


def _apply(c: StaticCandidate, info) -> StaticCandidate:
    if info is None:
        return c
    segs, method = info
    origin, path, query = _path_of(segs)
    lim = list(c.limitations)
    if path is None:
        lim.append("path_base_unresolved")
        return replace(c, limitations=tuple(dict.fromkeys(lim)))
    exact = all(s is not _UNKNOWN for s in segs)
    lim = [x for x in lim if x not in ("path_not_syntactically_determined", "method_not_provided_by_provider")]
    lim.append("path_resolved_by_static_constants")
    lim.append("method_from_static_syntax")  # fetch の options 省略は仕様上 GET。実行で確かめた値ではない
    if method == "UNKNOWN":
        lim.append("method_unknown")
    # 確定した値だけを path に入れる。引数が入る候補は path_pattern に留める（resolution は変えない）
    return replace(c, path=c.path or (path if exact else None), path_pattern=None if exact else path,
                   origin=c.origin or origin, method=c.method or method, query_dependent=c.query_dependent or query,
                   limitations=tuple(dict.fromkeys(lim)))


def _wrapper_candidate(f: _File, start: int, end: int, info, sha: str, how: str) -> StaticCandidate:
    sl, sc = f.line_col(start)
    el, ec = f.line_col(end)
    loc = SourceLocation(artifact_path=f.path, unit="line_column_utf16", start_line=sl, start_column=sc,
                         end_line=el, end_column=ec)
    segs, method = info
    origin, path, query = _path_of(segs)
    exact = all(s is not _UNKNOWN for s in segs)
    lim = [how, "method_from_static_syntax", "provider:Static syntax does not prove that this relationship executes at runtime."]
    if method == "UNKNOWN":
        lim.append("method_unknown")
    return StaticCandidate(
        id=static_candidate_id(sha, loc, "api"), kind="api", artifact_path=f.path, artifact_sha256=sha,
        location=loc, resolution="partial", epistemic_state="inferred", authority=AUTHORITY,
        method=method, origin=origin, path=path if exact else None, path_pattern=None if exact else path,
        expression=f.text[start:end][:200], query_dependent=query, limitations=tuple(lim))
