"""レイアウト故障検知（ReDeCheck型・幾何情報ベース）。

マルチビューポート機能（P1-9）は「項目の有無」しか比較していない。ここでは
要素のバウンディングボックス（座標・大きさ）を使い、ReDeCheck の5類型のうち
機械判定の確実な2種を検出する:
- Viewport Protrusion: 要素が画面幅からはみ出す（横スクロールの発生）
- Element Collision  : インタラクティブ要素同士が重なる

主張境界: 観測した幾何情報の記録であり、それが不具合であることは主張しない
（レスポンシブ設計として意図的な重なり・折り返しと区別できないため）。
"""

from __future__ import annotations

from typing import Any

CLAIM_SCOPE = "observed_geometry_only"

CLAIM_NOTICE = (
    "本結果は観測した要素の幾何情報の記録であり、"
    "はみ出し・重なりが不具合であることを判定するものではない。"
)

# AA や border 由来の 1-2px の接触を故障と呼ばないための下限。
COLLISION_MIN_OVERLAP_PX = 4
PROTRUSION_TOLERANCE_PX = 2


def detect_viewport_protrusion(
    boxes: list[dict[str, Any]], viewport_width: int
) -> list[dict[str, Any]]:
    """要素が画面幅から右へはみ出しているものを検出する。"""
    protrusions: list[dict[str, Any]] = []
    limit = viewport_width + PROTRUSION_TOLERANCE_PX
    for box in boxes:
        right = float(box.get("x", 0)) + float(box.get("w", 0))
        if right > limit and float(box.get("w", 0)) > 0:
            protrusions.append(
                {
                    "selector": str(box.get("selector", "")),
                    "right_edge": round(right, 1),
                    "viewport_width": viewport_width,
                    "overflow_px": round(right - viewport_width, 1),
                }
            )
    return protrusions


def detect_element_collision(boxes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """インタラクティブ要素同士の重なりを検出する（包含関係は除外）。"""
    collisions: list[dict[str, Any]] = []
    interactive = [b for b in boxes if b.get("interactive")]
    for i in range(len(interactive)):
        for j in range(i + 1, len(interactive)):
            a, b = interactive[i], interactive[j]
            if _contains(a, b) or _contains(b, a):
                continue  # 親子の包含は正常
            dx, dy = _overlap_extent(a, b)
            # 両軸とも下限を超えて重なる場合のみ故障とする。
            # 1-2px の辺接触（AA/border 由来）を除外するため面積でなく重なり幅で判定。
            if dx >= COLLISION_MIN_OVERLAP_PX and dy >= COLLISION_MIN_OVERLAP_PX:
                collisions.append(
                    {
                        "selector_a": str(a.get("selector", "")),
                        "selector_b": str(b.get("selector", "")),
                        "overlap_px2": round(dx * dy, 1),
                    }
                )
    return collisions


def build_layout_failure_report(
    observations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """ビューポート名 -> {boxes, viewport_width, horizontal_overflow} から報告を作る。"""
    per_viewport: list[dict[str, Any]] = []
    total_protrusions = 0
    total_collisions = 0
    for name in sorted(observations):
        obs = observations[name]
        boxes = obs.get("boxes", [])
        width = int(obs.get("viewport_width", 0))
        protrusions = detect_viewport_protrusion(boxes, width) if width else []
        collisions = detect_element_collision(boxes)
        total_protrusions += len(protrusions)
        total_collisions += len(collisions)
        per_viewport.append(
            {
                "viewport": name,
                "viewport_width": width,
                "horizontal_overflow": bool(obs.get("horizontal_overflow")),
                "protrusions": protrusions,
                "collisions": collisions,
            }
        )
    return {
        "meta": {"claim_scope": CLAIM_SCOPE, "claim_notice": CLAIM_NOTICE},
        "viewports": per_viewport,
        "summary": {
            "protrusions": total_protrusions,
            "collisions": total_collisions,
        },
    }


# ─────────────────── 幾何 ───────────────────


def _overlap_extent(a: dict[str, Any], b: dict[str, Any]) -> tuple[float, float]:
    """2矩形の x/y 各軸の重なり幅（負なら0）。"""
    ax, ay, aw, ah = _xywh(a)
    bx, by, bw, bh = _xywh(b)
    dx = min(ax + aw, bx + bw) - max(ax, bx)
    dy = min(ay + ah, by + bh) - max(ay, by)
    return (max(0.0, dx), max(0.0, dy))


def _contains(outer: dict[str, Any], inner: dict[str, Any]) -> bool:
    ox, oy, ow, oh = _xywh(outer)
    ix, iy, iw, ih = _xywh(inner)
    return ox <= ix and oy <= iy and ox + ow >= ix + iw and oy + oh >= iy + ih


def _xywh(box: dict[str, Any]) -> tuple[float, float, float, float]:
    return (
        float(box.get("x", 0)),
        float(box.get("y", 0)),
        float(box.get("w", 0)),
        float(box.get("h", 0)),
    )
