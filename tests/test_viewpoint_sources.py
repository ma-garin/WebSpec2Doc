"""観点の根拠を出典へ解決する（data/viewpoint_sources.json）。

観点の standards は「ISO/IEC 25010 機能正確性」のように規格名＋条項で書かれている。
利用者が原典を確かめられないと、観点は根拠のない指示書になる。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.services.viewpoint_sources import list_sources, resolve  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _all_standards() -> list[tuple[str, str, str]]:
    """同梱テンプレートが使っている standards を (template, 観点名, standards) で返す。"""
    out = []
    for path in sorted((ROOT / "data" / "viewpoint_templates").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for folder in data.get("folders", []):
            for item in folder.get("items", []):
                std = str(item.get("standards", "")).strip()
                if std:
                    out.append((path.stem, item["name"], std))
    return out


class TestCatalog:
    def test_sources_are_loaded(self) -> None:
        sources = list_sources()
        assert len(sources) >= 20, "出典カタログが少なすぎる"

    def test_required_fields(self) -> None:
        for s in list_sources():
            for key in ("id", "prefix", "title", "issuer", "level", "url"):
                assert s.get(key), f"{s.get('id')}: {key} が空"

    def test_urls_are_http(self) -> None:
        """href に入るため、http(s) 以外を持たせない。"""
        for s in list_sources():
            assert s["url"].startswith(("http://", "https://")), f"{s['id']}: {s['url']}"

    def test_ids_are_unique(self) -> None:
        ids = [s["id"] for s in list_sources()]
        assert len(ids) == len(set(ids)), "出典 id が重複"


class TestResolve:
    def test_resolves_with_clause(self) -> None:
        """条項部分を clause として切り出すこと（原典のどこを見るかを示すため）。"""
        got = resolve("OWASP ASVS 4.1")
        assert got is not None
        assert got["id"] == "owasp_asvs"
        assert got["clause"] == "4.1"
        assert got["url"].startswith("https://")

    def test_longer_prefix_wins(self) -> None:
        """接頭辞が似る規格で誤った出典を返さないこと。

        「ISO/IEC 25010」と「ISO/IEC 27001」は短い方が先に当たると取り違える。
        """
        assert resolve("ISO/IEC 25010 機能正確性")["id"] == "iso25010"
        assert resolve("ISO/IEC 27001 A.8")["id"] == "iso27001"
        assert resolve("ISO/IEC/IEEE 29119-3")["id"] == "iso29119"

    def test_unknown_returns_none(self) -> None:
        assert resolve("存在しない規格 1.2") is None

    def test_empty_returns_none(self) -> None:
        assert resolve("") is None
        assert resolve("   ") is None


class TestCoverage:
    def test_every_standards_resolves(self) -> None:
        """同梱テンプレートの standards がすべて出典へ解決できること。

        解決できないものが混ざると、画面に「出典カタログに登録がありません」が出る。
        観点を足すときは出典も足す。
        """
        unresolved = [
            f"{tmpl}: {name} → {std}"
            for tmpl, name, std in _all_standards()
            if resolve(std) is None
        ]
        assert not unresolved, "出典を引けない standards がある:\n" + "\n".join(unresolved[:10])
