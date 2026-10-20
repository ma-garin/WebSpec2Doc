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


def test_doc_app_hides_url_only_inputs_and_names_sample_completion() -> None:
    """URL 版だけの入力は試作で出さない。完了・見出しは「サンプルの再生」と書く（実アプリの解析完了に見せない）。"""
    root = Path(__file__).resolve().parent.parent
    css = (root / "static/css/doc-app.css").read_text(encoding="utf-8")
    for sel in ("#record-mode", "#discover-scope", ".wizard-p1-hints"):
        assert f"body[data-app-mode] {sel}" in css, sel
    html = _html()
    assert "サンプルの再生が完了" in html and "実アプリは解析していません" in html
    assert 'class="doc-app-unsupported" disabled' in html and "未対応" in html
    assert "サンプル画面（再生）" in html
    js = (root / "static/js/execution.js").read_text(encoding="utf-8")
    assert "サンプルの再生が完了" in js
    mode = (root / "static/js/doc-app-mode.js").read_text(encoding="utf-8")
    assert "サンプルで出力を見る（試作）" in mode
    overview = (root / "static/js/view-overview.js").read_text(encoding="utf-8")
    assert "サンプルデータの再生（クロール・実アプリ解析なし）" in overview


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
