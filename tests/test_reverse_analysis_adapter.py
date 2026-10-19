"""REA adapter（rea-agents 6.7.0 固定）の契約。

守るべきは「検証できない出力を成功にしないこと」と「自分が起動したプロセスを必ず片付けること」。
provider は導入・実行しない。偽の実行ファイルが固定版の Evidence fixture を返す。
fixture の出所は tests/fixtures/reverse_analysis/PROVENANCE.md。
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from reverse_analysis.rea_adapter import (
    ANALYZE_SUBCOMMAND,
    InvalidProviderOutput,
    canonical_digest,
    canonical_json,
    evidence_semantic_projection,
    parse_provider_json,
    probe_version,
    run_static_analysis,
    semantic_graph_id,
    validate_evidence,
    verify_file,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "reverse_analysis"
EVIDENCE_FIXTURE = FIXTURE_DIR / "rea_6_7_0_application_evidence.json"


# ---------------------------------------------------------------- fixture 補助


def recommit(evidence: dict[str, Any], placeholder_roots: bool = False) -> dict[str, Any]:
    """変更した Evidence の node/observation/edge/graph/evidence の commitment を計算し直す。

    placeholder_roots=True のとき、``@<index>`` を並べ替え前の nodes[index] の ID に置き換える。
    """
    ev = copy.deepcopy(evidence)
    result = ev["normalized_result"]
    graph = result["graph"]
    remap: dict[str, str] = {}
    for index, node in enumerate(graph["nodes"]):
        new_id = f"jag_node_{canonical_digest({'kind': node['kind'], 'identity': node['identity']})}"
        remap[node["node_id"]] = new_id
        if placeholder_roots:
            remap[f"@{index}"] = new_id
        node["node_id"] = new_id
        for obs in node["observations"]:
            semantic = {"node_id": new_id, **{k: v for k, v in obs.items() if k != "observation_id"}}
            obs["observation_id"] = f"jag_observation_{canonical_digest(semantic)}"
        node["observations"].sort(key=lambda o: o["observation_id"])
    graph["nodes"].sort(key=lambda n: n["node_id"])
    graph["root_node_ids"] = sorted(remap.get(r, r) for r in graph["root_node_ids"])
    for edge in graph["edges"]:
        edge["source_node_id"] = remap.get(edge["source_node_id"], edge["source_node_id"])
        edge["target_node_id"] = remap.get(edge["target_node_id"], edge["target_node_id"])
        edge["edge_id"] = f"jag_edge_{canonical_digest({k: v for k, v in edge.items() if k != 'edge_id'})}"
    graph["edges"].sort(key=lambda e: e["edge_id"])
    graph["graph_id"] = f"jag_{canonical_digest({k: v for k, v in graph.items() if k != 'graph_id'})}"
    semantic = result["semantic_graph"]
    semantic["application_graph_id"] = graph["graph_id"]
    semantic["root_artifact_sha256"] = result["root_artifact_sha256"]
    for snode in semantic["nodes"]:
        snode["application_node_ids"] = sorted({remap.get(i, i) for i in snode["application_node_ids"]})
    semantic["graph_id"] = semantic_graph_id(semantic)
    if ev["subject"] is not None:
        ev["subject"]["digest"]["sha256"] = result["root_artifact_sha256"]
    ev["evidence_id"] = f"ev_{canonical_digest(evidence_semantic_projection(ev))}"
    return ev


def load_fixture() -> dict[str, Any]:
    return json.loads(EVIDENCE_FIXTURE.read_text(encoding="utf-8"))


def copy_app(tmp_path: Path) -> Path:
    target = tmp_path / "input-app"
    shutil.copytree(FIXTURE_DIR / "app", target)
    return target


def make_fake_rea(tmp_path: Path, body: str, version: str = "6.7.0") -> Path:
    """偽の rea。--version は version を返し、解析時は body を実行する。"""
    script = tmp_path / "fake-rea"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, os, signal, subprocess, sys, time\n"
        f"LOG = {str(tmp_path / 'fake-log.json')!r}\n"
        "if sys.argv[1:] == ['--version']:\n"
        f"    print({version!r}); sys.exit(0)\n"
        "with open(LOG, 'w') as fh: json.dump({'argv': sys.argv[1:], 'cwd': os.getcwd(), 'tmpdir': os.environ.get('TMPDIR')}, fh)\n"
        + body,
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def emit_evidence(tmp_path: Path, evidence: dict[str, Any]) -> str:
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps(evidence), encoding="utf-8")
    return f"sys.stdout.write(open({str(payload)!r}).read())\n"


def fake_log(tmp_path: Path) -> dict[str, Any] | None:
    path = tmp_path / "fake-log.json"
    return json.loads(path.read_text()) if path.exists() else None


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


# ---------------------------------------------------------------- 正規 JSON


def test_canonical_json_sorts_keys_by_utf16_code_units_like_javascript() -> None:
    # Python の code point 順では U+E000 が先、JS の UTF-16 code unit 順では絵文字（D83D）が先
    assert canonical_json({"\ue000": 1, "\U0001f600": 2, "a": 3}) == '{"a":3,"\U0001f600":2,"\ue000":1}'


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1e21, "1e+21"), (1e-7, "1e-7"), (1e-5, "0.00001"), (1.5, "1.5"), (100.0, "100"), (-0.0, "0"), (123456789012.5, "123456789012.5")],
)
def test_canonical_json_formats_numbers_like_ecmascript(value: float, expected: str) -> None:
    assert canonical_json(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # 6.7.0 src/domain/canonicalDigest.test.ts の固定入力のうち JSON で表せるもの。上流は
        # canonicalize（JSON.stringify と Object.keys().sort()）の出力と一致することを検査している。
        ({"\ue000": "BMP", "\U00010000": "supplementary"}, '{"\U00010000":"supplementary","\ue000":"BMP"}'),
        (
            {"€": "\ud800", "😀": "\udc00", "\r": '\n\t"\\', "number": -0.0, "exponent": 1e30},
            '{"\\r":"\\n\\t\\"\\\\","exponent":1e+30,"number":0,"€":"\\ud800","😀":"\\udc00"}',
        ),
        ([{"key": "value"}, {"key": "value"}], '[{"key":"value"},{"key":"value"}]'),
    ],
)
def test_canonical_json_matches_upstream_canonical_digest_vectors(value: Any, expected: str) -> None:
    assert canonical_json(value) == expected


def test_parse_provider_json_rejects_duplicate_keys_and_nan() -> None:
    with pytest.raises(InvalidProviderOutput):
        parse_provider_json(b'{"a":1,"a":2}')
    with pytest.raises(InvalidProviderOutput):
        parse_provider_json(b'{"a":NaN}')
    with pytest.raises(InvalidProviderOutput):
        parse_provider_json(b'{"a":1')  # 途中で切れた JSON


# ---------------------------------------------------------------- Evidence 検証


def test_fixture_is_a_self_consistent_6_7_0_evidence() -> None:
    result = validate_evidence(load_fixture())
    assert result["format"] == "directory"
    assert {n["kind"] for n in result["graph"]["nodes"]} >= {"endpoint", "source-map", "source-module"}


def test_tampered_value_without_recommit_is_rejected_at_observation() -> None:
    evidence = load_fixture()
    node = next(n for n in evidence["normalized_result"]["graph"]["nodes"] if n["kind"] == "endpoint")
    node["observations"][0]["properties"]["value"] = "/api/forged"
    with pytest.raises(InvalidProviderOutput) as caught:
        validate_evidence(evidence)
    assert caught.value.pointer.endswith("/observation_id")


def test_stale_evidence_id_is_rejected_even_when_graph_is_consistent() -> None:
    evidence = recommit(load_fixture())
    evidence["limitations"] = ["changed after commitment"]
    with pytest.raises(InvalidProviderOutput) as caught:
        validate_evidence(evidence)
    assert caught.value.pointer == "/evidence_id"


def _semantic(evidence: dict[str, Any]) -> dict[str, Any]:
    return evidence["normalized_result"]["semantic_graph"]


@pytest.mark.parametrize(
    ("mutate", "pointer"),
    [
        (lambda e: e["provider"].update(version="2"), "/provider"),
        (lambda e: e.update(extra_key=1), ""),
        (lambda e: e["normalized_result"].update(format="asar"), "/normalized_result/format"),
        (lambda e: e["normalized_result"]["graph"]["edges"][0].update(relation="teleports"), "/relation"),
        (lambda e: _semantic(e)["nodes"][0]["application_node_ids"].append("jag_node_" + "0" * 64), "/semantic_graph/nodes/0/application_node_ids"),
        (lambda e: _semantic(e)["nodes"][0]["identity"].update(role_key="function"), "/semantic_graph/nodes/0/node_id"),
        (lambda e: _semantic(e)["evidence_contexts"][0].update(confidence="low"), "/semantic_graph/evidence_contexts/0/context_id"),
        (lambda e: _semantic(e)["coverage"]["families"].pop(), "/semantic_graph/coverage/families"),
        (lambda e: _semantic(e).pop("fingerprints"), "/normalized_result/semantic_graph"),
        (lambda e: _semantic(e)["nodes"][0]["evidence"].update(context_id="jsrg_evidence_" + "0" * 64), "/semantic_graph/nodes/0/evidence/context_id"),
    ],
)
def test_contract_violations_are_invalid_provider_output(mutate: Any, pointer: str) -> None:
    evidence = load_fixture()
    mutate(evidence)
    evidence = recommit(evidence)
    with pytest.raises(InvalidProviderOutput) as caught:
        validate_evidence(evidence)
    assert caught.value.pointer.endswith(pointer or "/")


def test_fixture_semantic_graph_has_the_full_upstream_shape() -> None:
    semantic = _semantic(load_fixture())
    assert set(semantic) == {
        "schema", "root_artifact_sha256", "application_graph_id", "root_node_ids", "evidence_contexts",
        "nodes", "relations", "fingerprints", "unknowns", "coverage", "limitations", "graph_id",
    }  # fmt: skip
    assert semantic["schema"] == "JavaScriptSemanticRelationGraph"
    assert len(semantic["coverage"]["families"]) == 12
    assert semantic["graph_id"] == semantic_graph_id(semantic)


def test_stale_semantic_graph_id_is_rejected() -> None:
    evidence = load_fixture()
    _semantic(evidence)["nodes"][0]["label"] = "changed"
    evidence["evidence_id"] = f"ev_{canonical_digest(evidence_semantic_projection(evidence))}"
    with pytest.raises(InvalidProviderOutput) as caught:
        validate_evidence(evidence)
    assert caught.value.pointer == "/normalized_result/semantic_graph/graph_id"


def test_observed_fact_without_location_breaks_evidence_rules() -> None:
    evidence = load_fixture()
    node = next(n for n in evidence["normalized_result"]["graph"]["nodes"] if n["kind"] == "endpoint")
    node["observations"][0]["evidence"]["location"] = {"available": False, "reason": "unknown", "detail": "lost"}
    with pytest.raises(InvalidProviderOutput):
        validate_evidence(recommit(evidence))


# ---------------------------------------------------------------- 実行境界（偽 provider）


def test_complete_run_uses_argv_only_and_cleans_owned_workdir(tmp_path: Path) -> None:
    root = copy_app(tmp_path)
    fake = make_fake_rea(tmp_path, emit_evidence(tmp_path, load_fixture()))
    result = run_static_analysis(str(fake), str(root))
    assert result.status == "complete", result.diagnostics
    assert result.provider_version == "6.7.0"
    assert result.evidence_id == load_fixture()["evidence_id"]
    assert {f.path: f.status for f in result.files} == {
        "dist/app.js": "verified", "dist/app.js.map": "verified", "src/app.ts": "verified"
    }
    log = fake_log(tmp_path)
    assert log is not None and log["argv"] == [ANALYZE_SUBCOMMAND, str(root.resolve()), "--json"]
    assert log["tmpdir"] == log["cwd"] or Path(log["tmpdir"]).resolve() == Path(log["cwd"]).resolve()
    assert not Path(log["cwd"]).exists()  # 所有一時ディレクトリは片付け済み


def test_provider_partial_coverage_is_partial_not_complete(tmp_path: Path) -> None:
    evidence = load_fixture()
    evidence["normalized_result"]["graph"]["coverage"] = {
        "status": "partial", "truncated": True, "omitted_count": 2,
        "limits": [{"name": "max_files", "value": 3, "unit": "items"}],
    }  # fmt: skip
    fake = make_fake_rea(tmp_path, emit_evidence(tmp_path, recommit(evidence)))
    result = run_static_analysis(str(fake), str(copy_app(tmp_path)))
    assert result.status == "partial"
    assert result.analysis is not None


@pytest.mark.parametrize("command", ["", "relative/rea", "/nonexistent/ws2d/rea"])
def test_missing_provider_is_unavailable(command: str, tmp_path: Path) -> None:
    result = run_static_analysis(command, str(copy_app(tmp_path)))
    assert result.status == "unavailable"
    assert result.diagnostics[0].code == "missing_provider"
    assert result.analysis is None


def test_other_provider_version_is_unsupported_without_running_analysis(tmp_path: Path) -> None:
    fake = make_fake_rea(tmp_path, "print('{}')\n", version="6.8.0")
    result = run_static_analysis(str(fake), str(copy_app(tmp_path)))
    assert result.status == "unavailable"
    assert result.diagnostics[0].code == "unsupported_provider_version"
    assert result.provider_version == "6.8.0"
    assert fake_log(tmp_path) is None  # 解析は起動していない（自動 fallback なし）


@pytest.mark.parametrize("version", ["rea-agents 6.7.0", "v6.7.0", "6.7.0\nextra", " 6.7.0"])
def test_version_output_must_be_the_bare_incur_line(tmp_path: Path, version: str) -> None:
    fake = make_fake_rea(tmp_path, "print('{}')\n", version=version)
    result = run_static_analysis(str(fake), str(copy_app(tmp_path)))
    assert result.status == "unavailable"
    assert result.diagnostics[0].code == "unsupported_provider_version"
    assert fake_log(tmp_path) is None


def test_non_directory_and_symlink_inputs_are_rejected(tmp_path: Path) -> None:
    fake = make_fake_rea(tmp_path, "print('{}')\n")
    root = copy_app(tmp_path)
    link = tmp_path / "linked-app"
    link.symlink_to(root, target_is_directory=True)
    for given in (str(link), str(root / "dist" / "app.js"), str(root / ".." / "input-app")):
        result = run_static_analysis(str(fake), given)
        assert result.status == "failed"
        assert result.diagnostics[0].code == "invalid_static_input"
    assert fake_log(tmp_path) is None


def _internal_file_symlink(root: Path, tmp_path: Path) -> Path:
    (tmp_path / "outside.js").write_text("secret")
    (root / "dist" / "leak.js").symlink_to(tmp_path / "outside.js")
    return root


def _internal_dir_symlink(root: Path, tmp_path: Path) -> Path:
    (tmp_path / "outside-dir").mkdir()
    (root / "dist" / "leak").symlink_to(tmp_path / "outside-dir", target_is_directory=True)
    return root


def _internal_fifo(root: Path, tmp_path: Path) -> Path:
    os.mkfifo(root / "dist" / "pipe")
    return root


def _symlinked_parent(root: Path, tmp_path: Path) -> Path:
    (tmp_path / "parent-link").symlink_to(tmp_path, target_is_directory=True)
    return tmp_path / "parent-link" / root.name


@pytest.mark.parametrize("arrange", [_internal_file_symlink, _internal_dir_symlink, _internal_fifo, _symlinked_parent])
def test_unsafe_tree_is_rejected_before_provider_starts(tmp_path: Path, arrange: Any) -> None:
    fake = make_fake_rea(tmp_path, "print('{}')\n")
    given = arrange(copy_app(tmp_path), tmp_path)
    result = run_static_analysis(str(fake), str(given))
    assert (result.status, result.diagnostics[0].code, result.analysis) == ("failed", "invalid_static_input", None)
    shown = json.dumps([d.__dict__ for d in result.diagnostics], ensure_ascii=False)
    assert str(tmp_path) not in shown
    assert fake_log(tmp_path) is None  # provider は起動していない


@pytest.mark.skipif(os.geteuid() == 0, reason="root は権限に関係なく読めるため")
def test_unreadable_referenced_file_fails_with_sanitized_diagnostic(tmp_path: Path) -> None:
    root = copy_app(tmp_path)
    target = root / "src" / "app.ts"
    fake = make_fake_rea(tmp_path, emit_evidence(tmp_path, load_fixture()))
    target.chmod(0)
    try:
        assert verify_file(root, "src/app.ts").status == "unreadable"
        result = run_static_analysis(str(fake), str(root))
    finally:
        target.chmod(0o644)
    assert (result.status, result.diagnostics[0].code, result.analysis) == ("failed", "static_input_unreadable", None)
    shown = json.dumps([d.__dict__ for d in result.diagnostics], ensure_ascii=False)
    assert str(tmp_path) not in shown


def test_verify_file_read_error_is_not_raised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = copy_app(tmp_path)

    def broken_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(Path, "open", broken_open)
    assert verify_file(root, "dist/app.js").status == "unreadable"


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ("print('not json')\n", "invalid_provider_output"),
        ("print(json.dumps({'error': 'JavaScript application analysis failed', 'code': 'X'})); sys.exit(1)\n", "provider_reported_error"),
        ("sys.stdout.write('{\"evidence_id\": '); sys.exit(3)\n", "provider_exit_nonzero"),
        # --full-output 付きの外枠 {ok, data, meta} は 6.7.0 の --json 単独の出力ではない
        (f"print(json.dumps({{'ok': True, 'data': json.load(open({str(EVIDENCE_FIXTURE)!r})), 'meta': {{}}}}))\n", "invalid_provider_output"),
    ],
)
def test_broken_outputs_fail_without_evidence(tmp_path: Path, body: str, code: str) -> None:
    fake = make_fake_rea(tmp_path, body)
    result = run_static_analysis(str(fake), str(copy_app(tmp_path)))
    assert result.status == "failed"
    assert result.diagnostics[0].code == code
    assert result.analysis is None


def test_valid_evidence_with_nonzero_exit_is_not_adopted(tmp_path: Path) -> None:
    fake = make_fake_rea(tmp_path, emit_evidence(tmp_path, load_fixture()) + "sys.exit(4)\n")
    result = run_static_analysis(str(fake), str(copy_app(tmp_path)))
    assert (result.status, result.diagnostics[0].code, result.analysis) == ("failed", "provider_exit_nonzero", None)


_STUBBORN_WITH_CHILD = (
    "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    f"open(LOG + '.child', 'w').write(str(child.pid))\n"
    "time.sleep(60)\n"
)


def test_timeout_stops_owned_process_group_after_grace(tmp_path: Path) -> None:
    fake = make_fake_rea(tmp_path, _STUBBORN_WITH_CHILD)
    started = time.monotonic()
    result = run_static_analysis(str(fake), str(copy_app(tmp_path)), analysis_timeout=1.0, grace=0.5)
    elapsed = time.monotonic() - started
    assert (result.status, result.diagnostics[0].code) == ("failed", "provider_timeout")
    assert 1.0 <= elapsed < 10
    child = int((tmp_path / "fake-log.json.child").read_text())
    deadline = time.monotonic() + 2
    while pid_alive(child) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not pid_alive(child)  # SIGTERM を無視した leader と孫まで停止
    log = fake_log(tmp_path)
    assert log is not None and not Path(log["cwd"]).exists()


def _wait_dead(pids: list[int], seconds: float = 2) -> list[int]:
    """製品の停止を待ち、まだ生きている pid を返す（テスト側では kill しない）。"""
    deadline = time.monotonic() + seconds
    while any(pid_alive(p) for p in pids) and time.monotonic() < deadline:
        time.sleep(0.05)
    return [p for p in pids if pid_alive(p)]


def test_cancel_event_stops_analysis_and_owned_group(tmp_path: Path) -> None:
    fake = make_fake_rea(tmp_path, _STUBBORN_WITH_CHILD)
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    result = run_static_analysis(str(fake), str(copy_app(tmp_path)), cancel_event=cancel, grace=0.5)
    assert (result.status, result.diagnostics[0].code, result.analysis) == ("cancelled", "provider_cancelled", None)
    child = int((tmp_path / "fake-log.json.child").read_text())
    assert _wait_dead([child]) == []  # SIGTERM を無視した leader の孫まで製品が停止


def _version_hang_rea(tmp_path: Path) -> Path:
    """--version の応答前に止まる偽 rea。子を作り pid を残す。解析に入れば LOG を書く。"""
    script = tmp_path / "hang-rea"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, os, signal, subprocess, sys, time\n"
        f"LOG = {str(tmp_path / 'fake-log.json')!r}\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"    open({str(tmp_path / 'probe.pids')!r}, 'w').write(f'{{os.getpid()}} {{child.pid}}')\n"
        "    time.sleep(60)\n"
        "open(LOG, 'w').write('analysis started')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_cancel_during_version_probe_is_cancelled_not_unavailable(tmp_path: Path) -> None:
    fake = _version_hang_rea(tmp_path)
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    result = run_static_analysis(str(fake), str(copy_app(tmp_path)), cancel_event=cancel, grace=0.5)
    assert (result.status, result.diagnostics[0].code, result.analysis) == ("cancelled", "provider_cancelled", None)
    pids = [int(p) for p in (tmp_path / "probe.pids").read_text().split()]
    assert _wait_dead(pids) == []  # 版確認の leader と子を製品が停止
    assert fake_log(tmp_path) is None  # 取り消し後に解析を起動していない


def test_probe_receives_cancel_event_by_keyword(tmp_path: Path) -> None:
    received: dict[str, Any] = {}

    def probe(command: str, **kwargs: Any) -> Any:
        received.update(kwargs)
        return probe_version(command, **kwargs)

    fake = _version_hang_rea(tmp_path)
    cancel = threading.Event()
    cancel.set()
    result = run_static_analysis(str(fake), str(copy_app(tmp_path)), cancel_event=cancel, grace=0.5, probe=probe)
    assert received["cancel_event"] is cancel and result.status == "cancelled"


def test_stdout_over_limit_is_not_parsed_as_partial(tmp_path: Path) -> None:
    fake = make_fake_rea(tmp_path, emit_evidence(tmp_path, load_fixture()))
    result = run_static_analysis(str(fake), str(copy_app(tmp_path)), stdout_limit=1000, grace=0.5)
    assert (result.status, result.diagnostics[0].code, result.analysis) == ("failed", "provider_output_limit_exceeded", None)


def test_stderr_is_bounded_and_never_shown(tmp_path: Path) -> None:
    body = "sys.stderr.write('SECRET-TOKEN /Users/someone/private ' * 50); sys.stderr.flush(); time.sleep(5)\n"
    fake = make_fake_rea(tmp_path, body)
    result = run_static_analysis(str(fake), str(copy_app(tmp_path)), stderr_limit=200, grace=0.5)
    assert (result.status, result.diagnostics[0].code) == ("failed", "provider_stderr_limit_exceeded")
    shown = json.dumps([d.__dict__ for d in result.diagnostics], ensure_ascii=False)
    assert "SECRET-TOKEN" not in shown and "/Users/" not in shown


def test_progress_on_stderr_within_limit_does_not_fail(tmp_path: Path) -> None:
    body = "sys.stderr.write(json.dumps({'rea_progress': {'phase': 'x'}}) + '\\n')\n" + emit_evidence(tmp_path, load_fixture())
    fake = make_fake_rea(tmp_path, body)
    assert run_static_analysis(str(fake), str(copy_app(tmp_path))).status == "complete"


# ---------------------------------------------------------------- 参照ファイル


def test_verify_file_rejects_traversal_symlink_and_missing(tmp_path: Path) -> None:
    root = copy_app(tmp_path)
    (tmp_path / "outside.js").write_text("x")
    (root / "dist" / "escape.js").symlink_to(tmp_path / "outside.js")
    assert verify_file(root, "../outside.js").status == "unsafe"
    assert verify_file(root, "/etc/hosts").status == "unsafe"
    assert verify_file(root, "dist/escape.js").status == "unsafe"
    assert verify_file(root, "dist/none.js").status == "missing"
    assert verify_file(root, "dist").status == "not_regular"
    verified = verify_file(root, "dist/app.js")
    assert verified.status == "verified" and verified.size == (root / "dist" / "app.js").stat().st_size


# ---------------------------------------------------------------- 境界の型不正・unsafe 参照


def _first_obs(evidence: dict[str, Any], kind: str) -> dict[str, Any]:
    node = next(n for n in evidence["normalized_result"]["graph"]["nodes"] if n["kind"] == kind)
    return node["observations"][0]


def _assert_sanitized_invalid(result: Any, tmp_path: Path) -> None:
    assert (result.status, result.analysis, result.evidence_id) == ("failed", None, None)
    assert [d.code for d in result.diagnostics] == ["invalid_provider_output"]
    shown = json.dumps([d.__dict__ for d in result.diagnostics], ensure_ascii=False)
    assert str(tmp_path) not in shown and "Traceback" not in shown and "/etc" not in shown


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: _first_obs(e, "endpoint")["evidence"].update(authority=[]),
        lambda e: _first_obs(e, "endpoint")["evidence"].update(state={}),
        lambda e: _first_obs(e, "endpoint")["evidence"].update(confidence=["exact"]),
        lambda e: _first_obs(e, "source-module").update(source_map_reference={"resolution": []} | {
            k: v for k, v in _first_obs(e, "source-module")["source_map_reference"].items() if k != "resolution"}),
        lambda e: e["normalized_result"]["graph"]["nodes"][0].update(identity=[]),
    ],
)
def test_schema_type_errors_become_sanitized_invalid_provider_output(tmp_path: Path, mutate: Any) -> None:
    evidence = load_fixture()
    mutate(evidence)
    fake = make_fake_rea(tmp_path, emit_evidence(tmp_path, recommit(evidence)))
    _assert_sanitized_invalid(run_static_analysis(str(fake), str(copy_app(tmp_path))), tmp_path)


def test_keyboard_interrupt_in_validation_is_not_swallowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import reverse_analysis.rea_adapter as adapter

    def interrupted(_: Any) -> Any:
        raise KeyboardInterrupt

    monkeypatch.setattr(adapter, "validate_evidence", interrupted)
    fake = make_fake_rea(tmp_path, emit_evidence(tmp_path, load_fixture()))
    with pytest.raises(KeyboardInterrupt):
        run_static_analysis(str(fake), str(copy_app(tmp_path)))


@pytest.mark.parametrize("bad", ["/etc/passwd", "../outside.js", "dist/../../outside.js", "ABSROOT/dist/app.js"])
@pytest.mark.parametrize("where", ["source", "map_path", "resolution"])
def test_unsafe_reference_paths_are_rejected_before_any_file_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str, where: str
) -> None:
    import reverse_analysis.rea_adapter as adapter

    root = copy_app(tmp_path)
    bad = bad.replace("ABSROOT", str(root.resolve()))
    evidence = load_fixture()
    if where == "source":
        _first_obs(evidence, "endpoint")["evidence"]["location"]["value"]["source"] = bad
    elif where == "map_path":
        _first_obs(evidence, "source-module")["source_map_reference"]["map_path"] = bad
    else:
        _first_obs(evidence, "source-module")["source_map_reference"]["resolution"]["path"] = bad

    def no_read(*_: Any) -> Any:
        raise AssertionError("参照ファイルを読んではいけない")

    monkeypatch.setattr(adapter, "verify_file", no_read)
    fake = make_fake_rea(tmp_path, emit_evidence(tmp_path, recommit(evidence)))
    result = run_static_analysis(str(fake), str(root))
    _assert_sanitized_invalid(result, tmp_path)
    assert result.files == ()


def test_original_source_name_with_parent_segment_is_still_accepted() -> None:
    evidence = load_fixture()
    assert _first_obs(evidence, "source-module")["source_map_reference"]["source_name"] == "../src/app.ts"
    validate_evidence(evidence)
