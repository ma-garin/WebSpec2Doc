"""AC: 案件の作成・版の退避・秘密キーの拒否・保存期間（store）。"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from web.services.backendtest import store


def _saved(name="月次締め", level="system"):
    return store.save(store.new(name, "batch", level))


def test_new_job_has_eight_draft_stages_and_defaults(data_dir):
    """Given 名前・種類・レベル / When 作成して保存 / Then 段階 1〜8 が下書き、保存期間 90 日、段階 4 はシニア QA 承認。"""
    job = _saved()
    loaded = store.load(job["id"])
    assert sorted(loaded["stages"]) == [str(n) for n in range(1, 9)]
    assert {s["status"] for s in loaded["stages"].values()} == {"draft"}
    assert loaded["retention_days"] == 90
    assert loaded["approver_roles"]["4"] == "senior_qa"
    assert (data_dir / "backendtest" / job["id"] / "job.json").is_file()


@pytest.mark.parametrize("name,kind,level", [
    ("", "batch", "system"), ("月次", "api", "system"), ("月次", "batch", "unit")])
def test_new_rejects_invalid_input(data_dir, name, kind, level):
    """Given 空の名前・未対応の種類・不明なレベル / When 作成 / Then 利用者に見せられる理由で拒否。"""
    with pytest.raises(store.StoreError):
        store.new(name, kind, level)


@pytest.mark.parametrize("envs,targets", [
    ([{"name": "検証", "db": {"host": "h", "password": "p"}}], []),
    ([], [{"id": "t1", "api_key": "k"}]),
    ([{"name": "検証", "token": "x"}], []),
])
def test_save_rejects_secret_keys_and_writes_nothing(data_dir, envs, targets):
    """Given 接続先・対象にパスワード・トークン系の欄 / When 保存 / Then 拒否し job.json を書かない。"""
    job = {**store.new("秘密", "batch", "system"), "envs": envs, "targets": targets}
    with pytest.raises(store.StoreError, match="パスワード"):
        store.save(job)
    assert not (data_dir / "backendtest" / job["id"] / "job.json").exists()


def test_versions_are_kept_and_trimmed_to_latest_ten(data_dir):
    """Given 段階 1 を 12 版保存 / When 版を読む / Then 直近 10 版だけ残り、中身はその版の成果物。"""
    job = _saved()
    for v in range(1, 13):
        stages = {**job["stages"], "1": {**job["stages"]["1"], "version": v}}
        store.save_version({**job, "purpose": f"目的 v{v}", "stages": stages}, 1)
    assert store.load_version(job["id"], 1, 12)["artifact"]["purpose"] == "目的 v12"
    assert store.load_version(job["id"], 1, 3)["artifact"]["purpose"] == "目的 v3"
    with pytest.raises(KeyError):
        store.load_version(job["id"], 1, 2)
    assert len(list(store.versions_dir(job["id"]).glob("1-v*.json"))) == store.MAX_VERSIONS


def _age(job: dict, days: int, **extra) -> None:
    old = (date.today() - timedelta(days=days)).isoformat() + "T00:00:00+00:00"
    path = store.job_dir(job["id"]) / "job.json"
    path.write_text(json.dumps({**job, "updated_at": old, **extra}, ensure_ascii=False), encoding="utf-8")


def test_purge_expired_respects_retention_and_running(data_dir):
    """Given 100 日前の案件（既定 90 日・365 日に上書き・実行中） / When 掃除 / Then 既定の案件だけ消え記録が残る。"""
    expired, kept, running = _saved("期限切れ"), _saved("延長"), _saved("実行中")
    _age(expired, 100)
    _age(kept, 100, retention_days=365)
    _age(running, 100, runs=[{"id": "r1", "status": "running"}])
    removed = store.purge_expired()
    assert removed == [expired["id"]]
    assert not store.job_dir(expired["id"]).exists()
    assert store.load(kept["id"])["name"] == "延長"
    assert store.load(running["id"])["name"] == "実行中"
    assert expired["id"] in (data_dir / "backendtest" / "purge.log").read_text(encoding="utf-8")


def test_delete_rejects_running_job(data_dir):
    """Given 実行中の案件 / When 削除 / Then 拒否され案件は残る。"""
    job = store.save({**store.new("実行中", "batch", "system"), "runs": [{"id": "r1", "status": "queued"}]})
    with pytest.raises(store.StoreError, match="実行中"):
        store.delete(job["id"])
    assert store.load(job["id"])["id"] == job["id"]
