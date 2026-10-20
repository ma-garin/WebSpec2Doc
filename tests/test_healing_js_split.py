"""System05: healing.js / healing-reports.js を責務ごとに分けた後の結線（読み込み順・ファイル間の参照・大きさ）と deep link。

分割は本文を変えずに行い、ファイル間の共有は window.HealingApp / window.HealingReports（HL）だけにしている。
他ファイルの宣言を使うのに転送関数を書き忘れると、その操作を押した時に初めて ReferenceError になる。
ここで静的に全ファイルを突き合わせて、押す前に見つける。
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS_DIR = ROOT / "static/js"
SETS = {
    # 名前空間: (読み込み順, それを読むテンプレート)
    "HealingApp": (["healing-core", "healing-projects", "healing-report", "healing-run",
                    "healing-actions", "healing-history", "healing"], ["templates/healing.html"]),
    "HealingReports": (["healing-reports-core", "healing-reports-list", "healing-reports-doc",
                        "healing-reports-bundle", "healing-reports"],
                       ["templates/healing_reports.html", "templates/healing_report.html"]),
}


def _read(name: str) -> str:
    return (JS_DIR / f"{name}.js").read_text(encoding="utf-8")


def _strip(src: str) -> str:
    """文字列・コメントの中の語を拾わないよう、ざっくり取り除く。"""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"(?m)^\s*//.*$", "", src)
    src = re.sub(r"'(?:\\.|[^'\\\n])*'", "''", src)
    return re.sub(r'"(?:\\.|[^"\\\n])*"', '""', src)


def _local_names(src: str) -> set[str]:
    names = set(re.findall(r"(?m)^  function ([\w$]+)\(", src))
    return names | set(re.findall(r"(?m)^  var ([\w$]+) =", src))


@pytest.mark.parametrize("ns", list(SETS))
def test_templates_load_split_files_in_order_and_entry_last(ns):
    order, templates = SETS[ns]
    for tpl in templates:
        html = (ROOT / tpl).read_text(encoding="utf-8")
        found = [n for n in re.findall(r"filename='js/(healing[\w-]*)\.js'", html) if n in order]
        assert found == order, tpl


@pytest.mark.parametrize("ns", list(SETS))
def test_each_file_is_small_and_shares_only_its_namespace(ns):
    for name in SETS[ns][0]:
        src = _read(name)
        assert len(src.splitlines()) <= 1000, name
        assert f"window.{ns} = window.{ns} || {{}}" in src, name
        assert "'use strict';" in src, name


@pytest.mark.parametrize("ns", list(SETS))
def test_every_cross_file_name_is_forwarded(ns):
    files = {name: _read(name) for name in SETS[ns][0]}
    exported: dict[str, str] = {}
    for name, src in files.items():
        for sym in re.findall(r"(?m)^  HL\.([\w$]+) = [\w$]+;$", src):
            exported[sym] = name
    missing = []
    for name, src in files.items():
        body = _strip(src)
        local = _local_names(src)
        for sym, owner in exported.items():
            if owner == name or sym in local:
                continue
            # $ は DOM 参照の表（$['hl-...']）。正規表現の行末 $ と区別するため [ が続く時だけ数える
            pattern = r"(?<![\w$.\\])\$\[" if sym == "$" else r"(?<![\w$.])" + re.escape(sym) + r"(?![\w$])"
            if re.search(pattern, body):
                missing.append(f"{name}.js uses {sym} (from {owner}.js) without forwarding")
    assert not missing, "\n".join(missing)


@pytest.mark.parametrize("ns", list(SETS))
def test_initialised_exactly_once_by_the_entry_file(ns):
    order = SETS[ns][0]
    # 初期化の登録はちょうど 1 回（2 回登録するとボタンの処理が二重に結び付く）
    assert sum(_read(n).count("'DOMContentLoaded'") for n in order) == 1
    assert "'DOMContentLoaded'" in _read(order[-1])


def test_settings_entry_sets_admin_flag_through_owner():
    src = _read("healing")
    assert "setAdminFlag(" in src and "IS_ADMIN = " not in src


@pytest.mark.skipif(shutil.which("node") is None, reason="node が無いので構文検査を省略")
def test_split_files_parse():
    for order, _ in SETS.values():
        for name in order:
            subprocess.run(["node", "--check", str(JS_DIR / f"{name}.js")], check=True)


def test_orchestration_links_healing_with_site_and_reports_page_does_not_guess():
    from web.services.orchestration.home_summary import _links

    assert _links("127.0.0.1:8767", True)["s05"] == "/healing?site=127.0.0.1:8767"
    js = _read("healing-reports-list")
    assert "function applySite(" in js and "hits.length === 1" in js
    assert "推測では選" in js
    assert 'id="hl-site-notice"' in (ROOT / "templates/healing_reports.html").read_text(encoding="utf-8")
