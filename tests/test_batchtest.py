"""バッチ・スクリプトのテスト（System 07）。読み取り・ケース設計・コード生成・API の受入基準。"""
from __future__ import annotations

import ast
import io
import zipfile

import pytest

import app as appmod
from web import config
from web.services.batchtest import codegen, design, parse

BAT = """@echo off
if not defined CLOSE_HOME (
  echo CLOSE_HOME が設定されていません 1>&2
  exit /b 9
)
if "%~1"=="" (
  echo 使い方: monthly_close.bat YYYYMM
  exit /b 2
)
set "YM=%~1"
echo %YM%| findstr /r "^20[0-9][0-9][01][0-9]$" >nul || (
  echo 年月が不正です 1>&2
  exit /b 2
)
set "IN=%CLOSE_HOME%\\data\\in\\input_%YM%.csv"
if not exist "%IN%" (
  echo 入力ファイルがありません 1>&2
  exit /b 1
)
if /i "%~2"=="--dry-run" goto :eof
type "%IN%" > "%CLOSE_HOME%\\data\\out\\close_%YM%.csv"
exit /b 0
"""
FILES = [{"name": "monthly_close.bat", "kind": "script"}, {"name": "input_202609.csv", "kind": "input"}]


def test_analyze_reads_args_exit_codes_and_files():
    """Given バッチ / When 読み取る / Then 引数・フラグ・終了コードの意味・入出力・環境変数が取れる。"""
    f = parse.analyze(BAT, "monthly_close.bat")
    assert [a["name"] for a in f["args"]] == ["YM"]
    assert f["args"][0]["required"] and f["args"][0]["format"] == "yyyymm"
    assert [x["name"] for x in f["flags"]] == ["--dry-run"]
    codes = {c["code"]: [m["text"] for m in c["meanings"]] for c in f["exit_codes"]}
    assert codes["2"] == ["使い方: monthly_close.bat YYYYMM", "年月が不正です"]
    assert codes["1"] == ["入力ファイルがありません"]
    assert f["inputs"][0]["path"].endswith("input_%YM%.csv")
    assert f["outputs"][0]["path"].endswith("close_%YM%.csv")
    assert [e["name"] for e in f["env_vars"]] == ["CLOSE_HOME"]


def test_design_uses_evidence_and_marks_unknown_as_ask():
    """Given 読み取り結果 / When ケースを作る / Then 根拠のある期待結果は終了コード付き、根拠の無いものは要確認。"""
    f = parse.analyze(BAT, "monthly_close.bat")
    cases = design.design(f, [], FILES, parse.default_command(f))
    by = {c["pre"]: c for c in cases}
    assert by["YM を省く"]["expect"]["code"] == 2 and not by["YM を省く"]["ask"]
    assert by["YM = 202613（無効の端）"]["expect"]["code"] == 2
    assert by["入力ファイルを置かない"]["expect"]["code"] == 1
    assert by["CLOSE_HOME を未設定にする"]["expect"]["code"] == 9
    assert by["見出し行だけ（0 件）"]["ask"] and by["見出し行だけ（0 件）"]["expect"]["code"] is None
    assert [c["id"] for c in cases] == [f"B-{i:02d}" for i in range(1, len(cases) + 1)]


def test_design_takes_evidence_from_spec():
    f = parse.analyze(BAT, "monthly_close.bat")
    spec = [{"file": "仕様.md", "text": "同じ年月で再実行した場合は出力を上書きする。", "location": "4 行"}]
    rerun = next(c for c in design.design(f, spec, FILES, "") if c["obs"] == "再実行")
    assert not rerun["ask"] and rerun["src"] == "仕様.md 4 行"


@pytest.mark.parametrize("fw, name", [("pytest", "test_monthly_close.py"), ("pester", "monthly_close.Tests.ps1"),
                                      ("bats", "monthly_close.bats")])
def test_codegen_one_test_per_case(fw, name):
    f = parse.analyze(BAT, "monthly_close.bat")
    cases = design.design(f, [], FILES, "")
    src = codegen.generate(f, cases, FILES, fw)
    assert src[0]["name"] == name
    if fw == "pytest":
        ast.parse(src[0]["body"])
    else:
        assert src[0]["body"].count(cases[-1]["id"]) >= 1


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return appmod.app.test_client()


def test_api_end_to_end(client):
    """作成 → 取り込み → 読み取り → ケース → コード → 書き出し が API で通る。"""
    jid = client.post("/api/batch-test/jobs", json={"name": "月次"}).get_json()["job"]["id"]
    data = {"files": [(io.BytesIO(BAT.encode()), "monthly_close.bat"), (io.BytesIO(b"id,v\n1,2\n"), "input_202609.csv")]}
    r = client.post(f"/api/batch-test/jobs/{jid}/files", data=data, content_type="multipart/form-data")
    assert [f["kind"] for f in r.get_json()["job"]["files"]] == ["script", "input"]
    assert client.post(f"/api/batch-test/jobs/{jid}/analyze").get_json()["job"]["settings"]["command"] == "monthly_close.bat {YM}"
    cases = client.post(f"/api/batch-test/jobs/{jid}/cases").get_json()["job"]["cases"]
    ask = next(c for c in cases if c["ask"])
    edited = client.patch(f"/api/batch-test/jobs/{jid}/cases/{ask['id']}", json={"exp": "0 件で終わる", "code": "0"}).get_json()
    assert not next(c for c in edited["job"]["cases"] if c["id"] == ask["id"])["ask"]
    assert client.post(f"/api/batch-test/jobs/{jid}/code").status_code == 200
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/batch-test/jobs/{jid}/export/code.zip").data))
    assert {"test_monthly_close.py", "README.md", "fixtures/monthly_close.bat"} <= set(z.namelist())
    assert client.get(f"/api/batch-test/jobs/{jid}/export/cases.xlsx").status_code == 200


def test_api_errors_are_user_readable(client):
    assert client.post("/api/batch-test/jobs", json={"name": ""}).status_code == 400
    assert client.get("/api/batch-test/jobs/000000000000").status_code == 404
    assert client.get("/api/batch-test/jobs/../x").status_code == 404
    jid = client.post("/api/batch-test/jobs", json={"name": "空"}).get_json()["job"]["id"]
    r = client.post(f"/api/batch-test/jobs/{jid}/analyze")
    assert r.status_code == 400 and "スクリプトがありません" in r.get_json()["error"]
    r = client.post(f"/api/batch-test/jobs/{jid}/files", data={"files": [(io.BytesIO(b""), "a.bat")]},
                    content_type="multipart/form-data")
    assert r.status_code == 400 and "空" in r.get_json()["error"]
    r = client.get(f"/api/batch-test/jobs/{jid}/export/code.zip")
    assert r.status_code == 400
