"""Gherkin（BDD）形式の要件取り込み。

boilerplate研究（統制記法で抽出精度が構造的に向上）の知見を、独自記法ではなく
BDD実務標準の Gherkin で実現する。顧客のBDD資産・人材とそのまま接続できる。

1シナリオ = 1要件として取り込む。Then 節は期待結果として手順書へ引き渡す。
日本語キーワード（機能/シナリオ/前提/もし/ならば）と英語の両方に対応する。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ingest.models import DocumentedRequirement

_FEATURE_KW = ("feature:", "機能:")
_SCENARIO_KW = ("scenario:", "scenario outline:", "シナリオ:", "シナリオアウトライン:")
_GIVEN_KW = ("given ", "前提 ", "前提")
_WHEN_KW = ("when ", "もし ", "もし")
_THEN_KW = ("then ", "ならば ", "ならば")
_AND_KW = ("and ", "but ", "かつ ", "しかし ", "かつ", "しかし")
_REQ_TAG_RE = re.compile(r"@(REQ-[A-Za-z0-9_\-]+)")


def is_gherkin(text: str, filename: str) -> bool:
    """.feature 拡張子、または Feature:/機能: 行を含めば Gherkin とみなす。"""
    if filename.lower().endswith(".feature"):
        return True
    for line in text.splitlines():
        stripped = line.strip().lower()
        if any(stripped.startswith(kw) for kw in _FEATURE_KW):
            return True
    return False


def parse_gherkin(text: str) -> list[DocumentedRequirement]:
    """Gherkin テキストを要件のリストへ変換する（1シナリオ=1要件）。"""
    requirements: list[DocumentedRequirement] = []
    pending_tags: list[str] = []
    current: dict[str, Any] | None = None
    counter = 0
    last_kind = ""

    def flush() -> None:
        nonlocal current
        if current is not None:
            requirements.append(_to_requirement(current))
        current = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lowered = line.lower()

        if line.startswith("@"):
            pending_tags.extend(_REQ_TAG_RE.findall(line))
            continue
        if any(lowered.startswith(kw) for kw in _FEATURE_KW):
            continue  # Feature 見出しは要件にしない
        if any(lowered.startswith(kw) for kw in _SCENARIO_KW):
            flush()
            counter += 1
            current = {
                "title": _strip_keyword(line, _SCENARIO_KW),
                "given": [],
                "when": [],
                "then": [],
                "tags": list(pending_tags),
                "index": counter,
            }
            pending_tags = []
            last_kind = ""
            continue
        if current is None:
            continue

        if any(lowered.startswith(kw) for kw in _GIVEN_KW):
            current["given"].append(_strip_keyword(line, _GIVEN_KW))
            last_kind = "given"
        elif any(lowered.startswith(kw) for kw in _WHEN_KW):
            current["when"].append(_strip_keyword(line, _WHEN_KW))
            last_kind = "when"
        elif any(lowered.startswith(kw) for kw in _THEN_KW):
            current["then"].append(_strip_keyword(line, _THEN_KW))
            last_kind = "then"
        elif any(lowered.startswith(kw) for kw in _AND_KW) and last_kind:
            current[last_kind].append(_strip_keyword(line, _AND_KW))

    flush()
    return requirements


def read_gherkin(path: Path) -> list[DocumentedRequirement]:
    return parse_gherkin(path.read_text(encoding="utf-8"))


# ─────────────────── 内部 ───────────────────


def _to_requirement(scenario: dict[str, Any]) -> DocumentedRequirement:
    tags = scenario["tags"]
    req_id = tags[0] if tags else f"GH-{scenario['index']:03d}"
    then_text = " / ".join(scenario["then"])
    description_parts = []
    if scenario["given"]:
        description_parts.append("前提: " + " / ".join(scenario["given"]))
    if scenario["when"]:
        description_parts.append("操作: " + " / ".join(scenario["when"]))
    if then_text:
        description_parts.append("期待結果: " + then_text)
    return DocumentedRequirement(
        req_id=req_id,
        title=str(scenario["title"]),
        description="。".join(description_parts),
        category="機能",
        source="gherkin",
    )


def _strip_keyword(line: str, keywords: tuple[str, ...]) -> str:
    lowered = line.lower()
    for kw in keywords:
        if lowered.startswith(kw):
            return line[len(kw) :].strip()
    return line.strip()
