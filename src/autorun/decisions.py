"""実行条件の確定（AutoRun）。

AutoRun は観測では決められない事項を「前提」として置いて止まらずに進む。
以前はそれを「要確認」という名前で一覧し、人にチェックさせていたが、
これはシステム側の都合の名前だった。人から見れば確認事項ではなく
**自分が決めるべきこと**であり、AI が仮置きした結果を追認させる形になっていた。

ここでは前提を **質問** に変換する。答えは2択で、推奨をあらかじめ選んだ状態で
提示する。そのままなら押すだけで済み、違うなら選び直すか自由入力で指示する。

原則:
- 選択の余地がないものは質問にしない（事実として別に出す）
- 推奨は必ず1つに決める。「お好みで」は出さない
- 推奨の理由を必ず添える。なぜそれを勧めるのか分からない選択肢は出さない
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 自由入力を受け付ける選択肢のキー
FREE_TEXT = "custom"


@dataclass(frozen=True)
class Choice:
    """2択の片方。"""

    key: str
    label: str
    detail: str
    # 選ぶと自由入力欄が必要になるか（例: 合否基準を自分で決める）
    needs_text: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "detail": self.detail,
            "needs_text": self.needs_text,
        }


@dataclass(frozen=True)
class Decision:
    """人が決める1件。前提1件に対して1問を対応させる。"""

    decision_id: str
    # 対応する前提項目（stages.py の StageItem.item_id）
    source_item_id: str
    question: str
    context: str
    recommended: str
    choices: tuple[Choice, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "source_item_id": self.source_item_id,
            "question": self.question,
            "context": self.context,
            "recommended": self.recommended,
            "choices": [c.to_dict() for c in self.choices],
        }


# 前提項目 → 質問 の対応表。
# stages.py が置く前提のうち、**人が決めるべきもの**だけをここに載せる。
# 載っていない前提（例: 基準の確立）は質問にせず、事実として別途提示する。
_DECISION_SPECS: dict[str, dict[str, Any]] = {
    "plan-assume-auth": {
        "decision_id": "auth_scope",
        "question": "ログインが必要な画面もテストしますか？",
        "context": "ロール別の期待結果が指定されていません。",
        "recommended": "public_only",
        "choices": (
            Choice(
                key="public_only",
                label="未ログインの範囲だけ",
                detail="認証情報が未登録のため、到達できる画面だけを対象にします。",
            ),
            Choice(
                key="authenticated",
                label="ログインしてテスト",
                detail="認証情報の登録が必要です。登録画面へ進みます。",
            ),
        ),
    },
    "plan-assume-sideeffect": {
        "decision_id": "side_effect",
        "question": "フォームの送信まで実行しますか？",
        "context": "送信すると、対象サイトに実データが登録されます。",
        "recommended": "observe_only",
        "choices": (
            Choice(
                key="observe_only",
                label="送信しない（入力だけ）",
                detail="入力検証だけを観測します。相手先にデータが残りません。",
            ),
            Choice(
                key="submit",
                label="送信まで実行",
                detail="注文・決済・メール送信が実際に発生します。",
            ),
        ),
    },
    "plan-assume-exit": {
        "decision_id": "exit_criteria",
        "question": "合否はどう判定しますか？",
        "context": "リリース判定基準の指定がありません。",
        "recommended": "severity",
        "choices": (
            Choice(
                key="severity",
                label="重大度で整理して人が判断",
                detail="高・中・低に分けて提示します。自動では合否を出しません。",
            ),
            Choice(
                key=FREE_TEXT,
                label="基準を指定する",
                detail="例: 高リスクが0件なら合格、中リスクは3件まで許容",
                needs_text=True,
            ),
        ),
    },
    "plan-assume-browser": {
        "decision_id": "browser",
        "question": "どのブラウザで確認しますか？",
        "context": "指定がない場合は検証済みの実行環境を使います。",
        "recommended": "chromium",
        "choices": (
            Choice(
                key="chromium",
                label="Chromium（PC）",
                detail="動作確認済みの実行環境です。",
            ),
            Choice(
                key=FREE_TEXT,
                label="他を指定",
                detail="例: Firefox で確認したい",
                needs_text=True,
            ),
        ),
    },
}


def build_decisions(assumed_item_ids: list[str]) -> list[Decision]:
    """置かれた前提のうち、人が決めるべきものを質問に変換する。

    対応表に無い前提は質問にしない。選択の余地がないものを質問の形にすると、
    答えようのない問いを突きつけることになる。
    """
    decisions: list[Decision] = []
    for item_id in assumed_item_ids:
        spec = _DECISION_SPECS.get(item_id)
        if spec is None:
            continue
        decisions.append(
            Decision(
                decision_id=str(spec["decision_id"]),
                source_item_id=item_id,
                question=str(spec["question"]),
                context=str(spec["context"]),
                recommended=str(spec["recommended"]),
                choices=tuple(spec["choices"]),
            )
        )
    return decisions


def facts_from_assumptions(
    assumed_items: list[tuple[str, str, str]],
) -> list[dict[str, str]]:
    """質問にしない前提を、事実として返す。

    引数は (item_id, title, detail) の並び。対応表に無いものだけを通す。
    「決めようがないこと」を隠さず出すために使う。
    """
    return [
        {"title": title, "detail": detail}
        for item_id, title, detail in assumed_items
        if item_id not in _DECISION_SPECS
    ]


def validate_answers(
    decisions: list[Decision], answers: dict[str, Any]
) -> tuple[dict[str, dict[str, str]], list[str]]:
    """回答を検証して正規化する。

    戻り値は (正規化済みの回答, エラーメッセージ). 未回答は推奨で補完する
    （そのまま実行できることが案Cの前提のため、未回答は不正にしない）。
    """
    normalized: dict[str, dict[str, str]] = {}
    errors: list[str] = []

    for decision in decisions:
        raw = answers.get(decision.decision_id)
        if not isinstance(raw, dict):
            raw = {}
        choice_key = str(raw.get("choice", "")).strip() or decision.recommended
        valid_keys = {c.key for c in decision.choices}
        if choice_key not in valid_keys:
            errors.append(f"{decision.question}: 不正な選択です")
            continue

        choice = next(c for c in decision.choices if c.key == choice_key)
        text = str(raw.get("text", "")).strip()
        if choice.needs_text and not text:
            errors.append(f"{decision.question}: 指定内容を入力してください")
            continue

        normalized[decision.decision_id] = {
            "choice": choice_key,
            "label": choice.label,
            "text": text,
            "source_item_id": decision.source_item_id,
            "used_recommendation": "1" if choice_key == decision.recommended else "",
        }

    return normalized, errors


def summarize(normalized: dict[str, dict[str, str]]) -> str:
    """監査ログ用に、確定した条件を1行へまとめる。"""
    if not normalized:
        return "実行条件の指定なし（すべて推奨）"
    parts = []
    for decision_id, answer in normalized.items():
        label = answer["label"]
        if answer["text"]:
            label += f"（{answer['text']}）"
        parts.append(f"{decision_id}={label}")
    return " / ".join(parts)
