"""要件タイプ別テンプレによる coverage candidate の列挙。欠陥の断定はしない（status=CANDIDATE）。"""
from __future__ import annotations

from typing import Any

from .testability import unit_view

# テンプレ語彙はここ 1 か所に集約。item = (名称, 検出語, 重大度)
TEMPLATES: dict[str, dict] = {
    "認証": {
        "triggers": ("ログイン", "認証", "サインイン", "パスワード"),
        "items": (
            ("成功", ("成功", "ログインできる", "遷移"), "low"),
            ("失敗", ("失敗", "誤り", "不一致", "拒否"), "medium"),
            ("試行上限", ("試行", "回まで", "上限"), "medium"),
            ("ロック", ("ロック", "凍結"), "medium"),
            ("解除", ("解除", "再開", "アンロック"), "low"),
            ("タイムアウト", ("タイムアウト", "有効期限"), "low"),
            ("セッション", ("セッション", "トークン"), "medium"),
            ("権限", ("権限", "ロール", "認可"), "medium"),
            ("監査", ("監査", "ログ記録", "履歴"), "low"),
            ("エラー応答", ("エラー", "メッセージ"), "low"),
        )},
    "アップロード": {
        "triggers": ("アップロード", "添付", "取り込み", "ファイル選択"),
        "items": (
            ("形式", ("形式", "拡張子", "MIME"), "medium"),
            ("最大サイズ", ("最大", "サイズ", "MB", "KB"), "medium"),
            ("複数", ("複数", "一括"), "low"),
            ("不正形式", ("不正", "非対応", "許可されない"), "medium"),
            ("空", ("空ファイル", "0バイト", "空"), "low"),
            ("破損", ("破損", "壊れ"), "low"),
            ("失敗", ("失敗", "エラー"), "medium"),
            ("タイムアウト", ("タイムアウト", "中断"), "low"),
            ("重複", ("重複", "同名", "上書き"), "low"),
        )},
    "CRUD": {
        "triggers": ("登録", "作成", "更新", "削除", "一覧", "編集", "参照", "検索"),
        "items": (
            ("作成", ("登録", "作成", "追加"), "low"),
            ("参照", ("参照", "一覧", "表示", "検索"), "low"),
            ("更新", ("更新", "編集", "変更"), "low"),
            ("削除", ("削除",), "low"),
            ("権限", ("権限", "ロール", "認可"), "medium"),
            ("検証", ("検証", "バリデーション", "必須", "入力チェック", "形式"), "medium"),
            ("not found", ("存在しない", "見つからない", "404", "not found"), "low"),
            ("競合", ("競合", "同時", "排他", "楽観", "重複"), "medium"),
            ("監査", ("監査", "履歴", "ログ記録"), "low"),
        )},
}


def check(units: list[Any]) -> list[dict]:
    views = [unit_view(u) for u in units]
    corpus = " ".join(v["text"] for v in views)
    out: list[dict] = []
    for tname, tpl in TEMPLATES.items():
        hit = [v["requirement_id"] for v in views if any(t in v["text"] for t in tpl["triggers"])]
        if not hit:
            continue
        for item, words, sev in tpl["items"]:
            if any(w.lower() in corpus.lower() for w in words):
                continue
            out.append({"type": tname, "item": item, "status": "CANDIDATE", "severity": sev,
                        "requirement_ids": hit,
                        "message": f"{tname}要件に「{item}」の記述が見当たらない（coverage candidate・欠陥の断定ではない）"})
    return out
