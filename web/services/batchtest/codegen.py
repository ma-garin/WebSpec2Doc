"""テストコードの生成。ケース表 1 行 = テスト 1 件。要確認のケースは skip で残す（消さない）。"""
from __future__ import annotations

import json
from pathlib import Path

_RUNNER = {"cmd": '["cmd", "/c", SCRIPT]', "sh": '["bash", SCRIPT]', "pwsh": '["pwsh", "-NoProfile", "-File", SCRIPT]'}

_PYTEST = '''"""自動生成: {script} のテスト（ケース表 {first}〜{last}・{n} 件）。

実行: pytest -v {fname}
・fixtures/ に取り込んだサンプルを置いてあります。
・パスに残った変数（%NAME% / $NAME）は、引数と環境変数の値で置き換えます。合わない所は VALUES を直してください。
・「要確認」のケースは skip にしてあります。期待結果が決まったら skip を外してください。
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = "{script}"
FACTS = json.loads(r\'\'\'{facts}\'\'\')
CASES = json.loads(r\'\'\'{cases}\'\'\')
SAMPLE = {sample}
EXPECTED = {expected}
TIMEOUT = 300


def resolve(template, values, home):
    import re
    path = re.sub(r"%~?(\\w+)%|\\$\\{{(\\w+)\\}}|\\$env:(\\w+)|\\$(\\w+)",
                  lambda m: values.get(next(g for g in m.groups() if g), m.group(0)), template)
    path = path.replace("\\\\", "/")
    p = Path(path)
    return p if p.is_absolute() else home / p


def prepare(case, home):
    shutil.copy(HERE / "fixtures" / SCRIPT, home / SCRIPT)
    env = dict(os.environ)
    values = {{e["name"]: str(home) for e in FACTS["env_vars"]}}
    env.update(values)
    for name in case["setup"]["unset_env"]:
        env.pop(name, None)
    values.update({{a["name"]: v for a, v in zip(FACTS["args"], case["argv"])}})
    inputs = [resolve(i["path"], values, home) for i in FACTS["inputs"]] or ([home / SAMPLE] if SAMPLE else [])
    mode = case["setup"]["inputs"]
    for target in inputs:
        if mode == "missing" or not SAMPLE:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = (HERE / "fixtures" / SAMPLE).read_text(encoding="utf-8", errors="replace").splitlines(True)
        if mode == "header_only":
            lines = lines[:1]
        elif mode == "broken" and lines:
            lines = lines + [",".join(lines[0].rstrip("\\r\\n").split(",")[:-1]) + "\\n"]
        target.write_text("".join(lines), encoding="utf-8")
    outputs = [resolve(o["path"], values, home) for o in FACTS["outputs"]]
    logs = [resolve(l["path"], values, home) for l in FACTS["logs"]]
    for p in outputs + logs:
        if not case["setup"]["outdir_missing"] or p not in outputs:
            p.parent.mkdir(parents=True, exist_ok=True)
    if case["setup"]["lock"] and FACTS["lock"]:
        lock = resolve(FACTS["lock"]["path"], values, home)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("", encoding="utf-8")
    return env, outputs, logs


def run(case, env, home):
    return subprocess.run({runner} + case["argv"], cwd=home, env=env,
                          capture_output=True, text=True, timeout=TIMEOUT)


def _read(p):
    return p.read_text(encoding="utf-8", errors="replace").replace("\\r\\n", "\\n")


@pytest.mark.parametrize("case", [
    pytest.param(c, id=c["id"], marks=[pytest.mark.skip(reason=c["id"] + ": 仕様に記載なし（要確認）")] if c["ask"] else [])
    for c in CASES
])
def test_case(case, tmp_path):
    env, outputs, logs = prepare(case, tmp_path)
    log_before = {{p: p.stat().st_size if p.exists() else 0 for p in logs}}
    first = None
    if case["setup"]["rerun"]:
        run(case, env, tmp_path)
        first = {{p: _read(p) for p in outputs if p.exists()}}
    r = run(case, env, tmp_path)
    exp = case["expect"]
    if exp["code"] is not None:
        assert r.returncode == exp["code"], f"終了コード {{r.returncode}}（期待 {{exp['code']}}）\\n{{r.stdout}}\\n{{r.stderr}}"
    if exp["output"] == "absent":
        assert not any(p.exists() for p in outputs), "出力ファイルが作られている"
    if exp["output"] in ("exists", "match", "same"):
        assert outputs and all(p.exists() for p in outputs), "出力ファイルが無い"
    if exp["output"] == "match" and EXPECTED:
        assert _read(outputs[0]) == _read(HERE / "fixtures" / EXPECTED), "出力が期待出力と違う"
    if exp["output"] == "same":
        assert {{p: _read(p) for p in outputs}} == first, "2 回目の出力が 1 回目と違う"
    if exp["log"] == "appended":
        assert any(p.exists() and p.stat().st_size > log_before[p] for p in logs), "ログに追記されていない"
'''

