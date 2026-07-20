"""管理 CLI（src/cli_manage.py）のうち、web 非依存ロジックのテスト。

`_load_candidates`（経路・形式のフォールバック）と `_format_row`（整形）を検証する。
これらは cli_manage の import 時点で web/flask を読み込まないため、単体で動く。
"""

from __future__ import annotations

import json

import cli_manage


def test_load_candidates_prefers_domain_root(tmp_path) -> None:
    domain = "example.com"
    root = tmp_path / domain
    root.mkdir(parents=True)
    (root / "playwright_candidates.json").write_text(
        json.dumps([{"id": "root1"}]), encoding="utf-8"
    )
    qa = root / "qa_process"
    qa.mkdir()
    (qa / "playwright_candidates.json").write_text(
        json.dumps({"candidates": [{"id": "qa1"}]}), encoding="utf-8"
    )
    assert cli_manage._load_candidates(tmp_path, domain) == [{"id": "root1"}]


def test_load_candidates_falls_back_to_qa_process(tmp_path) -> None:
    domain = "example.com"
    qa = tmp_path / domain / "qa_process"
    qa.mkdir(parents=True)
    (qa / "playwright_candidates.json").write_text(
        json.dumps({"candidates": [{"id": "qa1"}]}), encoding="utf-8"
    )
    assert cli_manage._load_candidates(tmp_path, domain) == [{"id": "qa1"}]


def test_load_candidates_missing_returns_empty(tmp_path) -> None:
    assert cli_manage._load_candidates(tmp_path, "example.com") == []


def test_load_candidates_ignores_broken_json(tmp_path) -> None:
    domain = "example.com"
    root = tmp_path / domain
    root.mkdir(parents=True)
    (root / "playwright_candidates.json").write_text("{ broken", encoding="utf-8")
    assert cli_manage._load_candidates(tmp_path, domain) == []


def test_format_row_dict_and_scalar() -> None:
    assert cli_manage._format_row("hello") == "hello"
    line = cli_manage._format_row({"id": "s1", "name": "標準観点"})
    assert "id=s1" in line and "name=標準観点" in line


def test_build_parser_requires_group() -> None:
    parser = cli_manage._build_parser()
    with __import__("pytest").raises(SystemExit):
        parser.parse_args([])
