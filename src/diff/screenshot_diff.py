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
    is_significant: bool  # 画素・構造の両方で有意（下記参照）
    structural_similarity: float = 1.0  # SSIM 0.0〜1.0（1.0=同一）
    # after 側に変更領域の枠を描いた画像（P2-2）。作れなかったときは空文字。
    diff_image_path: str = ""


SSIM_SIGNIFICANT_BELOW = 0.98  # 経験値: AA/フォント差はほぼ 0.99 以上に収まる


def compare_screenshots(
    before_path: Path,
    after_path: Path,
    page_id: str = "",
    threshold: float = DEFAULT_THRESHOLD,
) -> ScreenshotDiff:
    """2 枚の PNG を比較して変化率と構造的類似度（SSIM）を返す。

    画素差分率のみだとアンチエイリアス・フォントレンダリング差で恒常的に
    偽陽性が出る（ビジュアルリグレッション研究の定説）。SSIM は人間の知覚と
    相関が高いため、有意判定は「画素で閾値超過 かつ SSIMでも構造変化あり」の
    両条件にする。numpy が無い環境では従来の画素判定のみで動く。
    """
    diff_ratio = _compute_diff_ratio(before_path, after_path)
    ssim = _compute_ssim(before_path, after_path)
    pixel_significant = diff_ratio > threshold
    structurally_changed = ssim < SSIM_SIGNIFICANT_BELOW
    return ScreenshotDiff(
        page_id=page_id,
        before_path=str(before_path),
        after_path=str(after_path),
        diff_ratio=diff_ratio,
        # ssim==1.0 はフォールバック（numpy無し）か完全同一。前者では画素判定のみに従う。
        is_significant=pixel_significant and (structurally_changed or ssim >= 1.0),
        structural_similarity=ssim,
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


# 変更領域の枠色（赤）と、走査に使うグリッド幅。
# グリッドを粗くすると枠が実際の変更より大きく見え、細かくすると枠が散らばって読めない。
# 16px は detect_dynamic_regions が動的領域検出で使っている値に合わせた。
DIFF_BOX_COLOR = (225, 29, 72)
DIFF_BOX_WIDTH = 3
DIFF_GRID = 16
MAX_DIFF_BOXES = 40


def _changed_blocks(
    mask: Any, grid: int = DIFF_GRID
) -> list[tuple[int, int, int, int]]:  # PIL.Image instance
    """差分マスクを grid 単位で走査し、変化のあったブロックを矩形で返す。

    1 ピクセルずつ枠を出すと読めないため、ブロック単位に丸める。
    隣接ブロックは横方向にだけ連結する（縦にも連結すると、無関係な変更が
    1 つの大きな枠にまとまって「どこが変わったか」が消える）。
    """
    width, height = mask.size
    boxes: list[tuple[int, int, int, int]] = []
    for top in range(0, height, grid):
        run_start: int | None = None
        for left in range(0, width, grid):
            box = (left, top, min(left + grid, width), min(top + grid, height))
            changed = any(mask.crop(box).histogram()[1:])
            if changed and run_start is None:
                run_start = left
            elif not changed and run_start is not None:
                boxes.append((run_start, top, left, min(top + grid, height)))
                run_start = None
        if run_start is not None:
            boxes.append((run_start, top, width, min(top + grid, height)))
    return boxes


def save_diff_overlay(
    before_path: Path,
    after_path: Path,
    out_path: Path,
    masks: tuple[tuple[int, int, int, int], ...] = (),
    channel_tolerance: int = DEFAULT_CHANNEL_TOLERANCE,
) -> Path | None:
    """after 側に変更領域の枠を描いた画像を保存し、そのパスを返す（P2-2）。

    差分比率は既存の比較関数が算出しているが、**どこが変わったかは残していなかった**。
    テキスト中心の差分では見た目の変化が読めないため、画像として残す。

    枠は after 側にだけ描く。両方に描くと目移りして対応関係が追いにくい。
    Pillow が無い・画像が壊れている場合は None を返す（比較そのものは止めない）。
    """
    if not before_path.exists() or not after_path.exists():
        return None
    try:
        from PIL import Image, ImageChops, ImageDraw  # noqa: PLC0415
    except ImportError:
        logger.debug("Pillow が利用できないため差分画像を作りません。")
        return None
    try:
        before_img = Image.open(before_path).convert("RGB")
        after_img = Image.open(after_path).convert("RGB")
        target_size = _smaller_size(before_img.size, after_img.size)
        if before_img.size != target_size:
            before_img = before_img.resize(target_size)
        if after_img.size != target_size:
            after_img = after_img.resize(target_size)

        masked_before, masked_after = before_img, after_img
        if masks:
            masked_before, masked_after = before_img.copy(), after_img.copy()
            for target in (masked_before, masked_after):
                draw_mask = ImageDraw.Draw(target)
                for x, y, width, height in masks:
                    draw_mask.rectangle((x, y, x + width, y + height), fill=(0, 0, 0))

        diff_img = ImageChops.difference(masked_before, masked_after)
        lut = [255 if value > channel_tolerance else 0 for value in range(256)]
        bands = diff_img.split()
        mask = bands[0].point(lut)
        for band in bands[1:]:
            mask = ImageChops.lighter(mask, band.point(lut))

        boxes = _changed_blocks(mask)
        if not boxes:
            return None
        overlay = after_img.copy()
        draw = ImageDraw.Draw(overlay)
        # 枠が多すぎると画面が赤で埋まって読めない。上限を超えたら描画を打ち切り、
        # 打ち切った事実はログに残す（黙って間引くと「全部囲めている」と誤解される）。
        if len(boxes) > MAX_DIFF_BOXES:
            logger.info(
                "変更領域が %d 箇所あるため %d 箇所までを枠で示します: %s",
                len(boxes),
                MAX_DIFF_BOXES,
                after_path.name,
            )
        for box in boxes[:MAX_DIFF_BOXES]:
            draw.rectangle(box, outline=DIFF_BOX_COLOR, width=DIFF_BOX_WIDTH)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        overlay.save(out_path)
        return out_path
    except Exception as exc:
        logger.warning("差分画像を作れませんでした: %s (%s)", after_path, exc)
        return None


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


def _compute_ssim(before_path: Path, after_path: Path) -> float:
    """グレースケール・グローバル SSIM を計算する。

    scikit-image を増やさず numpy のみで、標準的な SSIM の定義
    （輝度・コントラスト・構造の積、C1=(0.01L)^2, C2=(0.03L)^2）を
    画像全体に対して求める。局所窓方式より粗いが、AA・フォント差のような
    微小変化と本物のレイアウト変化の弁別には十分効く。
    numpy / Pillow が無い・読めない場合は 1.0（判定に影響させない）を返す。
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return 1.0
    if not before_path.exists() or not after_path.exists():
        return 0.0
    try:
        before_img = Image.open(before_path).convert("L")
        after_img = Image.open(after_path).convert("L")
    except OSError:
        return 1.0
    target = _smaller_size(before_img.size, after_img.size)
    if target[0] == 0 or target[1] == 0:
        return 0.0
    if before_img.size != target:
        before_img = before_img.resize(target)
    if after_img.size != target:
        after_img = after_img.resize(target)
    x = np.asarray(before_img, dtype=np.float64)
    y = np.asarray(after_img, dtype=np.float64)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    mx, my = x.mean(), y.mean()
    vx, vy = x.var(), y.var()
    cov = ((x - mx) * (y - my)).mean()
    numerator = (2 * mx * my + c1) * (2 * cov + c2)
    denominator = (mx**2 + my**2 + c1) * (vx + vy + c2)
    if denominator == 0:
        return 1.0
    return float(max(0.0, min(1.0, numerator / denominator)))
