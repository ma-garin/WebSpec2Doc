"""スクリーンショットから視覚的複雑性と色の豊かさを算出する。

なぜ必要か:
    第一印象は視覚的複雑性と色の豊かさでおおよそ説明できる
    （Reinecke et al. 2013 は、この2つの知覚モデルに属性を加えて
    500ms 提示後の美的魅力度評定の分散の約半分を説明した）。
    DOM の要素数はその代理でしかない。実際に目に入るのは描画結果なので、
    描画結果そのものから測る。

指標:
    compression_ratio
        PNG 圧縮後サイズ ÷ 無圧縮サイズ。画像圧縮率は視覚的複雑性の代理として
        Tuch ら・Miniukovich らが用いている。単純な画面ほどよく圧縮される。
    edge_density
        輝度差が閾値を超える画素の割合。要素の輪郭・区切り線・文字の多さを表す。
    colorfulness
        Hasler & Süsstrunk (2003) の式。rg = R-G, yb = 0.5(R+G)-B について
        sqrt(σrg² + σyb²) + 0.3 * sqrt(μrg² + μyb²)。

限界:
    知覚モデルそのものではなく、原著で用いられた画像特徴量の再実装である。
    絶対値で美しさを主張するものではなく、**同じ画面の悪化を検知する**ために使う。
"""

from __future__ import annotations

import io
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

#: 輝度差がこれを超えた画素をエッジとみなす（0-255）。
_EDGE_THRESHOLD = 24

#: 長辺をここまで縮めてから測る。等倍だと解像度差で値がぶれる。
_NORMALIZE_LONG_EDGE = 1280


@dataclass(frozen=True)
class VisualComplexity:
    """1枚の画面についての実測値。"""

    width: int
    height: int
    compression_ratio: float
    edge_density: float
    colorfulness: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalized(image: Image.Image) -> Image.Image:
    """解像度差を吸収する。長辺が閾値以下ならそのまま。"""
    long_edge = max(image.width, image.height)
    if long_edge <= _NORMALIZE_LONG_EDGE:
        return image
    scale = _NORMALIZE_LONG_EDGE / long_edge
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def _compression_ratio(image: Image.Image) -> float:
    """PNG 圧縮後 ÷ 無圧縮。低いほど単純な画面。"""
    raw = image.width * image.height * 3
    if raw == 0:
        return 0.0
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return round(buffer.getbuffer().nbytes / raw, 4)


def _edge_density(image: Image.Image) -> float:
    """輝度差が閾値を超える画素の割合。"""
    gray = np.asarray(image.convert("L"), dtype=np.int16)
    if gray.size == 0:
        return 0.0
    dx = np.abs(np.diff(gray, axis=1))
    dy = np.abs(np.diff(gray, axis=0))
    edges = int((dx > _EDGE_THRESHOLD).sum() + (dy > _EDGE_THRESHOLD).sum())
    total = dx.size + dy.size
    return round(edges / total, 4) if total else 0.0


def _colorfulness(image: Image.Image) -> float:
    """Hasler & Süsstrunk (2003) の colorfulness。"""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float64)
    if rgb.size == 0:
        return 0.0
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    rg = r - g
    yb = 0.5 * (r + g) - b
    std = math.sqrt(float(rg.std()) ** 2 + float(yb.std()) ** 2)
    mean = math.sqrt(float(rg.mean()) ** 2 + float(yb.mean()) ** 2)
    return round(std + 0.3 * mean, 2)


def measure(image_path: str | Path) -> VisualComplexity:
    """スクリーンショット1枚を測る。"""
    with Image.open(image_path) as opened:
        image = _normalized(opened.convert("RGB"))
        return VisualComplexity(
            width=image.width,
            height=image.height,
            compression_ratio=_compression_ratio(image),
            edge_density=_edge_density(image),
            colorfulness=_colorfulness(image),
        )
