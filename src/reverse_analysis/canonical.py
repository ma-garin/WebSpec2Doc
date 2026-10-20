"""正規 JSON（キーは UTF-16 code unit 順・空白なし）と SHA-256 digest、厳格な JSON 読込。

外部ツール連携の撤去に伴い旧アダプタから移設した共通部。出力は移設前と同一（ゴールデン値で固定）。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

_LONE_SURROGATE = re.compile(r"[\ud800-\udfff]")


class InvalidJsonInput(ValueError):
    """厳格 JSON の規則に合わない入力。pointer は入力内の位置。"""

    def __init__(self, pointer: str, reason: str) -> None:
        super().__init__(f"{pointer or '/'}: {reason}")
        self.pointer = pointer or "/"
        self.reason = reason


# 旧名の別名（移設前の呼び出し元向け）
InvalidProviderOutput = InvalidJsonInput


def canonical_json(value: Any) -> str:
    """キーを UTF-16 code unit 順に並べ、空白なし・ECMAScript の数値表記で正規 JSON 文字列を作る。"""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _js_number(value)
    if isinstance(value, str):
        return _js_string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    if isinstance(value, Mapping):
        keys = sorted(value, key=lambda key: str(key).encode("utf-16-be", "surrogatepass"))
        return "{" + ",".join(f"{_js_string(str(k))}:{canonical_json(value[k])}" for k in keys) + "}"
    raise TypeError(f"正規化できない値です: {type(value).__name__}")


def canonical_digest(value: Any) -> str:
    """正規 JSON の UTF-8 の SHA-256（hex）。"""
    encoded = canonical_json(value).encode("utf-8", "surrogatepass")
    return hashlib.sha256(encoded).hexdigest()


def _js_string(text: str) -> str:
    encoded = json.dumps(text, ensure_ascii=False)
    return _LONE_SURROGATE.sub(lambda m: f"\\u{ord(m.group()):04x}", encoded)


def _js_number(number: float) -> str:
    """ECMAScript Number::toString と同じ表記（最短の往復表現）。"""
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError("NaN・Infinity は正規化できません")
    if number == 0:
        return "0"
    sign = "-" if number < 0 else ""
    _, digit_tuple, exponent = Decimal(repr(abs(number))).normalize().as_tuple()
    digits = "".join(str(d) for d in digit_tuple)
    k = len(digits)
    n = int(exponent) + k
    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        mantissa = digits if k == 1 else digits[0] + "." + digits[1:]
        body = f"{mantissa}e{'+' if e > 0 else '-'}{abs(e)}"
    return sign + body


def parse_json(data: bytes) -> Any:
    """重複キー・NaN/Infinity・不正 UTF-8 を拒否して JSON を読む。"""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidJsonInput("", "入力が UTF-8 ではありません") from exc

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise InvalidJsonInput("", f"重複したキーがあります: {key!r}")
            result[key] = value
        return result

    def reject_constant(name: str) -> Any:
        raise InvalidJsonInput("", f"JSON に {name} は使えません")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)
    except json.JSONDecodeError as exc:
        raise InvalidJsonInput("", "入力が JSON として読めません") from exc


# 旧名の別名
parse_provider_json = parse_json
