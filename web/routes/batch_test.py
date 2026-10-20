"""バッチ・スクリプトのテスト（System 07）。処理の中身は web/services/batchtest/ にある。"""
from __future__ import annotations

import logging
import re

from flask import Blueprint, Response, g, jsonify, render_template, request

from web.auth import auth_enabled
from web.routes.backend_test import actor
from web.services.batchtest import codegen, design, export, parse, store

bp = Blueprint("batch_test", __name__)
log = logging.getLogger(__name__)
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_SPEC_SUFFIX = (".txt", ".md", ".docx", ".xlsx", ".pdf")


_AUDIT_MAX = 50  # 操作履歴（誰がいつ何をしたか）の保持件数


@bp.before_request
def _check_write_permission():
    """書き込みは案件の作成者・メンバーだけ（認証オン時）。操作者は System 08 と同じ actor() で取る。
    メンバーを持たない従来の案件は誰でも書ける（操作者は記録する）。認証オフでは制限しない。"""
    if request.method in ("GET", "HEAD", "OPTIONS") or not request.view_args or "jid" not in request.view_args:
        return None
    if not auth_enabled():
        return None
    try:
        members = store.load(request.view_args["jid"]).get("members")
    except (KeyError, ValueError, OSError):
        return None  # 存在しない・壊れた案件は各ルートが 404/500 を返す
    user = getattr(g, "auth_user", None)
    if members and actor() not in members and not (isinstance(user, dict) and user.get("role") == "admin"):
        return _err("この案件を変更する権限がありません。管理者に権限の付与を依頼してください。", 403)
    return None


@bp.after_request
def _record_actor(resp):
    """書き込みが成功したら、操作者・時刻・操作を案件に残す。新規作成者はメンバー（owner）になる。"""
    if request.method in ("GET", "HEAD", "OPTIONS") or resp.status_code >= 400:
        return resp
    try:
        jid = (request.view_args or {}).get("jid")
        created = request.method == "POST" and jid is None
        if created:
            jid = ((resp.get_json(silent=True) or {}).get("job") or {}).get("id")
        if not jid:
            return resp
        try:
            job = store.load(jid)
        except KeyError:  # 削除された案件には残す先がない
            return resp
        who = actor()
        entry = {"at": store.now(), "actor": who, "op": f"{request.method} {request.url_rule.rule}"}
        extra = {"members": {who: "owner"}, "created_by": who} if created else {}
        store.save({**job, **extra, "updated_by": who,
                    "audit": [*(job.get("audit") or []), entry][-_AUDIT_MAX:]})
    except (ValueError, OSError):
        log.exception("操作者の記録に失敗")
    return resp


def _err(message: str, status: int):
    return jsonify(error=message), status


def _load(jid: str):
    try:
        return store.load(jid), None
    except KeyError:
        return None, _err("案件が見つかりません。一覧から選び直してください。", 404)
    except (ValueError, OSError):
        log.exception("案件の読み込みに失敗 %s", jid)
        return None, _err("案件を読めませんでした。時間をおいて再読み込みしてください。", 500)


@bp.route("/batch-test")
def page() -> str:
    return render_template("batch_test.html")


@bp.route("/api/batch-test/jobs", methods=["GET"])
def list_jobs():
    try:
        return jsonify(jobs=store.list_all())
    except OSError:
        log.exception("案件一覧の取得に失敗")
        return _err("案件の一覧を読めませんでした。時間をおいて再読み込みしてください。", 500)


@bp.route("/api/batch-test/jobs", methods=["POST"])
def create_job():
    name = str((request.get_json(silent=True) or {}).get("name") or "").strip()
    if not name or len(name) > 100:
        return _err("案件名を 1〜100 文字で入れてください。", 400)
    return jsonify(job=store.save(store.new(name))), 201


@bp.route("/api/batch-test/jobs/<jid>", methods=["GET"])
def get_job(jid: str):
    job, err = _load(jid)
    return err or jsonify(job=job)


@bp.route("/api/batch-test/jobs/<jid>", methods=["PATCH"])
def update_job(jid: str):
    job, err = _load(jid)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    if "name" in body:
        name = str(body["name"] or "").strip()
        if not name or len(name) > 100:
            return _err("案件名を 1〜100 文字で入れてください。", 400)
        job = {**job, "name": name}
    settings = dict(job["settings"])
    for key, allowed in (("env", store.ENVS), ("framework", store.FRAMEWORKS)):
        if key in body:
            if body[key] not in allowed:
                return _err("選べない値です。一覧から選び直してください。", 400)
            settings[key] = body[key]
    if "command" in body:
        settings["command"] = str(body["command"] or "")[:300]
    return jsonify(job=store.save({**job, "settings": settings}))


