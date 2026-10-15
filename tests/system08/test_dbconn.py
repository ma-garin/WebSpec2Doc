"""AC: 本番判定・読み取り専用の強制（guard_sql）・接続失敗の理由にパスワードを出さない。"""
from __future__ import annotations

import logging

import psycopg
import pytest

from web.services.backendtest import dbconn, store


def _env(name="検証", host="db.stg.local", dbname="bt"):
    return {"name": name, "db": {"host": host, "dbname": dbname, "port": 5432, "user": "u"}}


@pytest.mark.parametrize("env,declared,recovery", [
    (_env(name="本番"), False, False), (_env(host="db01.prod.example.jp"), False, False),
    (_env(dbname="sales_live"), False, False), (_env(), True, False), (_env(), False, True)])
def test_classify_production_by_any_signal(env, declared, recovery):
    """Given 名前・ホスト・DB 名・申告・複製先のどれか 1 つ / When 判定 / Then 本番で理由が付く。"""
    got = dbconn.classify(env, declared, recovery)
    assert got["production"] is True and got["reasons"]


def test_classify_staging_is_not_production_unless_host_suffix_matches(monkeypatch):
    """Given 検証用の名前 / When 判定 / Then 本番でない。本番帯の接尾辞を設定すると本番。"""
    assert dbconn.classify(_env(), False) == {"production": False, "reasons": []}
    monkeypatch.setenv(dbconn.PROD_SUFFIX_ENV, ".stg.local")
    assert dbconn.classify(_env(), False)["production"] is True


def test_must_read_only_for_production_or_not_writable():
    assert dbconn.must_read_only({"production": True, "writable": True})
    assert dbconn.must_read_only({"production": False, "writable": False})
    assert not dbconn.must_read_only({"production": False, "writable": True})


@pytest.mark.parametrize("sql", [
    "INSERT INTO orders VALUES (1)", "update orders set amount = 0", "DELETE FROM orders",
    "CREATE TABLE x (a int)", "DROP TABLE orders", "ALTER TABLE orders ADD c int", "TRUNCATE orders",
    "VACUUM", "vacuum analyze orders", "LOCK TABLE orders", "SELECT * INTO o2 FROM orders",
    "WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d",
    "SELECT 1; DELETE FROM orders",
    "SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE",
    "SET transaction_read_only = off", "SET default_transaction_read_only TO off",
])
def test_guard_sql_rejects_writes_on_read_only(sql):
    """Given 読み取り専用の接続 / When DML・DDL・VACUUM・読み取り専用解除の SET / Then 拒否。"""
    with pytest.raises(store.StoreError, match="読み取り専用"):
        dbconn.guard_sql(sql, True)


@pytest.mark.parametrize("sql", ["SELECT * FROM orders", "WITH a AS (SELECT 1 AS n) SELECT n FROM a",
                                 "select count(*) from orders where status = 'new'"])
def test_guard_sql_allows_reads(sql):
    dbconn.guard_sql(sql, True)


def test_guard_sql_allows_writes_when_writable():
    dbconn.guard_sql("INSERT INTO orders VALUES (1)", False)


def test_connect_failure_message_and_log_have_no_password(caplog):
    """Given 到達できない接続先と秘密 / When 接続 / Then 理由と次の行動を返し、例外文とログに秘密が無い。"""
    secret = "Sup3r-S3cret-pw"
    env = _env(host="127.0.0.1")
    env["db"]["port"] = 1
    caplog.set_level(logging.DEBUG)
    with pytest.raises(store.StoreError) as exc:
        dbconn.connect(env, secret, True)
    assert secret not in str(exc.value) and "確かめ" in str(exc.value)
    assert exc.value.__cause__ is None
    assert secret not in caplog.text
    result = dbconn.check(env, secret)
    assert result["reachable"] is False and secret not in str(result)


def test_real_db_session_is_read_only(pg_env):
    """Given 実 DB に読み取り専用で接続 / When 書き込み / Then guard と DB セッションの両方で止まる。"""
    conn = dbconn.connect(pg_env, None, True)
    try:
        with conn.cursor() as cur:  # guard は transaction_read_only の語を安全側で拒否するため直接確かめる
            cur.execute("SHOW transaction_read_only")
            assert cur.fetchone()[0] == "on"
        assert dbconn.execute(conn, "SELECT 1 AS n", True) == [{"n": 1}]
        with pytest.raises(store.StoreError):
            dbconn.execute(conn, "CREATE TABLE bt_should_not_exist (a int)", True)
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            with conn.cursor() as cur:  # guard を通らない経路でも DB 側で拒否される
                cur.execute("CREATE TABLE bt_should_not_exist (a int)")
    finally:
        conn.rollback()
        conn.close()
