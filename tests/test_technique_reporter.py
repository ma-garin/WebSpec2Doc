"""technique_reporter のユニットテスト（技法エクスポート Markdown）。"""

from __future__ import annotations

from generator.technique_reporter import generate_techniques_markdown


def _screen(page_id: str, title: str, fields=None, to=None) -> dict:
    return {
        "page_id": page_id,
        "title": title,
        "url": f"https://example.com/{page_id}",
        "buttons": [],
        "forms": [{"action": "/s", "method": "post", "fields": list(fields or [])}]
        if fields
        else [],
        "transitions": {"to": list(to or []), "from": []},
    }


def _field(name: str, **kw) -> dict:
    base = {
        "name": name,
        "field_type": "text",
        "required": False,
        "maxlength": None,
        "minlength": None,
        "min_value": "",
        "max_value": "",
        "pattern": "",
        "options": [],
    }
    base.update(kw)
    return base


def test_markdown_has_matrix_and_legend() -> None:
    screens = [_screen("P001", "ログイン", [_field("ID", required=True), _field("PW", required=True)])]
    md = generate_techniques_markdown(screens)
    assert "# テスト設計技法" in md
    assert "| 画面 |" in md  # マトリクス表ヘッダ
    assert "決定表" in md  # dt 技法略称が凡例/見出しに含まれる


def test_markdown_lists_per_screen_recommendation_and_stub() -> None:
    screens = [_screen("P001", "検索", [_field("年齢", field_type="number")], to=["P002"])]
    md = generate_techniques_markdown(screens)
    assert "P001" in md
    assert "境界値分析" in md  # number 型由来の bva 推奨
    assert "状態遷移テスト" in md  # 遷移先ありで st 推奨
    assert "テストケース雛形" in md


def test_markdown_recomputes_when_techniques_absent() -> None:
    # techniques キーが無い screen でも recommender で再計算する
    screens = [_screen("P001", "入力", [_field("メール", field_type="email")])]
    assert "techniques" not in screens[0]
    md = generate_techniques_markdown(screens)
    assert "同値分割" in md


def test_markdown_handles_screen_without_techniques() -> None:
    screens = [_screen("P001", "静的ページ")]
    md = generate_techniques_markdown(screens)
    assert "P001" in md
    assert "推奨技法なし" in md
