#!/usr/bin/env python3
"""note 貼り付け用テキストを生成する。

note のエディタは Markdown の表組みに対応していないため、
コードブロックの外にある表だけを箇条書きへ変換する。
プロンプト本体（コードブロック内）はコピペ用なので一切変更しない。
"""
import re
import sys
from pathlib import Path

SRC = Path("docs/prompt-library/url-to-testdesign-prompts.md")
OUT = Path(sys.argv[1])


def cells(line: str) -> list[str]:
    return [c.strip().replace("\\|", "|") for c in line.strip().strip("|").split("|")]


_INDEX_HEADERS = {"#", "順", "ルール#", "ケース#", "no", "No"}


def table_to_list(head: list[str], rows: list[list[str]]) -> list[str]:
    """先頭列が通し番号の表は、その列を落として2列目を見出しにする。"""
    if len(head) > 2 and (
        head[0] in _INDEX_HEADERS
        or all(r and r[0].isdigit() for r in rows)
    ):
        head = head[1:]
        rows = [r[1:] for r in rows]
    out: list[str] = []
    for row in rows:
        row = row + [""] * (len(head) - len(row))
        # 見出しに使うセルは、入れ子の ** で強調が壊れないよう先に落とす
        first = (row[0] or "（なし）").replace("**", "")
        if len(head) == 2:
            out.append(f"・**{first}** → {row[1]}")
            continue
        rest = "／".join(
            f"{h}: {v}" for h, v in zip(head[1:], row[1:], strict=False) if v and v != "-"
        )
        out.append(f"・**{first}**")
        if rest:
            out.append(f"　{rest}")
    return out


def convert(md: str) -> str:
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    in_code = False
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            in_code = not in_code
            out.append(line)
            i += 1
            continue
        if (
            not in_code
            and line.startswith("|")
            and i + 1 < len(lines)
            and re.match(r"^\|[\s:|-]+\|$", lines[i + 1])
        ):
            head = cells(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            out.extend(table_to_list(head, rows))
            out.append("")
            continue
        out.append(line)
        i += 1
    text = "\n".join(out)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text


HEADER = """※ この記事は社内メンバー向けの限定公開です。外部への転載はしないでください。

"""

OUT.write_text(HEADER + convert(SRC.read_text(encoding="utf-8")), encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
