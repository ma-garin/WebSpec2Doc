"""reverse analysis サービスと CLI の結線（Native 静的解析は stub で差し替える）。

静的解析の中身（抽出・route・source map）は native 側のテストが持つ。ここで守るのは
結線: 保存先の拒否・取り消し・schema・旧名の読込・外部プロセスを起動しないこと。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import main
from crawler.page_crawler import ApiEndpoint, PageData
from diff.snapshot import save_snapshot
from reverse_analysis import reporter
from reverse_analysis.models import Coverage, SourceLocation, StaticCandidate
from reverse_analysis.normalize import StaticNormalization
from reverse_analysis.reporter import (
    OUTPUT_FILENAME,
    TOP_LEVEL_KEYS,
    ReportSchemaError,
    load_document,
    validate_document,
)
from reverse_analysis.service import (
    ENGINE_LIMITATIONS,
    LIMIT_STATIC_SYNTAX_ONLY,
    ReverseAnalysisRequest,
    run_reverse_analysis,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "reverse_analysis"
ENGINE = "webspec2doc-native/test"


# ---------------------------------------------------------------- 補助


@dataclass(frozen=True)
class _Result:
    normalization: StaticNormalization


def _candidate(kind: str, path: str, line: int, method: str | None) -> StaticCandidate:
    sha = hashlib.sha256(path.encode()).hexdigest()
    return StaticCandidate(
        id=f"sc_{kind}_{line}", kind=kind, artifact_path="dist/app.js", artifact_sha256=sha,
        location=SourceLocation("dist/app.js", "line_column_utf16", line, 0, line, 10),
        resolution="exact", epistemic_state="observed" if kind == "api" else "inferred",
        authority="syntax", method=method, path=path,
    )  # fmt: skip


def _static(status: str = "complete") -> StaticNormalization:
    candidates = (
        _candidate("api", "/api/orders", 3, "GET"),
        _candidate("route", "/users", 9, None),
    )
    return StaticNormalization(
        status, ENGINE, "a" * 64, (), candidates, Coverage(status, False, 0, ()), (), (),
    )  # fmt: skip


def _runner(status: str = "complete") -> Any:
    calls: list[tuple[str, Any]] = []

    def run(js_input: str, *, cancel_event: threading.Event | None = None) -> _Result:
        calls.append((js_input, cancel_event))
        return _Result(_static(status))

    run.calls = calls  # type: ignore[attr-defined]
    return run


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


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
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    import reverse_analysis.service as service

    app = tmp_path / "input-app"
    shutil.copytree(FIXTURE_DIR / "app", app)
    monkeypatch.setattr(service, "run_static_analysis", _runner())
    return {"app": app, "snapshot": _snapshot(tmp_path), "out": tmp_path / "out"}


def _request(env: dict[str, Path], **override: Any) -> ReverseAnalysisRequest:
    values = {
        "js_input": str(env["app"]),
        "runtime_snapshot": str(env["snapshot"]),
        "output_dir": str(env["out"]),
    }
    values.update({k: str(v) for k, v in override.items()})
    return ReverseAnalysisRequest(**values)


def _cli_argv(env: dict[str, Path], out: Path | None = None) -> list[str]:
    return [
        "--reverse-analysis",
        "--js-input", str(env["app"]),
        "--runtime-snapshot", str(env["snapshot"]),
        "--output", str(out or env["out"]),
    ]  # fmt: skip


def _parse(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> Any:
    monkeypatch.setattr(sys, "argv", ["main.py", *argv])
    return main.parse_args()


# ---------------------------------------------------------------- 正常系


def test_保存したJSONはengine_versionと既知の制限を持ち実測と静的を混ぜない(env: dict[str, Path]) -> None:
    before_app, before_snap = _tree_digest(env["app"]), env["snapshot"].read_bytes()
    outcome = run_reverse_analysis(_request(env))
    assert outcome.exit_code == 0 and outcome.output_path is not None
    assert sorted(p.name for p in env["out"].iterdir()) == [OUTPUT_FILENAME]
    doc = load_document(outcome.output_path)
    assert tuple(doc) == TOP_LEVEL_KEYS and doc["status"] == "complete"
    assert doc["producer"]["engine_version"] == ENGINE and "provider_version" not in doc["producer"]
    assert doc["inputs"]["static_root_label"] == "input-app"
    limits = doc["coverage"]["static"]["limitations"]
    assert LIMIT_STATIC_SYNTAX_ONLY in limits and set(ENGINE_LIMITATIONS) <= set(limits)
    assert not any("provider_endpoint" in lim or "provider_route" in lim for lim in limits)
    assert not any("REA" in d["message"] for d in doc["diagnostics"])
    assert {c["kind"] for c in doc["static_candidates"]} == {"api", "route"}
    assert doc["summary"]["observed_api_records"] == len(doc["runtime_observations"]) == 2
    assert all(r["epistemic_state"] != "observed" for r in doc["relations"])
    assert _tree_digest(env["app"]) == before_app and env["snapshot"].read_bytes() == before_snap


def test_同じ入力から同じバイト列のJSONになる(env: dict[str, Path], tmp_path: Path) -> None:
    first = run_reverse_analysis(_request(env))
    second = run_reverse_analysis(_request(env, output_dir=tmp_path / "out2"))
    assert first.output_path and second.output_path
    assert first.output_path.read_bytes() == second.output_path.read_bytes()


def test_include_provenanceは出典を保存し既定では保存しない(env: dict[str, Path], tmp_path: Path) -> None:
    plain = run_reverse_analysis(_request(env))
    assert plain.document is not None and "provider_evidence" not in plain.document
    opted = run_reverse_analysis(
        ReverseAnalysisRequest(str(env["app"]), str(env["snapshot"]), str(tmp_path / "o2"), True)
    )
    assert opted.document is not None and "provider_evidence" in opted.document


def test_serviceは外部プロセスを起動しない(env: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_a: Any, **_k: Any) -> Any:
        pytest.fail("外部プロセスを起動した")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    runner = _runner()
    outcome = run_reverse_analysis(_request(env), static_runner=runner)
    assert outcome.exit_code == 0 and len(runner.calls) == 1
    assert runner.calls[0][0] == str(env["app"]) and runner.calls[0][1] is not None


def test_request_にREA実行ファイルの項目は無い() -> None:
    names = set(ReverseAnalysisRequest.__dataclass_fields__)
    assert names == {"js_input", "runtime_snapshot", "output_dir", "include_provenance"}


def test_旧名producer_provider_versionで保存済みの文書も検証できる(env: dict[str, Path]) -> None:
    outcome = run_reverse_analysis(_request(env))
    assert outcome.document is not None
    legacy = json.loads(json.dumps(outcome.document))
    legacy["producer"] = {
        "name": legacy["producer"]["name"],
        "version": legacy["producer"]["version"],
        "provider_version": "6.7.0",
    }
    validate_document(legacy)


# ---------------------------------------------------------------- 失敗系（保存される）


def test_静的解析がunavailableでも実測は保存し非成功(env: dict[str, Path]) -> None:
    outcome = run_reverse_analysis(_request(env), static_runner=_runner("unavailable"))
    assert outcome.status == "unavailable" and outcome.exit_code == 2 and outcome.output_path
    doc = load_document(outcome.output_path)
    assert len(doc["runtime_observations"]) == 2 and doc["coverage"]["runtime"]["status"] == "complete"

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
        ["--reverse-analysis", "--js-input", "a", "--runtime-snapshot", "b"],
        ["--reverse-analysis", "--js-input", "a", "--runtime-snapshot", "b", "--rea-command", "/c", "--output", "o"],
    ],
)
def test_入力不足_flag無しの専用引数_既定出力先_旧rea_commandは拒否する(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        _parse(monkeypatch, argv)
    assert exc.value.code == 2


def test_旧名の_reverse_provider_evidence_は別名として受理する(env: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    for flag in ("--reverse-provenance", "--reverse-provider-evidence"):
        args = _parse(monkeypatch, [*_cli_argv(env), flag])
        assert args.reverse_provenance is True
    assert _parse(monkeypatch, _cli_argv(env)).reverse_provenance is False


def test_flag無しの_reverse_provenance_は拒否する(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit) as exc:
        _parse(monkeypatch, ["--reverse-provenance"])
    assert exc.value.code == 2


@pytest.mark.parametrize("extra", [["--url", "https://e.example"], ["--urls", "https://e.example"], ["--compare"], ["--ci"]])
def test_既存クロールモードとの併用は拒否する(env: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], extra: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        _parse(monkeypatch, [*_cli_argv(env), *extra])
    assert exc.value.code == 2
    assert "併用できません" in capsys.readouterr().err
    assert not env["out"].exists()


def test_CLIは要約を表示し出力先を示す(env: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    code = main._run_reverse_analysis(_parse(monkeypatch, _cli_argv(env)))
    out = capsys.readouterr().out
    assert code == 0 and f"出力先: {env['out'] / OUTPUT_FILENAME}" in out
    for label in ("実測", "静的構文の事実", "対応推論", "coverage 静的", "coverage 実測"):
        assert label in out


def test_flag_OFFではreverse_analysisをimportしない() -> None:
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
