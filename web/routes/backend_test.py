"""バッチ・バックエンドのテスト（System 08）の画面・案件・資料・対象・接続先。処理は web/services/backendtest/。
段階は backend_test_stages.py、実行・判定は backend_test_run.py が同じ bp に足す。接続のパスワードは保存しない。"""
from __future__ import annotations

import logging
import re

from flask import Blueprint, g, jsonify, render_template, request

from web.auth import effective_auth_mode
from web.services.backendtest import catalog, dbconn, intake, redact, store

bp = Blueprint("backend_test", __name__)
log = logging.getLogger(__name__)
API = "/api/backend-test/jobs"
SENIOR = "senior_qa"
ROLES = ("qa", SENIOR)
LLM_PROVIDERS = ("openai", "ollama")
SSLMODES = ("disable", "allow", "prefer", "require", "verify-ca", "verify-full")
MAX_ITEMS = 20         # 対象・接続先それぞれの上限
LOCAL_ACTOR = "local"   # 認証オフのときの操作者名（作成者もこの名前で members に入る）
_SECRET_KEY = re.compile(r"pass(word|wd)?|secret|token|api_?key|credential|private_?key", re.I)
_NO_SECRET = ("接続のパスワードやトークンは保存できません。"
              "パスワードを外して保存し、接続確認や実行のときに入れてください。")


def err(message: str, status: int):
    return jsonify(error=message), status


def actor() -> str:
    """操作した人。認証オフ・未ログインでは LOCAL_ACTOR。段階・実行のルートもこれを使う。"""
    user = getattr(g, "auth_user", None)
    name = str(user.get("email") or user.get("name") or "") if isinstance(user, dict) else ""
    if not name and effective_auth_mode() == "off":  # 認証オフのときだけ本文の actor を使う（ロールの確認用）
        name = str(body().get("actor") or "").strip()[:64]
    return name or LOCAL_ACTOR


def body() -> dict:
    return data if isinstance(data := request.get_json(silent=True), dict) else {}


def load_job(jid: str):
    try:
        return store.load(jid), None
    except (KeyError, store.StoreError):
        return None, err("案件が見つかりません。一覧から選び直してください。", 404)
    except (ValueError, OSError):
        log.exception("案件の読み込みに失敗 %s", jid)
        return None, err("案件を読めませんでした。時間をおいて再読み込みしてください。", 500)


def respond(job: dict, status: int = 200, **extra):
    """保存して {job, ...extra} を返す。保存できない理由（秘密の混入など）は 400。"""
    try:
        return jsonify(job=store.save(job), **extra), status
    except store.StoreError as exc:
        return err(str(exc), 400)
    except OSError:
        log.exception("案件の保存に失敗 %s", job.get("id"))
        return err("保存できませんでした。時間をおいてもう一度操作してください。", 500)


def _without_secret(value):
    """秘密らしいキーを除いた新しい値（元の dict は変えない）。"""
    if isinstance(value, dict):
        return {k: _without_secret(v) for k, v in value.items() if not _SECRET_KEY.search(str(k))}
    if isinstance(value, list):
        return [_without_secret(v) for v in value]
    return value


def _str_list(value, limit: int = 50) -> list[str]:
    items = value if isinstance(value, list) else []
    return [str(v).strip()[:300] for v in items if str(v).strip()][:limit]


def _next_id(used: set, prefix: str) -> str:
    return next(f"{prefix}{n}" for n in range(1, 10000) if f"{prefix}{n}" not in used)


def _assign_ids(raws: list, prefix: str) -> list[str]:
    """渡された id を活かし、無い・重複・形が違うものだけ空き番号を振る。"""
    given = [str(r.get("id") or "") if isinstance(r, dict) else "" for r in raws]
    ids: list[str] = []
    for rid in given:
        ok = re.fullmatch(prefix + r"\d{1,4}", rid) and rid not in ids
        ids.append(rid if ok else _next_id(set(ids) | set(given), prefix))
    return ids


@bp.route("/backend-test")
def page() -> str:
    return render_template("backend_test.html")


@bp.route(API, methods=["GET"])
def list_jobs():
    try:
        return jsonify(jobs=store.list_all())
    except OSError:
        log.exception("案件一覧の取得に失敗")
        return err("案件の一覧を読めませんでした。時間をおいて再読み込みしてください。", 500)


@bp.route(API, methods=["POST"])
def create_job():
    data = body()
    name = str(data.get("name") or "").strip()
    if not name or len(name) > 100:
        return err("案件名を 1〜100 文字で入れてください。", 400)
    try:
        text = {k: str(data.get(k) or "").strip()[:2000] for k in ("purpose", "scope")}
        job = store.new(name, str(data.get("target_kind") or "batch"), str(data.get("level") or ""), **text)
    except store.StoreError as exc:
        return err(str(exc), 400)
    return respond({**job, "members": {actor(): SENIOR}}, 201)


@bp.route(API + "/<jid>", methods=["GET"])
def get_job(jid: str):
    job, e = load_job(jid)
    if e:
        return e
    role = (job.get("members") or {}).get(actor())
    return jsonify(job=job, my_role=role)


