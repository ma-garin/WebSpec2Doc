"""要件定義書・基本設計書（Markdown）を、対検査の単位に分ける。

単位は 3 種類: item（箇条書き 1 項目。字下げした続きの行を含む）、
para（見出しの下の地の文のまとまり）、row（表の 1 行）。
行番号は 1 始まりで、評価セットの行範囲と同じ数え方。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

ID_RE = re.compile(r"\bREQ-\d{3,}\b")
_HEAD = re.compile(r"^(#{1,6})\s+(.*)$")
_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])\s+")
_SEP = re.compile(r"^\|?\s*:?-{2,}")


@dataclass(frozen=True)
class Unit:
    kind: str                      # item / para / row
    start: int                     # 1 始まり
    end: int
    text: str
    heading: tuple[str, ...]       # 上位の見出しの並び
    ids: tuple[str, ...] = ()
    headers: tuple[str, ...] = ()  # row のときの表の見出し
    cells: tuple[str, ...] = ()    # row のときのセル
    table: int = -1                # 同じ表の行は同じ番号
    extra: dict = field(default_factory=dict, compare=False, hash=False)


def _cells(line: str) -> tuple[str, ...]:
    return tuple(c.strip() for c in line.strip().strip("|").split("|"))


def _unit(kind, start, end, lines, heading, **kw) -> Unit:
    text = "\n".join(lines).strip()
    return Unit(kind, start, end, text, heading, tuple(dict.fromkeys(ID_RE.findall(text))), **kw)


def segment(markdown: str) -> list[Unit]:
    """Markdown を単位の列にする。見出し行と空行は単位にしない。"""
    units: list[Unit] = []
    heads: list[str] = []
    buf: list[str] = []
    buf_start = 0
    buf_kind = ""
    headers: tuple[str, ...] = ()
    table_no = -1
    in_table = False

    def flush(end: int) -> None:
        nonlocal buf, buf_kind
        if buf:
            units.append(_unit(buf_kind, buf_start, end, buf, tuple(heads)))
        buf, buf_kind = [], ""

    lines = markdown.splitlines()
    for no, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        m = _HEAD.match(line)
        if m:
            flush(no - 1)
            in_table = False
            level = len(m.group(1))
            heads[:] = heads[: level - 1] + [m.group(2).strip()]
            continue
        if not line.strip():
            flush(no - 1)
            in_table = False
            continue
        if line.lstrip().startswith("|"):
            flush(no - 1)
            if not in_table:
                in_table, table_no, headers = True, table_no + 1, _cells(line)
                continue
            if _SEP.match(line.strip()):
                continue
            units.append(_unit("row", no, no, [line], tuple(heads),
                               headers=headers, cells=_cells(line), table=table_no))
            continue
        in_table = False
        if _ITEM.match(line):
            flush(no - 1)
            buf, buf_start, buf_kind = [line], no, "item"
        elif line[:1] in (" ", "\t") and buf_kind == "item":
            buf.append(line)
        elif buf_kind == "para":
            buf.append(line)
        else:
            flush(no - 1)
            buf, buf_start, buf_kind = [line], no, "para"
    flush(len(lines))
    return units


def requirement_units(units: list[Unit]) -> list[Unit]:
    """要件定義書のうち、機能要件・非機能要件の章にある item と para。"""
    keys = ("機能要件", "非機能要件")
    return [u for u in units if u.kind in ("item", "para")
            and any(k in h for h in u.heading for k in keys)]
