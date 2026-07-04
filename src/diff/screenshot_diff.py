from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.05


@dataclass(frozen=True)
class ScreenshotDiff:
    page_id: str
    before_path: str
    after_path: str
    diff_ratio: float  # 変化したピクセルの割合 0.0〜1.0
    is_significant: bool  # diff_ratio > threshold


def compare_screenshots(
    before_path: Path,
    after_path: Path,
    page_id: str = "",
    threshold: float = DEFAULT_THRESHOLD,
) -> ScreenshotDiff:
    """2 枚の PNG を比較して変化率を返す。
    Pillow が利用できない場合はファイルサイズ比較でフォールバックする。"""
    diff_ratio = _compute_diff_ratio(before_path, after_path)
    return ScreenshotDiff(
        page_id=page_id,
        before_path=str(before_path),
        after_path=str(after_path),
        diff_ratio=diff_ratio,
        is_significant=diff_ratio > threshold,
    )


def compare_snapshot_screenshots(
    before_dir: Path,
    after_dir: Path,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[ScreenshotDiff]:
    """2 つのスナップショットディレクトリの screenshots/ フォルダを比較する。"""
    before_ss = before_dir / "screenshots"
    after_ss = after_dir / "screenshots"

    if not before_ss.is_dir() or not after_ss.is_dir():
        logger.warning("screenshots ディレクトリが見つかりません: %s / %s", before_ss, after_ss)
        return []

    before_files = {p.name: p for p in before_ss.glob("*.png")}
    after_files = {p.name: p for p in after_ss.glob("*.png")}
    common = sorted(before_files.keys() & after_files.keys())

    results: list[ScreenshotDiff] = []
    for name in common:
        page_id = Path(name).stem
        results.append(
            compare_screenshots(before_files[name], after_files[name], page_id, threshold)
        )
    return results


def _compute_diff_ratio(before_path: Path, after_path: Path) -> float:
    """差分比率を計算する。Pillow が使えない場合はサイズ比較でフォールバックする。"""
    if not before_path.exists() or not after_path.exists():
        logger.warning("ファイルが見つかりません: %s / %s", before_path, after_path)
        return 1.0

    try:
        from PIL import Image, ImageChops  # noqa: PLC0415

        return _compute_pixel_diff_ratio(before_path, after_path, Image, ImageChops)
    except ImportError:
        logger.debug("Pillow が利用できません。ファイルサイズ比較でフォールバックします。")
        return _compute_size_diff_ratio(before_path, after_path)


def _compute_pixel_diff_ratio(
    before_path: Path,
    after_path: Path,
    Image: Any,  # PIL.Image module
    ImageChops: Any,  # PIL.ImageChops module
) -> float:
    """Pillow を使ったピクセルレベルの差分比率を計算する。"""
    before_img = Image.open(before_path).convert("RGB")
    after_img = Image.open(after_path).convert("RGB")

    target_size = _smaller_size(before_img.size, after_img.size)
    if before_img.size != target_size:
        before_img = before_img.resize(target_size)
    if after_img.size != target_size:
        after_img = after_img.resize(target_size)

    diff_img = ImageChops.difference(before_img, after_img)
    diff_pixels = _count_nonzero_pixels(diff_img)
    total_pixels = target_size[0] * target_size[1]
    if total_pixels == 0:
        return 0.0
    return diff_pixels / total_pixels


def _count_nonzero_pixels(diff_img: Any) -> int:  # PIL.Image instance
    """差分イメージの非ゼロピクセル数を返す（getdata 非依存・Pillow 14 対応）。

    帯（RGB/RGBA の各チャンネル）を ImageChops.lighter で畳み込み、
    「いずれかのチャンネルが非ゼロのピクセル数」をヒストグラムで数える。
    """
    from PIL import ImageChops  # noqa: PLC0415

    bands = diff_img.split()
    mask = bands[0]
    for band in bands[1:]:
        mask = ImageChops.lighter(mask, band)
    return sum(mask.histogram()[1:])


def _compute_size_diff_ratio(before_path: Path, after_path: Path) -> float:
    """ファイルサイズの差を使った粗い近似差分比率を返す。"""
    size1 = before_path.stat().st_size
    size2 = after_path.stat().st_size
    max_size = max(size1, size2)
    if max_size == 0:
        return 0.0
    return abs(size1 - size2) / max_size


def _smaller_size(size1: tuple[int, int], size2: tuple[int, int]) -> tuple[int, int]:
    """2 つのサイズのうち、面積の小さい方を返す。"""
    if size1[0] * size1[1] <= size2[0] * size2[1]:
        return size1
    return size2
