from __future__ import annotations

import struct
import warnings
import zlib
from pathlib import Path

import pytest

from diff.screenshot_diff import (
    ScreenshotDiff,
    compare_screenshots,
    compare_snapshot_screenshots,
)

# ─────────────────── 旧実装（getdata ベース）: パリティ比較用 ───────────────────


def _legacy_count_nonzero_pixels(diff_img: object) -> int:
    """SPEC-6-1 で置き換える前の実装（getdata + any(c != 0)）。パリティ検証専用。

    getdata() は Pillow 14 で削除予定の非推奨 API のため、pyproject.toml の
    filterwarnings（error 化）と衝突しないよう、この関数内でのみ意図的に無視する。
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        data = diff_img.getdata()  # type: ignore[attr-defined]
    return sum(1 for pixel in data if any(c != 0 for c in pixel))


# ─────────────────────── PNG 生成ヘルパー ───────────────────────


def _make_minimal_png(path: Path, width: int = 2, height: int = 2, color: int = 0) -> None:
    """最小限の PNG ファイルを生成する（PIL 不要）。"""

    def chunk(name: bytes, data: bytes) -> bytes:
        c = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", c)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = chunk(b"IHDR", ihdr_data)

    # 各行にフィルタバイト(0x00)を付ける（RGBなので1行 = 1 + width*3 バイト）
    raw_row = bytes([0]) + bytes([color, color, color] * width)
    raw_data = raw_row * height
    compressed = zlib.compress(raw_data)
    idat = chunk(b"IDAT", compressed)
    iend = chunk(b"IEND", b"")

    path.write_bytes(signature + ihdr + idat + iend)


# ─────────────────────── テスト: compare_screenshots ───────────────────────


class TestCompareScreenshots:
    def test_same_files_zero_diff(self, tmp_path: Path) -> None:
        """同じファイルを比較すると diff_ratio ≒ 0.0 になる。"""
        img = tmp_path / "screen.png"
        _make_minimal_png(img)

        result = compare_screenshots(img, img, page_id="home")

        assert result.diff_ratio == pytest.approx(0.0, abs=1e-9)
        assert result.is_significant is False
        assert result.page_id == "home"

    def test_different_files_nonzero_diff(self, tmp_path: Path) -> None:
        """異なる内容のファイルを比較すると diff_ratio > 0.0 になる。"""
        before = tmp_path / "before.png"
        after = tmp_path / "after.png"
        _make_minimal_png(before, color=0)
        _make_minimal_png(after, color=255)

        result = compare_screenshots(before, after, page_id="form")

        assert result.diff_ratio > 0.0

    def test_returns_frozen_dataclass(self, tmp_path: Path) -> None:
        """戻り値が frozen dataclass であること（変更不可）。"""
        img = tmp_path / "x.png"
        _make_minimal_png(img)

        result = compare_screenshots(img, img)

        assert isinstance(result, ScreenshotDiff)
        # frozen dataclass は直接代入で FrozenInstanceError (AttributeError サブクラス) を送出する
        with pytest.raises(AttributeError):
            result.diff_ratio = 0.5  # type: ignore[misc]

    def test_threshold_determines_is_significant(self, tmp_path: Path) -> None:
        """threshold を超えると is_significant=True になる。"""
        before = tmp_path / "b.png"
        after = tmp_path / "a.png"
        _make_minimal_png(before, color=0)
        _make_minimal_png(after, color=200)

        result_strict = compare_screenshots(before, after, threshold=0.0)
        result_loose = compare_screenshots(before, after, threshold=1.0)

        assert result_strict.is_significant is True
        assert result_loose.is_significant is False

    def test_stores_path_strings(self, tmp_path: Path) -> None:
        """before_path / after_path が文字列として保持される。"""
        img = tmp_path / "img.png"
        _make_minimal_png(img)

        result = compare_screenshots(img, img, page_id="p1")

        assert result.before_path == str(img)
        assert result.after_path == str(img)


class TestCompareScreenshotsMissingFile:
    def test_missing_before_returns_ratio_1(self, tmp_path: Path) -> None:
        """before ファイルが存在しない場合は diff_ratio=1.0 で例外を投げない。"""
        before = tmp_path / "nonexistent.png"
        after = tmp_path / "after.png"
        _make_minimal_png(after)

        result = compare_screenshots(before, after, page_id="x")

        assert result.diff_ratio == pytest.approx(1.0)
        assert result.is_significant is True

    def test_missing_after_returns_ratio_1(self, tmp_path: Path) -> None:
        """after ファイルが存在しない場合は diff_ratio=1.0 で例外を投げない。"""
        before = tmp_path / "before.png"
        after = tmp_path / "nonexistent.png"
        _make_minimal_png(before)

        result = compare_screenshots(before, after, page_id="y")

        assert result.diff_ratio == pytest.approx(1.0)

    def test_both_missing_returns_ratio_1(self, tmp_path: Path) -> None:
        """両ファイルが存在しない場合も例外を投げない。"""
        before = tmp_path / "b.png"
        after = tmp_path / "a.png"

        result = compare_screenshots(before, after, page_id="z")

        assert result.diff_ratio == pytest.approx(1.0)


# ─────────────────────── テスト: compare_snapshot_screenshots ───────────────────────


class TestCompareSnapshotScreenshots:
    def test_matches_by_page_id(self, tmp_path: Path) -> None:
        """before/after の screenshots/ に同名 PNG がある場合だけ比較する。"""
        before_dir = tmp_path / "snap_before"
        after_dir = tmp_path / "snap_after"
        (before_dir / "screenshots").mkdir(parents=True)
        (after_dir / "screenshots").mkdir(parents=True)

        # 共通ファイル
        _make_minimal_png(before_dir / "screenshots" / "login.png", color=0)
        _make_minimal_png(after_dir / "screenshots" / "login.png", color=0)

        # before のみ存在するファイル（after に対応なし）
        _make_minimal_png(before_dir / "screenshots" / "old_page.png", color=100)

        # after のみ存在するファイル（before に対応なし）
        _make_minimal_png(after_dir / "screenshots" / "new_page.png", color=200)

        results = compare_snapshot_screenshots(before_dir, after_dir)

        assert len(results) == 1
        assert results[0].page_id == "login"

    def test_empty_when_no_screenshots_dir(self, tmp_path: Path) -> None:
        """screenshots/ ディレクトリが存在しない場合は空リストを返す。"""
        before_dir = tmp_path / "before"
        after_dir = tmp_path / "after"
        before_dir.mkdir()
        after_dir.mkdir()

        results = compare_snapshot_screenshots(before_dir, after_dir)

        assert results == []

    def test_empty_when_no_common_files(self, tmp_path: Path) -> None:
        """共通ファイルがなければ空リストを返す。"""
        before_dir = tmp_path / "snap_before"
        after_dir = tmp_path / "snap_after"
        (before_dir / "screenshots").mkdir(parents=True)
        (after_dir / "screenshots").mkdir(parents=True)

        _make_minimal_png(before_dir / "screenshots" / "only_before.png")
        _make_minimal_png(after_dir / "screenshots" / "only_after.png")

        results = compare_snapshot_screenshots(before_dir, after_dir)

        assert results == []

    def test_all_matched_files_compared(self, tmp_path: Path) -> None:
        """複数の共通ファイルがすべて比較される。"""
        before_dir = tmp_path / "snap_before"
        after_dir = tmp_path / "snap_after"
        (before_dir / "screenshots").mkdir(parents=True)
        (after_dir / "screenshots").mkdir(parents=True)

        for name in ("home.png", "login.png", "form.png"):
            _make_minimal_png(before_dir / "screenshots" / name, color=0)
            _make_minimal_png(after_dir / "screenshots" / name, color=0)

        results = compare_snapshot_screenshots(before_dir, after_dir)

        assert len(results) == 3
        page_ids = {r.page_id for r in results}
        assert page_ids == {"home", "login", "form"}

    def test_custom_threshold_applied(self, tmp_path: Path) -> None:
        """カスタム threshold が各比較に適用される。"""
        before_dir = tmp_path / "snap_before"
        after_dir = tmp_path / "snap_after"
        (before_dir / "screenshots").mkdir(parents=True)
        (after_dir / "screenshots").mkdir(parents=True)

        _make_minimal_png(before_dir / "screenshots" / "p.png", color=0)
        _make_minimal_png(after_dir / "screenshots" / "p.png", color=0)

        results_strict = compare_snapshot_screenshots(before_dir, after_dir, threshold=0.0)
        results_default = compare_snapshot_screenshots(before_dir, after_dir)

        # 同一ファイルなら diff_ratio=0.0 → threshold=0.0 でも False（0 > 0 は偽）
        assert results_default[0].is_significant is False
        assert results_strict[0].is_significant is False


# ─────────────────────── PIL フォールバックのテスト ───────────────────────


class TestSizeFallback:
    def test_same_size_files_give_zero_ratio(self, tmp_path: Path) -> None:
        """同じサイズのファイルはサイズ差 0 → diff_ratio=0.0。"""
        before = tmp_path / "b.png"
        after = tmp_path / "a.png"
        content = b"X" * 100
        before.write_bytes(content)
        after.write_bytes(content)

        # PIL が使えない環境を模倣するため、_compute_size_diff_ratio を直接テスト
        from diff.screenshot_diff import _compute_size_diff_ratio

        ratio = _compute_size_diff_ratio(before, after)

        assert ratio == pytest.approx(0.0)

    def test_different_size_files_give_nonzero_ratio(self, tmp_path: Path) -> None:
        """サイズが違えば diff_ratio > 0.0。"""
        before = tmp_path / "b.bin"
        after = tmp_path / "a.bin"
        before.write_bytes(b"X" * 100)
        after.write_bytes(b"X" * 200)

        from diff.screenshot_diff import _compute_size_diff_ratio

        ratio = _compute_size_diff_ratio(before, after)

        assert ratio == pytest.approx(0.5)


# ─────────── _count_nonzero_pixels: 旧実装（getdata）とのパリティ（SPEC-6-1 AC-2） ───────────


class TestCountNonzeroPixelsParity:
    """getdata 非依存の新実装が旧実装と同一の値を返すことを検証する。"""

    def test_identical_images_zero_diff(self) -> None:
        """全一致画像なら新旧どちらも 0。"""
        Image = pytest.importorskip("PIL.Image")
        from diff.screenshot_diff import _count_nonzero_pixels

        img_a = Image.new("RGB", (4, 4), (10, 20, 30))
        img_b = Image.new("RGB", (4, 4), (10, 20, 30))
        diff_img = _pil_difference(img_a, img_b)

        assert _count_nonzero_pixels(diff_img) == _legacy_count_nonzero_pixels(diff_img) == 0

    def test_full_diff_all_pixels_counted(self) -> None:
        """全画素が反転していれば全ピクセルが数えられる。"""
        Image = pytest.importorskip("PIL.Image")
        from diff.screenshot_diff import _count_nonzero_pixels

        img_a = Image.new("RGB", (3, 3), (0, 0, 0))
        img_b = Image.new("RGB", (3, 3), (255, 255, 255))
        diff_img = _pil_difference(img_a, img_b)

        expected = 3 * 3
        assert _count_nonzero_pixels(diff_img) == _legacy_count_nonzero_pixels(diff_img) == expected

    def test_single_channel_single_pixel_diff(self) -> None:
        """1 画素・1 チャンネルだけの僅差でもその画素が数えられる
        （グレースケール変換による近似では丸めで潰れてしまうケース）。"""
        Image = pytest.importorskip("PIL.Image")
        from diff.screenshot_diff import _count_nonzero_pixels

        img_a = Image.new("RGB", (3, 3), (100, 100, 100))
        img_b = Image.new("RGB", (3, 3), (100, 100, 100))
        img_b.putpixel((1, 1), (100, 100, 101))  # B チャンネルだけ +1
        diff_img = _pil_difference(img_a, img_b)

        assert _count_nonzero_pixels(diff_img) == _legacy_count_nonzero_pixels(diff_img) == 1

    def test_rgba_alpha_only_diff_is_counted(self) -> None:
        """RGBA で alpha チャンネルのみ差分がある場合もカウントされる
        （旧 getdata の tuple 比較と同値であること）。"""
        Image = pytest.importorskip("PIL.Image")
        from diff.screenshot_diff import _count_nonzero_pixels

        img_a = Image.new("RGBA", (2, 2), (50, 60, 70, 255))
        img_b = Image.new("RGBA", (2, 2), (50, 60, 70, 255))
        img_b.putpixel((0, 0), (50, 60, 70, 200))  # alpha のみ差分
        diff_img = _pil_difference(img_a, img_b)

        assert _count_nonzero_pixels(diff_img) == _legacy_count_nonzero_pixels(diff_img) == 1


def _pil_difference(img_a: object, img_b: object) -> object:
    """ImageChops.difference のラッパー（型チェッカー向けに object 経由で呼ぶ）。"""
    from PIL import ImageChops

    return ImageChops.difference(img_a, img_b)  # type: ignore[arg-type]
