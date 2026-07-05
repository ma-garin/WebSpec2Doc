from __future__ import annotations

import json
from typing import Any

from web.config import TEST_DESIGN_SETTINGS_FILE

# テスト値カタログの既定値。R1-19「メール: 上限値/上限値+1/空白/2byte/RFC違反/
# 未登録/解約済み等」への対応。ここでの値はすべて一般的なQA観点として広く
# 知られた既知境界値であり、解析対象サイト固有のデータではないため
# evidence-only 原則（実測データのみを主張する）の対象外。
DEFAULT_VALUE_CATALOG: dict[str, list[dict[str, str]]] = {
    "email": [
        {
            "label": "上限値",
            "value": f"{'a' * 64}@{'b' * 63}.com",
            "note": "ローカル部64文字・ドメイン255文字以内の上限",
        },
        {
            "label": "上限値+1",
            "value": f"{'a' * 65}@{'b' * 63}.com",
            "note": "ローカル部が上限を1文字超過",
        },
        {"label": "空白", "value": "", "note": "未入力"},
        {"label": "2byte文字混入", "value": "たろう@example.com", "note": "全角文字を含む不正形式"},
        {"label": "RFC違反", "value": "not-an-email", "note": "@を含まない不正形式"},
        {
            "label": "未登録",
            "value": "not-registered@example.com",
            "note": "会員データベースに存在しないアドレス",
        },
        {
            "label": "解約済み",
            "value": "withdrawn-user@example.com",
            "note": "退会・解約済みアカウントのアドレス",
        },
    ],
    "phone_jp": [
        {"label": "上限値", "value": "090-9999-9999", "note": "携帯電話番号の標準桁数"},
        {"label": "上限値+1", "value": "090-99999-9999", "note": "桁数超過"},
        {"label": "空白", "value": "", "note": "未入力"},
        {"label": "ハイフンなし", "value": "09099999999", "note": "区切り文字なし表記"},
        {"label": "国際表記", "value": "+81-90-9999-9999", "note": "国番号付き表記"},
        {"label": "不正文字混入", "value": "090-9999-999a", "note": "数字以外の文字を含む"},
    ],
    "name": [
        {"label": "上限値", "value": "山" * 50, "note": "氏名欄の想定上限文字数"},
        {"label": "上限値+1", "value": "山" * 51, "note": "文字数超過"},
        {"label": "空白", "value": "", "note": "未入力"},
        {"label": "全角スペース混入", "value": "山田　太郎", "note": "姓名間の全角スペース"},
        {"label": "絵文字混入", "value": "山田太郎😀", "note": "サロゲートペア文字を含む"},
        {
            "label": "特殊文字混入",
            "value": "<script>alert(1)</script>",
            "note": "XSSペイロードとしての入力",
        },
    ],
    "date": [
        {"label": "下限値", "value": "1900-01-01", "note": "想定最小日付"},
        {"label": "下限値-1", "value": "1899-12-31", "note": "想定範囲外（過去方向）"},
        {"label": "上限値", "value": "2099-12-31", "note": "想定最大日付"},
        {"label": "上限値+1", "value": "2100-01-01", "note": "想定範囲外（未来方向）"},
        {"label": "うるう年境界", "value": "2024-02-29", "note": "うるう年2月29日の妥当性"},
        {"label": "不正日付", "value": "2024-02-30", "note": "存在しない日付"},
    ],
    "price": [
        {"label": "下限値", "value": "0", "note": "無料・0円の扱い"},
        {"label": "下限値-1", "value": "-1", "note": "負値（想定外）"},
        {"label": "上限値", "value": "9999999", "note": "想定最大金額"},
        {"label": "上限値+1", "value": "10000000", "note": "想定範囲外"},
        {"label": "小数混入", "value": "100.5", "note": "整数のみ許容する項目への小数入力"},
    ],
    "quantity": [
        {"label": "下限値", "value": "1", "note": "最小注文数量"},
        {"label": "下限値-1", "value": "0", "note": "0個（想定外）"},
        {"label": "上限値", "value": "99", "note": "想定最大数量"},
        {"label": "上限値+1", "value": "100", "note": "想定範囲外"},
    ],
    "password": [
        {"label": "下限値", "value": "Aa1!5678", "note": "最小文字数（8文字）を満たす"},
        {"label": "下限値-1", "value": "Aa1!567", "note": "最小文字数未満（7文字）"},
        {"label": "上限値", "value": "Aa1!" + "x" * 60, "note": "想定最大文字数（64文字）"},
        {"label": "上限値+1", "value": "Aa1!" + "x" * 61, "note": "想定範囲外（65文字）"},
        {"label": "文字種不足", "value": "aaaaaaaa", "note": "英大文字・数字・記号を含まない"},
    ],
}


def _default_settings() -> dict[str, Any]:
    return {"value_catalog": {k: list(v) for k, v in DEFAULT_VALUE_CATALOG.items()}}


def get_test_design_settings() -> dict[str, Any]:
    """テスト設計設定（テスト値カタログ等）を読み込む。ファイルが無ければ既定値で作成する。"""
    path = TEST_DESIGN_SETTINGS_FILE
    if not path.is_file():
        settings = _default_settings()
        save_test_design_settings(settings)
        return settings
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_settings()
    if not isinstance(data, dict) or not isinstance(data.get("value_catalog"), dict):
        return _default_settings()
    return data


def save_test_design_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """テスト設計設定を保存する。value_catalog が無い場合は既定値を補う。"""
    value_catalog = settings.get("value_catalog")
    if not isinstance(value_catalog, dict):
        value_catalog = _default_settings()["value_catalog"]
    normalized = {"value_catalog": value_catalog}
    path = TEST_DESIGN_SETTINGS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return normalized
