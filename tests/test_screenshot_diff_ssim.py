"""SSIM併用比較の契約。

守るべきは「微小なレンダリング差（AA相当）を有意と言わないこと」と
「本物のレイアウト変化を見逃さないこと」。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from diff.screenshot_diff import compare_screenshots


def _save(path: Path, array: np.ndarray) -> Path:
    Image.fromarray(array.astype("uint8")).save(path)
    return path


def _base(width: int = 200, height: int = 120) -> np.ndarray:
    img = np.full((height, width, 3), 255, dtype=np.uint8)
    img[20:40, 20:180] = 30  # 見出しバー
    img[60:100, 20:90] = 120  # 左カラム
    return img


def test_identical_images_are_not_significant(tmp_path: Path) -> None:
    a = _save(tmp_path / "a.png", _base())
    b = _save(tmp_path / "b.png", _base())

    result = compare_screenshots(a, b)

    assert result.structural_similarity == 1.0
    assert result.is_significant is False


def test_antialiasing_like_noise_is_not_significant(tmp_path: Path) -> None:
    """全画素に±3の微小ノイズ: 画素差分率はほぼ1.0になるがSSIMは高く保たれる。

    これが画素比較のみだと偽陽性になる、研究上の代表ケース。
    """
    base = _base()
    rng = np.random.default_rng(seed=7)
    noisy = np.clip(base.astype(int) + rng.integers(-3, 4, base.shape), 0, 255)
    a = _save(tmp_path / "a.png", base)
    b = _save(tmp_path / "b.png", noisy)

    result = compare_screenshots(a, b)

    assert result.diff_ratio > 0.5  # 画素だけ見ると「ほぼ全部変わった」
    assert result.structural_similarity > 0.98
    assert result.is_significant is False  # SSIM併用で偽陽性を抑止


def test_real_layout_change_is_significant(tmp_path: Path) -> None:
    base = _base()
    changed = _base()
    changed[60:100, 110:180] = 0  # 新しいブロックが出現
    changed[20:40, 20:180] = 255  # 見出しバーが消失
    a = _save(tmp_path / "a.png", base)
    b = _save(tmp_path / "b.png", changed)

    result = compare_screenshots(a, b)

    assert result.structural_similarity < 0.98
    assert result.is_significant is True


def test_missing_file_reports_full_difference(tmp_path: Path) -> None:
    a = _save(tmp_path / "a.png", _base())

    result = compare_screenshots(a, tmp_path / "absent.png")

    assert result.diff_ratio == 1.0
    assert result.structural_similarity == 0.0
