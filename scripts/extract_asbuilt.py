#!/usr/bin/env python3
"""as-built 設計情報をソースコードから機械抽出する。

SDLC 文書（docs/sdlc/）のうち、コードに正解が存在する部分の入力データを生成する。
手書きすると 121 本のエンドポイントを必ず取りこぼすため、AST とパッケージメタデータ
から機械的に起こす。出力は docs/sdlc/_asbuilt/ 配下。

使い方:
    venv/bin/python scripts/extract_asbuilt.py

出力:
    _asbuilt/routes.json      Flask エンドポイント一覧（blueprint / method / path / 関数）
    _asbuilt/modules.json     src・web のモジュール / クラス / 公開関数
    _asbuilt/schema.sql       SQLite 物理スキーマ（instance/*.db の .schema）
    _asbuilt/licenses.json    依存 OSS のライセンス一覧
    _asbuilt/templates.json   Jinja2 テンプレートと include/extends 関係
"""

from __future__ import annotations

import ast
import json
import re
import sqlite3
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "sdlc" / "_asbuilt"

# Flask の HTTP メソッドショートカット。route デコレータは methods= から拾う。
_METHOD_SHORTCUTS = {"get", "post", "put", "patch", "delete"}
_SOURCE_PACKAGES = ("src", "web")
_SKIP_DIR_PARTS = {"__pycache__", "venv", ".venv", ".runtime", "node_modules", ".git"}


def _iter_python_files(base: Path):
    """base 配下の .py を、仮想環境やキャッシュを除いて列挙する。"""
    for path in sorted(base.rglob("*.py")):
        if _SKIP_DIR_PARTS & set(path.parts):
            continue
        yield path


def _decorator_route_info(node: ast.AST) -> tuple[list[str], str] | None:
    """デコレータ 1 個から (HTTPメソッド群, パス) を取り出す。route でなければ None。"""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None

    attr = node.func.attr
    path = None
    if node.args and isinstance(node.args[0], ast.Constant):
        path = node.args[0].value
    if not isinstance(path, str):
        return None

    if attr in _METHOD_SHORTCUTS:
        return [attr.upper()], path
    if attr != "route":
        return None

    methods = ["GET"]
    for kw in node.keywords:
        if kw.arg == "methods" and isinstance(kw.value, ast.List | ast.Tuple):
            found = [e.value for e in kw.value.elts if isinstance(e, ast.Constant)]
            if found:
                methods = [str(m).upper() for m in found]
    return methods, path


