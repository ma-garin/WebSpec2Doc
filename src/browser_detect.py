"""顧客環境の Google Chrome / Microsoft Edge を検出し、Playwright の channel で起動する。

製品境界: ブラウザの同梱・実行時ダウンロード（playwright install）・外部コマンド実行は行わない。
見つからなければ成功扱いにせず BrowserUnavailable（status=BLOCKED / reason=browser unavailable）。
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

BROWSER_ENV = "WEBSPEC2DOC_BROWSER"
UNAVAILABLE_REASON = "browser unavailable"
BLOCKED_STATUS = "BLOCKED"
CHANNELS = ("chrome", "msedge")
_ALIASES = {"chrome": "chrome", "msedge": "msedge", "edge": "msedge"}

#: OS 別・channel 別の探索候補。darwin/windows は絶対パス（%VAR% 形式を環境変数で展開）、
#: linux は PATH 上のコマンド名。レジストリ参照・subprocess は使わない。
PATH_TABLES: dict[str, dict[str, tuple[str, ...]]] = {
    "darwin": {
        "chrome": ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",),
        "msedge": ("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",),
    },
    "windows": {
        "chrome": tuple(
            f"%{v}%\\Google\\Chrome\\Application\\chrome.exe"
            for v in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData")
        ),
        "msedge": tuple(
            f"%{v}%\\Microsoft\\Edge\\Application\\msedge.exe"
            for v in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData")
        ),
    },
    "linux": {
        "chrome": ("google-chrome", "google-chrome-stable"),
        "msedge": ("microsoft-edge", "microsoft-edge-stable"),
    },
}


class BrowserUnavailable(RuntimeError):
    """使える Chrome / Edge が無い、または起動できない。成功扱いにしてはいけない。"""

    def __init__(self, detail: str = "", tried: Sequence[str] = (), reason: str = UNAVAILABLE_REASON):
        self.reason = reason
        self.detail = detail
        self.tried = list(tried)
        super().__init__(reason + (f": {detail}" if detail else ""))


@dataclass(frozen=True)
class BrowserChoice:
    channel: str  # "chrome" | "msedge"
    path: str
    source: str  # "env" | "arg" | "auto"


@dataclass
class _Probe:
    found: dict[str, str] = field(default_factory=dict)
    tried: list[str] = field(default_factory=list)


def _os_key(system: str | None) -> str:
    name = (system or sys.platform).lower()
    if name.startswith("win"):
        return "windows"
    if name.startswith("darwin"):
        return "darwin"
    return "linux"


def _expand(template: str, env: Mapping[str, str]) -> str | None:
    out = template
    while "%" in out:
        start = out.index("%")
        end = out.find("%", start + 1)
        if end < 0:
            return None
        value = env.get(out[start + 1 : end])
        if not value:
            return None
        out = out[:start] + value + out[end + 1 :]
    return out


def _normalize(name: str | None) -> str | None:
    return _ALIASES.get((name or "").strip().lower())


def detect_browser(
    prefer: str | None = None,
    *,
    system: str | None = None,
    env: Mapping[str, str] | None = None,
    tables: Mapping[str, Mapping[str, Sequence[str]]] | None = None,
    exists: Callable[[str], bool] | None = None,
    which: Callable[[str], str | None] | None = None,
) -> BrowserChoice:
    """インストール済みブラウザを返す。優先順は prefer ＞ 環境変数 ＞ chrome ＞ msedge。

    見つからなければ BrowserUnavailable（tried に調べた全候補）。
    """
    env_map: Mapping[str, str] = os.environ if env is None else env
    table = (tables or PATH_TABLES).get(_os_key(system), {})
    exists_fn = exists or os.path.isfile
    which_fn = which or shutil.which

    wanted = _normalize(prefer)
    source = "arg"
    if wanted is None:
        wanted = _normalize(env_map.get(BROWSER_ENV))
        source = "env"
    order = [c for c in ([wanted] if wanted else [])] + [c for c in CHANNELS if c != wanted]

    probe = _Probe()
    for channel in order:
        for entry in table.get(channel, ()):
            if _os_key(system) == "linux":
                probe.tried.append(entry)
                path = which_fn(entry)
            else:
                expanded = _expand(entry, env_map)
                probe.tried.append(expanded or entry)
                path = expanded if expanded and exists_fn(expanded) else None
            if path:
                return BrowserChoice(
                    channel=channel,
                    path=str(path),
                    source=source if channel == wanted else "auto",
                )
    raise BrowserUnavailable("Google Chrome または Microsoft Edge が見つかりません", probe.tried)


def launch_browser(p: Any, headless: bool = True, args: Sequence[str] | None = None, **kwargs: Any):
    """検出した channel で Chromium 系ブラウザを起動する（executable_path は渡さない）。

    起動に失敗したら BrowserUnavailable("launch failed")。
    """
    choice = detect_browser()
    try:
        return p.chromium.launch(
            channel=choice.channel,
            headless=headless,
            args=list(args) if args else None,
            **kwargs,
        )
    except Exception as exc:  # noqa: BLE001 - 環境要因（MDM・権限・DISPLAY なし等）を一括で変換
        raise BrowserUnavailable(
            f"{choice.channel} を起動できません: {exc}", [choice.path], reason="browser unavailable"
        ) from exc


def status(**detect_kwargs: Any) -> dict[str, Any]:
    """doctor・画面向けの検出結果。"""
    try:
        choice = detect_browser(**detect_kwargs)
    except BrowserUnavailable as exc:
        return {
            "available": False,
            "status": BLOCKED_STATUS,
            "reason": exc.reason,
            "detail": exc.detail,
            "tried": exc.tried,
        }
    return {
        "available": True,
        "channel": choice.channel,
        "path": choice.path,
        "source": choice.source,
    }
