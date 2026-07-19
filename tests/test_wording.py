"""文言一貫性チェックの契約。

守るべきは「辞書外を指摘しないこと」と「どちらが正しいかを決めつけないこと」。
"""

from __future__ import annotations

import json
from pathlib import Path

from wording.consistency import (
    CLAIM_NOTICE,
    DEFAULT_DICTIONARY,
    ISSUE_STYLE,
    ISSUE_SYNONYM,
    ISSUE_WIDTH,
    SynonymGroup,
    WordingDictionary,
    check_wording,
    load_dictionary,
    texts_from_pages,
)


def _issues(result: dict, kind: str) -> list[dict]:
    return [issue for issue in result["issues"] if issue["type"] == kind]


# ─────────────────── 同義語 ───────────────────


def test_mixed_synonyms_are_reported() -> None:
    texts = {
        "https://e.com/a": ["ログインしてください"],
        "https://e.com/b": ["サインインはこちら"],
    }

    issues = _issues(check_wording(texts), ISSUE_SYNONYM)

    assert issues[0]["terms"] == ["サインイン", "ログイン"]
    assert issues[0]["occurrences"]["ログイン"] == ["https://e.com/a"]


def test_single_term_used_consistently_is_not_reported() -> None:
    texts = {"https://e.com/a": ["ログイン"], "https://e.com/b": ["ログイン画面"]}

    assert _issues(check_wording(texts), ISSUE_SYNONYM) == []


def test_message_does_not_declare_a_correct_term() -> None:
    """正解を決めるのは組織であってツールではない。"""
    texts = {"a": ["ログイン"], "b": ["サインイン"]}

    message = _issues(check_wording(texts), ISSUE_SYNONYM)[0]["message"]

    assert "組織で決めてください" in message


def test_terms_outside_dictionary_are_not_reported() -> None:
    texts = {"a": ["取消"], "b": ["キャンセル"]}

    assert _issues(check_wording(texts), ISSUE_SYNONYM) == []


def test_custom_dictionary_extends_detection() -> None:
    dictionary = WordingDictionary(synonyms=(SynonymGroup(("取消", "キャンセル")),))
    texts = {"a": ["取消"], "b": ["キャンセル"]}

    assert len(_issues(check_wording(texts, dictionary), ISSUE_SYNONYM)) == 1


def test_ignored_terms_are_skipped() -> None:
    dictionary = WordingDictionary(
        synonyms=DEFAULT_DICTIONARY.synonyms, ignore_terms=frozenset({"サインイン"})
    )
    texts = {"a": ["ログイン"], "b": ["サインイン"]}

    assert _issues(check_wording(texts, dictionary), ISSUE_SYNONYM) == []


# ─────────────────── 全角半角 ───────────────────


def test_full_and_half_width_variants_are_reported() -> None:
    texts = {"a": ["ＩＤを入力"], "b": ["IDを入力"]}

    issues = _issues(check_wording(texts), ISSUE_WIDTH)

    assert issues[0]["normalized"] == "ID"
    assert sorted(issues[0]["variants"]) == ["ID", "ＩＤ"]


def test_consistent_width_is_not_reported() -> None:
    texts = {"a": ["IDを入力"], "b": ["IDを確認"]}

    assert _issues(check_wording(texts), ISSUE_WIDTH) == []


def test_width_check_can_be_disabled() -> None:
    dictionary = WordingDictionary(synonyms=(), check_width=False)
    texts = {"a": ["ＩＤ"], "b": ["ID"]}

    assert _issues(check_wording(texts, dictionary), ISSUE_WIDTH) == []


# ─────────────────── 敬体・常体 ───────────────────


def test_mixed_politeness_within_one_screen_is_reported() -> None:
    texts = {"https://e.com/a": ["ここに入力します。", "値は必須である。"]}

    issues = _issues(check_wording(texts), ISSUE_STYLE)

    assert issues[0]["page_url"] == "https://e.com/a"
    assert issues[0]["polite_sentences"] == 1
    assert issues[0]["plain_sentences"] == 1


def test_consistent_politeness_is_not_reported() -> None:
    texts = {"a": ["ここに入力します。", "値は必須です。"]}

    assert _issues(check_wording(texts), ISSUE_STYLE) == []


def test_mixing_across_different_screens_is_not_reported() -> None:
    """画面ごとに文体を変える設計はあり得るため、画面をまたぐ混在は指摘しない。"""
    texts = {"a": ["入力します。"], "b": ["必須である。"]}

    assert _issues(check_wording(texts), ISSUE_STYLE) == []


def test_style_check_can_be_disabled() -> None:
    dictionary = WordingDictionary(synonyms=(), check_style=False)
    texts = {"a": ["入力します。", "必須である。"]}

    assert _issues(check_wording(texts, dictionary), ISSUE_STYLE) == []


# ─────────────────── 辞書の読み込み ───────────────────


def test_missing_dictionary_falls_back_to_default(tmp_path: Path) -> None:
    assert load_dictionary(tmp_path / "absent.json") == DEFAULT_DICTIONARY


def test_broken_dictionary_falls_back_to_default(tmp_path: Path) -> None:
    path = tmp_path / "d.json"
    path.write_text("{ broken", encoding="utf-8")

    assert load_dictionary(path) == DEFAULT_DICTIONARY


def test_custom_dictionary_is_loaded(tmp_path: Path) -> None:
    path = tmp_path / "d.json"
    path.write_text(
        json.dumps(
            {
                "synonyms": [{"terms": ["取消", "キャンセル"], "note": "破棄"}],
                "check_width": False,
                "ignore_terms": ["ID"],
            }
        ),
        encoding="utf-8",
    )

    dictionary = load_dictionary(path)

    assert dictionary.synonyms[0].terms == ("取消", "キャンセル")
    assert dictionary.check_width is False
    assert "ID" in dictionary.ignore_terms


def test_group_with_single_term_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "d.json"
    path.write_text(json.dumps({"synonyms": [{"terms": ["ログイン"]}]}), encoding="utf-8")

    assert load_dictionary(path).synonyms == DEFAULT_DICTIONARY.synonyms


# ─────────────────── 集計・主張境界 ───────────────────


def test_summary_counts_each_issue_type() -> None:
    texts = {
        "a": ["ログイン", "ＩＤ", "入力します。", "必須である。"],
        "b": ["サインイン", "ID"],
    }

    summary = check_wording(texts)["summary"]

    assert summary[ISSUE_SYNONYM] >= 1
    assert summary[ISSUE_WIDTH] >= 1
    assert summary[ISSUE_STYLE] >= 1
    assert summary["total"] == sum(
        summary[key] for key in (ISSUE_SYNONYM, ISSUE_WIDTH, ISSUE_STYLE)
    )


def test_claim_scope_is_declared() -> None:
    result = check_wording({})

    assert result["meta"]["claim_scope"] == "dictionary_matches_only"
    assert result["meta"]["claim_notice"] == CLAIM_NOTICE


def test_texts_are_collected_from_title_and_headings() -> None:
    class FakePage:
        url = "https://e.com/"
        title = "予約"
        headings = ("ご予約内容", "")

    assert texts_from_pages([FakePage()]) == {"https://e.com/": ["予約", "ご予約内容"]}
