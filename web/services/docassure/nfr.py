"""非機能要件の分類（決定論）。

ISO/IEC 25010 は参考分類であり、本実装は規格への準拠を主張しない。
数値＋単位の測定可能な基準が無いものは measurable=False（要定量化の候補）。
"""
from __future__ import annotations

import re
from typing import Any

from web.services.docassure.model import CANDIDATE, OBSERVED
from web.services.docassure.state_transition import records

REFERENCE = "ISO/IEC 25010 は参考分類。規格準拠を主張しない"
_CATS: list[tuple[str, str]] = [
    ("性能", r"応答時間|レスポンス|スループット|性能|処理時間|秒以内|ミリ秒以内|\d+\s*ms"),
    ("可用性", r"可用性|稼働率|無停止|SLA|ダウンタイム|24時間365日"),
    ("信頼性", r"信頼性|障害率|MTBF|MTTF|冗長|フェイルオーバー|耐障害"),
    ("セキュリティ", r"暗号|認証|脆弱性|TLS|アクセス制御|セキュリティ|パスワード|不正アクセス"),
    ("ユーザビリティ", r"操作性|ユーザビリティ|分かりやす|わかりやす|学習容易|クリック数"),
    ("アクセシビリティ", r"アクセシビリティ|WCAG|スクリーンリーダー|コントラスト比|キーボード操作"),
    ("保守性", r"保守性|テスト容易|モジュール化|カバレッジ|変更容易"),
    ("移植性", r"移植|ポータビリティ|OS非依存|環境非依存|クラウド移行"),
    ("互換性", r"互換|対応ブラウザ|Chrome|Safari|Edge|Firefox|下位バージョン"),
    ("可観測性", r"可観測|監視|メトリクス|トレース|アラート"),
    ("復旧性", r"復旧|RTO|リカバリ|復元|RPO"),
    ("容量", r"容量|同時接続|同時ユーザー|同時アクセス|ストレージ|最大\d+[^\s。]*件"),
    ("保持", r"保持期間|保存期間|保管|アーカイブ"),
    ("バックアップ", r"バックアップ|世代管理"),
    ("DR", r"\bDR\b|災害|遠隔地|別リージョン|ディザスタ"),
    ("監査性", r"監査|証跡|操作ログ|ログイン履歴|追跡可能"),
]
_METRIC = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:ミリ秒|ms|秒|分|時間|日|週間|か月|ヶ月|カ月|年|%|％|件|人|台|回|世代|文字|GB|MB|TB|px|rps|TPS)"
    r"|\d+(?:\.\d+)?\s*:\s*1|\b9{2,}(?:\.\d+)?\s*%")


def classify(src: Any, document_id: str = "doc") -> list[dict[str, Any]]:
    out = []
    for r in records(src, document_id):
        t = r["text"].strip()
        cats = [name for name, rx in _CATS if re.search(rx, t, re.I)]
        if not cats:
            continue
        m = _METRIC.search(t)
        out.append({"text": t, "categories": cats, "measurable": bool(m),
                    "metric": m.group().strip() if m else "", "location": r["loc"],
                    "provenance": OBSERVED, "status": CANDIDATE, "reference": REFERENCE})
    return out
