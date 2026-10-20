"""Source map v3 の読み取りと Base64 VLQ の復号（公開仕様 https://tc39.es/ecma426/ のみに基づく自前実装）。

- `//# sourceMappingURL=` は外部ファイル（入力ディレクトリの中に限る）と data URI（base64／百分率符号化）を読む。
  http(s) は取得しない（製品境界）。読めない・壊れている・範囲外のものは SourceMapFinding と limitation にし、解析は続ける。
- 位置は生成側・元側とも 行 1 始まり・列 0 始まり（api_resolve・facts と同じ）。仕様の 0 始まりの行は変換して返す。
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from reverse_analysis.models import Diagnostic

MAX_MAP_BYTES = 64 * 1024 * 1024
_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_B64_INDEX = {c: i for i, c in enumerate(_B64)}
_URL_RE = re.compile(r"[#@]\s*sourceMappingURL=([^\s'\"]+)")


class SourceMapError(ValueError):
    """map を解釈できない。code は SourceMapFinding.finding に使う。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- VLQ

def vlq_decode(text: str) -> list[int]:
    """Base64 VLQ 列を整数列へ。各桁の下位 5 bit が値、bit 5 が継続、先頭桁の最下位 bit が符号。"""
    out: list[int] = []
    value = shift = 0
    for ch in text:
        digit = _B64_INDEX.get(ch)
        if digit is None:
            raise SourceMapError("map_parse_failed", f"VLQ に使えない文字 {ch!r}")
        value |= (digit & 31) << shift
        if digit & 32:
            shift += 5
            if shift > 30:  # 32 bit を超える値は仕様外
                raise SourceMapError("map_parse_failed", "VLQ の値が大きすぎます")
            continue
        out.append(-(value >> 1) if value & 1 else value >> 1)
        value = shift = 0
    if shift:
        raise SourceMapError("map_parse_failed", "VLQ が途中で終わっています")
    return out


def vlq_encode(n: int) -> str:
    """vlq_decode の逆（テスト用）。"""
    v = ((-n) << 1) | 1 if n < 0 else n << 1
    out = ""
    while True:
        digit, v = v & 31, v >> 5
        out += _B64[digit | (32 if v else 0)]
        if not v:
            return out


# ---------------------------------------------------------------- map 本体

@dataclass(frozen=True)
class Segment:
    column: int                 # 生成側の列（0 始まり）
    source: int | None          # sources の添字。生成側だけの断片は None
    line: int | None            # 元側の行（1 始まり）
    col: int | None             # 元側の列（0 始まり）
    name: int | None = None


@dataclass(frozen=True)
class OriginalPosition:
    source: str
    line: int
    column: int
    name: str | None = None


@dataclass(frozen=True)
class SourceMap:
    sources: tuple[str, ...]
    names: tuple[str, ...]
    lines: tuple[tuple[Segment, ...], ...]      # 生成側の行ごと（0 始まりの添字 = 行 - 1）
    source_root: str = ""
    sources_content: tuple[str | None, ...] = ()
    file: str | None = None
    _cols: tuple[tuple[int, ...], ...] = field(default=(), repr=False, compare=False)

    def original_source(self, index: int) -> str:
        name = self.sources[index]
        root = self.source_root
        return f"{root.rstrip('/')}/{name}" if root and not re.match(r"^(?:[a-z][a-z0-9+.-]*:|/)", name, re.I) else name

    def lookup(self, line: int, column: int) -> OriginalPosition | None:
        """生成位置（行 1 始まり・列 0 始まり）に対応する元位置。無ければ None（推測しない）。"""
        if not 1 <= line <= len(self.lines):
            return None
        segs = self.lines[line - 1]
        i = bisect_right(self._cols[line - 1], column) - 1
        if i < 0 or segs[i].source is None or segs[i].line is None or segs[i].col is None:
            return None
        s = segs[i]
        if s.source >= len(self.sources):
            return None
        name = self.names[s.name] if s.name is not None and s.name < len(self.names) else None
        return OriginalPosition(self.original_source(s.source), s.line, s.col, name)


