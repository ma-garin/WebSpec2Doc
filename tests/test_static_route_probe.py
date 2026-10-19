"""静的 route 候補の到達確認（System 03）。ブラウザは使わず、navigator を fake に差し替える。"""

from __future__ import annotations

import contextlib
import json

import pytest
from web.services import static_route_probe as probe
from web.services import static_route_probe_store as store

DOMAIN = "app.example.com"
ORIGIN = {"Origin": "http://localhost"}
SHA = "a" * 64


def _routes(*values: str) -> dict:
    return {"state": "ok", "evidence": [
        {"id": f"s{i}", "group": "route", "origin": "static", "value": v,
         "location": {"file": "app.js", "line": i}, "state": "static"}
        for i, v in enumerate(values, 1)
    ] + [{"id": "r1", "group": "route", "origin": "runtime", "value": "/runtime", "state": "observed"}]}  # fmt: skip


class FakeNav:
    """URL → NavResult / 例外 の表で動く navigator。開いた URL を記録する。"""

    def __init__(self, table: dict, states: int | None = 2) -> None:
        self.table, self.opened, self._states = table, [], states

    def goto(self, url: str) -> probe.NavResult:
        self.opened.append(url)
        out = self.table[url]
        if isinstance(out, Exception):
            raise out
        return out

    def states(self) -> int | None:
        return self._states


def _opener(nav: FakeNav):
    @contextlib.contextmanager
    def opener():
        yield nav

    return opener


@pytest.fixture(autouse=True)
def _safe(monkeypatch):
    monkeypatch.setattr(probe, "_is_safe_target", lambda url: "unsafe.test" not in url)
    probe._running.clear()
    yield
    probe._running.clear()


@pytest.fixture()
def site(tmp_path):
    snaps = tmp_path / DOMAIN / "snapshots"
    snaps.mkdir(parents=True)
    (snaps / "20261019-000000.json").write_text(json.dumps(
        [{"url": "https://other.test/x"}, {"url": f"https://{DOMAIN}/items"}]))
    ra = tmp_path / DOMAIN / "reverse_analysis"
    ra.mkdir()
    (ra / "run.json").write_text(json.dumps({"domain": DOMAIN, "snapshot_sha256": SHA}))
    return tmp_path


def _res(url: str, status: int = 200, final: str | None = None) -> probe.NavResult:
    return probe.NavResult(status, final or url)


SITE_ORIGIN = f"https://{DOMAIN}"


def test_classifies_six_kinds(site):
    nav = FakeNav({
        f"{SITE_ORIGIN}/ok": _res(f"{SITE_ORIGIN}/ok"),
        f"{SITE_ORIGIN}/gone": _res(f"{SITE_ORIGIN}/gone", 404),
        f"{SITE_ORIGIN}/moved": _res(f"{SITE_ORIGIN}/moved", final=f"{SITE_ORIGIN}/home"),
        f"{SITE_ORIGIN}/private": _res(f"{SITE_ORIGIN}/private", final=f"{SITE_ORIGIN}/Sign-In?next=/private"),
        f"{SITE_ORIGIN}/slow": probe.NavError("timeout"),
        f"{SITE_ORIGIN}/boom": RuntimeError("/Users/x/secret/path exploded"),
    })
    cands = _routes("/ok", "gone", "/moved", "private", "slow", "boom", "article/:slug", "unsafe.test")["evidence"][:-1]
    cands[-1] = {**cands[-1], "value": "x"}  # url は origin 固定。安全判定は origin ごと差し替えて別テスト
    items = probe.probe_candidates(SITE_ORIGIN, cands, nav)
    got = {i["route"]: i for i in items}
    assert [got[k]["status"] for k in ("/ok", "gone", "/moved", "private", "slow", "boom", "article/:slug")] == [
        "observed", "unreached", "unreached", "auth_required", "failed", "failed", "ambiguous"]
    assert got["/ok"]["observed_at"] and got["/ok"]["states_found"] == 2
    assert got["/moved"]["reason"] == "別の画面（/home）へ移動した"
    assert got["private"]["reason"] == "ログイン画面へ移動した"
    assert "timeout" not in got["slow"]["reason"] and "時間内" in got["slow"]["reason"]
    assert "/Users" not in got["boom"]["reason"] and "exploded" not in got["boom"]["reason"]
    assert all(got[k]["observed_at"] is None for k in got if k != "/ok")


