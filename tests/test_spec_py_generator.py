"""Python spec 生成器: TS 生成器と同じ入力から同じ操作を表すコードが出ること。"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from web.services import pw_spec_api
from web.services.spec_py_generator import generate_spec_py, metadata_file_path_py
from web.services.spec_ts_generator import generate_spec_ts

URL = "https://example.com/ja/form"


def _field(name: str, ftype: str = "text", **kw):
    return {"name": name, "field_type": ftype, "locators": [f'[name="{name}"]'], **kw}


def _candidates():
    return [
        {"id": "T1", "title": "画面表示スモーク", "trace_id": "P001",
         "steps": [f"page.goto('{URL}')"], "expected": "表示"},
        {"id": "T2", "title": "画面遷移", "trace_id": "P001->P002",
         "steps": [f"page.goto('{URL}')"]},
        {"id": "T3", "title": "フォーム入力", "trace_id": "P001-F01-I01",
         "steps": [f"page.goto('{URL}')"], "form_action": "/submit",
         "field": _field("email", "email"),
         "required_siblings": [_field("visit_date", "date"), _field("kind", "select",
                               options=["選択してください", "A"]), _field("agree", "checkbox")]},
        {"id": "T4", "title": "必須入力", "trace_id": "P001-F01-I02",
         "steps": [f"page.goto('{URL}')"], "form_action": "/submit",
         "field": _field("kind", "select", options=["選択してください", "A"])},
        {"id": "T5", "title": "手動確認", "trace_id": "P009", "automation_status": "manual-review",
         "steps": []},
    ]


@pytest.fixture
def paths(tmp_path: Path):
    cand = tmp_path / "playwright_candidates.json"
    cand.write_text(json.dumps({"candidates": _candidates()}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "report.json").write_text(json.dumps({"screens": [
        {"page_id": "P001", "url": URL, "title": "お問い合わせフォーム", "fingerprint": "fp1"},
        {"page_id": "P002", "url": "https://example.com/ja/done", "title": "完了画面",
         "fingerprint": "fp2"},
    ]}, ensure_ascii=False), encoding="utf-8")
    return tmp_path, cand


def test_compiles_and_maps_operations(paths):
    d, cand = paths
    out = d / "autorun_spec.py"
    generate_spec_py("example.com", cand, out, allow_submit=True)
    src = out.read_text(encoding="utf-8")
    ast.parse(src)
    compile(src, str(out), "exec")
    assert "playwright" not in src.split("from web.services")[0]
    # スモーク・遷移
    assert "assert 'お問い合わせフォーム' in title" in src
    assert "page.goto('https://example.com/ja/done')" in src
    assert "assert '完了画面' in title" in src
    # skip
    assert "skip=True" in src
    # フォーム: fill/select/check/clear/検証/送信
    assert ".fill('webspec2doc-qa@example.com')" in src
    assert ".select_option('A')" in src
    assert ".check()" in src
    assert "checkValidity" in src and "form_valid is True" in src
    assert ".select_option('選択してください')" in src
    assert "field_valid is False" in src
    assert "strftime('%Y/%m/%d')" in src  # /ja/ は YYYY/MM/DD
    assert "force=True" in src
    assert "submit_button.click()" in src


def test_no_submit_by_default(paths):
    d, cand = paths
    out = d / "a_spec.py"
    generate_spec_py(cand, out, "example.com")  # design 順の引数も受理
    src = out.read_text(encoding="utf-8")
    ast.parse(src)
    assert "submit" not in src.replace("# ", "").replace("/submit", "")


def test_meta_ids_match_ts(paths):
    d, cand = paths
    py_out = d / "py" / "autorun_spec.py"
    ts_out = d / "ts" / "autorun.spec.ts"
    py_out.parent.mkdir()
    ts_out.parent.mkdir()
    generate_spec_py("example.com", cand, py_out)
    generate_spec_ts("example.com", cand, ts_out)
    py_meta = json.loads(metadata_file_path_py(py_out).read_text(encoding="utf-8"))
    ts_meta = json.loads((ts_out.parent / "autorun.meta.json").read_text(encoding="utf-8"))
    assert py_meta == ts_meta
    ts_src = ts_out.read_text(encoding="utf-8")
    py_src = py_out.read_text(encoding="utf-8")
    assert ts_src.count("test(") + ts_src.count("test.skip(") == py_src.count("@case(")
    assert py_src.count("skip=True") == ts_src.count("test.skip(")


def test_filter_and_exec_with_fake_page(paths):
    d, cand = paths
    out = d / "s_spec.py"
    generate_spec_py("example.com", cand, out, filter_mode="smoke")
    assert out.read_text(encoding="utf-8").count("@case(") == 1

    out2 = d / "all_spec.py"
    generate_spec_py("example.com", cand, out2, enable_strong_assertions=True,
                     enable_self_healing=True)
    ast.parse(out2.read_text(encoding="utf-8"))
    pw_spec_api.reset_registry()
    ns: dict = {}
    exec(compile(out2.read_text(encoding="utf-8"), str(out2), "exec"), ns)
    cases = pw_spec_api.registered_cases()
    assert [c.skip for c in cases] == [False, False, False, False, True]
    assert cases[0].label == "T1 画面表示スモーク [P001]"
    pw_spec_api.reset_registry()