@bp.route("/api/batch-test/jobs/<jid>", methods=["DELETE"])
def delete_job(jid: str):
    job, err = _load(jid)
    if err:
        return err
    import shutil
    shutil.rmtree(store.job_dir(job["id"]), ignore_errors=True)
    return jsonify(ok=True)


@bp.route("/api/batch-test/jobs/<jid>/files", methods=["POST"])
def upload(jid: str):
    job, err = _load(jid)
    if err:
        return err
    uploads = request.files.getlist("files")
    if not uploads:
        return _err("ファイルが選ばれていません。スクリプトか仕様書を選んでください。", 400)
    try:
        for f in uploads:
            job = store.add_file(job, f.filename or "", f.read())
    except store.StoreError as exc:
        return _err(str(exc), 400)
    return jsonify(job=store.save(job))


@bp.route("/api/batch-test/jobs/<jid>/files/<path:name>", methods=["PATCH", "DELETE"])
def change_file(jid: str, name: str):
    job, err = _load(jid)
    if err:
        return err
    try:
        if request.method == "DELETE":
            job = store.remove_file(job, name)
        else:
            kind = (request.get_json(silent=True) or {}).get("kind")
            if kind not in store.KINDS or not any(f["name"] == name for f in job["files"]):
                return _err("種類を一覧から選び直してください。", 400)
            job = {**job, "files": [{**f, "kind": kind} if f["name"] == name else f for f in job["files"]]}
    except KeyError:
        return _err("そのファイルは取り込まれていません。一覧を再読み込みしてください。", 404)
    return jsonify(job=store.save(job))


def _read_spec(job: dict) -> tuple[list[dict], list[str]]:
    from web.services.docverify.ingest import IngestError, ingest
    passages, notes = [], []
    for f in job["files"]:
        if f["kind"] != "spec" or not f["name"].lower().endswith(_SPEC_SUFFIX):
            continue
        try:
            path = store.file_path(job, f["name"])
            _, ps = ingest(f["name"], path.read_bytes(), store.job_dir(job["id"]) / "spec_work")
            passages += [{"file": f["name"], "text": p["text"], "location": p["location"]} for p in ps]
        except IngestError as exc:
            notes.append(f"{f['name']}: {exc}")
    return passages, notes


@bp.route("/api/batch-test/jobs/<jid>/analyze", methods=["POST"])
def analyze(jid: str):
    job, err = _load(jid)
    if err:
        return err
    scripts = [f for f in job["files"] if f["kind"] == "script"]
    if not scripts:
        return _err("スクリプトがありません。.bat / .cmd / .sh / .ps1 を取り込んでください。", 400)
    if len(scripts) > 1:
        return _err("スクリプトは 1 案件 1 本です。テストしないスクリプトを外してください。", 400)
    try:
        text = parse.read_text(store.file_path(job, scripts[0]["name"]))
        facts = parse.analyze(text, scripts[0]["name"])
        spec, notes = _read_spec(job)
    except OSError:
        log.exception("読み取りに失敗 %s", jid)
        return _err("ファイルを読めませんでした。もう一度取り込んでください。", 500)
    settings = dict(job["settings"])
    settings["env"] = facts["dialect"]
    holes = set(re.findall(r"\{([^{}]+)\}", settings.get("command") or ""))
    if holes != {a["name"] for a in facts["args"]} or scripts[0]["name"] not in (settings.get("command") or ""):
        settings["command"] = parse.default_command(facts)
    job = store.save({**job, "facts": facts, "spec": spec, "settings": settings, "analyzed_at": store.now()})
    return jsonify(job=job, notes=notes)


@bp.route("/api/batch-test/jobs/<jid>/cases", methods=["POST"])
def make_cases(jid: str):
    job, err = _load(jid)
    if err:
        return err
    if not job.get("facts"):
        return _err("先に「読み取る」を押して、スクリプトを読み取ってください。", 400)
    manual = [c for c in job["cases"] if c.get("origin") == "manual"]
    cases = design.renumber(design.design(job["facts"], job["spec"], job["files"], job["settings"]["command"]) + manual)
    return jsonify(job=store.save({**job, "cases": cases, "designed_at": store.now(), "sources": []}))


