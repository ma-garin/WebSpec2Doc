"""doc サブコマンド（web/cli_doc_assure.py）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.cli_doc_assure import main

TEXT = "# 要件\n\nREQ-1 システムはログインできること。\nREQ-2 応答は 3 秒以内であること。\n"


@pytest.fixture()
def doc(tmp_path):
    p = tmp_path / "spec.md"
    p.write_text(TEXT, encoding="utf-8")
    return p


@pytest.mark.parametrize("cmd", ["verify", "requirements", "conflicts", "trace"])
@pytest.mark.parametrize("fmt", ["json", "md", "csv"])
def test_formats(cmd, fmt, doc, tmp_path):
    out = tmp_path / "o.txt"
    code = main([cmd, str(doc), "--format", fmt, "--out", str(out)])
    assert code in (0, 2)
    body = out.read_text(encoding="utf-8")
    assert body.strip()
    if fmt == "json":
        json.loads(body)


def test_stdout_default_md(doc, capsys):
    main(["verify", str(doc)])
    assert "Document Assurance Report" in capsys.readouterr().out


def test_missing_file(tmp_path, capsys):
    assert main(["verify", str(tmp_path / "none.md")]) == 1
    assert "見つかりません" in capsys.readouterr().err


def test_unsupported_format(tmp_path, capsys):
    p = tmp_path / "a.exe"
    p.write_bytes(b"x")
    assert main(["verify", str(p)]) == 1
    assert "対応形式" in capsys.readouterr().err


def test_empty_file(tmp_path):
    p = tmp_path / "e.md"
    p.write_text("  \n", encoding="utf-8")
    assert main(["verify", str(p)]) == 1


def test_exit_codes_by_state(doc, monkeypatch):
    from web.services.docassure import pipeline
    real = pipeline.analyze

    def fake(state):
        return lambda *a, **k: {**real(*a, **k), "readiness": {"state": state, "reasons": []}}
    for state, blocked_default, cond in (("BLOCKED", 2, 2), ("CONDITIONALLY_READY", 0, 2), ("READY", 0, 0)):
        monkeypatch.setattr(pipeline, "analyze", fake(state))
        assert main(["verify", str(doc), "--format", "json"]) == blocked_default
        assert main(["verify", str(doc), "--format", "json", "--fail-on", "conditional"]) == cond


def test_no_args_is_input_error():
    assert main([]) == 1
