"""画面間データ依存追跡（第9弾 I）の契約。

守るべきは「観測できた反映のみ提示」「短すぎる値の除外」「網羅を主張しないこと」。
"""

from __future__ import annotations

from crawler.data_flow import CLAIM_NOTICE, track_reflections


def _report(*screens) -> dict:
    return {"screens": list(screens)}


def _screen(page_id, title="", headings=(), inputs=()):
    return {
        "page_id": page_id,
        "title": title,
        "headings": list(headings),
        "buttons": [],
        "validation_observations": [
            {"field_name": name, "attempted_value": value} for name, value in inputs
        ],
    }


def test_value_input_on_one_screen_reflected_on_another() -> None:
    report = _report(
        _screen("P001", title="検索", inputs=[("keyword", "ホテル函館")]),
        _screen("P002", title="ホテル函館の検索結果"),
    )

    result = track_reflections(report)

    assert len(result["flows"]) == 1
    flow = result["flows"][0]
    assert flow["source_page"] == "P001"
    assert flow["sink_pages"] == ["P002"]


def test_no_reflection_yields_no_flow() -> None:
    report = _report(
        _screen("P001", inputs=[("q", "abcdef")]),
        _screen("P002", title="無関係な内容"),
    )

    assert track_reflections(report)["flows"] == []


def test_short_values_are_ignored() -> None:
    report = _report(
        _screen("P001", inputs=[("q", "ab")]),
        _screen("P002", title="ab の話"),
    )

    assert track_reflections(report)["flows"] == []


def test_source_screen_is_not_counted_as_sink() -> None:
    report = _report(
        _screen("P001", title="入力ホテル函館", inputs=[("q", "ホテル函館")]),
    )

    # 反映先が自分だけなら flow にしない
    assert track_reflections(report)["flows"] == []


def test_multiple_sinks_are_listed() -> None:
    report = _report(
        _screen("P001", inputs=[("q", "予約番号XYZ")]),
        _screen("P002", title="予約番号XYZ の確認"),
        _screen("P003", headings=["予約番号XYZ 完了"]),
    )

    flow = track_reflections(report)["flows"][0]
    assert flow["sink_pages"] == ["P002", "P003"]


def test_claim_scope_declared() -> None:
    result = track_reflections(_report())

    assert result["meta"]["claim_notice"] == CLAIM_NOTICE
    assert result["summary"]["flows"] == 0
