"""QualityForward のテストケース表カラム定義。

テストケースの出力はこのカラム構成に揃える。将来 QualityForward へ
インポートする際に、そのまま貼り付けられる形を保つのが目的。

カラム順（ユーザー指定）:
    No, 画面, 正常系/異常系, 観点名, 大項目, 中項目, 小項目,
    前提条件, 手順, 期待結果, 備考
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Final

CASE_TYPE_NORMAL: Final = "正常系"
CASE_TYPE_ABNORMAL: Final = "異常系"

#: 出力カラムの並び（表示・エクスポート共通の単一真実源）
COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("no", "No"),
    ("screen", "画面"),
    ("case_type", "正常系/異常系"),
    ("viewpoint", "観点名"),
    ("category_large", "大項目"),
    ("category_medium", "中項目"),
    ("category_small", "小項目"),
    ("precondition", "前提条件"),
    ("steps", "手順"),
    ("expected", "期待結果"),
    ("note", "備考"),
)

COLUMN_KEYS: Final[tuple[str, ...]] = tuple(key for key, _ in COLUMNS)
COLUMN_LABELS: Final[tuple[str, ...]] = tuple(label for _, label in COLUMNS)


@dataclass(frozen=True)
class TestCaseRow:
    """QualityForward 互換のテストケース1行。"""

    # pytest が `Test` 始まりのクラスをテストとして収集しようとするのを防ぐ
    __test__ = False

    no: int
    screen: str
    case_type: str
    viewpoint: str
    category_large: str
    category_medium: str
    category_small: str = ""
    precondition: str = ""
    steps: str = ""
    expected: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def renumbered(self, no: int) -> TestCaseRow:
        """通番を振り直した新しい行を返す（元は変更しない）。"""
        return replace(self, no=no)


def renumber(rows: list[TestCaseRow]) -> list[TestCaseRow]:
    """No 列を 1 から振り直した新しいリストを返す。"""
    return [row.renumbered(i) for i, row in enumerate(rows, start=1)]


def to_table(rows: list[TestCaseRow]) -> dict[str, Any]:
    """UI / エクスポート用の表データ（ヘッダ＋行）に変換する。"""
    return {
        "columns": [{"key": key, "label": label} for key, label in COLUMNS],
        "rows": [row.to_dict() for row in rows],
    }


def to_csv(rows: list[TestCaseRow]) -> str:
    """QualityForward へ貼り付けるための CSV を返す。"""
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMN_LABELS)
    for row in rows:
        data = row.to_dict()
        writer.writerow([data[key] for key in COLUMN_KEYS])
    return buffer.getvalue()


def from_dict(data: dict[str, Any], fallback_no: int = 0) -> TestCaseRow:
    """dict（LLM 応答や編集結果）を TestCaseRow へ正規化する。"""

    def text(key: str) -> str:
        value = data.get(key, "")
        return "" if value is None else str(value)

    case_type = text("case_type")
    if case_type not in (CASE_TYPE_NORMAL, CASE_TYPE_ABNORMAL):
        case_type = CASE_TYPE_NORMAL

    raw_no = data.get("no", fallback_no)
    try:
        no = int(raw_no)
    except (TypeError, ValueError):
        no = fallback_no

    return TestCaseRow(
        no=no,
        screen=text("screen"),
        case_type=case_type,
        viewpoint=text("viewpoint"),
        category_large=text("category_large"),
        category_medium=text("category_medium"),
        category_small=text("category_small"),
        precondition=text("precondition"),
        steps=text("steps"),
        expected=text("expected"),
        note=text("note"),
    )