def decode_mappings(mappings: str, n_sources: int = 0, n_names: int = 0) -> tuple[tuple[Segment, ...], ...]:
    lines: list[tuple[Segment, ...]] = []
    src = oline = ocol = name = 0
    for raw_line in mappings.split(";"):
        gcol = 0                                   # 生成側の列は行ごとに 0 へ戻る
        segs: list[Segment] = []
        for raw in raw_line.split(","):
            if not raw:
                continue
            f = vlq_decode(raw)
            if len(f) not in (1, 4, 5):
                raise SourceMapError("map_parse_failed", f"断片のフィールド数が不正です（{len(f)}）")
            gcol += f[0]
            if gcol < 0:
                raise SourceMapError("map_parse_failed", "生成側の列が負です")
            if len(f) == 1:
                segs.append(Segment(gcol, None, None, None))
                continue
            src, oline, ocol = src + f[1], oline + f[2], ocol + f[3]
            if len(f) == 5:
                name += f[4]
            if not (0 <= src < n_sources) or oline < 0 or ocol < 0 or (len(f) == 5 and not 0 <= name < n_names):
                raise SourceMapError("map_parse_failed", "断片が sources／names／位置の範囲外を指しています")
            segs.append(Segment(gcol, src, oline + 1, ocol, name if len(f) == 5 else None))
        lines.append(tuple(segs))
    return tuple(lines)


def parse_source_map(text: str) -> SourceMap:
    """v3 map の JSON を解釈する。不正は SourceMapError。"""
    if len(text) > MAX_MAP_BYTES:
        raise SourceMapError("map_parse_failed", "map が大きすぎます")
    text = text.lstrip("﻿")
    if text.startswith(")]}'"):  # XSSI 対策の接頭辞（仕様）
        text = text.split("\n", 1)[1] if "\n" in text else ""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise SourceMapError("map_parse_failed", f"JSON として読めません: {exc}") from exc
    if not isinstance(data, dict):
        raise SourceMapError("map_parse_failed", "map の最上位がオブジェクトではありません")
    if data.get("version") != 3:
        raise SourceMapError("map_unsupported_version", f"version={data.get('version')!r}（v3 のみ対応）")
    if "sections" in data:
        raise SourceMapError("map_unsupported_index_map", "index map（sections）には未対応です")
    sources, names, mappings = data.get("sources"), data.get("names", []), data.get("mappings")
    if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
        raise SourceMapError("map_parse_failed", "sources が文字列の配列ではありません")
    if not isinstance(names, list) or not all(isinstance(s, str) for s in names) or not isinstance(mappings, str):
        raise SourceMapError("map_parse_failed", "names または mappings の型が不正です")
    content = data.get("sourcesContent") or []
    lines = decode_mappings(mappings, len(sources), len(names))
    return SourceMap(
        sources=tuple(sources), names=tuple(names), lines=lines,
        source_root=data["sourceRoot"] if isinstance(data.get("sourceRoot"), str) else "",
        sources_content=tuple(c if isinstance(c, str) else None for c in content) if isinstance(content, list) else (),
        file=data["file"] if isinstance(data.get("file"), str) else None,
        _cols=tuple(tuple(s.column for s in segs) for segs in lines))


# ---------------------------------------------------------------- 参照の解決

@dataclass(frozen=True)
class SourceMapFinding:
    """map を使えなかった理由。finding は map_not-found / map_parse_failed / map_remote_not_fetched / ほか。"""

    path: str            # map を宣言した JS（入力ディレクトリからの相対）
    finding: str
    detail: str
    declared: str | None = None


@dataclass(frozen=True)
class SourceMapResult:
    maps: dict[str, SourceMap]
    findings: tuple[SourceMapFinding, ...]
    diagnostics: tuple[Diagnostic, ...]
    limitations: tuple[str, ...]


