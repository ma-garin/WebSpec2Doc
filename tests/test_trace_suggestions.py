"""TF-IDF突合候補（第8弾 D）の契約。

守るべきは「自動リンクしないこと」「決定性」「根拠語を添えること」
「閾値未満・候補ゼロを無理に出さないこと」。
"""

from __future__ import annotations

from mbt.trace_suggestions import (
    CLAIM_SCOPE,
    SUGGESTION_THRESHOLD,
    build_screen_corpus,
    suggest_matches,
    tokenize,
)


def _report() -> dict:
    return {
        "screens": [
            {
                "page_id": "P001",
                "title": "トップページ",
                "headings": ["ようこそ"],
                "buttons": ["ログイン"],
                "forms": [],
            },
            {
                "page_id": "P002",
                "title": "宿泊プラン検索",
                "headings": ["プランを探す"],
                "buttons": ["検索"],
                "forms": [{"fields": [{"name": "plan_keyword", "placeholder": "プラン名で検索"}]}],
            },
            {
                "page_id": "P003",
                "title": "予約確認",
                "headings": ["ご予約内容"],
                "buttons": ["確定"],
                "forms": [],
            },
        ]
    }


# ─────────────────── トークン化 ───────────────────


def test_english_words_and_japanese_bigrams() -> None:
    tokens = tokenize("Login 検索")

    assert "login" in tokens
    assert "検索" in tokens


def test_corpus_collects_titles_headings_buttons_fields() -> None:
    corpus = build_screen_corpus(_report())

    assert set(corpus) == {"P001", "P002", "P003"}
    assert any("プラ" in t or "プラン" in t for t in corpus["P002"])


# ─────────────────── 候補提示 ───────────────────


def test_japanese_requirement_matches_relevant_screen_top() -> None:
    unmatched = [{"req_id": "REQ-01", "title": "宿泊プランを検索できる"}]

    result = suggest_matches(unmatched, _report())

    candidates = result[0]["candidates"]
    assert candidates, "候補が出るべき"
    assert candidates[0]["page_id"] == "P002"  # プラン検索画面が最上位


def test_candidates_carry_matched_terms() -> None:
    unmatched = [{"req_id": "REQ-01", "title": "プラン検索"}]

    result = suggest_matches(unmatched, _report())

    assert result[0]["candidates"][0]["matched_terms"]


def test_generation_is_deterministic() -> None:
    unmatched = [{"req_id": "REQ-01", "title": "予約を確認する"}]

    assert suggest_matches(unmatched, _report()) == suggest_matches(unmatched, _report())


def test_below_threshold_candidates_are_omitted() -> None:
    unmatched = [{"req_id": "REQ-99", "title": "zzz全く無関係xyz"}]

    result = suggest_matches(unmatched, _report())

    assert all(c["score"] >= SUGGESTION_THRESHOLD for c in result[0]["candidates"])


def test_empty_corpus_yields_empty_candidates() -> None:
    result = suggest_matches([{"req_id": "REQ-01", "title": "x"}], {"screens": []})

    assert result[0]["candidates"] == []


def test_claim_scope_is_declared() -> None:
    result = suggest_matches([{"req_id": "REQ-01", "title": "予約"}], _report())

    assert result[0]["claim_scope"] == CLAIM_SCOPE
    assert CLAIM_SCOPE == "textual_similarity_candidates_only"


def test_scores_are_bounded_0_to_1() -> None:
    result = suggest_matches([{"req_id": "REQ-01", "title": "宿泊プラン検索"}], _report())

    for candidate in result[0]["candidates"]:
        assert 0.0 <= candidate["score"] <= 1.0
