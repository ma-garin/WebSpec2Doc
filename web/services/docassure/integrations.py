"""他システム向けの JSON 出力（System02 テスト候補 / System09 影響 / System01 実装突合）。

連携先の取り込み口は未結線。ここは JSON を返すだけで、送信・登録はしない（"wired": False）。
LLM は使わない。根拠のない種別の候補は作らず、観測できなかったものを欠陥と断定しない。
"""
from __future__ import annotations

import re
from typing import Any

from . import boundary
from .testability import NOT_TESTABLE, assess, unit_view

WIRED = False
RE_PERM = re.compile(r"権限|ロール|管理者|認可|許可|アクセス制御|閲覧可|編集可")
RE_NEG = re.compile(r"不正|無効|拒否|禁止|できない|未入力|必須")
RE_ERR = re.compile(r"エラー|失敗|異常|タイムアウト|例外")
RE_STATE = re.compile(r"状態|ステータス|遷移|承認済|未承認|有効|無効化")
RE_RECOV = re.compile(r"再試行|リトライ|復旧|復元|ロールバック|再開|再送")
RE_QUOTED = re.compile(r"[「『]([^」』]+)[」』]")
_BASE = {"state": "GENERATED", "execution": "NOT_EXECUTED", "verification": "NOT_VERIFIED"}


def _cand(rid: str, kind: str, title: str, given: str, when: str, then: str,
          data: Any = None, prov: str = "INFERRED") -> dict:
    return {"candidate_id": f"TC-{rid}-{kind}", "requirement_id": rid, "kind": kind, "title": title,
            "steps": [f"Given {given}", f"When {when}", f"Then {then}"], "data": data,
            **_BASE, "provenance": prov}


def test_candidates(units: list) -> list[dict]:
    """System02 向けテスト候補。NOT_TESTABLE は候補でなく required_clarification を返す。"""
    out: list[dict] = []
    for u in units:
        v = unit_view(u)
        rid, text = v["requirement_id"], v["text"]
        a = assess(u)
        if a["verdict"] == NOT_TESTABLE:
            out.append({"candidate_id": None, "requirement_id": rid, "kind": "required_clarification",
                        "required_clarification": True, "missing": a["missing"], "reasons": a["reasons"],
                        "wired": WIRED})
            continue
        subj = v["fields"].get("action") or v["raw_text"][:40]
        exp = v["fields"].get("expected_result") or "<要確認: 期待結果>"
        out.append(_cand(rid, "happy", f"正常系: {subj}", "前提条件を満たしている", f"{subj}を実行する",
                         exp, prov="DERIVED"))
        b = boundary.derive(u)
        if not b.get("gap"):
            out.append(_cand(rid, "boundary", f"境界値: {subj}", "入力の許容範囲が定義されている",
                             "境界値を入力する", "範囲内は受理され範囲外は拒否される",
                             data=b["boundary_values"], prov="DERIVED"))
        rules = [("permission", RE_PERM, "権限のないユーザーで操作する", "操作が許可されない"),
                 ("negative", RE_NEG, "不正な入力で実行する", "処理が拒否され理由が示される"),
                 ("error", RE_ERR, "処理中に失敗を発生させる", "<要確認: エラー時の挙動>"),
                 ("state", RE_STATE, "状態を遷移させる", "<要確認: 遷移後の状態>"),
                 ("recovery", RE_RECOV, "失敗後に復旧操作を行う", "<要確認: 復旧後の状態>")]
        for kind, rx, when, then in rules:
            if rx.search(text):
                out.append(_cand(rid, kind, f"{kind}: {subj}", "原文が当該観点に言及している", when, then))
    return out


def impact_payload(diff_items: list[dict], units: list) -> dict:
    """System09 向け変更影響。未結線（送信しない）。"""
    changes, removed, hints = [], [], []
    for d in diff_items:
        ch, rid = d.get("change"), d.get("requirement_id", "")
        if ch == "REMOVED":
            removed.append(rid)
        elif ch in ("MODIFIED", "SPLIT", "MERGED", "CREATED"):
            changes.append({"requirement_id": rid, "change": ch,
                            "threshold_change": d.get("change_type") == "threshold_change",
                            "before": d.get("before_value") or (d.get("before") or {}).get("text", ""),
                            "after": d.get("after_value") or (d.get("after") or {}).get("text", ""),
                            "risk": d.get("risk", "unknown")})
        for o in d.get("impacted_requirements") or []:
            hints.append({"requirement_id": rid, "may_conflict_with": o,
                          "note": "語の重なりによる候補。確定ではない"})
    return {"changes": changes, "removed": removed, "conflicts_hint": hints, "wired": WIRED}


def alignment(units: list, observed: list[dict]) -> list[dict]:
    """System01 観測 Evidence と仕様の語を突き合わせる。観測できなかった≠存在しない。"""
    views = [unit_view(u) for u in units]
    out: list[dict] = []
    for i, o in enumerate(observed):
        label = str(o.get("label", "")).strip()
        hits = [v["requirement_id"] for v in views if label and
                (label in v["text"] or any(label in q or q in label for q in RE_QUOTED.findall(v["text"])))]
        seen = bool(o.get("observed"))
        lim = str(o.get("limitation") or "")
        if not seen:
            status = "NOT_OBSERVED"
            lim = lim or "観測できなかった理由は不明（存在しないとは言えない）"
        else:
            status = "ALIGNED_CANDIDATE" if hits else "UNMATCHED_OBSERVATION"
        out.append({"candidate_id": f"AL-{i + 1}", "type": "IMPLEMENTATION_ALIGNMENT_CANDIDATE",
                    "evidence_kind": o.get("kind"), "label": label, "url": o.get("url", ""),
                    "requirement_ids": hits, "status": status, "limitation": lim,
                    "is_defect": False, "wired": WIRED})
    return out
