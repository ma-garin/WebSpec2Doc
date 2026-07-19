"""Page Object 形式の spec.ts 出力（第9弾 E）の契約。

守るべきは「既定（フラット）が従来と一致すること」と「PO版が画面ごとの
クラスを持つこと」。
"""

from __future__ import annotations

import json
from pathlib import Path

from web.services.spec_ts_generator import generate_spec_ts


def _candidates(tmp_path: Path) -> Path:
    path = tmp_path / "playwright_candidates.json"
    path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "id": "PW-0001",
                        "title": "ログイン画面表示",
                        "trace_id": "P001",
                        "automation_status": "auto",
                        "steps": [{"action": "goto", "url": "https://e.com/login"}],
                        "locators": ["#username", "#password"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_flat_output_has_no_page_object_class(tmp_path: Path) -> None:
    spec = tmp_path / "autorun.spec.ts"
    generate_spec_ts("e.com", _candidates(tmp_path), spec, generate_page_object=False)

    assert not spec.with_name("autorun.page.ts").exists()
    assert "export class" not in spec.read_text(encoding="utf-8")


def test_page_object_mode_emits_page_class_file(tmp_path: Path) -> None:
    spec = tmp_path / "autorun.spec.ts"
    generate_spec_ts("e.com", _candidates(tmp_path), spec, generate_page_object=True)

    po = spec.with_name("autorun.page.ts")
    assert po.is_file()
    content = po.read_text(encoding="utf-8")
    assert "export class" in content
    assert "readonly page: Page" in content


def test_flat_and_po_generate_same_number_of_tests(tmp_path: Path) -> None:
    flat = tmp_path / "flat.spec.ts"
    po = tmp_path / "po.spec.ts"
    generate_spec_ts("e.com", _candidates(tmp_path), flat, generate_page_object=False)
    generate_spec_ts("e.com", _candidates(tmp_path), po, generate_page_object=True)

    assert flat.read_text().count("test(") == po.read_text().count("test(")
