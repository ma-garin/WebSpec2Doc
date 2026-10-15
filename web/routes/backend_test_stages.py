"""System 08 段階 1〜6 の API（生成・承認・差し戻し・項目修正・期待値確定・ゴールデン）。

状態の遷移は services/backendtest/stages.py（純粋関数）に任せ、ここは入出力・権限・保存だけを持つ。
基本設計書 WS2D-BD-008 4 章（状態機械）・5 章（stages・oracle・golden・code）。
"""
from __future__ import annotations

import logging

from flask import jsonify, request

from web.services.backendtest import cases as cases_mod
from web.services.backendtest import (codegen, codegen_gate, intake, llm_gate, oracle, stages, store,
                                      testdata, viewpoints)
from web.services.backendtest.store import StoreError

from web.routes.backend_test import actor as _case_actor
from web.routes.backend_test import bp

log = logging.getLogger(__name__)

API = "/api/backend-test/jobs/<jid>"
_STAGE_NAMES = {s["no"]: s["name"] for s in stages.STAGES}
_SENIOR = "senior_qa"


# ---- 共通 ---------------------------------------------------------------------

def _err(message: str, status: int, **extra):
    return jsonify(error=message, **extra), status


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _actor() -> str:
    """操作者名。作成者を members に入れる案件ルートと同じ規則（backend_test.actor）に揃える。"""
    return _case_actor()


def _load(jid: str):
    try:
        return store.load(jid), None
    except KeyError:
        return None, _err("案件が見つかりません。一覧から選び直してください。", 404)
    except (ValueError, OSError):
        log.exception("案件の読み込みに失敗 %s", jid)
        return None, _err("案件を読めませんでした。時間をおいて再読み込みしてください。", 500)


def _member_role(job: dict, actor: str):
    """案件のメンバーならロール、メンバー外なら None。"""
    return (job.get("members") or {}).get(actor)


def _open(jid: str):
    """(job, actor, role, エラー応答)。メンバー外は 403（承認・確定をメンバー外に許さない）。"""
    job, err = _load(jid)
    if err:
        return None, "", None, err
    actor = _actor()
    role = _member_role(job, actor)
    if role is None:
        return None, actor, None, _err(
            "この案件のメンバーではありません。案件の作成者にメンバー追加を依頼してください。", 403)
    return job, actor, role, None


def _required_role(job: dict, n: int) -> str:
    configured = (job.get("approver_roles") or {}).get(str(n)) or \
        next(s["approver_role"] for s in stages.STAGES if s["no"] == n)
    if n == stages.ORACLE_STAGE:
        return _SENIOR
    return configured


def _save(job: dict):
    try:
        return store.save(job), None
    except StoreError as exc:
        return None, _err(str(exc), 400)
    except OSError:
        log.exception("案件の保存に失敗 %s", job.get("id"))
        return None, _err("保存できませんでした。時間をおいてもう一度操作してください。", 500)


def _stage_view(job: dict, n: int) -> dict:
    return dict((job.get("stages") or {}).get(str(n)) or {})


def _bad_stage(n: int):
    return n not in _STAGE_NAMES


# ---- LLM（規則ベースの補強。失敗しても生成は止めない） -----------------------------

def _llm_note(job: dict, n: int, purpose: str, payload: dict, instructions: str, actor: str):
    """llm_gate を通して補強文を得る。(新しい job, 本文 or None)。止められた・失敗したら None。"""
    if not any(str(v or "").strip() for v in payload.values()):
        return job, None
    try:
        got = llm_gate.send(job, n, purpose, payload, actor, instructions=instructions)
    except StoreError as exc:  # GateBlocked・LlmCallFailed を含む。止めた記録だけ残す
        log.info("LLM の補強を省略（段階 %s・%s）: %s", n, purpose, exc)
        record = getattr(exc, "record", None)
        return (llm_gate.append_record(job, record) if record else job), None
    job = llm_gate.append_record(job, got["record"])
    return store.audit(job, "llm", n, purpose, actor), got["text"]


