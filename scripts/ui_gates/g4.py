"""G-4 状態注入（仕様 §7.5）。画面ごとに empty / 500 / 403 / loading を注入し .ui-state を数える。"""
from __future__ import annotations

import json
import os

import yaml

FIXTURE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            "quality", "ui_state_fixtures.yml")
STATES = ("empty", "500", "403", "loading")
LOADING_DELAY_S = 10
SETTLE_S = 3

JS_UI_STATE = r"""() => {
  const vis = e => e.offsetParent !== null && !e.closest('[hidden]');
  const st = [...document.querySelectorAll('.ui-state')].filter(vis);
  return {
    states: st.length,
    btns: st.length ? st[0].querySelectorAll('.c-btn').length : 0,
    loading: [...document.querySelectorAll('[data-kind="loading"]')].filter(vis).length,
  };
}"""


def load_fixtures(path: str = FIXTURE_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _handler(state: str, fx: dict):
    def handle(route):
        if state == "loading":
            import time
            time.sleep(LOADING_DELAY_S)
            return route.continue_()
        if state == "empty":
            return route.fulfill(status=200, content_type="application/json",
                                 body=json.dumps((fx.get("empty") or {}).get("body", {})))
        return route.fulfill(status=int(state), content_type="application/json",
                             body=json.dumps({"error": "injected"}))
    return handle


def check(browser_ctx, base: str, path: str, fixtures: dict | None = None) -> list[str]:
    """browser_ctx は Playwright の BrowserContext（状態ごとに新しいページを開く）。
    戻り値は ["G-4: ...", ...]。fixture 無しは "G-4 未検査: <path>" を 1 件返す（合格に数えない）。"""
    fixtures = load_fixtures() if fixtures is None else fixtures
    fx = fixtures.get(path)
    if fx and fx.get("skip"):
        return []  # skip の値は理由。データ取得領域を持たない画面は対象外
    if not fx:
        return [f"G-4 未検査: {path}"]
    out: list[str] = []
    for state in STATES:
        page = browser_ctx.new_page()
        try:
            for pat in fx.get("apis", []):
                page.route(pat, _handler(state, fx))
            page.goto(base + path, wait_until="commit" if state == "loading" else "networkidle", timeout=30000)
            page.wait_for_timeout(1500 if state == "loading" else 500)
            r = page.evaluate(JS_UI_STATE)
            if r["states"] != 1:
                out.append(f"G-4: {state} 注入時の .ui-state が {r['states']} 個（1 個であるべき）")
            elif state == "loading" and r["btns"] != 0:
                out.append(f"G-4: loading の .ui-state 内 .c-btn が {r['btns']} 個（0 個であるべき）")
            elif state != "loading" and r["btns"] != 1:
                out.append(f"G-4: {state} の .ui-state 内 .c-btn が {r['btns']} 個（1 個であるべき）")
        except Exception as e:  # 注入の失敗は合格にしない
            out.append(f"G-4: {state} 注入に失敗: {type(e).__name__}")
        finally:
            page.close()
    page = browser_ctx.new_page()
    try:
        page.goto(base + path, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(SETTLE_S * 1000)
        if page.evaluate(JS_UI_STATE)["loading"]:
            out.append("G-4: 正常応答に戻して 3 秒後も loading が残っている")
    except Exception as e:
        out.append(f"G-4: 復帰確認に失敗: {type(e).__name__}")
    finally:
        page.close()
    return out
