"""ソースツリー走査によるルート定義抽出（Code Fusion の入口）。

AST の全解析はしない。**ルート定義の宣言箇所だけ**を行単位の正規表現で拾い、
`CodeBundle` に正規化する。目的は「ソース上にルート定義が存在する」という
事実の収集であり、到達可能性や実装済みかどうかは一切主張しない
（`code_models.CLAIM_NOTICE` を参照）。

対応フレームワーク:

- flask: ``@bp.route(<path>, methods=[...])`` / ``@bp.get(<path>)`` 等の短縮形 /
  ``add_url_rule(<path>, ...)``。同一ファイル内の ``Blueprint(..., url_prefix=...)``
  を prefix として保持する（結合はしない）。
- fastapi: ``@app.get(<path>)`` / ``@router.post(<path>)`` 等。
  ``APIRouter(prefix="/api")`` を prefix として保持する。
- django: ``urlpatterns`` を含むファイルの ``path()`` / ``re_path()``。
- express: js/ts の ``app.get(<path>, handler)`` / ``router.post(<path>, handler)``。
- nextjs: ファイルパス規約（``pages/**`` と ``app/**/page.*``・``app/**/route.*``）。

flask と fastapi は短縮形デコレータ（``@x.get(...)``）の記法が同一のため、
ファイル内の import / ``Blueprint(`` / ``APIRouter(`` から所属を判定する。
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from ingest.code_models import (
    KIND_API,
    KIND_PAGE,
    CodeBundle,
    CodeEvidence,
    CodeRoute,
)

logger = logging.getLogger(__name__)

#: 走査対象外のディレクトリ名
EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "venv",
        ".venv",
        "__pycache__",
        "dist",
        "build",
        ".next",
        "site-packages",
        "coverage",
        "htmlcov",
        ".mypy_cache",
        ".pytest_cache",
        "vendor",
    }
)

#: 走査対象の拡張子
SOURCE_SUFFIXES: frozenset[str] = frozenset({".py", ".js", ".jsx", ".ts", ".tsx"})

#: これを超えるサイズのファイルはスキップする（バイト）
MAX_FILE_BYTES: int = 2 * 1024 * 1024

#: evidence.quote の最大長
MAX_QUOTE_CHARS: int = 200

#: デコレータの直後から handler 定義を探す最大行数
HANDLER_LOOKAHEAD: int = 5

#: 複数行にまたがる呼び出しを連結する最大行数
JOIN_LOOKAHEAD: int = 10

FRAMEWORK_FLASK = "flask"
FRAMEWORK_FASTAPI = "fastapi"
FRAMEWORK_DJANGO = "django"
FRAMEWORK_EXPRESS = "express"
FRAMEWORK_NEXTJS = "nextjs"

_HTTP_VERBS = ("get", "post", "put", "patch", "delete", "head", "options")

# --- 正規表現 -------------------------------------------------------------

_PY_DECORATOR_RE = re.compile(
    r"""^\s*@\s*(?P<obj>[A-Za-z_][\w.]*)\s*\.\s*
        (?P<verb>route|get|post|put|patch|delete|head|options)\s*\(\s*
        (?:[rbuf]{1,2})?(?P<q>['"])(?P<path>(?:\\.|(?!(?P=q)).)*)(?P=q)""",
    re.VERBOSE,
)

_ADD_URL_RULE_RE = re.compile(
    r"""(?:(?P<obj>[A-Za-z_][\w.]*)\s*\.\s*)?add_url_rule\s*\(\s*(?:[rbuf]{1,2})?(?P<q>['"])
        (?P<path>(?:\\.|(?!(?P=q)).)*)(?P=q)(?P<rest>.*)""",
    re.VERBOSE | re.DOTALL,
)

#: 文字列リテラル以外のパス（定数・変数）を渡しているデコレータの検出用。
#: 例: ``@bp.get(TENANT_SELECT_PATH)``。黙って落とすと欠落が利用者に伝わらないため、
#: これを検出して `skipped` に積む（モジュール定数の解決まではしない）。
_PY_DECORATOR_HEAD_RE = re.compile(
    r"""^\s*@\s*(?P<obj>[A-Za-z_][\w.]*)\s*\.\s*
        (?P<verb>route|get|post|put|patch|delete|head|options)\s*\(\s*(?P<arg>[^)]*)""",
    re.VERBOSE,
)

_METHODS_RE = re.compile(r"methods\s*=\s*[\[(](?P<body>[^\])]*)[\])]", re.DOTALL)
#: `methods=` の存在自体（値がリテラルでない場合の検出に使う）
_METHODS_PRESENT_RE = re.compile(r"\bmethods\s*=")

_BLUEPRINT_RE = re.compile(r"\bBlueprint\s*\(")
_APIROUTER_RE = re.compile(r"\bAPIRouter\s*\(")
#: ``名前 = Blueprint(...)`` / ``名前 = APIRouter(...)`` の代入先を取る
_PY_ROUTER_ASSIGN_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z_]\w*)\s*=\s*(?:[\w.]+\.)?(?:Blueprint|APIRouter)\s*\("
)
_URL_PREFIX_RE = re.compile(r"url_prefix\s*=\s*(?:[rbuf]{1,2})?['\"](?P<v>[^'\"]*)['\"]")
_PREFIX_RE = re.compile(r"\bprefix\s*=\s*(?:[rbuf]{1,2})?['\"](?P<v>[^'\"]*)['\"]")

