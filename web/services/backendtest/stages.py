"""System 08 段階 1〜8 の状態機械（基本設計書 WS2D-BD-008 4 章）。

すべて純粋関数。入力の job dict は変更せず、新しい dict を返す。
版の退避（versions/）は呼び出し側が store.save_version で行う。
"""
from __future__ import annotations

import copy
from datetime import datetime
from typing import Callable

try:
    from .store import StoreError
except ImportError:  # U01（store）が未配置のときだけ。型は同じ ValueError 派生
    class StoreError(ValueError):
        """利用者に見せてよい理由を持つ失敗。"""

STAGES: tuple[dict, ...] = (
    {"no": 1, "key": "purpose", "name": "目的・範囲", "approver_role": "qa", "fields": ("purpose", "scope")},
    {"no": 2, "key": "intake", "name": "対象の読み取り", "approver_role": "qa", "fields": ("facts", "questions")},
    {"no": 3, "key": "viewpoints", "name": "観点表", "approver_role": "qa", "fields": ("viewpoints",)},
    {"no": 4, "key": "cases", "name": "ケース表", "approver_role": "senior_qa", "fields": ("cases",)},
    {"no": 5, "key": "data_specs", "name": "テストデータ仕様", "approver_role": "qa", "fields": ("data_specs",)},
    {"no": 6, "key": "code", "name": "テストコード", "approver_role": "qa", "fields": ("code",)},
    {"no": 7, "key": "run", "name": "実行", "approver_role": "qa", "fields": ("runs",)},
    {"no": 8, "key": "report", "name": "判定・報告", "approver_role": "senior_qa", "fields": ("results", "defects")},
)
_BY_NO = {s["no"]: s for s in STAGES}
ROLE_RANK = {"qa": 1, "senior_qa": 2}
ORACLE_STAGE = 4          # 期待値の確定を含む段階。承認は設定に関わらず senior_qa 以上
_RUN_FINISHED = {"done", "cancelled", "timeout"}
_CHECKS: dict[int, list[Callable[[dict], str | None]]] = {}


def register_check(n: int, fn: Callable[[dict], str | None]) -> None:
    """段階固有の承認条件を足す（例: 段階 3 の coverage().silent）。fn は止める理由か None を返す。"""
    _check_n(n)
    _CHECKS.setdefault(n, []).append(fn)


def downstream(n: int) -> list[int]:
    _check_n(n)
    return [m for m in _BY_NO if m > n]


# ---- 内部ヘルパ -------------------------------------------------------------

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _check_n(n) -> None:
    if not isinstance(n, int) or n not in _BY_NO:
        raise StoreError("段階の番号が正しくありません。1〜8 の段階を選び直してください。")


def _default_stage() -> dict:
    return {"status": "draft", "version": 0, "stale": False, "approved_by_role": None,
            "approved_by": None, "approved_at": None, "reject_reason": None,
            "comments": {}, "proposals": []}


def _stage(job: dict, n: int) -> dict:
    raw = (job.get("stages") or {}).get(str(n)) or {}
    return {**_default_stage(), **copy.deepcopy(raw)}


def _with_stages(job: dict, updates: dict[int, dict]) -> dict:
    stages = dict(job.get("stages") or {})
    for n, st in updates.items():
        stages[str(n)] = st
    return {**job, "stages": stages}


def _audit(job: dict, action: str, n: int, version: int, detail: str, actor: str) -> dict:
    entry = {"at": _now(), "actor": actor, "action": action, "stage": n,
             "version": version, "detail": detail}
    return {**job, "audit": [*(job.get("audit") or []), entry]}


def _stale_downstream(job: dict, n: int) -> dict:
    """前段が変わったので、生成済み・承認済みの後段に stale を立てる（成果物と状態は変えない）。"""
    updates = {}
    for m in downstream(n):
        st = _stage(job, m)
        if st["status"] != "draft" and not st["stale"]:
            updates[m] = {**st, "stale": True}
    return _with_stages(job, updates) if updates else job


def _artifact_of(job: dict, n: int) -> dict:
    return {f: copy.deepcopy(job.get(f)) for f in _BY_NO[n]["fields"]}


