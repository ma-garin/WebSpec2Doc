"""web/services/testrail_exporter.py のユニットテスト"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# web/ をパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "web"))

from services.testrail_exporter import (
    TestRailCase,
    build_testrail_cases_from_report,
    export_to_testrail_csv,
    risk_score_to_priority,
)


def _make_case(section: str = "テスト画面", title: str = "TC-001") -> TestRailCase:
    return TestRailCase(
        section=section,
        title=title,
        steps="ステップ1\nステップ2",
        expected="正常に動作すること",
        priority="High",
        case_type="Functional",
        refs="https://example.com/",
    )


class TestExportToTestRailCsv:
    def test_export_to_testrail_csv_creates_file(self, tmp_path: Path) -> None:
        cases = [_make_case("画面A", "TC-001"), _make_case("画面B", "TC-002")]
        output = tmp_path / "testrail.csv"

        export_to_testrail_csv(cases, output)

        assert output.exists()
        # csv.reader を使ってパースすることでステップ内の改行を含む行を正しく数える
        with output.open(encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        # ヘッダー行 + 2 データ行
        assert len(rows) == 3

    def test_export_creates_parent_dir(self, tmp_path: Path) -> None:
        cases = [_make_case()]
        output = tmp_path / "sub" / "testrail.csv"

        export_to_testrail_csv(cases, output)

        assert output.exists()

    def test_export_header_row(self, tmp_path: Path) -> None:
        cases = [_make_case()]
        output = tmp_path / "testrail.csv"

        export_to_testrail_csv(cases, output)

        with output.open(encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)

        assert header == [
            "Section",
            "Title",
            "Steps",
            "Expected Result",
            "Priority",
            "Type",
            "References",
        ]

    def test_export_data_row_values(self, tmp_path: Path) -> None:
        case = TestRailCase(
            section="ログイン画面",
            title="パスワード未入力テスト",
            steps="手順1\n手順2",
            expected="エラーメッセージが表示される",
            priority="Critical",
            case_type="Functional",
            refs="https://example.com/login",
        )
        output = tmp_path / "testrail.csv"

        export_to_testrail_csv([case], output)

        with output.open(encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            row = next(reader)

        assert row[0] == "ログイン画面"
        assert row[1] == "パスワード未入力テスト"
        assert row[4] == "Critical"
        assert row[6] == "https://example.com/login"

    def test_export_bom_encoding(self, tmp_path: Path) -> None:
        cases = [_make_case()]
        output = tmp_path / "testrail.csv"

        export_to_testrail_csv(cases, output)

        # BOM 付き UTF-8 の先頭 3 バイトを確認
        assert output.read_bytes()[:3] == b"\xef\xbb\xbf"

    def test_export_returns_path(self, tmp_path: Path) -> None:
        cases = [_make_case()]
        output = tmp_path / "testrail.csv"

        result = export_to_testrail_csv(cases, output)

        assert result == output

    def test_export_empty_list(self, tmp_path: Path) -> None:
        output = tmp_path / "testrail.csv"

        export_to_testrail_csv([], output)

        rows = output.read_text(encoding="utf-8-sig").splitlines()
        assert len(rows) == 1  # ヘッダーのみ


class TestRiskScoreToPriority:
    def test_risk_score_to_priority_boundaries(self) -> None:
        assert risk_score_to_priority(30) == "Critical"
        assert risk_score_to_priority(15) == "High"
        assert risk_score_to_priority(5) == "Medium"
        assert risk_score_to_priority(4) == "Low"

    def test_above_critical_threshold(self) -> None:
        assert risk_score_to_priority(100) == "Critical"
        assert risk_score_to_priority(30.1) == "Critical"

    def test_just_below_critical(self) -> None:
        assert risk_score_to_priority(29.9) == "High"

    def test_just_below_high(self) -> None:
        assert risk_score_to_priority(14.9) == "Medium"

    def test_zero(self) -> None:
        assert risk_score_to_priority(0) == "Low"

    def test_negative(self) -> None:
        assert risk_score_to_priority(-1) == "Low"


class TestBuildTestRailCasesFromReport:
    def _minimal_report(self) -> dict:
        return {
            "screens": [
                {
                    "title": "ログイン画面",
                    "url": "https://example.com/login",
                    "forms": [
                        {
                            "action": "/login",
                            "method": "post",
                            "fields": [
                                {
                                    "name": "password",
                                    "element_id": "pw",
                                    "field_type": "password",
                                    "required": True,
                                    "test_conditions": [
                                        "未入力で送信（必須チェック）",
                                        "パスワード: 最小長 / 記号含む / 空",
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }

    def test_build_testrail_cases_from_report(self) -> None:
        report = self._minimal_report()
        cases = build_testrail_cases_from_report(report)

        assert len(cases) == 1
        assert cases[0].section == "ログイン画面"
        assert cases[0].refs == "https://example.com/login"
        assert cases[0].case_type == "Functional"

    def test_steps_joined_with_newline(self) -> None:
        report = self._minimal_report()
        cases = build_testrail_cases_from_report(report)

        assert "未入力で送信（必須チェック）" in cases[0].steps
        assert "パスワード: 最小長 / 記号含む / 空" in cases[0].steps
        # 複数条件が改行で結合されている
        assert "\n" in cases[0].steps

    def test_field_name_in_case_title(self) -> None:
        report = self._minimal_report()
        cases = build_testrail_cases_from_report(report)

        assert "password" in cases[0].title

    def test_empty_screens(self) -> None:
        cases = build_testrail_cases_from_report({"screens": []})
        assert cases == []

    def test_screen_without_forms(self) -> None:
        report = {
            "screens": [
                {
                    "title": "概要ページ",
                    "url": "https://example.com/about",
                    "forms": [],
                }
            ]
        }
        cases = build_testrail_cases_from_report(report)
        assert cases == []

    def test_multiple_fields_produce_multiple_cases(self) -> None:
        report = {
            "screens": [
                {
                    "title": "お問い合わせ",
                    "url": "https://example.com/contact",
                    "forms": [
                        {
                            "action": "/send",
                            "method": "post",
                            "fields": [
                                {
                                    "name": "name",
                                    "element_id": "",
                                    "field_type": "text",
                                    "required": True,
                                    "test_conditions": ["未入力で送信"],
                                },
                                {
                                    "name": "email",
                                    "element_id": "",
                                    "field_type": "email",
                                    "required": True,
                                    "test_conditions": ["メール形式チェック"],
                                },
                            ],
                        }
                    ],
                }
            ]
        }
        cases = build_testrail_cases_from_report(report)
        assert len(cases) == 2

    def test_missing_screens_key(self) -> None:
        cases = build_testrail_cases_from_report({})
        assert cases == []
