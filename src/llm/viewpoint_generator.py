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
from typing import Any

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
        import openai  # noqa: F401
    except ImportError:
        logger.warning("openai パッケージが見つからないためルールベースにフォールバックします。")
        return generate_abnormal_scenarios_by_rules(screen_classification, field_data_list)
    try:
        return _call_llm_for_abnormal_scenarios(screen_classification, field_data_list, api_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM abnormal scenario generation failed, falling back to rules: %s", exc)
        return generate_abnormal_scenarios_by_rules(screen_classification, field_data_list)


def _call_llm_for_abnormal_scenarios(
    screen_classification: Any,
    field_data_list: list,
    api_key: str,
) -> list[AbnormalScenario]:
    """OpenAI API を呼び出して異常系シナリオ JSON 配列を取得する。"""
    screen_info = {
        "screen_type": screen_classification.screen_type,
        "field_count": len(field_data_list),
    }
    prompt = (
        "あなたは QA エンジニアです。以下の Web 画面情報に基づき異常系テストシナリオを JSON 配列で返してください。\n"
        f"画面情報: {json.dumps(screen_info, ensure_ascii=False)}\n\n"
        "各要素は以下のキーを持つこと: "
        "category(入力値異常/認証/ネットワーク/業務フロー/セキュリティ), "
        "title(シナリオタイトル), description(詳細説明), "
        "affected_fields(影響フィールド名の配列), "
        "risk_level(高/中/低), test_steps(テストステップ配列 2〜4 件)"
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
    items = parsed if isinstance(parsed, list) else parsed.get("scenarios", [])
    raw = [
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
    return raw


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