def test_unsafe_url_is_failed_and_not_opened():
    nav = FakeNav({})
    res = probe.classify_route("https://unsafe.test", "x", nav)
    assert res["status"] == "failed" and nav.opened == []


def test_observed_only_when_path_matches():
    nav = FakeNav({f"{SITE_ORIGIN}/a": _res(f"{SITE_ORIGIN}/a/"), f"{SITE_ORIGIN}/b": _res(f"{SITE_ORIGIN}/b", final=f"{SITE_ORIGIN}/")})
    assert probe.classify_route(SITE_ORIGIN, "a", nav)["status"] == "observed"  # 末尾 / は正規化
    assert probe.classify_route(SITE_ORIGIN, "/b", nav)["status"] == "unreached"
    assert probe.classify_route(SITE_ORIGIN, "/a", nav)["url"] == f"{SITE_ORIGIN}/a"  # 先頭 / を重ねない


def test_ambiguous_is_not_opened():
    nav = FakeNav({})
    for v in ("users/:id", "*", "", "（値を特定できない）", "a/*/b"):
        assert probe.classify_route(SITE_ORIGIN, v, nav)["status"] == "ambiguous"
    assert nav.opened == []


def test_duplicate_value_opened_once_and_shared_by_all_ids():
    nav = FakeNav({f"{SITE_ORIGIN}/dup": _res(f"{SITE_ORIGIN}/dup")})
    items = probe.probe_candidates(SITE_ORIGIN, _routes("dup", "dup", "dup")["evidence"][:3], nav)
    assert nav.opened == [f"{SITE_ORIGIN}/dup"]
    assert [i["evidence_id"] for i in items] == ["s1", "s2", "s3"]
    assert {i["status"] for i in items} == {"observed"}


class _Req:
    def __init__(self, method):
        self.method = method


class _Route:
    def __init__(self, method):
        self.request, self.calls = _Req(method), []

    def abort(self):
        self.calls.append("abort")

    def continue_(self):
        self.calls.append("continue")


def test_guard_route_aborts_everything_but_safe_methods():
    for m in ("POST", "PUT", "PATCH", "DELETE", "post", "TRACE", ""):
        r = _Route(m)
        probe.guard_route(r)
        assert r.calls == ["abort"], m
    for m in ("GET", "HEAD", "OPTIONS"):
        r = _Route(m)
        probe.guard_route(r)
        assert r.calls == ["continue"], m


def test_run_saves_and_status_reports(site, monkeypatch):
    nav = FakeNav({f"{SITE_ORIGIN}/ok": _res(f"{SITE_ORIGIN}/ok"), f"{SITE_ORIGIN}/moved": _res(f"{SITE_ORIGIN}/moved", final=f"{SITE_ORIGIN}/home")})
    ev = _routes("ok", "moved", "p/:id")
    res = probe.run_probe(site, DOMAIN, ev, _opener(nav))
    assert res.result == "success"
    assert nav.opened == [f"{SITE_ORIGIN}/ok", f"{SITE_ORIGIN}/moved"]  # 起点は DOMAIN 一致の最初のページ
    doc = json.loads(store.probe_path(site, DOMAIN).read_text())
    assert doc["rea_snapshot_sha256"] == SHA and len(doc["items"]) == 3
    monkeypatch.setattr(probe, "build_viewpoints", lambda e: {"viewpoints": [
        {"evidence_id": "s1", "text": "ok に遷移できる", "is_new": True},
        {"evidence_id": "s2", "text": "moved", "is_new": True}]})
    st = probe.build_status(site, DOMAIN, ev)
    assert st["state"] == "ok" and st["before"] == {"static_routes": 3}
    assert st["after"] == {"observed": 1, "unreached": 1, "auth_required": 0, "ambiguous": 1,
                           "failed": 0, "promoted": 1, "system02_runnable": 1}
    by = {i["evidence_id"]: i for i in st["items"]}
    assert by["s1"]["system02_viewpoints"] == ["ok に遷移できる"] and by["s2"]["system02_viewpoints"] == []
    assert by["s1"]["status_label"] == "実測で到達" and st["can_run"] and st["finished_at"]


