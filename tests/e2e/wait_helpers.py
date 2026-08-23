"""E2E の「起動待ち」を 1 か所へ集めるユーティリティ。

サーバーやデモサイトが待ち受けを始めるのを待つポーリングは、各 E2E ファイルに
同じループがコピーされていた（9 ファイル）。ここへ集約し、固定待機の出現箇所を
このモジュールだけに閉じ込める。

**ブラウザ操作の待機にこれを使ってはいけない。** 画面の待ちは
``expect(page.locator("#result")).to_be_visible()`` のような肯定的な目印で待つ
（scripts/check_e2e_conventions.py が固定待機を禁止している）。

ここで待つのは「別プロセスが待ち受けを開始したか」だけで、毎回条件を確認しながら
回し、成立しなければ False を返す。skip にするか fail にするかは呼び出し側が決める。
"""

from __future__ import annotations

import time
from collections.abc import Callable

import requests

DEFAULT_TIMEOUT_SEC = 15.0
DEFAULT_INTERVAL_SEC = 0.5
PROBE_TIMEOUT_SEC = 0.5


def wait_until(
    predicate: Callable[[], bool],
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    interval_sec: float = DEFAULT_INTERVAL_SEC,
) -> bool:
    """``predicate()`` が True を返すまで待つ。

    E2E で固定待機（sleep）を書いてよい唯一の場所。待ち時間の間も毎回条件を
    確認するため、盲目的な遅延にはならない。

    Returns:
        成立したら True。``timeout_sec`` を過ぎても成立しなければ False。
    """
    deadline = time.monotonic() + timeout_sec
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval_sec)


def http_responds(url: str, probe_timeout_sec: float = PROBE_TIMEOUT_SEC) -> bool:
    """URL が何らかの応答を返すか（ステータスコードは問わない）。"""
    try:
        requests.get(url, timeout=probe_timeout_sec)
    except Exception:
        return False
    return True


def http_is_ok(url: str, probe_timeout_sec: float = PROBE_TIMEOUT_SEC) -> bool:
    """URL が成功ステータス（2xx/3xx）を返すか。"""
    try:
        return requests.get(url, timeout=probe_timeout_sec).ok
    except requests.RequestException:
        return False


def wait_http_ok(
    url: str,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    interval_sec: float = DEFAULT_INTERVAL_SEC,
) -> bool:
    """URL が応答するまで待つ（プロセスが待ち受けを始めたかの確認）。"""
    return wait_until(lambda: http_responds(url), timeout_sec, interval_sec)


def wait_http_success(
    url: str,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    interval_sec: float = DEFAULT_INTERVAL_SEC,
) -> bool:
    """URL が成功ステータス（2xx/3xx）を返すまで待つ。"""
    return wait_until(lambda: http_is_ok(url), timeout_sec, interval_sec)
