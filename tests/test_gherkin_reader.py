"""Gherkin要件取り込み（第8弾 G）の契約。

守るべきは「日英キーワード両対応」「@REQタグの要件ID保持」「Then節の期待結果化」
「非Gherkin文書への非干渉」。
"""

from __future__ import annotations

from ingest.gherkin_reader import is_gherkin, parse_gherkin

ENGLISH = """@REQ-LOGIN
Feature: Authentication
  Scenario: A user logs in
    Given the user is on the login page
    When they submit valid credentials
    Then the dashboard is shown
"""

JAPANESE = """機能: 宿泊予約
  シナリオ: プランを検索する
    前提 トップページにいる
    もし キーワードを入れて検索する
    ならば プラン一覧が表示される
    かつ 件数が表示される
"""


# ─────────────────── 判定 ───────────────────


def test_feature_extension_is_gherkin() -> None:
    assert is_gherkin("anything", "requirements.feature") is True


def test_feature_keyword_is_gherkin() -> None:
    assert is_gherkin(JAPANESE, "req.txt") is True
    assert is_gherkin(ENGLISH, "req.txt") is True


def test_plain_markdown_is_not_gherkin() -> None:
    assert is_gherkin("# 要件一覧\n- ログインできる", "req.md") is False


# ─────────────────── 解析 ───────────────────


def test_english_scenario_becomes_requirement() -> None:
    reqs = parse_gherkin(ENGLISH)

    assert len(reqs) == 1
    assert reqs[0].req_id == "REQ-LOGIN"
    assert reqs[0].title == "A user logs in"


def test_japanese_scenario_becomes_requirement() -> None:
    reqs = parse_gherkin(JAPANESE)

    assert len(reqs) == 1
    assert reqs[0].title == "プランを検索する"


def test_req_tag_is_used_as_id() -> None:
    assert parse_gherkin(ENGLISH)[0].req_id == "REQ-LOGIN"


def test_untagged_scenario_gets_generated_id() -> None:
    assert parse_gherkin(JAPANESE)[0].req_id == "GH-001"


def test_then_clause_appears_in_description() -> None:
    reqs = parse_gherkin(ENGLISH)

    assert "期待結果" in reqs[0].description
    assert "dashboard is shown" in reqs[0].description


def test_and_clause_extends_previous_step() -> None:
    """かつ節が直前のステップ種別（ならば）に連なる。"""
    reqs = parse_gherkin(JAPANESE)

    assert "件数が表示される" in reqs[0].description


def test_multiple_scenarios_yield_multiple_requirements() -> None:
    text = """機能: 予約
  シナリオ: 検索する
    もし 検索する
    ならば 結果が出る
  シナリオ: 予約する
    もし 予約ボタンを押す
    ならば 確認画面が出る
"""
    reqs = parse_gherkin(text)

    assert [r.req_id for r in reqs] == ["GH-001", "GH-002"]


def test_comments_and_blank_lines_are_ignored() -> None:
    text = """# これはコメント
機能: X

  シナリオ: Y
    もし 何かする
    ならば 何か起きる
"""
    assert len(parse_gherkin(text)) == 1


def test_source_is_gherkin() -> None:
    assert parse_gherkin(ENGLISH)[0].source == "gherkin"
