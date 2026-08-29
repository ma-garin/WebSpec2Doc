#!/usr/bin/env python3
"""機能単位アセットのエクスポート（他環境への受け渡し用バンドル生成）。

このリポジトリの役割は「機能単位で作り込み、他環境へアセットを渡す」こと。
受け渡しの単位は `quality/feature_contracts.yml` の feature_id に一致させる。
受け側が推測せずに組み込めるだけの情報を 1 つのバンドルに固める。

    - ファイル実体（repo 相対パスのまま。配置先がパスそのもので分かる）
    - SHA-256（欠落・改ざん・部分コピーを受け側で検出できる）
    - 組み込み手順（Blueprint 登録・SPA シェルへの include / script / link）
    - 同梱外依存（内部モジュール・サードパーティ・環境変数・呼び出す API・データファイル）

使い方:
    python3 scripts/export_feature_asset.py --list
    python3 scripts/export_feature_asset.py test_activity_support
    python3 scripts/export_feature_asset.py test_activity_support --with-tests --with-docs
    python3 scripts/export_feature_asset.py --all

出力:
    dist/assets/<feature_id>/<version>/manifest.json / INTEGRATION.md / contract.json / files/...
    dist/assets/<feature_id>-<version>.tar.gz

注意: 本スクリプトが行うのは静的解析による棚卸しである。実行時の動作確認は行わない
（`.claude/rules/speed-harness.md` H-7）。実行検証が要る場合は受け側で行う。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FILE = ROOT / "quality" / "feature_contracts.yml"
DEFAULT_OUT = ROOT / "dist" / "assets"

# contract のキー -> バンドル内での役割。受け側の配置手順はこの役割で分岐する。
ROLE_BY_KEY = {
    "ui_files": "ui",
    "route_files": "route",
    "core_files": "core",
}

# import 名と配布パッケージ名が食い違うもの。requirements.txt との突き合わせ用。
DIST_ALIASES = {
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "PIL": "Pillow",
    "fitz": "PyMuPDF",
    "jwt": "PyJWT",
}

INTERNAL_ROOTS = ("web", "src", "scripts", "tests")

# web/__init__.py が `src/` を sys.path に差し込むため、`from diff.snapshot import ...`
# のようなトップレベル import が `src/diff/snapshot.py` を指す。サードパーティと
# 誤判定すると受け側が「存在しない pip パッケージ」を探すことになるので必ず解決する。
SRC_ON_SYS_PATH = True

RE_ENV = re.compile(
    r"""os\.(?:environ\.get|getenv)\(\s*["']([A-Z][A-Z0-9_]*)["']"""
    r"""|os\.environ\[\s*["']([A-Z][A-Z0-9_]*)["']"""
)
RE_BLUEPRINT = re.compile(
    r"""Blueprint\(\s*["'](\w+)["']\s*,\s*__name__\s*(?:,\s*url_prefix\s*=\s*["']([^"']*)["'])?"""
)
RE_ROUTE = re.compile(
    r"""@\w+\.(route|get|post|put|patch|delete)\(\s*["']([^"']+)["']([^)]*)\)"""
)
RE_METHODS = re.compile(r"""methods\s*=\s*\[([^\]]*)\]""")
RE_JS_FETCH = re.compile(r"""fetch\(\s*[`'"]([^`'"]+)""")
RE_API_LITERAL = re.compile(r"""[`'"](/api/[A-Za-z0-9_\-/.]*)""")
RE_TPL_INCLUDE = re.compile(r"""\{%-?\s*(?:include|extends)\s+["']([^"']+)["']""")
RE_TPL_STATIC = re.compile(
    r"""url_for\(\s*["']static["']\s*,\s*filename\s*=\s*["']([^"']+)["']"""
)
RE_DATA_FILE = re.compile(r"""\bdata/[A-Za-z0-9_./-]+\.(?:json|csv|ya?ml)""")
RE_WINDOW_GLOBAL = re.compile(r"""\bwindow\.([A-Za-z_$][\w$]*)""")

# window.* のうちブラウザ組み込み。アセットの依存ではないので除く。
BROWSER_GLOBALS = frozenset({
    "addEventListener", "removeEventListener", "dispatchEvent", "location", "open",
    "close", "closed", "document", "alert", "confirm", "prompt", "setTimeout",
    "setInterval", "clearTimeout", "clearInterval", "fetch", "innerWidth",
    "innerHeight", "outerWidth", "outerHeight", "scrollTo", "scrollY", "scrollX",
    "matchMedia", "localStorage", "sessionStorage", "history", "navigator",
    "requestAnimationFrame", "cancelAnimationFrame", "getComputedStyle", "URL",
    "URLSearchParams", "crypto", "performance", "console", "parent", "top", "self",
    "screen", "print", "focus", "blur", "getSelection", "CustomEvent", "Event",
    "Blob", "FormData", "AbortController", "IntersectionObserver", "ResizeObserver",
    "MutationObserver", "postMessage", "onload", "onerror", "onresize", "onhashchange",
})


# --------------------------------------------------------------------------
# 読み込み
# --------------------------------------------------------------------------
def load_contracts() -> list[dict[str, Any]]:
    if not CONTRACT_FILE.exists():
        raise SystemExit(f"契約ファイルがない: {CONTRACT_FILE}")
    data = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
    return list(data.get("features", []))


def find_feature(features: list[dict[str, Any]], feature_id: str) -> dict[str, Any]:
    for feature in features:
        if feature.get("feature_id") == feature_id:
            return feature
    known = ", ".join(sorted(f.get("feature_id", "?") for f in features))
    raise SystemExit(f"未知の feature_id: {feature_id}\n登録済み: {known}")


def git_revision() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def git_dirty() -> bool:
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        return bool(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def requirements_index() -> dict[str, str]:
    """requirements*.txt を「小文字の配布名 -> 元の行の指定」に落とす。"""
    index: dict[str, str] = {}
    for name in ("requirements.txt", "requirements-dev.txt"):
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            dist = re.split(r"[<>=!\[ ]", line, 1)[0].strip()
            if dist:
                index[dist.lower()] = line
    return index


# --------------------------------------------------------------------------
# 静的解析
# --------------------------------------------------------------------------
def _module_to_paths(module: str) -> list[str]:
    """`web.services.foo` -> 実在する repo 相対パス候補。"""
    parts = module.split(".")
    if not parts or parts[0] not in INTERNAL_ROOTS:
        return []
    base = "/".join(parts)
    found = [c for c in (f"{base}.py", f"{base}/__init__.py") if (ROOT / c).exists()]
    if found:
        return found
    # `from web.services import foo` の foo が付いていない形（親パッケージ）
    parent = "/".join(parts[:-1])
    if parent and (ROOT / f"{parent}/{parts[-1]}.py").exists():
        return [f"{parent}/{parts[-1]}.py"]
    return []


def analyze_python(rel: str, text: str, acc: dict[str, Any]) -> None:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:  # 解析できないものは黙って捨てず記録する
        acc["parse_errors"].append(f"{rel}: {exc}")
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _record_import(alias.name, acc)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 相対 import は同梱ファイル内で閉じる想定
                continue
            base = node.module or ""
            _record_import(base, acc)
            for alias in node.names:
                _record_import(f"{base}.{alias.name}" if base else alias.name, acc)

    for match in RE_ENV.finditer(text):
        acc["env_vars"].add(match.group(1) or match.group(2))

    for name, prefix in RE_BLUEPRINT.findall(text):
        acc["blueprints"].append({"file": rel, "name": name, "url_prefix": prefix or ""})

    for verb, path, tail in RE_ROUTE.findall(text):
        methods_match = RE_METHODS.search(tail)
        if methods_match:
            methods = [
                m.strip().strip("\"'") for m in methods_match.group(1).split(",") if m.strip()
            ]
        elif verb == "route":
            methods = ["GET"]
        else:
            methods = [verb.upper()]
        acc["provides_endpoints"].append({"file": rel, "rule": path, "methods": methods})

    for hit in RE_DATA_FILE.findall(text):
        acc["data_files"].add(hit)


def _record_import(module: str, acc: dict[str, Any]) -> None:
    if not module:
        return
    top = module.split(".")[0]
    if top in INTERNAL_ROOTS:
        for path in _module_to_paths(module):
            acc["internal_modules"].add(path)
        return
    if top in sys.stdlib_module_names or top == "__future__":
        return
    if SRC_ON_SYS_PATH:
        under_src = _module_to_paths(f"src.{module}")
        if under_src:
            acc["internal_modules"].update(under_src)
            return
        # `from analyzer.html_analyzer import X` の X のように、モジュールではなく
        # シンボルを指す形はパス解決に失敗する。トップレベルが内部パッケージなら
        # サードパーティに落とさない（落とすと受け側が pip で探すことになる）。
        if (ROOT / "src" / top).is_dir() or (ROOT / "src" / f"{top}.py").is_file():
            return
    acc["third_party"].add(DIST_ALIASES.get(top, top))


def analyze_js(rel: str, text: str, acc: dict[str, Any]) -> None:
    for hit in RE_JS_FETCH.findall(text):
        endpoint = hit.split("?", 1)[0].split("$", 1)[0]
        if endpoint.startswith("/"):
            acc["consumes_endpoints"].add(endpoint)
    for hit in RE_API_LITERAL.findall(text):
        endpoint = hit.split("?", 1)[0]
        if endpoint != "/api/":  # 文字列連結の断片。情報量がないので捨てる
            acc["consumes_endpoints"].add(endpoint)
    for hit in RE_DATA_FILE.findall(text):
        acc["data_files"].add(hit)
    for hit in RE_WINDOW_GLOBAL.findall(text):
        if hit not in BROWSER_GLOBALS:
            acc["window_globals"].add(hit)


def analyze_html(rel: str, text: str, acc: dict[str, Any]) -> None:
    for hit in RE_TPL_INCLUDE.findall(text):
        acc["template_includes"].add(hit)
    for hit in RE_TPL_STATIC.findall(text):
        acc["static_refs"].add(f"static/{hit}")
    for hit in RE_API_LITERAL.findall(text):
        acc["consumes_endpoints"].add(hit.split("?", 1)[0])


# --------------------------------------------------------------------------
# バンドル構築
# --------------------------------------------------------------------------
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_files(
    feature: dict[str, Any], with_tests: bool, with_docs: bool, docs: list[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """(同梱ファイル, 契約にあるが実在しないパス) を返す。"""
    entries: list[dict[str, Any]] = []
    missing: list[str] = []
    seen: set[str] = set()

    planned: list[tuple[str, str]] = []
    for key, role in ROLE_BY_KEY.items():
        planned += [(rel, role) for rel in feature.get(key, [])]
    if with_tests:
        planned += [(rel, "test") for rel in feature.get("required_tests", [])]
    if with_docs:
        planned += [(rel, "doc") for rel in docs]

    for rel, role in planned:
        if rel in seen:
            continue
        seen.add(rel)
        path = ROOT / rel
        if not path.is_file():
            missing.append(rel)
            continue
        entries.append(
            {
                "path": rel,
                "role": role,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return entries, missing


def analyze_bundle(entries: list[dict[str, Any]]) -> dict[str, Any]:
    acc: dict[str, Any] = {
        "internal_modules": set(),
        "third_party": set(),
        "env_vars": set(),
        "data_files": set(),
        "consumes_endpoints": set(),
        "window_globals": set(),
        "template_includes": set(),
        "static_refs": set(),
        "provides_endpoints": [],
        "blueprints": [],
        "parse_errors": [],
    }
    for entry in entries:
        rel = entry["path"]
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if rel.endswith(".py"):
            analyze_python(rel, text, acc)
        elif rel.endswith(".js"):
            analyze_js(rel, text, acc)
        elif rel.endswith((".html", ".jinja", ".jinja2")):
            analyze_html(rel, text, acc)
    return acc


def build_dependencies(
    entries: list[dict[str, Any]], acc: dict[str, Any], reqs: dict[str, str]
) -> dict[str, Any]:
    bundled = {e["path"] for e in entries}
    bundled_templates = {p.split("templates/", 1)[1] for p in bundled if "templates/" in p}

    external_internal = sorted(p for p in acc["internal_modules"] if p not in bundled)
    third_party = [
        {
            "import": name,
            "requirement": reqs.get(name.lower(), ""),
            "declared_in_requirements": name.lower() in reqs,
        }
        for name in sorted(acc["third_party"])
    ]

    return {
        # 同梱していないが受け側に存在しなければ動かない内部モジュール
        "internal_modules_not_bundled": external_internal,
        "third_party_packages": third_party,
        "env_vars": sorted(acc["env_vars"]),
        "data_files": sorted(acc["data_files"]),
        # このアセットが呼び出す API（受け側に実在が必要）
        "consumes_endpoints": sorted(acc["consumes_endpoints"]),
        # 同梱 JS が参照するグローバル（他アセット由来なら別途受け渡しが要る）
        "window_globals": sorted(acc["window_globals"]),
        "template_includes_not_bundled": sorted(
            t for t in acc["template_includes"] if t not in bundled_templates
        ),
        "static_refs_not_bundled": sorted(
            s for s in acc["static_refs"] if s not in bundled
        ),
    }


def related_docs(feature_id: str) -> list[str]:
    """機能 ID または機能名を本文に含む docs/ 配下の Markdown を拾う。"""
    hits: list[str] = []
    docs_root = ROOT / "docs"
    if not docs_root.is_dir():
        return hits
    for path in sorted(docs_root.rglob("*.md")):
        if "archive" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if feature_id in text:
            hits.append(str(path.relative_to(ROOT)))
    return hits


# --------------------------------------------------------------------------
# 受け側が読む組み込み手順
# --------------------------------------------------------------------------
def _bullets(items: list[str], empty: str = "なし") -> str:
    return "\n".join(f"- `{i}`" for i in items) if items else f"- {empty}"


def render_integration(manifest: dict[str, Any]) -> str:
    feature = manifest["feature"]
    deps = manifest["dependencies"]
    files = manifest["files"]
    wiring = manifest["wiring"]

    by_role: dict[str, list[dict[str, Any]]] = {}
    for entry in files:
        by_role.setdefault(entry["role"], []).append(entry)

    lines: list[str] = []
    add = lines.append

    add(f"# 組み込み手順: {feature['name']}")
    add("")
    add("| 項目 | 値 |")
    add("|---|---|")
    add(f"| feature_id | `{feature['feature_id']}` |")
    add(f"| 版 | `{manifest['version']}` |")
    add(f"| 生成元 | `{manifest['source']['repository']}` @ `{manifest['source']['revision']}` |")
    add(f"| 生成日時 (UTC) | {manifest['generated_at']} |")
    add(f"| リスク / 状態 | {feature['risk_level']} / {feature['status']} |")
    add(f"| 同梱ファイル数 | {len(files)} |")
    if manifest["source"]["working_tree_dirty"]:
        add("| 生成時の作業ツリー | **未コミットの変更あり**（再現性が落ちる。コミット後の再生成を推奨） |")
    add("")

    add("## 0. 先に検証する")
    add("")
    add("配置の前にバンドルの完全性を確認する。SHA-256 が 1 つでも合わなければ、")
    add("転送か展開が壊れているので配置しない。")
    add("")
    add("```bash")
    add("python3 scripts/verify_feature_asset.py <このディレクトリ>")
    add("# 受け側リポジトリの依存充足も見る場合")
    add("python3 scripts/verify_feature_asset.py <このディレクトリ> --against <受け側リポジトリのルート>")
    add("```")
    add("")

    add("## 1. ファイルを配置する")
    add("")
    add("`files/` 配下は **リポジトリ相対パスをそのまま保持** している。配置先はパスそのもの。")
    add("")
    add("```bash")
    add("rsync -a files/ <受け側リポジトリのルート>/")
    add("```")
    add("")
    for role, label in (
        ("route", "ルート（API）"),
        ("core", "サービス / コア"),
        ("ui", "UI（テンプレート・JS・CSS）"),
        ("test", "テスト"),
        ("doc", "ドキュメント"),
    ):
        entries = by_role.get(role, [])
        if not entries:
            continue
        add(f"### {label}（{len(entries)} 件）")
        add("")
        add("| パス | bytes | sha256 (先頭12) |")
        add("|---|---:|---|")
        for entry in entries:
            add(f"| `{entry['path']}` | {entry['bytes']} | `{entry['sha256'][:12]}` |")
        add("")

    add("## 2. 配線する")
    add("")
    if wiring["blueprints"]:
        add("### 2-1. Blueprint を登録する")
        add("")
        add("受け側の `web/__init__.py`（アプリケーションファクトリ）に追記する。")
        add("")
        add("```python")
        mods = sorted({Path(b["file"]).stem for b in wiring["blueprints"]})
        add(f"from web.routes import {', '.join(mods)}")
        for mod in mods:
            add(f"app.register_blueprint({mod}.bp)")
        add("```")
        add("")
        add("| Blueprint | url_prefix | 定義元 |")
        add("|---|---|---|")
        for bp in wiring["blueprints"]:
            add(f"| `{bp['name']}` | `{bp['url_prefix'] or '(なし)'}` | `{bp['file']}` |")
        add("")
    else:
        add("### 2-1. Blueprint を登録する")
        add("")
        add("- このアセットに Blueprint は含まれない（登録作業なし）。")
        add("")

    templates = [e["path"] for e in by_role.get("ui", []) if e["path"].endswith(".html")]
    scripts = [e["path"] for e in by_role.get("ui", []) if e["path"].endswith(".js")]
    styles = [e["path"] for e in by_role.get("ui", []) if e["path"].endswith(".css")]
    if templates or scripts or styles:
        add("### 2-2. SPA シェルに差し込む")
        add("")
        add("受け側の `templates/index.html` に追記する（本リポジトリと同じ配線規約）。")
        add("")
        add("```jinja")
        for path in templates:
            rel = path.split("templates/", 1)[-1]
            add("{% include '" + rel + "' %}")
        for path in styles:
            rel = path.split("static/", 1)[-1]
            add(
                "<link rel=\"stylesheet\" href=\"{{ url_for('static', filename='"
                + rel
                + "') }}?v={{ _ver }}\">"
            )
        for path in scripts:
            rel = path.split("static/", 1)[-1]
            add(
                "<script src=\"{{ url_for('static', filename='"
                + rel
                + "') }}?v={{ _ver }}\"></script>"
            )
        add("```")
        add("")
        add("`?v={{ _ver }}` は本リポジトリのキャッシュバスター。受け側に同等の仕組みが")
        add("なければ外す。**外すと JS / CSS の古いキャッシュを掴む**ため、代替を用意すること。")
        add("")

    add("### 2-3. 機能契約を登録する")
    add("")
    add("受け側でも完了判定を機械化する場合は、`contract.json` の内容を受け側の")
    add("`quality/feature_contracts.yml` の `features` に追加する。")
    add("**feature_id はそのまま流用せず、受け側の体系で付け直す**")
    add("（`docs/common-assets-docs-vs-testlab.md` 第 3 節: 契約の形式は共用してよいが中身は各システム固有）。")
    add("")

    add("## 3. 同梱していない依存（受け側に必要なもの）")
    add("")
    add("ここが埋まらないとアセットは動かない。配置前に 1 つずつ確認する。")
    add("")
    add("### 3-1. 内部モジュール（同梱外）")
    add("")
    add("同梱ファイルが import しているが、このアセットには含まれないもの。")
    add("受け側に同名・同パスで実在する必要がある。")
    add("")
    add(_bullets(deps["internal_modules_not_bundled"], "なし（同梱ファイル内で閉じている）"))
    add("")
    add("### 3-2. サードパーティ")
    add("")
    if deps["third_party_packages"]:
        add("| import 名 | requirements の指定 |")
        add("|---|---|")
        for pkg in deps["third_party_packages"]:
            spec = pkg["requirement"] or "**本リポジトリの requirements.txt に記載なし・要確認**"
            add(f"| `{pkg['import']}` | {spec} |")
    else:
        add("- なし（標準ライブラリのみ）")
    add("")
    add("### 3-3. 環境変数")
    add("")
    add(_bullets(deps["env_vars"]))
    add("")
    add("### 3-4. 呼び出す API（受け側に実在が必要）")
    add("")
    add(_bullets(deps["consumes_endpoints"]))
    add("")
    add("### 3-5. データファイル")
    add("")
    add(_bullets(deps["data_files"]))
    add("")
    add("### 3-6. 同梱外のテンプレート / 静的ファイル参照")
    add("")
    add(_bullets(
        deps["template_includes_not_bundled"] + deps["static_refs_not_bundled"],
        "なし",
    ))
    add("")
    add("### 3-7. 同梱 JS が参照するグローバル")
    add("")
    add("他アセット由来のものが混ざっていれば、そのアセットも併せて受け渡す。")
    add("")
    add(_bullets(deps["window_globals"], "なし"))
    add("")

    add("## 3-8. 併せて渡す必要のある他機能の資産")
    add("")
    add("このアセットと対で動くが、**別の機能契約に属している**ファイル。")
    add("受け側に無ければ、その機能のアセットも別途エクスポートして渡す。")
    add("")
    if manifest["shared_assets"]:
        add("| ファイル | 所属する機能 | 関係 |")
        add("|---|---|---|")
        for item in manifest["shared_assets"]:
            add(
                f"| `{item['path']}` | {', '.join(f'`{o}`' for o in item['owned_by'])} "
                f"| {item['reason']} |"
            )
    else:
        add("- なし")
    add("")

    add("## 4. このアセットが提供する API")
    add("")
    if wiring["provides_endpoints"]:
        add("| メソッド | ルール | 定義元 |")
        add("|---|---|---|")
        for ep in wiring["provides_endpoints"]:
            add(f"| {', '.join(ep['methods'])} | `{ep['rule']}` | `{ep['file']}` |")
    else:
        add("- なし")
    add("")

    add("## 5. 受け入れ確認（契約より）")
    add("")
    add("組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**")
    add("")
    add("### 出力")
    add("")
    add(_bullets(feature.get("outputs", [])))
    add("")
    add("### 永続化")
    add("")
    add(_bullets(feature.get("persistence", [])))
    add("")
    add("### 失敗経路（すべて実際に踏むこと）")
    add("")
    add("\n".join(f"- {m}" for m in feature.get("failure_modes", [])) or "- なし")
    add("")
    add("### 対応テスト")
    add("")
    add(_bullets(feature.get("required_tests", [])))
    add("")

    add("## 6. 未検証事項（エクスポート側の申告）")
    add("")
    add("- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる")
    add("  URL・実行時にのみ解決される参照は検出できない。")
    add("- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**")
    add("  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。")
    add("- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。")
    if manifest["warnings"]:
        add("")
        add("### 生成時の警告")
        add("")
        add("\n".join(f"- {w}" for w in manifest["warnings"]))
    add("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 欠落検出（フォルダ単位で渡す以上、契約の登録漏れは致命傷になる）
# --------------------------------------------------------------------------
def ownership_index(features: list[dict[str, Any]]) -> dict[str, list[str]]:
    """ファイルパス -> それを契約に登録している feature_id の一覧。"""
    owners: dict[str, list[str]] = {}
    for feature in features:
        for key in ROLE_BY_KEY:
            for rel in feature.get(key, []):
                owners.setdefault(rel, []).append(feature["feature_id"])
    return owners


def detect_gaps(
    entries: list[dict[str, Any]],
    owners: dict[str, list[str]],
    feature_id: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """同梱ファイルと対になるはずのファイルが同梱されていない箇所を洗い出す。

    契約（feature_contracts.yml）は人が書くため登録漏れが起きる。実際に
    `diff_history` は JS だけが登録され、その画面テンプレート
    （`templates/partials/view-run-history.html` ほか）が抜けていた。
    フォルダ単位で渡す以上、これは渡した先で「画面が出ない」に直結するので機械的に拾う。

    `templates/index.html`（SPA シェル）は組み込み先そのものなので対象外にする。
    受け側での差し込みは INTEGRATION.md 第 2-2 節が扱う。
    """
    bundled = {e["path"] for e in entries}
    gaps: list[dict[str, str]] = []
    shared: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _flag(rel: str, reason: str) -> None:
        if rel in bundled or rel in seen or not (ROOT / rel).is_file():
            return
        seen.add(rel)
        other_owners = [f for f in owners.get(rel, []) if f != feature_id]
        if other_owners:
            # 他機能の契約に登録済み = 共通資産。登録漏れではなく「一緒に渡す対象」。
            shared.append({"path": rel, "owned_by": other_owners, "reason": reason})
        else:
            gaps.append({"path": rel, "reason": reason})

    for rel in sorted(bundled):
        name = Path(rel).stem
        if rel.startswith("static/js/"):
            base = name[5:] if name.startswith("view-") else name
            for candidate in (
                f"templates/partials/{name}.html",
                f"templates/partials/view-{base}.html",
                f"templates/partials/{base}.html",
            ):
                _flag(candidate, f"`{rel}` の画面テンプレートと見られるが未同梱")
            _flag(f"static/css/{name}.css", f"`{rel}` と対の CSS と見られるが未同梱")
        elif rel.startswith("templates/partials/"):
            base = name[5:] if name.startswith("view-") else name
            for candidate in (f"static/js/{name}.js", f"static/js/{base}.js"):
                _flag(candidate, f"`{rel}` を動かす JS と見られるが未同梱")
            for candidate in (f"static/css/{name}.css", f"static/css/{base}.css"):
                _flag(candidate, f"`{rel}` と対の CSS と見られるが未同梱")

    # 同梱の静的ファイルを差し込んでいるテンプレート（シェルを除く）
    templates_root = ROOT / "templates"
    # `static/app.css` のような static/ 直下のファイルはアプリ全体の共通バンドル。
    # これを逆引きすると「参照している全テンプレート」が出てノイズになるため除く。
    static_names = {
        p.split("static/", 1)[1]
        for p in bundled
        if p.startswith("static/") and p.count("/") > 1
    }
    if templates_root.is_dir():
        for path in sorted(templates_root.rglob("*.html")):
            rel = str(path.relative_to(ROOT))
            if rel in bundled or rel == "templates/index.html":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for ref in RE_TPL_STATIC.findall(text):
                if ref in static_names:
                    _flag(rel, f"同梱の `static/{ref}` を差し込んでいるが未同梱")

    return gaps, shared


# --------------------------------------------------------------------------
# 出力
# --------------------------------------------------------------------------
def _is_path_like(value: str) -> bool:
    return "/" in value or value.endswith((".py", ".mjs", ".js", ".ts", ".spec.ts"))


def export(
    feature: dict[str, Any],
    version: str,
    out_root: Path,
    *,
    with_tests: bool,
    with_docs: bool,
    archive: bool,
) -> Path:
    feature_id = feature["feature_id"]
    docs = related_docs(feature_id) if with_docs else []

    # required_tests はファイルパスの場合と種別ラベル（happy_path 等）の場合がある。
    # パスに見えるものだけ同梱対象にし、ラベルは受け入れ確認（第5節）で扱う。
    feature_for_files = dict(feature)
    feature_for_files["required_tests"] = [
        t for t in feature.get("required_tests", []) if _is_path_like(t)
    ]

    entries, missing = collect_files(feature_for_files, with_tests, with_docs, docs)
    if not entries:
        raise SystemExit(f"同梱できるファイルが 1 つもない: {feature_id}")

    acc = analyze_bundle(entries)
    deps = build_dependencies(entries, acc, requirements_index())
    owners = ownership_index(load_contracts())
    gaps, shared = detect_gaps(entries, owners, feature_id)

    warnings: list[str] = []
    for rel in missing:
        warnings.append(f"契約に載っているがファイルが実在しない: `{rel}`")
    for gap in gaps:
        warnings.append(
            f"どの機能契約にも登録されていない関連ファイル: `{gap['path']}` — {gap['reason']}"
        )
    for err in acc["parse_errors"]:
        warnings.append(f"解析できなかった: {err}")
    shared_html = any(item["path"].endswith(".html") for item in shared)
    if (
        not any(e["path"].endswith(".html") for e in entries)
        and any(e["path"].endswith(".js") for e in entries)
        and not shared_html
    ):
        # 画面 HTML が同梱にも共通資産にも見当たらない = この機能だけでは画面が出ない。
        warnings.append(
            "JS は同梱しているが画面テンプレート（.html）が、同梱にも他機能の共通資産にも"
            "見当たらない。契約の ui_files に登録漏れがないか確認すること。"
        )

    manifest: dict[str, Any] = {
        "schema": "webspec2doc/feature-asset@1",
        "version": version,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {
            "repository": "WebSpec2Doc",
            "revision": git_revision(),
            "working_tree_dirty": git_dirty(),
            "contract_file": "quality/feature_contracts.yml",
        },
        "feature": feature,
        "files": entries,
        "wiring": {
            "blueprints": acc["blueprints"],
            "provides_endpoints": acc["provides_endpoints"],
        },
        "dependencies": deps,
        "gaps": gaps,
        "shared_assets": shared,
        "warnings": warnings,
        "verification": {
            "static_analysis": "done",
            "pytest": "not_run",
            "verify_ui": "not_run",
            "manual_screen_check": "not_run",
        },
    }

    bundle_dir = out_root / feature_id / version
    files_dir = bundle_dir / "files"
    if bundle_dir.exists():
        import shutil

        shutil.rmtree(bundle_dir)
    files_dir.mkdir(parents=True)

    import shutil

    for entry in entries:
        dest = files_dir / entry["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / entry["path"], dest)

    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (bundle_dir / "contract.json").write_text(
        json.dumps(feature, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (bundle_dir / "INTEGRATION.md").write_text(
        render_integration(manifest), encoding="utf-8"
    )

    if archive:
        tar_path = out_root / f"{feature_id}-{version}.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(bundle_dir, arcname=f"{feature_id}-{version}")

    return bundle_dir


def cmd_list(features: list[dict[str, Any]]) -> int:
    print(f"{'feature_id':38} {'risk':9} {'状態':12} files  名称")
    for feature in sorted(features, key=lambda f: f["feature_id"]):
        count = sum(len(feature.get(k, [])) for k in ROLE_BY_KEY)
        print(
            f"{feature['feature_id']:38} {feature['risk_level']:9} "
            f"{feature['status']:12} {count:5}  {feature['name']}"
        )
    return 0


def cmd_audit(features: list[dict[str, Any]]) -> int:
    """どの機能契約にも属していない UI ファイルを洗い出す。

    `scripts/quality_harness.py` は `.py` モジュールの登録漏れしか見ていない
    （FEATURE_SOURCE_ROOTS = src / web/routes / web/services）。テンプレート・JS・CSS は
    登録されていなくてもゲートが通るため、機能単位で渡そうとした時点で初めて
    「画面が出ない」が露見する。渡す前にここで潰す。
    """
    owners = ownership_index(features)
    patterns = (
        "static/js/*.js",
        "static/css/*.css",
        "static/*.css",
        "templates/*.html",
        "templates/auth/*.html",
        "templates/partials/*.html",
    )
    unregistered: list[tuple[int, str, list[str]]] = []
    for pattern in patterns:
        for path in sorted(ROOT.glob(pattern)):
            rel = str(path.relative_to(ROOT))
            if rel in owners:
                continue
            unregistered.append((path.stat().st_size, rel, _referenced_by(rel)))

    total = len(owners)
    print(f"契約に登録済みの資産: {total} 件 / 未登録の UI ファイル: {len(unregistered)} 件")
    print()
    if not unregistered:
        print("未登録なし。全 UI ファイルがいずれかの機能アセットとして渡せる。")
        return 0
    print(f"{'bytes':>8}  ファイル")
    print(f"{'':>8}  └ 参照元（この数が多いものは機能資産ではなく共通基盤の可能性が高い）")
    for size, rel, refs in sorted(unregistered, reverse=True):
        print(f"{size:8}  {rel}")
        shown = ", ".join(refs[:4]) + (f" ほか{len(refs) - 4}件" if len(refs) > 4 else "")
        print(f"{'':>8}  └ {shown or '参照元を検出できず'}")
    print()
    print("対処: 機能に属するものは quality/feature_contracts.yml の ui_files へ登録する。")
    print("      複数機能から参照される共通基盤は、機能アセットとは別に受け側へ先に渡す。")
    return 1


def _referenced_by(rel: str) -> list[str]:
    """このファイルを参照しているテンプレートを探す。"""
    if not rel.startswith("static/"):
        return []
    needle = rel.split("static/", 1)[1]
    hits: list[str] = []
    templates_root = ROOT / "templates"
    if not templates_root.is_dir():
        return hits
    for path in sorted(templates_root.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if needle in RE_TPL_STATIC.findall(text):
            hits.append(str(path.relative_to(ROOT)))
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="機能単位アセットを他環境へ渡すためのバンドルを生成する。"
    )
    parser.add_argument("feature_id", nargs="?", help="quality/feature_contracts.yml の feature_id")
    parser.add_argument("--list", action="store_true", help="エクスポート可能な機能を一覧する")
    parser.add_argument("--all", action="store_true", help="全機能をエクスポートする")
    parser.add_argument(
        "--audit",
        action="store_true",
        help="どの機能契約にも属していない UI ファイルを洗い出す（渡す前の点検）",
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT), help=f"出力先（既定: {DEFAULT_OUT}）")
    parser.add_argument("--version", default=None, help="版（既定: YYYYMMDD-<short sha>）")
    parser.add_argument("--with-tests", action="store_true", help="required_tests のファイルも同梱する")
    parser.add_argument("--with-docs", action="store_true", help="feature_id に言及する docs/ を同梱する")
    parser.add_argument("--no-archive", action="store_true", help="tar.gz を作らない")
    args = parser.parse_args(argv)

    features = load_contracts()
    if args.list:
        return cmd_list(features)
    if args.audit:
        return cmd_audit(features)
    if not args.feature_id and not args.all:
        parser.error("feature_id か --all か --list か --audit のいずれかが要る")

    version = args.version or f"{datetime.now().strftime('%Y%m%d')}-{git_revision()}"
    out_root = Path(args.out)
    if not out_root.is_absolute():
        out_root = ROOT / out_root

    targets = features if args.all else [find_feature(features, args.feature_id)]
    exit_code = 0
    for feature in targets:
        try:
            bundle = export(
                feature,
                version,
                out_root,
                with_tests=args.with_tests,
                with_docs=args.with_docs,
                archive=not args.no_archive,
            )
        except SystemExit as exc:
            print(f"[SKIP] {feature['feature_id']}: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        mark = "!" if manifest["warnings"] else " "
        print(
            f"[OK]{mark} {feature['feature_id']:34} "
            f"{len(manifest['files']):3} files  警告 {len(manifest['warnings'])}  "
            f"-> {bundle.relative_to(ROOT)}"
        )
        for warning in manifest["warnings"]:
            print(f"      警告: {warning}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