def _apply_artifact(job: dict, n: int, artifact: dict) -> dict:
    fields = _BY_NO[n]["fields"]
    unknown = [k for k in artifact if k not in fields]
    if unknown:
        raise StoreError(f"段階 {n} の成果物に含められない項目があります（{', '.join(unknown)}）。"
                         "生成をやり直してください。")
    return {**job, **copy.deepcopy(artifact)}


def _role_rank(role) -> int:
    return ROLE_RANK.get(role or "", 0)


def _actor_role(job: dict, actor: str, role=None):
    """ロールは job.members から引く。メンバー外のときだけ渡された role を使う。"""
    members = job.get("members") or {}
    return members.get(actor, role)


def _required_role(job: dict, n: int) -> str:
    configured = (job.get("approver_roles") or {}).get(str(n)) or _BY_NO[n]["approver_role"]
    if n == ORACLE_STAGE and _role_rank(configured) < _role_rank("senior_qa"):
        return "senior_qa"
    return configured


def _require_status(st: dict, n: int, allowed: set, action: str) -> None:
    if st["status"] not in allowed:
        raise StoreError(f"段階 {n} はいまの状態（{st['status']}）では{action}できません。"
                         "段階の状態を確かめてからやり直してください。")


# ---- 生成 -------------------------------------------------------------------

def can_generate(job: dict, n: int) -> tuple[bool, str]:
    if not isinstance(n, int) or n not in _BY_NO:
        return False, "段階の番号が正しくありません。1〜8 の段階を選び直してください。"
    if n == 1:
        return True, ""
    prev = _stage(job, n - 1)
    if prev["status"] != "approved":
        return False, f"段階 {n - 1}（{_BY_NO[n - 1]['name']}）が未承認です。先に承認してください。"
    if prev["stale"]:
        return False, f"段階 {n - 1}（{_BY_NO[n - 1]['name']}）の前段が変わりました。先に段階 {n - 1} を作り直してください。"
    return True, ""


def put_generated(job: dict, n: int, artifact: dict, actor: str) -> dict:
    """生成結果を置く。承認済みの段階は成果物を変えず proposals に積む。"""
    ok, reason = can_generate(job, n)
    if not ok:
        raise StoreError(reason)
    st = _stage(job, n)
    if st["status"] == "approved":
        return _propose(job, n, st, artifact, actor)
    new_job = _apply_artifact(job, n, artifact)
    st = {**st, "status": "generated", "version": st["version"] + 1, "stale": False,
          "approved_by_role": None, "approved_by": None, "approved_at": None}
    new_job = _stale_downstream(_with_stages(new_job, {n: st}), n)
    return _audit(new_job, "generate", n, st["version"], "", actor)


def _propose(job: dict, n: int, st: dict, artifact: dict, actor: str) -> dict:
    _apply_artifact(job, n, artifact)  # 項目の検査だけ行う
    current = _artifact_of(job, n)
    changed = {k: v for k, v in artifact.items() if current.get(k) != v}
    if not changed:
        if st["stale"]:  # 作り直しても同じ結果 = 前段の変更の影響なし
            job = _with_stages(job, {n: {**st, "stale": False}})
            return _audit(job, "generate", n, st["version"], "前段の変更による差分なし", actor)
        return job
    pid = f"P{n}-{len(st['proposals']) + 1:03d}"
    impacted = [m for m in downstream(n) if _stage(job, m)["status"] != "draft"]
    proposal = {"id": pid, "base_version": st["version"], "artifact": copy.deepcopy(changed),
                "fields": sorted(changed), "at": _now(), "by": actor, "impacted": impacted}
    st = {**st, "proposals": [*st["proposals"], proposal]}
    notice = {"at": proposal["at"], "stage": n, "proposal": pid, "impacted": impacted,
              "text": f"承認済みの段階 {n}（{_BY_NO[n]['name']}）に変更の提案があります。採用すると後段の作り直しが必要です。"}
    new_job = {**_with_stages(job, {n: st}), "notices": [*(job.get("notices") or []), notice]}
    return _audit(new_job, "generate", n, st["version"], f"提案 {pid}", actor)


