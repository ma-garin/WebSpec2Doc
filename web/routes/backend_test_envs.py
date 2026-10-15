"""System 08 の接続先ルート（一覧の置き換え・追加・接続確認）。backend_test から分けたもの（同じ bp に載せる）。"""
from __future__ import annotations

from flask import request
from web.services.backendtest import dbconn
from web.services.backendtest import store

from web.routes.backend_test import API, MAX_ITEMS, SSLMODES, _NO_SECRET, _assign_ids, _int_in, _next_id, _without_secret, body, bp, err, load_job, respond


def _classified(env: dict) -> dict:
    got = dbconn.classify(env, env["declared_production"], env.get("in_recovery", False))
    return {**env, "production": bool(got.get("production")),
            "production_reasons": list(got.get("reasons") or [])}


def _env(raw, eid: str, old: dict | None = None) -> dict:
    """接続先を正規化し本番判定を付ける。秘密は受け取らない前提（呼び出し側で除く）。"""
    if not isinstance(raw, dict):
        raise store.StoreError("接続先の形式が読めません。画面から入れ直してください。")
    name = str(raw.get("name") or "").strip()
    if not name or len(name) > 100:
        raise store.StoreError("接続先の名前を 1〜100 文字で入れてください。")
    db = raw.get("db") if isinstance(raw.get("db"), dict) else {}
    sslmode = db.get("sslmode") or "prefer"
    if sslmode not in SSLMODES:
        raise store.StoreError("暗号化の方式を一覧から選び直してください。")
    env = {"id": eid, "name": name,
           "db": {"kind": "postgresql", "host": str(db.get("host") or "").strip()[:255],
                  "port": _int_in(db.get("port") or 5432, 1, 65535, "ポートは 1〜65535 の数で入れてください。"), "dbname": str(db.get("dbname") or "").strip()[:63],
                  "user": str(db.get("user") or "").strip()[:63], "sslmode": sslmode},
           "file_root": str(raw.get("file_root") or "").strip()[:500],
           "writable": raw.get("writable") is not False,
           "declared_production": raw.get("declared_production") is True,
           "in_recovery": bool((old or {}).get("in_recovery"))}
    return _classified(env)


def _run_check(env: dict, secret: str | None) -> tuple[dict, dict]:
    """接続確認。秘密は引数でだけ受け、どこにも残さない。戻り値は（判定し直した env, 応答）。"""
    result = dbconn.check(env, secret)
    env = _classified({**env, "in_recovery": bool(result.get("in_recovery")) or bool(env.get("in_recovery"))})
    return env, {"reachable": bool(result.get("reachable")), "auth": bool(result.get("auth")),
                 "privilege": result.get("privilege"), "in_recovery": env["in_recovery"],
                 "production": env["production"], "production_reasons": env["production_reasons"],
                 "read_only": dbconn.must_read_only(env), "message": str(result.get("message") or "")}


def _secret_of(data: dict) -> str | None:
    db = data.get("db") if isinstance(data.get("db"), dict) else {}
    value = data.get("secret") or data.get("password") or db.get("password")
    if value is not None and not isinstance(value, str):
        raise store.StoreError("パスワードが読めません。文字で入れ直してください。")
    return value or None


def _replace_envs(job: dict, data: dict):
    """PUT: 一覧ごと置き換え。秘密を含めたら 400（BD 8 章）。"""
    raws = data.get("envs")
    if not isinstance(raws, list) or len(raws) > MAX_ITEMS:
        return err(f"接続先は 0〜{MAX_ITEMS} 件で送ってください。画面を再読み込みしてやり直してください。", 400)
    if _without_secret(data) != data:
        return err(_NO_SECRET, 400)
    old, ids = {x["id"]: x for x in job["envs"]}, _assign_ids(raws, "e")
    envs = [_env(r, i, old.get(i)) for r, i in zip(raws, ids)]
    current = data.get("current_env", job.get("current_env"))
    return respond({**job, "envs": envs, "current_env": current if current in ids else (ids[0] if ids else None)})


def _add_env(job: dict, data: dict):
    """POST: 1 件追加。本文のパスワードは接続確認にだけ使い、保存しない。"""
    if len(job["envs"]) >= MAX_ITEMS:
        return err(f"接続先は {MAX_ITEMS} 件までです。不要な接続先を外してください。", 400)
    secret, check = _secret_of(data), None
    env = _env(_without_secret(data), _next_id({x["id"] for x in job["envs"]}, "e"))
    if secret:
        env, check = _run_check(env, secret)
    return respond({**job, "envs": job["envs"] + [env], "current_env": job.get("current_env") or env["id"]},
                   201, check=check)


@bp.route(API + "/<jid>/envs", methods=["PUT", "POST"])
def put_envs(jid: str):
    job, e = load_job(jid)
    if e:
        return e
    try:
        return (_replace_envs if request.method == "PUT" else _add_env)(job, body())
    except store.StoreError as exc:
        return err(str(exc), 400)


@bp.route(API + "/<jid>/envs/<eid>/check", methods=["POST"])
def check_env(jid: str, eid: str):
    job, e = load_job(jid)
    if e:
        return e
    env = next((x for x in job["envs"] if x["id"] == eid), None)
    if env is None:
        return err("その接続先は登録されていません。接続先の一覧を再読み込みしてください。", 404)
    try:
        env, result = _run_check(env, _secret_of(body()))
    except store.StoreError as exc:
        return err(str(exc), 400)
    return respond({**job, "envs": [env if x["id"] == eid else x for x in job["envs"]]}, **result)
