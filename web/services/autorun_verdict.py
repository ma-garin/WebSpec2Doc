"""AutoRun 結果ページの判定・段階証跡・実行状況（読み取りモデル）。

原則:
- 判定は共通語彙（合格／不合格／判定不能／未判定）だけを使い、「全体」と「今回の変更分」を分ける。
- 件数だけでなく、失敗したテスト・未検証・未承認の段階を名指しする。
- 不在は証明しない。観測できなかったものは「未検証」として残し、合格の根拠にしない。
- 承認は認証済み利用者の記録だけを数える。認証なしの記録は「本人確認なし」と表示する。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from autorun.stages import STAGE_DEFINITIONS, STATUS_APPROVED, STATUS_SKIPPED, Pipeline

from web.services.autorun_run_record import PREV_RECORD_FILE, RECORD_FILE

PASS, FAIL, UNDECIDABLE, UNJUDGED = "合格", "不合格", "判定不能", "未判定"

#: 各段の出口条件（承認してよい状態の定義）。利用者向け文言。
EXIT_CRITERIA: dict[str, str] = {
    "test_objective": "テスト目的が1件以上選ばれ、方針に人が同意している",
    "test_plan": "範囲・前提・合否基準が決まり、人が同意している",
    "features": "切り出したフィーチャーの全件を人が個別に承認している",
    "viewpoints": "フィーチャーごとの観点に抜けが無いと人が判断している",
    "basic_design": "観点ごとに適用するテスト技法が決まっている",
    "detail_design": "確かめる内容（ハイレベルケース）が全量そろっている",
    "test_cases": "手順・データ・期待結果（ローレベルケース）が全量そろっている",
    "playwright_automation": "自動化できなかったケースが「未自動化」として明示されている",
}

STATUS_LABEL = {
    "pending": "未着手",
    "generated": "承認待ち",
    "approved": "承認済み",
    "skipped": "前回承認を流用",
}

#: 実行の終わり方 → 利用者向けの見出し・説明・次の行動
OUTCOME_TEXT: dict[str, tuple[str, str, str]] = {
    "not_run": ("まだ実行していません", "テストの実行記録がありません。", "AutoRun の画面から実行を開始してください。"),
    "complete": ("実行が完了しました", "計画したテストを最後まで実行しました。", "失敗と未検証の項目を確認してください。"),
    "failed": ("実行が途中で止まりました", "実行中に問題が起き、最後まで進めませんでした。", "下のログで止まった箇所を確認し、もう一度実行してください。"),
    "timeout": ("時間切れで止まりました", "承認・入力の待ち時間、またはテストの制限時間を超えました。", "待ち時間内に承認するか、制限時間を見直して再実行してください。"),
    "login_wall": ("ログインが必要な画面を確かめられていません", "ログイン画面の先は観測していません。結果に含まれていない画面があります。", "認証情報を入力して再実行するか、対象外として記録してください。"),
    "partial": ("一部の結果だけが得られています", "実行は止まりましたが、それまでの結果は保存されています。", "得られた結果を確認し、残りを再実行してください。"),
    "cancelled": ("実行を中止しました", "利用者の操作で実行を中止しました。", "必要なら再実行してください。"),
}


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _approval_trail(pipeline: Pipeline) -> dict[str, dict[str, str]]:
    """段階ごとの最後の承認記録（誰が・いつ・理由）。"""
    trail: dict[str, dict[str, str]] = {}
    for entry in pipeline.audit:
        if entry.action == "approve" and not entry.item_id:
            trail[entry.stage_id] = {"at": entry.at, "actor": entry.actor, "reason": entry.detail}
    return trail


def build_stages(pipeline: Pipeline) -> list[dict[str, Any]]:
    """工程バー用の段階一覧（出口条件・担当・判断の証跡つき）。"""
    trail = _approval_trail(pipeline)
    by_id = {s.stage_id: s for s in pipeline.stages}
    rows = []
    for d in STAGE_DEFINITIONS:
        stage = by_id.get(d.stage_id)
        status = stage.status if stage else "pending"
        record = trail.get(d.stage_id, {})
        actor = record.get("actor", "")
        rows.append({
            "step_no": d.step_no,
            "stage_id": d.stage_id,
            "name": d.name,
            "status": status,
            "status_label": STATUS_LABEL.get(status, status),
            "exit_criteria": EXIT_CRITERIA.get(d.stage_id, ""),
            "owner": "作成: AutoRun／判断: 人",
            "approved_at": record.get("at", ""),
            "approver": actor or ("本人確認なし" if record else ""),
            "authenticated": bool(actor),
            "reason": record.get("reason", ""),
        })
    return rows


def classify_outcome(record: dict[str, Any] | None, has_results: bool) -> str:
    if not record:
        return "complete" if has_results else "not_run"
    status = record.get("status", "")
    error = str(record.get("error") or "")
    log_text = "\n".join(record.get("log") or [])
    if status == "cancelled":
        return "cancelled"
    if "タイムアウト" in error or "時間切れ" in error:
        return "timeout"
    if record.get("login_required") and ("スキップ" in log_text or record.get("input_request_type") == "login"):
        return "login_wall"
    if status == "failed":
        return "partial" if has_results else "failed"
    return "complete" if status == "complete" else ("partial" if has_results else "failed")


def _judge(failed: list[str], total: int, outcome: str, unverified: list[str]) -> str:
    if total == 0:
        return UNJUDGED if outcome == "not_run" else UNDECIDABLE
    if failed:
        return FAIL
    if outcome in ("failed", "timeout", "cancelled", "partial"):
        return UNDECIDABLE
    return PASS


def build_verdict(qa: Path) -> dict[str, Any]:
    """結果ページの判定帯・実行状況・常時表示ログを返す。"""
    pipeline_data = _read_json(qa / "stages.json")
    pipeline = Pipeline.from_dict(pipeline_data) if isinstance(pipeline_data, dict) else Pipeline.initial()
    stages = build_stages(pipeline)
    record = _read_json(qa / RECORD_FILE)
    record = record if isinstance(record, dict) else None
    prev = _read_json(qa / PREV_RECORD_FILE)
    prev = prev if isinstance(prev, dict) else None

    report = _read_json(qa / "playwright_report.json") or {}
    outcomes: dict[str, str] = {}
    for t in (report.get("tests") or report.get("results") or []) if isinstance(report, dict) else []:
        if isinstance(t, dict) and (t.get("title") or t.get("name")):
            outcomes[str(t.get("title") or t.get("name"))] = str(t.get("status") or "")
    outcome = classify_outcome(record, bool(outcomes))
    unverified = list((record or {}).get("unverified") or [])
    if outcome == "login_wall":
        unverified.append("ログインが必要な画面（観測していません）")
    unapproved = [
        f"{s['step_no']}. {s['name']}"
        for s in stages
        if s["status"] not in (STATUS_APPROVED, STATUS_SKIPPED)
    ]
    unauthenticated = [f"{s['step_no']}. {s['name']}" for s in stages if s["approver"] == "本人確認なし"]

    failed = sorted(n for n, st in outcomes.items() if st in ("failed", "timedOut", "timeout"))
    overall = {
        "scope": "全体",
        "verdict": _judge(failed, len(outcomes), outcome, unverified),
        "basis": f"テスト {len(outcomes)} 件中 失敗 {len(failed)} 件",
        "named": {"失敗したテスト": failed, "未検証": unverified, "未承認の段階": unapproved,
                  "本人確認のない承認": unauthenticated},
    }

    prev_outcomes = (prev or {}).get("test_outcomes") or {}
    if not prev:
        changed = {"scope": "今回の変更分", "verdict": UNJUDGED,
                   "basis": "前回の実行記録が無いため、変更分を比べられません", "named": {}}
    else:
        delta = sorted(n for n in outcomes if prev_outcomes.get(n) != outcomes[n])
        new_fail = [n for n in delta if n in failed]
        removed = sorted(n for n in prev_outcomes if n not in outcomes)
        changed = {
            "scope": "今回の変更分",
            "verdict": FAIL if new_fail else (PASS if delta or removed else UNJUDGED),
            "basis": f"前回から結果が変わったテスト {len(delta)} 件・今回実行していないテスト {len(removed)} 件",
            "named": {"今回新たに失敗": new_fail, "結果が変わったテスト": delta,
                      "今回実行していない（未検証）": removed},
        }

    title, detail, action = OUTCOME_TEXT[outcome]
    return {
        "stages": stages,
        "outcome": {"kind": outcome, "title": title, "detail": detail, "next_action": action,
                    "finished_at": (record or {}).get("finished_at", "")},
        "verdicts": [overall, changed],
        "log": list((record or {}).get("log") or []),
        "claim_scope": "示しているのは自動で確かめられた範囲です。未検証の項目は、欠陥が無いことの証明ではありません。",
    }
