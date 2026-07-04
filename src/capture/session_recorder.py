"""探索セッションの操作記録。

記録用ブラウザでテスターが自由に操作している間、ポーリングで
window バッファから操作イベントを回収し、画面状態のシグネチャ
（クロール時と同一アルゴリズム）とともに JSONL へ追記する。

ポーリング方式（イベントを JS 側バッファに溜めて Python 側で回収）に
しているのは、Playwright sync API の binding コールバック内から
page 操作を行うと再入で行き詰まるため。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from crawler.action_explorer import _live_state, state_signature

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

SESSIONS_DIR_NAME = "sessions"
DEFAULT_POLL_INTERVAL_SEC = 0.5

# 気づきマークウィジェットのボタン要素 id（click リスナーの二重記録除外にも使う）
FINDING_WIDGET_ID = "__ws2d_finding_btn"

# クリック・変更イベントを window バッファへ溜める（ナビゲーションごとに再注入される）。
# 右下固定の「⚑ 気づき」ボタン（気づきマークウィジェット）も同スクリプトで注入する
# （Shadow DOM は不使用・高 z-index。既存の add_init_script + evaluate 再注入機構に乗せる）。
_RECORDER_JS = """
(() => {
  if (window.__ws2dRecorderInit) return;
  window.__ws2dRecorderInit = true;
  window.__ws2dEvents = window.__ws2dEvents || [];
  const FINDING_BTN_ID = '__ws2d_finding_btn';
  const describe = (el) => {
    if (!el || !el.tagName) return '';
    if (el.id) return '#' + el.id;
    const name = el.getAttribute && el.getAttribute('name');
    if (name) return el.tagName.toLowerCase() + "[name='" + name + "']";
    const text = (el.innerText || '').trim().slice(0, 20);
    return el.tagName.toLowerCase() + (text ? ':has-text("' + text + '")' : '');
  };
  const interactive =
    'a, button, [role=button], input, select, textarea, summary, [role=tab], [aria-expanded]';
  document.addEventListener('click', (event) => {
    const el = (event.target.closest && event.target.closest(interactive)) || event.target;
    // 気づきボタン自身のクリックは操作イベントとして二重記録しない（専用ハンドラで処理する）
    if (el && el.id === FINDING_BTN_ID) return;
    window.__ws2dEvents.push({ type: 'click', selector: describe(el) });
  }, true);
  document.addEventListener('change', (event) => {
    window.__ws2dEvents.push({ type: 'input', selector: describe(event.target) });
  }, true);
  const injectFindingWidget = () => {
    if (document.getElementById(FINDING_BTN_ID) || !document.body) return;
    const btn = document.createElement('button');
    btn.id = FINDING_BTN_ID;
    btn.type = 'button';
    btn.textContent = '⚑ 気づき';
    btn.style.cssText =
      'position:fixed;right:12px;bottom:12px;z-index:2147483647;' +
      'padding:8px 14px;background:#d93025;color:#fff;border:none;' +
      'border-radius:4px;font-size:13px;cursor:pointer;' +
      'box-shadow:0 1px 4px rgba(0,0,0,0.3);';
    btn.addEventListener('click', (event) => {
      event.stopPropagation();
      const note = window.prompt('気づきメモ（空でも可）', '') || '';
      window.__ws2dEvents.push({ type: 'finding', note: note });
    });
    document.body.appendChild(btn);
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectFindingWidget);
  } else {
    injectFindingWidget();
  }
})()
"""

_DRAIN_JS = """
() => {
  const events = window.__ws2dEvents || [];
  window.__ws2dEvents = [];
  return events;
}
"""


def normalize_footprint_path(url: str) -> str:
    """URL を探索カバレッジの照合用パスに正規化する。"""
    path = urlparse(url).path.rstrip("/").lower()
    return path or "/"


@dataclass
class SessionRecorder:
    """1 探索セッション分の操作記録。

    page は呼び出し側が用意する（CLI では記録用ブラウザ、テストでは実ブラウザ/フェイク）。
    """

    page: Any
    session_path: Path
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    _records: list[dict[str, Any]] = field(default_factory=list)
    _last_url: str = ""
    _last_state_sig: str = "default"

    def start(self) -> None:
        """リスナーを注入し、現在ページを最初の訪問として記録する。"""
        self.page.add_init_script(_RECORDER_JS)
        try:
            self.page.evaluate(_RECORDER_JS)
        except Exception:  # noqa: BLE001  # 初期ページが about:blank 等でも継続する
            logger.warning("気づきウィジェットを注入できません（記録は継続）")
        self._record_visit(self.page.url)

    def poll_once(self) -> int:
        """バッファの操作イベントと画面状態の変化を回収する。

        戻り値は今回記録したイベント数。ページ/ブラウザが閉じられた場合は
        PlaywrightError が伝播する（呼び出し側で終了判定に使う）。
        """
        recorded = 0
        url = self.page.url
        if url != self._last_url:
            self._record_visit(url)
            recorded += 1
        raw_events = self.page.evaluate(_DRAIN_JS)
        if isinstance(raw_events, list):
            for event in raw_events:
                if not isinstance(event, dict):
                    continue
                event_type = str(event.get("type") or "")
                if event_type == "finding":
                    # 気づき時点の画面状態は self._last_state_sig をそのまま転記する
                    # （再計算しない。AC-2: 独自ハッシュを作らず記録済みシグネチャを使う）
                    self._append(
                        {
                            "kind": "finding",
                            "note": str(event.get("note") or ""),
                            "url": url,
                            "path": normalize_footprint_path(url),
                            "state_id": self._last_state_sig,
                        }
                    )
                    recorded += 1
                    continue
                self._append(
                    {
                        "kind": "action",
                        "action_type": event_type,
                        "selector": str(event.get("selector") or ""),
                        "url": url,
                        "path": normalize_footprint_path(url),
                    }
                )
                recorded += 1
        sig = state_signature(tuple(_live_state(self.page)))
        if sig != self._last_state_sig:
            self._last_state_sig = sig
            if sig != "default":
                self._append(
                    {
                        "kind": "state",
                        "state_id": sig,
                        "url": url,
                        "path": normalize_footprint_path(url),
                    }
                )
                recorded += 1
        return recorded

    def run(self, duration_sec: float | None = None) -> None:
        """ブラウザが閉じられるか制限時間まで記録を続ける。"""
        deadline = time.monotonic() + duration_sec if duration_sec else None
        while deadline is None or time.monotonic() < deadline:
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001  # ページクローズ＝セッション終了
                break
            time.sleep(DEFAULT_POLL_INTERVAL_SEC)
        self.flush()

    def flush(self) -> None:
        """記録を JSONL へ書き出す。"""
        if not self._records:
            return
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        with self.session_path.open("a", encoding="utf-8") as handle:
            for record in self._records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._records.clear()

    def _record_visit(self, url: str) -> None:
        self._last_url = url
        self._last_state_sig = "default"
        # 記録開始直後の about:blank / chrome-error 等は足跡として意味を持たない
        if url.startswith(("about:", "chrome-error:")):
            return
        self._append({"kind": "visit", "url": url, "path": normalize_footprint_path(url)})

    def _append(self, record: dict[str, Any]) -> None:
        # 日時ベースの推移集計（バーンダウン, SPEC-5-2）のために全レコードへ ts を付与する
        record.setdefault("ts", self.clock().isoformat(timespec="seconds"))
        self._records.append(record)


def record_exploration_session(
    url: str,
    output_dir: Path,
    duration_sec: float | None = None,
    headless: bool = False,
) -> Path:
    """記録用ブラウザを起動し、閉じられるまで探索セッションを記録する。

    クローラと同じ UA・ロケール設定のブラウザを使う（ヘッドありが既定。
    テスト・CI では headless=True を指定する）。
    """
    from playwright.sync_api import sync_playwright

    from crawler.page_crawler import BROWSER_LOCALE, USER_AGENT
    from crawler.url_safety import validate_target_url

    validate_target_url(url)
    session_path = _next_session_path(output_dir)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, args=[f"--lang={BROWSER_LOCALE}"])
        try:
            context = browser.new_context(user_agent=USER_AGENT, locale=BROWSER_LOCALE)
            page = context.new_page()
            recorder = SessionRecorder(page=page, session_path=session_path)
            recorder.start()
            page.goto(url)
            recorder.run(duration_sec=duration_sec)
        finally:
            browser.close()
    return session_path


def _next_session_path(output_dir: Path) -> Path:
    sessions_dir = output_dir / SESSIONS_DIR_NAME
    sessions_dir.mkdir(parents=True, exist_ok=True)
    index = len(list(sessions_dir.glob("session_*.jsonl"))) + 1
    return sessions_dir / f"session_{index:03d}.jsonl"
