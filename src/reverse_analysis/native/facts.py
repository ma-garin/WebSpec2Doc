"""Native 解析の契約: パーサが返す事実（凍結 dataclass）。

位置の規約: line は 1 始まり、col は 1 始まりの UTF-8 バイト列上の列
（`models.LOCATION_UNITS` の "line_column_utf8"）。end は排他的な終端。
解釈（API か・route か）はここに持たない。生の構文情報だけを持つ。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 値の静的な確定度。
RES_STATIC = "static"  # 構文だけで値が決まる（文字列リテラル等）
RES_PARTIAL = "partial"  # 一部だけ決まる（テンプレートの置換あり・文字列連結等）
RES_DYNAMIC = "dynamic"  # 実行しないと決まらない（変数・関数呼び出し等）
RESOLUTIONS = frozenset({RES_STATIC, RES_PARTIAL, RES_DYNAMIC})

# 式の長さの上限（巨大な関数式の引数を丸ごと抱えない）。超えたら truncated=True。
MAX_EXPRESSION_CHARS = 1000


@dataclass(frozen=True, kw_only=True)
class Fact:
    """全ての事実が持つ位置。"""

    file: str
    line: int
    col: int
    end_line: int
    end_col: int


@dataclass(frozen=True, kw_only=True)
class ValueFact(Fact):
    """式 1 つの生の情報。"""

    expression: str  # 原文（MAX_EXPRESSION_CHARS で切る）
    node_type: str  # tree-sitter のノード種別（string / template_string / object / identifier ...）
    resolution: str = RES_DYNAMIC
    string_value: str | None = None  # resolution == static かつ文字列のときだけ
    truncated: bool = False
    properties: tuple[PropertyFact, ...] = ()  # node_type == object のときの浅いキー一覧


@dataclass(frozen=True, kw_only=True)
class PropertyFact(Fact):
    """オブジェクトリテラルの pair（または JSX 属性）。key は引用符を除いた文字列。"""

    key: str
    value: ValueFact | None = None  # 値なし JSX 属性（<Route index />）は None


@dataclass(frozen=True, kw_only=True)
class ImportFact(Fact):
    """静的 import／re-export 元／require()。"""

    specifier: str | None  # 静的に決まらない require(x) は None
    kind: str  # "import" | "require" | "reexport"
    names: tuple[str, ...] = ()  # "default" / "*" / 名前（as の元側）
    resolution: str = RES_STATIC


@dataclass(frozen=True, kw_only=True)
class ExportFact(Fact):
    """export 宣言。"""

    name: str  # "default" / "*" / 名前（as の公開側）
    kind: str  # "named" | "default" | "all"
    source: str | None = None  # export ... from "x" の x


@dataclass(frozen=True, kw_only=True)
class DynamicImportFact(Fact):
    """import(expr)。specifier は resolution == static のときだけ入る。"""

    expression: str
    specifier: str | None = None
    resolution: str = RES_DYNAMIC


@dataclass(frozen=True, kw_only=True)
class CallFact(Fact):
    """呼び出し式。callee は原文（"axios.get" / "fetch" / "$http.post"）。import() は含まない。"""

    callee: str
    args: tuple[ValueFact, ...] = ()
    callee_truncated: bool = False


@dataclass(frozen=True, kw_only=True)
class RouteCandidateFact(Fact):
    """route 宣言の候補（生の構文。意味づけは routes.py）。

    kind "jsx"    : path / index 属性を持つ JSX 要素。tag=要素名、properties=属性
    kind "object" : `path` キーを持つオブジェクトリテラル。tag=""、properties=浅いキー一覧
    parent: routes 配列内の、構文上の親候補の index（無ければ None）
    container: 最も内側の包む呼び出しの callee 原文（createBrowserRouter 等。無ければ ""）
    """

    kind: str
    tag: str = ""
    properties: tuple[PropertyFact, ...] = ()
    parent: int | None = None
    container: str = ""


@dataclass(frozen=True, kw_only=True)
class SourceMapRef(Fact):
    """`//# sourceMappingURL=` コメント。inline は data: URL。"""

    url: str
    inline: bool = False


@dataclass(frozen=True, kw_only=True)
class Limitation:
    """解析できなかった・保証できない箇所。0 件と未対応を区別するための記録。"""

    code: str  # "syntax_error" | "parser_failure" | "unsupported_file_type" ...
    message: str
    file: str = ""
    line: int | None = None
    col: int | None = None


@dataclass(frozen=True, kw_only=True)
class ParsedFile:
    path: str
    sha256: str
    imports: tuple[ImportFact, ...] = ()
    exports: tuple[ExportFact, ...] = ()
    dynamic_imports: tuple[DynamicImportFact, ...] = ()
    calls: tuple[CallFact, ...] = ()
    routes: tuple[RouteCandidateFact, ...] = ()
    source_map_ref: SourceMapRef | None = None  # 複数あれば最後（仕様どおり）
    limitations: tuple[Limitation, ...] = field(default_factory=tuple)
    parser: str = ""  # 例 "tree-sitter-javascript/0.25.0"
    complete: bool = True  # False = 構文エラー等で部分結果
