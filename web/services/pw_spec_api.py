"""生成された Python spec（`*_spec.py`）がランナーとやり取りする最小 API。

契約（ランナー web/services/pw_runner.py が前提にする）:
- spec は `from web.services.pw_spec_api import case, expect, ...` で読み込む。
- `@case(label, skip=False)` が関数 `fn(page)` を登録する。ランナーは
  `registered_cases()` を順に取り出し、skip=True は実行せず skipped とする。
- 失敗は `AssertionError` / Playwright の例外で表す。
- `annotate()` で積んだ注記は、ケース終了ごとに `take_annotations()` で回収できる。
Node を一切要求しない（playwright の sync API のみ）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import expect  # noqa: F401  再エクスポート


@dataclass(frozen=True)
class RegisteredCase:
    label: str
    skip: bool
    fn: Callable[[Any], None]


_REGISTRY: list[RegisteredCase] = []
_ANNOTATIONS: list[dict[str, str]] = []
# 生成 spec が実行中のステップ ID（例: "S3"）を書き込み、ランナーが失敗ステップとして読む。
LAST_STEP: str = ""


def case(label: str, skip: bool = False) -> Callable[[Callable[[Any], None]], Callable[[Any], None]]:
    """テストケースを登録するデコレータ。"""

    def decorator(fn: Callable[[Any], None]) -> Callable[[Any], None]:
        _REGISTRY.append(RegisteredCase(label=label, skip=skip, fn=fn))
        return fn

    return decorator


def registered_cases() -> list[RegisteredCase]:
    return list(_REGISTRY)


def reset_registry() -> None:
    _REGISTRY.clear()
    _ANNOTATIONS.clear()


def annotate(type_: str, description: str) -> None:
    """証跡用の注記（TS の test.info().annotations.push 相当）。"""
    _ANNOTATIONS.append({"type": type_, "description": description})


def take_annotations() -> list[dict[str, str]]:
    items = list(_ANNOTATIONS)
    _ANNOTATIONS.clear()
    return items


def safe_enabled(locator: Any) -> bool:
    """有効かどうか。取得に失敗したら False（TS の isEnabled().catch(() => false) 相当）。"""
    try:
        return bool(locator.is_enabled())
    except Exception:
        return False


def safe_uncheck(locator: Any) -> None:
    """チェックを外す。失敗は無視（TS の uncheck().catch(() => {}) 相当）。"""
    try:
        locator.uncheck()
    except Exception:
        pass
