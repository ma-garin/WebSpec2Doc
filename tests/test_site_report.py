"""web/services/site_report.py の受入テスト（C2）。

守るべき性質は 3 つ:
  1. 配布物が単体で完結する（`<script src` / `<link` を含まない）
  2. 外部由来の文字列がすべてエスケープされる（XSS）
  3. データが空でも例外を出さず、無いことを日本語で明示する（数字を捏造しない）
"""

from __future__ import annotations

import re

import pytest

from web.services.site_report import ALL_SECTIONS, build_site_report_html


def _full_kwargs() -> dict:
    return {
        "report": {"meta": {"target_url": "http://127.0.0.1:8766/", "crawled_at": "2026-08-30 14:03"}},
        "tests": [
            {
                "id": "PW-0082",
                "name": "email: 上限値+1",
                "screen": "P004",
                "status": "fail",
                "last": {"error": "送信されてしまいました", "dur_ms": 1200},
            },
            {"id": "PW-0001", "name": "ログインできる", "screen": "P001", "status": "pass"},
        ],
        "runs": [
            {"run_id": "r-1", "at": "2026-08-30 14:10", "passed": 124, "failed": 1, "total": 125, "duration_ms": 252000}
        ],
        "drift": {
            "items": [
                {"id": "d1", "kind": "element", "title": "name が変わった", "impact": ["PW-0082"], "state": "open"},
                {"id": "d2", "kind": "text", "title": "見出しが変わった", "state": "dismissed"},
            ]
        },
        "map_screens": [
            {"id": "P004", "name": "お問い合わせ", "tests": 28, "fails": 1, "coverage": 72},
            {"id": "P009", "name": "マイページ", "tests": 0, "fails": 0, "coverage": 0},
        ],
        "usage": {
            "total_crawls": 18,
            "total_screens": 126,
            "total_test_conditions": 1240,
            "estimated_saved_hours": 36.5,
            "estimated_saved_yen": 182500,
            "coefficients": {"hourly_rate_yen": 5000},
        },
        "base_url": "http://127.0.0.1:8765",
    }


def test_no_external_resources() -> None:
    """外部読み込みが 1 つも無い（受入: grep -c '<script src' → 0）。"""
    out = build_site_report_html("demomart", **_full_kwargs())
    assert "<script src" not in out
    assert "<script" not in out
    assert "<link" not in out
    assert "var(--" not in out  # 配布物ではトークン参照が解決できない
    assert len(out.encode("utf-8")) < 2 * 1024 * 1024


def test_renders_real_values() -> None:
    out = build_site_report_html("demomart", **_full_kwargs())
    assert "demomart — テスト自動化レポート" in out
    assert "124" in out and "125" in out
    assert "4:12" in out  # 252000ms
    assert "お問い合わせ" in out
    assert "未着手" in out  # テスト 0 件の画面はカバレッジを 0% と書かない
    assert "36.5" in out and "¥182,500" in out  # 桁区切り
    assert "kind=screenshot" in out and "kind=trace" in out
    assert "検出した変更（未対応 1 件）" in out  # dismissed は数えない


@pytest.mark.parametrize(
    "payload",
    [
        {"domain": '<img src=x onerror="alert(1)">'},
        {"tests": [{"id": "<b>x</b>", "name": "<script>alert(1)</script>", "screen": "P0", "status": "fail", "last": {"error": '"><script>bad()</script>'}}]},
        {"drift": [{"id": "d", "kind": "element", "title": "<script>evil()</script>", "state": "open"}]},
        {"map_screens": [{"id": "P0", "name": "<script>x()</script>", "tests": 1, "fails": 0, "coverage": 50}]},
        {"report": {"meta": {"target_url": '"><script>x()</script>'}}},
    ],
)
def test_escapes_untrusted_strings(payload: dict) -> None:
    domain = payload.pop("domain", "demomart")
    out = build_site_report_html(domain, **payload)
    # タグとして復活しないこと。属性値を割るための " も残っていないこと
    assert "<script" not in out
    assert "<img" not in out
    assert "<b>x</b>" not in out
    assert "&lt;script&gt;" in out or "&lt;img" in out


