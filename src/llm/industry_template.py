"""業種別テスト観点テンプレートモジュール。

業種定数・テンプレート辞書・取得ヘルパー・追加観点生成を提供する。
"""

from __future__ import annotations

from dataclasses import dataclass

from llm.screen_classifier import (
    SCREEN_AUTH,
    SCREEN_PAYMENT,
    SCREEN_PERSONAL_INFO,
    SCREEN_SEARCH,
    ScreenClassification,
)

# 業種定数
INDUSTRY_EC = "ec"
INDUSTRY_FINANCE = "finance"
INDUSTRY_MEDICAL = "medical"
INDUSTRY_GOVERNMENT = "government"
INDUSTRY_GENERAL = "general"


@dataclass(frozen=True)
class IndustryTemplate:
    industry: str
    name: str
    key_test_areas: tuple[str, ...]
    required_viewpoints: tuple[str, ...]
    risk_keywords: tuple[str, ...]


INDUSTRY_TEMPLATES: dict[str, IndustryTemplate] = {
    INDUSTRY_EC: IndustryTemplate(
        industry=INDUSTRY_EC,
        name="EC・通販",
        key_test_areas=("カート", "決済", "在庫", "セッション", "配送料計算", "クーポン"),
        required_viewpoints=(
            "カート操作の正常・異常フロー",
            "決済エラーハンドリングと二重課金防止",
            "在庫切れ時のユーザー通知",
            "クーポン・割引の計算正確性",
            "ゲスト購入とログイン購入の両フロー",
        ),
        risk_keywords=("決済", "カード", "カート", "在庫", "クーポン", "配送"),
    ),
    INDUSTRY_FINANCE: IndustryTemplate(
        industry=INDUSTRY_FINANCE,
        name="金融・FinTech",
        key_test_areas=("振込", "残高", "ログイン", "セッション", "暗号化", "取引履歴"),
        required_viewpoints=(
            "振込金額の境界値テスト",
            "残高不足時のエラーハンドリング",
            "セッションタイムアウトと再認証",
            "通信経路の暗号化確認",
            "取引履歴の表示正確性",
        ),
        risk_keywords=("振込", "残高", "取引", "ログイン", "認証", "暗号"),
    ),
    INDUSTRY_MEDICAL: IndustryTemplate(
        industry=INDUSTRY_MEDICAL,
        name="医療・ヘルスケア",
        key_test_areas=("入力制限", "アクセス制御", "監査ログ", "患者ID", "医薬品名"),
        required_viewpoints=(
            "患者 ID の入力バリデーション",
            "ロールベースアクセス制御の検証",
            "監査ログの完全性確認",
            "医薬品名の誤入力防止",
            "個人情報マスキングの確認",
        ),
        risk_keywords=("患者", "医薬品", "診断", "処方", "カルテ", "個人情報"),
    ),
    INDUSTRY_GOVERNMENT: IndustryTemplate(
        industry=INDUSTRY_GOVERNMENT,
        name="行政・公共",
        key_test_areas=("JIS X 8341 アクセシビリティ", "SSL", "改ざん防止", "個人情報保護"),
        required_viewpoints=(
            "JIS X 8341-3:2016 レベル AA 準拠確認",
            "SSL/TLS 証明書の有効性確認",
            "ページ改ざん検知の仕組み確認",
            "個人情報取得・保管・廃棄フローのテスト",
            "多ブラウザ・多デバイスの動作確認",
        ),
        risk_keywords=("マイナンバー", "個人情報", "行政", "公的", "証明書"),
    ),
    INDUSTRY_GENERAL: IndustryTemplate(
        industry=INDUSTRY_GENERAL,
        name="一般",
        key_test_areas=("基本機能", "入力値検証", "エラーハンドリング"),
        required_viewpoints=(
            "正常系の基本動作確認",
            "入力値バリデーションの確認",
            "エラーメッセージの適切な表示",
        ),
        risk_keywords=(),
    ),
}


def get_template(industry: str) -> IndustryTemplate:
    """業種テンプレートを返す。未知の業種は general を返す。"""
    return INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES[INDUSTRY_GENERAL])


# 業種 × 画面種別の組み合わせ追加観点テーブル
_ADDITIONAL: dict[tuple[str, str], list[str]] = {
    (INDUSTRY_EC, SCREEN_PAYMENT): [
        "3D セキュア認証のテスト",
        "決済代行サービスのサンドボックスでの動作確認",
        "カード情報の非保持化対応確認",
    ],
    (INDUSTRY_EC, SCREEN_AUTH): [
        "ソーシャルログイン（Google/LINE 等）の動作確認",
        "パスワードレス認証オプションのテスト",
    ],
    (INDUSTRY_EC, SCREEN_SEARCH): [
        "商品絞り込み条件の組み合わせテスト",
        "在庫ゼロ商品のフィルタリング確認",
    ],
    (INDUSTRY_FINANCE, SCREEN_AUTH): [
        "多要素認証（MFA/TOTP）のテスト",
        "ハードウェアトークン認証のテスト",
        "不正ログイン検知アラートのテスト",
    ],
    (INDUSTRY_FINANCE, SCREEN_PAYMENT): [
        "振込限度額チェックのテスト",
        "取引承認フロー（上長承認）のテスト",
    ],
    (INDUSTRY_MEDICAL, SCREEN_PERSONAL_INFO): [
        "患者同意書の電子署名フローのテスト",
        "匿名化・仮名化処理の確認",
    ],
    (INDUSTRY_MEDICAL, SCREEN_AUTH): [
        "医師・看護師・一般スタッフの権限分離テスト",
        "緊急アクセス（break-glass）フローのテスト",
    ],
    (INDUSTRY_GOVERNMENT, SCREEN_PERSONAL_INFO): [
        "マイナンバー収集の法令根拠表示確認",
        "特定個人情報の保護評価書との整合確認",
    ],
    (INDUSTRY_GOVERNMENT, SCREEN_AUTH): [
        "マイナンバーカード認証のテスト",
        "電子証明書の有効期限チェック",
    ],
}


def get_additional_viewpoints(
    screen_classification: ScreenClassification,
    industry: str,
) -> list[str]:
    """業種と画面種別の組み合わせで特化した追加観点を返す。"""
    return list(_ADDITIONAL.get((industry, screen_classification.screen_type), []))
