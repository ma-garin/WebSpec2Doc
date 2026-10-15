"""AC: 生成コードが構文として正しく、gate が assert の弱体化と password の直書きを検出する。"""
from __future__ import annotations

import ast
import re

import pytest

from web.services.backendtest import cases, codegen, codegen_gate, viewpoints

FACTS = [{"id": "F001", "subject": "orders.amount", "value": "numeric(10,2) NOT NULL", "origin": "ddl",
          "source": {"file": "schema.sql", "line": 4, "text": "amount numeric(10,2) NOT NULL"}}]


@pytest.fixture()
def generated():
    vps = viewpoints.build(FACTS, "system", "batch")
    built = cases.build(vps, FACTS, "system")
    assert built, "ケースが 0 件では生成コードを検証できない"
    job = {"cases": built, "facts": FACTS, "level": "system",
           "targets": [{"id": "T001", "kind": "batch", "name": "締め", "command": "run_close.sh"}]}
    return built, codegen.generate(job)


def _replace(files, path, text):
    return [{**f, "text": text} if f["path"] == path else f for f in files]


def test_generated_code_parses_and_passes_gate(generated):
    """Given ケース表 / When コードを生成 / Then 全 .py が ast.parse を通り gate の問題 0 件、全ケースに要約。"""
    built, out = generated
    for f in out["files"]:
        if f["path"].endswith(".py"):
            ast.parse(f["text"], filename=f["path"])
    assert codegen_gate.gate(out["files"], cases=built) == []
    assert set(out["summaries"]) == {c["id"] for c in built}
    assert all(out["summaries"].values())


def test_test_names_use_case_id_prefix(generated):
    """Given ケース ID / When 生成 / Then テスト名は test_<id 小文字>_ で始まり、部分一致で取り違えない。"""
    built, out = generated
    for c in built:
        assert str(out["map"][c["id"]]).startswith(f"test_{c['id'].lower()}_")


def test_gate_detects_weakened_assert(generated):
    """Given 前回の生成コード / When assert を pass に置き換えた版 / Then weakened で止まる。"""
    built, out = generated
    path = "tests/test_cases.py"
    text = next(f["text"] for f in out["files"] if f["path"] == path)
    weakened, n = re.subn(r"^(\s+)assert .*$", r"\1pass", text, count=1, flags=re.M)
    assert n == 1, "生成コードに assert が無い"
    new_files = _replace(out["files"], path, weakened)
    problems = codegen_gate.gate(new_files, previous_files=out["files"], cases=built)
    assert any(p["rule"] == "weakened" for p in problems)
    assert codegen_gate.guard(out["files"], new_files)


def test_gate_detects_hardcoded_password(generated):
    """Given 生成コードに password を直書き / When gate / Then secret で止まり行番号が付く。"""
    built, out = generated
    path = "tests/test_cases.py"
    text = next(f["text"] for f in out["files"] if f["path"] == path)
    leaked = _replace(out["files"], path, text + '\nDB_PASSWORD = "hunter2-real-pw"\n')
    problems = [p for p in codegen_gate.gate(leaked, cases=built) if p["rule"] == "secret"]
    assert problems and problems[0]["path"] == path and problems[0]["line"]
