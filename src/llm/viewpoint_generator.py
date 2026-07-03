"""テスト観点・異常系シナリオをルールまたは LLM で生成するモジュール。

ScreenClassification とフィールド情報を元に TestViewpoint リストを返す。
LLM 版は失敗時にルールベースへ自動フォールバックする。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from crawler.page_crawler import SourceEvidence
from llm.screen_classifier import (
    _LLM_MODEL,
    SCREEN_AUTH,
    SCREEN_FORM,
    SCREEN_GENERAL,
    SCREEN_PAYMENT,
    SCREEN_PERSONAL_INFO,
    ScreenClassification,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from llm.provider import LLMProvider

_CATEGORIES = ("機能", "セキュリティ", "ユーザビリティ", "パフォーマンス", "アクセシビリティ")
_RISK_LEVELS = ("高", "中", "低")

# ルール由来の観点は DOM 実測・決定的ルールに基づくため confidence は 1.0 固定
RULES_VIEWPOINT_CONFIDENCE = 1.0
# LLM 由来の観点はスキーマ検証・ルール整合検証の通過で 0.7、example_cases が規定件数なら +0.2
LLM_BASE_CONFIDENCE = 0.7
LLM_EXAMPLE_CASES_BONUS = 0.2
_EXAMPLE_CASES_MIN = 2
_EXAMPLE_CASES_MAX = 3


@dataclass(frozen=True)
class TestViewpoint:
    category: str
    viewpoint: str
    risk_level: str  # "高" / "中" / "低"
    example_cases: tuple[str, ...]  # 2〜3 件
    confidence: float = RULES_VIEWPOINT_CONFIDENCE
    evidence: SourceEvidence | None = None


@dataclass(frozen=True)
class AbnormalScenario:
    scenario_id: str  # 例: "AS001"
    category: str  # "入力値異常" / "認証" / "ネットワーク" / "業務フロー" / "セキュリティ"
    title: str  # シナリオタイトル
    description: str  # 詳細説明（日本語）
    affected_fields: tuple[str, ...]  # 影響フィールド名
    risk_level: str  # "高" / "中" / "低"
    test_steps: tuple[str, ...]  # テストステップ（日本語）


# ---------- ルールベース生成 ----------


def _default_screen_evidence(screenshot_path: str | None = None) -> SourceEvidence:
    """画面全体を根拠とする SourceEvidence を構築する（画面分類由来の観点用）。"""
    return SourceEvidence(
        selector="body",
        html_attribute=None,
        screenshot_path=screenshot_path,
        bbox=None,
    )


def _evidence_of_field(field: Any, html_attribute: str | None = None) -> SourceEvidence | None:
    """フィールドから根拠を取り出す。evidence がなければ name からセレクタを構築する。"""
    evidence = getattr(field, "evidence", None)
    if isinstance(evidence, SourceEvidence):
        if html_attribute is not None:
            return replace(evidence, html_attribute=html_attribute)
        return evidence
    name = str(getattr(field, "name", "") or "")
    if name:
        return SourceEvidence(selector=f"[name='{name}']", html_attribute=html_attribute)
    return None


def generate_viewpoints_by_rules(
    screen_classification: ScreenClassification,
    field_data_list: list,  # list[FieldData]
    screen_evidence: SourceEvidence | None = None,
) -> list[TestViewpoint]:
    """画面分類とフィールド情報からテスト観点を生成する（オフライン動作）。

    ルール由来のため全観点 confidence=1.0 固定で、根拠（evidence）を必ず付与する。
    """
    screen_ev = screen_evidence or _default_screen_evidence()
    viewpoints: list[TestViewpoint] = []

    viewpoints.extend(
        replace(v, confidence=RULES_VIEWPOINT_CONFIDENCE, evidence=screen_ev)
        for v in _screen_type_viewpoints(screen_classification.screen_type)
    )
    viewpoints.extend(_field_viewpoints(field_data_list))

    # 全画面共通: 正常系確認
    viewpoints.append(
        TestViewpoint(
            category="機能",
            viewpoint="正常系の基本動作確認",
            risk_level="低",
            example_cases=("期待する入力で操作が正常に完了すること", "遷移先が正しいこと"),
            confidence=RULES_VIEWPOINT_CONFIDENCE,
            evidence=screen_ev,
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
    """フィールド属性から追加観点を生成する（根拠は該当フィールドの evidence）。"""
    viewpoints: list[TestViewpoint] = []
    required_field = next((f for f in field_data_list if getattr(f, "required", False)), None)
    maxlength_field = next(
        (f for f in field_data_list if getattr(f, "maxlength", None) is not None), None
    )

    if required_field is not None:
        viewpoints.append(
            TestViewpoint(
                category="機能",
                viewpoint="必須フィールドの未入力エラー",
                risk_level="中",
                example_cases=(
                    "必須項目を空で送信したときにエラーが表示されること",
                    "必須項目に値を入力すれば送信できること",
                ),
                confidence=RULES_VIEWPOINT_CONFIDENCE,
                evidence=_evidence_of_field(required_field, html_attribute="required"),
            )
        )
    if maxlength_field is not None:
        viewpoints.append(
            TestViewpoint(
                category="機能",
                viewpoint="最大文字数境界値のテスト",
                risk_level="低",
                example_cases=(
                    "最大文字数ちょうどで入力できること",
                    "最大文字数 +1 文字では入力または送信が拒否されること",
                ),
                confidence=RULES_VIEWPOINT_CONFIDENCE,
                evidence=_evidence_of_field(maxlength_field, html_attribute="maxlength"),
            )
        )
    return viewpoints


# ---------- 異常系シナリオ生成（ルールベース） ----------


def generate_abnormal_scenarios_by_rules(
    screen_classification: Any,  # ScreenClassification
    field_data_list: list,  # list[FieldData]
) -> list[AbnormalScenario]:
    """画面分類とフィールド情報からルールベースで異常系シナリオを生成する。"""
    raw: list[AbnormalScenario] = []

    raw.extend(_common_abnormal_scenarios())
    raw.extend(_screen_type_abnormal_scenarios(screen_classification.screen_type))
    raw.extend(_field_abnormal_scenarios(field_data_list))

    seen: set[str] = set()
    unique: list[AbnormalScenario] = []
    for s in raw:
        if s.title not in seen:
            seen.add(s.title)
            unique.append(s)

    return [
        AbnormalScenario(
            scenario_id=f"AS{i + 1:03d}",
            category=s.category,
            title=s.title,
            description=s.description,
            affected_fields=s.affected_fields,
            risk_level=s.risk_level,
            test_steps=s.test_steps,
        )
        for i, s in enumerate(unique)
    ]


def _make_scenario(**kwargs: Any) -> AbnormalScenario:
    """一時的な scenario_id="AS000" で AbnormalScenario を生成するヘルパー。"""
    return AbnormalScenario(
        scenario_id="AS000",
        category=kwargs["category"],
        title=kwargs["title"],
        description=kwargs["description"],
        affected_fields=kwargs.get("affected_fields", ()),
        risk_level=kwargs["risk_level"],
        test_steps=kwargs["test_steps"],
    )


def _common_abnormal_scenarios() -> list[AbnormalScenario]:
    """全画面共通の異常系シナリオを返す。"""
    return [
        _make_scenario(
            category="セキュリティ",
            title="SQLインジェクション攻撃",
            description="文字列フィールドに ' OR 1=1 -- を入力してSQLインジェクションを試みる。",
            affected_fields=(),
            risk_level="高",
            test_steps=(
                "対象画面を開く",
                "文字列入力フィールドに ' OR 1=1 -- を入力する",
                "送信し、エラーメッセージまたは異常な応答が返らないことを確認する",
            ),
        ),
        _make_scenario(
            category="セキュリティ",
            title="XSS（クロスサイトスクリプティング）攻撃",
            description="文字列フィールドに <script>alert(1)</script> を入力してXSSを試みる。",
            affected_fields=(),
            risk_level="高",
            test_steps=(
                "対象画面を開く",
                "文字列入力フィールドに <script>alert(1)</script> を入力する",
                "送信し、スクリプトが実行されないことを確認する",
            ),
        ),
        _make_scenario(
            category="入力値異常",
            title="超長文字列入力",
            description="文字列フィールドに10,000文字の入力を行い、システムの挙動を確認する。",
            affected_fields=(),
            risk_level="中",
            test_steps=(
                "対象画面を開く",
                "文字列入力フィールドに10,000文字の文字列を入力する",
                "送信し、適切なエラーまたは制限が働くことを確認する",
            ),
        ),
        _make_scenario(
            category="入力値異常",
            title="nullバイト混入",
            description="文字列フィールドにnullバイト（\\x00）を含む文字列を入力してシステムの挙動を確認する。",
            affected_fields=(),
            risk_level="中",
            test_steps=(
                "対象画面を開く",
                "文字列入力フィールドにnullバイト（\\x00）を含む文字列を入力する",
                "送信し、異常な挙動が発生しないことを確認する",
            ),
        ),
    ]


def _screen_type_abnormal_scenarios(screen_type: str) -> list[AbnormalScenario]:
    """画面種別固有の異常系シナリオを返す。"""
    if screen_type == SCREEN_AUTH:
        return [
            _make_scenario(
                category="認証",
                title="ブルートフォース攻撃（連続ログイン失敗）",
                description="同一IPから100回連続でログイン失敗を試み、アカウントロックが機能することを確認する。",
                affected_fields=(),
                risk_level="高",
                test_steps=(
                    "ログインページを開く",
                    "パスワードフィールドに100回連続で誤ったパスワードを入力する",
                    "アカウントロックが発生することを確認する",
                ),
            ),
            _make_scenario(
                category="認証",
                title="セッション固定攻撃",
                description="ログイン前後でsession_idが変わらない脆弱性を確認する。",
                affected_fields=(),
                risk_level="高",
                test_steps=(
                    "ログイン前のsession_idを記録する",
                    "正常にログインする",
                    "ログイン後のsession_idがログイン前と異なることを確認する",
                ),
            ),
            _make_scenario(
                category="ユーザビリティ",
                title="パスワードのクリップボード貼り付けログイン",
                description="パスワードをクリップボードから貼り付けてログインできることを確認する。",
                affected_fields=(),
                risk_level="低",
                test_steps=(
                    "ログインページを開く",
                    "パスワードをクリップボードにコピーする",
                    "パスワードフィールドに貼り付けてログインする",
                    "正常にログインできることを確認する",
                ),
            ),
        ]
    if screen_type == SCREEN_PAYMENT:
        return [
            _make_scenario(
                category="業務フロー",
                title="決済の二重送信",
                description="ネットワーク遅延中にsubmitボタンを2回クリックして二重課金が発生しないことを確認する。",
                affected_fields=(),
                risk_level="高",
                test_steps=(
                    "決済画面を開き、決済情報を入力する",
                    "ネットワーク遅延を模擬した状態でsubmitボタンを2回クリックする",
                    "決済が1回のみ処理されることを確認する",
                ),
            ),
            _make_scenario(
                category="業務フロー",
                title="決済中のブラウザバック",
                description="決済処理中にブラウザの戻るボタンを押して、データ不整合が発生しないことを確認する。",
                affected_fields=(),
                risk_level="高",
                test_steps=(
                    "決済画面を開き、決済情報を入力して送信する",
                    "処理中にブラウザの戻るボタンを押す",
                    "決済状態およびデータに不整合が発生しないことを確認する",
                ),
            ),
            _make_scenario(
                category="業務フロー",
                title="タイムアウト直前の送信",
                description="セッションタイムアウト直前に決済を送信し、適切なエラーハンドリングが行われることを確認する。",
                affected_fields=(),
                risk_level="中",
                test_steps=(
                    "決済画面を開き、セッションがタイムアウト直前になるまで待つ",
                    "決済情報を入力して送信する",
                    "タイムアウトエラーまたは適切なメッセージが表示されることを確認する",
                ),
            ),
        ]
    return []


def _field_abnormal_scenarios(field_data_list: list) -> list[AbnormalScenario]:
    """フィールド属性から異常系シナリオを生成する。"""
    scenarios: list[AbnormalScenario] = []

    required_fields = [
        getattr(f, "name", "") for f in field_data_list if getattr(f, "required", False)
    ]
    if required_fields:
        scenarios.append(
            _make_scenario(
                category="入力値異常",
                title="必須フィールドを空にして送信",
                description="必須フィールドを空のまま送信し、バリデーションエラーが発生することを確認する。",
                affected_fields=tuple(required_fields),
                risk_level="中",
                test_steps=(
                    "対象画面を開く",
                    "必須フィールドを空のままにする",
                    "送信ボタンをクリックし、バリデーションエラーが表示されることを確認する",
                ),
            )
        )

    maxlength_fields = [
        (getattr(f, "name", ""), getattr(f, "maxlength", None))
        for f in field_data_list
        if getattr(f, "maxlength", None) is not None
    ]
    if maxlength_fields:
        field_name, maxlength = maxlength_fields[0]
        scenarios.append(
            _make_scenario(
                category="入力値異常",
                title="maxlength+1文字を入力して送信",
                description=f"最大文字数（{maxlength}）を超える文字列を入力して送信し、適切なエラーが発生することを確認する。",
                affected_fields=(field_name,) if field_name else (),
                risk_level="低",
                test_steps=(
                    "対象画面を開く",
                    f"maxlength制限のあるフィールドに{maxlength}+1文字を入力する",
                    "送信し、入力または送信が拒否されることを確認する",
                ),
            )
        )

    return scenarios


# ---------- LLM 版（異常系シナリオ） ----------


_ABNORMAL_SCENARIO_CATEGORIES = ("入力値異常", "認証", "ネットワーク", "業務フロー", "セキュリティ")

ABNORMAL_SCENARIO_SCHEMA_NAME = "abnormal_scenarios"

ABNORMAL_SCENARIO_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "scenarios": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": list(_ABNORMAL_SCENARIO_CATEGORIES)},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "affected_fields": {"type": "array", "items": {"type": "string"}},
                    "risk_level": {"type": "string", "enum": list(_RISK_LEVELS)},
                    "test_steps": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "category",
                    "title",
                    "description",
                    "affected_fields",
                    "risk_level",
                    "test_steps",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["scenarios"],
    "additionalProperties": False,
}


def generate_abnormal_scenarios_with_llm(
    screen_classification: Any,
    field_data_list: list,
    api_key: str = "",
) -> list[AbnormalScenario]:
    """LLMを使って異常系シナリオを生成し、失敗時はルールベースへフォールバックする。"""
    if not api_key:
        logger.info("api_key が未設定のためルールベースにフォールバックします。")
        return generate_abnormal_scenarios_by_rules(screen_classification, field_data_list)
    try:
        return _call_llm_for_abnormal_scenarios(screen_classification, field_data_list, api_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "LLM 異常系シナリオ応答を棄却しました（理由: %s）。ルールベースにフォールバックします。",
            exc,
        )
        return generate_abnormal_scenarios_by_rules(screen_classification, field_data_list)


def _call_llm_for_abnormal_scenarios(
    screen_classification: Any,
    field_data_list: list,
    api_key: str,
) -> list[AbnormalScenario]:
    """OpenAI API（Structured Outputs）で異常系シナリオを取得する。"""
    from llm.openai_client import request_structured_json

    screen_info = {
        "screen_type": screen_classification.screen_type,
        "field_count": len(field_data_list),
    }
    prompt = (
        "あなたは QA エンジニアです。以下の Web 画面情報に基づき異常系テストシナリオを返してください。\n"
        f"画面情報: {json.dumps(screen_info, ensure_ascii=False)}\n\n"
        "各シナリオは以下のキーを持つこと: "
        "category(入力値異常/認証/ネットワーク/業務フロー/セキュリティ), "
        "title(シナリオタイトル), description(詳細説明), "
        "affected_fields(影響フィールド名の配列), "
        "risk_level(高/中/低), test_steps(テストステップ配列 2〜4 件)"
    )
    parsed = request_structured_json(
        api_key,
        _LLM_MODEL,
        prompt,
        ABNORMAL_SCENARIO_SCHEMA_NAME,
        ABNORMAL_SCENARIO_JSON_SCHEMA,
    )
    items = parsed.get("scenarios", [])
    return [
        AbnormalScenario(
            scenario_id=f"AS{i + 1:03d}",
            category=str(item["category"]),
            title=str(item["title"]),
            description=str(item["description"]),
            affected_fields=tuple(str(f) for f in item.get("affected_fields", [])),
            risk_level=str(item["risk_level"]),
            test_steps=tuple(str(s) for s in item.get("test_steps", [])),
        )
        for i, item in enumerate(items)
    ]


# ---------- LLM 版（LLMProvider 抽象から利用されるスキーマ・検証ユーティリティ） ----------

VIEWPOINT_SCHEMA_NAME = "test_viewpoints"

# OpenAI Structured Outputs（strict）用 JSON Schema
VIEWPOINT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "viewpoints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": list(_CATEGORIES)},
                    "viewpoint": {"type": "string"},
                    "risk_level": {"type": "string", "enum": list(_RISK_LEVELS)},
                    "example_cases": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["category", "viewpoint", "risk_level", "example_cases"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["viewpoints"],
    "additionalProperties": False,
}


class ViewpointValidationError(ValueError):
    """LLM 観点応答のスキーマ違反・カテゴリ不正を表す例外。"""


def build_viewpoint_prompt(screen_info: dict) -> str:
    """観点生成用プロンプトを構築する。"""
    return (
        "あなたは QA エンジニアです。以下の Web 画面情報に基づきテスト観点を返してください。\n"
        f"画面情報: {json.dumps(screen_info, ensure_ascii=False)}\n\n"
        "各観点は以下のキーを持つこと: "
        "category(機能/セキュリティ/ユーザビリティ/パフォーマンス/アクセシビリティ), "
        "viewpoint(観点説明), risk_level(高/中/低), example_cases(文字列配列 2〜3 件)"
    )


def validate_viewpoint_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """LLM 応答のスキーマ・カテゴリ整合を検証し、観点 dict のリストを返す。

    違反があれば ``ViewpointValidationError`` を送出する（呼び出し側でルールへフォールバック）。
    """
    items = payload.get("viewpoints")
    if not isinstance(items, list) or not items:
        raise ViewpointValidationError("viewpoints 配列がありません。")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ViewpointValidationError(f"観点 {index} がオブジェクトではありません。")
        category = item.get("category")
        if category not in _CATEGORIES:
            raise ViewpointValidationError(f"観点 {index} のカテゴリが不正です: {category!r}")
        viewpoint = item.get("viewpoint")
        if not isinstance(viewpoint, str) or not viewpoint.strip():
            raise ViewpointValidationError(f"観点 {index} の viewpoint が不正です。")
        risk_level = item.get("risk_level")
        if risk_level not in _RISK_LEVELS:
            raise ViewpointValidationError(f"観点 {index} の risk_level が不正です: {risk_level!r}")
        cases = item.get("example_cases")
        if not isinstance(cases, list) or not all(isinstance(c, str) for c in cases):
            raise ViewpointValidationError(f"観点 {index} の example_cases が不正です。")
    return items


def llm_viewpoint_confidence(item: dict[str, Any]) -> float:
    """スキーマ検証・ルール整合検証の通過状況から LLM 観点の確信度を算出する。

    検証を通過した時点で 0.7、example_cases が規定の 2〜3 件であれば +0.2（最大 0.9）。
    """
    cases = item.get("example_cases") or []
    bonus = (
        LLM_EXAMPLE_CASES_BONUS
        if _EXAMPLE_CASES_MIN <= len(cases) <= _EXAMPLE_CASES_MAX
        else 0.0
    )
    return round(LLM_BASE_CONFIDENCE + bonus, 2)


def fallback_classification(screen_info: dict) -> ScreenClassification:
    """screen_info から分類を取り出す。なければ general 分類を返す。"""
    sc_raw = screen_info.get("screen_classification")
    if isinstance(sc_raw, ScreenClassification):
        return sc_raw
    return ScreenClassification(SCREEN_GENERAL, 0.5, (), "low")


def make_provider(api_key: str = "", model: str = "") -> LLMProvider:
    """API キーの有無に応じて観点生成プロバイダを返す。"""
    from llm.provider import LLMProvider, OpenAIProvider, RulesProvider  # noqa: F401

    if api_key:
        return OpenAIProvider(api_key, model)
    return RulesProvider()