def test_saved_result_not_used_for_other_rea_result(site):
    ev = _routes("ok")
    probe.run_probe(site, DOMAIN, ev, _opener(FakeNav({f"{SITE_ORIGIN}/ok": _res(f"{SITE_ORIGIN}/ok")})))
    assert store.load(site, DOMAIN) is not None
    (site / DOMAIN / "reverse_analysis" / "run.json").write_text(
        json.dumps({"domain": DOMAIN, "snapshot_sha256": "b" * 64}))
    assert store.load(site, DOMAIN) is None
    assert probe.build_status(site, DOMAIN, ev)["state"] == "not_run"


def test_no_rea(site):
    assert probe.run_probe(site, DOMAIN, {"state": "empty"}).result == "no_rea"
    assert probe.run_probe(site, DOMAIN, {"state": "ok", "evidence": []}).result == "no_rea"
    st = probe.build_status(site, DOMAIN, {"state": "empty"})
    assert st["state"] == "no_rea" and st["can_run"] is False and st["cannot_run_reason"]


def test_browser_failure_is_error_and_keeps_old_result(site):
    @contextlib.contextmanager
    def broken():
        raise RuntimeError("chromium missing at /abs/path")
        yield

    res = probe.run_probe(site, DOMAIN, _routes("ok"), broken)
    assert res.result == "error" and "/abs" not in res.message
    assert not store.probe_path(site, DOMAIN).exists() and not probe.is_running(DOMAIN)


def test_busy_when_running(site):
    probe._running.add(DOMAIN)
    assert probe.run_probe(site, DOMAIN, _routes("ok"), _opener(FakeNav({}))).result == "busy"
    assert probe.build_status(site, DOMAIN, _routes("ok"))["can_run"] is False


@pytest.fixture()
def client(site, monkeypatch):
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    import web.routes.static_route_probe as mod

    monkeypatch.setattr(mod, "scoped_output_dir", lambda _b: site)
    holder = {"ev": _routes("ok"), "nav": FakeNav({f"{SITE_ORIGIN}/ok": _res(f"{SITE_ORIGIN}/ok")})}
    monkeypatch.setattr(mod, "site_evidence", lambda d: holder["ev"])
    monkeypatch.setattr(probe, "playwright_navigator", _opener(holder["nav"]))
    from web import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client(), holder


def test_api_post_get_and_busy_and_no_rea(client):
    c, holder = client
    url = f"/api/sites/{DOMAIN}/static-routes/probe"
    assert c.get(url).get_json()["state"] == "not_run"
    r = c.post(url, headers=ORIGIN)
    assert r.status_code == 200 and r.get_json()["result"] == "success"
    body = c.get(url).get_json()
    assert body["state"] == "ok" and body["after"]["observed"] == 1
    probe._running.add(DOMAIN)
    assert c.post(url, headers=ORIGIN).status_code == 409
    assert c.post(url, headers=ORIGIN).get_json()["result"] == "busy"
    probe._running.clear()
    holder["ev"] = {"state": "empty"}
    r = c.post(url, headers=ORIGIN)
    assert r.status_code == 422 and r.get_json()["result"] == "no_rea"
    assert c.get("/api/sites/bad%2Fname/static-routes/probe").status_code in (400, 404)
