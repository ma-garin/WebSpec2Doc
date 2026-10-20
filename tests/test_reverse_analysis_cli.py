"""Task 3: 明示 CLI → runtime 読込 → 静的解析 → 正規化 → 突合 → reverse_analysis.json 保存。

provider は導入・実行しない。偽の rea 実行ファイルが固定版 Evidence fixture
（tests/fixtures/reverse_analysis/PROVENANCE.md）を返す。
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

import main
from apispec.recovery import build_screen_api_map
from crawler.page_crawler import ApiEndpoint, PageData
from diff.snapshot import load_snapshot, save_snapshot
from reverse_analysis import reporter
from reverse_analysis.normalize import LIMIT_DIGEST_MISMATCH, LIMIT_FILE_NOT_VERIFIED
from reverse_analysis.rea_adapter import run_static_analysis
from reverse_analysis.reporter import (
    OUTPUT_FILENAME,
    TOP_LEVEL_KEYS,
    ReportSchemaError,
    load_document,
    validate_document,
)
from reverse_analysis.runtime import resolve_json_pointer
from reverse_analysis.service import (
    LIMIT_PROVIDER_NO_HTTP_METHOD,
    LIMIT_PROVIDER_NO_ROUTE,
    ReverseAnalysisRequest,
    run_reverse_analysis,
)

from test_reverse_analysis_adapter import load_fixture, pid_alive, recommit

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "reverse_analysis"
EVIDENCE_FIXTURE = FIXTURE_DIR / "rea_6_7_0_application_evidence.json"
RUNTIME_SNAPSHOT = FIXTURE_DIR / "runtime_snapshot.json"
VALUE_RECORD = FIXTURE_DIR / "value_measurement.json"
CLI_ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


# ---------------------------------------------------------------- 補助


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _fake_rea(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "fake-rea"
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys, time\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('6.7.0'); sys.exit(0)\n" + body,
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def _emit_fixture(tmp_path: Path) -> str:
    payload = tmp_path / "payload.json"
    shutil.copyfile(EVIDENCE_FIXTURE, payload)
    return f"sys.stdout.write(open({str(payload)!r}).read())\n"


def _snapshot(tmp_path: Path) -> Path:
    pages = [
        PageData(
            url="https://app.example.com/orders",
            title="注文",
            headings=(),
            links=(),
            forms=(),
            screenshot_path=None,
            api_calls=(
                ApiEndpoint("GET", "/api/orders", 200, "application/json", ("id",)),
                ApiEndpoint("POST", "/api/orders", 201, "application/json", ()),
            ),
        )
    ]
    return save_snapshot(pages, tmp_path / "crawl")


@pytest.fixture()
def env(tmp_path: Path) -> dict[str, Path]:
    app = tmp_path / "input-app"
    shutil.copytree(FIXTURE_DIR / "app", app)
    return {
        "app": app,
        "snapshot": _snapshot(tmp_path),
        "rea": _fake_rea(tmp_path, _emit_fixture(tmp_path)),
        "out": tmp_path / "out",
    }


def _request(env: dict[str, Path], **override: Any) -> ReverseAnalysisRequest:
    values = {
        "js_input": str(env["app"]),
        "runtime_snapshot": str(env["snapshot"]),
        "rea_command": str(env["rea"]),
        "output_dir": str(env["out"]),
    }
    values.update({k: str(v) for k, v in override.items()})
    return ReverseAnalysisRequest(**values)


def _cli_argv(env: dict[str, Path], out: Path | None = None) -> list[str]:
    return [
        "--reverse-analysis",
        "--js-input", str(env["app"]),
        "--runtime-snapshot", str(env["snapshot"]),
        "--rea-command", str(env["rea"]),
        "--output", str(out or env["out"]),
    ]  # fmt: skip


def _parse(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> Any:
    monkeypatch.setattr(sys, "argv", ["main.py", *argv])
    return main.parse_args()


# ---------------------------------------------------------------- 正常系（実 CLI）


def test_明示CLIで独立JSONを保存し要約と出力先を表示する(env: dict[str, Path], tmp_path: Path) -> None:
    before_app, before_snap = _tree_digest(env["app"]), env["snapshot"].read_bytes()
    proc = subprocess.run(
        [sys.executable, str(ROOT / "src" / "main.py"), *_cli_argv(env)],
        cwd=tmp_path, capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )  # fmt: skip
    assert proc.returncode == 0, proc.stderr
    out_file = env["out"] / "reverse_analysis.json"
    assert sorted(p.name for p in env["out"].iterdir()) == ["reverse_analysis.json"]
    assert f"出力先: {out_file}" in proc.stdout
    for label in ("実測", "静的構文の事実", "対応推論", "未確認", "coverage 静的", "coverage 実測"):
        assert label in proc.stdout
    assert LIMIT_PROVIDER_NO_HTTP_METHOD in proc.stdout and "HTTP method を返さない" in proc.stdout

    doc = load_document(out_file)
    assert tuple(doc) == TOP_LEVEL_KEYS and doc["status"] == "complete"
    assert doc["producer"]["provider_version"] == "6.7.0"
    assert doc["inputs"]["static_root_label"] == "input-app"
    assert doc["inputs"]["runtime_snapshot_sha256"] == hashlib.sha256(before_snap).hexdigest()
    # 入力・snapshot を書き換えない
    assert _tree_digest(env["app"]) == before_app and env["snapshot"].read_bytes() == before_snap


def test_最終JSONは実測と静的事実と推論を混ぜず絶対rootや生出力を持たない(env: dict[str, Path], tmp_path: Path) -> None:
    outcome = run_reverse_analysis(_request(env))
    assert outcome.exit_code == 0 and outcome.output_path is not None
    text = outcome.output_path.read_text(encoding="utf-8")
    doc = json.loads(text)
    assert str(tmp_path) not in text and "/fixture/app" not in text
    assert "pid" not in text.lower() and "stderr" not in text
    assert all(isinstance(c["sha256"], str) and c["sha256"] for c in doc["artifacts"])

    snapshot_doc = json.loads(env["snapshot"].read_text(encoding="utf-8"))
    for obs in doc["runtime_observations"]:
        assert obs["origin"] is None and obs["query_scope"] == "not_retained"
        assert obs["epistemic_state"] == "observed"
        assert resolve_json_pointer(snapshot_doc, obs["json_pointer"])["path"] == obs["path"]

    api = [c for c in doc["static_candidates"] if c["kind"] == "api"]
    assert api and all(c["method"] is None for c in api)  # GET と推定しない
    assert not [c for c in doc["static_candidates"] if c["kind"] == "route"]  # route 捏造禁止
    assert doc["summary"]["matched_relations"] == 0
    assert all(r["classification"] != "matched" for r in doc["relations"])
    assert all(r["epistemic_state"] != "observed" for r in doc["relations"])
    api_ids = {c["id"] for c in api}
    for rel in doc["relations"]:
        if set(rel["static_ids"]) & api_ids and rel["runtime_ids"]:
            pytest.fail("method 欠損の候補が実測へ対応付けられた")
    assert doc["summary"]["observed_api_records"] == len(doc["runtime_observations"]) == 2

    static_limits = doc["coverage"]["static"]["limitations"]
    assert LIMIT_PROVIDER_NO_HTTP_METHOD in static_limits and LIMIT_PROVIDER_NO_ROUTE in static_limits
    unsupported = [d for d in doc["diagnostics"] if d["code"] == "static_node_unsupported"]
    assert unsupported, "未対応 node を件数だけでなく位置付きで残す"
    for diag in unsupported:
        assert "kind=" in diag["message"] and "node_id=jag_node_" in diag["message"]
        assert "provider_pointer=/normalized_result/graph/nodes/" in diag["message"]


def test_同じ入力とprovider応答から同じバイト列のJSONになる(env: dict[str, Path], tmp_path: Path) -> None:
    first = run_reverse_analysis(_request(env))
    second = run_reverse_analysis(_request(env, output_dir=tmp_path / "out2"))
    assert first.output_path and second.output_path
    assert first.output_path.read_bytes() == second.output_path.read_bytes()
    again = run_reverse_analysis(_request(env))  # 同じ専用 dir への再実行は置き換え
    assert again.output_path and again.output_path.read_bytes() == first.output_path.read_bytes()


# ---------------------------------------------------------------- 失敗系（保存される）


def test_provider不在でも実測は保存しstaticはunavailableで非成功(env: dict[str, Path]) -> None:
    outcome = run_reverse_analysis(_request(env, rea_command="/nonexistent/ws2d/rea"))
    assert outcome.status == "unavailable" and outcome.exit_code == 2
    assert outcome.output_path is not None
    doc = load_document(outcome.output_path)
    assert doc["static_candidates"] == [] and doc["coverage"]["static"]["status"] == "unavailable"
    assert len(doc["runtime_observations"]) == 2 and doc["coverage"]["runtime"]["status"] == "complete"
    codes = [d["code"] for d in doc["diagnostics"]]
    assert "missing_provider" in codes
    assert all(d["next_action"] for d in doc["diagnostics"])


def test_不正なprovider出力はfailedで保存し次の行動を示す(env: dict[str, Path], tmp_path: Path) -> None:
    (tmp_path / "bad").mkdir()
    bad = _fake_rea(tmp_path / "bad", "print('{not json')\n")
    outcome = run_reverse_analysis(_request(env, rea_command=bad))
    assert outcome.status == "failed" and outcome.exit_code == 2 and outcome.output_path
    doc = load_document(outcome.output_path)
    assert doc["coverage"]["static"]["status"] == "failed" and doc["static_candidates"] == []
    assert "invalid_provider_output" in [d["code"] for d in doc["diagnostics"]]


def test_timeoutはfailedで非成功exit(env: dict[str, Path], tmp_path: Path) -> None:
    (tmp_path / "slow").mkdir()
    slow = _fake_rea(tmp_path / "slow", "time.sleep(30)\n")
    runner = functools.partial(run_static_analysis, analysis_timeout=0.5, grace=0.5)
    outcome = run_reverse_analysis(_request(env, rea_command=slow), static_runner=runner)
    assert outcome.status == "failed" and outcome.exit_code == 2 and outcome.output_path
    assert "provider_timeout" in [d["code"] for d in load_document(outcome.output_path)["diagnostics"]]


def test_取り消しはcancelledで130(env: dict[str, Path]) -> None:
    event = threading.Event()
    event.set()
    outcome = run_reverse_analysis(_request(env), cancel_event=event)
    assert outcome.status == "cancelled" and outcome.exit_code == 130
    assert outcome.output_path is not None
    assert load_document(outcome.output_path)["coverage"]["static"]["status"] == "cancelled"


def test_KeyboardInterruptもcancelledとして保存する(env: dict[str, Path]) -> None:
    def interrupted(*_args: Any, **_kwargs: Any) -> Any:
        raise KeyboardInterrupt

    outcome = run_reverse_analysis(_request(env), static_runner=interrupted)
    assert outcome.status == "cancelled" and outcome.exit_code == 130
    assert outcome.output_path is not None


def test_snapshot不在はfailedで静的結果と併せて保存する(env: dict[str, Path], tmp_path: Path) -> None:
    outcome = run_reverse_analysis(_request(env, runtime_snapshot=tmp_path / "crawl" / "none.json"))
    assert outcome.status == "failed" and outcome.exit_code == 2 and outcome.output_path
    doc = load_document(outcome.output_path)
    assert doc["coverage"]["runtime"]["status"] == "failed" and doc["runtime_observations"] == []
    assert doc["static_candidates"]  # 静的側は残す


# ---------------------------------------------------------------- 保存先の拒否・保存不能


@pytest.mark.parametrize("where", ["in_input", "in_snapshot_dir", "symlink", "shared_dir"])
def test_入力内_snapshot親内_symlink_共用dirへの出力は拒否する(env: dict[str, Path], tmp_path: Path, where: str) -> None:
    if where == "in_input":
        out = env["app"] / "ra-out"
    elif where == "in_snapshot_dir":
        out = env["snapshot"].parent / "ra-out"
    elif where == "symlink":
        (tmp_path / "real").mkdir()
        out = tmp_path / "link"
        out.symlink_to(tmp_path / "real")
    else:
        out = tmp_path / "shared"
        out.mkdir()
        (out / "report.json").write_text("{}", encoding="utf-8")
    before = _tree_digest(tmp_path)
    outcome = run_reverse_analysis(_request(env, output_dir=out))
    assert outcome.output_path is None and outcome.exit_code == 2
    assert outcome.diagnostics[0].code == "output_location_rejected"
    assert _tree_digest(tmp_path) == before


def test_親成分のsymlinkを通る出力は拒否する(env: dict[str, Path], tmp_path: Path) -> None:
    (tmp_path / "real-parent").mkdir()
    (tmp_path / "link-parent").symlink_to(tmp_path / "real-parent")
    out = tmp_path / "link-parent" / "nested" / "ra-out"
    before = _tree_digest(tmp_path)
    outcome = run_reverse_analysis(_request(env, output_dir=out))
    assert outcome.output_path is None and outcome.exit_code == 2
    assert outcome.diagnostics[0].code == "output_location_rejected"
    assert _tree_digest(tmp_path) == before
    assert not (tmp_path / "real-parent" / "nested").exists()


@pytest.mark.parametrize("fault", ["unreadable_dir", "iterdir_error", "symlink_loop"])
def test_出力先の検査で例外が出てもtracebackを出さず次の行動を示す(
    env: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], fault: str,
) -> None:  # fmt: skip
    out = tmp_path / "ra-out"
    if fault == "unreadable_dir" and hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root は権限 000 のディレクトリも読めるため、読めない出力先を作れない")
    if fault == "unreadable_dir":
        locked = tmp_path / "locked"
        locked.mkdir()
        out = locked / "ra-out"
        locked.chmod(0)
    elif fault == "iterdir_error":
        out.mkdir()

        def broken_iterdir(_self: Path) -> Any:
            raise PermissionError(f"denied: {out}")

        monkeypatch.setattr(Path, "iterdir", broken_iterdir)
    else:
        out = tmp_path / "loop-a" / "ra-out"
        (tmp_path / "loop-a").symlink_to(tmp_path / "loop-b")
        (tmp_path / "loop-b").symlink_to(tmp_path / "loop-a")
    try:
        args = _parse(monkeypatch, _cli_argv(env, out))
        code = main._run_reverse_analysis(args)
    finally:
        if fault == "unreadable_dir":
            (tmp_path / "locked").chmod(0o755)
    captured = capsys.readouterr()
    assert code == 2
    assert "Traceback" not in captured.err and "次の行動:" in captured.err
    assert str(tmp_path) not in captured.err and "出力先:" not in captured.out
    assert not (out / OUTPUT_FILENAME).exists()


def test_run_reverse_analysisの想定外OSErrorもCLIで要約する(
    env: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import reverse_analysis.service as service

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError(f"unexpected at {env['out']}")

    monkeypatch.setattr(service, "run_reverse_analysis", boom)
    code = main._run_reverse_analysis(_parse(monkeypatch, _cli_argv(env)))
    captured = capsys.readouterr()
    assert code == 2 and "成果物はありません" in captured.err and "次の行動:" in captured.err
    assert str(env["out"]) not in captured.err and captured.out == ""


def test_保存不能は成果物ありと称さず次の行動をstderrに出す(
    env: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_replace(*_args: Any) -> None:
        raise OSError(f"disk full at {env['out']}")

    monkeypatch.setattr(reporter.os, "replace", fail_replace)
    args = _parse(monkeypatch, _cli_argv(env))
    code = main._run_reverse_analysis(args)
    captured = capsys.readouterr()
    assert code == 2
    assert list(env["out"].iterdir()) == []  # 一時ファイルも残さない
    assert "成果物はありません" in captured.err and "次の行動:" in captured.err
    assert "disk full" not in captured.err and "出力先:" not in captured.out


# ---------------------------------------------------------------- schema


def test_未知のschema_versionと欠けたキーは拒否する(env: dict[str, Path], tmp_path: Path) -> None:
    outcome = run_reverse_analysis(_request(env))
    assert outcome.document is not None
    validate_document(outcome.document)
    for mutate in (
        lambda d: d.update(schema_version=2),
        lambda d: d.update(schema_version="1"),
        lambda d: d.pop("summary"),
        lambda d: d.update(status="ok"),
    ):
        doc = json.loads(json.dumps(outcome.document))
        mutate(doc)
        with pytest.raises(ReportSchemaError):
            validate_document(doc)
    path = tmp_path / "v2.json"
    path.write_text(json.dumps({**outcome.document, "schema_version": 2}), encoding="utf-8")
    with pytest.raises(ReportSchemaError):
        load_document(path)


# ---------------------------------------------------------------- CLI 引数・flag OFF


@pytest.mark.parametrize(
    "argv",
    [
        ["--reverse-analysis", "--output", "x"],
        ["--js-input", "a"],
        ["--reverse-analysis", "--js-input", "a", "--runtime-snapshot", "b", "--rea-command", "/c"],
    ],
)
def test_入力不足_flag無しの専用引数_既定出力先は拒否する(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        _parse(monkeypatch, argv)
    assert exc.value.code == 2


@pytest.mark.parametrize("extra", [["--url", "https://e.example"], ["--urls", "https://e.example"], ["--compare"], ["--ci"]])
def test_既存クロールモードとの併用は拒否する(env: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], extra: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        _parse(monkeypatch, [*_cli_argv(env), *extra])
    assert exc.value.code == 2
    assert "併用できません" in capsys.readouterr().err
    assert not env["out"].exists()


def test_flag_OFFではreverse_analysisをimportせずREAも呼ばない() -> None:
    code = (
        "import sys; sys.argv=['main.py','--url','https://e.example'];"
        "import main; a=main.parse_args();"
        "print(a.reverse_analysis, a.js_input, sorted(m for m in sys.modules if m.startswith('reverse_analysis')))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )  # fmt: skip
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "False None []"


def test_flag_OFFの既存分岐は従来どおりでreverse_analysisへ入らない(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(main, "_discover", lambda *_a: calls.append("discover"))
    monkeypatch.setattr(main, "_run_reverse_analysis", lambda *_a: pytest.fail("flag OFF で呼ばれた"))
    args = _parse(monkeypatch, ["--url", "https://e.example", "--discover"])
    main.run(args)
    assert calls == ["discover"]


# ---------------------------------------------------------------- Task 4: 最終 CLI 受入（fake provider）
# 測定記録は tests/fixtures/reverse_analysis/value_measurement.json。実 REA は実行しない（AC10 は未検証）。


def _value_env(tmp_path: Path, payload: str | None = None) -> dict[str, Path]:
    """固定 snapshot（バイト固定）と自己所有 app を tmp に複製し、fixture を返す偽 rea を置く。"""
    app = tmp_path / "input-app"
    shutil.copytree(FIXTURE_DIR / "app", app)
    (tmp_path / "crawl").mkdir()
    snapshot = tmp_path / "crawl" / RUNTIME_SNAPSHOT.name
    shutil.copyfile(RUNTIME_SNAPSHOT, snapshot)
    body = payload if payload is not None else _emit_fixture(tmp_path)
    return {"app": app, "snapshot": snapshot, "rea": _fake_rea(tmp_path, body), "out": tmp_path / "out"}


def _run_cli(env: dict[str, Path]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "src" / "main.py"), *_cli_argv(env)],
        cwd=env["app"].parent, capture_output=True, text=True, timeout=120, env=CLI_ENV,
    )  # fmt: skip


def _before_map_bytes(snapshot: Path) -> bytes:
    """Before: 既存の build_screen_api_map の成果物（測定記録と同じ直列化）。"""
    screen_map = build_screen_api_map(load_snapshot(snapshot))
    return json.dumps(screen_map, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hits(candidate: dict[str, Any], truth: dict[str, Any]) -> bool:
    loc = candidate["location"]
    return (
        candidate["kind"] == truth["kind"]
        and candidate["artifact_path"] == truth["artifact_path"]
        and (loc["start_line"], loc["start_column"]) == (truth["start_line"], truth["start_column"])
    )


def test_受入_固定snapshotのBeforeAfterを測定記録と照合し正解位置で数える(tmp_path: Path) -> None:
    record = json.loads(VALUE_RECORD.read_text(encoding="utf-8"))
    env = _value_env(tmp_path)
    snap_bytes, app_digest = env["snapshot"].read_bytes(), _tree_digest(env["app"])
    assert _sha(snap_bytes) == record["inputs"]["runtime_snapshot_sha256"]
    before = _before_map_bytes(env["snapshot"])
    assert _sha(before) == record["before"]["screen_api_map_sha256"]
    assert len(before) == record["cost_fake_provider"]["before_output_bytes"]

    proc = _run_cli(env)
    assert proc.returncode == 0, proc.stderr
    raw = (env["out"] / OUTPUT_FILENAME).read_bytes()
    assert (_sha(raw), len(raw)) == (record["after"]["output_sha256"], record["after"]["output_bytes"]), (
        "出力が測定記録と違う。src を変えたなら value_measurement.json を測り直す"
    )
    doc = load_document(env["out"] / OUTPUT_FILENAME)
    assert doc["summary"] == record["after"]["summary"]
    # 入力と Before 成果物は不変
    assert env["snapshot"].read_bytes() == snap_bytes and _tree_digest(env["app"]) == app_digest
    assert _before_map_bytes(env["snapshot"]) == before

    expected_kinds = record["after"]["candidates_by_kind"]
    kinds = Counter(c["kind"] for c in doc["static_candidates"])
    assert {k: kinds.get(k, 0) for k in expected_kinds} == expected_kinds

    js_lines = (env["app"] / "dist" / "app.js").read_text(encoding="utf-8").splitlines()
    matched: set[str] = set()
    for truth in record["ground_truth"]:
        (cand,) = [c for c in doc["static_candidates"] if _hits(c, truth)]
        matched.add(cand["id"])
        assert (cand["origin"], cand["path"], cand["resolution"]) == (
            truth["origin"], truth["path"], truth["resolution"],
        ), truth["id"]  # fmt: skip
        assert cand["epistemic_state"] == "observed" and cand["method"] is None
        if truth["text"] is not None:  # 位置は 1 始まり行・0 始まり UTF-16 列・終端を含まない
            loc = cand["location"]
            assert loc["unit"] == "line_column_utf16"
            assert js_lines[loc["start_line"] - 1][loc["start_column"] : loc["end_column"]] == truth["text"]
            assert (loc["end_line"], loc["end_column"]) == (truth["start_line"], truth["end_column"])
    false_extractions = [c for c in doc["static_candidates"] if c["id"] not in matched]
    assert len(false_extractions) == record["after"]["false_extractions"] == 0
    signatures = {(c["kind"], c["artifact_path"], json.dumps(c["location"], sort_keys=True)) for c in doc["static_candidates"]}
    assert len(signatures) == len(doc["static_candidates"])  # 重複水増しなし
    assert record["after"]["duplicate_candidates"] == 0

    # 有用新規: Before の実測 path と重なる候補は数えない
    observed_paths = {obs["path"] for obs in doc["runtime_observations"]}
    in_before = [t["id"] for t in record["ground_truth"] if t["path"] in observed_paths]
    assert in_before == record["after"]["not_counted_as_new"]
    assert all(t["in_before"] == (t["id"] in in_before) for t in record["ground_truth"])
    useful = [t for t in record["ground_truth"] if t["useful_new"] and not t["in_before"]]
    assert len(useful) == record["after"]["useful_new_evidence"] >= 1
    # 静的候補を実測仕様へ昇格させない（method 欠損のため現 slice では inferred も出ない）
    assert doc["summary"]["matched_relations"] == doc["summary"]["inferred_relations"] == 0
    assert all(r["epistemic_state"] != "observed" for r in doc["relations"])
    assert record["provider"]["kind"] == "fake"


def test_受入_実プロセスへのSIGINTで子も止まりcancelledを保存して130(tmp_path: Path) -> None:
    info = tmp_path / "provider-started.json"
    body = (
        "import json, os, subprocess\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"tmp = {str(info)!r} + '.part'\n"
        "with open(tmp, 'w') as fh: json.dump({'pid': os.getpid(), 'child': child.pid, 'cwd': os.getcwd()}, fh)\n"
        f"os.replace(tmp, {str(info)!r})\n"
        "time.sleep(60)\n"
    )
    env = _value_env(tmp_path, payload=body)
    proc, stdout, stderr, started, survivors = _sigint_cli(env, info)
    assert survivors == []  # 製品が leader と子を止めた（テスト側の kill より前に判定）
    assert proc.returncode == 130, stderr
    out_file = env["out"] / OUTPUT_FILENAME
    assert "reverse analysis: 取り消し" in stdout and f"出力先: {out_file}" in stdout
    assert "Traceback" not in stderr
    doc = load_document(out_file)
    assert doc["status"] == "cancelled" and doc["coverage"]["static"]["status"] == "cancelled"
    assert doc["static_candidates"] == [] and "provider_cancelled" in [d["code"] for d in doc["diagnostics"]]
    assert len(doc["runtime_observations"]) == 3  # 取り消し前に読んだ実測は残す
    assert sorted(p.name for p in env["out"].iterdir()) == [OUTPUT_FILENAME]  # 一時ファイルなし
    assert not Path(started["cwd"]).exists()  # 所有する作業 dir を片付けた


def _sigint_cli(env: dict[str, Path], info: Path) -> tuple[subprocess.Popen[str], str, str, dict[str, Any], list[int]]:
    """CLI を実プロセスで起動し、provider の開始合図後に SIGINT を送る。

    所有 pid の生存判定は finally の後始末（失敗時専用の kill）より前に行い、製品の停止能力を隠さない。
    """
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "src" / "main.py"), *_cli_argv(env)],
        cwd=env["app"].parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=CLI_ENV,
        start_new_session=True,
    )  # fmt: skip
    started: dict[str, Any] = {}
    survivors: list[int] = []
    try:
        deadline = time.monotonic() + 30
        while not info.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert info.exists(), "fake provider が開始合図を出さなかった"
        started = json.loads(info.read_text(encoding="utf-8"))
        proc.send_signal(signal.SIGINT)
        stdout, stderr = proc.communicate(timeout=30)
        owned = [started["pid"], started["child"]]
        deadline = time.monotonic() + 5
        while any(pid_alive(p) for p in owned) and time.monotonic() < deadline:
            time.sleep(0.05)
        survivors = [p for p in owned if pid_alive(p)]
    finally:  # 失敗時の後始末専用。成功 path の判定は上で済んでいる
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
        for pid in (started.get("pid"), started.get("child")):  # 自己所有の pid だけ
            if pid and pid_alive(pid):
                os.kill(pid, signal.SIGKILL)
    return proc, stdout, stderr, started, survivors


def test_受入_版確認中のSIGINTも子まで止めcancelledを保存して130(tmp_path: Path) -> None:
    info = tmp_path / "provider-started.json"
    env = _value_env(tmp_path)
    env["rea"].write_text(
        f"#!{sys.executable}\n"
        "import json, os, signal, subprocess, sys, time\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"    tmp = {str(info)!r} + '.part'\n"
        "    with open(tmp, 'w') as fh: json.dump({'pid': os.getpid(), 'child': child.pid}, fh)\n"
        f"    os.replace(tmp, {str(info)!r})\n"
        "    time.sleep(60)\n"
        f"open({str(tmp_path / 'analysis-started')!r}, 'w').write('x')\n",
        encoding="utf-8",
    )
    proc, stdout, stderr, _started, survivors = _sigint_cli(env, info)
    assert survivors == []  # 版確認の leader と子を製品が止めた
    assert proc.returncode == 130, stderr
    assert "reverse analysis: 取り消し" in stdout and "Traceback" not in stderr
    doc = load_document(env["out"] / OUTPUT_FILENAME)
    assert doc["status"] == "cancelled" and doc["coverage"]["static"]["status"] == "cancelled"
    codes = [d["code"] for d in doc["diagnostics"]]
    assert "provider_cancelled" in codes and "provider_version_unavailable" not in codes
    assert not (tmp_path / "analysis-started").exists()  # 取り消し後に解析を起動しない


def _unresolved_map_payload(tmp_path: Path) -> str:
    """REA が map から元ソースを解決できなかったと返す Evidence（commitment は計算し直す）。"""
    evidence = load_fixture()
    for node in evidence["normalized_result"]["graph"]["nodes"]:
        for obs in node["observations"] if node["kind"] == "source-module" else ():
            obs["source_map_reference"]["resolution"] = {"kind": "unresolved", "reason": "source-map-invalid"}
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps(recommit(evidence)), encoding="utf-8")
    return f"sys.stdout.write(open({str(payload)!r}).read())\n"


@pytest.mark.parametrize(
    ("case", "exit_code", "status_text", "codes", "absent_code"),
    [
        ("old", 2, "一部のみ", {"source_map_stale", "static_artifact_digest_mismatch"}, "static_artifact_not_verified"),
        ("broken", 2, "一部のみ", {"source_map_stale", "static_artifact_digest_mismatch"}, "static_artifact_not_verified"),
        ("missing", 2, "一部のみ", {"source_map_stale", "static_artifact_not_verified"}, "static_artifact_digest_mismatch"),
        ("unresolved", 0, "完了", {"source_map_unresolved"}, "source_map_stale"),
    ],
)
def test_受入_古い_壊れた_欠測_未解決のmapを利用者出力まで区別する(
    tmp_path: Path, case: str, exit_code: int, status_text: str, codes: set[str], absent_code: str
) -> None:  # fmt: skip
    payload = _unresolved_map_payload(tmp_path) if case == "unresolved" else None
    env = _value_env(tmp_path, payload=payload)
    map_file = env["app"] / "dist" / "app.js.map"
    if case == "old":
        map_file.write_text('{"version":3,"file":"app.js","sources":["../src/old.ts"],"names":[],"mappings":"AAAA"}')
    elif case == "broken":  # adapter は map を解釈せず digest だけを見るため、古い map と同じ扱い
        map_file.write_text("{not json")
    elif case == "missing":
        map_file.unlink()

    proc = _run_cli(env)
    assert proc.returncode == exit_code, proc.stderr
    assert f"reverse analysis: {status_text}" in proc.stdout
    doc = load_document(env["out"] / OUTPUT_FILENAME)
    found = {d["code"] for d in doc["diagnostics"]}
    assert codes <= found and absent_code not in found
    for diag in doc["diagnostics"]:
        if diag["code"] in codes:
            assert diag["message"] in proc.stdout and diag["next_action"] in proc.stdout
    limits = doc["coverage"]["static"]["limitations"]
    for code, limit in (
        ("static_artifact_digest_mismatch", LIMIT_DIGEST_MISMATCH),
        ("static_artifact_not_verified", LIMIT_FILE_NOT_VERIFIED),
    ):  # coverage と CLI 表示の欠測理由は、候補に実在する理由だけ（虚偽理由を出さない）
        shown = code in found
        assert (limit in limits) == shown and (f"制限・欠測理由: {limit}" in proc.stdout) == shown
    (source,) = [c for c in doc["static_candidates"] if c["kind"] == "source"]
    assert (source["epistemic_state"], source["resolution"]) == ("unknown", "unavailable")
    assert source["path"] != "../src/app.ts"  # 原ソースを捏造しない
    api = [c for c in doc["static_candidates"] if c["kind"] == "api"]
    assert len(api) == 3  # map の不備で JS 側の候補を落とさない


def test_受入_flag_OFFも明示実行も既存のreportとsnapshotのバイトを変えない(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    crawl = tmp_path / "existing-crawl"
    (crawl / "snapshots").mkdir(parents=True)
    (crawl / "report.json").write_text('{"pages": []}\n', encoding="utf-8")
    shutil.copyfile(RUNTIME_SNAPSHOT, crawl / "snapshots" / RUNTIME_SNAPSHOT.name)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "rea-was-called"
    rea_on_path = bin_dir / "rea"
    rea_on_path.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    rea_on_path.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    before = _tree_digest(crawl)

    calls: list[str] = []
    monkeypatch.setattr(main, "_discover", lambda *_a: calls.append("discover"))
    main.run(_parse(monkeypatch, ["--url", "https://e.example", "--discover", "--output", str(crawl)]))
    assert calls == ["discover"] and not marker.exists()
    assert _tree_digest(crawl) == before

    env = _value_env(tmp_path / "ra")
    env["snapshot"] = crawl / "snapshots" / RUNTIME_SNAPSHOT.name
    proc = _run_cli(env)
    assert proc.returncode == 0, proc.stderr
    assert _tree_digest(crawl) == before  # 既存成果物の追加・変更なし
    assert not marker.exists()  # PATH 上の rea を探さず、指定した実行ファイルだけを使う
