"""欠陥から修正候補ファイルを推定するモジュール。

7 種類の根拠でファイルをスコアリングし、スコア降順で返す。

Python の例外から辿る 4 種（traceback・import・recent-change・test-name）は、
スタックトレースが製品コードを指すことを前提にしている。
E2E の失敗にはそれが無い。Playwright が残すのは
「どの画面の・どのセレクタが・見つからなかったか」だけで、
製品コードのファイル名は 1 つも出てこない。

そこで画面側から辿る 3 種を足した。

- selector … テストが探した文言・test-id を、製品コードの中から探す
- route ……… 失敗した URL を、ルート定義とそれが描くテンプレートに結びつける
- screen …… 01 が作った画面仕様の見出し・ボタン名を手がかりにする

この 3 種が無いと、E2E 起点の修正で「直すべきファイル」を 1 つも出せない。
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from web.services.healing.types import Defect

# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LocationEvidence:
    """推定ファイル 1 件の根拠と信頼度。"""

    path: str  # リポジトリルートからの相対パス
    #: "traceback" | "import" | "recent-change" | "test-name"
    #: | "selector" | "route" | "screen"
    reason: str
    score: float  # 0.0-1.0
    detail: str = ""  # 人が読む根拠説明（日本語）


# ─────────────────────────────────────────────────────────────────────────
# 内部ヘルパー
# ─────────────────────────────────────────────────────────────────────────


def _is_test_file(path: str) -> bool:
    """テストファイルかどうか判定する。

    ディレクトリ名では判定しない。tests/ 配下に置かれた製品コードを
    テスト扱いすると、修正候補から誤って除外される（risk.py と同じ規則）。
    """
    name = Path(path).name
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def _normalize_path(path: str) -> str | None:
    """推定ファイルパスを正規化し、存在確認。None なら存在しない。"""
    p = Path(path).with_suffix(".py") if not path.endswith(".py") else Path(path)
    if p.exists():
        try:
            return str(p.relative_to(p.cwd() if p.is_absolute() else Path.cwd()))
        except ValueError:
            return str(p)
    return None


def _extract_paths_from_traceback(text: str) -> list[str]:
    """evidence/message から File "xxx.py" と path/to/file.py:N を抽出。"""
    paths = []
    # 形式1: File "path/to/file.py", line NNN
    for match in re.finditer(r'File "([^"]+\.py)"', text):
        paths.append(match.group(1))
    # 形式2: /path/to/file.py:NNN
    for match in re.finditer(r"([^\s]+\.py):\d+", text):
        paths.append(match.group(1))
    return [p for p in paths if p and not _is_test_file(p)]


def _extract_imports_from_test(test_file: str, repo: Path) -> list[str]:
    """test_file から import を抽出し、リポジトリ内で解決する。"""
    try:
        content = (repo / test_file).read_text(encoding="utf-8")
    except Exception:
        return []

    results = []
    # from x.y import z
    for match in re.finditer(r"from\s+([\w.]+)\s+import", content):
        module = match.group(1)
        module_path = module.replace(".", "/") + ".py"
        if (repo / module_path).exists():
            results.append(module_path)
    # import x.y.z
    for match in re.finditer(r"import\s+([\w.]+)", content):
        module = match.group(1).split(".")[0]
        module_path = module + ".py"
        if (repo / module_path).exists():
            results.append(module_path)
    return results


def _get_recent_files(repo: Path) -> list[str]:
    """直近 20 commit で変更された .py ファイルを抽出（dulwich。git コマンドは使わない）。"""
    from web.services.healing import git_ops

    return [name for name in git_ops.recent_changed_files(repo, 20) if name.endswith(".py")]


def _guess_source_from_test_id(test_id: str) -> str | None:
    """test_id から対象関数・クラス名を推測（例: test_add -> add）。"""
    # 形式: path/to/test_file.py::test_function
    match = re.search(r"::test_(\w+)(?:\[|$)", test_id)
    if match:
        return match.group(1)
    return None


# 走査から外すディレクトリ。仮想環境や依存パッケージを候補に出すと
# 「直すべきファイル」の一覧が実質使い物にならなくなる。
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        "venv",
        ".venv",
        "node_modules",
        ".git",
        "__pycache__",
        "site-packages",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "output",
    }
)


def _is_scannable(rel_path: str) -> bool:
    """走査対象か。仮想環境・依存パッケージ・生成物は対象外。"""
    return not any(part in _SKIP_DIRS for part in Path(rel_path).parts)


def _search_by_name(repo: Path, name: str, limit: int = 500) -> list[str]:
    """リポジトリ内で def/class name を検索。最大 limit ファイルまで。"""
    results = []
    count = 0
    for py_file in repo.rglob("*.py"):
        if count >= limit:
            break
        rel = str(py_file.relative_to(repo))
        if not _is_scannable(rel):
            continue
        if _is_test_file(rel):
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
            # def name( / class Name(
            if re.search(rf"^\s*(def|class)\s+{re.escape(name)}\s*[\(\:]", content, re.MULTILINE):
                results.append(str(py_file.relative_to(repo)))
        except Exception:
            pass
        count += 1
    return results


# ─────────────────────────────────────────────────────────────────────────
# 画面から辿る根拠（selector / route / screen）
#
# Python の例外を持たない E2E の失敗に効く。走査は「テキストを含むか」の
# 単純一致で済ませる。構文解析に踏み込むと言語ごとの実装が要るうえ、
# 候補を 5 件に絞る用途には精度が足りて余る。
# ─────────────────────────────────────────────────────────────────────────

#: 走査対象の拡張子。画面の文言が書かれうる場所。
_UI_SUFFIXES: tuple[str, ...] = (
    ".html",
    ".jinja",
    ".jinja2",
    ".tsx",
    ".jsx",
    ".vue",
    ".py",
    ".js",
    ".ts",
)
#: 1 回の限局で開くファイル数の上限。
_MAX_SCAN_FILES = 2000
#: 1 ファイルの上限。これを超えるものはビルド生成物とみなして読まない。
_MAX_FILE_BYTES = 512 * 1024
#: 1 欠陥あたりの打ち切り時間。超えたら、そこまでの結果を返す。
_LOCATE_BUDGET_SEC = 10.0

#: セレクタの抽出規則。(正規表現, スコア)。
#: test-id と id は文言より一意なので高く見る。
_SELECTOR_PATTERNS: tuple[tuple[re.Pattern[str], float], ...] = (
    (re.compile(r"""getByRole\(\s*['"][^'"]+['"]\s*,\s*\{\s*name:\s*['"]([^'"]+)['"]"""), 0.6),
    (re.compile(r"""getBy(?:Text|Label|Placeholder|AltText|Title)\(\s*['"]([^'"]+)['"]"""), 0.6),
    (re.compile(r"""getByTestId\(\s*['"]([^'"]+)['"]"""), 0.8),
    (re.compile(r"""locator\(\s*['"](#[\w-]+|\[data-testid=[^\]]+\])['"]"""), 0.8),
)

#: Flask / FastAPI 系のルート定義。デコレータ 1 行を見るだけで、
#: route だけでなく get / post などのメソッド別の書き方にも当たる。
_ROUTE_DEF_RE = re.compile(r"""@\w+\.(?:route|get|post|put|patch|delete)\(\s*['"]([^'"]+)['"]""")
#: Django の urls.py。
_DJANGO_PATH_RE = re.compile(r"""\bpath\(\s*['"]([^'"]*)['"]\s*,\s*([\w.]+)""")
#: Express 系。app.get("/x", …) / router.post("/x", …)。
_EXPRESS_ROUTE_RE = re.compile(r"""\.(?:get|post|put|delete|patch)\(\s*['"](/[^'"]*)['"]""")
_RENDER_TEMPLATE_RE = re.compile(r"""render_template\(\s*['"]([^'"]+)['"]""")
_DEF_NAME_RE = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)", re.MULTILINE)

#: URL のうち、可変とみなすセグメント（連番・UUID・ハッシュ）。
_VAR_SEGMENT_RE = re.compile(
    r"^(?:\d+"
    r"|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|[0-9a-fA-F]{12,})$"
)


def _load_json(path: Path) -> dict[str, Any] | None:
    """壊れた JSON で限局を落とさない。読めなければ None。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _needle_variants(raw: str) -> list[str]:
    """セレクタから、製品コードの中を探すときの検索語を作る。

    `#hl-start` や `[data-testid="save"]` はセレクタの書き方であって、
    ソースにその形では書かれていない。中身の識別子だけを取り出す。
    """
    text = raw.strip()
    if text.startswith("#"):
        text = text[1:]
    elif text.startswith("["):
        inner = re.search(r"=\s*['\"]?([^'\"\]]+)", text)
        text = inner.group(1) if inner else ""
    text = text.strip()
    return [text] if 2 <= len(text) <= 120 else []


def _extract_selector_needles(text: str) -> list[tuple[str, float, str]]:
    """失敗メッセージから (検索語, スコア, 人が読む表示) を取り出す。"""
    found: dict[str, tuple[float, str]] = {}
    for pattern, score in _SELECTOR_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(1)
            for needle in _needle_variants(raw):
                current = found.get(needle)
                if current is None or score > current[0]:
                    found[needle] = (score, raw.strip())
    ranked = sorted(found.items(), key=lambda kv: (-kv[1][0], kv[0]))
    return [(needle, score, label) for needle, (score, label) in ranked[:8]]


def _scan_for_needles(
    repo: Path,
    needles: Sequence[tuple[str, float, str]],
    *,
    deadline: float,
) -> dict[str, tuple[float, str]]:
    """検索語を含むファイルを探す。返すのは 相対パス -> (スコア, 表示)。"""
    hits: dict[str, tuple[float, str]] = {}
    if not needles:
        return hits
    opened = 0
    for suffix in _UI_SUFFIXES:
        for path in repo.rglob(f"*{suffix}"):
            if opened >= _MAX_SCAN_FILES or time.monotonic() > deadline:
                return hits
            try:
                rel = str(path.relative_to(repo))
            except ValueError:
                continue
            if not _is_scannable(rel) or _is_test_file(rel):
                continue
            try:
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            opened += 1
            for needle, score, label in needles:
                if needle not in content:
                    continue
                current = hits.get(rel)
                if current is None or score > current[0]:
                    hits[rel] = (score, label)
    return hits


def _url_path(url: str) -> str:
    """URL から path を取り、可変セグメントを <var> に潰す。"""
    try:
        path = urlparse(url).path or "/"
    except ValueError:
        return ""
    parts = [("<var>" if _VAR_SEGMENT_RE.match(p) else p) for p in path.split("/")]
    return "/".join(parts) or "/"


def _route_matches(route: str, url_path: str) -> bool:
    """ルート定義が URL の path に当たるか。可変部分は互いに素通しする。

    可変セグメントだけで構成されたルート（@app.route("/<page>") のような
    catch-all）は当たったことにしない。あらゆる URL に一致してしまい、
    「どこを直すか」の手がかりにならないため（2026-09-06 実測で、
    デモサイトが /healing の根拠として出た）。
    """
    route_parts = [p for p in route.split("/") if p]
    url_parts = [p for p in url_path.split("/") if p]
    if len(route_parts) != len(url_parts):
        return False
    static_matches = 0
    for route_part, url_part in zip(route_parts, url_parts, strict=False):
        if route_part[:1] in ("<", ":", "{") or url_part == "<var>":
            continue
        if route_part != url_part:
            return False
        static_matches += 1
    return static_matches > 0


def _templates_after(content: str, start: int) -> list[str]:
    """ルート定義の直後の関数本体から render_template の引数を拾う。"""
    tail = content[start : start + 4000]
    # 次のデコレータまでが、このルートの関数。
    next_decorator = tail.find("\n@")
    if next_decorator > 0:
        tail = tail[:next_decorator]
    return [m.group(1) for m in _RENDER_TEMPLATE_RE.finditer(tail)]


def _resolve_template(repo: Path, route_file: Path, template: str) -> str:
    """render_template の引数を、実在するテンプレートファイルに解決する。

    テンプレートフォルダはルート定義のあるパッケージ側が優先。
    リポジトリ直下の templates/ に決め打ちすると、同名のテンプレートを
    持つ別アプリのファイルを掴む（2026-09-06 実測）。
    """
    candidates: list[Path] = []
    for parent in list(route_file.parents):
        candidate = parent / "templates" / template
        if candidate not in candidates:
            candidates.append(candidate)
    for candidate in candidates:
        if (repo / candidate).is_file():
            return str(candidate)
    return ""


def _route_hits(repo: Path, url: str, *, deadline: float) -> dict[str, tuple[float, str]]:
    """失敗した URL から、ルート定義とそれが描くテンプレートを引く。"""
    hits: dict[str, tuple[float, str]] = {}
    url_path = _url_path(url)
    if not url_path or url_path == "/":
        # ルートパスは全ルートに当たりうるので、根拠として弱すぎる。
        return hits

    # Next.js は URL とファイル配置が対応するので、走査せずに直接当てる。
    segments = [p for p in url_path.split("/") if p]
    for base in ("app", "src/app"):
        for ext in ("tsx", "jsx", "ts", "js"):
            candidate = Path(base, *segments, f"page.{ext}")
            if (repo / candidate).is_file():
                hits[str(candidate)] = (0.85, f"URL {url_path} の画面ファイル")
    for base in ("pages", "src/pages"):
        for ext in ("tsx", "jsx", "ts", "js"):
            candidate = Path(base, *segments).with_suffix(f".{ext}")
            if (repo / candidate).is_file():
                hits[str(candidate)] = (0.85, f"URL {url_path} の画面ファイル")

    for suffix in (".py", ".js", ".ts"):
        for path in repo.rglob(f"*{suffix}"):
            if time.monotonic() > deadline:
                return hits
            try:
                rel = str(path.relative_to(repo))
            except ValueError:
                continue
            if not _is_scannable(rel) or _is_test_file(rel):
                continue
            try:
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            matched: list[tuple[str, int]] = []
            for match in _ROUTE_DEF_RE.finditer(content):
                if _route_matches(match.group(1), url_path):
                    matched.append((match.group(1), match.end()))
            if suffix == ".py":
                for match in _DJANGO_PATH_RE.finditer(content):
                    route = "/" + match.group(1)
                    if _route_matches(route, url_path):
                        matched.append((route, match.end()))
            else:
                for match in _EXPRESS_ROUTE_RE.finditer(content):
                    if _route_matches(match.group(1), url_path):
                        matched.append((match.group(1), match.end()))
            if not matched:
                continue

            for _route, end in matched:
                name_match = _DEF_NAME_RE.search(content, end)
                handler = name_match.group(1) if name_match else ""
                detail = f"URL {url_path} のルート"
                if handler:
                    detail = f"{detail} → {handler}()"
                current = hits.get(rel)
                if current is None or 0.7 > current[0]:
                    hits[rel] = (0.7, detail)
                for template in _templates_after(content, end):
                    template_rel = _resolve_template(repo, Path(rel), template)
                    if not template_rel:
                        continue
                    hits[template_rel] = (
                        0.85,
                        f"URL {url_path} のルートが描く画面",
                    )
    return hits


def _screen_needles(
    out_dir: Path | None, domain: str, screen_id: str
) -> list[tuple[str, float, str]]:
    """01 が作った画面仕様から、その画面にある文言を検索語として取り出す。"""
    if out_dir is None or not domain or not screen_id:
        return []
    data = _load_json(Path(out_dir) / domain / "report.json")
    if data is None:
        return []
    for screen in data.get("screens") or []:
        if not isinstance(screen, Mapping):
            continue
        if str(screen.get("page_id") or "") != screen_id:
            continue
        texts: list[str] = []
        for key in ("buttons", "headings"):
            for value in screen.get(key) or []:
                text = str(value).strip()
                # 「実装」「受付」のような 2〜3 文字の語は、どのファイルにも
                # 出てくるため候補を汚す。画面仕様は根拠として最も弱い
                # （0.5）ので、当たりの精度を長さで担保する。
                if 4 <= len(text) <= 60:
                    texts.append(text)
        seen: dict[str, None] = {}
        for text in texts:
            seen.setdefault(text, None)
        return [(text, 0.5, text) for text in list(seen)[:12]]
    return []


def _add_score(
    scores: dict[str, dict[str, Any]],
    path: str,
    score: float,
    reason: str,
    detail: str = "",
) -> None:
    """1 ファイルに根拠を 1 つ足す。スコアは最も強い根拠を採る。"""
    entry = scores.setdefault(path, {"score": 0.0, "reasons": [], "details": [], "top_reason": ""})
    if score > float(entry["score"]) or not entry["top_reason"]:
        entry["top_reason"] = reason
    entry["score"] = max(float(entry["score"]), score)
    entry["reasons"].append(reason)
    if detail and detail not in entry["details"]:
        entry["details"].append(detail)


def _build_scores(
    defect: Defect,
    repo: Path,
    *,
    project: Any = None,
    out_dir: Path | None = None,
    deadline: float | None = None,
) -> dict[str, dict[str, Any]]:
    """7 種類の根拠からスコア辞書を構築。"""
    scores: dict[str, dict[str, Any]] = {}
    if deadline is None:
        deadline = time.monotonic() + _LOCATE_BUDGET_SEC

    # 根拠1: traceback
    for path in _extract_paths_from_traceback(defect.evidence + defect.message):
        _add_score(scores, path, 0.9, "traceback", "実行時トレースに出ています")

    # 根拠2: import
    if defect.test_id:
        test_match = re.match(r"([^:]+\.py)", defect.test_id)
        if test_match and _is_test_file(test_match.group(1)):
            for path in _extract_imports_from_test(test_match.group(1), repo):
                _add_score(scores, path, 0.7, "import", "失敗したテストが import しています")

    # 根拠3: recent-change
    for path in _get_recent_files(repo):
        _add_score(scores, path, 0.5, "recent-change", "直近の変更に含まれています")

    # 根拠4: test-name
    source_name = _guess_source_from_test_id(defect.test_id)
    if source_name:
        for path in _search_by_name(repo, source_name, limit=500):
            _add_score(
                scores, path, 0.6, "test-name", f"テスト名が指す {source_name} を定義しています"
            )

    # 根拠5・7: セレクタと画面仕様の文言。走査が同じなので 1 回にまとめる。
    # E2E の失敗にはトレースが無く、ここが唯一の手がかりになる。
    domain = str(getattr(project, "domain", "") or "")
    selector_needles = _extract_selector_needles(f"{defect.message}\n{defect.evidence}")
    screen_needles = _screen_needles(out_dir, domain, defect.screen_id)
    selector_keys = {needle for needle, _, _ in selector_needles}
    merged = selector_needles + [n for n in screen_needles if n[0] not in selector_keys]
    if merged and time.monotonic() < deadline:
        screen_keys = {needle for needle, _, _ in screen_needles}
        for path, (score, label) in _scan_for_needles(repo, merged, deadline=deadline).items():
            if label in screen_keys and label not in selector_keys:
                _add_score(
                    scores,
                    path,
                    score,
                    "screen",
                    f"画面仕様 {defect.screen_id} の「{label}」を含みます",
                )
            else:
                _add_score(scores, path, score, "selector", f"文言「{label}」を含みます")

    # 根拠6: route
    if defect.url and time.monotonic() < deadline:
        for path, (score, detail) in _route_hits(repo, defect.url, deadline=deadline).items():
            _add_score(scores, path, score, "route", detail)

    return scores


def _make_evidence(path: str, score_data: dict[str, Any]) -> LocationEvidence:
    """スコア辞書から LocationEvidence を構築。

    detail は人が読む説明を優先する。根拠コードの羅列（traceback / import）は
    そのまま画面と PR 本文に出るため、説明が 1 つでもあればそちらを使う。
    """
    score = min(float(score_data.get("score", 0.0)), 1.0)
    reasons: list[str] = list(score_data.get("reasons", []))
    details: list[str] = list(score_data.get("details", []))
    # 最も強い根拠を出す。最初に足した根拠を出すと、弱い recent-change が
    # ルート定義や文言一致を押しのけて表示される。
    primary = str(score_data.get("top_reason") or "") or (reasons[0] if reasons else "unknown")
    if details:
        detail = " / ".join(dict.fromkeys(details))
    else:
        detail = " / ".join(dict.fromkeys(reasons)) if reasons else ""
    return LocationEvidence(path=path, reason=primary, score=score, detail=detail)


# ─────────────────────────────────────────────────────────────────────────
# 主エンドポイント
# ─────────────────────────────────────────────────────────────────────────


def locate(
    defect: Defect,
    *,
    repo: Path,
    limit: int = 5,
    project: Any = None,
    out_dir: Path | None = None,
) -> tuple[LocationEvidence, ...]:
    """欠陥から修正候補ファイルを推定する。

    Args:
        defect: 欠陥情報
        repo: リポジトリルートのパス
        limit: 返すファイルの最大数
        project: 接続先。domain があれば画面仕様を手がかりに使う
        out_dir: 出力ルート。画面仕様 report.json をここから読む

    Returns:
        スコア降順の LocationEvidence タプル。

    走査は 1 欠陥あたり 10 秒で打ち切り、そこまでの結果を返す。
    候補を 5 件に絞るのが目的で、全部見終えることではない。
    """
    deadline = time.monotonic() + _LOCATE_BUDGET_SEC
    scores = _build_scores(defect, repo, project=project, out_dir=out_dir, deadline=deadline)
    results = [_make_evidence(path, data) for path, data in scores.items()]
    results.sort(key=lambda e: (-e.score, e.path))
    return tuple(results[:limit])