_PESTER = '''# 自動生成: {script} のテスト（Pester 5）。実行: Invoke-Pester -Output Detailed
# 確かめるのは終了コードと出力ファイルの有無。入力の作り分け（0 件・列不足）は pytest 版を使ってください。
BeforeAll {{ $Script = Join-Path $PSScriptRoot "fixtures/{script}" }}
Describe "{script}" {{
{blocks}}}
'''

_BATS = '''#!/usr/bin/env bats
# 自動生成: {script} のテスト（bats-core）。実行: bats {fname}
# 確かめるのは終了コードと出力ファイルの有無。入力の作り分け（0 件・列不足）は pytest 版を使ってください。
setup() {{
  cd "$BATS_TEST_TMPDIR"
  cp "$BATS_TEST_DIRNAME/fixtures/{script}" .
{envs}}}
{blocks}'''


def _pester_block(c: dict, facts: dict) -> str:
    skip = " -Skip" if c["ask"] else ""
    args = " ".join(f"'{a}'" for a in c["argv"])
    lines = [f'  It "{c["id"]} {c["obs"]}: {c["pre"]}"{skip} {{',
             "    Push-Location $TestDrive",
             *[f'    $env:{e["name"]} = $TestDrive' for e in facts["env_vars"] if e["name"] not in c["setup"]["unset_env"]],
             *[f'    Remove-Item Env:{n} -ErrorAction SilentlyContinue' for n in c["setup"]["unset_env"]]]
    runner = {"cmd": f"cmd /c $Script {args}", "sh": f"bash $Script {args}", "pwsh": f"& $Script {args}"}[facts["dialect"]]
    lines.append(f"    {runner} | Out-Null")
    if c["expect"]["code"] is not None:
        lines.append(f'    $LASTEXITCODE | Should -Be {c["expect"]["code"]}')
    lines += ["    Pop-Location", "  }", ""]
    return "\n".join(lines)


def _bats_block(c: dict, facts: dict) -> str:
    args = " ".join(f'"{a}"' for a in c["argv"])
    runner = {"cmd": "cmd /c", "sh": "bash", "pwsh": "pwsh -File"}[facts["dialect"]]
    body = [f'@test "{c["id"]} {c["obs"]}: {c["pre"]}" {{']
    if c["ask"]:
        body.append(f'  skip "{c["id"]}: 仕様に記載なし（要確認）"')
    body += [f"  unset {n}" for n in c["setup"]["unset_env"]]
    body.append(f'  run {runner} "./{facts["script"]}" {args}')
    if c["expect"]["code"] is not None:
        body.append(f'  [ "$status" -eq {c["expect"]["code"]} ]')
    return "\n".join(body + ["}", ""])


def generate(facts: dict, cases: list[dict], files: list[dict], framework: str) -> list[dict]:
    if not cases:
        raise ValueError("ケースがありません。先にケース表を作ってください。")
    stem = Path(facts["script"]).stem
    sample = next((f["name"] for f in files if f["kind"] == "input"), None)
    expected = next((f["name"] for f in files if f["kind"] == "expected"), None)
    ids = f'{cases[0]["id"]}〜{cases[-1]["id"]}（{len(cases)} 件）'
    if framework == "pytest":
        name = f"test_{stem}.py"
        body = _PYTEST.format(script=facts["script"], first=cases[0]["id"], last=cases[-1]["id"], n=len(cases),
                              fname=name, runner=_RUNNER[facts["dialect"]], sample=repr(sample), expected=repr(expected),
                              facts=json.dumps(facts, ensure_ascii=False, indent=1),
                              cases=json.dumps(cases, ensure_ascii=False, indent=1))
    elif framework == "pester":
        name = f"{stem}.Tests.ps1"
        body = _PESTER.format(script=facts["script"], blocks="".join(_pester_block(c, facts) for c in cases))
    else:
        name = f"{stem}.bats"
        envs = "".join(f'  export {e["name"]}="$BATS_TEST_TMPDIR"\n' for e in facts["env_vars"])
        body = _BATS.format(script=facts["script"], fname=name, envs=envs,
                            blocks="\n".join(_bats_block(c, facts) for c in cases))
    readme = (f"# {facts['script']} のテスト\n\n"
              f"- 生成元: WebSpec2Doc バッチ・スクリプトのテスト\n- ケース: {ids}\n"
              f"- 要確認（skip）: {', '.join(c['id'] for c in cases if c['ask']) or 'なし'}\n"
              f"- fixtures/ に取り込んだスクリプトとサンプルを置いています。\n"
              f"- このテストは生成しただけで、生成した環境では実行していません。\n")
    fixtures = [f["name"] for f in files if f["kind"] in ("script", "input", "expected")]
    return [
        {"name": name, "map": ids, "body": body},
        {"name": "README.md", "map": "実行のしかたと要確認の一覧", "body": readme},
        {"name": "fixtures/", "map": f"{len(fixtures)} ファイル（取り込んだもの）", "body": "\n".join(fixtures)},
    ]
