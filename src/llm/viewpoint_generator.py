"""テスト観点・異常系シナリオをルールまたは LLM で生成するモジュール。

ScreenClassification とフィールド情報を元に TestViewpoint リストを返す。
LLM 版は失敗時にルールベースへ自動フォールバックする。
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

from llm.screen_classifier import (
    _LLM_MODEL,
    _OPENAI_CHAT_URL,
    SCREEN_AUTH,
    SCREEN_FORM,
    SCREEN_GENERAL,
    SCREEN_PAYMENT,
    SCREEN_PERSONAL_INFO,
    ScreenClassification,
)

logger = logging.getLogger(__name__)

_CATEGORIES = ("機能", "セキュリティ", "ユーザビリティ", "パフォーマンス", "アクセシビリティ")


@dataclass(frozen=True)
class TestViewpoint:
    category: str
    viewpoint: str
    risk_level: str  # "高" / "中" / "低"
    example_cases: tuple[str, ...]  # 2〜3 件


# ---------- ルールベース生成 ----------


def generate_viewpoints_by_rules(
    screen_classification: ScreenClassification,
    field_data_list: list,  # list[FieldData]
) -> list[TestViewpoint]:
    """画面分類とフィールド情報からテスト観点を生成する（オフライン動作）。"""
    viewpoints: list[TestViewpoint] = []

    viewpoints.extend(_screen_type_viewpoints(screen_classification.screen_type))
    viewpoints.extend(_field_viewpoints(field_data_list))

    # 全画面共通: 正常系確認
    viewpoints.append(
        TestViewpoint(
            category="機能",
            viewpoint="正常系の基本動作確認",
            risk_level="低",
            example_cases=("期待する入力で操作が正常に完了すること", "遷移先が正しいこと"),
        )
    )

    return viewpoints


def _screen_type_viewpoints(screen_type: str) -> list[TestViewpoint]:
    """画面種別に固有のテスト観点を返す。"""
    if screen_type == SCREEN_PAYMENT:
        return [
            TestViewpoint(
                category="セキュリティ",
                viewpoint="カード情報の暗号化・通信路の安全性",
                risk_level="高",
                example_cases=(
                    "HTTPS で送信されること",
                    "カード番号がログに残らないこと",
                    "PCI DSS 準拠の入力フォームであること",
                ),
            ),
            TestViewpoint(
                category="機能",
                viewpoint="金額計算・決済エラーハンドリング",
                risk_level="高",
                example_cases=(
                    "正常決済が完了すること",
                    "カード拒否時にエラーメッセージが表示されること",
                    "ネットワーク切断時に二重課金が発生しないこと",
                ),
            ),
        ]
    if screen_type == SCREEN_AUTH:
        return [
            TestViewpoint(
                category="セキュリティ",
                viewpoint="ブルートフォース攻撃対策・セッション管理",
                risk_level="高",
                example_cases=(
                    "連続ログイン失敗でアカウントがロックされること",
                    "ログアウト後にセッションが無効になること",
                    "セッション固定攻撃が防止されること",
                ),
            ),
            TestViewpoint(
                category="機能",
                viewpoint="パスワードリセット・再認証フロー",
                risk_level="中",
                example_cases=(
                    "パスワードリセットメールが送信されること",
                    "リセットリンクの有効期限が切れた場合にエラーになること",
                ),
            ),
        ]
    if screen_type == SCREEN_PERSONAL_INFO:
        return [
            TestViewpoint(
                category="セキュリティ",
                viewpoint="入力値の永続化防止・表示マスキング",
                risk_level="高",
                example_cases=(
                    "ブラウザの autocomplete が無効になっていること",
                    "表示時にマイナンバーなど機微情報がマスクされること",
                ),
            ),
            TestViewpoint(
                category="アクセシビリティ",
                viewpoint="個人情報入力フォームのアクセシビリティ",
                risk_level="中",
                example_cases=(
                    "スクリーンリーダーで項目名が読み上げられること",
                    "フォーカス順が論理的であること",
                ),
            ),
        ]
    if screen_type == SCREEN_FORM:
        return [
            TestViewpoint(
                category="ユーザビリティ",
                viewpoint="バリデーションメッセージの明確さ",
                risk_level="中",
                example_cases=(
                    "入力エラー時に該当項目の近くにメッセージが表示されること",
                    "エラー内容がユーザーにとって理解しやすいこと",
                ),
            ),
            TestViewpoint(
                category="機能",
                viewpoint="必須項目の漏れチェック",
                risk_level="中",
                example_cases=(
                    "必須項目を空で送信するとエラーになること",
                    "全必須項目を入力すると送信できること",
                ),
            ),
        ]
    return []


def _field_viewpoints(field_data_list: list) -> list[TestViewpoint]:
    """フィールド属性から追加観点を生成する。"""
    viewpoints: list[TestViewpoint] = []
    has_required = any(getattr(f, "required", False) for f in field_data_list)
    has_maxlength = any(getattr(f, "maxlength", None) is not None for f in field_data_list)

    if has_required:
        viewpoints.append(
            TestViewpoint(
                category="機能",
                viewpoint="必須フィールドの未入力エラー",
                risk_level="中",
                example_cases=(
                    "必須項目を空で送信したときにエラーが表示されること",
                    "必須項目に値を入力すれば送信できること",
                ),
            )
        )
    if has_maxlength:
        viewpoints.append(
            TestViewpoint(
                category="機能",
                viewpoint="最大文字数境界値のテスト",
                risk_level="低",
                example_cases=(
                    "最大文字数ちょうどで入力できること",
                    "最大文字数 +1 文字では入力または送信が拒否されること",
                ),
            )
        )
    return viewpoints


# ---------- LLM 版 ----------


def generate_viewpoints_with_llm(
    screen_info: dict,
    api_key: str,
) -> list[TestViewpoint]:
    """LLM でテスト観点を生成し、失敗時はルールベースへフォールバックする。"""
    try:
        return _call_llm_for_viewpoints(screen_info, api_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM viewpoint generation failed, falling back to rules: %s", exc)
        sc_raw = screen_info.get("screen_classification")
        if isinstance(sc_raw, ScreenClassification):
            return generate_viewpoints_by_rules(sc_raw, screen_info.get("fields", []))
        return generate_viewpoints_by_rules(
            ScreenClassification(SCREEN_GENERAL, 0.5, (), "low"), []
        )


def _call_llm_for_viewpoints(screen_info: dict, api_key: str) -> list[TestViewpoint]:
    """OpenAI API を呼び出してテスト観点 JSON 配列を取得する。"""
    prompt = (
        "あなたは QA エンジニアです。以下の Web 画面情報に基づきテスト観点を JSON 配列で返してください。\n"
        f"画面情報: {json.dumps(screen_info, ensure_ascii=False)}\n\n"
        "各要素は以下のキーを持つこと: "
        "category(機能/セキュリティ/ユーザビリティ/パフォーマンス/アクセシビリティ), "
        "viewpoint(観点説明), risk_level(高/中/低), example_cases(文字列配列 2〜3 件)"
    )
    payload = {
        "model": _LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    request = urllib.request.Request(
        _OPENAI_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as resp:  # nosec B310
        data = json.loads(resp.read().decode("utf-8"))
    text = data["choices"][0]["message"]["content"]
    parsed = json.loads(text)
    items = parsed if isinstance(parsed, list) else parsed.get("viewpoints", [])
    return [
        TestViewpoint(
            category=str(item["category"]),
            viewpoint=str(item["viewpoint"]),
            risk_level=str(item["risk_level"]),
            example_cases=tuple(str(c) for c in item.get("example_cases", [])),
        )
        for item in items
    ]
