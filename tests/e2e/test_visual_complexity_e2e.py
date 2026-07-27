"""視覚的複雑性の実測（L3 システムテスト）。

なぜ測るか:
    第一印象は視覚的複雑性と典型性でおおよそ説明できる（Reinecke et al. 2013 は
    複雑性と色の豊かさで美的魅力度評定の分散の約半分を説明した）。
    「ごちゃごちゃして見える」を主観のまま放置すると、増改築のたびに悪化して
    誰も気づけない。要素数・色数・情報密度を数値で固定し、回帰を検知する。

測り方は2系統:
    1. DOM 由来（要素数・色数・情報密度）— 何が増えたかを特定しやすい
    2. 描画結果由来（圧縮率・エッジ密度・colorfulness）— 実際に目に入る量に近い
       Reinecke et al. 2013 が用いた画像特徴量の再実装（web/services/visual_complexity.py）

限界:
    知覚モデルそのものではない。絶対値で美しさを主張するものではなく、
    **これ以上増やさないための上限**として使う。

閾値の根拠:
    2026-07-26 時点の実測値に余裕を持たせた上限。悪化したら気づくのが目的で、
    「この値が理想」という主張ではない。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from playwright.sync_api import Page

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from web.services.visual_complexity import measure  # noqa: E402

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")

#: DOM から視覚的複雑性の代理指標を算出する。
_MEASURE_JS = """() => {
  const vis = e => {
    const r = e.getBoundingClientRect();
    const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.display !== 'none'
      && s.visibility !== 'hidden' && Number(s.opacity) > 0.05;
  };
  const all = Array.from(document.querySelectorAll('body *')).filter(vis);
  const leaves = all.filter(e => !Array.from(e.children).some(vis));
  const colors = new Set(), fonts = new Set(), sizes = new Set();
  let inkArea = 0;
  for (const e of leaves) {
    const s = getComputedStyle(e), r = e.getBoundingClientRect();
    colors.add(s.color);
    if (s.backgroundColor !== 'rgba(0, 0, 0, 0)') colors.add(s.backgroundColor);
    fonts.add(s.fontFamily.split(',')[0].trim());
    sizes.add(s.fontSize);
    if (e.textContent && e.textContent.trim()) inkArea += r.width * r.height;
  }
  const vw = document.documentElement.clientWidth;
  const vh = document.documentElement.clientHeight;
  const interactive = all.filter(e => /^(BUTTON|A|INPUT|SELECT|TEXTAREA)$/.test(e.tagName));
  const primary = all.filter(e => (e.className || '').toString().includes('btn-primary'));
  return {
    visibleElements: all.length,
    interactive: interactive.length,
    primaryCtas: primary.length,
    distinctColors: colors.size,
    distinctFontFamilies: fonts.size,
    distinctFontSizes: sizes.size,
    textDensityPct: Math.round((inkArea / (vw * vh)) * 100),
  };
}"""

#: 画面ごとの上限。2026-07-26 の実測値に余裕を持たせた値。
_BUDGETS = {
    "auto-run": {
        "path": "/auto-run",
        "visibleElements": 260,
        "interactive": 40,
        "primaryCtas": 2,
        "distinctColors": 18,
        "distinctFontFamilies": 4,
        "distinctFontSizes": 16,
        "textDensityPct": 45,
    },
    "report": {
        "path": "/autorun/report/127.0.0.1:8767",
        "visibleElements": 400,
        "interactive": 40,
        "primaryCtas": 2,
        "distinctColors": 20,
        "distinctFontFamilies": 4,
        "distinctFontSizes": 18,
        "textDensityPct": 45,
    },
}


class TestVisualComplexityBudget:
    """視覚的複雑性が上限を超えていないこと。"""

    @pytest.mark.parametrize("name", sorted(_BUDGETS))
    def test_within_budget(self, page: Page, name: str) -> None:
        budget = _BUDGETS[name]
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto(f"{BASE_URL}{budget['path']}")
        page.wait_for_load_state("networkidle")
        measured = page.evaluate(_MEASURE_JS)

        exceeded = {
            key: (measured[key], limit)
            for key, limit in budget.items()
            if key != "path" and measured.get(key, 0) > limit
        }
        assert not exceeded, (
            f"{name} の視覚的複雑性が上限を超えました: "
            f"{json.dumps(exceeded, ensure_ascii=False)} / 実測={json.dumps(measured, ensure_ascii=False)}"
        )

    def test_single_primary_cta_on_intake(self, page: Page) -> None:
        """受付画面の主要CTAは1つ。

        同じ重さの青ボタンが並ぶと、どれを押せばよいか決められない
        （視線誘導が成立しない）。
        """
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto(f"{BASE_URL}/auto-run")
        page.wait_for_load_state("networkidle")
        measured = page.evaluate(_MEASURE_JS)
        assert (
            measured["primaryCtas"] <= 1
        ), f"受付画面の主要CTAが {measured['primaryCtas']} 個あります（1個以下にすること）"


#: 描画結果から測る上限。2026-07-26 の実測に余裕を持たせた値。
#: 参考実測: 受付 圧縮率0.083/エッジ0.046、改修前の段階画面 0.080/0.043 →
#: 改修後 0.068/0.033（要確認1本化とCTA整理で約2割低下）。
_IMAGE_BUDGETS = {
    "auto-run": {
        "path": "/auto-run",
        "compression_ratio": 0.12,
        "edge_density": 0.065,
        "colorfulness": 55.0,
    },
    "report": {
        "path": "/autorun/report/127.0.0.1:8767",
        "compression_ratio": 0.12,
        "edge_density": 0.065,
        "colorfulness": 55.0,
    },
}


class TestRenderedComplexityBudget:
    """描画結果そのものの複雑性が上限を超えていないこと。

    DOM の要素数は代理でしかない。実際に目に入るのは描画結果なので、
    スクリーンショットから圧縮率・エッジ密度・色の豊かさを測る。
    """

    @pytest.mark.parametrize("name", sorted(_IMAGE_BUDGETS))
    def test_rendered_within_budget(self, page: Page, tmp_path: Path, name: str) -> None:
        budget = _IMAGE_BUDGETS[name]
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto(f"{BASE_URL}{budget['path']}")
        page.wait_for_load_state("networkidle")
        shot = tmp_path / f"{name}.png"
        page.screenshot(path=str(shot), full_page=False, animations="disabled", caret="hide")

        measured = measure(shot).to_dict()
        exceeded = {
            key: (measured[key], limit)
            for key, limit in budget.items()
            if key != "path" and measured.get(key, 0) > limit
        }
        assert not exceeded, (
            f"{name} の描画複雑性が上限を超えました: "
            f"{json.dumps(exceeded, ensure_ascii=False)} / "
            f"実測={json.dumps(measured, ensure_ascii=False)}"
        )
