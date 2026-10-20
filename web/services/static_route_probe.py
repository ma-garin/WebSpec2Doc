"""静的 route 候補の到達確認（System 03）。

System 01 のリバース解析が見つけた「到達未確認の静的 route 候補」を、GET の遷移だけで開き、
アプリがその URL に留まった実測があるものだけ observed にする。

安全策: GET/HEAD/OPTIONS 以外のリクエストは全て遮断し、クリック・入力・送信はしない。
静的候補（reverse_analysis.json）は書き換えない。結果は route_probe.json に保存する
（形式は static_route_probe_store を参照）。

ブラウザ操作は ``open_navigator`` に差し替えられる（テストは fake を渡す）。
navigator は ``goto(url) -> NavResult``（失敗は NavError）と、任意で ``states() -> int | None`` を持つ。

認証状態の再利用: 未認証の探索で auth_required だった route だけ、System 01 が保存した
<出力>/<domain>/auth.json（Playwright storage_state）付きの新しい context で 1 回だけ再探索する。
auth.json の中身は読まず、ログ・API 応答・保存 JSON にパスも中身も出さない
（``open_navigator(storage_state=<path>)`` に渡すだけ）。使うのは通常ファイルで出力配下に resolve できるものだけ。
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from web.services import reverse_analysis_run as runner
from web.services import static_route_probe_store as store
from web.services.rea_test_viewpoints import build_viewpoints

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
GOTO_TIMEOUT_MS = 15000
_AUTH_WORDS = ("login", "signin", "sign-in", "auth")
_JST = timezone(timedelta(hours=9))

_running: set[str] = set()
_running_lock = threading.Lock()


@dataclass(frozen=True)
class NavResult:
    http_status: int | None
    final_url: str


class NavError(Exception):
    """遷移の失敗。kind は "timeout" | "error"（生の例外文は持ち回らない）。"""

    def __init__(self, kind: str = "error") -> None:
        super().__init__(kind)
        self.kind = kind


@dataclass(frozen=True)
class ProbeRun:
    result: str  # success | busy | no_rea | error
    message: str
    next_action: str


OpenNavigator = Callable[[], AbstractContextManager[Any]]


def is_running(domain: str) -> bool:
    with _running_lock:
        return domain in _running


# ------------------------------------------------------------------ 分類


def norm_path(path: str) -> str:
    path = path or "/"
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/") or "/"


def needs_value(route: str) -> bool:
    """値の推測が要る route（パラメータ・ワイルドカード・値なし）。開かない。"""
    value = (route or "").strip()
    return not value or ":" in value or "*" in value or value.startswith("（")


def build_url(origin: str, route: str) -> str:
    return origin.rstrip("/") + "/" + route.strip().lstrip("/")


def _is_safe_target(url: str) -> bool:
    from crawler.url_safety import is_safe_target

    return is_safe_target(url)


LIMIT_REACH = "URL への到達だけを確認。画面内容・機能の正しさは未確認"
LIMIT_AUTH = "System01 で保存済みの認証状態を使用"
REASON_AUTH_EXPIRED = "保存済みの認証状態でもログイン画面へ移動した（期限切れの可能性）"
REASON_NO_AUTH = "保存済みの認証状態がありません"


def auth_state_path(base: Path, domain: str) -> Path | None:
    """System 01 が保存した auth.json。通常ファイル（symlink 不可）で出力配下に resolve できるときだけ返す。"""
    try:
        path = base / domain / "auth.json"
        if path.is_symlink() or not path.is_file():
            return None
        resolved = path.resolve()
        if not resolved.is_relative_to(base.resolve()):
            return None
        return resolved
    except (OSError, ValueError):
        return None


def _decorate(res: dict[str, Any], authenticated: bool, attempted: bool) -> dict[str, Any]:
    """認証の有無・観測した事実・限界を付ける（auth.json のパスや中身は入れない）。"""
    st, final = res["status"], res.get("final_url")
    if st == "observed":
        evidence = f"GET の遷移で最終 URL {final} に留まった" + ("（認証状態あり）" if authenticated else "")
        limit = LIMIT_REACH + (f"。{LIMIT_AUTH}" if authenticated else "")
    elif st == "auth_required":
        evidence = f"GET の遷移でログイン画面（最終 URL {final}）へ移動した" + ("（認証状態あり）" if authenticated else "")
        limit = "ログイン画面までしか観測できず、この route の内容は未確認"
    elif st == "unreached":
        evidence = (f"GET の応答が HTTP {res['http_status']} だった" if (res.get("http_status") or 0) >= 400
                    else f"GET の遷移で別の URL（{final}）へ移動した") + ("（認証状態あり）" if authenticated else "")
        limit = "この route への到達は確認できていない"
    elif st == "ambiguous":
        evidence, limit = "パラメータの値が必要なため開かなかった", "値を推測しないため到達は未確認"
    else:
        evidence, limit = f"{res['reason']}", "到達は未確認"
    return {**res, "authenticated": authenticated, "auth_attempted": attempted,
            "evidence": evidence, "limitation": limit}  # fmt: skip


def classify_route(origin: str, route: str, navigator: Any, *, authenticated: bool = False) -> dict[str, Any]:
    """route 値 1 つを分類する。evidence_id を含まない結果（共通部分）を返す。

    authenticated=True は認証状態付き navigator での再探索（auth_required は期限切れの可能性として扱う）。
    """
    res = _classify_core(origin, route, navigator)
    if authenticated and res["status"] == "auth_required":
        res = {**res, "reason": REASON_AUTH_EXPIRED}
    return _decorate(res, authenticated, authenticated)


def _classify_core(origin: str, route: str, navigator: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"url": None, "http_status": None, "final_url": None,
                            "observed_at": None, "states_found": None}  # fmt: skip
    if needs_value(route):
        return {**base, "status": "ambiguous", "reason": "パラメータの値が必要（値を推測しない）"}
    url = build_url(origin, route)
    if not _is_safe_target(url):
        return {**base, "status": "failed", "reason": "安全に開けない宛先のため確認しなかった"}
    base["url"] = url
    try:
        nav = navigator.goto(url)
    except NavError as exc:
        why = "時間内に読み込みが終わらなかった" if exc.kind == "timeout" else "ページを開けなかった"
        return {**base, "status": "failed", "reason": f"確認に失敗した（{why}）"}
    except Exception:  # noqa: BLE001  生の例外文を利用者に出さない
        return {**base, "status": "failed", "reason": "確認に失敗した（ページを開けなかった）"}
    base["http_status"], base["final_url"] = nav.http_status, nav.final_url
    if nav.http_status is not None and nav.http_status >= 400:
        return {**base, "status": "unreached", "reason": f"ページが応答しなかった（HTTP {nav.http_status}）"}
    want = norm_path(urlparse(url).path)
    got = norm_path(urlparse(nav.final_url or "").path)
    if got == want:
        found = _count_states(navigator)
        return {**base, "status": "observed", "reason": "GET の遷移でこの URL に到達し、留まった",
                "observed_at": datetime.now(_JST).isoformat(timespec="seconds"), "states_found": found}  # fmt: skip
    if any(w in got.lower() for w in _AUTH_WORDS):
        return {**base, "status": "auth_required", "reason": "ログイン画面へ移動した"}
    return {**base, "status": "unreached", "reason": f"別の画面（{got}）へ移動した"}


def _count_states(navigator: Any) -> int | None:
    """到達できたページの補足根拠。失敗しても判定には影響させない。"""
    states = getattr(navigator, "states", None)
    if states is None:
        return None
    try:
        return states()
    except Exception:  # noqa: BLE001
        return None


def _reprobe_with_auth(origin: str, by_value: dict[str, dict[str, Any]],
                       open_auth_navigator: OpenNavigator) -> None:  # fmt: skip
    """auth_required の route だけ、認証状態付きの新しい context で 1 回だけ再探索する（by_value を更新）。"""
    targets = [r for r, v in by_value.items() if v["status"] == "auth_required"]
    if not targets:
        return
    try:
        with open_auth_navigator() as auth_nav:
            for route in targets:
                by_value[route] = classify_route(origin, route, auth_nav, authenticated=True)
    except Exception:  # noqa: BLE001  認証状態付き context を開けない／途中で壊れた分は failed
        for route in targets:
            if not by_value[route].get("auth_attempted"):
                failed = {**by_value[route], "status": "failed",
                          "reason": "確認に失敗した（保存済みの認証状態でページを開けなかった）"}  # fmt: skip
                by_value[route] = _decorate(failed, True, True)


def probe_candidates(origin: str, candidates: list[dict[str, Any]], navigator: Any, *,
                     open_auth_navigator: OpenNavigator | None = None,
                     auth_available: bool | None = None) -> list[dict[str, Any]]:  # fmt: skip
    """候補ごとに結果を付ける。同じ route 値は 1 回だけ開き、全候補 id に同じ結果を付ける。

    open_auth_navigator があれば、未認証で auth_required だった route だけ認証状態付きで再探索する。
    auth_available=False のとき auth_required の理由に「保存済みの認証状態がありません」を添える。
    """
    by_value: dict[str, dict[str, Any]] = {}
    items = []
    for cand in candidates:
        route = str(cand.get("value") or "")
        if route not in by_value:
            by_value[route] = classify_route(origin, route, navigator)
    if open_auth_navigator is not None:
        _reprobe_with_auth(origin, by_value, open_auth_navigator)
    elif auth_available is False:
        for route, v in by_value.items():
            if v["status"] == "auth_required":
                by_value[route] = {**v, "reason": f"{v['reason']}（{REASON_NO_AUTH}）"}
    for cand in candidates:
        route = str(cand.get("value") or "")
        items.append({"evidence_id": cand.get("id"), "route": route,
                      "location": cand.get("location"), **by_value[route]})  # fmt: skip
    return items


def reprobe_items_with_auth(origin: str, items: list[dict[str, Any]],
                            open_auth_navigator: OpenNavigator) -> list[dict[str, Any]]:  # fmt: skip
    """未認証の探索結果（items）のうち auth_required の route だけを、認証状態付きで再探索する。"""
    keys = ("evidence_id", "route", "location")
    by_value = {i["route"]: {k: v for k, v in i.items() if k not in keys} for i in items}
    _reprobe_with_auth(origin, by_value, open_auth_navigator)
    return [{**{k: i.get(k) for k in keys}, **by_value[i["route"]]} for i in items]


# ------------------------------------------------------------------ Playwright


def guard_route(route: Any) -> None:
    """GET/HEAD/OPTIONS 以外のリクエストを全て abort する route ハンドラ。"""
    try:
        method = str(route.request.method).upper()
    except Exception:  # noqa: BLE001
        method = ""
    try:
        if method in SAFE_METHODS:
            route.continue_()
        else:
            route.abort()
    except Exception:  # noqa: BLE001
        pass


class _PlaywrightNavigator:
    def __init__(self, page: Any) -> None:
        self._page = page

    def goto(self, url: str) -> NavResult:
        try:
            resp = self._page.goto(url, wait_until="networkidle", timeout=GOTO_TIMEOUT_MS)
        except Exception as exc:  # noqa: BLE001
            kind = "timeout" if type(exc).__name__ == "TimeoutError" else "error"
            raise NavError(kind) from None
        return NavResult(resp.status if resp is not None else None, self._page.url)

    def states(self) -> int | None:
        from crawler.action_explorer import explore_page_actions

        return len(explore_page_actions(self._page, max_actions=3))


@contextlib.contextmanager
def playwright_navigator(storage_state: str | None = None) -> Iterator[_PlaywrightNavigator]:
    from crawler.playwright_runtime import configure_playwright_browsers_path

    configure_playwright_browsers_path()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context(storage_state=storage_state) if storage_state else browser.new_context()
            page = context.new_page()
            page.route("**/*", guard_route)
            yield _PlaywrightNavigator(page)
        finally:
            browser.close()


# ------------------------------------------------------------------ 実行


def static_route_candidates(evidence: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not evidence or evidence.get("state") != "ok":
        return []
    return [e for e in evidence.get("evidence") or []
            if e.get("group") == "route" and e.get("origin") == "static" and e.get("id")]  # fmt: skip


def snapshot_origin(base: Path, domain: str) -> str | None:
    import json

    from crawler.url_safety import domain_key_from_url

    snap = runner.latest_snapshot(base, domain)
    if snap is None:
        return None
    try:
        pages = json.loads(snap.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for page in pages if isinstance(pages, list) else []:
        url = page.get("url", "") if isinstance(page, dict) else ""
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https") and parsed.netloc and domain_key_from_url(url) == domain:
            return f"{parsed.scheme}://{parsed.netloc}"
    return None


_NO_REA = ProbeRun("no_rea", "このサイトには到達確認できる静的 route 候補がありません。",
                   "先に「リバース解析を実行」して、route 候補を見つけてください。")  # fmt: skip


def run_probe(base: Path, domain: str, evidence: dict[str, Any],
              open_navigator: OpenNavigator | None = None) -> ProbeRun:  # fmt: skip
    candidates = static_route_candidates(evidence)
    sha = store.current_rea_sha(base, domain)
    if not candidates or not sha:
        return _NO_REA
    with _running_lock:
        if domain in _running:
            return ProbeRun("busy", "このサイトの到達確認は実行中です。", "終わるまで待ってから再度開いてください。")
        _running.add(domain)
    try:
        origin = snapshot_origin(base, domain)
        if origin is None:
            return ProbeRun("error", "到達確認の起点になるページが実行時記録にありません。",
                            "先にドキュメント作成でサイトを解析してください。")  # fmt: skip
        started = datetime.now(_JST)
        t0 = time.monotonic()
        try:
            opener = open_navigator or playwright_navigator
            auth_path = auth_state_path(base, domain)
            auth_opener = None
            if auth_path is not None:
                def auth_opener(_p: str = str(auth_path)):  # noqa: ANN202
                    return opener(storage_state=_p)

            # 認証状態付きの再探索は、未認証のブラウザを閉じてから開く（Playwright の同期 API は入れ子にできない）
            with opener() as navigator:
                items = probe_candidates(origin, candidates, navigator,
                                         auth_available=auth_path is not None)  # fmt: skip
            if auth_opener is not None:
                items = reprobe_items_with_auth(origin, items, auth_opener)
        except Exception:  # noqa: BLE001
            return ProbeRun("error", "ブラウザを起動できず、到達確認を完了できませんでした。結果は更新していません。",
                            "管理者にブラウザ（Playwright）の導入を確認してください。")  # fmt: skip
        store.save(base, domain, {
            "domain": domain, "rea_snapshot_sha256": sha,
            "started_at": started.isoformat(timespec="seconds"),
            "finished_at": datetime.now(_JST).isoformat(timespec="seconds"),
            "seconds": round(time.monotonic() - t0, 1), "items": items,
        })  # fmt: skip
        n_obs = sum(1 for i in items if i["status"] == "observed")
        n_auth = sum(1 for i in items if i["status"] == "observed" and i.get("authenticated"))
        extra = f"（うち {n_auth} 件は保存済みの認証状態で確認）" if n_auth else ""
        return ProbeRun("success", f"{len(items)} 件の route 候補のうち {n_obs} 件を実測で到達確認しました。{extra}",
                        "結果を確認し、未到達・認証等で未確認の候補は画面から手動で確かめてください。")  # fmt: skip
    finally:
        with _running_lock:
            _running.discard(domain)


# ------------------------------------------------------------------ 読み出し


def build_status(base: Path, domain: str, evidence: dict[str, Any]) -> dict[str, Any]:
    candidates = static_route_candidates(evidence)
    running = is_running(domain)
    out: dict[str, Any] = {
        "site": {"domain": domain}, "running": running,
        "before": {"static_routes": len(candidates)}, "after": None,
        "seconds": None, "finished_at": None, "items": [],
    }  # fmt: skip
    if not candidates:
        return {**out, "state": "no_rea", "can_run": False,
                "cannot_run_reason": "到達確認できる静的 route 候補がありません。",
                "message": _NO_REA.message, "next_action": _NO_REA.next_action}  # fmt: skip
    can_run = not running
    reason = None if can_run else "到達確認が実行中です。"
    doc = store.load(base, domain)
    if doc is None:
        return {**out, "state": "not_run", "can_run": can_run, "cannot_run_reason": reason,
                "message": f"静的 route 候補 {len(candidates)} 件はまだ到達確認していません（到達は未確認）。",
                "next_action": "「探索を実行」を押すと、GET の遷移だけで各 route を開きます。"}  # fmt: skip
    views: dict[str, list[str]] = {}
    runnable = 0
    observed_ids = {i["evidence_id"] for i in doc["items"] if i.get("status") == "observed"}
    # 探索結果を渡す（渡さないと観点の文言が「到達は未確認」のままになり、実測の事実と食い違う）
    probe = {i.get("evidence_id"): i for i in doc["items"] if i.get("evidence_id")}
    for v in (build_viewpoints(evidence, probe=probe).get("viewpoints") or []):
        eid = v.get("evidence_id")
        if eid in observed_ids:
            views.setdefault(eid, []).append(v.get("text"))
            runnable += 1 if v.get("is_new") else 0
    counts = {s: 0 for s in store.STATUSES}
    items = []
    for i in doc["items"]:
        st = i.get("status")
        counts[st] = counts.get(st, 0) + 1
        items.append({
            "evidence_id": i.get("evidence_id"), "route": i.get("route"), "url": i.get("url"),
            "status": st, "status_label": store.STATUS_LABEL.get(st, st), "reason": i.get("reason"),
            "http_status": i.get("http_status"), "final_url": i.get("final_url"),
            "observed_at": i.get("observed_at"), "location": i.get("location"),
            "states_found": i.get("states_found"),
            "authenticated": bool(i.get("authenticated")), "auth_attempted": bool(i.get("auth_attempted")),
            "evidence": i.get("evidence") or "", "limitation": i.get("limitation") or "",
            "system02_viewpoints": views.get(i.get("evidence_id"), []),
        })  # fmt: skip
    return {
        **out, "state": "ok", "can_run": can_run, "cannot_run_reason": reason,
        "message": f"{counts['observed']} 件が実測で到達、{len(items) - counts['observed']} 件は未確認のままです。",
        "next_action": "未到達・認証等で未確認・曖昧の候補は、画面から手動で確かめてください。",
        "after": {**counts, "promoted": counts["observed"], "system02_runnable": runnable,
                  "observed_authenticated": sum(1 for i in items if i["status"] == "observed" and i["authenticated"]),
                  "auth_state_available": auth_state_path(base, domain) is not None},
        "seconds": doc.get("seconds"), "finished_at": doc.get("finished_at"), "items": items,
    }  # fmt: skip
