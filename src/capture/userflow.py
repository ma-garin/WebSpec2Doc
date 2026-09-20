"""記録イベント ⇔ user-flow JSON（Recorder 互換）の相互変換。

正本形式は Chrome DevTools Recorder の user-flow JSON（@puppeteer/replay の
Schema と互換）で、独自情報は各 step の `ws2d` キーに置く。Selenium IDE
`.side` は取り込み（import）のみ対応する。LLM は使わず、記録・取り込んだ
イベント列をそのまま変換するだけ（evidence-only 原則: 推定・言い換えをしない）。

本モジュールの関数は純粋（同じ入力には同じ出力を返す）。ディスクに触れるのは
`load_recording` / `save_user_flow` のみで、他の関数はファイル IO を行わない。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

SESSIONS_DIR_NAME = "sessions"

# Playwright の既定ビューポート（記録時のイベントに幅・高さの情報が無いため、
# user-flow 生成時の setViewport はこの既定値で補う）。
DEFAULT_VIEWPORT_WIDTH = 1280
DEFAULT_VIEWPORT_HEIGHT = 720

_SESSION_NUMBER_RE = re.compile(r"(\d+)")
_ENTER_PLACEHOLDER = "${KEY_ENTER}"

# --- events -> user-flow -----------------------------------------------------


def events_to_user_flow(
    events: list[dict[str, Any]], *, session: str, domain: str, title: str = ""
) -> dict[str, Any]:
    """記録イベント列（JSONL 1 行 = 1 dict）を Recorder 互換の user-flow JSON へ変換する。

    kind="state" のイベントは step を生成せず、以降の step の `ws2d.state_id`
    を更新するためだけに使う（kind="visit" で "default" にリセットする）。
    kind="finding" も step にはせず、flow 直下の `ws2d.findings` に集める。
    """
    steps: list[dict[str, Any]] = [_initial_viewport_step()]
    findings: list[dict[str, Any]] = []
    current_state_id = "default"

    for event in events:
        kind = str(event.get("kind") or "")
        if kind == "visit":
            current_state_id = "default"
            steps.append(_step_navigate(event, order=len(steps), state_id=current_state_id))
        elif kind == "action":
            action_type = str(event.get("action_type") or "")
            if action_type == "click":
                steps.append(_step_click(event, order=len(steps), state_id=current_state_id))
            elif action_type == "input":
                steps.append(_step_change(event, order=len(steps), state_id=current_state_id))
            elif action_type == "keydown":
                steps.append(_step_key_down(event, order=len(steps), state_id=current_state_id))
                steps.append(_step_key_up(event, order=len(steps), state_id=current_state_id))
            else:
                logger.warning("events_to_user_flow: 未対応の action_type を無視: %s", action_type)
        elif kind == "state":
            current_state_id = str(event.get("state_id") or current_state_id)
        elif kind == "finding":
            findings.append(
                {
                    "after_step": steps[-1]["ws2d"]["order"],
                    "note": event.get("note", ""),
                    "url": event.get("url", ""),
                    "state_id": event.get("state_id", current_state_id),
                }
            )
        else:
            logger.warning("events_to_user_flow: 未対応の kind を無視: %s", kind)

    recorded_at = str(events[0].get("ts")) if events and events[0].get("ts") else ""
    return {
        "title": title or _default_title(domain, session),
        "steps": steps,
        "ws2d": {
            "session": session,
            "domain": domain,
            "recorded_at": recorded_at,
            "source": "recorded",
            "findings": findings,
        },
    }


def _default_title(domain: str, session: str) -> str:
    match = _SESSION_NUMBER_RE.search(session)
    number = match.group(1) if match else session
    return f"{domain} 探索セッション {number}"


def _initial_viewport_step() -> dict[str, Any]:
    return {
        "type": "setViewport",
        "width": DEFAULT_VIEWPORT_WIDTH,
        "height": DEFAULT_VIEWPORT_HEIGHT,
        "deviceScaleFactor": 1,
        "isMobile": False,
        "hasTouch": False,
        "isLandscape": False,
        "ws2d": {"order": 0},
    }


def _selectors_from_event(event: dict[str, Any]) -> list[list[str]]:
    """§1: `selectors` があればそれを、無ければ `[[selector]]` を候補列とする。"""
    selectors = event.get("selectors")
    if selectors:
        return [[str(item) for item in group] for group in selectors]
    return [[str(event.get("selector") or "")]]


def _ws2d_common(event: dict[str, Any], *, order: int, state_id: str) -> dict[str, Any]:
    ws2d: dict[str, Any] = {"order": order}
    if state_id:
        ws2d["state_id"] = state_id
    for key in ("screenshot", "url", "title", "ts", "masked", "input_type"):
        value = event.get(key)
        if value is not None:
            ws2d[key] = value
    return ws2d


def _step_navigate(event: dict[str, Any], *, order: int, state_id: str) -> dict[str, Any]:
    url = str(event.get("url") or "")
    title = str(event.get("title") or "")
    return {
        "type": "navigate",
        "url": url,
        "assertedEvents": [{"type": "navigation", "url": url, "title": title}],
        "ws2d": _ws2d_common(event, order=order, state_id=state_id),
    }


def _step_click(event: dict[str, Any], *, order: int, state_id: str) -> dict[str, Any]:
    return {
        "type": "click",
        "target": "main",
        "selectors": _selectors_from_event(event),
        "offsetX": 0,
        "offsetY": 0,
        "ws2d": _ws2d_common(event, order=order, state_id=state_id),
    }


def _step_change(event: dict[str, Any], *, order: int, state_id: str) -> dict[str, Any]:
    return {
        "type": "change",
        "selectors": _selectors_from_event(event),
        "value": str(event.get("value") or ""),
        "ws2d": _ws2d_common(event, order=order, state_id=state_id),
    }


def _step_key_down(event: dict[str, Any], *, order: int, state_id: str) -> dict[str, Any]:
    return {
        "type": "keyDown",
        "key": str(event.get("key") or ""),
        "ws2d": _ws2d_common(event, order=order, state_id=state_id),
    }


def _step_key_up(event: dict[str, Any], *, order: int, state_id: str) -> dict[str, Any]:
    return {
        "type": "keyUp",
        "key": str(event.get("key") or ""),
        "ws2d": _ws2d_common(event, order=order, state_id=state_id),
    }


# --- user-flow -> events ------------------------------------------------------

_NAVIGATE_KNOWN_KEYS = {"type", "url", "assertedEvents"}
_CLICK_KNOWN_KEYS = {"type", "target", "selectors", "offsetX", "offsetY"}
_CHANGE_KNOWN_KEYS = {"type", "selectors", "value"}
_KEY_DOWN_KNOWN_KEYS = {"type", "key"}
_NON_EVENT_STEP_TYPES = {"setViewport", "keyUp"}
_PROMOTABLE_WS2D_KEYS = ("ts", "screenshot", "title", "masked", "input_type", "state_id", "url")


def user_flow_to_events(flow: dict[str, Any], *, session: str) -> list[dict[str, Any]]:
    """user-flow JSON を記録イベント列（JSONL 1 行相当の dict のリスト）へ変換する。

    自前で生成した flow（`ws2d` 付き）だけでなく、Chrome DevTools Recorder の
    書き出しそのまま（`ws2d` 無し）も読める。未対応の step type は無視して
    件数をログに出す（戻り値のイベントには含めない）。`setViewport` / `keyUp`
    はそれ自体では独立したイベントを作らない既知の type として黙って読み飛ばす
    （`keyUp` は対になる `keyDown`側で `action(keydown)` として記録済み）。
    """
    events: list[dict[str, Any]] = []
    ignored = 0
    steps = flow.get("steps") or []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            ignored += 1
            continue
        step_type = str(step.get("type") or "")
        if step_type == "navigate":
            events.append(_event_from_navigate(step, index=index))
        elif step_type == "click":
            events.append(_event_from_click(step, index=index))
        elif step_type == "change":
            events.append(_event_from_change(step, index=index))
        elif step_type == "keyDown":
            events.append(_event_from_key_down(step, index=index))
        elif step_type in _NON_EVENT_STEP_TYPES:
            continue
        else:
            ignored += 1
            logger.info(
                "user_flow_to_events: 未対応の step type を無視（session=%s）: %s",
                session,
                step_type,
            )
    if ignored:
        logger.info(
            "user_flow_to_events: %d 件の step を無視しました（session=%s）", ignored, session
        )
    return events


def _promoted_ws2d_fields(step: dict[str, Any]) -> dict[str, Any]:
    """自前 flow の `step.ws2d` から event 側へ昇格させる既知フィールドを取り出す。"""
    own = step.get("ws2d")
    if not isinstance(own, dict):
        return {}
    return {key: own[key] for key in _PROMOTABLE_WS2D_KEYS if own.get(key) is not None}


def _event_ws2d(step: dict[str, Any], *, index: int, known_step_keys: set[str]) -> dict[str, Any]:
    """未知の Recorder step フィールドを退避しつつ、step の索引を `order` に積む。"""
    own = step.get("ws2d")
    ws2d: dict[str, Any] = dict(own) if isinstance(own, dict) else {}
    for key, value in step.items():
        if key != "ws2d" and key not in known_step_keys and key not in ws2d:
            ws2d[key] = value
    ws2d.setdefault("order", index)
    return ws2d


def _event_from_navigate(step: dict[str, Any], *, index: int) -> dict[str, Any]:
    url = str(step.get("url") or "")
    event: dict[str, Any] = {"kind": "visit", "url": url, "path": _normalize_path(url)}
    promoted = _promoted_ws2d_fields(step)
    for key in ("ts", "screenshot", "title", "masked", "input_type"):
        if key in promoted:
            event[key] = promoted[key]
    if "title" not in event:
        asserted = step.get("assertedEvents") or []
        if asserted and isinstance(asserted[0], dict) and asserted[0].get("title"):
            event["title"] = str(asserted[0]["title"])
    event.setdefault("ts", "")
    event["ws2d"] = _event_ws2d(step, index=index, known_step_keys=_NAVIGATE_KNOWN_KEYS)
    return event


def _selector_groups(step: dict[str, Any]) -> list[list[str]]:
    raw = step.get("selectors") or []
    return [[str(item) for item in group] for group in raw if isinstance(group, list)]


def _fill_common_action_fields(event: dict[str, Any], step: dict[str, Any]) -> None:
    promoted = _promoted_ws2d_fields(step)
    url = str(promoted.get("url") or "")
    event["url"] = url
    event["path"] = _normalize_path(url)
    for key in ("ts", "screenshot", "title", "masked", "input_type", "state_id"):
        if key in promoted:
            event[key] = promoted[key]
    event.setdefault("ts", "")


def _event_from_click(step: dict[str, Any], *, index: int) -> dict[str, Any]:
    selectors = _selector_groups(step)
    event: dict[str, Any] = {
        "kind": "action",
        "action_type": "click",
        "selector": selectors[0][0] if selectors and selectors[0] else "",
        "selectors": selectors,
    }
    _fill_common_action_fields(event, step)
    event["ws2d"] = _event_ws2d(step, index=index, known_step_keys=_CLICK_KNOWN_KEYS)
    return event


def _event_from_change(step: dict[str, Any], *, index: int) -> dict[str, Any]:
    selectors = _selector_groups(step)
    event: dict[str, Any] = {
        "kind": "action",
        "action_type": "input",
        "selector": selectors[0][0] if selectors and selectors[0] else "",
        "selectors": selectors,
        "value": str(step.get("value") or ""),
    }
    _fill_common_action_fields(event, step)
    event["ws2d"] = _event_ws2d(step, index=index, known_step_keys=_CHANGE_KNOWN_KEYS)
    return event


def _event_from_key_down(step: dict[str, Any], *, index: int) -> dict[str, Any]:
    event: dict[str, Any] = {
        "kind": "action",
        "action_type": "keydown",
        "selector": "",
        "key": str(step.get("key") or ""),
    }
    _fill_common_action_fields(event, step)
    event["ws2d"] = _event_ws2d(step, index=index, known_step_keys=_KEY_DOWN_KNOWN_KEYS)
    return event


def _normalize_path(url: str) -> str:
    """URL をイベントの path 照合用に正規化する（session_recorder と同一アルゴリズム）。"""
    if not url:
        return "/"
    path = urlparse(url).path.rstrip("/").lower()
    return path or "/"


# --- Selenium IDE .side -> user-flow ------------------------------------------


def side_to_user_flow(side: dict[str, Any]) -> list[dict[str, Any]]:
    """Selenium IDE `.side`（version "2.0"/"3.0"、tests[].commands[]）を
    test ごとに 1 flow へ変換する。対応外の command / target は無視して数え、
    ログに件数を出す（LLM は使わず evidence-only: 推定・補完はしない）。
    """
    base_url = str(side.get("url") or "")
    domain = urlparse(base_url).netloc
    flows: list[dict[str, Any]] = []
    for test_index, test in enumerate(side.get("tests") or []):
        if not isinstance(test, dict):
            continue
        steps: list[dict[str, Any]] = []
        ignored = 0
        for command in test.get("commands") or []:
            if not isinstance(command, dict):
                ignored += 1
                continue
            built = _side_command_to_steps(command, base_url=base_url)
            if built:
                steps.extend(built)
            else:
                ignored += 1
        if not steps or steps[0].get("type") != "setViewport":
            steps.insert(0, _initial_viewport_step())
        for order, step in enumerate(steps):
            step.setdefault("ws2d", {})
            step["ws2d"]["order"] = order
        test_name = str(test.get("name") or "")
        if ignored:
            logger.info(
                "side_to_user_flow: %d 件のコマンドを無視しました（test=%s）", ignored, test_name
            )
        session = str(test.get("name") or test.get("id") or f"side_test_{test_index + 1}")
        flows.append(
            {
                "title": test_name or str(side.get("name") or ""),
                "steps": steps,
                "ws2d": {
                    "session": session,
                    "domain": domain,
                    "recorded_at": "",
                    "source": "imported:side",
                    "findings": [],
                },
            }
        )
    return flows


def _side_target_to_selector(target: str) -> str | None:
    """.side の target 記法を Recorder 形式のセレクタ文字列へ変換する。"""
    if target.startswith("id="):
        return "#" + target[len("id=") :]
    if target.startswith("name="):
        return f"[name='{target[len('name='):]}']"
    if target.startswith("css="):
        return target[len("css=") :]
    if target.startswith("xpath="):
        return "xpath/" + target[len("xpath=") :]
    if target.startswith("linkText="):
        return "text/" + target[len("linkText=") :]
    return None


def _parse_window_size(value: str) -> tuple[int, int]:
    try:
        width_str, height_str = value.lower().split("x", 1)
        return int(width_str), int(height_str)
    except (ValueError, AttributeError):
        return DEFAULT_VIEWPORT_WIDTH, DEFAULT_VIEWPORT_HEIGHT


def _side_command_to_steps(command: dict[str, Any], *, base_url: str) -> list[dict[str, Any]]:
    name = str(command.get("command") or "")
    target = str(command.get("target") or "")
    value = str(command.get("value") or "")

    if name == "open":
        url = urljoin(base_url, target) if base_url else target
        return [
            {
                "type": "navigate",
                "url": url,
                "assertedEvents": [{"type": "navigation", "url": url, "title": ""}],
                "ws2d": {},
            }
        ]

    if name in ("click", "clickAt", "check", "uncheck"):
        selector = _side_target_to_selector(target)
        if selector is None:
            return []
        return [
            {
                "type": "click",
                "target": "main",
                "selectors": [[selector]],
                "offsetX": 0,
                "offsetY": 0,
                "ws2d": {},
            }
        ]

    if name in ("type", "sendKeys"):
        selector = _side_target_to_selector(target)
        if selector is None:
            return []
        steps: list[dict[str, Any]] = []
        text = value
        enter = text.endswith(_ENTER_PLACEHOLDER)
        if enter:
            text = text[: -len(_ENTER_PLACEHOLDER)]
        if text:
            steps.append({"type": "change", "selectors": [[selector]], "value": text, "ws2d": {}})
        if enter:
            steps.append({"type": "keyDown", "key": "Enter", "ws2d": {}})
            steps.append({"type": "keyUp", "key": "Enter", "ws2d": {}})
        return steps

    if name == "select":
        selector = _side_target_to_selector(target)
        if selector is None:
            return []
        option = value[len("label=") :] if value.startswith("label=") else value
        return [{"type": "change", "selectors": [[selector]], "value": option, "ws2d": {}}]

    if name == "setWindowSize":
        width, height = _parse_window_size(value)
        return [
            {
                "type": "setViewport",
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "isMobile": False,
                "hasTouch": False,
                "isLandscape": False,
                "ws2d": {},
            }
        ]

    if name == "mouseOver":
        selector = _side_target_to_selector(target)
        if selector is None:
            return []
        return [{"type": "hover", "selectors": [[selector]], "ws2d": {}}]

    return []


# --- load / save（ディスクに触れるのはここだけ） --------------------------------


def _session_domain_from_path(path: Path) -> tuple[str, str]:
    session = path.stem
    parent = path.parent
    domain = parent.parent.name if parent.name == SESSIONS_DIR_NAME else parent.name
    return session, domain


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(json.loads(line))
    return events


def _ensure_ws2d(
    flow_data: dict[str, Any], *, session: str, domain: str, source: str
) -> dict[str, Any]:
    flow = dict(flow_data)
    ws2d = dict(flow.get("ws2d") or {})
    ws2d.setdefault("session", session)
    ws2d.setdefault("domain", domain)
    ws2d.setdefault("recorded_at", "")
    ws2d.setdefault("source", source)
    ws2d.setdefault("findings", [])
    flow["ws2d"] = ws2d
    flow.setdefault("title", "")
    flow.setdefault("steps", [])
    return flow


def load_recording(path: Path) -> tuple[dict[str, Any], str]:
    """拡張子と中身から記録データの種類を判定し、user-flow JSON へ変換する。

    `.jsonl` は探索セッションの JSONL（`events_to_user_flow`）、`.side` は
    Selenium IDE の書き出し（`side_to_user_flow` の先頭 test）、それ以外の
    `.json` は Chrome DevTools Recorder の書き出しとして扱う。ディスクを
    読むのはこの関数だけで、変換処理自体は他の関数同様に純粋。
    戻り値は `(flow, source)`。
    """
    suffix = path.suffix.lower()
    session, domain = _session_domain_from_path(path)

    if suffix == ".jsonl":
        events = _read_jsonl(path)
        flow = events_to_user_flow(events, session=session, domain=domain)
        return flow, str(flow["ws2d"]["source"])

    if suffix == ".side":
        side_data = json.loads(path.read_text(encoding="utf-8"))
        flows = side_to_user_flow(side_data)
        if not flows:
            raise ValueError(f".side にテストが含まれていません: {path}")
        flow = flows[0]
        return flow, str(flow["ws2d"]["source"])

    flow_data = json.loads(path.read_text(encoding="utf-8"))
    flow = _ensure_ws2d(flow_data, session=session, domain=domain, source="imported:chrome")
    return flow, str(flow["ws2d"]["source"])


def save_user_flow(flow: dict[str, Any], path: Path) -> None:
    """user-flow JSON をファイルへ書き出す（ensure_ascii=False, indent=2）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(flow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
