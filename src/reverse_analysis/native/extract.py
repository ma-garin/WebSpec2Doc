"""ParsedFile の呼び出し式から API 候補（StaticCandidate kind=api）を作る。

認識する呼び出し: fetch / XMLHttpRequest#open / axios.<method> / axios({method}) / $http / $http.<method> / $.ajax。
ベース URL の定数・ヘルパー関数経由の解決・到達しないコードの除外は `api_resolve.refine` を再利用する（重複実装しない）。
method が決まらないものは UNKNOWN、解決できない部分は :param、ベース URL が解決できなければ path を出さない。
入力 `calls` の位置は行 1 始まり・列 0 始まり（api_resolve と同じ）。
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from reverse_analysis import api_resolve
from reverse_analysis.models import Diagnostic, SourceLocation, StaticCandidate, static_candidate_id

AUTHORITY = "webspec2doc-native-ast"
_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
_HTTP = frozenset(m.upper() for m in _METHODS)
_ID = r"[A-Za-z_$][\w$]*"
_FETCH = re.compile(r"^(?:(?:window|self|globalThis)\.)?fetch$")
_AXIOS_M = re.compile(rf"^axios\.({'|'.join(_METHODS)})$")
_AXIOS = re.compile(r"^axios(?:\.request)?$")
_HTTP_SVC = re.compile(rf"^\$http(?:\.({'|'.join(_METHODS)}))?$")
_AJAX = re.compile(r"^(?:\$|jQuery)\.ajax$")
_OPEN = re.compile(rf"^{_ID}(?:\.{_ID})*\.open$")
_OPEN_METHOD = re.compile(r"""\(\s*(['"`])([A-Za-z]+)\1\s*,""")


def classify_call(callee: str, expression: str = "") -> tuple[str, str | None] | None:
    """(種別, 構文から決まる method) を返す。API 呼び出しでなければ None。method 不明は None（後で UNKNOWN）。"""
    callee = callee.strip()
    if _FETCH.match(callee):
        return "fetch", None
    if m := _AXIOS_M.match(callee):
        return "axios", m.group(1).upper()
    if _AXIOS.match(callee):
        return "axios", None
    if m := _HTTP_SVC.match(callee):
        return "$http", m.group(1).upper() if m.group(1) else None
    if _AJAX.match(callee):
        return "ajax", None
    if _OPEN.match(callee):
        # window.open(url, "_blank") と区別するため、第 1 引数が HTTP method の文字列のものだけ XHR とみなす
        m2 = _OPEN_METHOD.search(expression[len(callee):] if expression.startswith(callee) else expression)
        if m2 and m2.group(2).upper() in _HTTP:
            return "xhr", m2.group(2).upper()
    return None


def _cp_col(lines: list[str] | None, line: int, byte_col: int) -> int:
    """facts の列（1 始まり・UTF-8 バイト）を api_resolve の列（0 始まり・文字数）へ。"""
    if lines and 1 <= line <= len(lines):
        return len(lines[line - 1].encode("utf-8")[:max(byte_col - 1, 0)].decode("utf-8", "ignore"))
    return max(byte_col - 1, 0)


def _read_lines(js_input: Path | None, root_label: str, path: str) -> list[str] | None:
    if js_input is None:
        return None
    rel = path[len(root_label) + 1:] if root_label and path.startswith(root_label + "/") else path
    try:
        return (Path(js_input) / rel).read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeDecodeError):
        return None


def _expression(lines: list[str] | None, call, sl: int, sc: int, el: int, ec: int) -> str:
    if lines and el <= len(lines):
        if sl == el:
            return lines[sl - 1][sc:ec]
        return "\n".join([lines[sl - 1][sc:], *lines[sl:el - 1], lines[el - 1][:ec]])
    return f"{call.callee}({', '.join(a.expression for a in call.args)})"


def _initial(pf, call, kind: str, method: str | None, lines: list[str] | None) -> StaticCandidate:
    sc, ec = _cp_col(lines, call.line, call.col), _cp_col(lines, call.end_line, call.end_col)
    loc = SourceLocation(artifact_path=pf.path, unit="line_column_utf16", start_line=call.line, start_column=sc,
                         end_line=call.end_line, end_column=ec)
    return StaticCandidate(
        id=static_candidate_id(pf.sha256, loc, "api"), kind="api", artifact_path=pf.path, artifact_sha256=pf.sha256,
        location=loc, resolution="partial", epistemic_state="inferred", authority=AUTHORITY, method=method,
        expression=_expression(lines, call, call.line, sc, call.end_line, ec)[:200],
        limitations=(f"call_kind:{kind}", "path_not_syntactically_determined",
                     "provider:Static syntax does not prove that this relationship executes at runtime."))


def extract_api_candidates(parsed_files: Iterable, js_input: Path | None = None, root_label: str = "",
                           ) -> tuple[tuple[StaticCandidate, ...], tuple[Diagnostic, ...]]:
    """API 候補と診断を返す。js_input があれば api_resolve.refine でベース URL・method・ヘルパー経由を補う。"""
    initial: list[StaticCandidate] = []
    sha: dict[str, str] = {}
    for pf in parsed_files:
        sha[pf.path] = pf.sha256
        lines = _read_lines(js_input, root_label, pf.path)
        for call in pf.calls:
            hit = classify_call(call.callee, _expression(lines, call, call.line, _cp_col(lines, call.line, call.col),
                                                         call.end_line, _cp_col(lines, call.end_line, call.end_col)))
            if hit is not None:
                initial.append(_initial(pf, call, *hit, lines))
    if js_input is not None:
        refined, diags = api_resolve.refine(tuple(initial), Path(js_input), root_label, sha)
    else:
        refined, diags = tuple(initial), ()
    out, seen = [], set()
    for c in refined:
        if "call_kind:$http" in c.limitations and c.path is None and c.path_pattern is None:
            c = _http_literal(c)  # api_resolve は $http を知らない。文字列リテラルだけ読む
        if c.method is None:
            c = _with_unknown(c)
        if c.id in seen:
            continue
        seen.add(c.id)
        out.append(c)
    out.sort(key=lambda c: (c.artifact_path, c.location.start_line or 0, c.location.start_column or 0))
    return tuple(out), diags


_STR = r"""(['"])(/[^'"?#]*)(?:\?[^'"]*)?\1"""
_HTTP_ARG = re.compile(rf"\(\s*{_STR}")
_HTTP_OBJ_URL = re.compile(rf"\burl\s*:\s*{_STR}")
_HTTP_OBJ_METHOD = re.compile(r"\bmethod\s*:\s*['\"]([A-Za-z]+)['\"]")


def _http_literal(c: StaticCandidate) -> StaticCandidate:
    expr = c.expression or ""
    m = _HTTP_ARG.search(expr) or _HTTP_OBJ_URL.search(expr)
    if not m:
        return replace(c, limitations=tuple(dict.fromkeys((*c.limitations, "path_base_unresolved"))))
    mm = _HTTP_OBJ_METHOD.search(expr)
    method = c.method or (mm.group(1).upper() if mm and mm.group(1).upper() in _HTTP else ("GET" if mm is None and "{" in expr else None))
    return replace(c, path=m.group(2), method=method, limitations=tuple(dict.fromkeys(
        (*c.limitations, "path_from_string_literal", "method_from_static_syntax"))))


def _with_unknown(c: StaticCandidate) -> StaticCandidate:
    return replace(c, method="UNKNOWN", limitations=tuple(dict.fromkeys((*c.limitations, "method_unknown"))))
