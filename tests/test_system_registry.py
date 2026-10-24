"""System 一覧の正本（web/system_registry.py）と、それを使う画面の整合テスト。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as appmod  # noqa: E402
from web.system_registry import SYSTEMS, system  # noqa: E402

H = {"Host": "127.0.0.1"}


def _client():
    return appmod.app.test_client()


def test_registry_numbers_unique():
    numbers = [s.number for s in SYSTEMS if s.number]
    assert len(numbers) == len(set(numbers))
    assert len({s.key for s in SYSTEMS}) == len(SYSTEMS)


def test_systems_page_card_count_matches_registry():
    html = _client().get("/systems", headers=H).get_data(as_text=True)
    # 認証オフ（auth_user なし）では管理者専用も含め全件並ぶ
    assert len(re.findall(r'<a class="syscard ', html)) == len(SYSTEMS)
    for s in SYSTEMS:
        assert f">{s.label}</span>" in html
        assert s.name in html


def test_preview_system_marked_as_trial():
    html = _client().get("/systems", headers=H).get_data(as_text=True)
    assert "試作" in html
    assert "未到達 Activity" not in html
    assert system("app").is_preview
    assert not any(s.is_preview for s in SYSTEMS if s.key != "app")


def test_cli_page_uses_registry_numbers():
    html = _client().get("/cli", headers=H).get_data(as_text=True)
    assert f'<span>{system("cli").label} {system("cli").name}</span>' in html
    assert system("cli").label == "System 04"
    assert system("autorun").number == "03"
    assert f"{system('autorun').number} AutoRun" in html


def test_no_hardcoded_system_count_in_templates():
    pat = re.compile(r"[0-9０-９一二三四五六七八九十]+\s*つ(の|は)(独立した)?(システム|System)")
    for f in (ROOT / "templates").rglob("*.html"):
        text = f.read_text(encoding="utf-8")
        assert not pat.search(text), f"{f.name} に System 数の固定文言がある"


def test_switcher_names_match_registry():
    c = _client()
    assert system("batch").name in c.get("/batch-test", headers=H).get_data(as_text=True)
    assert system("backend").name in c.get("/backend-test", headers=H).get_data(as_text=True)


def test_test_automation_requires_testlab_permission(monkeypatch):
    from web.routes import pages

    monkeypatch.setattr(pages, "_may_use_testlab", lambda: False)
    assert _client().get("/test-automation", headers=H).status_code == 403
