"""TF-IDF類似による要件↔画面の突合候補提示（LLM不要・決定的）。

ルールベースの完全一致で「対応画面なし」となった要件に、テキスト類似度で候補を
提示する。トレーサビリティ研究の20年来のベースライン（Antoniol et al., TSE 2002
のベクトル空間モデル）を、標準ライブラリのみで実装したもの。

**自動リンクは絶対にしない**（phantom links 対策。確定は人のみ）。候補には根拠語
（matched_terms）を必ず添え、なぜその候補かを人が検証できるようにする。

主張境界: テキスト類似度に基づく候補であり、正しい対応であることは主張しない。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

CLAIM_SCOPE = "textual_similarity_candidates_only"
SUGGESTION_THRESHOLD = 0.15  # これ未満は候補に出さない（雑音抑制）
TOP_K = 3

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]+")
_CJK_RE = re.compile(r"[぀-ヿ一-鿿ｦ-ﾟ]")


def tokenize(text: str) -> list[str]:
    """英数字は小文字の単語、日本語（CJK）は文字bigramへ。決定的。"""
    lowered = str(text).lower()
    tokens = list(_WORD_RE.findall(lowered))
    cjk = "".join(_CJK_RE.findall(lowered))
    tokens.extend(cjk[i : i + 2] for i in range(len(cjk) - 1))
    return tokens


def build_screen_corpus(report: dict[str, Any]) -> dict[str, list[str]]:
    """page_id -> トークン列。title/headings/フィールド属性/ボタン文言を集める。"""
    corpus: dict[str, list[str]] = {}
    for screen in report.get("screens", []):
        if not isinstance(screen, dict):
            continue
        page_id = str(screen.get("page_id", ""))
        if not page_id:
            continue
        texts: list[str] = [str(screen.get("title", ""))]
        texts.extend(str(h) for h in screen.get("headings", []))
        texts.extend(str(b) for b in screen.get("buttons", []))
        for form in screen.get("forms", []):
            if not isinstance(form, dict):
                continue
            for field in form.get("fields", []):
                if not isinstance(field, dict):
                    continue
                texts.extend(
                    str(field.get(key, ""))
                    for key in ("name", "placeholder", "aria_label", "label")
                )
        tokens: list[str] = []
        for text in texts:
            tokens.extend(tokenize(text))
        corpus[page_id] = tokens
    return corpus


def suggest_matches(
    unmatched_requirements: list[dict[str, Any]], report: dict[str, Any]
) -> list[dict[str, Any]]:
    """各未突合要件へ TF-IDF cosine 上位 TOP_K の画面候補を返す。"""
    corpus = build_screen_corpus(report)
    if not corpus:
        return [
            {"req_id": str(req.get("req_id", "")), "candidates": []}
            for req in unmatched_requirements
        ]

    idf = _compute_idf(corpus)
    screen_vectors = {pid: _tfidf_vector(tokens, idf) for pid, tokens in corpus.items()}

    suggestions: list[dict[str, Any]] = []
    for req in unmatched_requirements:
        req_text = f"{req.get('title', '')} {req.get('req_id', '')}"
        req_tokens = tokenize(req_text)
        req_vector = _tfidf_vector(req_tokens, idf)

        scored: list[tuple[float, str, list[str]]] = []
        for page_id in sorted(screen_vectors):
            score = _cosine(req_vector, screen_vectors[page_id])
            if score >= SUGGESTION_THRESHOLD:
                matched = _matched_terms(req_vector, screen_vectors[page_id])
                scored.append((score, page_id, matched))
        scored.sort(key=lambda item: (-item[0], item[1]))

        suggestions.append(
            {
                "req_id": str(req.get("req_id", "")),
                "title": str(req.get("title", "")),
                "candidates": [
                    {
                        "page_id": page_id,
                        "score": round(score, 3),
                        "matched_terms": matched,
                    }
                    for score, page_id, matched in scored[:TOP_K]
                ],
                "claim_scope": CLAIM_SCOPE,
            }
        )
    return suggestions


# ─────────────────── TF-IDF ───────────────────


def _compute_idf(corpus: dict[str, list[str]]) -> dict[str, float]:
    document_count = len(corpus)
    doc_freq: Counter[str] = Counter()
    for tokens in corpus.values():
        for term in set(tokens):
            doc_freq[term] += 1
    return {
        term: math.log((1 + document_count) / (1 + freq)) + 1.0 for term, freq in doc_freq.items()
    }


def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    if not tokens:
        return {}
    tf = Counter(tokens)
    total = len(tokens)
    return {term: (count / total) * idf.get(term, 0.0) for term, count in tf.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[term] * b[term] for term in common)
    norm_a = math.sqrt(sum(value * value for value in a.values()))
    norm_b = math.sqrt(sum(value * value for value in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _matched_terms(a: dict[str, float], b: dict[str, float], top: int = 5) -> list[str]:
    common = set(a) & set(b)
    ranked = sorted(common, key=lambda term: (-(a[term] * b[term]), term))
    # bigram（日本語）は読みにくいので単語を優先しつつ上位を返す
    return ranked[:top]
