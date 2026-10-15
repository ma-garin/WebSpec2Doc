"""影響度分析（System 09）のシステムテスト（画面を使わない項目）。ID は 07-system-test.md の ST-xxx。"""
from __future__ import annotations

import statistics
import time

import pytest

import app as appmod
from web import config, tenancy
from web.routes import impact_api
from web.services.impact import db, jobs
from web.services.impact.engine import run as engine_run
from web.services.impact.repo import crs, systems

API = "/api/impact/v2"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    impact_api._RECOVERED.clear()
    return tmp_path


def _bulk_items(conn, sid: str, n: int) -> None:
    """項目 n 件を直接入れる（取り込みの時間を測定から外す）。1 割に「電話番号」を含める。"""
    did = db.new_id()
    conn.execute("INSERT INTO documents(id, system_id, name, kind, size, item_count, sha256, created_by, created_at) "
                 "VALUES (?,?,?,?,?,?,?,?,?)", (did, sid, "大規模設計書.md", "design", 0, n, "", "local", db.now()))
    words = ["会員", "注文", "在庫", "配送", "請求", "ポイント", "通知", "検索", "帳票", "権限"]
    rows = []
    for i in range(n):
        topic = "電話番号の入力チェックを行う" if i % 10 == 0 else f"{words[i % 10]}の処理 {i} を行う"
        rows.append((db.new_id(), sid, did, f"DSN-{i:05d}", f"- {topic}。共通部品 {i % 37} を使う。", f"{i + 1}行", "設計", i))
    conn.executemany("INSERT INTO items(id, system_id, document_id, code, text, location, section, ord) "
                     "VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit()


def test_st003_rule_analysis_10k_items_under_30s(env):
    """ST-003 Given 項目 10,000・変更 5 When 縮退で分析を 3 回 Then 中央値 30 秒以内。"""
    conn = db.connect()
    sid = systems.create(conn, "大規模", "", "local")["id"]
    _bulk_items(conn, sid, 10_000)
    text = ("電話番号を必須にする。電話番号の桁数を11桁にする。会員の退会時に注文を取り消す。"
            "在庫の引当を夜間に行う。請求書の発行日を月末にする。")
    times = []
    for k in range(3):
        cr = crs.create(conn, sid, f"大規模 {k}", "性能測定", text, None, None, 2, "local")
        t0 = time.perf_counter()
        engine_run.analyze(conn, sid, cr["code"], "local", lambda *a, **kw: None, lambda: False)
        times.append(time.perf_counter() - t0)
        made = conn.execute("SELECT COUNT(*) n FROM impacts WHERE cr_id=?", (cr["id"],)).fetchone()["n"]
        assert made >= 100, f"影響が {made} 件しか作られていない（空振りの測定になっている）"
    med = statistics.median(times)
    print(f"ST-003 影響 {made} 件")
    print(f"ST-003 中央値 {med:.2f} 秒（{', '.join(f'{x:.2f}' for x in times)}）")
    assert med <= 30.0


def test_st006_interrupted_job_is_recovered(env):
    """ST-006 Given 分析中にプロセスが止まった（running のまま） When 再起動後に DB を開く Then 中断になり CR は起票に戻り、再分析できる。"""
    conn = db.connect()
    sid = systems.create(conn, "復帰", "", "local")["id"]
    cr = crs.create(conn, sid, "電話番号", "理由", "電話番号を必須にする。", None, None, 1, "local")
    conn.execute("UPDATE change_requests SET status='analyzing' WHERE id=?", (cr["id"],))
    conn.execute("INSERT INTO jobs(id, cr_id, status, stage, progress, message, cancel, started_at) "
                 "VALUES ('deadjob00001', ?, 'running', 'candidates', 40, '', 0, ?)", (cr["id"], db.now()))
    conn.commit()
    assert jobs.recover(conn) >= 1
    assert conn.execute("SELECT status FROM jobs WHERE id='deadjob00001'").fetchone()["status"] == "interrupted"
    assert crs.get(conn, sid, cr["code"])["status"] == "draft"
    client = appmod.app.test_client()
    job = client.post(f"{API}/systems/{sid}/crs/{cr['code']}/analyze", json={}).get_json()["job"]
    end = time.time() + 15
    while time.time() < end and client.get(f"{API}/jobs/{job['id']}").get_json()["job"]["status"] not in ("done", "failed"):
        time.sleep(0.2)
    assert client.get(f"{API}/jobs/{job['id']}").get_json()["job"]["status"] == "done"


def test_st007_other_tenant_cannot_see(env, monkeypatch):
    """ST-007 Given テナント A の対象システム When テナント B から ID を指定 Then 404（存在を明かさない）。"""
    slug = {"v": "tenant-a"}
    monkeypatch.setattr(tenancy, "_tenant_slug", lambda: slug["v"])
    client = appmod.app.test_client()
    sid = client.post(f"{API}/systems", json={"name": "A の対象"}).get_json()["system"]["id"]
    assert client.get(f"{API}/systems/{sid}").status_code == 200
    slug["v"] = "tenant-b"
    impact_api._RECOVERED.clear()
    assert client.get(f"{API}/systems/{sid}").status_code == 404
    assert client.get(f"{API}/systems/{sid}/crs").status_code == 404
    assert client.get(f"{API}/systems").get_json()["systems"] == []
    assert (env / "tenants" / "tenant-a" / "impact" / "impact.db").exists()
