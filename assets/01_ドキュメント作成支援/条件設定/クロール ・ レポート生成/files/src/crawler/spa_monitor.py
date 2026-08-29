"""SPA 遷移（pushState / replaceState / hashchange）の捕捉。

ページに init script を注入し、URL 変化を伴う History API 呼び出しを
記録して SpaTransition として収集する。transition_graph の遷移エッジ
として供給できる形式で返す。
"""

from __future__ import annotations

import logging
from typing import Any

from playwright.sync_api import Page

from crawler.page_crawler import SpaTransition

logger = logging.getLogger(__name__)

_INIT_SCRIPT = """
(() => {
  if (window.__ws2d_hooked) return;
  window.__ws2d_hooked = true;
  window.__ws2d_transitions = [];
  const record = (kind, to) => {
    try {
      const from = window.__ws2d_last || location.href;
      window.__ws2d_transitions.push({ kind: kind, from: from, to: to });
      window.__ws2d_last = to;
    } catch (e) { /* 記録失敗はクロールを妨げない */ }
  };
  const origPush = history.pushState;
  history.pushState = function (state, title, url) {
    const result = origPush.apply(this, arguments);
    if (url) record('pushstate', new URL(url, location.href).href);
    return result;
  };
  const origReplace = history.replaceState;
  history.replaceState = function (state, title, url) {
    const result = origReplace.apply(this, arguments);
    if (url) record('replacestate', new URL(url, location.href).href);
    return result;
  };
  window.addEventListener('hashchange', (event) => {
    record('hashchange', event.newURL);
  });
})();
"""

_COLLECT_JS = "() => window.__ws2d_transitions || []"

_VALID_KINDS = frozenset({"pushstate", "replacestate", "hashchange", "dom_change"})


class SpaTransitionMonitor:
    """pushState / replaceState / hashchange をフックして遷移を収集する。"""

    def attach(self, page: Page) -> None:
        """ナビゲーション前に init script を注入する（goto の前に呼ぶこと）。"""
        try:
            page.add_init_script(_INIT_SCRIPT)
        except Exception as exc:
            logger.warning("SPA 遷移フックの注入に失敗しました: %s", exc)

    def collect(self, page: Page) -> tuple[SpaTransition, ...]:
        """注入済みフックが記録した遷移を SpaTransition として返す。"""
        try:
            raw = page.evaluate(_COLLECT_JS)
        except Exception as exc:
            logger.debug("SPA 遷移の収集に失敗しました: %s", exc)
            return ()
        if not isinstance(raw, list):
            return ()
        transitions = [_record_transition(item) for item in raw]
        return tuple(t for t in transitions if t is not None)


def _record_transition(raw: Any) -> SpaTransition | None:
    """dict から SpaTransition を構築する（不正な場合は None）。"""
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "")
    to_url = str(raw.get("to") or "")
    if kind not in _VALID_KINDS or not to_url:
        return None
    return SpaTransition(
        from_url=str(raw.get("from") or ""),
        to_url=to_url,
        kind=kind,
    )
