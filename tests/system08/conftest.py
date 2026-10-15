"""System 08（バックエンドテスト）のテスト共通部品。DATA_DIR は tmp_path、LLM は送らない。"""
from __future__ import annotations

import getpass

import pytest

from web import config
from web.services.backendtest import dbconn, llm_gate, store

DDL = b"""CREATE TABLE orders (
  order_id integer PRIMARY KEY,
  customer_id integer NOT NULL,
  amount numeric(10,2) NOT NULL,
  status varchar(10) NOT NULL DEFAULT 'new',
  updated_at timestamp
);
CREATE TABLE order_summary (
  ym char(6) PRIMARY KEY,
  total numeric(12,2) NOT NULL
);
"""


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture()
def no_llm(monkeypatch):
    """外部・ローカルの LLM に送らない（送れば失敗として扱われ、補強だけ省かれる）。"""
    def fake_send(*args, **kwargs):
        raise store.StoreError("テストでは LLM に送りません。")
    monkeypatch.setattr(llm_gate, "send", fake_send)


@pytest.fixture()
def client(data_dir, no_llm):
    import app as appmod
    return appmod.app.test_client()


@pytest.fixture()
def pg_env():
    """ローカルの PostgreSQL。接続できなければ理由付きで skip。"""
    env = {"name": "ローカル検証", "db": {"kind": "postgresql", "host": "localhost", "port": 5432,
                                       "dbname": "postgres", "user": getpass.getuser()}}
    try:
        conn = dbconn.connect(env, None, True)
    except store.StoreError as exc:
        pytest.skip(f"ローカルの PostgreSQL に接続できないため実 DB の検証を省略: {exc}")
    conn.close()
    return env
