"""Entity ごとの CRUD と横断関心事（権限・検証・監査・失敗）の有無を作る。決定論。候補（CANDIDATE）。"""
from __future__ import annotations

import re
from typing import Any

from web.services.docassure.model import CANDIDATE, OBSERVED
from web.services.docassure.state_transition import records

_VERBS = {
    "create": r"登録|作成|追加|新規|発行|申請|投稿",
    "read": r"参照|閲覧|表示|検索|一覧|取得|照会|確認",
    "update": r"更新|変更|編集|修正",
    "delete": r"削除|廃止|取消|解約|退会",
}
_ALL = "|".join(_VERBS.values())
_ENT = re.compile(r"([一-龥ァ-ヴーA-Za-z0-9]{2,12}?)(?:を|の)(?:新規)?(?:" + _ALL + ")")
_BR = re.compile(r"\bBR-\d{1,5}\b")
_CROSS = {
    "permission": r"権限|ロール|管理者のみ|認可|許可された",
    "validation": r"入力チェック|検証|必須|形式|バリデーション|重複|桁|文字以内",
    "audit": r"監査|履歴|操作ログ|証跡|記録",
    "failure": r"失敗|エラー|異常|リトライ|ロールバック|不可",
}
_STOP = {"これ", "それ", "システム", "画面", "ユーザー", "利用者", "管理者", "内容", "情報", "データ"}


def build(src: Any, document_id: str = "doc") -> dict[str, Any]:
    recs = [r for r in records(src, document_id)]
    ents: dict[str, dict[str, Any]] = {}
    rules: dict[str, dict[str, Any]] = {}
    for r in recs:
        text = r["text"]
        for b in _BR.findall(text):
            rules.setdefault(b, {"id": b, "entity_type": "business_rule", "text": text.strip(),
                                 "location": r["loc"], "provenance": OBSERVED})
        for m in _ENT.finditer(text):
            name = re.sub(r"(?:情報|データ)$", "", m.group(1)) or m.group(1)
            if name in _STOP or name.endswith(("する", "した")):
                continue
            e = ents.setdefault(name, {"name": name, "entity_type": "entity", **{k: False for k in _VERBS},
                                       **{k: False for k in _CROSS}, "locations": [], "provenance": OBSERVED})
            for op, rx in _VERBS.items():
                if re.search(rf"{re.escape(m.group(1))}(?:を|の)(?:新規)?(?:{rx})", text):
                    e[op] = True
            e["locations"].append(r["loc"])
    for r in recs:  # 横断関心事は、文中に名前が出る既知 Entity すべてに付ける
        for name, e in ents.items():
            if name in r["text"]:
                for k, rx in _CROSS.items():
                    if re.search(rx, r["text"]):
                        e[k] = True
    gaps = []
    for e in ents.values():
        if (e["create"] or e["update"] or e["delete"]) and not e["validation"]:
            gaps.append({"entity": e["name"], "kind": "no_validation", "status": CANDIDATE})
        if e["delete"] and not (e["audit"] or e["permission"]):
            gaps.append({"entity": e["name"], "kind": "delete_without_audit_or_permission", "status": CANDIDATE})
    return {"entities": list(ents.values()), "business_rules": list(rules.values()),
            "gaps": gaps, "status": CANDIDATE}
