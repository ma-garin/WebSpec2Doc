from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.05
DEFAULT_CHANNEL_TOLERANCE = 24
_DYNAMIC_REGION_GRID_PX = 16
_THRESHOLD_ENV = "WEBSPEC2DOC_COMPARE_DIFF_THRESHOLD"
_TOLERANCE_ENV = "WEBSPEC2DOC_COMPARE_DIFF_TOLERANCE"


def threshold_from_env(default: float = DEFAULT_THRESHOLD) -> float:
    """環境変数から画像差分の有意閾値を取得する（不正値・未設定は既定値）。"""
    return _float_from_env(_THRESHOLD_ENV, default)


def channel_tolerance_from_env(default: int = DEFAULT_CHANNEL_TOLERANCE) -> int:
    """環境変数から画素値ゆらぎ許容量を取得する（不正値・未設定は既定値）。"""
    return int(_float_from_env(_TOLERANCE_ENV, float(default)))


def _float_from_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s の値が不正です（%r）。既定値 %s を使用します。", name, raw, default)
        return default
    if value < 0:
        logger.warning(
            "%s に負値が指定されました（%s）。既定値 %s を使用します。", name, value, default
        )
        return default
    return value


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


def compare_screenshots_masked(
    before_path: Path,
    after_path: Path,
    page_id: str = "",
    threshold: float = DEFAULT_THRESHOLD,
    masks: tuple[tuple[int, int, int, int], ...] = (),
    channel_tolerance: int = DEFAULT_CHANNEL_TOLERANCE,
) -> ScreenshotDiff:
    """現新比較用: マスク領域を塗り潰し・画素値ゆらぎを許容して 2 枚の PNG を比較する。

    既存の ``compare_screenshots`` のシグネチャ・戻り値・挙動は変更しない
    （マスクなし・ゆらぎ 0 相当で呼び出せば同等の結果になる拡張版）。
    masks は (x, y, width, height) のタプル列で、時計・カルーセル等の動的領域や
    ``--compare-mask-selector`` で指定した要素の bounding_box を塗り潰して比較する。
    channel_tolerance はアンチエイリアスによる画素値のゆらぎを同一扱いにする閾値。
    """
    diff_ratio = _compute_diff_ratio_masked(before_path, after_path, masks, channel_tolerance)
    return ScreenshotDiff(
        page_id=page_id,
        before_path=str(before_path),
        after_path=str(after_path),
        diff_ratio=diff_ratio,
        is_significant=diff_ratio > threshold,
    )


def _compute_diff_ratio_masked(
    before_path: Path,
    after_path: Path,
    masks: tuple[tuple[int, int, int, int], ...],
    channel_tolerance: int,
) -> float:
    if not before_path.exists() or not after_path.exists():
        logger.warning("ファイルが見つかりません: %s / %s", before_path, after_path)
        return 1.0
    try:
        from PIL import Image, ImageChops, ImageDraw  # noqa: PLC0415

        return _compute_pixel_diff_ratio_masked(
            before_path, after_path, masks, channel_tolerance, Image, ImageChops, ImageDraw
        )
    except ImportError:
        logger.debug("Pillow が利用できません。ファイルサイズ比較でフォールバックします。")
        return _compute_size_diff_ratio(before_path, after_path)