def _spec_text(facts: list) -> str:
    rows = [f for f in facts if (f.get("origin") or (f.get("source") or {}).get("kind")) == "spec"]
    return "\n".join(f"{f.get('subject', '')}: {f.get('value', '')}" for f in rows)


# ---- 段階ごとの生成 ------------------------------------------------------------

def _gen_purpose(job: dict, body: dict, actor: str):
    purpose = str(body.get("purpose", job.get("purpose") or "")).strip()
    scope = str(body.get("scope", job.get("scope") or "")).strip()
    if not purpose:
        raise StoreError("テストの目的が空です。目的を入れてから作成してください。")
    targets = body.get("targets")
    if targets is not None:
        if not isinstance(targets, list):
            raise StoreError("対象の指定が読めません。対象を選び直してください。")
        job = {**job, "targets": targets}
    return job, {"purpose": purpose, "scope": scope}, {}


def _gen_intake(job: dict, body: dict, actor: str):
    got = intake.read_all(job)
    reds = got.get("redactions") or {}
    files = [{**f, "redactions": reds[f.get("name")]} if f.get("name") in reds else f
             for f in job.get("files") or []]
    job = {**job, "files": files}
    job, note = _llm_note(job, 2, "spec_summary", {"spec": _spec_text(got["facts"])},
                          "仕様書から読み取った事実を、テスト担当者向けに日本語 3 文で要約してください。", actor)
    if note:
        job = {**job, "notices": [*(job.get("notices") or []),
                                  {"stage": 2, "kind": "spec_summary", "text": note, "at": store.now()}]}
    return job, {"facts": got["facts"], "questions": got["questions"]}, {"unread": got.get("unread") or []}


def _gen_viewpoints(job: dict, body: dict, actor: str):
    try:
        built = viewpoints.build(job.get("facts") or [], job.get("level"), job.get("target_kind"))
    except ValueError as exc:
        raise StoreError(str(exc)) from exc
    return job, {"viewpoints": built}, {}


def _gen_cases(job: dict, body: dict, actor: str):
    built = cases_mod.build(job.get("viewpoints") or [], job.get("facts") or [], job.get("level"))
    return job, {"cases": built}, {}


def _gen_data_specs(job: dict, body: dict, actor: str):
    return job, {"data_specs": testdata.spec_from_cases(job.get("cases") or [], job.get("facts") or [])}, {}


class _GateFailed(Exception):
    def __init__(self, problems: list):
        super().__init__("生成したコードに問題があります")
        self.problems = problems


def _gen_code(job: dict, body: dict, actor: str):
    out = codegen.generate(job)
    prev = (job.get("code") or {}).get("files") or None
    problems = codegen_gate.gate(out["files"], previous_files=prev, cases=job.get("cases") or [])
    if problems:
        raise _GateFailed(problems)
    code = {**out, "gate": []}
    summaries = "\n".join(f"{k}: {v}" for k, v in (out.get("summaries") or {}).items())
    job, note = _llm_note(job, 6, "code_summary", {"spec": summaries},
                          "テストの日本語要約を読み、コードを書かない QA 向けに全体像を日本語 3 文で補ってください。",
                          actor)
    if note:
        code = {**code, "overview": note}
    return job, {"code": code}, {}


_GENERATORS = {1: _gen_purpose, 2: _gen_intake, 3: _gen_viewpoints,
               4: _gen_cases, 5: _gen_data_specs, 6: _gen_code}


