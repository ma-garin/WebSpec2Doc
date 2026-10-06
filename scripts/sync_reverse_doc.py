#!/usr/bin/env python3
"""reverse_doc の純粋モジュールを web/vendor/reverse_doc に写し直す（System 06 用）。

使い方: venv/bin/python scripts/sync_reverse_doc.py <reverse_doc のリポジトリ> [git の ref。既定 origin/main]
写すのは docs_ingest/readers・ambiguity・confidence・conflicts・questions・docdiff と、それらが import するモジュール。
DB（docs_ingest/store）と Web 画面は写さない。import は web.vendor.reverse_doc に書き換える。
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOTS = ["models.py", "docs_ingest/readers.py", "ambiguity.py", "confidence.py",
         "conflicts.py", "questions.py", "docdiff.py"]
SKIP = {"docs_ingest/__init__.py", "docs_ingest/store.py"}
VENDOR = pathlib.Path(__file__).resolve().parents[1] / "web" / "vendor" / "reverse_doc"


def _git(repo: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def _deps(src: str, base: pathlib.PurePosixPath) -> list[str]:
    mods = re.findall(r"^\s*from (reverse_doc(?:\.[\w.]+)?|\.[\w.]*) import", src, re.M)
    mods += re.findall(r"^\s*import (reverse_doc\.[\w.]+)", src, re.M)
    out = []
    for m in mods:
        if m.startswith("reverse_doc"):
            mod = m[len("reverse_doc"):].lstrip(".")
            if mod:
                out.append(mod.replace(".", "/"))
        elif m.strip("."):
            out.append(str(base / m.lstrip(".").replace(".", "/")))
    return out


def main() -> int:
    repo, ref = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "origin/main")
    sha = _git(repo, "rev-parse", ref).stdout.strip()
    todo, done = list(ROOTS), []
    while todo:
        f = todo.pop(0)
        if f in done or f in SKIP:
            continue
        r = _git(repo, "show", f"{sha}:src/reverse_doc/{f}")
        if r.returncode:
            print(f"見つからない: {f}")
            continue
        done.append(f)
        for p in _deps(r.stdout, pathlib.PurePosixPath(f).parent):
            for cand in (p + ".py", p + "/__init__.py"):
                if _git(repo, "cat-file", "-e", f"{sha}:src/reverse_doc/{cand}").returncode == 0:
                    todo.append(cand)
                    break
        src = re.sub(r"^(\s*)(from|import) reverse_doc([. ])", r"\1\2 web.vendor.reverse_doc\3", r.stdout, flags=re.M)
        out = VENDOR / f
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(src, encoding="utf-8")
    for d in (VENDOR.parent, VENDOR / "docs_ingest"):
        (d / "__init__.py").touch()
    (VENDOR / "__init__.py").write_text(
        f'"""reverse_doc の純粋モジュールの写し（出所: ma-garin/reverse_doc {sha}）。直接編集しない。"""\n', encoding="utf-8")
    print(f"{sha} から {len(done)} ファイルを写した: {', '.join(done)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
