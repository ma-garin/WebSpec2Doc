"""欠陥から修正候補ファイルを推定するモジュール。

4 種類の根拠（traceback・import・recent-change・test-name）で
ファイルをスコアリングし、スコア降順で返す。
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from web.services.healing.types import Defect

# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LocationEvidence:
    """推定ファイル 1 件の根拠と信頼度。"""

    path: str  # リポジトリルートからの相対パス
    reason: str  # "traceback" | "import" | "recent-change" | "test-name"
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
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


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
    """git log から直近 20 commit で変更されたファイルを抽出。"""
    try:
        result = subprocess.run(
            ["git", "log", "-n", "20", "--name-only", "--pretty=format:"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
        if result.returncode != 0:
            return []
        return [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip() and line.endswith(".py")
        ]
    except Exception:
        return []


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
            if (
                re.search(rf"^\s*(def|class)\s+{re.escape(name)}\s*[\(\:]", content, re.MULTILINE)
            ):
                results.append(str(py_file.relative_to(repo)))
        except Exception:
            pass
        count += 1
    return results


def _build_scores(
    defect: Defect, repo: Path
) -> dict[str, dict[str, float | list[str]]]:
    """4 種類の根拠からスコア辞書を構築。"""
    scores: dict[str, dict[str, float | list[str]]] = {}

    # 根拠1: traceback
    for path in _extract_paths_from_traceback(defect.evidence + defect.message):
        if path not in scores:
            scores[path] = {"score": 0.0, "reasons": []}
        scores[path]["score"] = max(scores[path]["score"], 0.9)  # type: ignore
        scores[path]["reasons"].append("traceback")  # type: ignore

    # 根拠2: import
    if defect.test_id:
        test_match = re.match(r"([^:]+\.py)", defect.test_id)
        if test_match and _is_test_file(test_match.group(1)):
            for path in _extract_imports_from_test(test_match.group(1), repo):
                if path not in scores:
                    scores[path] = {"score": 0.0, "reasons": []}
                scores[path]["score"] = max(scores[path]["score"], 0.7)  # type: ignore
                scores[path]["reasons"].append("import")  # type: ignore

    # 根拠3: recent-change
    for path in _get_recent_files(repo):
        if path not in scores:
            scores[path] = {"score": 0.0, "reasons": []}
        scores[path]["score"] = max(scores[path]["score"], 0.5)  # type: ignore
        scores[path]["reasons"].append("recent-change")  # type: ignore

    # 根拠4: test-name
    source_name = _guess_source_from_test_id(defect.test_id)
    if source_name:
        for path in _search_by_name(repo, source_name, limit=500):
            if path not in scores:
                scores[path] = {"score": 0.0, "reasons": []}
            scores[path]["score"] = max(scores[path]["score"], 0.6)  # type: ignore
            scores[path]["reasons"].append("test-name")  # type: ignore

    return scores


def _make_evidence(
    path: str, score_data: dict[str, float | list[str]]
) -> LocationEvidence:
    """スコア辞書から LocationEvidence を構築。"""
    score = min(float(score_data.get("score", 0.0)), 1.0)  # type: ignore
    reasons: list[str] = score_data.get("reasons", [])  # type: ignore
    primary = reasons[0] if reasons else "unknown"
    detail = " / ".join(dict.fromkeys(reasons)) if reasons else ""
    return LocationEvidence(path=path, reason=primary, score=score, detail=detail)


# ─────────────────────────────────────────────────────────────────────────
# 主エンドポイント
# ─────────────────────────────────────────────────────────────────────────


def locate(
    defect: Defect, *, repo: Path, limit: int = 5
) -> tuple[LocationEvidence, ...]:
    """欠陥から修正候補ファイルを推定する。

    Args:
        defect: 欠陥情報
        repo: リポジトリルートのパス
        limit: 返すファイルの最大数

    Returns:
        スコア降順のLocationEvidence タプル
    """
    scores = _build_scores(defect, repo)
    results = [_make_evidence(path, data) for path, data in scores.items()]
    results.sort(key=lambda e: (-e.score, e.path))
    return tuple(results[:limit])
