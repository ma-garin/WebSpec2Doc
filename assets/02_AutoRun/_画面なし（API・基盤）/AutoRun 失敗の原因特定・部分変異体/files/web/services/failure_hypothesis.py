"""L3 原因特定 — 失敗の仮説を立て、検証して原因を絞り込む。

設計計画 rev.3 の Phase 2。

解決する問題:
  失敗が「Timeout」「expected true, received false」としか報告されず、
  **なぜ失敗したのか分からない**。人はここで仮説を立て、再現し、原因を特定する。

仮説カタログの根拠:
  本セッションで人（エージェント）が手作業で突き止めた**実在の原因**を知識化したもの。
  机上の想定ではない。hotel-example-site の実サイト検証で 26 件の失敗を
  5 つの原因に帰着させた過程をそのまま規則にしている。

安全性:
  - 対象へのアクセスは **失敗したテストの再実行のみ**（成功したテストは触らない）
  - 仮説数・試行回数・実時間すべてに上限。無限ループを構造的に不可能にする
  - すべての送信は K1 送信ゲートウェイを経由する
  - **説明できなかった失敗を必ず明示**する（「全部原因が分かった」と装わない）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: 1つの失敗に対して試す仮説の上限（無限ループの構造的防止）
MAX_HYPOTHESES_PER_FAILURE = 4
#: 原因特定を試みる失敗の上限（大量失敗時に予算を食い潰さない）
MAX_FAILURES_TO_TRIAGE = 40


@dataclass(frozen=True)
class Hypothesis:
    """失敗原因の仮説。純データとして定義し、拡張可能にする。"""

    hypothesis_id: str
    title: str
    #: この仮説が該当しうる失敗の兆候（エラー文の正規表現）
    signature: re.Pattern[str]
    #: 検証のためにテストへ加える変更の説明（人が読む）
    probe: str
    #: 実サイトで観測された根拠（この仮説が机上でない証拠）
    evidence: str
    #: 高いほど先に試す。環境起因は最初に判定する（落ちている対象を叩かないため）
    priority: int = 50


#: 仮説カタログ。すべて本セッションの実観測に基づく。
HYPOTHESES: tuple[Hypothesis, ...] = (
    Hypothesis(
        hypothesis_id="H7",
        title="環境起因（対象の一時障害・ネットワーク）",
        signature=re.compile(
            r"net::ERR_|ECONNREFUSED|ETIMEDOUT|502|503|504|Navigation failed", re.I
        ),
        probe="間隔を空けて再実行し、再現性を確認する",
        evidence="真の欠陥と flaky を分けるため。落ちている対象を再試行で叩かない",
        # 最優先。対象が落ちているのに他の仮説で叩き続けるのを防ぐ
        priority=100,
    ),
    Hypothesis(
        hypothesis_id="H1",
        title="既存値への連結（事前入力済みの値が残る）",
        signature=re.compile(r"checkValidity|toBe\(true\)|toBe\(false\)|valid", re.I),
        probe="fill('') で明示的に空にしてから再入力し、値を確認する",
        evidence='実サイトで "2026/07/212026/08/03" のような連結値を観測',
        priority=80,
    ),
    Hypothesis(
        hypothesis_id="H2",
        title="ロケール依存の値書式",
        signature=re.compile(r"checkValidity|valid|Please enter a valid|有効な値", re.I),
        probe="URLのロケールパスから書式を推定して再試行（/en-US/→MM/DD/YYYY、/ja/→YYYY/MM/DD）",
        evidence="ISO形式(2026-08-03)が customValidity で拒否され、MM/DD/YYYY で通った",
        priority=75,
    ),
    Hypothesis(
        hypothesis_id="H3",
        title="オーバーレイによるクリック遮断",
        signature=re.compile(
            r"intercepts pointer events|element is not visible|not stable|Timeout.*click", re.I
        ),
        probe="ポップアップを閉じてから（body への強制クリック）再操作する",
        evidence="jQuery UI datepicker が他要素へのクリックを遮っていた",
        priority=70,
    ),
    Hypothesis(
        hypothesis_id="H4",
        title="条件付き disabled（他項目に連動して無効化）",
        signature=re.compile(r"not enabled|disabled|element is not editable|Timeout.*fill", re.I),
        probe="対象の有効状態を確認し、無効なら「条件付き項目」として分類する",
        evidence="email/tel が contact の選択に連動して disabled になっていた",
        priority=65,
    ),
    Hypothesis(
        hypothesis_id="H5",
        title="兄弟必須項目の制約違反",
        signature=re.compile(r"checkValidity|toBe\(true\)|rangeUnderflow|rangeOverflow", re.I),
        probe="同一フォーム内の他必須項目の min/max を尊重した値で再試行する",
        evidence="プラン別に人数が2固定で、汎用値(1)が制約を侵していた",
        priority=60,
    ),
    Hypothesis(
        hypothesis_id="H6",
        title="タイミング（要素の遅延生成）",
        signature=re.compile(r"Timeout|waiting for locator|not found", re.I),
        probe="待機条件を変えて再試行する",
        evidence="一般的原因として追加（本セッションでは主因ではなかった）",
        priority=40,
    ),
)


@dataclass
class TriageResult:
    """1件の失敗に対する原因特定の結果。"""

    title: str
    error_excerpt: str
    candidates: tuple[dict[str, Any], ...] = ()

    @property
    def explained(self) -> bool:
        return bool(self.candidates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "error_excerpt": self.error_excerpt,
            "explained": self.explained,
            "candidates": list(self.candidates),
        }


def match_hypotheses(error_text: str) -> tuple[Hypothesis, ...]:
    """失敗の兆候から、適用可能な仮説を優先度順に絞る。

    全仮説を無差別に試さない（予算と対象への配慮）。
    """
    matched = [h for h in HYPOTHESES if h.signature.search(error_text or "")]
    matched.sort(key=lambda h: h.priority, reverse=True)
    return tuple(matched[:MAX_HYPOTHESES_PER_FAILURE])


def triage(failures: list[dict[str, Any]]) -> dict[str, Any]:
    """失敗テスト群の原因を仮説で絞り込む（静的解析のみ・アクセス不要）。

    実際の再実行による検証は Phase 2 の後続で追加する。現段階でも、
    エラーの兆候から**原因候補と次の一手**を提示できるため価値がある。

    重要: `unexplained` を必ず返す。「全部原因が分かった」と装わない（条件2）。
    """
    targets = [f for f in failures if isinstance(f, dict)][:MAX_FAILURES_TO_TRIAGE]
    results: list[TriageResult] = []
    for failure in targets:
        error_text = str(failure.get("error", ""))
        matched = match_hypotheses(error_text)
        results.append(
            TriageResult(
                title=str(failure.get("title", "")),
                error_excerpt=_excerpt(error_text),
                candidates=tuple(
                    {
                        "hypothesis_id": h.hypothesis_id,
                        "title": h.title,
                        "probe": h.probe,
                        "evidence": h.evidence,
                    }
                    for h in matched
                ),
            )
        )

    explained = [r for r in results if r.explained]
    unexplained = [r for r in results if not r.explained]
    truncated = max(0, len([f for f in failures if isinstance(f, dict)]) - len(targets))

    return {
        "applicable": bool(results),
        "triaged": [r.to_dict() for r in explained],
        # 説明できなかった失敗を隠さない（条件2の直接適用）
        "unexplained": [r.to_dict() for r in unexplained],
        "unexplained_count": len(unexplained),
        "truncated_count": truncated,
        "notice": (
            "原因候補は失敗の兆候から推定したものです。"
            "候補が示されたことは原因の確定を意味せず、"
            "候補が無いことは原因が無いことを意味しません（未特定）。"
        ),
    }


def _excerpt(text: str, limit: int = 300) -> str:
    return " ".join(str(text).split())[:limit]
