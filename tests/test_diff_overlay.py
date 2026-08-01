"""スクリーンショット差分の可視化（P2-2）。

既存の比較は差分「比率」しか残しておらず、どこが変わったかは画像に残っていなかった。
save_diff_overlay がその欠けを埋める。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from diff.screenshot_diff import (  # noqa: E402
    DIFF_BOX_COLOR,
    MAX_DIFF_BOXES,
    _changed_blocks,
    save_diff_overlay,
)

Image = pytest.importorskip("PIL.Image", reason="Pillow が無い環境では画像差分を作らない")


def _png(path: Path, size=(120, 80), color=(255, 255, 255), boxes=()) -> Path:
    from PIL import Image as PILImage
    from PIL import ImageDraw

    img = PILImage.new("RGB", size, color)
    draw = ImageDraw.Draw(img)
    for box in boxes:
        draw.rectangle(box, fill=(0, 0, 0))
    img.save(path)
    return path


class TestSaveDiffOverlay:
    def test_creates_overlay_when_changed(self, tmp_path: Path) -> None:
        before = _png(tmp_path / "before.png")
        after = _png(tmp_path / "after.png", boxes=[(20, 20, 60, 50)])
        out = save_diff_overlay(before, after, tmp_path / "diff" / "P001.png")
        assert out is not None and out.is_file()

    def test_no_overlay_when_identical(self, tmp_path: Path) -> None:
        """差分が無いのに画像を作らない。作ると「変化あり」と誤読させる。"""
        before = _png(tmp_path / "before.png")
        after = _png(tmp_path / "after.png")
        assert save_diff_overlay(before, after, tmp_path / "diff" / "P001.png") is None

    def test_overlay_marks_the_changed_area_in_red(self, tmp_path: Path) -> None:
        """枠が変更領域の上に描かれること（色で確認）。"""
        before = _png(tmp_path / "before.png")
        after = _png(tmp_path / "after.png", boxes=[(20, 20, 60, 50)])
        out = save_diff_overlay(before, after, tmp_path / "diff" / "P001.png")
        assert out is not None
        from PIL import Image as PILImage

        colors = {c for _, c in PILImage.open(out).convert("RGB").getcolors(maxcolors=99999)}
        assert DIFF_BOX_COLOR in colors, "変更領域の枠色が見つからない"

    def test_overlay_is_based_on_after_image(self, tmp_path: Path) -> None:
        """枠は after 側にだけ描く。両方に描くと対応関係が追いにくい。"""
        before = _png(tmp_path / "before.png", color=(255, 255, 255))
        after = _png(tmp_path / "after.png", color=(200, 220, 255))
        out = save_diff_overlay(before, after, tmp_path / "diff" / "P001.png")
        assert out is not None
        from PIL import Image as PILImage

        colors = {c for _, c in PILImage.open(out).convert("RGB").getcolors(maxcolors=99999)}
        assert (200, 220, 255) in colors, "after 側の地色が残っていない"
        assert (255, 255, 255) not in colors, "before 側の地色が混ざっている"

    def test_masked_area_is_not_marked(self, tmp_path: Path) -> None:
        """マスク領域（時計・カルーセル等）の変化は枠にしない。"""
        before = _png(tmp_path / "before.png")
        after = _png(tmp_path / "after.png", boxes=[(20, 20, 60, 50)])
        out = save_diff_overlay(
            before, after, tmp_path / "diff" / "P001.png", masks=((10, 10, 70, 60),)
        )
        assert out is None

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        before = _png(tmp_path / "before.png")
        assert save_diff_overlay(before, tmp_path / "nope.png", tmp_path / "d.png") is None

    def test_broken_image_does_not_raise(self, tmp_path: Path) -> None:
        """壊れた画像でも比較そのものを止めない。"""
        before = _png(tmp_path / "before.png")
        broken = tmp_path / "broken.png"
        broken.write_bytes(b"not a png")
        assert save_diff_overlay(before, broken, tmp_path / "d.png") is None

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        before = _png(tmp_path / "before.png")
        after = _png(tmp_path / "after.png", boxes=[(20, 20, 60, 50)])
        out = save_diff_overlay(before, after, tmp_path / "a" / "b" / "P001.png")
        assert out is not None and out.parent.is_dir()


class TestChangedBlocks:
    def test_returns_empty_for_blank_mask(self) -> None:
        from PIL import Image as PILImage

        assert _changed_blocks(PILImage.new("L", (64, 64), 0)) == []

    def test_merges_horizontally_adjacent_blocks(self) -> None:
        """横に連続するブロックは1つの矩形にまとめる（枠が細切れだと読めない）。"""
        from PIL import Image as PILImage
        from PIL import ImageDraw

        mask = PILImage.new("L", (64, 32), 0)
        ImageDraw.Draw(mask).rectangle((0, 0, 47, 15), fill=255)
        boxes = _changed_blocks(mask, grid=16)
        assert len(boxes) == 1
        assert boxes[0][0] == 0 and boxes[0][2] == 48

    def test_does_not_merge_vertically(self) -> None:
        """縦は連結しない。無関係な変更が1つの大枠にまとまると位置が消える。"""
        from PIL import Image as PILImage
        from PIL import ImageDraw

        mask = PILImage.new("L", (32, 64), 0)
        draw = ImageDraw.Draw(mask)
        draw.rectangle((0, 0, 15, 15), fill=255)
        draw.rectangle((0, 32, 15, 47), fill=255)
        assert len(_changed_blocks(mask, grid=16)) == 2


def test_box_limit_is_defined() -> None:
    """枠の上限が定義されていること（赤で埋まって読めなくなるのを防ぐ）。"""
    assert MAX_DIFF_BOXES > 0