def _int_in(value, low: int, high: int, message: str) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"\d{1,6}", str(value)) or not low <= int(value) <= high:
        raise store.StoreError(message)
    return int(value)


def _apply_patch(job: dict, data: dict) -> dict:
    """PATCH の項目を当てた新しい job。不正な値は StoreError。"""
    out = dict(job)
    if "name" in data:
        name = str(data["name"] or "").strip()
        if not name or len(name) > 100:
            raise store.StoreError("案件名を 1〜100 文字で入れてください。")
        out["name"] = name
    for key in ("purpose", "scope"):
        if key in data:
            out[key] = str(data[key] or "").strip()[:2000]
    if "level" in data:
        if data["level"] not in store.LEVELS:
            raise store.StoreError("テストレベルを一覧から選び直してください。")
        out["level"] = data["level"]
    if "retention_days" in data:
        out["retention_days"] = _int_in(data["retention_days"], 1, 3650, "保存期間は 1〜3650 日の数で入れてください。")
    if "llm" in data:
        provider = (data["llm"] or {}).get("provider") if isinstance(data["llm"], dict) else None
        if provider not in LLM_PROVIDERS:
            raise store.StoreError("AI の送り先を一覧から選び直してください。")
        out["llm"] = {**job["llm"], "provider": provider}   # 外部へ送る範囲は変えられない
    if "approver_roles" in data:
        roles = data["approver_roles"]
        if not isinstance(roles, dict) or any(k not in store.STAGE_NOS or v not in ROLES for k, v in roles.items()):
            raise store.StoreError("承認する役割が読めません。段階ごとに QA かシニア QA を選び直してください。")
        out["approver_roles"] = {**job["approver_roles"], **roles}
    return out


@bp.route(API + "/<jid>", methods=["PATCH"])
def update_job(jid: str):
    job, e = load_job(jid)
    if e:
        return e
    data = body()
    if "approver_roles" in data and (job.get("members") or {}).get(actor()) != SENIOR:
        return err("承認する役割を変えられるのはシニア QA だけです。シニア QA に依頼してください。", 403)
    try:
        job = _apply_patch(job, data)
    except store.StoreError as exc:
        return err(str(exc), 400)
    return respond(job)


@bp.route(API + "/<jid>", methods=["DELETE"])
def delete_job(jid: str):
    try:
        store.delete(jid)
    except (KeyError, FileNotFoundError):
        return err("案件が見つかりません。一覧を再読み込みしてください。", 404)
    except store.StoreError as exc:
        return err(str(exc), 409)
    except OSError:
        log.exception("案件の削除に失敗 %s", jid)
        return err("案件を削除できませんでした。時間をおいてもう一度操作してください。", 500)
    return jsonify(ok=True)


def _reread(job: dict, extra_values=()):
    """資料を読み直して facts・questions を更新し保存する。段階 2 が承認済みなら置き換えず古い印を付ける。"""
    try:
        got = intake.read_all(job, extra_values)
    except store.StoreError as exc:
        return err(str(exc), 400)
    files = [{**f, "redactions": got["redactions"].get(f["name"], [])} for f in job["files"]]
    job = {**job, "files": files}
    stage2 = (job.get("stages") or {}).get("2") or {}
    notes = []
    if stage2.get("status") == "approved":
        job = {**job, "stages": {**job["stages"], "2": {**stage2, "stale": True}}}
        notes.append("対象の読み取りは承認済みのため事実は置き換えていません。反映するには段階 2 を作り直してください。")
    else:
        answers = {q["text"]: q.get("answer") for q in job.get("questions") or [] if q.get("answer")}
        questions = [{**q, "answer": answers.get(q["text"], q.get("answer"))} for q in got["questions"]]
        job = {**job, "facts": got["facts"], "questions": questions}
    # 読めなかった資料・解析できなかった文は job に残す（欄が無い案件は新規キーとして追加）
    kept = {k: got[k] for k in ("unread", "unparsed") if k in got}
    job = {**job, **kept}
    return respond(job, unread=got.get("unread", []), **({"unparsed": got["unparsed"]} if "unparsed" in got else {}),
                   notes=notes)


@bp.route(API + "/<jid>/files", methods=["POST"])
def upload(jid: str):
    job, e = load_job(jid)
    if e:
        return e
    uploads = request.files.getlist("files")
    if not uploads:
        return err("ファイルが選ばれていません。DDL・ジョブ定義・仕様書・ソースを選んでください。", 400)
    try:
        for f in uploads:
            data = f.read()
            if len(data) > store.MAX_FILE_BYTES:
                return err(f"{f.filename} が 20MB を超えています。小さくしてから取り込んでください。", 413)
            job = store.add_file(job, f.filename or "", data)
    except store.StoreError as exc:
        return err(str(exc), 400)
    except OSError:
        log.exception("資料の取り込みに失敗 %s", jid)
        return err("ファイルを保存できませんでした。もう一度取り込んでください。", 500)
    return _reread(job)


