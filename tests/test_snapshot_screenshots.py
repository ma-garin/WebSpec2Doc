"""スナップショットのスクリーンショット世代保存。

screenshots/ は再クロールのたびに上書きされる。JSON だけを世代保存していたため、
古い世代のスナップショットも最新の画像を指しており、現新比較で before/after を
並べても同じ画像になっていた。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crawler.page_crawler import PageData  # noqa: E402
from diff.snapshot import save_snapshot, snapshot_shots_dir  # noqa: E402


def _page(url: str, shot: Path | None) -> PageData:
    return PageData(
        url=url,
        title="T",
        headings=("Heading",),
        links=(),
        forms=(),
        screenshot_path=str(shot) if shot else None,
    )


def _shot(path: Path, content: bytes = b"first") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _saved_paths(snapshot_path: Path) -> list[str | None]:
    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    return [p.get("screenshot_path") for p in data]


class TestScreenshotArchiving:
    def test_screenshot_is_copied_into_a_generation_folder(self, tmp_path: Path) -> None:
        shot = _shot(tmp_path / "screenshots" / "P001.png")
        snapshot = save_snapshot([_page("https://x/", shot)], tmp_path)

        shots_dir = snapshot_shots_dir(snapshot)
        assert (shots_dir / "P001.png").is_file()
        assert _saved_paths(snapshot) == [str(shots_dir / "P001.png")]

    def test_two_generations_keep_their_own_image(self, tmp_path: Path, monkeypatch) -> None:
        """再クロールで上書きされても、前の世代の画像が残ること（これが本題）。

        タイムスタンプは固定する。同一秒に 2 回保存するとファイル名が衝突するのは
        JSON 側も同じ既存挙動で、ここで見たいのは世代が分かれたときの保持。
        """
        import diff.snapshot as snapshot_module

        stamps = iter(["20260801-143846", "20260801-143907"])
        monkeypatch.setattr(snapshot_module, "_timestamp", lambda: next(stamps))

        live = tmp_path / "screenshots" / "P001.png"
        _shot(live, b"old-capture")
        first = save_snapshot([_page("https://x/", live)], tmp_path)

        _shot(live, b"new-capture")  # 再クロールで上書き
        second = save_snapshot([_page("https://x/", live)], tmp_path)

        first_path = Path(_saved_paths(first)[0] or "")
        second_path = Path(_saved_paths(second)[0] or "")
        assert first_path != second_path
        assert first_path.read_bytes() == b"old-capture"
        assert second_path.read_bytes() == b"new-capture"

    def test_page_without_screenshot_is_unchanged(self, tmp_path: Path) -> None:
        snapshot = save_snapshot([_page("https://x/", None)], tmp_path)
        assert _saved_paths(snapshot) == [None]

    def test_missing_source_keeps_original_path(self, tmp_path: Path) -> None:
        """元画像が消えていても保存は止めない（比較の材料が減るだけ）。"""
        missing = tmp_path / "screenshots" / "gone.png"
        snapshot = save_snapshot([_page("https://x/", missing)], tmp_path)
        assert _saved_paths(snapshot) == [str(missing)]

    def test_no_shots_dir_when_nothing_to_copy(self, tmp_path: Path) -> None:
        snapshot = save_snapshot([_page("https://x/", None)], tmp_path)
        assert not snapshot_shots_dir(snapshot).exists()

    def test_shots_dir_name_matches_snapshot_stem(self, tmp_path: Path) -> None:
        """対応関係をファイル名だけで追えること。"""
        shot = _shot(tmp_path / "screenshots" / "P001.png")
        snapshot = save_snapshot([_page("https://x/", shot)], tmp_path)
        assert snapshot_shots_dir(snapshot).name == f"{snapshot.stem}-shots"
        assert snapshot_shots_dir(snapshot).parent == snapshot.parent