def _blueprint_name(tree: ast.Module) -> str:
    """モジュール先頭の Blueprint("name", ...) から blueprint 名を取る。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name != "Blueprint":
            continue
        if node.value.args and isinstance(node.value.args[0], ast.Constant):
            return str(node.value.args[0].value)
    return ""


def _first_docline(node: ast.AST) -> str:
    """docstring の 1 行目。文書の「概要」列にそのまま載せる。"""
    doc = ast.get_docstring(node) or ""
    return doc.strip().splitlines()[0].strip() if doc.strip() else ""


def _route_docstrings() -> dict[str, dict[str, Any]]:
    """endpoint 名 -> {summary, module, module_summary, line} を AST から作る。

    url_map はパスとメソッドの正解を持つが docstring を持たない。説明文だけ AST で補う。
    """
    index: dict[str, dict[str, Any]] = {}
    for path in _iter_python_files(ROOT / "web" / "routes"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            print(f"WARN: parse failed {path}: {exc}", file=sys.stderr)
            continue

        blueprint = _blueprint_name(tree)
        module_doc = _first_docline(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not any(_decorator_route_info(d) for d in node.decorator_list):
                continue
            key = f"{blueprint}.{node.name}" if blueprint else node.name
            index[key] = {
                "module": str(path.relative_to(ROOT)),
                "module_summary": module_doc,
                "summary": _first_docline(node),
                "line": node.lineno,
            }
    return index


def extract_routes() -> list[dict[str, Any]]:
    """Flask の url_map から全エンドポイントを抽出する。

    Blueprint の url_prefix（/api/v1・/api/admin・/auth/oidc）はデコレータの引数に
    現れないため、AST だけではパスが不正確になる。実際にアプリを組み立てて url_map を
    引くのが唯一の正解。docstring だけ AST 側から合流させる。
    """
    import os

    # 起動時にブラウザを開かせない・ローカル対象を許可する（抽出目的の実行のため）
    os.environ.setdefault("FLASK_TESTING", "1")
    os.environ.setdefault("WEBSPEC2DOC_ALLOW_LOCAL", "1")

    sys.path.insert(0, str(ROOT))
    from web import create_app  # 環境変数を設定してから import する

    app = create_app()
    docs = _route_docstrings()

    routes: list[dict[str, Any]] = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        methods = sorted((rule.methods or set()) - {"HEAD", "OPTIONS"})
        blueprint = rule.endpoint.split(".")[0] if "." in rule.endpoint else ""
        meta = docs.get(rule.endpoint, {})
        routes.append(
            {
                "module": meta.get("module", ""),
                "blueprint": blueprint,
                "module_summary": meta.get("module_summary", ""),
                "endpoint": rule.endpoint,
                "function": rule.endpoint.split(".")[-1],
                "methods": methods or ["GET"],
                "path": str(rule.rule),
                "summary": meta.get("summary", ""),
                "line": meta.get("line", 0),
            }
        )
    routes.sort(key=lambda r: (r["blueprint"], r["path"], r["methods"][0]))
    return routes


def extract_modules() -> list[dict[str, Any]]:
    """src・web のモジュール構成、クラス、公開関数を抽出する（詳細設計の入力）。"""
    modules: list[dict[str, Any]] = []

    for package in _SOURCE_PACKAGES:
        base = ROOT / package
        if not base.is_dir():
            continue
        for path in _iter_python_files(base):
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError) as exc:
                print(f"WARN: parse failed {path}: {exc}", file=sys.stderr)
                continue

            classes = []
            functions = []
            for node in tree.body:  # トップレベルのみ。ネストは詳細設計の粒度を超える
                if isinstance(node, ast.ClassDef):
                    methods = [
                        {"name": m.name, "summary": _first_docline(m), "line": m.lineno}
                        for m in node.body
                        if isinstance(m, ast.FunctionDef | ast.AsyncFunctionDef)
                        and not m.name.startswith("_")
                    ]
                    classes.append(
                        {
                            "name": node.name,
                            "summary": _first_docline(node),
                            "bases": [ast.unparse(b) for b in node.bases],
                            "methods": methods,
                            "line": node.lineno,
                        }
                    )
                elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    if node.name.startswith("_"):
                        continue
                    functions.append(
                        {
                            "name": node.name,
                            "summary": _first_docline(node),
                            "signature": _signature(node),
                            "line": node.lineno,
                        }
                    )

            # トップレベル名（web / src）だけ集めても依存構造は見えない。
            # web.services / web.routes / src.crawler のようなサブパッケージ単位で取る。
            deps: set[str] = set()
            for node in ast.walk(tree):
                target = None
                if isinstance(node, ast.ImportFrom) and node.module:
                    target = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in _SOURCE_PACKAGES:
                            deps.add(_subpackage(alias.name))
                    continue
                if target and target.split(".")[0] in _SOURCE_PACKAGES:
                    deps.add(_subpackage(target))

            own = _subpackage(str(path.relative_to(ROOT)).replace("/", ".").removesuffix(".py"))
            deps.discard(own)  # 自分自身への参照は依存として数えない

            modules.append(
                {
                    "path": str(path.relative_to(ROOT)),
                    "package": package,
                    "subpackage": own,
                    "summary": _first_docline(tree),
                    "loc": source.count("\n") + 1,
                    "classes": classes,
                    "functions": functions,
                    "internal_deps": sorted(deps),
                }
            )
    modules.sort(key=lambda m: m["path"])
    return modules


def _subpackage(dotted: str) -> str:
    """`web.services.auth_store` -> `web.services`。2 階層目までを依存の単位にする。"""
    parts = dotted.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else parts[0]


# WS2D-BD-001 のレイヤ構造。番号が小さいほど上位（呼ぶ側）。
# 上位 → 下位の依存は正常で、下位 → 上位が逆流＝循環の原因になる。
_LAYER_RANK = {
    "web.routes": 1,
    "web.services": 3,
}
_WEB_SHARED_RANK = 2  # web 直下（auth, tenancy, config, audit_context …）は共通基盤
_DOMAIN_RANK = 4  # src.* はドメイン中核。誰にも依存しないのが正しい


def _layer_rank(node: str) -> int:
    if node in _LAYER_RANK:
        return _LAYER_RANK[node]
    if node.split(".")[0] == "src":
        return _DOMAIN_RANK
    return _WEB_SHARED_RANK


def offending_imports(
    modules: list[dict[str, Any]], cycles: list[list[str]]
) -> list[dict[str, str]]:
    """循環を成立させている「逆流した import」だけを名指しする。

    循環はサブパッケージ単位で数えるため、逆依存が 1 本残るだけで経路は複数出る。
    件数だけ見ても改善が見えないので、実際に直すべき import を列挙する。
    経路上のエッジを全部挙げると `web.routes -> web.services` のような正常な依存まで
    混ざるので、レイヤ順序に逆らう向きのものに絞る。
    """
    edges: set[tuple[str, str]] = set()
    for cycle in cycles:
        for src, dst in zip(cycle, cycle[1:], strict=False):
            if _layer_rank(src) > _layer_rank(dst):  # 下位 → 上位＝逆流
                edges.add((src, dst))

    offenders: list[dict[str, str]] = []
    for module in modules:
        node = module.get("subpackage") or module["package"]
        for dep in module["internal_deps"]:
            if (node, dep) in edges:
                offenders.append(
                    {
                        "module": module["path"],
                        "imports": dep,
                        "reason": f"{node}(層{_layer_rank(node)}) -> {dep}(層{_layer_rank(dep)}) の逆流",
                    }
                )
    offenders.sort(key=lambda d: d["module"])
    return offenders


def detect_cycles(modules: list[dict[str, Any]]) -> list[list[str]]:
    """サブパッケージ間の循環依存を検出する。設計書に載せるべき事実なので機械で取る。"""
    graph: dict[str, set[str]] = {}
    for module in modules:
        node = module.get("subpackage") or module["package"]
        graph.setdefault(node, set()).update(module["internal_deps"])

    cycles: list[list[str]] = []
    seen_pairs: set[tuple[str, ...]] = set()

    def walk(node: str, path: list[str], visiting: set[str]) -> None:
        for nxt in sorted(graph.get(node, ())):
            if nxt in visiting:
                cycle = path[path.index(nxt) :] + [nxt]
                key = tuple(sorted(set(cycle)))
                if key not in seen_pairs:
                    seen_pairs.add(key)
                    cycles.append(cycle)
                continue
            if len(path) >= 6:  # 長い経路は設計判断に使えないので打ち切る
                continue
            walk(nxt, path + [nxt], visiting | {nxt})

    for start in sorted(graph):
        walk(start, [start], {start})
    return cycles


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """引数と戻り値注釈だけの短い署名。本文は詳細設計に載せない。"""
    args = [a.arg for a in node.args.args]
    if node.args.vararg:
        args.append(f"*{node.args.vararg.arg}")
    if node.args.kwarg:
        args.append(f"**{node.args.kwarg.arg}")
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"({', '.join(args)}){returns}"


def extract_schema() -> str:
    """instance/*.db の物理スキーマを DDL として出力する。"""
    chunks: list[str] = []
    instance_dir = ROOT / "instance"
    if not instance_dir.is_dir():
        return "-- instance/ が存在しないためスキーマ未取得\n"

    for db_path in sorted(instance_dir.glob("*.db")):
        if ".e2e." in db_path.name:  # テスト専用 DB は納品対象外
            continue
        chunks.append(f"-- ===== {db_path.name} =====")
        try:
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
                rows = conn.execute(
                    "SELECT type, name, sql FROM sqlite_master "
                    "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END, name"
                ).fetchall()
            for _type, _name, sql in rows:
                chunks.append(f"{sql.strip()};")
        except sqlite3.Error as exc:
            chunks.append(f"-- 読み取り失敗: {exc}")
        chunks.append("")
    return "\n".join(chunks) + "\n"


def _license_of(meta: Any) -> tuple[str, str]:
    """配布メタデータからライセンス名と、その判定根拠を返す。

    近年のパッケージは PEP 639 の `License-Expression` にライセンスを入れ、
    従来の `License` フィールドと `License ::` classifier を空にする。
    そこだけ見ていると Flask・numpy・pytest まで UNKNOWN になる。
    """
    expression = (meta.get("License-Expression") or "").strip()
    if expression:
        return expression, "License-Expression (PEP 639)"

    for item in meta.get_all("Classifier") or []:
        if item.startswith("License ::"):
            return item.split("::")[-1].strip(), "Classifier"

    legacy = (meta.get("License") or "").strip()
    if legacy:
        # 一部のパッケージは License に全文を入れる。1 行目だけを名前として扱う
        first_line = legacy.splitlines()[0].strip()
        if first_line and len(first_line) <= 80:
            return first_line, "License field"
        return "要確認（License 欄に全文が入っている）", "License field (full text)"

    files = meta.get_all("License-File") or []
    if files:
        return "要確認（同梱 LICENSE ファイル参照）", f"License-File: {', '.join(files[:3])}"

    return "UNKNOWN", "メタデータに記載なし"


def extract_licenses() -> list[dict[str, str]]:
    """requirements に現れる依存の OSS ライセンスを配布メタデータから取る。"""
    results: list[dict[str, str]] = []
    seen: set[str] = set()

    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        license_name, source = _license_of(dist.metadata)
        results.append(
            {
                "name": name,
                "version": dist.version or "",
                "license": license_name.strip() or "UNKNOWN",
                "license_source": source,  # 判定根拠。監査で「どこから取ったか」を問われる
                "ecosystem": "PyPI",
                "homepage": dist.metadata.get("Home-page")
                or dist.metadata.get("Project-URL")
                or "",
            }
        )
    results.sort(key=lambda d: d["name"].lower())
    return results


def _npm_licenses() -> list[dict[str, str]]:
    """AutoRun が使う npm 依存（Playwright 実行環境）のライセンス。"""
    pkg_json = ROOT / "package.json"
    if not pkg_json.exists():
        return []
    try:
        out = subprocess.run(
            ["npm", "ls", "--all", "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        data = json.loads(out.stdout or "{}")
    except (OSError, json.JSONDecodeError, subprocess.SubprocessError):
        return []

    found: list[dict[str, str]] = []

    def walk(deps: dict[str, Any]) -> None:
        for name, info in (deps or {}).items():
            if not isinstance(info, dict):
                continue
            found.append(
                {
                    "name": name,
                    "version": str(info.get("version", "")),
                    "license": str(info.get("license", "UNKNOWN")),
                    "ecosystem": "npm",
                }
            )
            walk(info.get("dependencies", {}))

    walk(data.get("dependencies", {}))
    return found


def extract_templates() -> list[dict[str, Any]]:
    """テンプレートと extends / include 関係（画面設計書の構成入力）。"""
    templates: list[dict[str, Any]] = []
    base = ROOT / "templates"
    if not base.is_dir():
        return templates

    pattern = re.compile(r"{%-?\s*(extends|include)\s+[\"']([^\"']+)[\"']")
    for path in sorted(base.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        refs = pattern.findall(text)
        blocks = re.findall(r"{%-?\s*block\s+(\w+)", text)
        templates.append(
            {
                "path": str(path.relative_to(ROOT)),
                "loc": text.count("\n") + 1,
                "extends": [t for kind, t in refs if kind == "extends"],
                "includes": sorted({t for kind, t in refs if kind == "include"}),
                "blocks": sorted(set(blocks)),
                "title": (
                    m.group(1).strip()
                    if (m := re.search(r"<title[^>]*>(.*?)</title>", text, re.S))
                    else ""
                ),
            }
        )
    return templates


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    routes = extract_routes()
    modules = extract_modules()
    templates = extract_templates()
    licenses = extract_licenses() + _npm_licenses()
    schema = extract_schema()

    (OUT_DIR / "routes.json").write_text(
        json.dumps(routes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "modules.json").write_text(
        json.dumps(modules, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "templates.json").write_text(
        json.dumps(templates, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "licenses.json").write_text(
        json.dumps(licenses, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "schema.sql").write_text(schema, encoding="utf-8")

    cycles = detect_cycles(modules)
    offenders = offending_imports(modules, cycles)
    (OUT_DIR / "dependency_cycles.json").write_text(
        json.dumps(
            {"cycles": cycles, "offending_modules": offenders},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"routes    : {len(routes)}")
    print(f"modules   : {len(modules)}")
    print(f"templates : {len(templates)}")
    print(f"licenses  : {len(licenses)}")
    print(f"cycles    : {len(cycles)} 経路 / 原因 import {len(offenders)} 本")
    for cycle in cycles[:10]:
        print(f"        経路: {' -> '.join(cycle)}")
    for item in offenders[:10]:
        print(f"        原因: {item['module']} -> {item['imports']}")
    print(f"output    : {OUT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
