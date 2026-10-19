"""reverse analysis の runtime 入力の契約。

守るべきは「snapshot に無いことを書かないこと」。既存 snapshot は API の origin と
query を保存しないため、画面 URL の origin を API の接続先に流用してはならない。
各観測は snapshot の digest と実在する JSON pointer へ戻れなければならない。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from crawler.page_crawler import ApiEndpoint, PageData
from diff.snapshot import save_snapshot
from reverse_analysis.models import RuntimeObservation
from reverse_analysis.runtime import load_runtime_observations, resolve_json_pointer


def _page(url: str, calls: tuple[ApiEndpoint, ...]) -> PageData:
    return PageData(
        url=url,
        title="画面",
        headings=(),
        links=(),
        forms=(),
        screenshot_path=None,
        api_calls=calls,
    )


def _saved_snapshot(tmp_path: Path) -> Path:
    pages = [
        _page(
            "https://app.example.com/orders",
            (
                ApiEndpoint("get", "/api/orders", 200, "application/json", ("id", "total")),
                ApiEndpoint("POST", "/api/orders", 201, "application/json", ()),
            ),
        ),
        _page("https://app.example.com/about", ()),
        _page(
            "https://app.example.com/users/1",
            (ApiEndpoint("GET", "/api/users/1", 200, "application/json", ("name",)),),
        ),
    ]
    return save_snapshot(pages, tmp_path)


def _write(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_各観測はsnapshot_digestと実在するJSON_pointerへ戻れる(tmp_path: Path) -> None:
    """既存の save_snapshot で保存した実ファイルから、出典へ戻れる観測を作る。"""
    snapshot = _saved_snapshot(tmp_path)
    raw = json.loads(snapshot.read_text(encoding="utf-8"))
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()

    result = load_runtime_observations(snapshot)

    assert result.coverage.status == "complete"
    assert result.snapshot_sha256 == digest
    assert len(result.observations) == 3
    for observation in result.observations:
        assert observation.snapshot_sha256 == digest
        source = resolve_json_pointer(raw, observation.json_pointer)
        assert source["method"].upper() == observation.method
        assert source["path"] == observation.path
        assert source["status_code"] == observation.status_code
    assert [o.json_pointer for o in result.observations] == [
        "/0/api_calls/0",
        "/0/api_calls/1",
        "/2/api_calls/0",
    ]


def test_画面URLのoriginをAPI_originにせずqueryは保持されない旨を残す(tmp_path: Path) -> None:
    """page_url は記録するが、API の origin は null・query_scope は not_retained。"""
    result = load_runtime_observations(_saved_snapshot(tmp_path))

    for observation in result.observations:
        assert observation.page_url.startswith("https://app.example.com/")
        assert observation.origin is None
        assert observation.query_scope == "not_retained"
        assert observation.epistemic_state == "observed"
    assert "runtime_origin_not_recorded" in result.coverage.limitations
    assert "runtime_query_not_retained" in result.coverage.limitations


def test_originを捏造したRuntimeObservationは作れない() -> None:
    with pytest.raises(ValueError):
        RuntimeObservation(
            id="ro-x",
            snapshot_sha256="0" * 64,
            json_pointer="/0/api_calls/0",
            page_url="https://app.example.com/",
            method="GET",
            path="/api",
            status_code=200,
            content_type="",
            sample_fields=(),
            origin="https://app.example.com",  # type: ignore[arg-type]
        )


def test_methodを大文字化しpathは加工しない(tmp_path: Path) -> None:
    result = load_runtime_observations(_saved_snapshot(tmp_path))

    assert result.observations[0].method == "GET"
    # 数値 segment をテンプレート化しない（/api/users/{id} にしない）
    assert result.observations[2].path == "/api/users/1"


def test_同一内容の重複呼び出しは別のpointerを持つ(tmp_path: Path) -> None:
    call = {
        "method": "GET",
        "path": "/api/ping",
        "status_code": 200,
        "content_type": "",
        "sample_fields": [],
    }
    path = _write(tmp_path, [{"url": "https://a.example/", "api_calls": [call, call]}])

    result = load_runtime_observations(path)

    assert [o.json_pointer for o in result.observations] == ["/0/api_calls/0", "/0/api_calls/1"]
    assert len({o.id for o in result.observations}) == 2


def test_同じsnapshotからは同じIDと順序が得られ入力を書き換えない(tmp_path: Path) -> None:
    snapshot = _saved_snapshot(tmp_path)
    before = snapshot.read_bytes()

    first = load_runtime_observations(snapshot)
    second = load_runtime_observations(snapshot)

    assert first == second
    assert snapshot.read_bytes() == before


def test_API呼び出しが無いsnapshotは空の完了でありunavailableではない(tmp_path: Path) -> None:
    path = _write(tmp_path, [{"url": "https://a.example/", "api_calls": []}])

    result = load_runtime_observations(path)

    assert result.observations == ()
    assert result.coverage.status == "complete"
    assert result.diagnostics == ()


def test_存在しないsnapshotはfailedで次の行動を示す(tmp_path: Path) -> None:
    result = load_runtime_observations(tmp_path / "missing.json")

    assert result.coverage.status == "failed"
    assert result.coverage.omitted_count is None
    assert result.diagnostics[0].code == "runtime_snapshot_missing"
    assert result.diagnostics[0].next_action
    assert str(tmp_path) not in result.diagnostics[0].message


def test_壊れたJSONはfailedで絶対pathを出さない(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.json"
    path.write_text("[{", encoding="utf-8")

    result = load_runtime_observations(path)

    assert result.coverage.status == "failed"
    assert result.observations == ()
    assert result.diagnostics[0].code == "runtime_snapshot_invalid_json"
    assert str(tmp_path) not in result.diagnostics[0].message


@pytest.mark.parametrize(
    ("payload", "pointer"),
    [
        ({"url": "x"}, "/"),
        ([["not-a-page"]], "/0"),
        ([{"title": "url 欠損"}], "/0/url"),
        ([{"url": "x", "api_calls": {}}], "/0/api_calls"),
        ([{"url": "x", "api_calls": [{"path": "/a", "status_code": 200}]}], "/0/api_calls/0/method"),
        (
            [{"url": "x", "api_calls": [{"method": "GET", "path": "/a", "status_code": True}]}],
            "/0/api_calls/0/status_code",
        ),
        (
            [
                {
                    "url": "x",
                    "api_calls": [
                        {"method": "GET", "path": "/a", "status_code": 200, "sample_fields": [1]}
                    ],
                }
            ],
            "/0/api_calls/0/sample_fields",
        ),
    ],
)
def test_構造が不正なsnapshotは黙って補完せずfailedにする(
    tmp_path: Path, payload: object, pointer: str
) -> None:
    """load_snapshot の既定値補完（method 欠損→空文字等）に頼らず、先に拒否する。"""
    result = load_runtime_observations(_write(tmp_path, payload))

    assert result.coverage.status == "failed"
    assert result.observations == ()
    assert result.diagnostics[0].code == "runtime_snapshot_invalid_schema"
    assert pointer in result.diagnostics[0].message


def test_最低限の検証を通っても既存ローダーで読めない入れ子はfailedにする(tmp_path: Path) -> None:
    """headings=null 等は既存 load_snapshot が例外を出す。traceback と絶対 path を出さない。"""
    payload = [{"url": "x", "headings": None, "api_calls": []}]

    result = load_runtime_observations(_write(tmp_path, payload))

    assert result.coverage.status == "failed"
    assert result.observations == ()
    assert result.diagnostics[0].code == "runtime_snapshot_invalid_schema"
    assert str(tmp_path) not in result.diagnostics[0].message
    assert "Traceback" not in result.diagnostics[0].message


@pytest.mark.parametrize("mode", ["deleted", "changed"])
def test_再読込で削除や変更を検出したらfailedにする(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    snapshot = _saved_snapshot(tmp_path)
    original = Path.read_bytes
    calls = {"n": 0}

    def flaky_read_bytes(self: Path) -> bytes:
        calls["n"] += 1
        if self == snapshot and calls["n"] >= 2:
            if mode == "deleted":
                raise FileNotFoundError(str(self))
            return b"[]"
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", flaky_read_bytes)

    result = load_runtime_observations(snapshot)

    assert result.coverage.status == "failed"
    assert result.observations == ()
    assert result.diagnostics[0].code == "runtime_snapshot_changed"
    assert str(tmp_path) not in result.diagnostics[0].message
