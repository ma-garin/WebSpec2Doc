"""要確認キュー: AI 下書きのうち「人が見るべき項目」を選び出す。

AutoRun は既定で自律的に成果物を作る。人が全項目を承認していては
「URL を入れたら出てくる」利点が消えるため、介入は例外に絞る。

判定は 2 軸:

- 信頼度 (confidence): measured（実測）> user（人が確定）> llm（LLM 提案）> assumed（前提）
- リスク (risk): 決済・認証など、間違えたときの影響が大きい領域か

「AI 由来（llm / assumed）」または「高リスク」を要確認とし、それ以外
（実測 × 低〜中リスク）は自動承認の対象にする。実測でも高リスクな領域は
人が見る——観測できていても、影響の大きさは観測では下がらないため。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: 信頼度。値が小さいほど強い根拠。
CONFIDENCE_MEASURED = "measured"
CONFIDENCE_USER = "user"
CONFIDENCE_LLM = "llm"
CONFIDENCE_ASSUMED = "assumed"

#: 人の確認を要する信頼度（AI 由来）
AI_DERIVED_CONFIDENCES = frozenset({CONFIDENCE_LLM, CONFIDENCE_ASSUMED})

RISK_HIGH = "high"
RISK_MEDIUM = "med"
RISK_LOW = "low"

#: 高リスク領域を示す語。間違えると金銭・認証・個人情報に影響する。
_HIGH_RISK_KEYWORDS: tuple[str, ...] = (
    "決済",
    "支払",
    "purchase",
    "payment",
    "checkout",
    "billing",
    "認証",
    "ログイン",
    "login",
    "signin",
    "sign-in",
    "auth",
    "パスワード",
    "password",
    "個人情報",
    "personal",
    "private",
    "削除",
    "delete",
    "管理",
    "admin",
)

#: 中リスク領域を示す語。業務データは変わるが金銭・認証ほどではない。
_MEDIUM_RISK_KEYWORDS: tuple[str, ...] = (
    "カート",
    "cart",
    "注文",
    "order",
    "在庫",
    "stock",
    "登録",
    "register",
    "更新",
    "update",
    "送信",
    "submit",
)

_CONFIDENCE_LABELS = {
    CONFIDENCE_MEASURED: "実測",
    CONFIDENCE_USER: "人が確定",
    CONFIDENCE_LLM: "LLM提案",
    CONFIDENCE_ASSUMED: "前提",
}

_RISK_LABELS = {RISK_HIGH: "高", RISK_MEDIUM: "中", RISK_LOW: "低"}


@dataclass(frozen=True)
class ReviewEntry:
    """要確認キューの 1 行。段階をまたいで項目を横断的に並べる。"""

    stage_id: str
    stage_name: str
    step_no: int
    item_id: str
    title: str
    detail: str
    confidence: str
    risk: str
    needs_review: bool
    approved: bool
    #: なぜ人が見る必要があるのか（見ないでよい場合は自動承認の理由）
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "stage_name": self.stage_name,
            "step_no": self.step_no,
            "item_id": self.item_id,
            "title": self.title,
            "detail": self.detail,
            "confidence": self.confidence,
            "confidence_label": _CONFIDENCE_LABELS.get(self.confidence, self.confidence),
            "risk": self.risk,
            "risk_label": _RISK_LABELS.get(self.risk, self.risk),
            "needs_review": self.needs_review,
            "approved": self.approved,
            "reason": self.reason,
        }


def confidence_of(item: Any) -> str:
    """項目の信頼度を返す。前提は source より優先する（最も弱い根拠のため）。"""
    if getattr(item, "assumed", False):
        return CONFIDENCE_ASSUMED
    source = str(getattr(item, "source", "") or "")
    if source == "llm":
        return CONFIDENCE_LLM
    if source == "user":
        return CONFIDENCE_USER
    return CONFIDENCE_MEASURED


def risk_of(item: Any, page_urls: dict[str, str] | None = None) -> str:
    """項目のリスクを返す。題名・詳細と、紐づく画面 URL の双方を見る。"""
    haystack = " ".join(
        [
            str(getattr(item, "title", "") or ""),
            str(getattr(item, "detail", "") or ""),
            _page_text(item, page_urls or {}),
        ]
    ).lower()
    if any(keyword in haystack for keyword in _HIGH_RISK_KEYWORDS):
        return RISK_HIGH
    if any(keyword in haystack for keyword in _MEDIUM_RISK_KEYWORDS):
        return RISK_MEDIUM
    return RISK_LOW


def _page_text(item: Any, page_urls: dict[str, str]) -> str:
    """項目 data の画面参照から URL を引き当てて結合する。"""
    data = getattr(item, "data", None)
    if not isinstance(data, dict) or not page_urls:
        return ""
    refs: list[str] = []
    page_id = data.get("page_id")
    if page_id:
        refs.append(str(page_id))
    screen_ids = data.get("screen_ids")
    if isinstance(screen_ids, list | tuple):
        refs.extend(str(s) for s in screen_ids)
    return " ".join(page_urls.get(ref, "") for ref in refs)


def needs_review(confidence: str, risk: str) -> bool:
    """人の確認が要るか。AI 由来、または高リスクなら要確認。"""
    return confidence in AI_DERIVED_CONFIDENCES or risk == RISK_HIGH


def review_reason(confidence: str, risk: str) -> str:
    """要確認/自動承認の理由を、利用者に読める言葉で返す。"""
    if confidence == CONFIDENCE_ASSUMED:
        return "観測できず前提を置いています。実環境での確認が必要です。"
    if confidence == CONFIDENCE_LLM:
        return "LLM の提案です。採否は人が判断してください。"
    if risk == RISK_HIGH:
        return "実測ですが、決済・認証など影響の大きい領域のため確認を推奨します。"
    return "実測に基づき、影響の小さい領域のため自動承認の対象です。"


def page_urls_from_report(report: dict[str, Any] | None) -> dict[str, str]:
    """report.json から画面 ID → URL の対応を作る。欠損時は空。"""
    if not isinstance(report, dict):
        return {}
    urls: dict[str, str] = {}
    for page in report.get("pages") or []:
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("page_id") or page.get("id") or "")
        url = str(page.get("url") or "")
        if page_id and url:
            urls[page_id] = url
    return urls


def build_review_queue(pipeline: Any, page_urls: dict[str, str] | None = None) -> list[ReviewEntry]:
    """全段階の項目を横断して要確認キューを組み立てる。

    段階の順（step_no）を保ったまま項目を平坦に並べる。工程を辿らせるためではなく、
    同じ観点が複数段階に散らばっていても 1 つのリストで捌けるようにするため。
    """
    entries: list[ReviewEntry] = []
    for stage in getattr(pipeline, "stages", ()) or ():
        definition = stage.definition
        for item in stage.items:
            confidence = confidence_of(item)
            risk = risk_of(item, page_urls)
            entries.append(
                ReviewEntry(
                    stage_id=stage.stage_id,
                    stage_name=definition.name,
                    step_no=definition.step_no,
                    item_id=item.item_id,
                    title=item.title,
                    detail=item.detail,
                    confidence=confidence,
                    risk=risk,
                    needs_review=needs_review(confidence, risk),
                    approved=bool(item.approved),
                    reason=review_reason(confidence, risk),
                )
            )
    return entries


def summarize(entries: list[ReviewEntry]) -> dict[str, int]:
    """キューの件数サマリ。UI の進捗表示と確定可否の判定に使う。"""
    review = [e for e in entries if e.needs_review]
    return {
        "total": len(entries),
        "review": len(review),
        "review_done": len([e for e in review if e.approved]),
        "review_pending": len([e for e in review if not e.approved]),
        "auto": len([e for e in entries if not e.needs_review]),
        "approved": len([e for e in entries if e.approved]),
    }