@bp.post(API + "/stages/<int:n>/generate")
def api_stage_generate(jid: str, n: int):
    if n not in _GENERATORS:
        return _err("この段階はここでは生成できません。実行と判定はそれぞれの画面から行ってください。", 404)
    job, actor, role, err = _open(jid)
    if err:
        return err
    ok, reason = stages.can_generate(job, n)
    if not ok:
        return _err(reason, 409)
    try:
        job, artifact, extra = _GENERATORS[n](job, _body(), actor)
        job = stages.put_generated(job, n, artifact, actor)
    except _GateFailed as exc:
        return _err("生成したコードに問題があります。一覧の理由を見て、生成し直すか該当箇所を直してください。",
                    422, problems=exc.problems)
    except StoreError as exc:
        return _err(str(exc), 400)
    if _stage_view(job, n).get("status") == "generated":
        try:
            store.save_version(job, n)
        except OSError:
            log.exception("版の退避に失敗 %s 段階 %s", jid, n)
            return _err("版を保存できませんでした。時間をおいてもう一度生成してください。", 500)
    job, err = _save(job)
    if err:
        return err
    return jsonify(stage=_stage_view(job, n), job=store.summary(job), **extra)


# ---- 承認・差し戻し --------------------------------------------------------------

@bp.post(API + "/stages/<int:n>/approve")
def api_stage_approve(jid: str, n: int):
    if _bad_stage(n):
        return _err("段階の番号が正しくありません。1〜8 の段階を選び直してください。", 404)
    job, actor, role, err = _open(jid)
    if err:
        return err
    if stages.ROLE_RANK.get(role, 0) < stages.ROLE_RANK.get(_required_role(job, n), 0):
        label = "シニア QA" if _required_role(job, n) == _SENIOR else "QA"
        return _err(f"この段階の承認には{label}の権限が必要です。権限のある人に依頼してください。", 403)
    try:
        version = int(_body().get("version", _stage_view(job, n).get("version")))
    except (TypeError, ValueError):
        return _err("版の番号が読めません。画面を読み込み直してから承認してください。", 400)
    try:
        job = stages.approve(job, n, version, role, actor)
    except StoreError as exc:
        return _err(str(exc), 409)
    job, err = _save(job)
    if err:
        return err
    return jsonify(stage=_stage_view(job, n), job=store.summary(job))


@bp.post(API + "/stages/<int:n>/reject")
def api_stage_reject(jid: str, n: int):
    if _bad_stage(n):
        return _err("段階の番号が正しくありません。1〜8 の段階を選び直してください。", 404)
    job, actor, role, err = _open(jid)
    if err:
        return err
    body = _body()
    reason = str(body.get("reason") or "").strip()
    if not reason:
        return _err("差し戻しには理由が必要です。理由を入れてください。", 400)
    comments = body.get("comments") if isinstance(body.get("comments"), dict) else {}
    try:
        job = stages.reject(job, n, reason, comments, actor)
    except StoreError as exc:
        return _err(str(exc), 409)
    job, err = _save(job)
    if err:
        return err
    return jsonify(stage=_stage_view(job, n), job=store.summary(job))


# ---- 項目の人手修正 --------------------------------------------------------------

_CASE_LOCKED = {"id", "oracle", "decision"}


def _edit_case(job: dict, item_id: str, value, reason: str, actor: str) -> dict:
    """ケースの記述（前提・手順など）を直す。期待値（oracle）は期待値の API でだけ変える。"""
    if _stage_view(job, 4).get("status") == "approved":
        raise StoreError("承認済みのケース表は直せません。差し戻してから直してください。")
    if not isinstance(value, dict):
        raise StoreError("修正の内容がありません。直した内容を入れてください。")
    edits = {k: v for k, v in value.items() if k not in _CASE_LOCKED}
    found = [c for c in job.get("cases") or [] if c.get("id") == item_id]
    if not found:
        raise StoreError(f"項目 {item_id} が見つかりません。画面を読み込み直してください。")
    new_cases = [{**c, **edits, "edited_by": actor, "edit_reason": reason or ""} if c.get("id") == item_id else c
                 for c in job.get("cases") or []]
    return store.audit({**job, "cases": new_cases}, "edit", 4, f"{item_id}: edited", actor)


