from __future__ import annotations

"""フロントエンド・バックエンド技術スタックを Playwright で自動検出する。

page.evaluate() でブラウザ内のグローバル変数・DOM マーカー・スクリプト URL を検査し、
レスポンスヘッダー（Server / X-Powered-By）と組み合わせて StackInfo を生成する。
"""

import logging
from dataclasses import dataclass

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

logger = logging.getLogger(__name__)

UNKNOWN = "不明"

# ブラウザ内で実行するスタック検出スクリプト
_DETECT_SCRIPT = """
(() => {
  try {
    const w = window;
    const d = document;
    const scripts = Array.from(d.querySelectorAll('script[src]')).map(s => s.src).slice(0, 30);
    const metas = {};
    d.querySelectorAll('meta').forEach(m => {
      const k = m.name || m.property || '';
      if (k) metas[k] = m.content || '';
    });
    return {
      hasReact: !!(w.React || w.__REACT_DEVTOOLS_GLOBAL_HOOK__ ||
                   d.querySelector('[data-reactroot],[data-react-helmet]')),
      reactVersion: (w.React && w.React.version) || null,
      hasVue3: !!(w.__vue_app__),
      hasVue2: !!(w.Vue && typeof w.Vue.version === 'string' && w.Vue.version.startsWith('2')),
      hasAngular: !!(w.ng || w.angular || d.querySelector('[ng-version]')),
      angularVersion: (d.querySelector('[ng-version]') || {getAttribute: () => null})
                      .getAttribute('ng-version'),
      hasSvelte: !!(w.__svelte || d.querySelector('[class^="svelte-"]')),
      hasNext: !!(w.__NEXT_DATA__),
      nextBuildId: (w.__NEXT_DATA__ && w.__NEXT_DATA__.buildId) || null,
      hasNuxt: !!(w.__NUXT__ || w.__nuxt || d.getElementById('__nuxt')),
      hasRemix: !!(w.__remixContext),
      hasAstro: !!(d.querySelector('astro-island')),
      hasTailwind: !!(d.querySelector('.flex, .grid, .container') &&
                      d.querySelector('[class*="text-"], [class*="bg-"], [class*="p-"], [class*="m-"]')),
      hasBootstrap: !!(d.querySelector('.container, .row .col, .btn, .navbar')),
      hasMUI: !!(d.querySelector('[class*="MuiBox"], [class*="MuiButton"], [class*="MuiTypography"]')),
      hasAntDesign: !!(d.querySelector('.ant-btn, .ant-input, .ant-form')),
      hasRedux: !!(w.__REDUX_DEVTOOLS_EXTENSION__ || w.__REDUX_DEVTOOLS_EXTENSION_COMPOSE__),
      hasMobX: !!(w.mobxReact || w.mobx),
      hasPinia: !!(w.__pinia),
      scriptUrls: scripts,
      metaGenerator: metas['generator'] || '',
    };
  } catch(e) {
    return {};
  }
})()
"""


@dataclass(frozen=True)
class StackInfo:
    """クロール中に検出した技術スタック情報。"""

    frontend_framework: str
    rendering_mode: str
    css_framework: str
    state_management: str
    backend_hints: tuple[str, ...]
    detected_libraries: tuple[str, ...]


def detect_stack(page: Page, response_headers: dict[str, str]) -> StackInfo:
    """Playwright page から技術スタックを検出して StackInfo を返す。

    page.evaluate() による JS 実行が失敗した場合は UNKNOWN でフォールバックする。
    """
    try:
        info: dict = page.evaluate(_DETECT_SCRIPT) or {}
    except PlaywrightError as exc:
        logger.debug("スタック検出 JS 実行失敗: %s", exc)
        info = {}

    frontend = _detect_frontend(info)
    rendering = _detect_rendering(info, frontend)
    css = _detect_css(info)
    state = _detect_state(info)
    backend = _detect_backend(response_headers, info)
    libraries = _collect_libraries(info)

    return StackInfo(
        frontend_framework=frontend,
        rendering_mode=rendering,
        css_framework=css,
        state_management=state,
        backend_hints=tuple(backend),
        detected_libraries=tuple(libraries),
    )


def _detect_frontend(info: dict) -> str:
    if info.get("hasNext"):
        return "React / Next.js"
    if info.get("hasNuxt"):
        return "Vue / Nuxt.js"
    if info.get("hasRemix"):
        return "React / Remix"
    if info.get("hasAstro"):
        return "Astro"
    if info.get("hasReact"):
        v = info.get("reactVersion")
        return f"React {v}" if v else "React"
    if info.get("hasVue3"):
        return "Vue 3"
    if info.get("hasVue2"):
        return "Vue 2"
    if info.get("hasAngular"):
        v = info.get("angularVersion")
        return f"Angular {v}" if v else "Angular"
    if info.get("hasSvelte"):
        return "Svelte"
    scripts = " ".join(info.get("scriptUrls", []))
    if "react" in scripts:
        return "React"
    if "vue" in scripts:
        return "Vue"
    if "angular" in scripts:
        return "Angular"
    return UNKNOWN


def _detect_rendering(info: dict, frontend: str) -> str:
    if info.get("hasNext"):
        return "SSR / Next.js"
    if info.get("hasNuxt"):
        return "SSR / Nuxt.js"
    if info.get("hasRemix"):
        return "SSR / Remix"
    if frontend != UNKNOWN and frontend not in ("Astro",):
        return "SPA"
    return "MPA"


def _detect_css(info: dict) -> str:
    if info.get("hasMUI"):
        return "Material UI"
    if info.get("hasAntDesign"):
        return "Ant Design"
    if info.get("hasTailwind"):
        return "Tailwind CSS"
    if info.get("hasBootstrap"):
        return "Bootstrap"
    return UNKNOWN


def _detect_state(info: dict) -> str:
    if info.get("hasRedux"):
        return "Redux"
    if info.get("hasMobX"):
        return "MobX"
    if info.get("hasPinia"):
        return "Pinia"
    return UNKNOWN


def _detect_backend(headers: dict[str, str], info: dict) -> list[str]:
    hints: list[str] = []
    # HTTP ヘッダーのキーは大文字小文字が混在するためどちらも確認
    for key in ("server", "Server"):
        val = headers.get(key, "")
        if val:
            hints.append(f"Server: {val}")
            break
    for key in ("x-powered-by", "X-Powered-By"):
        val = headers.get(key, "")
        if val:
            hints.append(f"X-Powered-By: {val}")
            break
    gen = info.get("metaGenerator", "")
    if gen:
        hints.append(f"Generator: {gen}")
    return hints


def _collect_libraries(info: dict) -> list[str]:
    mapping = {
        "hasReact": "React",
        "hasVue3": "Vue 3",
        "hasVue2": "Vue 2",
        "hasAngular": "Angular",
        "hasSvelte": "Svelte",
        "hasNext": "Next.js",
        "hasNuxt": "Nuxt.js",
        "hasRemix": "Remix",
        "hasAstro": "Astro",
        "hasTailwind": "Tailwind CSS",
        "hasBootstrap": "Bootstrap",
        "hasMUI": "Material UI",
        "hasAntDesign": "Ant Design",
        "hasRedux": "Redux",
        "hasMobX": "MobX",
        "hasPinia": "Pinia",
    }
    return [name for key, name in mapping.items() if info.get(key)]
