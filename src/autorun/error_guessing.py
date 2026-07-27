"""エラー推測 / 欠陥ベーステスト — 欠陥タクソノミを実測項目へ突き合わせる。

他の技法（同値分割・境界値・デシジョンテーブル等）は仕様ベースで、
「仕様に書かれた条件」しか検証しない。実際に多い欠陥は仕様の外側にある
（前後空白、全角数字、二重送信、セッション切れ後の送信など）。
エラー推測はそれを経験知から補う技法で、ISTQB では経験ベース技法に分類される。

**本モジュールの出力は実測ではなく一般知識に由来する。** そのため:

- confidence は `CATALOG_CONFIDENCE`（0.9）で固定し、実測由来（1.0）と必ず区別する
- 「この欠陥がある」ではなく「この欠陥が起きやすい箇所」として提示する
- 適用先は実測した項目種別・画面種別に限る（観測していない項目には出さない）

タクソノミは項目種別・画面種別ごとの静的表で、生成は純関数で決定的。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TECHNIQUE_ERROR_GUESSING = "エラー推測"

#: 一般知識（欠陥タクソノミ）由来。実測由来の 1.0 とは必ず区別する。
CATALOG_CONFIDENCE = 0.9

_SKIP_FIELD_TYPES = frozenset({"hidden", "submit", "button", "reset", "image"})


@dataclass(frozen=True)
class DefectGuess:
    """1 つの欠陥推測。適用先と根拠を必ず持つ。"""

    guess_id: str
    target: str  # 適用先（項目名 または 画面）
    category: str
    title: str
    input_value: str
    expected: str
    confidence: float = CATALOG_CONFIDENCE

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.guess_id,
            "target": self.target,
            "category": self.category,
            "title": self.title,
            "input": self.input_value,
            "expected": self.expected,
            "confidence": self.confidence,
            "evidence": "欠陥タクソノミ（一般知識・未実測）",
        }


# =========================================================================
# 欠陥タクソノミ（項目種別 → (分類, 表題, 入力値, 期待結果)）
# =========================================================================
_TEXT_DEFECTS: tuple[tuple[str, str, str, str], ...] = (
    ("入力値の正規化", "前後の空白", "  値  ", "空白が除去されるか、明示的にエラーになる"),
    ("入力値の正規化", "改行の混入", "値\\n値", "改行が除去されるか、拒否される"),
    ("文字種", "全角と半角の混在", "ＡＢＣ123", "正規化されるか、形式エラーになる"),
    ("文字種", "絵文字・サロゲートペア", "😀𠮷", "保存後に文字化けせず、そのまま再表示される"),
    ("エスケープ", "HTML タグの混入", "<b>x</b>", "エスケープされ、タグとして解釈されない"),
    ("エスケープ", "SQL 特殊文字", "' OR '1'='1", "エスケープされ、エラーにも成功にもならない"),
)

_NUMBER_DEFECTS: tuple[tuple[str, str, str, str], ...] = (
    ("数値表記", "先頭ゼロ", "007", "0 除去後の値として扱われるか、形式エラーになる"),
    ("数値表記", "符号付き", "-0", "0 として扱われ、負号で異常終了しない"),
    ("数値表記", "指数表記", "1e5", "拒否されるか、100000 として一貫して扱われる"),
    ("桁あふれ", "極端に大きい値", "9" * 20, "桁あふれせず、範囲外エラーになる"),
    ("小数", "想定外の小数点", "1.5", "整数項目なら拒否され、丸めで黙って変わらない"),
)

_EMAIL_DEFECTS: tuple[tuple[str, str, str, str], ...] = (
    ("形式", "プラス記号エイリアス", "user+tag@example.com", "妥当なアドレスとして受理される"),
    ("形式", "大文字混在", "USER@Example.COM", "小文字と同一のアドレスとして扱われる"),
    ("形式", "長い TLD", "user@example.technology", "妥当なアドレスとして受理される"),
    ("形式", "連続ドット", "user..name@example.com", "形式エラーになる"),
)

_DATE_DEFECTS: tuple[tuple[str, str, str, str], ...] = (
    ("暦", "閏年の 2/29", "2024-02-29", "妥当な日付として受理される"),
    ("暦", "非閏年の 2/29", "2023-02-29", "存在しない日付として拒否される"),
    ("暦", "月末", "2024-01-31", "翌月への繰り上がりが起きない"),
    ("境界", "日付の下限側", "1900-01-01", "受理されるか、明示的に範囲外エラーになる"),
)

_PASSWORD_DEFECTS: tuple[tuple[str, str, str, str], ...] = (
    ("文字種", "空白のみ", "        ", "拒否される"),
    ("文字種", "多バイト文字", "パスワード1", "受理されるなら、再ログインでも同じ判定になる"),
    ("長さ", "極端に長い", "a" * 200, "切り詰めで別のパスワードとして保存されない"),
)

_TEL_DEFECTS: tuple[tuple[str, str, str, str], ...] = (
    ("区切り", "ハイフンあり/なし", "03-1234-5678", "どちらの表記でも同一の番号として扱われる"),
    ("文字種", "全角数字", "０３１２３４５６７８", "正規化されるか、形式エラーになる"),
    ("形式", "国番号付き", "+81312345678", "受理されるか、明示的にエラーになる"),
)

_FILE_DEFECTS: tuple[tuple[str, str, str, str], ...] = (
    ("拡張子", "拡張子偽装", "image.png（中身は実行ファイル）", "内容で判定され、拒否される"),
    ("サイズ", "0 バイト", "空ファイル", "拒否されるか、明示的に通知される"),
    ("文字", "日本語ファイル名", "テスト資料.pdf", "文字化けせずに保存・再取得できる"),
)

_BY_FIELD_TYPE: dict[str, tuple[tuple[str, str, str, str], ...]] = {
    "text": _TEXT_DEFECTS,
    "textarea": _TEXT_DEFECTS,
    "search": _TEXT_DEFECTS,
    "number": _NUMBER_DEFECTS,
    "range": _NUMBER_DEFECTS,
    "email": _EMAIL_DEFECTS,
    "date": _DATE_DEFECTS,
    "datetime-local": _DATE_DEFECTS,
    "month": _DATE_DEFECTS,
    "password": _PASSWORD_DEFECTS,
    "tel": _TEL_DEFECTS,
    "file": _FILE_DEFECTS,
}

#: フォームを持つ画面に共通して起きやすい欠陥（項目に依存しない）。
_FORM_LEVEL_DEFECTS: tuple[tuple[str, str, str, str], ...] = (
    ("多重実行", "送信ボタンの二重クリック", "送信を素早く 2 回押す", "登録が 1 件だけ作られる"),
    (
        "画面遷移",
        "送信後に戻るボタン",
        "送信 → ブラウザの戻る → 再送信",
        "二重登録されず、期限切れとして扱われる",
    ),
    (
        "セッション",
        "放置後の送信",
        "フォームを開いたまま長時間放置してから送信",
        "セッション切れが通知され、入力内容が失われない",
    ),
    (
        "並行更新",
        "同一データの同時更新",
        "2 つのタブで同じデータを開いて両方保存",
        "後勝ちで黙って上書きされず、競合が通知される",
    ),
    (
        "再読込",
        "送信直後のリロード",
        "送信完了画面で F5",
        "再送信の確認が出るか、冪等に扱われる",
    ),
)


# =========================================================================
# 構築
# =========================================================================
def _field_name(field: dict[str, Any]) -> str:
    return str(field.get("name") or field.get("label") or "")


def guesses_for_field(field: dict[str, Any], start_index: int) -> tuple[DefectGuess, ...]:
    """1 項目に対する欠陥推測。項目種別のタクソノミにあるものだけを出す。"""
    field_type = str(field.get("field_type", "text"))
    entries = _BY_FIELD_TYPE.get(field_type)
    if entries is None:
        return ()
    name = _field_name(field)
    return tuple(
        DefectGuess(
            guess_id=f"EG{start_index + offset}",
            target=name,
            category=category,
            title=title,
            input_value=value,
            expected=expected,
        )
        for offset, (category, title, value, expected) in enumerate(entries)
    )


def error_guessing(fields: list[dict[str, Any]], *, has_form: bool = True) -> dict[str, Any]:
    """`techniques.apply_all` から呼ぶ辞書インタフェース。"""
    target_fields = [
        f
        for f in fields
        if isinstance(f, dict) and str(f.get("field_type", "")) not in _SKIP_FIELD_TYPES
    ]
    guesses: list[DefectGuess] = []
    for field in target_fields:
        guesses.extend(guesses_for_field(field, len(guesses) + 1))

    if has_form and target_fields:
        base = len(guesses) + 1
        for offset, (category, title, value, expected) in enumerate(_FORM_LEVEL_DEFECTS):
            guesses.append(
                DefectGuess(
                    guess_id=f"EG{base + offset}",
                    target="画面全体",
                    category=category,
                    title=title,
                    input_value=value,
                    expected=expected,
                )
            )

    if not guesses:
        return {
            "applicable": False,
            "technique": TECHNIQUE_ERROR_GUESSING,
            "reason": "タクソノミに対応する項目種別が観測されていません。",
        }

    categories = sorted({g.category for g in guesses})
    return {
        "applicable": True,
        "technique": TECHNIQUE_ERROR_GUESSING,
        "guesses": [g.to_dict() for g in guesses],
        "case_count": len(guesses),
        "categories": categories,
        "confidence": CATALOG_CONFIDENCE,
        "coverage": (
            f"欠陥タクソノミ {len(categories)} 分類・{len(guesses)} 件を実測項目へ適用"
        ),
        "notice": (
            "本技法の出力は一般知識に由来し、対象システムの実測ではない。"
            "採否は必ずレビューで判断すること。"
        ),
    }