_FLASK_IMPORT_RE = re.compile(r"^\s*(?:from\s+flask|import\s+flask)\b", re.MULTILINE)
_FASTAPI_IMPORT_RE = re.compile(r"^\s*(?:from\s+fastapi|import\s+fastapi)\b", re.MULTILINE)

_DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+(?P<name>[A-Za-z_]\w*)\s*\(")

_DJANGO_PATH_RE = re.compile(
    r"""(?<![\w.])(?P<fn>re_path|path)\s*\(\s*(?:[rbuf]{1,2})?
        (?P<q>['"])(?P<path>(?:\\.|(?!(?P=q)).)*)(?P=q)
        \s*,\s*(?P<view>[^,)\n]*)""",
    re.VERBOSE,
)

_EXPRESS_RE = re.compile(
    r"""(?<![\w.$@])(?P<obj>app|router|server|api|[A-Za-z_$][\w$]*(?:Router|App))\s*\.\s*
        (?P<verb>get|post|put|patch|delete|head|options)\s*\(\s*
        (?P<q>['"`])(?P<path>[^'"`]*)(?P=q)\s*,\s*(?P<view>[^,)\n]*)""",
    re.VERBOSE,
)

_NEXT_EXPORTED_METHOD_RE = re.compile(
    r"export\s+(?:async\s+)?(?:function\s+|const\s+)(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b"
)

_NEXT_EXCLUDED_STEMS: frozenset[str] = frozenset({"_app", "_document", "_error"})

#: Next.js プロジェクトであることを示すファイル
_NEXT_CONFIG_NAMES: tuple[str, ...] = (
    "next.config.js",
    "next.config.mjs",
    "next.config.cjs",
    "next.config.ts",
)

_NEXT_DEP_RE = re.compile(r'"next"\s*:')

# --- kind 判定の材料 ------------------------------------------------------

#: ハンドラ本体にこれがあれば「画面ではなく応答体を直接返している」とみなす。
#: `make_response(` を含めるのは、`/open` のように副作用だけ実行して
#: `make_response(redirect(...))` を返す操作系エンドポイントが画面として
#: QA の未到達リストに載っていたため（実測で確認した誤計上）。
_API_BODY_RE = re.compile(r"\b(?:jsonify|make_response|send_file|send_from_directory|Response)\s*\(")

#: ハンドラ本体にこれがあれば HTML 応答（画面）とみなし、上の判定より優先する。
#: `send_from_directory(SITE_DIR, "index.html")` のように静的 HTML を返す
#: 画面ルートを API に落とさないため。
_HTML_BODY_RE = re.compile(r"render_template|\.html\b|\.htm\b|text/html")

#: ハンドラ名がこれに該当したら API（本リポの `api_review_cases` 等の実例に対応）
_API_HANDLER_PREFIX = "api_"
_API_HANDLER_SUFFIX = "_api"

#: パス末尾がこれらの拡張子なら静的・データ応答とみなす（.html / .htm は除く）
_API_PATH_SUFFIXES: frozenset[str] = frozenset(
    {
        ".json",
        ".xml",
        ".txt",
        ".csv",
        ".tsv",
        ".ico",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".css",
        ".js",
        ".map",
        ".pdf",
        ".zip",
        ".yaml",
        ".yml",
        ".xlsx",
    }
)

#: `/api` を「パス区切りで独立したセグメント」として判定する。
#: 単純な startswith だと `/apidocs` `/apiary` まで API に落ちるため。
_API_SEGMENT_RE = re.compile(r"(?:^|/)api(?:/|$)")

#: ハンドラ本体を読む最大行数（デコレータから次の定義まで）
_BODY_MAX_LINES: int = 200


# --- 内部ユーティリティ ---------------------------------------------------


def _blank_python_noncode(text: str) -> str:
    """Python ソースの三重引用符ブロックと `#` コメントを空白化する。

    docstring 中の ``@bp.route("/only-documentation")`` が実ルートとして
    計上されていたため（実測で確認）。行番号が evidence とずれないよう、
    除去部分は同じ長さの空白と改行に置き換える（行数・列位置は不変）。
    単一行の文字列リテラルは実際のパス指定そのものなので触らない。
    """
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "#":
            while index < length and text[index] != "\n":
                out.append(" ")
                index += 1
            continue
        if char in "\"'":
            triple = text[index : index + 3]
            if triple in ('"""', "'''"):
                closing = triple
                index += 3
                out.append("   ")
                while index < length and text[index : index + 3] != closing:
                    out.append("\n" if text[index] == "\n" else " ")
                    index += 1
                if index < length:
                    index += 3
                    out.append("   ")
                continue
            quote = char
            out.append(char)
            index += 1
            while index < length and text[index] != quote:
                if text[index] == "\\" and index + 1 < length:
                    out.append(text[index])
                    index += 1
                    if index >= length:
                        break
                if text[index] == "\n":  # 閉じないままの行末（構文エラー等）は打ち切る
                    break
                out.append(text[index])
                index += 1
            if index < length and text[index] == quote:
                out.append(quote)
                index += 1
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _blank_js_noncode(text: str) -> str:
    """js/ts ソースのブロックコメント `/* */` と行コメント `//` を空白化する。

    Python 側と同じ理由（コメント内の擬似ルートの誤計上）。`"https://x"` の
    `//` をコメントと誤認しないよう、文字列・テンプレートリテラルの中は
    そのまま残す。正規表現リテラルは判別しないため触らない。
    """
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        pair = text[index : index + 2]
        if pair == "//":
            while index < length and text[index] != "\n":
                out.append(" ")
                index += 1
            continue
        if pair == "/*":
            index += 2
            out.append("  ")
            while index < length and text[index : index + 2] != "*/":
                out.append("\n" if text[index] == "\n" else " ")
                index += 1
            if index < length:
                index += 2
                out.append("  ")
            continue
        char = text[index]
        if char in "\"'`":
            quote = char
            out.append(char)
            index += 1
            while index < length and text[index] != quote:
                if text[index] == "\\" and index + 1 < length:
                    out.append(text[index])
                    index += 1
                if text[index] == "\n" and quote != "`":
                    break
                out.append(text[index])
                index += 1
            if index < length and text[index] == quote:
                out.append(quote)
                index += 1
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _quote_of(line: str) -> str:
    """evidence 用に行を strip して最大長で切り詰める。"""
    return line.strip()[:MAX_QUOTE_CHARS]


def _join_statement(lines: list[str], index: int) -> str:
    """`index` 行目から括弧が閉じるまでを連結した論理行を返す。"""
    text = lines[index]
    depth = text.count("(") - text.count(")")
    cursor = index
    while depth > 0 and cursor + 1 < len(lines) and cursor - index < JOIN_LOOKAHEAD:
        cursor += 1
        text += " " + lines[cursor].strip()
        depth += lines[cursor].count("(") - lines[cursor].count(")")
    return text


def _parse_methods(text: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """`methods=[...]` を抽出して大文字タプルにする（重複は順序保持で除去）。

    `methods=` はあるが値がリテラルでない場合（``methods=POST_ONLY`` /
    ``methods=[*POST_ONLY]``）は **空タプル（= 不明）** を返す。
    ここで `("GET",)` と断定すると POST 専用 API が画面ルート扱いになり
    「デッドコードの疑い」と誤報されるため、GET と断定しない。
    """
    match = _METHODS_RE.search(text)
    if match is None:
        # `methods=` 自体が無ければ既定（省略時の挙動）。あるなら不明。
        return default if _METHODS_PRESENT_RE.search(text) is None else ()
    found: list[str] = []
    for raw in re.findall(r"['\"]([A-Za-z]+)['\"]", match.group("body")):
        verb = raw.upper()
        if verb not in found:
            found.append(verb)
    return tuple(found) if found else ()


def _find_handler(lines: list[str], index: int) -> str:
    """デコレータ行の直後から関数定義名を探す（最大 HANDLER_LOOKAHEAD 行）。"""
    for offset in range(1, HANDLER_LOOKAHEAD + 1):
        cursor = index + offset
        if cursor >= len(lines):
            break
        match = _DEF_RE.match(lines[cursor])
        if match is not None:
            return match.group("name")
    return ""


def _clean_identifier(raw: str) -> str:
    """view 引数のような断片から識別子らしい部分だけを取り出す。"""
    token = raw.strip().strip("'\"")
    match = re.match(r"^[A-Za-z_$][\w$.]*", token)
    return match.group(0) if match else ""


def _ensure_leading_slash(path: str) -> str:
    """先頭に `/` が無ければ付ける（正規表現アンカー `^` は除去する）。"""
    cleaned = path.lstrip("^")
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    return cleaned


def _handler_body(lines: list[str], index: int) -> str:
    """デコレータ行 `index` に続くハンドラ本体のテキストを返す。

    デコレータの連なりと関数定義行を読み飛ばし、デコレータより深い
    インデントの行を本体として集める（次の `def` / `@` / dedent で打ち切る）。
    kind 判定のため「何を返しているか」だけを見る用途なので、この粒度で足りる。
    """
    decorator_indent = len(lines[index]) - len(lines[index].lstrip())
    collected: list[str] = []
    seen_def = False
    for cursor in range(index + 1, min(len(lines), index + 1 + _BODY_MAX_LINES)):
        line = lines[cursor]
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if not seen_def:
            if _DEF_RE.match(line) is not None:
                seen_def = True
                collected.append(line)
                continue
            if line.lstrip().startswith("@"):
                continue
            break
        if indent <= decorator_indent:
            break
        collected.append(line)
    return "\n".join(collected)


def _decide_kind(
    path: str,
    prefix: str,
    methods: tuple[str, ...],
    framework: str,
    *,
    force_api: bool = False,
    handler: str = "",
    body: str = "",
) -> str:
    """ルート種別（page / api）を判定する。

    JSON・ファイル・メトリクスを返すエンドポイントが page に混ざると、
    QA の未到達リストと到達率の母数が汚れる（本リポで 11 件の実測）。
    そのためパス以外に **ハンドラ名・パス拡張子・ハンドラ本体**も材料にする。
    `methods` が空タプルのときは「不明」であり、GET と断定できない以上
    画面ルートの母数には入れない。
    """
    if force_api:
        return KIND_API
    combined = f"{prefix}{path}" if prefix else path

    if handler.startswith(_API_HANDLER_PREFIX) or handler.endswith(_API_HANDLER_SUFFIX):
        return KIND_API
    if Path(combined.split("?", 1)[0]).suffix.lower() in _API_PATH_SUFFIXES:
        return KIND_API
    if body and _API_BODY_RE.search(body) is not None and _HTML_BODY_RE.search(body) is None:
        return KIND_API

    # `/api` そのもの、または `/api/...` のみを API とする（`/apidocs` は対象外）。
    if combined == "/api" or combined.startswith("/api/"):
        return KIND_API
    if framework in (FRAMEWORK_FASTAPI, FRAMEWORK_EXPRESS) and _API_SEGMENT_RE.search(combined):
        return KIND_API
    if not ({"GET", "HEAD"} & set(methods)):
        return KIND_API
    return KIND_PAGE


def _python_framework(text: str) -> tuple[bool, bool]:
    """Python ソースが flask / fastapi のどちらに属するかの判定材料を返す。"""
    is_flask = bool(_FLASK_IMPORT_RE.search(text)) or bool(_BLUEPRINT_RE.search(text))
    is_fastapi = bool(_FASTAPI_IMPORT_RE.search(text)) or bool(_APIROUTER_RE.search(text))
    return is_flask, is_fastapi


def _python_prefix_map(lines: list[str]) -> dict[str, str]:
    """`変数名 -> prefix` の対応表を Blueprint / APIRouter 宣言から作る。

    以前は「url_prefix を持つ最初の 1 件」を返していたため、同一ファイルに
    ``pages_bp = Blueprint(...)`` と ``api_bp = Blueprint(..., url_prefix="/api/v2")``
    が並ぶと `@pages_bp.route("/dashboard")` にまで `/api/v2` が付いていた。
    デコレータのオブジェクト名で引き当て、引き当たらなければ prefix は "" とする。
    """
    mapping: dict[str, str] = {}
    for index, line in enumerate(lines):
        if _BLUEPRINT_RE.search(line) is None and _APIROUTER_RE.search(line) is None:
            continue
        assign = _PY_ROUTER_ASSIGN_RE.match(line)
        if assign is None:
            continue
        statement = _join_statement(lines, index)
        # Blueprint は url_prefix=、APIRouter は prefix= を使う
        match = _URL_PREFIX_RE.search(statement) or _PREFIX_RE.search(statement)
        mapping[assign.group("name")] = match.group("v") if match is not None else ""
    return mapping


# --- フレームワーク別の抽出 -----------------------------------------------


def _scan_python(rel_path: str, raw_text: str) -> tuple[list[CodeRoute], list[str]]:
    """Python ソースから flask / fastapi / django のルート定義を抽出する。

    Returns:
        (抽出したルート, スキップ理由のリスト)。パスが文字列リテラルでない
        デコレータは抽出できないが、黙って落とすと利用者に欠落が伝わらないため
        ``"<相対パス>:<行>: dynamic path"`` として 2 つ目に返す。
    """
    original = raw_text.splitlines()
    text = _blank_python_noncode(raw_text)  # docstring / コメント内の擬似ルートを除去
    lines = text.splitlines()
    routes: list[CodeRoute] = []
    skipped: list[str] = []
    is_flask, is_fastapi = _python_framework(text)

    prefix_map = _python_prefix_map(lines)

    def _quote_at(position: int) -> str:
        return _quote_of(original[position]) if position < len(original) else ""

    for index, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        statement = _join_statement(lines, index)

        match = _PY_DECORATOR_RE.match(statement)
        if match is None and (is_flask or is_fastapi):
            head = _PY_DECORATOR_HEAD_RE.match(statement)
            if head is not None and not head.group("arg").lstrip().startswith(("'", '"')):
                skipped.append(f"{rel_path}:{index + 1}: dynamic path")
                continue
        if match is not None:
            verb = match.group("verb")
            if verb == "route":
                framework = FRAMEWORK_FASTAPI if (is_fastapi and not is_flask) else FRAMEWORK_FLASK
                methods = _parse_methods(statement, ("GET",))
            else:
                if is_fastapi and not is_flask:
                    framework = FRAMEWORK_FASTAPI
                elif is_flask and not is_fastapi:
                    framework = FRAMEWORK_FLASK
                else:
                    # 双方の痕跡が無い/両方ある場合は短縮形の慣習で fastapi 寄せ
                    framework = FRAMEWORK_FASTAPI if is_fastapi else FRAMEWORK_FLASK
                methods = (verb.upper(),)
            # デコレータのオブジェクト名で Blueprint / APIRouter を引き当てる
            prefix = prefix_map.get(match.group("obj").split(".")[-1], "")
            path = match.group("path")
            handler = _find_handler(lines, index)
            routes.append(
                CodeRoute(
                    path=path,
                    methods=methods,
                    framework=framework,
                    handler=handler,
                    kind=_decide_kind(
                        path,
                        prefix,
                        methods,
                        framework,
                        handler=handler,
                        body=_handler_body(lines, index),
                    ),
                    prefix=prefix,
                    evidence=CodeEvidence(file=rel_path, line=index + 1, quote=_quote_at(index)),
                )
            )
            continue

        if "add_url_rule" in line:
            rule = _ADD_URL_RULE_RE.search(statement)
            if rule is None:
                if is_flask or is_fastapi:
                    skipped.append(f"{rel_path}:{index + 1}: dynamic path")
                continue
            path = rule.group("path")
            methods = _parse_methods(statement, ("GET",))
            handler = ""
            rest = rule.group("rest")
            args = [a for a in re.split(r",", rest) if a.strip()]
            if args:
                handler = _clean_identifier(args[0])
            obj = rule.group("obj") or ""
            prefix = prefix_map.get(obj.split(".")[-1], "") if obj else ""
            routes.append(
                CodeRoute(
                    path=path,
                    methods=methods,
                    framework=FRAMEWORK_FLASK,
                    handler=handler,
                    kind=_decide_kind(
                        path, prefix, methods, FRAMEWORK_FLASK, handler=handler
                    ),
                    prefix=prefix,
                    evidence=CodeEvidence(file=rel_path, line=index + 1, quote=_quote_at(index)),
                )
            )
            continue

        if "urlpatterns" in text and ("path(" in line or "re_path(" in line):
            if line.lstrip().startswith("#"):
                continue
            for django in _DJANGO_PATH_RE.finditer(statement):
                raw_path = django.group("path")
                path = _ensure_leading_slash(raw_path)
                methods = ("GET",)
                routes.append(
                    CodeRoute(
                        path=path,
                        methods=methods,
                        framework=FRAMEWORK_DJANGO,
                        handler=_clean_identifier(django.group("view")),
                        kind=_decide_kind(
                            path,
                            "",
                            methods,
                            FRAMEWORK_DJANGO,
                            handler=_clean_identifier(django.group("view")),
                        ),
                        prefix="",
                        evidence=CodeEvidence(
                            file=rel_path, line=index + 1, quote=_quote_at(index)
                        ),
                    )
                )

    return routes, skipped


def _scan_javascript(rel_path: str, raw_text: str) -> list[CodeRoute]:
    """js/ts ソースから express のルート定義を抽出する。

    コメント内の擬似ルートを実ルートとして計上しないよう、走査前に
    ブロックコメント・行コメントを空白化する（行番号は保つ）。
    """
    original = raw_text.splitlines()
    lines = _blank_js_noncode(raw_text).splitlines()
    routes: list[CodeRoute] = []
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        statement = _join_statement(lines, index)
        for match in _EXPRESS_RE.finditer(statement):
            path = match.group("path")
            if not path.startswith("/"):
                continue
            methods = (match.group("verb").upper(),)
            handler = _clean_identifier(match.group("view"))
            routes.append(
                CodeRoute(
                    path=path,
                    methods=methods,
                    framework=FRAMEWORK_EXPRESS,
                    handler=handler,
                    kind=_decide_kind(path, "", methods, FRAMEWORK_EXPRESS, handler=handler),
                    prefix="",
                    evidence=CodeEvidence(
                        file=rel_path,
                        line=index + 1,
                        quote=_quote_of(original[index]) if index < len(original) else "",
                    ),
                )
            )
    return routes


def _is_nextjs_base(root: Path, base_parts: list[str], memo: dict[str, bool]) -> bool:
    """`pages` / `app` を抱えるディレクトリが Next.js プロジェクトかを判定する。

    `pages/` という名前のディレクトリは静的サイトのミラー等でも普通に存在するため、
    `next.config.*` か package.json の "next" 依存が無ければ Next.js とみなさない。
    """
    key = "/".join(base_parts)
    cached = memo.get(key)
    if cached is not None:
        return cached

    candidates: list[Path] = [root.joinpath(*base_parts) if base_parts else root]
    if base_parts:  # src/pages のときはプロジェクトルートも見る
        candidates.append(root.joinpath(*base_parts[:-1]) if len(base_parts) > 1 else root)

    result = False
    for base in candidates:
        if any((base / name).is_file() for name in _NEXT_CONFIG_NAMES):
            result = True
            break
        package_json = base / "package.json"
        if package_json.is_file():
            try:
                if _NEXT_DEP_RE.search(package_json.read_text(encoding="utf-8")):
                    result = True
                    break
            except (OSError, UnicodeDecodeError) as exc:
                logger.debug("package.json 読み取り失敗: %s (%s)", package_json, exc)
    memo[key] = result
    return result


def _nextjs_route(
    root: Path, rel_path: str, text: str | None, memo: dict[str, bool]
) -> CodeRoute | None:
    """Next.js のファイルパス規約からルートを 1 件導出する（該当しなければ None）。"""
    parts = rel_path.split("/")
    anchor = -1
    for index, part in enumerate(parts[:-1]):
        if part in ("pages", "app") and all(p == "src" for p in parts[:index]):
            anchor = index
            break
    if anchor < 0:
        return None
    if not _is_nextjs_base(root, parts[:anchor], memo):
        return None

    kind_dir = parts[anchor]
    tail = parts[anchor + 1 :]
    stem = Path(tail[-1]).stem
    if stem in _NEXT_EXCLUDED_STEMS or stem.startswith("_"):
        return None

    force_api = False
    if kind_dir == "pages":
        segments = tail[:-1] + ([] if stem == "index" else [stem])
        force_api = bool(tail) and tail[0] == "api"
        methods: tuple[str, ...] = ("GET",)
    else:
        if stem not in ("page", "route"):
            return None
        segments = tail[:-1]
        force_api = stem == "route"
        methods = ("GET",)
        if stem == "route" and text:
            found = [m.upper() for m in _NEXT_EXPORTED_METHOD_RE.findall(text)]
            deduped: list[str] = []
            for verb in found:
                if verb not in deduped:
                    deduped.append(verb)
            if deduped:
                methods = tuple(deduped)

    path = "/" + "/".join(segments) if segments else "/"
    return CodeRoute(
        path=path,
        methods=methods,
        framework=FRAMEWORK_NEXTJS,
        handler=stem,
        kind=_decide_kind(path, "", methods, FRAMEWORK_NEXTJS, force_api=force_api),
        prefix="",
        evidence=CodeEvidence(file=rel_path, line=1, quote=f"nextjs file route: {rel_path}"),
    )


# --- 公開 API -------------------------------------------------------------


def scan_source_tree(root: Path, *, max_files: int = 3000) -> CodeBundle:
    """ソースツリーを走査してルート定義を抽出し `CodeBundle` を返す。

    Args:
        root: 走査ルートディレクトリ。
        max_files: 走査するソースファイル数の上限。超過時は打ち切り、
            `skipped` に ``"<root>: max_files reached"`` を積む。

    Returns:
        検出したルート・検出のあったファイル・検出のあった FW・スキップ理由。

        `skipped` にはファイル単位の理由に加え、パスが文字列リテラルでない
        デコレータ（``@bp.get(TENANT_SELECT_PATH)`` 等）を
        ``"<相対パス>:<行>: dynamic path"`` として積む。抽出できないものを
        黙って落とすと、利用者に欠落そのものが伝わらないため。

        `CodeRoute.methods` は **空タプルなら「不明」** を意味する
        （``methods=POST_ONLY`` のように解決できない場合）。GET と断定しない。

    Raises:
        FileNotFoundError: `root` が存在しない場合。
        ValueError: `root` がディレクトリでない場合。
    """
    if not root.exists():
        raise FileNotFoundError(f"走査ルートが存在しない: {root}")
    if not root.is_dir():
        raise ValueError(f"走査ルートがディレクトリでない: {root}")

    root_label = str(root)
    routes: list[CodeRoute] = []
    skipped: list[str] = []
    scanned = 0
    truncated = False
    next_memo: dict[str, bool] = {}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        if truncated:
            break
        for filename in sorted(filenames):
            if Path(filename).suffix not in SOURCE_SUFFIXES:
                continue
            if scanned >= max_files:
                truncated = True
                break
            scanned += 1

            full_path = Path(dirpath) / filename
            rel_path = os.path.relpath(full_path, root).replace(os.sep, "/")

            try:
                size = full_path.stat().st_size
            except OSError as exc:  # 壊れたシンボリックリンク等
                logger.debug("stat 失敗: %s (%s)", rel_path, exc)
                skipped.append(f"{rel_path}: read")
                continue
            if size > MAX_FILE_BYTES:
                skipped.append(f"{rel_path}: size")
                continue

            try:
                text = full_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                skipped.append(f"{rel_path}: decode")
                continue
            except OSError as exc:
                logger.debug("読み取り失敗: %s (%s)", rel_path, exc)
                skipped.append(f"{rel_path}: read")
                continue

            suffix = Path(filename).suffix
            if suffix == ".py":
                py_routes, py_skipped = _scan_python(rel_path, text)
                routes.extend(py_routes)
                skipped.extend(py_skipped)
            else:
                routes.extend(_scan_javascript(rel_path, text))
                next_route = _nextjs_route(root, rel_path, text, next_memo)
                if next_route is not None:
                    routes.append(next_route)

    if truncated:
        skipped.append(f"{root_label}: max_files reached")

    deduped: dict[tuple[str, tuple[str, ...], str, int], CodeRoute] = {}
    for route in routes:
        evidence = route.evidence
        key = (
            route.path,
            route.methods,
            evidence.file if evidence else "",
            evidence.line if evidence else 0,
        )
        deduped.setdefault(key, route)

    ordered = sorted(
        deduped.values(),
        key=lambda r: (
            r.evidence.file if r.evidence else "",
            r.evidence.line if r.evidence else 0,
            r.path,
        ),
    )
    source_files = sorted({r.evidence.file for r in ordered if r.evidence})
    frameworks = sorted({r.framework for r in ordered if r.framework})

    logger.info(
        "code_reader: %d files scanned, %d routes, frameworks=%s",
        scanned,
        len(ordered),
        frameworks,
    )
    return CodeBundle(
        root=root_label,
        routes=tuple(ordered),
        source_files=tuple(source_files),
        frameworks=tuple(frameworks),
        skipped=tuple(skipped),
    )
