"""クロール中の性能観測（Core Web Vitals のラボ計測）。

計測するもの: LCP / CLS / TTFB / DOMContentLoaded / load / transferSize。
計測しないもの: INP（実ユーザー入力が必要なフィールド専用メトリクスで、
ラボ＝自動クロールでは原理的に測れない）。

主張境界: これは**この実行環境での単一試行のラボ観測値**であり、実利用者の体感
（CrUX の75パーセンタイル）でも Google の評価値でもない。試行間・環境間で変動する。
数値は「画面間の相対比較」と「悪化の検知」に使うものであり、合否判定には使わない。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

CLAIM_SCOPE = "lab_single_run_this_environment"

# 参考の目安（Google公表の good しきい値）。判定には使わず、レポートの脚注用。
LCP_GOOD_MS = 2500
CLS_GOOD = 0.1

# ナビゲーション前に登録する観測スクリプト（buffered で登録前エントリも回収）。
PERFORMANCE_INIT_SCRIPT = """
(() => {
  const store = { lcp: 0, cls: 0 };
  window.__ws2d_perf = store;
  try {
    new PerformanceObserver((list) => {
      const entries = list.getEntries();
      const last = entries[entries.length - 1];
      if (last) store.lcp = last.startTime;
    }).observe({ type: 'largest-contentful-paint', buffered: true });
  } catch (e) { /* 未対応ブラウザでは LCP を欠測 */ }
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (!entry.hadRecentInput) store.cls += entry.value;
      }
    }).observe({ type: 'layout-shift', buffered: true });
  } catch (e) { /* 未対応ブラウザでは CLS を欠測 */ }
})();
"""

_COLLECT_SCRIPT = """
(() => {
  const nav = performance.getEntriesByType('navigation')[0];
  const perf = window.__ws2d_perf || {};
  return {
    lcp_ms: perf.lcp || 0,
    cls: perf.cls || 0,
    ttfb_ms: nav ? nav.responseStart : 0,
    dcl_ms: nav ? nav.domContentLoadedEventEnd : 0,
    load_ms: nav ? nav.loadEventEnd : 0,
    transfer_bytes: nav ? (nav.transferSize || 0) : 0,
  };
})()
"""


@dataclass(frozen=True)
class PerformanceSample:
    """1画面・1試行の性能観測値。"""

    lcp_ms: float
    cls: float
    ttfb_ms: float
    dcl_ms: float
    load_ms: float
    transfer_bytes: int
    claim_scope: str = CLAIM_SCOPE

    def to_dict(self) -> dict[str, Any]:
        return {
            "lcp_ms": round(self.lcp_ms, 1),
            "cls": round(self.cls, 4),
            "ttfb_ms": round(self.ttfb_ms, 1),
            "dcl_ms": round(self.dcl_ms, 1),
            "load_ms": round(self.load_ms, 1),
            "transfer_bytes": self.transfer_bytes,
            "claim_scope": self.claim_scope,
        }


def install_performance_observers(page: Any) -> None:
    """ナビゲーション前に観測スクリプトを登録する。失敗してもクロールは続行。"""
    try:
        page.add_init_script(PERFORMANCE_INIT_SCRIPT)
    except Exception:  # noqa: BLE001 - 観測はクロール本体を妨げない
        logger.debug("性能観測スクリプトの登録に失敗", exc_info=True)


def collect_performance(page: Any) -> PerformanceSample | None:
    """ページ読み込み後に観測値を回収する。計測不能なら None（欠測を偽装しない）。"""
    try:
        raw = page.evaluate(_COLLECT_SCRIPT)
    except Exception:  # noqa: BLE001 - 観測はクロール本体を妨げない
        logger.debug("性能観測値の回収に失敗", exc_info=True)
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return PerformanceSample(
            lcp_ms=float(raw.get("lcp_ms", 0) or 0),
            cls=float(raw.get("cls", 0) or 0),
            ttfb_ms=float(raw.get("ttfb_ms", 0) or 0),
            dcl_ms=float(raw.get("dcl_ms", 0) or 0),
            load_ms=float(raw.get("load_ms", 0) or 0),
            transfer_bytes=int(raw.get("transfer_bytes", 0) or 0),
        )
    except (TypeError, ValueError):
        return None
