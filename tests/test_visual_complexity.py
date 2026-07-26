"""視覚的複雑性の算出（web/services/visual_complexity.py）の単体テスト。

指標が「複雑なほど大きい」向きに動くことを、既知の画像で固定する。
向きが逆になると回帰検知が無意味になるため。
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from web.services.visual_complexity import measure


@pytest.fixture()
def plain(tmp_path):
    """単色。最も単純な画面。"""
    path = tmp_path / "plain.png"
    Image.new("RGB", (400, 300), (250, 250, 250)).save(path)
    return path


@pytest.fixture()
def busy(tmp_path):
    """細かい市松模様。輪郭が多い＝複雑。"""
    path = tmp_path / "busy.png"
    arr = np.indices((300, 400)).sum(axis=0) % 2
    rgb = np.stack([arr * 255] * 3, axis=-1).astype(np.uint8)
    Image.fromarray(rgb).save(path)
    return path


@pytest.fixture()
def colorful(tmp_path):
    """赤〜青の階調。色の振れ幅が大きい。"""
    path = tmp_path / "colorful.png"
    x = np.linspace(0, 255, 400, dtype=np.uint8)
    rgb = np.zeros((300, 400, 3), dtype=np.uint8)
    rgb[:, :, 0] = x[None, :]
    rgb[:, :, 2] = 255 - x[None, :]
    Image.fromarray(rgb).save(path)
    return path


class TestComplexityDirection:
    def test_busy_image_has_more_edges_than_plain(self, plain, busy) -> None:
        assert measure(busy).edge_density > measure(plain).edge_density

    def test_busy_image_compresses_worse_than_plain(self, plain, busy) -> None:
        assert measure(busy).compression_ratio > measure(plain).compression_ratio

    def test_colorful_image_scores_higher_than_gray(self, plain, colorful) -> None:
        assert measure(colorful).colorfulness > measure(plain).colorfulness

    def test_plain_image_is_near_zero(self, plain) -> None:
        m = measure(plain)
        assert m.edge_density == pytest.approx(0.0, abs=0.001)
        assert m.colorfulness == pytest.approx(0.0, abs=0.5)


class TestNormalization:
    def test_large_image_is_scaled_down(self, tmp_path) -> None:
        """解像度差で値がぶれないよう、長辺を正規化する。"""
        path = tmp_path / "huge.png"
        Image.new("RGB", (3000, 2000), (200, 200, 200)).save(path)
        m = measure(path)
        assert max(m.width, m.height) == 1280

    def test_small_image_is_left_alone(self, tmp_path) -> None:
        path = tmp_path / "small.png"
        Image.new("RGB", (320, 240), (200, 200, 200)).save(path)
        m = measure(path)
        assert (m.width, m.height) == (320, 240)


class TestSerialization:
    def test_to_dict_exposes_all_metrics(self, plain) -> None:
        keys = set(measure(plain).to_dict())
        assert keys == {"width", "height", "compression_ratio", "edge_density", "colorfulness"}
