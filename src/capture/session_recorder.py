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
STATUS_WRITE_INTERVAL_SEC = 1.0

# 気づきマークウィジェットのボタン要素 id（click リスナーの二重記録除外にも使う）
FINDING_WIDGET_ID = "__ws2d_finding_btn"

# クリック・変更・keydown イベントを window バッファへ溜める（ナビゲーションごとに再注入される）。
# 右下固定の「⚑ 気づき」ボタン（気づきマークウィジェット）も同スクリプトで注入する
# （Shadow DOM は不使用・高 z-index。既存の add_init_script + evaluate 再注入機構に乗せる）。
_RECORDER_JS = """
(() => {
  if (window.__ws2dRecorderInit) return;
  window.__ws2dRecorderInit = true;
  window.__ws2dEvents = window.__ws2dEvents || [];
  // 画面遷移（同一オリジン）でイベントを失わないよう sessionStorage にも写す。
  // クリック直後にナビゲーションが起きると window のバッファは消えるため、
  // 次のページの初期化時にここから復元し、Python 側の drain で両方を空にする。
  const STORE_KEY = '__ws2dEventsPending';
  try {
    const pending = JSON.parse(sessionStorage.getItem(STORE_KEY) || '[]');
    if (Array.isArray(pending) && pending.length) Array.prototype.push.apply(window.__ws2dEvents, pending);
  } catch (e) { /* sessionStorage 不可の環境では諦める */ }
  const persist = () => {
    try { sessionStorage.setItem(STORE_KEY, JSON.stringify(window.__ws2dEvents)); } catch (e) { /* 同上 */ }
  };
  window.__ws2dPush = (ev) => { window.__ws2dEvents.push(ev); persist(); };
  const FINDING_BTN_ID = '__ws2d_finding_btn';
  const describe = (el) => {
    if (!el || !el.tagName) return '';
    if (el.id) return '#' + el.id;
    const name = el.getAttribute && el.getAttribute('name');
    if (name) return el.tagName.toLowerCase() + "[name='" + name + "']";
    const text = (el.innerText || '').trim().slice(0, 20);
    return el.tagName.toLowerCase() + (text ? ':has-text("' + text + '")' : '');
  };
  const escapeCss = (value) =>
    (window.CSS && CSS.escape) ? CSS.escape(value) : String(value).replace(/[^a-zA-Z0-9_-]/g, '\\\\$&');
  const ariaName = (el) => {
    if (!el || !el.tagName) return null;
    if (el.id) {
      const label = document.querySelector("label[for='" + escapeCss(el.id) + "']");
      if (label && label.innerText && label.innerText.trim()) {
        return 'aria/' + label.innerText.trim().slice(0, 40);
      }
    }
    const ariaLabel = el.getAttribute && el.getAttribute('aria-label');
    if (ariaLabel && ariaLabel.trim()) return 'aria/' + ariaLabel.trim().slice(0, 40);
    const labelledBy = el.getAttribute && el.getAttribute('aria-labelledby');
    if (labelledBy) {
      const ref = document.getElementById(labelledBy);
      if (ref && ref.innerText && ref.innerText.trim()) {
        return 'aria/' + ref.innerText.trim().slice(0, 40);
      }
    }
    if (el.tagName === 'BUTTON' || el.tagName === 'A') {
      const text = (el.innerText || '').trim();
      if (text) return 'aria/' + text.slice(0, 40);
    }
    return null;
  };
  const absoluteXPath = (el) => {
    if (!el || el.nodeType !== 1) return '';
    if (el.id) return "//*[@id='" + el.id + "']";
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.documentElement) {
      let index = 1;
      let sibling = node.previousElementSibling;
      while (sibling) {
        if (sibling.tagName === node.tagName) index += 1;
        sibling = sibling.previousElementSibling;
      }
      parts.unshift(node.tagName.toLowerCase() + '[' + index + ']');
      node = node.parentElement;
    }
    return '/html/' + parts.join('/');
  };
  // §1 の候補列: #id / aria/<accessible name> / <tag>[name='x'] / xpath/<絶対xpath> / text/<可視テキスト>
  // のうち取れたものを順に返す。先頭は describe() の戻り値と一致させる。
  const describeAll = (el) => {
    if (!el || !el.tagName) return [];
    const idVal = el.id ? '#' + el.id : null;
    const ariaVal = ariaName(el);
    const name = el.getAttribute && el.getAttribute('name');
    const nameVal = name ? el.tagName.toLowerCase() + "[name='" + name + "']" : null;
    const xp = absoluteXPath(el);
    const xpathVal = xp ? 'xpath/' + xp : null;
    const text = (el.innerText || el.textContent || '').trim().slice(0, 40);
    const textVal = text ? 'text/' + text : null;
    const head = describe(el);
    const ordered = [idVal, ariaVal, nameVal, xpathVal, textVal];
    const seen = new Set();
    const result = [];
    const push = (value) => {
      if (value && !seen.has(value)) {
        seen.add(value);
        result.push([value]);
      }
    };
    push(head);
    ordered.forEach(push);
    return result;
  };
  const isMasked = (el) => {
    if (!el) return false;
    const type = (el.type || '').toLowerCase();
    if (type === 'password') return true;
    const hay = [el.name, el.id, el.getAttribute && el.getAttribute('autocomplete')]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return /pass|pwd|secret|token|card|cvv/.test(hay);
  };
  const inputTypeOf = (el) => {
    if (!el || !el.tagName) return 'text';
    const tag = el.tagName.toLowerCase();
    if (tag === 'select') return 'select';
    if (tag === 'textarea') return 'textarea';
    if (tag === 'input') return (el.type || 'text').toLowerCase();
    return tag;
  };
  const interactive =
    'a, button, [role=button], input, select, textarea, summary, [role=tab], [aria-expanded]';
  document.addEventListener('click', (event) => {
    const el = (event.target.closest && event.target.closest(interactive)) || event.target;
    // 気づきボタン自身のクリックは操作イベントとして二重記録しない（専用ハンドラで処理する）
    if (el && el.id === FINDING_BTN_ID) return;
    window.__ws2dPush({
      type: 'click',
      url: location.href,
      selector: describe(el),
      selectors: describeAll(el),
      title: document.title,
    });
  }, true);
  document.addEventListener('change', (event) => {
    const el = event.target;
    const masked = isMasked(el);
    let rawValue = '';
    try {
      rawValue = el.value == null ? '' : String(el.value);
    } catch (err) {
      rawValue = '';
    }
    window.__ws2dPush({
      type: 'input',
      url: location.href,
      selector: describe(el),
      selectors: describeAll(el),
      value: masked ? '***' : rawValue,
      masked: masked,
      input_type: inputTypeOf(el),
      title: document.title,
    });
  }, true);
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== 'Tab' && event.key !== 'Escape') return;
    const el = event.target;
    window.__ws2dPush({
      type: 'keydown',
      url: location.href,
      key: event.key,
      selector: describe(el),
      selectors: describeAll(el),
      title: document.title,
    });
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
      window.__ws2dPush({ type: 'finding', note: note });
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
  try { sessionStorage.removeItem('__ws2dEventsPending'); } catch (e) { /* 同上 */ }
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
    shots_dir: Path | None = None
    status_path: Path | None = None
    signal_path: Path | None = None
    step_count: int = 0
    _records: list[dict[str, Any]] = field(default_factory=list)
    _all_events: list[dict[str, Any]] = field(default_factory=list)
    _last_url: str = ""
    _last_state_sig: str = "default"
    _last_screenshot: str = ""

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
        raw_events = self.page.evaluate(_DRAIN_JS)
        events = [e for e in raw_events if isinstance(e, dict)] if isinstance(raw_events, list) else []
        # クリック直後に画面遷移した場合、その操作は sessionStorage 経由で次ページの
        # 初期化時に復元される（JS 側）。発生時の URL が今のページと違う操作は
        # 「遷移前の操作」なので、新しい visit を書く前に、元の URL で記録する。
        previous = [e for e in events if e.get("url") and str(e.get("url")) != url]
        current = [e for e in events if not (e.get("url") and str(e.get("url")) != url)]
        for event in previous:
            recorded += self._write_event(event, str(event.get("url")), take_shot=False)
        if url != self._last_url:
            self._record_visit(url)
            recorded += 1
        for event in current:
            recorded += self._write_event(event, url, take_shot=True)
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

    def _write_event(self, event: dict[str, Any], url: str, *, take_shot: bool) -> int:
        """drain した 1 イベントを JSONL レコードにして追記する。戻り値は記録数（0/1）。

        take_shot=False は「遷移前ページの操作」用。そのページはもう無いので、
        今の画面を撮っても証跡にならない（撮らない方が正直）。
        """
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
            return 1
        record: dict[str, Any] = {
            "kind": "action",
            "action_type": event_type,
            "selector": str(event.get("selector") or ""),
            "url": url,
            "path": normalize_footprint_path(url),
        }
        selectors = event.get("selectors")
        if isinstance(selectors, list) and selectors:
            record["selectors"] = selectors
        if event_type == "input":
            record["value"] = str(event.get("value") or "")
            record["masked"] = bool(event.get("masked"))
            input_type = event.get("input_type")
            if input_type:
                record["input_type"] = str(input_type)
        elif event_type == "keydown":
            key = event.get("key")
            if key:
                record["key"] = str(key)
        title = event.get("title")
        if title:
            record["title"] = str(title)
        self.step_count += 1
        if take_shot:
            screenshot = self._capture_screenshot()
            if screenshot:
                record["screenshot"] = screenshot
        self._append(record)
        return 1

    def run(self, duration_sec: float | None = None) -> None:
        """ブラウザが閉じられるか制限時間まで記録を続ける。

        signal_path が存在したら（外部からの停止要求）ループを抜ける。
        status_path があれば 1 秒に 1 回、進捗を JSON で書き出す。
        """
        deadline = time.monotonic() + duration_sec if duration_sec else None
        started_at = self.clock().isoformat(timespec="seconds")
        last_status_write = 0.0
        while deadline is None or time.monotonic() < deadline:
            if self.signal_path is not None and self.signal_path.exists():
                break
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001  # ページクローズ＝セッション終了
                break
            now = time.monotonic()
            if self.status_path is not None and now - last_status_write >= STATUS_WRITE_INTERVAL_SEC:
                self._write_status(phase="recording", started_at=started_at)
                last_status_write = now
            time.sleep(DEFAULT_POLL_INTERVAL_SEC)
        self.flush()
        self._write_status(phase="stopped", started_at=started_at)

    def flush(self) -> None:
        """記録を JSONL へ書き出し、user-flow JSON を（累積イベントで）上書き生成する。"""
        if self._records:
            self.session_path.parent.mkdir(parents=True, exist_ok=True)
            with self.session_path.open("a", encoding="utf-8") as handle:
                for record in self._records:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._records.clear()
        if self._all_events:
            self._write_flow()

    def _write_flow(self) -> None:
        """`sessions/session_NNN.flow.json` を書く（userflow は並行開発中のため遅延 import）。"""
        try:
            from capture.userflow import events_to_user_flow, save_user_flow
        except Exception:  # noqa: BLE001  # userflow 未整備でも記録自体は止めない
            logger.warning("userflow モジュールを読み込めません（flow.json 生成をスキップ）")
            return
        session = self.session_path.stem
        domain = self.session_path.parent.parent.name
        flow_path = self.session_path.parent / f"{session}.flow.json"
        try:
            flow = events_to_user_flow(list(self._all_events), session=session, domain=domain)
            save_user_flow(flow, flow_path)
        except Exception:  # noqa: BLE001  # flow 生成の失敗で記録を止めない
            logger.warning("flow.json の生成に失敗しました", exc_info=True)

    def _capture_screenshot(self) -> str | None:
        """現在の step_count 番号でスクショを撮り、output_dir からの相対パスを返す。

        shots_dir 未設定、または撮影に失敗した場合は None（記録は止めない）。
        """
        if self.shots_dir is None:
            return None
        target = self.shots_dir / f"step_{self.step_count:04d}.png"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(target), full_page=False)
        except Exception:  # noqa: BLE001  # スクショ失敗は記録を止めない
            return None
        try:
            return str(target.relative_to(self.session_path.parent.parent)).replace("\\", "/")
        except ValueError:
            return str(target)

    def _write_status(self, *, phase: str, started_at: str) -> None:
        if self.status_path is None:
            return
        events = self._all_events
        status = {
            "phase": phase,
            "events": len(events),
            "visits": sum(1 for event in events if event.get("kind") == "visit"),
            "actions": sum(1 for event in events if event.get("kind") == "action"),
            "findings": sum(1 for event in events if event.get("kind") == "finding"),
            "last_url": self._last_url,
            "last_screenshot": self._last_screenshot,
            "session": self.session_path.stem,
            "started_at": started_at,
        }
        try:
            self.status_path.parent.mkdir(parents=True, exist_ok=True)
            self.status_path.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
        except Exception:  # noqa: BLE001  # status 書き込み失敗で記録を止めない
            logger.warning("status ファイルを書き込めません", exc_info=True)

    def _record_visit(self, url: str) -> None:
        self._last_url = url
        self._last_state_sig = "default"
        # 記録開始直後の about:blank / chrome-error 等は足跡として意味を持たない
        if url.startswith(("about:", "chrome-error:")):
            return
        record: dict[str, Any] = {"kind": "visit", "url": url, "path": normalize_footprint_path(url)}
        title = self._current_title()
        if title:
            record["title"] = title
        self.step_count += 1
        screenshot = self._capture_screenshot()
        if screenshot:
            record["screenshot"] = screenshot
        self._append(record)

    def _current_title(self) -> str:
        try:
            return str(self.page.title())
        except Exception:  # noqa: BLE001  # title 取得失敗時は空文字（記録は止めない）
            return ""

    def _append(self, record: dict[str, Any]) -> None:
        # 日時ベースの推移集計（バーンダウン, SPEC-5-2）のために全レコードへ ts を付与する
        record.setdefault("ts", self.clock().isoformat(timespec="seconds"))
        self._records.append(record)
        self._all_events.append(record)
        screenshot = record.get("screenshot")
        if screenshot:
            self._last_screenshot = str(screenshot)


def _is_browser_closed_error(exc: Exception) -> bool:
    """Playwright の TargetClosedError、または『閉じられた』系エラーかどうかを判定する。"""
    return type(exc).__name__ == "TargetClosedError" or "closed" in str(exc).lower()


def record_exploration_session(
    url: str,
    output_dir: Path,
    duration_sec: float | None = None,
    headless: bool = False,
    *,
    storage_state: Path | None = None,
    signal_path: Path | None = None,
    status_path: Path | None = None,
) -> Path:
    """記録用ブラウザを起動し、閉じられるまで探索セッションを記録する。

    クローラと同じ UA・ロケール設定のブラウザを使う（ヘッドありが既定。
    テスト・CI では headless=True を指定する）。
    人間がブラウザを閉じた場合（TargetClosedError 等）も、ここまでの記録を
    flush して正常終了とする。
    """
    from playwright.sync_api import sync_playwright

    from crawler.page_crawler import BROWSER_LOCALE, USER_AGENT
    from crawler.url_safety import validate_target_url

    validate_target_url(url)
    session_path = _next_session_path(output_dir)
    shots_dir = output_dir / SESSIONS_DIR_NAME / "shots" / session_path.stem
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, args=[f"--lang={BROWSER_LOCALE}"])
        recorder: SessionRecorder | None = None
        try:
            context_kwargs: dict[str, Any] = {"user_agent": USER_AGENT, "locale": BROWSER_LOCALE}
            if storage_state is not None:
                context_kwargs["storage_state"] = str(storage_state)
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            recorder = SessionRecorder(
                page=page,
                session_path=session_path,
                shots_dir=shots_dir,
                status_path=status_path,
                signal_path=signal_path,
            )
            recorder.start()
            page.goto(url)
            recorder.run(duration_sec=duration_sec)
        except Exception as exc:  # noqa: BLE001  # ブラウザを閉じられた場合も記録を保存して終了する
            if not _is_browser_closed_error(exc):
                raise
            if recorder is not None:
                recorder.flush()
        finally:
            try:
                browser.close()
            except Exception:  # noqa: BLE001  # 既に閉じられていても構わない
                pass
    return session_path


def _next_session_path(output_dir: Path) -> Path:
    sessions_dir = output_dir / SESSIONS_DIR_NAME
    sessions_dir.mkdir(parents=True, exist_ok=True)
    index = len(list(sessions_dir.glob("session_*.jsonl"))) + 1
    return sessions_dir / f"session_{index:03d}.jsonl"
