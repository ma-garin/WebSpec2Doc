"""探索セッションの操作記録。

記録用ブラウザでテスターが自由に操作している間、ポーリングで
window バッファから操作イベントを回収し、画面状態のシグネチャ
（クロール時と同一アルゴリズム）とともに JSONL へ追記する。

ポーリング方式（イベントを JS 側バッファに溜めて Python 側で回収）に
しているのは、Playwright sync API の binding コールバック内から
page 操作を行うと再入で行き詰まるため。

記録するのは click / input(change) / press(Enter・Escape・Tab) の操作と、
テスターが操作ウィジェットから宣言する finding / assert_text / wait_text。
入力値も記録するが、`type="password"` だけは値を持たず `masked: true` のみを
残す（平文パスワードを JSONL に書かない）。
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

# 操作ウィジェットのボタン要素 id（click リスナーの二重記録除外にも使う）
FINDING_WIDGET_ID = "__ws2d_finding_btn"
ASSERT_WIDGET_ID = "__ws2d_assert_btn"
WAIT_WIDGET_ID = "__ws2d_wait_btn"

# 記録する値の上限文字数（長文入力で JSONL が肥大化するのを防ぐ）
MAX_RECORDED_VALUE_LEN = 500

# press として記録するキー（全キーを記録すると入力の一文字ごとに埋まるため限定する）
RECORDED_KEYS = ("Enter", "Escape", "Tab")

# クリック・変更・キー押下イベントを window バッファへ溜める（ナビゲーションごとに再注入される）。
# 右下固定の操作ウィジェット（⚑ 気づき / ✔ 検証 / ⏳ 待機）も同スクリプトで注入する
# （Shadow DOM は不使用・高 z-index。既存の add_init_script + evaluate 再注入機構に乗せる）。
#
# セレクタは describeAll() が優先順の候補配列を返す。イベントには candidates 配列を
# selectors として入れ、先頭候補を従来どおり selector にも入れる（下流互換）。
# 自己修復ロケータ（heal）の候補列にそのまま渡せる形にするのが目的。
_RECORDER_JS = """
(() => {
  if (window.__ws2dRecorderInit) return;
  window.__ws2dRecorderInit = true;
  window.__ws2dEvents = window.__ws2dEvents || [];
  const FINDING_BTN_ID = '__ws2d_finding_btn';
  const ASSERT_BTN_ID = '__ws2d_assert_btn';
  const WAIT_BTN_ID = '__ws2d_wait_btn';
  const WIDGET_IDS = [FINDING_BTN_ID, ASSERT_BTN_ID, WAIT_BTN_ID];
  const MAX_VALUE_LEN = 500;
  const PRESS_KEYS = ['Enter', 'Escape', 'Tab'];
  // 属性値をシングルクォート文字列へ安全に埋める（値に ' や \\ を含む場合の破損を防ぐ）
  const quote = (value) => "'" + String(value).replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\\\'") + "'";
  // id が CSS 識別子として妥当か（数字始まり・空白・記号を含む id は #id で引けない）
  const isCssIdent = (value) => /^[A-Za-z_-][A-Za-z0-9_-]*$/.test(value);
  const attr = (el, name) => (el.getAttribute ? el.getAttribute(name) : null) || '';
  // 優先順のセレクタ候補配列を返す。
  // 順序の判断: data-testid / data-test を #id より先に置く。
  //   理由 = テスト用属性は「テストから引くために人が明示的に付けた」ものなので意味が安定する。
  //   一方 id は React/Angular 等が実行時に採番する動的値（例: :r3:, mui-142）であることがあり、
  //   セッションを跨ぐと変わりうる。よって安定度の高い順に testid → id とする。
  const describeAll = (el) => {
    if (!el || !el.tagName) return [];
    const tag = el.tagName.toLowerCase();
    const candidates = [];
    const testid = attr(el, 'data-testid');
    if (testid) candidates.push('[data-testid=' + quote(testid) + ']');
    const dataTest = attr(el, 'data-test');
    if (dataTest) candidates.push('[data-test=' + quote(dataTest) + ']');
    if (el.id && isCssIdent(el.id)) candidates.push('#' + el.id);
    const name = attr(el, 'name');
    if (name) candidates.push(tag + '[name=' + quote(name) + ']');
    const ariaLabel = attr(el, 'aria-label');
    if (ariaLabel) candidates.push('[aria-label=' + quote(ariaLabel) + ']');
    // 改行・連続空白は 1 スペースへ潰す（select の option 群などで
    // 改行入りの :has-text セレクタになるのを防ぐ）。テキストは 40 文字で切る。
    const text = (el.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 40);
    candidates.push(tag + (text ? ':has-text("' + text.replace(/"/g, '\\\\"') + '")' : ''));
    // 重複除去（同じ候補を heal に 2 回渡さない）
    return candidates.filter((sel, index) => candidates.indexOf(sel) === index);
  };
  const describe = (el) => {
    const candidates = describeAll(el);
    return candidates.length ? candidates[0] : '';
  };
  // 既存 push 経路を保ったまま selectors を足すための共通ヘルパ
  const pushWithSelectors = (event, el) => {
    const candidates = describeAll(el);
    event.selector = candidates.length ? candidates[0] : '';
    event.selectors = candidates;
    window.__ws2dEvents.push(event);
  };
  const clip = (value) => String(value == null ? '' : value).slice(0, MAX_VALUE_LEN);
  const interactive =
    'a, button, [role=button], input, select, textarea, summary, [role=tab], [aria-expanded]';
  document.addEventListener('click', (event) => {
    const el = (event.target.closest && event.target.closest(interactive)) || event.target;
    // 操作ウィジェット自身のクリックは操作イベントとして二重記録しない（専用ハンドラで処理する）
    if (el && WIDGET_IDS.indexOf(el.id) >= 0) return;
    pushWithSelectors({ type: 'click' }, el);
  }, true);
  // type="password" だけを見ると取りこぼす秘密情報がある。実際に多いのは
  // 「パスワードを表示」トグルで type が text に変わる実装で、この瞬間に
  // 平文が記録されてしまう。名前・id・autocomplete からも秘密情報を判定する。
  // 判定は広めに倒す（記録できない項目が増える方が、平文が残るより安全）。
  const SECRET_HINT = /pass|passwd|pwd|secret|token|otp|one-?time|cvv|cvc|card|credit|\bcc[-_]?(num|number)?\b|pin|security-?code|credential|ssn|social-?security/i;
  const isSecretField = (el) => {
    const probe = [
      attr(el, 'name'), el.id || '', attr(el, 'autocomplete'),
      attr(el, 'aria-label'), attr(el, 'data-testid'),
    ].join(' ');
    return SECRET_HINT.test(probe);
  };

  document.addEventListener('change', (event) => {
    const el = event.target;
    if (!el || !el.tagName) return;
    const tag = el.tagName.toLowerCase();
    const inputType = (attr(el, 'type') || '').toLowerCase();
    const payload = { type: 'input', tag: tag, input_type: inputType };
    if (inputType === 'password' || isSecretField(el)) {
      // 必須要件: 平文の秘密情報を JSONL に残さない。値を持たず masked のみを記録する。
      payload.masked = true;
    } else if (inputType === 'checkbox' || inputType === 'radio') {
      payload.checked = !!el.checked;
      payload.value = clip(el.value);
    } else if (tag === 'select') {
      const selected = Array.prototype.slice.call(el.selectedOptions || []);
      payload.value = clip(el.value);
      payload.option_text = clip(selected.map((opt) => (opt.text || '').trim()).join(', '));
    } else {
      payload.value = clip(el.value);
    }
    pushWithSelectors(payload, el);
  }, true);
  document.addEventListener('keydown', (event) => {
    if (PRESS_KEYS.indexOf(event.key) < 0) return;
    pushWithSelectors({ type: 'press', key: event.key }, event.target);
  }, true);
  const makeWidgetButton = (id, label, background, bottom, onActivate) => {
    const btn = document.createElement('button');
    btn.id = id;
    btn.type = 'button';
    btn.textContent = label;
    btn.style.cssText =
      'position:fixed;right:12px;bottom:' + bottom + 'px;z-index:2147483647;' +
      'padding:8px 14px;background:' + background + ';color:#fff;border:none;' +
      'border-radius:4px;font-size:13px;cursor:pointer;' +
      'box-shadow:0 1px 4px rgba(0,0,0,0.3);';
    btn.addEventListener('click', (event) => {
      event.stopPropagation();
      onActivate();
    });
    return btn;
  };
  const selectedText = () => {
    try {
      return (window.getSelection() || '').toString().trim().slice(0, MAX_VALUE_LEN);
    } catch (err) {
      return '';
    }
  };
  const injectFindingWidget = () => {
    if (document.getElementById(FINDING_BTN_ID) || !document.body) return;
    document.body.appendChild(
      makeWidgetButton(FINDING_BTN_ID, '⚑ 気づき', '#d93025', 12, () => {
        const note = window.prompt('気づきメモ（空でも可）', '') || '';
        window.__ws2dEvents.push({ type: 'finding', note: note });
      })
    );
    document.body.appendChild(
      // 選択中テキストを初期値に入れる（画面から文言をコピーする手間を省く）
      makeWidgetButton(ASSERT_BTN_ID, '✔ 検証', '#1a73e8', 52, () => {
        const text = window.prompt('この画面に表示されているべきテキスト', selectedText());
        if (text) window.__ws2dEvents.push({ type: 'assert_text', text: text });
      })
    );
    document.body.appendChild(
      makeWidgetButton(WAIT_BTN_ID, '⏳ 待機', '#5f6368', 92, () => {
        const text = window.prompt('表示されるまで待つテキスト', selectedText());
        if (text) window.__ws2dEvents.push({ type: 'wait_text', text: text });
      })
    );
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


# 「期待」を宣言するイベント型 → JSONL の kind 対応（DOM 操作ではないため action と分ける）
_TEXT_EXPECTATION_KINDS = {"assert_text": "assertion", "wait_text": "wait"}

# 操作イベントに任意で付く拡張フィールド（存在する時だけ JSONL に落とす）。
# 下流は kind / selector しか読まないため、追加は純粋な上位互換になる。
_OPTIONAL_ACTION_FIELDS = ("tag", "input_type", "option_text", "key")


def _action_record(event: dict[str, Any], event_type: str, url: str) -> dict[str, Any]:
    """ブラウザ側の操作イベント 1 件を JSONL レコードへ変換する。

    selector（先頭候補・従来キー）は必ず残し、selectors（優先順の候補配列）を追加する。
    value 等は存在する時のみ入れる（password は JS 側で masked に置換済みで値が来ない）。
    """
    selectors = [str(sel) for sel in event.get("selectors") or [] if str(sel)]
    selector = str(event.get("selector") or "") or (selectors[0] if selectors else "")
    record: dict[str, Any] = {
        "kind": "action",
        "action_type": event_type,
        "selector": selector,
        "selectors": selectors or ([selector] if selector else []),
        "url": url,
        "path": normalize_footprint_path(url),
    }
    for key in _OPTIONAL_ACTION_FIELDS:
        if event.get(key) not in (None, ""):
            record[key] = str(event[key])
    # value は空文字も意味を持つ（入力をクリアした操作）ため、キーの有無で判定する
    if "value" in event and event.get("value") is not None:
        record["value"] = str(event["value"])
    # 真偽値は "" と区別が要るので個別に扱う（checkbox 未チェック=False を落とさない）
    if event.get("masked"):
        record["masked"] = True
    if isinstance(event.get("checked"), bool):
        record["checked"] = bool(event["checked"])
    return record


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
                if event_type in _TEXT_EXPECTATION_KINDS:
                    # assert_text / wait_text は DOM 操作ではなく「期待」の宣言なので
                    # kind: "action" に混ぜず専用 kind（assertion / wait）で落とす。
                    # 理由: reverse_generator._build_case は action をセレクタ付き手順として
                    # 文章化し、coverage は action を操作数に数える。セレクタを持たない
                    # これらを action にすると「「」を操作」という空手順と操作数の水増しが
                    # 発生する。未知 kind は既存の下流（reverse_generator / coverage /
                    # finding_reporter）がいずれも無視するため、追加しても互換は壊れない。
                    self._append(
                        {
                            "kind": _TEXT_EXPECTATION_KINDS[event_type],
                            "action_type": event_type,
                            "text": str(event.get("text") or ""),
                            "url": url,
                            "path": normalize_footprint_path(url),
                            "state_id": self._last_state_sig,
                        }
                    )
                    recorded += 1
                    continue
                # click / input / press は実操作なので従来どおり kind: "action"。
                # press は _ACTION_VERBS 未登録だが、下流は get() のフォールバックで
                # 「操作」と表現するだけなので例外にならない（互換維持）。
                self._append(_action_record(event, event_type, url))
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