def test_empty_data_is_explicit_not_fabricated() -> None:
    out = build_site_report_html("demomart")
    assert "実行の記録が 0 件" in out
    assert "テストがまだ 1 件も作られていません" in out
    assert "画面の解析結果がありません" in out
    assert "まだ比較していません" in out or "判定できません" in out
    assert "推定できません" in out
    # 捏造された数字が出ていないこと（KPI ブロック自体を描かない）
    assert '<div class="kpi">' not in out


def test_sections_can_be_narrowed() -> None:
    out = build_site_report_html("demomart", **_full_kwargs(), sections=["runs"])
    assert "直近の実行" in out
    assert "失敗したテスト" not in out
    assert "削減できた工数" not in out


def test_unknown_and_empty_sections() -> None:
    assert "直近の実行" in build_site_report_html("d", sections=list(ALL_SECTIONS) + ["nope"])
    out = build_site_report_html("d", sections=[])
    assert "節が 1 つも選ばれていません" in out


def test_tolerates_malformed_rows() -> None:
    out = build_site_report_html(
        "demomart",
        report=None,
        tests=["not a dict", None],
        runs="nonsense",
        drift={"items": [None, 5]},
        map_screens=None,
        usage="nope",
        base_url=None,
    )
    assert re.search(r"<html lang=\"ja\">", out)


def test_roi_says_whose_numbers_they_are() -> None:
    """サイト名義の見出しの下に、絞られていない全体値を黙って出さない。"""
    kwargs = _full_kwargs()
    out = build_site_report_html("demomart", **kwargs)
    assert "ワークスペース全体" in out
    assert "demomart単体の実績ではありません" in out

    scoped = _full_kwargs()
    scoped["usage"] = {**scoped["usage"], "domain": "demomart"}
    out2 = build_site_report_html("demomart", **scoped)
    assert "削減できた工数（推定・demomart のみ）" in out2
    assert "単体の実績ではありません" not in out2


def test_numbers_have_separators_and_no_stray_decimals() -> None:
    kwargs = _full_kwargs()
    kwargs["usage"] = {
        "total_crawls": 49,
        "total_screens": 286,
        "total_test_conditions": 744,
        "estimated_saved_hours": 340.5,
        "estimated_saved_yen": 1702500,
        "coefficients": {"hourly_rate_yen": 5000.0},
    }
    out = build_site_report_html("demomart", **kwargs)
    assert "¥1,702,500" in out and "¥1702500" not in out
    assert "単価 ¥5,000/h" in out and "5000.0" not in out
    assert "340.5 時間" in out


def test_runs_section_states_what_it_counts() -> None:
    """一覧（登録済み全件）と直近実行の母数が違うことを本文で明示する。"""
    kwargs = _full_kwargs()
    kwargs["runs"] = [{"run_id": "r-9", "at": "2026-08-30 18:36", "passed": 0, "failed": 1, "total": 1}]
    out = build_site_report_html("demomart", **kwargs)
    assert "直近の実行（2026-08-30 18:36）で流した 1 件" in out
    assert "登録済みのテストは 2 件" in out


def test_coverage_deduplicates_by_page_id() -> None:
    kwargs = _full_kwargs()
    kwargs["map_screens"] = [
        {"id": "P001", "name": "トップ", "tests": 13, "fails": 0, "coverage": 60},
        {"id": "P001", "name": "トップ", "tests": 11, "fails": 0, "coverage": 40},
        {"id": "P002", "name": "トップ", "tests": 11, "fails": 1, "coverage": 40},
    ]
    out = build_site_report_html("demomart", **kwargs)
    assert out.count("<td>P001</td>") == 1  # 同一 page_id は 1 行だけ
    assert "<td>P002</td>" in out  # 同名の別画面は消さない
    assert "重複していたため" in out


def test_drift_without_baseline_is_not_reported_as_zero_changes() -> None:
    out = build_site_report_html(
        "demomart",
        drift={"items": [], "baseline_at": "", "reason": "比較の基準となる前回のクロールがありません"},
    )
    assert "まだ比較していません" in out
    assert "未対応の変更はありません" not in out

    ok = build_site_report_html("demomart", drift={"items": [], "baseline_at": "2026-08-30T18:00"})
    assert "未対応の変更はありません" in ok
