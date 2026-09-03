#!/usr/bin/env python3
"""docs/prompt-library/url-to-testdesign-prompts.md → 配布用 HTML（Artifact）"""
import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from figures import FIGURES  # noqa: E402

SRC = Path("docs/prompt-library/url-to-testdesign-prompts.md")
OUT = Path(sys.argv[1])
FIG_RE = re.compile(r"^\[\[FIG:([a-z]+)\|(.+?)\]\]$")
BULLET_RE = r"^\s*(?:[-*] |・)"

def inline(text: str) -> str:
    """先に全体をエスケープし、そのうえで許可した記法だけを復元する。"""
    out = html.escape(text)
    out = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", lambda m: f"<strong>{m.group(1)}</strong>", out)
    out = out.replace("\\|", "|")
    return out


def slug(text: str) -> str:
    m = re.match(r"^(P\d+)\.", text)
    if m:
        return m.group(1).lower()
    m = re.match(r"^(\d+)\.", text)
    if m:
        return f"sec{m.group(1)}"
    return "sec-" + re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:24]


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def render(md: str) -> tuple[str, list[tuple[str, str, str]]]:
    lines = md.split("\n")
    out: list[str] = []
    toc: list[tuple[str, str, str]] = []
    i = 0
    code_id = 0
    while i < len(lines):
        line = lines[i]

        fig = FIG_RE.match(line.strip())
        if fig:
            key, caption = fig.group(1), fig.group(2)
            svg = FIGURES.get(key)
            if svg is None:
                raise KeyError(f"未定義の図版キー: {key}")
            out.append(
                f'<figure class="dia"><div class="dia-frame">{svg}</div>'
                f"<figcaption>{inline(caption)}</figcaption></figure>"
            )
            i += 1
            continue

        if line.startswith("```"):
            lang = line[3:].strip()
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1
            code_id += 1
            label = "プロンプト" if lang == "text" else (lang or "コード")
            out.append(
                f'<figure class="block" data-lang="{html.escape(lang)}">'
                f'<figcaption><span class="block-kind">{html.escape(label)}</span>'
                f'<button class="copy" type="button" data-target="c{code_id}">コピー</button>'
                f"</figcaption>"
                f'<pre id="c{code_id}"><code>{html.escape(chr(10).join(body))}</code></pre></figure>'
            )
            continue

        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            head = split_row(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in head)
            tb = "".join(
                "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows
            )
            out.append(
                f'<div class="scroller"><table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>'
            )
            continue

        if line.startswith("### "):
            t = line[4:].strip()
            sid = slug(t)
            m = re.match(r"^(P\d+)\.\s*(.+)$", t)
            if m:
                toc.append(("h3", sid, t))
            if m:
                out.append(
                    f'<h3 id="{sid}"><span class="pid">{html.escape(m.group(1))}</span>'
                    f"<span>{inline(m.group(2))}</span></h3>"
                )
            else:
                out.append(f'<h3 id="{sid}">{inline(t)}</h3>')
            i += 1
            continue

        if line.startswith("## "):
            t = line[3:].strip()
            sid = slug(t)
            toc.append(("h2", sid, t))
            out.append(f'<h2 id="{sid}">{inline(t)}</h2>')
            i += 1
            continue

        if line.startswith("# "):
            i += 1
            continue

        if line.startswith("> "):
            body = []
            while i < len(lines) and lines[i].startswith("> "):
                body.append(lines[i][2:])
                i += 1
            out.append(f'<blockquote><p>{inline(" ".join(body))}</p></blockquote>')
            continue

        if line.strip() == "---":
            out.append('<hr aria-hidden="true">')
            i += 1
            continue

        if re.match(BULLET_RE, line):
            items = []
            while i < len(lines) and re.match(BULLET_RE, lines[i]):
                items.append(inline(re.sub(BULLET_RE, "", lines[i])))
                i += 1
            out.append("<ul>" + "".join(f"<li>{it}</li>" for it in items) + "</ul>")
            continue

        if re.match(r"^\d+\. ", line):
            items = []
            while i < len(lines) and re.match(r"^\d+\. ", lines[i]):
                items.append(inline(re.sub(r"^\d+\.\s*", "", lines[i])))
                i += 1
            out.append("<ol>" + "".join(f"<li>{it}</li>" for it in items) + "</ol>")
            continue

        if line.strip():
            para = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#|\||```|>|\s*[-*] |・|\d+\. |---$|\[\[FIG:)", lines[i]
            ):
                para.append(lines[i])
                i += 1
            out.append(f"<p>{inline(' '.join(para))}</p>")
            continue

        i += 1

    return "\n".join(out), toc


def main() -> None:
    body, toc = render(SRC.read_text(encoding="utf-8"))
    nav = []
    for level, sid, text in toc:
        if level == "h2":
            nav.append(f'<a class="nav-sec" href="#{sid}">{inline(text)}</a>')
        else:
            m = re.match(r"^(P\d+)\.\s*(.+)$", text)
            if m:
                nav.append(
                    f'<a class="nav-p" href="#{sid}"><b>{html.escape(m.group(1))}</b>'
                    f"<span>{inline(m.group(2))}</span></a>"
                )

    OUT.write_text(
        TEMPLATE.replace("{{NAV}}", "\n".join(nav)).replace("{{BODY}}", body),
        encoding="utf-8",
    )
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


TEMPLATE = (Path(__file__).resolve().parent / "article_template.html").read_text(encoding="utf-8")

main()