@bp.route("/api/batch-test/jobs/<jid>/cases/<cid>", methods=["PATCH"])
def edit_case(jid: str, cid: str):
    job, err = _load(jid)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    exp = str(body.get("exp") or "").strip()[:300]
    if not exp:
        return _err("期待結果を入れてください。", 400)
    code = body.get("code")
    if code not in (None, "") and not re.fullmatch(r"\d{1,3}", str(code)):
        return _err("終了コードは 0〜999 の数で入れてください。", 400)
    hit = False
    cases = []
    for c in job["cases"]:
        if c["id"] == cid:
            hit = True
            c = {**c, "exp": exp, "ask": False, "src": c["src"] if c["src"] != "—" else "利用者が記入",
                 "expect": {**c["expect"], "code": int(code) if code not in (None, "") else c["expect"]["code"]}}
        cases.append(c)
    if not hit:
        return _err("そのケースは見つかりません。ケース表を再読み込みしてください。", 404)
    return jsonify(job=store.save({**job, "cases": cases, "sources": []}))


@bp.route("/api/batch-test/jobs/<jid>/cases/add", methods=["POST"])
def add_case(jid: str):
    job, err = _load(jid)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    pre, exp = str(body.get("pre") or "").strip()[:200], str(body.get("exp") or "").strip()[:300]
    argv = [a for a in str(body.get("args") or "").split() if a][:20]
    code = body.get("code")
    if not pre or not exp:
        return _err("前提・入力と期待結果を入れてください。", 400)
    if code not in (None, "") and not re.fullmatch(r"\d{1,3}", str(code)):
        return _err("終了コードは 0〜999 の数で入れてください。", 400)
    head = (job["settings"]["command"] or (job.get("facts") or {}).get("script", "")).split(" {")[0]
    case = {"id": "", "obs": str(body.get("obs") or "追加").strip()[:20], "tech": "経験ベース", "pre": pre,
            "argv": argv, "run": " ".join([head, *argv]).strip(), "exp": exp, "src": "利用者が記入",
            "ask": False, "origin": "manual",
            "setup": {"inputs": "sample", "unset_env": [], "lock": False, "rerun": False, "outdir_missing": False},
            "expect": {"code": int(code) if code not in (None, "") else None, "output": None, "log": None}}
    return jsonify(job=store.save({**job, "cases": design.renumber(job["cases"] + [case]), "sources": []}))


@bp.route("/api/batch-test/jobs/<jid>/code", methods=["POST"])
def make_code(jid: str):
    job, err = _load(jid)
    if err:
        return err
    if not job.get("facts"):
        return _err("先にスクリプトを読み取ってください。", 400)
    try:
        sources = codegen.generate(job["facts"], job["cases"], job["files"], job["settings"]["framework"])
    except ValueError as exc:
        return _err(str(exc), 400)
    return jsonify(job=store.save({**job, "sources": sources, "generated_at": store.now()}))


@bp.route("/api/batch-test/jobs/<jid>/export/<kind>", methods=["GET"])
def download(jid: str, kind: str):
    job, err = _load(jid)
    if err:
        return err
    stem = re.sub(r"[^\w-]", "_", (job.get("facts") or {}).get("script", "batch").rsplit(".", 1)[0])
    try:
        if kind == "cases.xlsx":
            if not job["cases"]:
                return _err("ケースがまだありません。先にケース表を作ってください。", 400)
            data, mime, fname = export.cases_xlsx(job), _XLSX, f"{stem}_cases.xlsx"
        elif kind == "code.zip":
            data, mime, fname = export.code_zip(job), "application/zip", f"{stem}_tests.zip"
        elif kind == "questions.csv":
            data, mime, fname = export.questions_csv(job), "text/csv; charset=utf-8", f"{stem}_questions.csv"
        else:
            return _err("書き出せない種類です。", 404)
    except ValueError as exc:
        return _err(str(exc), 400)
    _record_export(job, kind)
    return Response(data, mimetype=mime, headers={"Content-Disposition": f"attachment; filename={fname}"})


def _record_export(job: dict, kind: str) -> None:
    """書き出し（サーバからの送出）を案件に残す。リロード後も「書き出し済み（未実行）」と分かるようにする。

    受け取ったか・実行したか・確かめたかは記録しない。中身の指紋（basis）を持ち、後でケースやコードが
    変わったら store.with_export_state が stale を付ける。記録に失敗しても書き出し自体は止めない。
    """
    rec = {"at": store.now(), "actor": actor(), "basis": store.export_basis(job, kind),
           "cases": len(job.get("cases") or []), "sources": len(job.get("sources") or [])}
    try:
        store.save({**job, "exports": {**(job.get("exports") or {}), kind: rec}})
    except (ValueError, OSError):
        log.exception("書き出しの記録に失敗 %s %s", job.get("id"), kind)