def _compute_pixel_diff_ratio_masked(
    before_path: Path,
    after_path: Path,
    masks: tuple[tuple[int, int, int, int], ...],
    channel_tolerance: int,
    Image: Any,  # PIL.Image module
    ImageChops: Any,  # PIL.ImageChops module
    ImageDraw: Any,  # PIL.ImageDraw module
) -> float:
    """マスク適用・ゆらぎ許容ありのピクセルレベル差分比率を計算する。

    numpy は仕様外の新規依存として持ち込まない（罠 §8）。Pillow の split/point/
    ImageChops のみで RGB のまま比較する（getdata 非依存・Pillow 14 対応）。
    """
    before_img = Image.open(before_path).convert("RGB")
    after_img = Image.open(after_path).convert("RGB")

    target_size = _smaller_size(before_img.size, after_img.size)
    if before_img.size != target_size:
        before_img = before_img.resize(target_size)
    if after_img.size != target_size:
        after_img = after_img.resize(target_size)

    if masks:
        before_img = before_img.copy()
        after_img = after_img.copy()
        before_draw = ImageDraw.Draw(before_img)
        after_draw = ImageDraw.Draw(after_img)
        for x, y, width, height in masks:
            box = (x, y, x + width, y + height)
            before_draw.rectangle(box, fill=(0, 0, 0))
            after_draw.rectangle(box, fill=(0, 0, 0))

    diff_img = ImageChops.difference(before_img, after_img)
    diff_pixels = _count_significant_pixels(diff_img, channel_tolerance)
    total_pixels = target_size[0] * target_size[1]
    if total_pixels == 0:
        return 0.0
    return diff_pixels / total_pixels


def _count_significant_pixels(diff_img: Any, channel_tolerance: int) -> int:  # PIL.Image instance
    """差分イメージのうち、画素値差が channel_tolerance を超えるピクセル数を返す

    （getdata 非依存・Pillow 14 対応。_count_nonzero_pixels と同様に
    split/point/ImageChops.lighter/histogram のみで実装する）。
    """
    from PIL import ImageChops  # noqa: PLC0415

    lut = [255 if value > channel_tolerance else 0 for value in range(256)]
    bands = diff_img.split()
    mask = bands[0].point(lut)
    for band in bands[1:]:
        mask = ImageChops.lighter(mask, band.point(lut))
    return sum(mask.histogram()[1:])


def detect_dynamic_regions(
    page: Page, interval_sec: float = 1.0
) -> tuple[tuple[int, int, int, int], ...]:
    """同一ページを間隔をおいて 2 枚撮影し、動的領域（時計・カルーセル等）を検出する。

    16px グリッドで差分が出たブロックをマスク候補として返す（(x, y, width, height) 群）。
    現行側クロール中の実ブラウザ Page に対してのみ実行できる（撮影は追加 1 枚）。
    撮影に失敗した場合は空タプルを返す（動的領域なしとして扱い、比較自体は継続する）。
    """
    try:
        first = page.screenshot()
        page.wait_for_timeout(int(interval_sec * 1000))
        second = page.screenshot()
    except Exception as exc:  # noqa: BLE001  # Playwright の実行時エラーは種類を問わず継続する
        logger.warning("動的領域検出用の撮影に失敗しました: %s", exc)
        return ()
    return _diff_grid_blocks(first, second)


def _diff_grid_blocks(first_png: bytes, second_png: bytes) -> tuple[tuple[int, int, int, int], ...]:
    try:
        from PIL import Image, ImageChops  # noqa: PLC0415
    except ImportError:
        logger.debug("Pillow が利用できないため動的領域検出をスキップします。")
        return ()

    first_img = Image.open(io.BytesIO(first_png)).convert("RGB")
    second_img = Image.open(io.BytesIO(second_png)).convert("RGB")
    if first_img.size != second_img.size:
        logger.debug("2 枚の撮影サイズが一致しないため動的領域検出をスキップします。")
        return ()

    width, height = first_img.size
    diff_img = ImageChops.difference(first_img, second_img)
    regions: list[tuple[int, int, int, int]] = []
    for top in range(0, height, _DYNAMIC_REGION_GRID_PX):
        for left in range(0, width, _DYNAMIC_REGION_GRID_PX):
            right = min(left + _DYNAMIC_REGION_GRID_PX, width)
            bottom = min(top + _DYNAMIC_REGION_GRID_PX, height)
            block = diff_img.crop((left, top, right, bottom))
            if _count_nonzero_pixels(block) > 0:
                regions.append((left, top, right - left, bottom - top))
    return tuple(regions)
