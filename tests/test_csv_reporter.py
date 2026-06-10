"""src/generator/csv_reporter.py のユニットテスト"""

from __future__ import annotations

import csv
from pathlib import Path

from crawler.page_crawler import FieldData, FormData, PageData
from generator.csv_reporter import generate_csv_report, generate_testcase_csv


def _make_page(
    url: str = "https://example.com/",
    title: str = "テストページ",
    forms: tuple[FormData, ...] = (),
) -> PageData:
    return PageData(
        url=url,
        title=title,
        headings=(),
        links=(),
        forms=forms,
        screenshot_path=None,
    )


def _make_field(name: str = "q", field_type: str = "text", required: bool = False) -> FieldData:
    return FieldData(
        field_type=field_type,
        name=name,
        placeholder="",
        required=required,
    )


def _make_form(action: str = "/search", fields: tuple[FieldData, ...] = ()) -> FormData:
    return FormData(action=action, method="get", fields=fields)


class TestGenerateCsvReport:
    def test_generate_csv_report_creates_file(self, tmp_path: Path) -> None:
        field = _make_field("username", "text", required=True)
        form = _make_form("/login", (field,))
        page = _make_page("https://example.com/login", "ログイン", (form,))
        output = tmp_path / "report.csv"

        result = generate_csv_report([page], output)

        assert result == output
        assert output.exists()

    def test_bom_prefix(self, tmp_path: Path) -> None:
        page = _make_page()
        output = tmp_path / "report.csv"

        generate_csv_report([page], output)

        # BOM 付き UTF-8 の先頭 3 バイトを確認
        assert output.read_bytes()[:3] == b"\xef\xbb\xbf"

    def test_header_row(self, tmp_path: Path) -> None:
        page = _make_page()
        output = tmp_path / "report.csv"

        generate_csv_report([page], output)

        with output.open(encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)

        assert header == [
            "ページ番号",
            "ページ名",
            "URL",
            "フォームアクション",
            "フィールド名",
            "フィールド種別",
            "必須",
            "テスト条件",
        ]

    def test_field_row_values(self, tmp_path: Path) -> None:
        field = _make_field("email", "email", required=True)
        form = _make_form("/send", (field,))
        page = _make_page("https://example.com/contact", "お問い合わせ", (form,))
        output = tmp_path / "report.csv"

        generate_csv_report([page], output)

        with output.open(encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader)  # header
            row = next(reader)

        assert row[0] == "1"  # ページ番号
        assert row[1] == "お問い合わせ"
        assert row[2] == "https://example.com/contact"
        assert row[3] == "/send"  # フォームアクション
        assert row[4] == "email"  # フィールド名
        assert row[5] == "email"  # フィールド種別
        assert row[6] == "Yes"  # 必須

    def test_page_without_forms_outputs_empty_row(self, tmp_path: Path) -> None:
        page = _make_page("https://example.com/about", "概要ページ")
        output = tmp_path / "report.csv"

        generate_csv_report([page], output)

        with output.open(encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader)  # header
            row = next(reader)

        assert row[4] == "(空のフォーム)"

    def test_multiple_pages_numbered(self, tmp_path: Path) -> None:
        field = _make_field("q")
        form = _make_form("/search", (field,))
        page1 = _make_page("https://example.com/", "トップ", (form,))
        page2 = _make_page("https://example.com/about", "概要")
        output = tmp_path / "report.csv"

        generate_csv_report([page1, page2], output)

        with output.open(encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader)  # header
            rows = list(reader)

        assert rows[0][0] == "1"
        assert rows[1][0] == "2"

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        page = _make_page()
        output = tmp_path / "sub" / "report.csv"

        generate_csv_report([page], output)

        assert output.exists()

    def test_required_no_value(self, tmp_path: Path) -> None:
        field = _make_field("comment", "text", required=False)
        form = _make_form("/post", (field,))
        page = _make_page(forms=(form,))
        output = tmp_path / "report.csv"

        generate_csv_report([page], output)

        with output.open(encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)

        assert row[6] == "No"

    def test_test_conditions_in_last_column(self, tmp_path: Path) -> None:
        field = FieldData(
            field_type="text",
            name="name",
            placeholder="",
            required=True,
        )
        form = _make_form("/send", (field,))
        page = _make_page(forms=(form,))
        output = tmp_path / "report.csv"

        generate_csv_report([page], output)

        with output.open(encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)

        assert row[7]  # テスト条件が空でないこと


class TestGenerateTestcaseCsv:
    def _sample_cases(self) -> list[dict]:
        return [
            {
                "id": "TC-001",
                "title": "正常ログイン",
                "steps": ["ID を入力する", "パスワードを入力する", "ログインボタンをクリック"],
                "expected": "ダッシュボードが表示される",
                "automation_status": "automatable",
                "trace_id": "SCR-001",
            },
            {
                "id": "TC-002",
                "title": "パスワード未入力",
                "steps": "パスワード欄を空にしてログインする",
                "expected": "エラーメッセージが表示される",
                "automation_status": "manual-review",
                "trace_id": "SCR-001",
            },
        ]

    def test_generate_testcase_csv_steps_joined(self, tmp_path: Path) -> None:
        """steps がリストの場合に改行で結合されることを確認"""
        cases = self._sample_cases()
        output = tmp_path / "testcases.csv"

        generate_testcase_csv(cases, output)

        with output.open(encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader)  # header
            row = next(reader)

        steps_cell = row[2]
        assert "ID を入力する" in steps_cell
        assert "パスワードを入力する" in steps_cell
        assert "\n" in steps_cell

    def test_steps_as_string_preserved(self, tmp_path: Path) -> None:
        """steps が文字列の場合はそのまま出力されることを確認"""
        cases = self._sample_cases()
        output = tmp_path / "testcases.csv"

        generate_testcase_csv(cases, output)

        with output.open(encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader)
            next(reader)  # skip TC-001
            row = next(reader)

        assert row[2] == "パスワード欄を空にしてログインする"

    def test_creates_file_with_bom(self, tmp_path: Path) -> None:
        output = tmp_path / "testcases.csv"
        generate_testcase_csv(self._sample_cases(), output)

        assert output.read_bytes()[:3] == b"\xef\xbb\xbf"

    def test_header_row(self, tmp_path: Path) -> None:
        output = tmp_path / "testcases.csv"
        generate_testcase_csv([], output)

        with output.open(encoding="utf-8-sig") as f:
            header = next(csv.reader(f))

        assert header == [
            "ID",
            "タイトル",
            "ステップ",
            "期待結果",
            "自動化ステータス",
            "トレースID",
        ]

    def test_returns_path(self, tmp_path: Path) -> None:
        output = tmp_path / "testcases.csv"
        result = generate_testcase_csv([], output)

        assert result == output

    def test_data_row_values(self, tmp_path: Path) -> None:
        cases = [
            {
                "id": "TC-010",
                "title": "検索テスト",
                "steps": ["検索ワードを入力"],
                "expected": "結果が表示される",
                "automation_status": "automatable",
                "trace_id": "SCR-005",
            }
        ]
        output = tmp_path / "testcases.csv"
        generate_testcase_csv(cases, output)

        with output.open(encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader)
            row = next(reader)

        assert row[0] == "TC-010"
        assert row[1] == "検索テスト"
        assert row[3] == "結果が表示される"
        assert row[4] == "automatable"
        assert row[5] == "SCR-005"

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        output = tmp_path / "nested" / "testcases.csv"
        generate_testcase_csv([], output)

        assert output.exists()
