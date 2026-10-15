"""ホーム（SCR-06-01）の集計。契約: WS2D-DD-006 6 章・BD-006 6 章。

入力の dict/list は変更せず、新しい dict/list を返す。
"""
from __future__ import annotations

from web.services.docverify import metrics

_MAX_ACTIONS = 5
_NO_DUE = "9999-99-99"  # 期限なしは最後に並べる
# kind → (優先順, view, label の書式)。DD 6.1 の表で固定
_ACTIONS = {
    "critical": (0, "triage", "重大な指摘 {n} 件に対応する"),
    "candidates": (1, "triage", "未検討の候補 {n} 件を仕分ける"),
    "answers": (2, "questions", "回答待ちの質問 {n} 件の回答を取り込む"),
    "my_review": (3, "read", "自分の確認を終える"),
    "no_document": (4, "plan", "文書を取り込む"),
    "ready_to_close": (5, "gate", "出口基準を満たしました。判定して終える"),
}


def _is_open(review: dict) -> bool:
    # close() は status だけを closed にするため、phase と status の両方で終了を見る
    return review.get("phase") != "closed" and review.get("status") != "closed"


def _findings(review: dict) -> list[dict]:
    return review.get("findings") or []


def _labels() -> dict:
    return getattr(metrics, "ITEM_LABEL", None) or getattr(metrics, "_ITEM_LABEL", {})


def awaiting_answers(review: dict) -> int:
    """回答待ちの質問数（BD 6 章）。終了したレビューは 0。"""
    if not _is_open(review):
        return 0
    return sum(1 for f in _findings(review)
               if f.get("certainty") == "要確認" and f.get("status") != "rejected"
               and not str(f.get("answer") or "").strip())


def _count(review: dict, status: str) -> int:
    return sum(1 for f in _findings(review) if f.get("status") == status)


def _mine(reviews: list[dict], me: str) -> list[dict]:
    return [{"review_id": r["id"], "review_name": r.get("name"), "role": p.get("role"),
             "done": bool(p.get("done")), "phase": r.get("phase"), "due": r.get("due")}
            for r in reviews for p in r.get("participants") or [] if p.get("name") == me]


def _active_row(review: dict, summary: dict) -> dict:
    return {"review_id": review["id"], "review_name": review.get("name"), "phase": review.get("phase"),
            "due": review.get("due"), "findings": len(_findings(review)),
            "quality_overall": (summary.get("quality") or {}).get("overall"),
            "open": _count(review, "adopted"), "open_critical": summary.get("open_critical", 0),
            "candidates": _count(review, "candidate"),
            "updated_at": review.get("updated_at") or review.get("created_at"),
            "versions": len(review.get("versions") or []),
            "document_name": (review.get("document") or {}).get("name")}


def _avg(values: list) -> int | None:
    vals = [v for v in values if v is not None]
    return int(sum(vals) / len(vals) + 0.5) if vals else None  # 四捨五入（round は偶数丸め）


def average_quality(summaries: list[dict]) -> dict:
    """進行中レビューの品質スコアの平均（None を除く・四捨五入）。対象 0 件は None。"""
    quals = [s.get("quality") or {} for s in summaries]
    labels = _labels()
    keys = list(dict.fromkeys(k for q in quals for k in (q.get("items") or {})))
    items = {}
    for k in keys:
        cells = [(q.get("items") or {}).get(k) or {} for q in quals]
        label = next((c["label"] for c in cells if c.get("label")), labels.get(k, k))
        items[k] = {"score": _avg([c.get("score") for c in cells]), "label": label}
    overalls = [q.get("overall") for q in quals]
    return {"overall": _avg(overalls), "items": items, "n_reviews": len(summaries),
            "n_scored": sum(1 for v in overalls if v is not None)}


def _action(review: dict, kind: str, n: int = 0) -> dict:
    _, view, fmt = _ACTIONS[kind]
    return {"review_id": review["id"], "review_name": review.get("name"), "kind": kind,
            "view": view, "label": fmt.format(n=n)}


def _actions_for(review: dict, me: str) -> list[dict]:
    summary = metrics.summary(review)
    out = []
    counts = (("critical", summary.get("open_critical", 0)), ("candidates", _count(review, "candidate")),
              ("answers", awaiting_answers(review)))
    out += [_action(review, kind, n) for kind, n in counts if n > 0]
    if any(p.get("name") == me and p.get("role") == "reviewer" and not p.get("done")
           for p in review.get("participants") or []):
        out.append(_action(review, "my_review"))
    if not review.get("document"):
        out.append(_action(review, "no_document"))
    if summary.get("exit_ok"):
        out.append(_action(review, "ready_to_close"))
    return out


def next_actions(reviews: list[dict], me: str) -> tuple[list[dict], str]:
    """次にやること（最大 5 件）と対象範囲。自分が参加者の進行中レビューが無ければ進行中すべて。"""
    live = [r for r in reviews if _is_open(r)]
    mine = [r for r in live if any(p.get("name") == me for p in r.get("participants") or [])]
    scope, targets = ("mine", mine) if mine else ("active", live)
    due = {r["id"]: r.get("due") or _NO_DUE for r in targets}
    items = [a for r in targets for a in _actions_for(r, me)]
    ranked = sorted(items, key=lambda a: (_ACTIONS[a["kind"]][0], due[a["review_id"]]))
    return ranked[:_MAX_ACTIONS], scope


def build(reviews: list[dict], me: str) -> dict:
    """GET /api/docverify/home の応答（DD 6.1）。"""
    live = [r for r in reviews if _is_open(r)]
    summaries = [metrics.summary(r) for r in live]
    mine = _mine(reviews, me)
    active = [_active_row(r, s) for r, s in zip(live, summaries)]
    open_f = [f for r in reviews for f in _findings(r) if f.get("status") == "adopted"]  # 候補は未対応に数えない
    counts = {"mine": sum(1 for m in mine if not m["done"]), "active": len(active),
              "open_findings": len(open_f),
              "open_critical": sum(1 for f in open_f if f.get("severity") == "critical"),
              "awaiting_answers": sum(awaiting_answers(r) for r in live)}
    actions, scope = next_actions(reviews, me)
    return {"me": me, "mine": mine, "active": active, "counts": counts,
            "quality": average_quality(summaries), "next_actions": actions, "next_scope": scope}
