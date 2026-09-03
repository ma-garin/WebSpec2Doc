#!/usr/bin/env python3
"""note 貼り付け用テキストを生成する。

note のエディタは Markdown の表組みに対応していないため、
コードブロックの外にある表だけを箇条書きへ変換する。
プロンプト本体（コードブロック内）はコピペ用なので一切変更しない。
"""
import re
import sys
from pathlib import Path

# 図版キー → 書き出した PNG のファイル名（記事中の登場順）
FIGURE_FILES = {
    "attrs": "01_属性からテスト条件",
    "pipeline": "02_パイプライン全体",
    "coverage": "03_確認できる範囲",
    "guard": "04_データと指示の分離",
    "promptmap": "05_プロンプトの依存関係",
    "handson": "06_30分ハンズオン",
    "bvaline": "07_境界値の数直線",
    "dt": "08_デシジョンテーブル",
    "pairwise": "09_全数とペアワイズ",
    "switch": "10_0switchと1switch",
    "technique": "11_技法の選択",
    "ladder": "12_画面種別の判定",
}

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
        if not in_code:
            fig = re.match(r"^\[\[FIG:([a-z]+)\|(.+?)\]\]$", line.strip())
            if fig:
                # note は画像を個別にアップロードするため、
                # 挿入位置と対応するファイル名を本文に残す
                key, caption = fig.group(1), fig.group(2)
                name = FIGURE_FILES.get(key, key)
                out.append(f"［ここに画像を挿入: figures/{name}.png］")
                out.append(f"図: {caption}")
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

---
【note へ貼るときの手順】
1. 本文をこのままコピーして note の本文へ貼る
2. 「［ここに画像を挿入: figures/XX_….png］」の行を、対応する画像に差し替える
   （画像は figures/ フォルダに 01〜12 の連番で入っています）
3. コードブロック（プロンプト本体）は note の「コード」ブロックに入れると崩れません
4. 見出しの「## 」「### 」は note の見出し設定に置き換えてください
---

"""

OUT.write_text(HEADER + convert(SRC.read_text(encoding="utf-8")), encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
