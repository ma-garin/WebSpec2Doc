"""AC: 案件作成〜段階 1〜6 の生成・承認〜実行前の守り〜報告書の書き出し（Flask test_client）。"""
from __future__ import annotations

import io

from web.services.backendtest import store

from .conftest import DDL

JOBS = "/api/backend-test/jobs"


def _create(client, name="月次締め"):
    r = client.post(JOBS, json={"name": name, "target_kind": "batch", "level": "system"})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["job"]


def _version(client, jid, n):
    return client.get(f"{JOBS}/{jid}").get_json()["job"]["stages"][str(n)]["version"]


def _generate(client, jid, n, body=None):
    return client.post(f"{JOBS}/{jid}/stages/{n}/generate", json=body or {})


def _approve(client, jid, n, actor=None):
    body = {"version": _version(client, jid, n), **({"actor": actor} if actor else {})}
    return client.post(f"{JOBS}/{jid}/stages/{n}/approve", json=body)


def _upload(client, jid):
    r = client.post(f"{JOBS}/{jid}/files", data={"files": [(io.BytesIO(DDL), "schema.sql")]},
                    content_type="multipart/form-data")
    assert r.status_code in (200, 201), r.get_json()


def _through(client, jid, last):
    for n in range(1, last + 1):
        r = _generate(client, jid, n, {"purpose": "月次締めの集計を確かめる", "scope": "orders"} if n == 1 else None)
        assert r.status_code == 200, (n, r.get_json())
        r = _approve(client, jid, n)
        assert r.status_code == 200, (n, r.get_json())


def _add_member(jid, name, role):
    job = store.load(jid)
    store.save({**job, "members": {**job["members"], name: role}})


def test_create_job_makes_creator_senior_member(client):
    """Given 認証オフ / When 案件を作る / Then 201 で作成者がシニア QA のメンバー。"""
    job = _create(client)
    assert job["members"] == {"local": "senior_qa"}
    assert client.post(JOBS, json={"name": ""}).status_code == 400
    assert client.get(f"{JOBS}/000000000000").status_code == 404


def test_stage2_before_stage1_approval_is_409(client):
    """Given 段階 1 生成済み・未承認 / When 段階 2 を生成 / Then 409。"""
    jid = _create(client)["id"]
    assert _generate(client, jid, 1, {"purpose": "目的"}).status_code == 200
    r = _generate(client, jid, 2)
    assert r.status_code == 409 and r.get_json()["error"]


def test_end_to_end_stages_run_guards_and_report(client):
    """Given DDL を取り込んだ案件 / When 段階 1〜6 を生成・承認し実行・書き出し
    / Then 6 未承認の実行は 409、書き込みを伴う実行は確認トークン無しで 428、本番は 409、報告書は xlsx。"""
    jid = _create(client)["id"]
    _upload(client, jid)
    _through(client, jid, 5)
    assert _generate(client, jid, 6).status_code == 200
    env = client.post(f"{JOBS}/{jid}/envs", json={"name": "検証", "db": {"host": "127.0.0.1", "port": 1,
                                                                        "dbname": "bt", "user": "u"}})
    assert env.status_code in (200, 201), env.get_json()
    eid = env.get_json()["job"]["envs"][0]["id"]
    assert client.post(f"{JOBS}/{jid}/runs", json={"env_id": eid}).status_code == 409   # 段階 6 未承認
    assert _approve(client, jid, 6).status_code == 200

    preview = client.post(f"{JOBS}/{jid}/runs/preview", json={"env_id": eid})
    assert preview.status_code == 200 and preview.get_json()["writes"] is True
    assert preview.get_json()["confirm_token"]
    r = client.post(f"{JOBS}/{jid}/runs", json={"env_id": eid})
    assert r.status_code == 428 and r.get_json()["error"]

    prod = client.post(f"{JOBS}/{jid}/envs", json={"name": "本番", "db": {"host": "127.0.0.1", "dbname": "bt"}})
    pid = prod.get_json()["job"]["envs"][-1]["id"]
    assert client.post(f"{JOBS}/{jid}/runs", json={"env_id": pid}).status_code == 409

    x = client.get(f"{JOBS}/{jid}/export/report.xlsx")
    assert x.status_code == 200 and x.data[:2] == b"PK"
    stages = client.get(f"{JOBS}/{jid}").get_json()["job"]["stages"]
    assert all(stages[str(n)]["status"] == "approved" for n in range(1, 7))


def test_qa_member_cannot_approve_stage4_and_outsider_is_rejected(client, monkeypatch):
    """Given 認証オフ（本文の actor で操作者を指定）と qa ロールのメンバー・非メンバー
    / When 段階 4 承認・生成 / Then どちらも 403。"""
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    jid = _create(client)["id"]
    _upload(client, jid)
    _through(client, jid, 3)
    assert _generate(client, jid, 4).status_code == 200
    _add_member(jid, "qa1", "qa")
    r = _approve(client, jid, 4, actor="qa1")
    assert r.status_code == 403 and "シニア QA" in r.get_json()["error"]
    assert client.post(f"{JOBS}/{jid}/stages/4/generate", json={"actor": "stranger"}).status_code == 403
    assert _approve(client, jid, 4).status_code == 200


def test_stage2_reads_ddl_into_facts_with_source_lines(client):
    """Given DDL を取り込んだ案件 / When 段階 2 を生成 / Then 表・列の事実が取り込んだファイルと行番号付きで出る。"""
    jid = _create(client)["id"]
    _upload(client, jid)
    _through(client, jid, 1)
    r = _generate(client, jid, 2)
    assert r.status_code == 200, r.get_json()
    facts = r.get_json()["job"]["facts"]
    about_orders = [f for f in facts if "orders" in str(f.get("subject"))]
    assert about_orders, facts[:3]
    src = about_orders[0].get("source") or {}
    assert src.get("file") == "schema.sql" and int(src.get("line") or 0) >= 1