def adopt_proposal(job: dict, n: int, pid: str, actor: str) -> dict:
    _check_n(n)
    st = _stage(job, n)
    _require_status(st, n, {"approved"}, "提案を採用")
    found = [p for p in st["proposals"] if p.get("id") == pid]
    if not found:
        raise StoreError("指定した提案が見つかりません。画面を読み込み直してください。")
    new_job = _apply_artifact(job, n, found[0]["artifact"])
    st = {**st, "status": "generated", "version": st["version"] + 1, "stale": False,
          "approved_by_role": None, "approved_by": None, "approved_at": None,
          "proposals": [p for p in st["proposals"] if p.get("id") != pid]}
    new_job = _stale_downstream(_with_stages(new_job, {n: st}), n)
    return _audit(new_job, "generate", n, st["version"], f"提案 {pid} を採用", actor)


# ---- 項目の採否 -------------------------------------------------------------

def _update_item(job: dict, field: str, item_id: str, fn: Callable[[dict], dict]) -> dict:
    items = job.get(field) or []
    if not any(i.get("id") == item_id for i in items):
        raise StoreError(f"項目 {item_id} が見つかりません。画面を読み込み直してください。")
    return {**job, field: [fn(copy.deepcopy(i)) if i.get("id") == item_id else i for i in items]}


def _require_senior(job: dict, actor: str, what: str) -> None:
    if _role_rank(_actor_role(job, actor)) < _role_rank("senior_qa"):
        raise StoreError(f"{what}はシニア QA だけが行えます。シニア QA に依頼してください。")


def _decide_viewpoint(job, item_id, decision, value, reason, actor):
    if decision == "added":
        _require_senior(job, actor, "観点の追加")
        if not isinstance(value, dict) or not value.get("id"):
            raise StoreError("追加する観点の内容が足りません。番号と名称を入れてください。")
        if any(v.get("id") == value["id"] for v in job.get("viewpoints") or []):
            raise StoreError("同じ番号の観点がすでにあります。別の番号にしてください。")
        item = {**copy.deepcopy(value), "decision": "adopted", "reason": reason or "", "added_by": actor}
        return {**job, "viewpoints": [*(job.get("viewpoints") or []), item]}
    if decision not in {"adopted", "edited", "discarded"}:
        raise StoreError("観点の採否は採用・修正・破棄・追加から選んでください。")
    if decision == "discarded" and not (reason or "").strip():
        raise StoreError("破棄するときは理由が必要です。理由を入れてください。")
    edits = {}
    if decision == "edited":
        if not isinstance(value, dict):
            raise StoreError("修正の内容がありません。直した内容を入れてください。")
        edits = {k: v for k, v in value.items() if k not in {"id", "decision", "added_by"}}
    return _update_item(job, "viewpoints", item_id,
                        lambda v: {**v, **edits, "decision": decision, "reason": reason or v.get("reason", "")})


def _decide_case(job, item_id, decision, value, reason, actor):
    if decision != "confirm":
        raise StoreError("ケース表では期待値の確定だけを行えます。確定を選んでください。")
    _require_senior(job, actor, "期待値の確定")
    oracle_edits = value if isinstance(value, dict) else {}

    def apply(c):
        oracle = {**(c.get("oracle") or {}), **copy.deepcopy(oracle_edits),
                  "state": "human", "confirmed_by": actor}
        history = [*(c.get("history") or []), {"at": _now(), "by": actor, "action": "confirm", "reason": reason or ""}]
        return {**c, "oracle": oracle, "history": history}
    return _update_item(job, "cases", item_id, apply)


def _decide_intake(job, item_id, decision, value, reason, actor):
    if decision == "answer":
        return _update_item(job, "questions", item_id, lambda q: {**q, "answer": value})
    if decision == "confirm":
        return _update_item(job, "facts", item_id, lambda f: {**f, "confirmed": bool(value)})
    raise StoreError("対象の読み取りでは質問への回答か事実の確認を選んでください。")


def _decide_data_spec(job, item_id, decision, value, reason, actor):
    if decision != "edited" or not isinstance(value, dict):
        raise StoreError("テストデータ仕様は修正だけを行えます。直した内容を入れてください。")
    edits = {k: v for k, v in value.items() if k != "id"}
    return _update_item(job, "data_specs", item_id, lambda d: {**d, **edits})


_DECIDERS = {2: _decide_intake, 3: _decide_viewpoint, 4: _decide_case, 5: _decide_data_spec}


