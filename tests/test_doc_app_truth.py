"""/doc-app は試作（サンプル再生）であることを画面・ログ・成果物が偽らない。"""

from __future__ import annotations

import re
from pathlib import Path

import app as appmod
from web.services import app_mock

_FORBIDDEN = ("インストール", "エミュレータで起動", "起動して初期画面", "クロール中", "（エミュレータ）")


def _html() -> str:
    return appmod.app.test_client().get("/doc-app").get_data(as_text=True)


def _tag(html: str, tag_id: str) -> str:
    m = re.search(r"<(?:input|select)[^>]*\bid=\"" + re.escape(tag_id) + r"\"[^>]*>", html)
    assert m, tag_id
    return m.group(0)


def test_doc_app_shows_prototype_note() -> None:
    html = _html()
    assert 'role="note"' in html
    assert "試作（サンプルデータ）" in html
    assert "実解析は未対応" in html
    assert "デモ用サンプルアプリ" in html
    assert "ドキュメント作成(app)［試作］ - WebSpec2Doc" in html
    assert "APK / .app から" not in html


def test_doc_app_prototype_panel_and_primary_action() -> None:
    html = _html()
    assert html.index("ドキュメント作成(app)は試作です") < html.index('id="wizard-p1"')
    for word in ("できること", "できないこと", "SampleShop で出力の形を確かめる", "APK・.app の実解析",
                 "エミュレータ・実機での操作", "未到達 Activity の洗い出し", "自分のアプリの解析",
                 "サンプルデータ（固定 6 画面）", "実解析は未対応のため、サンプルデータで表示しています",
                 "css/doc-app.css"):
        assert word in html, word
    assert re.search(r'id="discover-btn"[^>]*>\s*サンプルで出力を見る\s*<', html)
    assert ">画面解析<" not in html
    assert html.count("サンプルデータの再生結果（実アプリの仕様ではありません）") == 1


def test_url_mode_has_no_prototype_panel() -> None:
    html = appmod.app.test_client().get("/").get_data(as_text=True)
    assert "doc-app-proto" not in html and "css/doc-app.css" not in html


def test_doc_app_inputs_are_disabled() -> None:
    html = _html()
    for tag_id in ("app-file", "app-device"):
        assert "disabled" in _tag(html, tag_id)
    assert "試作のため使用しません" in html


def test_mock_log_and_report(tmp_path: Path) -> None:
    lines = list(
        app_mock.run_stream(
            "r1", "app.sampleshop", tmp_path, "https://app.sampleshop/HomeActivity", lambda d, o: {}, sleep=lambda s: None
        )
    )
    log = "".join(lines)
    assert "サンプルデータを再生しています（実アプリは解析していません）" in log
    for word in _FORBIDDEN:
        assert word not in log, word
    report = (tmp_path / "app.sampleshop" / "report.html").read_text(encoding="utf-8")
    assert "サンプルデータの再生結果（実アプリの仕様ではありません）" in report