@bp.patch(API + "/stages/<int:n>/items/<item_id>")
def api_stage_item(jid: str, n: int, item_id: str):
    if _bad_stage(n):
        return _err("段階の番号が正しくありません。1〜8 の段階を選び直してください。", 404)
    job, actor, role, err = _open(jid)
    if err:
        return err
    body = _body()
    decision = str(body.get("decision") or "")
    value, reason = body.get("value"), str(body.get("reason") or "")
    try:
        if n == 4 and decision == "edited":
            job = _edit_case(job, item_id, value, reason, actor)
        else:
            job = stages.decide_item(job, n, item_id, decision, value, reason, actor)
    except StoreError as exc:
        status = 403 if "シニア QA" in str(exc) else 400
        return _err(str(exc), status)
    job, err = _save(job)
    if err:
        return err
    return jsonify(stage=_stage_view(job, n), job=store.summary(job))


# ---- 期待値（oracle）とゴールデン ---------------------------------------------------

def _find_case(job: dict, cid: str):
    return next((c for c in job.get("cases") or [] if c.get("id") == cid), None)


def _replace_case(job: dict, case: dict) -> dict:
    return {**job, "cases": [case if c.get("id") == case.get("id") else c for c in job.get("cases") or []]}


def _apply_oracle(job: dict, case: dict, body: dict, role, actor: str):
    """(新しいケース, 拒否理由)。権限で拒否するときだけ理由を返す。"""
    action = str(body.get("action") or "")
    members, facts = job.get("members") or {}, job.get("facts") or []
    if action == "configure_db_diff":
        return oracle.configure_db_diff(
            case, body.get("keys") or [], body.get("tolerance"), body.get("exclude") or (),
            mask=body.get("mask") or (), tables=body.get("tables"),
            count_formula=body.get("count_formula")), None
    if action == "set_alt_sql":
        return oracle.set_alt_sql(case, str(body.get("sql") or ""), role, sql_ja=str(body.get("sql_ja") or ""),
                                  actor=actor, members=members, source_facts=facts), None
    if action == "confirm":
        ok, reason = oracle.can_confirm(case, role, members, facts)
        if not ok:
            return None, reason
        return oracle.confirm(case, role, actor, members, facts), None
    raise StoreError("期待値の操作は前後比較の設定・別経路 SQL・確定から選んでください。")


@bp.patch(API + "/cases/<cid>/oracle")
def api_case_oracle(jid: str, cid: str):
    job, actor, role, err = _open(jid)
    if err:
        return err
    if _stage_view(job, 4).get("status") == "approved":
        return _err("承認済みのケース表の期待値は変えられません。差し戻してから操作してください。", 409)
    case = _find_case(job, cid)
    if case is None:
        return _err("ケースが見つかりません。画面を読み込み直してください。", 404)
    body = _body()
    try:
        new_case, denied = _apply_oracle(job, case, body, role, actor)
    except StoreError as exc:
        return _err(str(exc), 400)
    if denied:
        return _err(denied, 403)
    job = store.audit(_replace_case(job, new_case), "oracle", 4, f"{cid}: {body.get('action')}", actor)
    job, err = _save(job)
    if err:
        return err
    return jsonify(case=new_case, can_confirm=oracle.can_confirm(new_case, role, job.get("members") or {},
                                                                  job.get("facts") or []))


@bp.post(API + "/cases/<cid>/golden")
def api_case_golden(jid: str, cid: str):
    job, actor, role, err = _open(jid)
    if err:
        return err
    if role != _SENIOR:
        return _err("ゴールデンの承認はシニア QA だけができます。シニア QA に承認を依頼してください。", 403)
    case = _find_case(job, cid)
    if case is None:
        return _err("ケースが見つかりません。画面を読み込み直してください。", 404)
    ref = _body().get("golden_ref")
    try:
        new_case = oracle.approve_golden(case, ref, role, actor=actor, members=job.get("members") or {})
    except StoreError as exc:
        return _err(str(exc), 400)
    job = store.audit(_replace_case(job, new_case), "golden", 4, f"{cid}: approved", actor)
    job, err = _save(job)
    if err:
        return err
    return jsonify(case=new_case)