def decide_item(job: dict, n: int, item_id: str, decision: str, value, reason: str, actor: str) -> dict:
    _check_n(n)
    st = _stage(job, n)
    _require_status(st, n, {"generated"}, "項目を変更")
    decider = _DECIDERS.get(n)
    if decider is None:
        raise StoreError(f"段階 {n} には項目ごとの採否がありません。段階全体で承認か差し戻しを選んでください。")
    new_job = decider(job, item_id, decision, value, reason, actor)
    return _audit(new_job, "confirm", n, st["version"], f"{item_id}: {decision}", actor)


# ---- 承認・差し戻し・取消 ---------------------------------------------------

def _builtin_check(job: dict, n: int) -> str | None:
    if n == 4:
        missing = [c.get("id") for c in job.get("cases") or [] if not (c.get("oracle") or {}).get("method")]
        if missing:
            return f"期待値方式が未設定のケースが {len(missing)} 件あります。方式を選んでください。"
    if n == 6:
        summaries = (job.get("code") or {}).get("summaries") or {}
        lacking = [k for k in ((job.get("code") or {}).get("map") or {}) if not summaries.get(k)]
        if lacking:
            return f"日本語の要約が無いテストが {len(lacking)} 件あります。要約を作り直してください。"
    if n == 7:
        runs = job.get("runs") or []
        if not runs or runs[-1].get("status") not in _RUN_FINISHED:
            return "実行が終わっていません。実行の終了を待ってから承認してください。"
    if n == 8:
        pending = [r for r in job.get("results") or []
                   if r.get("state") == "undetermined" and not (r.get("human") or {}).get("verdict")]
        if pending:
            return f"判定待ちが {len(pending)} 件あります。判定を入れてから承認してください。"
    return None


def approve(job: dict, n: int, version: int, role, actor: str) -> dict:
    _check_n(n)
    st = _stage(job, n)
    _require_status(st, n, {"generated"}, "承認")
    if version != st["version"]:
        raise StoreError("表示中の版が最新ではありません。画面を読み込み直してから承認してください。")
    if st["stale"]:
        raise StoreError("前段が変わりました。この段階を作り直してから承認してください。")
    actor_role = _actor_role(job, actor, role)
    required = _required_role(job, n)
    if _role_rank(actor_role) < _role_rank(required):
        label = "シニア QA" if required == "senior_qa" else "QA"
        raise StoreError(f"この段階の承認には{label}の権限が必要です。権限のある人に依頼してください。")
    for check in [lambda j: _builtin_check(j, n), *_CHECKS.get(n, [])]:
        reason = check(job)
        if reason:
            raise StoreError(reason)
    st = {**st, "status": "approved", "approved_by_role": actor_role, "approved_by": actor,
          "approved_at": _now(), "reject_reason": None}
    return _audit(_with_stages(job, {n: st}), "approve", n, st["version"], "", actor)


def reject(job: dict, n: int, reason: str, comments: dict, actor: str) -> dict:
    _check_n(n)
    st = _stage(job, n)
    _require_status(st, n, {"generated", "approved"}, "差し戻し")
    if not (reason or "").strip():
        raise StoreError("差し戻しには理由が必要です。理由を入れてください。")
    st = {**st, "status": "rejected", "reject_reason": reason, "comments": copy.deepcopy(comments or {}),
          "approved_by_role": None, "approved_by": None, "approved_at": None}
    new_job = _stale_downstream(_with_stages(job, {n: st}), n)
    return _audit(new_job, "reject", n, st["version"], reason, actor)


def revert(job: dict, n: int, actor: str, previous: dict | None = None) -> dict:
    """直前の版を復元して承認待ちに戻す。previous を省くと store.load_version で読む。"""
    _check_n(n)
    st = _stage(job, n)
    if st["version"] < 2:
        raise StoreError("戻せる前の版がありません。このまま作業を続けてください。")
    if previous is None:
        from . import store  # 版の読み出しだけは保存層に任せる
        previous = store.load_version(job["id"], n, st["version"] - 1)
    artifact = previous.get("artifact", previous) if isinstance(previous, dict) else {}
    artifact = {k: v for k, v in artifact.items() if k in _BY_NO[n]["fields"]}
    new_job = _apply_artifact(job, n, artifact)
    st = {**st, "status": "generated", "version": st["version"] - 1, "stale": False,
          "approved_by_role": None, "approved_by": None, "approved_at": None}
    new_job = _stale_downstream(_with_stages(new_job, {n: st}), n)
    return _audit(new_job, "revert", n, st["version"], "", actor)