def find_source_mapping_url(source: str) -> str | None:
    """末尾側から最後の sourceMappingURL コメントを探す。"""
    found = None
    for line in source.splitlines()[-20:]:
        m = _URL_RE.search(line)
        if m and (line.lstrip().startswith(("//", "/*"))):
            found = m.group(1).rstrip("*/") if m.group(1).endswith("*/") else m.group(1)
    return found


def _read_data_uri(uri: str) -> str:
    head, sep, body = uri.partition(",")
    if not sep:
        raise SourceMapError("map_parse_failed", "data URI にカンマがありません")
    try:
        if head.endswith(";base64"):
            return base64.b64decode(unquote(body) + "=" * (-len(unquote(body)) % 4), validate=False).decode("utf-8")
        return unquote(body)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise SourceMapError("map_parse_failed", f"data URI を復号できません: {exc}") from exc


def load_source_map(declared: str, js_rel_path: str, js_root: Path) -> SourceMap:
    """宣言された URL から map を読む。入力ディレクトリの外・http(s)・読めないものは SourceMapError。"""
    if declared.startswith("data:"):
        return parse_source_map(_read_data_uri(declared))
    if re.match(r"^(?:https?:)?//", declared, re.I):
        raise SourceMapError("map_remote_not_fetched", "外部 URL の map は取得しません（入力ディレクトリに置いてください）")
    rel = unquote(declared.split("#", 1)[0].split("?", 1)[0])
    root = js_root.resolve()
    target = (root / Path(js_rel_path).parent / rel).resolve()
    if rel.startswith("/") or not target.is_relative_to(root):
        raise SourceMapError("map_path_rejected", "入力ディレクトリの外を指す map は読みません")
    if not target.is_file() or target.is_symlink():
        raise SourceMapError("map_not-found", "宣言された map が入力内に見つかりません")
    try:
        if target.stat().st_size > MAX_MAP_BYTES:
            raise SourceMapError("map_parse_failed", "map が大きすぎます")
        return parse_source_map(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise SourceMapError("map_parse_failed", f"map を読めません: {exc}") from exc


_TEXT = {
    "map_not-found": "宣言された source map が入力内に見つかりませんでした",
    "map_parse_failed": "source map を読めませんでした",
    "map_unsupported_version": "対応していない版の source map です",
    "map_unsupported_index_map": "index map 形式の source map には未対応です",
    "map_remote_not_fetched": "外部 URL の source map は取得しません",
    "map_path_rejected": "入力ディレクトリの外を指す source map は読みません",
}


def analyze_source_maps(parsed_files: Iterable, js_input: Path) -> SourceMapResult:
    """各 ParsedFile の source_map_ref を解決する。失敗は finding・診断・limitation にして継続する。"""
    maps: dict[str, SourceMap] = {}
    findings: list[SourceMapFinding] = []
    for pf in parsed_files:
        ref = getattr(pf, "source_map_ref", None)
        ref = getattr(ref, "url", ref)  # SourceMapRef（facts）または URL 文字列
        if not ref:
            continue
        try:
            maps[pf.path] = load_source_map(ref, pf.path, Path(js_input))
        except SourceMapError as exc:
            shown = "data URI" if ref.startswith("data:") else ref[:120]
            findings.append(SourceMapFinding(pf.path, exc.code, str(exc), shown))
    diags = tuple(Diagnostic(
        f"native_source_{f.finding.replace('-', '_')}", "warning", "static_normalize",
        f"{_TEXT.get(f.finding, 'source map を解決できませんでした')}（{f.path}・{f.declared or '不明'}）。"
        f"{f.detail}。元ソースは不明として扱います。",
        "source map を JS と同じ版で入力ディレクトリに置き、再実行してください。") for f in findings)
    lims = tuple(f"native_source_map:{f.finding}:{f.path}" for f in findings)
    return SourceMapResult(maps, tuple(findings), diags, lims)