def _change_file(job: dict, name: str, data: dict) -> tuple[dict, list[str]]:
    """種類の変更と追加の伏せ字（値は保存しない）。不正なら StoreError、無ければ KeyError。"""
    if not any(f["name"] == name for f in job["files"]):
        raise KeyError(name)
    kind = data.get("kind")
    if kind is not None:
        if kind not in store.FILE_KINDS:
            raise store.StoreError("種類を一覧から選び直してください。")
        job = {**job, "files": [{**f, "kind": kind} if f["name"] == name else f for f in job["files"]]}
    extra = data.get("redactions_add") or []
    if not isinstance(extra, list) or not all(isinstance(v, str) for v in extra):
        raise store.StoreError("伏せ字にする値が読めません。値を 1 つずつ入れ直してください。")
    return job, [v for v in extra if v.strip()]


@bp.route(API + "/<jid>/files/<path:name>", methods=["PATCH", "DELETE"])
def change_file(jid: str, name: str):
    job, e = load_job(jid)
    if e:
        return e
    extra: list[str] = []
    try:
        if request.method == "DELETE":
            job = store.remove_file(job, name)
        else:
            job, extra = _change_file(job, name, body())
    except KeyError:
        return err("そのファイルは取り込まれていません。一覧を再読み込みしてください。", 404)
    except store.StoreError as exc:
        return err(str(exc), 400)
    except OSError:
        log.exception("資料の削除に失敗 %s %s", jid, name)
        return err("ファイルを外せませんでした。時間をおいてもう一度操作してください。", 500)
    return _reread(job, extra)


def _target(raw, tid: str) -> dict:
    if not isinstance(raw, dict):
        raise store.StoreError("対象の形式が読めません。画面から入れ直してください。")
    if _without_secret(raw) != raw:
        raise store.StoreError(_NO_SECRET)
    kind = raw.get("kind") or "batch"
    if kind not in store.TARGET_KINDS:
        raise store.StoreError("この対象の種類にはまだ対応していません。バッチジョブを選んでください。")
    command = str(raw.get("command") or "").strip()
    if not command or len(command) > 300:
        raise store.StoreError("起動コマンドを 1〜300 文字で入れてください。")
    if any(h["kind"] == redact.KIND_SECRET for h in redact.scan(command)):
        raise store.StoreError("起動コマンドにパスワードらしい値があります。値を外し、実行のときに入れる形にしてください。")
    return {"id": tid, "kind": kind, "launch": "command", "command": command,
            "inputs": _str_list(raw.get("inputs")), "outputs": _str_list(raw.get("outputs"))}


@bp.route(API + "/<jid>/targets", methods=["PUT", "POST"])
def put_targets(jid: str):   # PUT は一覧ごと置き換え（targets[]）、POST は 1 件追加
    job, e = load_job(jid)
    if e:
        return e
    data = body()
    try:
        if request.method == "PUT":
            raws = data.get("targets")
            if not isinstance(raws, list) or len(raws) > MAX_ITEMS:
                return err(f"対象は 0〜{MAX_ITEMS} 件で送ってください。画面を再読み込みしてやり直してください。", 400)
            targets = [_target(r, i) for r, i in zip(raws, _assign_ids(raws, "t"))]
        else:
            if len(job["targets"]) >= MAX_ITEMS:
                return err(f"対象は {MAX_ITEMS} 件までです。不要な対象を外してください。", 400)
            tid = _next_id({t["id"] for t in job["targets"]}, "t")
            targets = job["targets"] + [_target(data, tid)]
    except store.StoreError as exc:
        return err(str(exc), 400)
    return respond({**job, "targets": targets}, 201 if request.method == "POST" else 200)


def _target_text(targets: list) -> str:
    """対象の要約（入力 → 出力）。入出力が無ければ起動のしかた。"""
    first = targets[0] if targets and isinstance(targets[0], dict) else {}

    def names(items) -> str:
        out = []
        for x in items or []:
            n = (x.get("name") or x.get("table") or x.get("path")) if isinstance(x, dict) else x
            if n:
                out.append(str(n))
        return "・".join(out)

    src, dst = names(first.get("inputs")), names(first.get("outputs"))
    if src or dst:
        return f"{src or '入力未設定'} → {dst or '出力未設定'}"
    return str(first.get("command") or "")


@bp.route("/api/backend-test/summary", methods=["GET"])
def home_summary():
    """ホーム用のまとめ: 案件ごとの対象の要約（一覧の応答は targets を外すため）と観点カタログ。"""
    targets: dict[str, str] = {}
    try:
        for item in store.list_all():
            try:
                targets[item["id"]] = _target_text(store.load(item["id"]).get("targets") or [])
            except (KeyError, ValueError, OSError):
                log.warning("案件の対象を読めませんでした %s", item.get("id"))
    except OSError:
        log.exception("案件のまとめの取得に失敗")
        return err("案件のまとめを読めませんでした。時間をおいて再読み込みしてください。", 500)
    keys = ("id", "cat_name", "name", "technique", "priority", "levels")
    return jsonify(targets=targets, catalog=[{k: v.get(k) for k in keys} for v in catalog.CATALOG])


from web.routes import backend_test_stages, backend_test_run, backend_test_envs  # noqa: E402,F401  段階・実行のルートを同じ bp に載せる
