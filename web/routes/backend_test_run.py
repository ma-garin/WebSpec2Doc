"""System 08 段階 7〜8 の API: 実行（書き込み前確認・キャンセル・結果）・判定・書き出し・監査。

BD-008 5 章・6 章。runner は pytest を起動するだけなので、書き込み前確認のトークン・
本番の読み取り専用強制・ケース選択・job.runs への要約保存はこのルートで包む。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets as _secrets
import threading
import time

from flask import Response, jsonify, request

from web.services.backendtest import dbconn, export, judge, results, runner, stages, store

from web.routes.backend_test import actor as _case_actor
from web.routes.backend_test import bp

log = logging.getLogger(__name__)

API = "/api/backend-test"
TOKEN_TTL_SEC = 10 * 60
CODE_STAGE, RUN_STAGE, REPORT_STAGE = "6", 7, 8
_KEY = _secrets.token_bytes(32)          # 確認トークンの HMAC 鍵（プロセス内のみ）
_TOKENS: dict[str, dict] = {}            # token -> {"sig", "expires"}
_TOKEN_LOCK = threading.Lock()
_EXPORTS = {"report.xlsx": (export.report_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "report.md": (export.report_md, "text/markdown; charset=utf-8"),
            "code.zip": (export.code_zip, "application/zip")}


# ---------------------------------------------------------------- 共通

def _err(message: str, status: int):
    return jsonify(error=message), status


def _actor() -> str:
    """操作者名。作成者を members に入れる案件ルートと同じ規則（backend_test.actor）に揃える。"""
    return _case_actor()


def _load(jid: str):
    try:
        return store.load(jid), None
    except KeyError:
        return None, _err("案件が見つかりません。一覧から選び直してください。", 404)
    except store.StoreError as exc:
        return None, _err(str(exc), 400)
    except (ValueError, OSError):
        log.exception("案件の読み込みに失敗 %s", jid)
        return None, _err("案件を読み込めませんでした。時間をおいて開き直してください。", 500)


def _save(job: dict):
    try:
        return store.save(job), None
    except store.StoreError as exc:
        return None, _err(str(exc), 400)
    except OSError:
        log.exception("案件の保存に失敗 %s", job.get("id"))
        return None, _err("案件を保存できませんでした。時間をおいてやり直してください。", 500)


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _find_env(job: dict, env_id) -> dict | None:
    eid = env_id or job.get("current_env")
    return next((e for e in job.get("envs") or [] if e.get("id") == eid), None)


def _code_ready(job: dict) -> str | None:
    st = (job.get("stages") or {}).get(CODE_STAGE) or {}
    if st.get("status") != "approved" or st.get("stale"):
        return "段階 6（テストコード）が未承認です。テストコードを承認してから実行してください。"
    return None


# ---------------------------------------------------------------- 実行の対象

def _selected(job: dict, case_ids) -> list[str]:
    """選んだケース。"remaining" は前回までの未実行・実行不能・不合格。省略は全件。"""
    all_ids = [str(c.get("id")) for c in job.get("cases") or [] if c.get("id")]
    if case_ids == "remaining":
        latest = _latest_states(job)
        return [c for c in all_ids if latest.get(c) not in ("pass",)]
    if not case_ids:
        return all_ids
    if not isinstance(case_ids, list):
        raise store.StoreError("ケースの指定が読めません。ケースを選び直してください。")
    unknown = [c for c in case_ids if str(c) not in all_ids]
    if unknown:
        raise store.StoreError(f"ケース {', '.join(map(str, unknown[:5]))} が見つかりません。ケース表を確認してください。")
    return [str(c) for c in case_ids]


def _latest_states(job: dict) -> dict:
    states: dict[str, str] = {}
    for r in job.get("results") or []:
        states[str(r.get("case"))] = r.get("state")
    return states


def _effective(job: dict, chosen: list[str]) -> tuple[list[str], list[str]]:
    """pytest -k は部分一致・大文字小文字無視。実際に走るケースと -k に渡すテスト名を返す。"""
    names = (job.get("code") or {}).get("map") or {}
    terms = [names.get(c) or f"test_{c.lower()}" for c in chosen]
    if not chosen:
        return [], []
    hit = [cid for cid, name in names.items() if any(t.lower() in str(name).lower() for t in terms)]
    return sorted(set(hit) | set(chosen)), terms


def _plan(job: dict, env: dict, chosen: list[str]) -> dict:
    by_id = {str(c.get("id")): c for c in job.get("cases") or []}
    effective, terms = _effective(job, chosen)
    tables: list[str] = []
    writes = False
    for cid in effective:
        case = by_id.get(cid) or {}
        writes = writes or bool(case.get("steps") or case.get("pre"))
        for t in (case.get("oracle") or {}).get("tables") or []:
            if t not in tables:
                tables.append(t)
    for spec in job.get("data_specs") or []:
        t = spec.get("table") if isinstance(spec, dict) else None
        writes = writes or bool(t)
        if t and t not in tables:
            tables.append(t)
    judged = dbconn.classify(env, bool(env.get("declared_production")))
    production = bool(env.get("production")) or judged["production"]
    reasons = list(env.get("production_reasons") or []) + [r for r in judged["reasons"]
                                                          if r not in (env.get("production_reasons") or [])]
    extra = [c for c in effective if c not in chosen]
    return {"env_id": env.get("id"), "env_name": env.get("name") or "", "production": production,
            "production_reasons": reasons, "read_only": production or dbconn.must_read_only(env),
            "writes": writes, "affected_tables": tables, "case_ids": chosen, "effective_case_ids": effective,
            "extra_case_ids": extra, "k_terms": terms,
            "code_version": ((job.get("stages") or {}).get(CODE_STAGE) or {}).get("version")}


def _signature(jid: str, plan: dict, business_date: str) -> str:
    material = json.dumps([jid, plan["env_id"], sorted(plan["effective_case_ids"]), plan["code_version"],
                           business_date], ensure_ascii=False)
    return hmac.new(_KEY, material.encode("utf-8"), hashlib.sha256).hexdigest()


def _issue_token(sig: str) -> str:
    token = _secrets.token_urlsafe(24)
    now = time.time()
    with _TOKEN_LOCK:
        for t in [t for t, v in _TOKENS.items() if v["expires"] < now]:
            _TOKENS.pop(t, None)
        _TOKENS[token] = {"sig": sig, "expires": now + TOKEN_TTL_SEC}
    return token


def _use_token(token, sig: str) -> bool:
    with _TOKEN_LOCK:
        entry = _TOKENS.get(str(token or ""))
        if not entry or entry["expires"] < time.time() or not hmac.compare_digest(entry["sig"], sig):
            return False
        _TOKENS.pop(str(token), None)  # 1 回限り
    return True


def _prepare(job: dict, data: dict):
    env = _find_env(job, data.get("env_id"))
    if env is None:
        return None, _err("接続先が見つかりません。接続先を登録して選び直してください。", 400)
    try:
        chosen = _selected(job, data.get("case_ids"))
    except store.StoreError as exc:
        return None, _err(str(exc), 400)
    if not chosen:
        return None, _err("実行するケースがありません。ケース表を確認してください。", 409)
    return (env, _plan(job, env, chosen)), None


# ---------------------------------------------------------------- 段階 7: 実行

@bp.route(f"{API}/jobs/<jid>/runs/preview", methods=["POST"])
def run_preview(jid):
    job, err = _load(jid)
    if err:
        return err
    if (msg := _code_ready(job)):
        return _err(msg, 409)
    data = _body()
    prepared, err = _prepare(job, data)
    if err:
        return err
    _env, plan = prepared
    out = {k: v for k, v in plan.items() if k != "k_terms"}
    if plan["writes"] and not plan["production"]:
        out["confirm_token"] = _issue_token(_signature(jid, plan, str(data.get("business_date") or "")))
        out["confirm_expires_sec"] = TOKEN_TTL_SEC
    return jsonify(out)


def _run_gate(jid: str, plan: dict, data: dict):
    if plan["writes"] and plan["production"]:
        return _err("本番と判定された接続先では、データ投入やジョブ起動を含む実行はできません。"
                    "検証用の接続先を選んでください。", 409)
    if plan["writes"] and not _use_token(data.get("confirm_token"),
                                         _signature(jid, plan, str(data.get("business_date") or ""))):
        return _err("書き込みを伴う実行の確認が済んでいないか、期限が切れています。"
                    "実行前の確認をやり直してください。", 428)
    return None


@bp.route(f"{API}/jobs/<jid>/runs", methods=["POST"])
def run_start(jid):
    job, err = _load(jid)
    if err:
        return err
    if (msg := _code_ready(job)):
        return _err(msg, 409)
    data = _body()
    prepared, err = _prepare(job, data)
    if err:
        return err
    env, plan = prepared
    if (gate := _run_gate(jid, plan, data)):
        return gate
    run_env = {**env, "production": plan["production"],
               "writable": bool(env.get("writable")) and not plan["read_only"]}
    password = str(data.get("secret") or data.get("password") or "")
    try:
        rid = runner.start(jid, run_env, {"password": password} if password else None,
                           int(data.get("timeout_sec") or runner.DEFAULT_TIMEOUT_SEC),
                           case_ids=plan["k_terms"], business_date=str(data.get("business_date") or ""))
    except store.StoreError as exc:
        return _err(str(exc), 409)
    except (TypeError, ValueError):
        return _err("制限時間の指定が読めません。秒数を入れ直してください。", 400)
    finally:
        password = ""
    summary = _summary(runner.status(rid, jid), plan["case_ids"], plan)
    job = store.audit(_with_run(job, summary), "run", RUN_STAGE,
                      f"{rid} 環境={plan['env_name']} ケース={len(plan['case_ids'])}件", _actor())
    _job, err = _save(job)
    if err:
        return err
    return jsonify(run=summary), 202


def _summary(raw: dict, chosen: list[str], plan: dict | None = None) -> dict:
    """runner の要約をケース ID に揃える（runner はテスト名を case_ids に持つため）。"""
    out = {k: v for k, v in raw.items() if k != "results"}
    done = {str(r.get("case")) for r in raw.get("results") or []}
    out.update(case_ids=list(chosen), not_run=[c for c in chosen if c not in done],
               progress={**(raw.get("progress") or {}), "total": len(chosen) or None})
    if plan:
        out.update(env=plan["env_id"], code_version=plan["code_version"], production=plan["production"],
                   read_only=plan["read_only"], writes=plan["writes"], affected_tables=plan["affected_tables"])
    return out


def _with_run(job: dict, summary: dict) -> dict:
    runs = [r for r in job.get("runs") or [] if r.get("id") != summary.get("id")]
    prev = next((r for r in job.get("runs") or [] if r.get("id") == summary.get("id")), {})
    return {**job, "runs": runs + [{**prev, **summary}]}


def _stored_run(job: dict, rid: str) -> dict | None:
    return next((r for r in job.get("runs") or [] if r.get("id") == rid), None)


def _sync(job: dict, rid: str, raw: dict) -> dict:
    """runner の状態を job.runs に反映する。終了の確定時だけ保存する（2 秒ポーリングを軽く保つ）。"""
    stored = _stored_run(job, rid) or {}
    summary = _summary(raw, stored.get("case_ids") or [])
    if raw.get("status") not in runner.ACTIVE and stored.get("status") != raw.get("status"):
        if _save(_with_run(job, summary))[1] is not None:
            log.error("実行 %s の終了状態を保存できませんでした", rid)
    return {**stored, **summary}


@bp.route(f"{API}/jobs/<jid>/runs/<rid>", methods=["GET"])
def run_status(jid, rid):
    job, err = _load(jid)
    if err:
        return err
    if _stored_run(job, rid) is None:
        return _err("実行が見つかりません。実行一覧から選び直してください。", 404)
    try:
        raw = runner.status(rid, jid)
    except (KeyError, store.StoreError, ValueError):
        return jsonify(run=_stored_run(job, rid))
    return jsonify(run=_sync(job, rid, raw))


@bp.route(f"{API}/jobs/<jid>/runs/<rid>/cancel", methods=["POST"])
def run_cancel(jid, rid):
    job, err = _load(jid)
    if err:
        return err
    if _stored_run(job, rid) is None:
        return _err("実行が見つかりません。実行一覧から選び直してください。", 404)
    try:
        raw = runner.cancel(rid, _actor())
    except KeyError:
        return _err("この実行はすでに終わっています。結果を確認してください。", 409)
    summary = _summary(raw, (_stored_run(job, rid) or {}).get("case_ids") or [])
    job = store.audit(_with_run(job, summary), "cancel", RUN_STAGE, rid, _actor())
    _job, err = _save(job)
    if err:
        return err
    return jsonify(run=summary)


# ---------------------------------------------------------------- 結果（evidence → oracle → judge）

@bp.route(f"{API}/jobs/<jid>/runs/<rid>/results", methods=["GET"])
def run_results(jid, rid):
    job, err = _load(jid)
    if err:
        return err
    run = _stored_run(job, rid)
    if run is None:
        return _err("実行が見つかりません。実行一覧から選び直してください。", 404)
    try:
        records = results.records(job, run)
    except ValueError:
        return _err("実行の番号が正しくありません。実行一覧から選び直してください。", 400)
    rows = judge.facts_and_judgement(records, job.get("cases") or [])
    return jsonify(run=run, results=rows, summary=judge.summarize(records))


# ---------------------------------------------------------------- 段階 8: 判定・書き出し・監査

@bp.route(f"{API}/jobs/<jid>/judge", methods=["POST"])
def judge_job(jid):
    job, err = _load(jid)
    if err:
        return err
    actor = _actor()
    if job.get("members") and actor and actor not in job["members"]:
        return _err("この案件のメンバーではないため判定できません。管理者にメンバー追加を依頼してください。", 403)
    if any(r.get("status") in runner.ACTIVE for r in job.get("runs") or []):
        return _err("実行中です。実行が終わってから判定してください。", 409)
    try:
        merged = results.merged(job)
    except ValueError:
        return _err("実行の記録が読めません。再実行してから判定してください。", 409)
    cases = job.get("cases") or []
    found = [{**d, "id": f"BUG-{i:03d}"} for i, d in enumerate(judge.defects(merged, cases), 1)]
    summary = judge.summarize(merged)
    try:
        job = stages.put_generated(job, REPORT_STAGE, {"results": merged, "defects": found}, actor)
    except store.StoreError as exc:
        return _err(str(exc), 409)
    job = {**job, "judgement": {**judge.verdict(summary), "summary": summary, "at": store.now(), "by": actor}}
    job = store.audit(job, "judge", REPORT_STAGE, job["judgement"]["verdict"], actor)
    saved, err = _save(job)
    if err:
        return err
    return jsonify(job=saved)


@bp.route(f"{API}/jobs/<jid>/export/<kind>", methods=["GET"])
def export_job(jid, kind):
    job, err = _load(jid)
    if err:
        return err
    if kind not in _EXPORTS:
        return _err("この形式の書き出しには対応していません。Excel・Markdown・コードの ZIP から選んでください。", 400)
    build, mime = _EXPORTS[kind]
    try:
        data = build(job)
    except (OSError, ValueError, KeyError):
        log.exception("書き出しに失敗 %s %s", jid, kind)
        return _err("書き出しに失敗しました。時間をおいてやり直してください。", 500)
    _job, err = _save(store.audit(job, "export", None, kind, _actor()))
    if err:
        log.error("書き出しの監査記録を保存できませんでした %s", jid)
    filename = f"{job.get('id')}_{kind}"
    return Response(data, mimetype=mime, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@bp.route(f"{API}/jobs/<jid>/audit", methods=["GET"])
def audit_log(jid):
    job, err = _load(jid)
    if err:
        return err
    return jsonify(audit=list(job.get("audit") or []))
