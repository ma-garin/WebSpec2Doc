from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from analyzer.html_analyzer import AnalyzedPage
from crawler.page_crawler import FieldData, FormData

logger = logging.getLogger(__name__)


# fingerprint バージョン:
#   v1: 正規化URL＋フォーム構造
#   v2: 正規化URL＋DOM状態シグネチャ（landmark構造＋開閉状態）＋フォーム構造
FINGERPRINT_VERSION_STRUCTURE = 1
FINGERPRINT_VERSION_STATE = 2
DEFAULT_FINGERPRINT_VERSION = FINGERPRINT_VERSION_STATE


@dataclass(frozen=True)
class CanonicalInfo:
    canonical_key: str
    is_canonical: bool
    variation_count: int
    variation_urls: tuple[str, ...]
    fingerprint: str = ""
    fingerprint_version: int = DEFAULT_FINGERPRINT_VERSION


def screen_fingerprint(
    page: AnalyzedPage,
    version: int = DEFAULT_FINGERPRINT_VERSION,
) -> str:
    """画面同定用の fingerprint を計算する。

    version=1 は旧来の「正規化URL＋フォーム構造」、version=2 は状態ベース
    （DOM 状態シグネチャを追加）。既存スナップショット（state_id="default"）でも
    v2 は v1 と同等の粒度に退化するため後方互換が保たれる。
    """
    normalized_url = _normalize_url(page.page_data.url)
    structure_signature = _structure_signature(page.page_data.forms)
    if version == FINGERPRINT_VERSION_STRUCTURE:
        raw_fingerprint = f"{normalized_url}\n{structure_signature}"
    else:
        state_id = page.page_data.state_id or "default"
        raw_fingerprint = f"{normalized_url}\nstate:{state_id}\n{structure_signature}"
    fingerprint = hashlib.sha1(raw_fingerprint.encode("utf-8"), usedforsecurity=False).hexdigest()[
        :16
    ]  # noqa: S324
    logger.debug("Computed fingerprint (v%d) for %s: %s", version, page.page_id, fingerprint)
    return fingerprint


def group_canonical_screens(
    pages: Sequence[AnalyzedPage],
    version: int = DEFAULT_FINGERPRINT_VERSION,
) -> dict[str, CanonicalInfo]:
    grouped_pages: dict[str, list[AnalyzedPage]] = defaultdict(list)
    for page in pages:
        grouped_pages[screen_fingerprint(page, version)].append(page)

    canonical_map: dict[str, CanonicalInfo] = {}
    for fingerprint, members in grouped_pages.items():
        sorted_members = sorted(members, key=lambda page: page.page_id)
        canonical_page = sorted_members[0]
        variation_urls = tuple(page.page_data.url for page in sorted_members[1:])
        variation_count = len(sorted_members)

        for page in sorted_members:
            canonical_map[page.page_id] = CanonicalInfo(
                canonical_key=canonical_page.page_id,
                is_canonical=page.page_id == canonical_page.page_id,
                variation_count=variation_count,
                variation_urls=variation_urls if page.page_id == canonical_page.page_id else (),
                fingerprint=fingerprint,
                fingerprint_version=version,
            )

        logger.debug(
            "Grouped fingerprint %s into canonical page %s with %d variations",
            fingerprint,
            canonical_page.page_id,
            variation_count,
        )

    logger.info(
        "Grouped %d pages into %d canonical screens",
        len(pages),
        sum(1 for info in canonical_map.values() if info.is_canonical),
    )
    return canonical_map


#: レコードを選ぶだけのクエリ値の形（連番 ID・UUID・ハッシュ・日付）。
#: reserve.html?plan-id=4 と ?plan-id=0 は同じ画面なので、この形の値は
#: キー名だけ残して値を伏せる（従来どおり 1 画面にまとめる）。
_RECORD_VALUE_PATTERN = re.compile(
    r"^(?:\d+"
    r"|[0-9a-fA-F]{8,}"
    r"|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?"
    r")$"
)
_MASKED_VALUE = "*"

#: 画面同定から丸ごと落とすクエリキー。セッション ID・計測タグ・キャッシュ避け・
#: CSRF トークンは同じ画面でもアクセスのたびに変わるため、残すと画面が無限に増える。
_VOLATILE_PARAMS: frozenset[str] = frozenset(
    {
        "phpsessid",
        "jsessionid",
        "aspsessionid",
        "sid",
        "sessionid",
        "session_id",
        "fbclid",
        "gclid",
        "msclkid",
        "yclid",
        "_ga",
        "_gl",
        "mc_cid",
        "mc_eid",
        "cb",
        "cachebuster",
        "nocache",
        "_",
        "ts",
        "timestamp",
        "ver",
        "rev",
        "csrf",
        "csrftoken",
        "csrf_token",
        "_token",
        "authenticity_token",
        "requestverificationtoken",
    }
)
#: utm_* と ASP.NET の __VIEWSTATE / __EVENTTARGET 等はまとめて前方一致で落とす。
_VOLATILE_PARAM_PREFIXES = ("utm_", "__")

#: 値が数値でも「どの画面か」を決めるクエリキー。ASP.NET / DNN の Default.aspx?tabid=55
#: のように、.NET 系 CMS は画面 ID を数値で持つ。ここに無いと全画面が 1 画面に潰れる。
_DEFAULT_ROUTING_PARAMS: frozenset[str] = frozenset(
    {
        "tabid",
        "pageid",
        "page_id",
        "screenid",
        "screen_id",
        "viewid",
        "view_id",
        "menuid",
        "menu_id",
        "nodeid",
        "node_id",
    }
)
#: 対象サイト固有のルーティングキーを足すための環境変数（カンマ区切り）。
ROUTING_PARAMS_ENV = "WEBSPEC2DOC_ROUTING_PARAMS"


def _routing_params() -> frozenset[str]:
    extra = os.environ.get(ROUTING_PARAMS_ENV, "")
    if not extra.strip():
        return _DEFAULT_ROUTING_PARAMS
    added = {token.strip().lower() for token in extra.split(",") if token.strip()}
    return _DEFAULT_ROUTING_PARAMS | added


def _normalize_query(query: str) -> str:
    """画面同定に効くクエリだけを残して正規化する。

    クエリを丸ごと捨てると、ルーティングをクエリで行うサイト
    （PHP の index.php?page=login、ASP.NET の Default.aspx?tabid=55）で
    全画面が 1 画面に潰れる。逆に丸ごと残すと明細 ?id=1..N が別画面に増える。
    そこで「値の形がレコード ID なら値を伏せ、それ以外は残す」で分ける。
    """
    if not query:
        return ""
    normalized: list[str] = []
    routing_params = _routing_params()
    for key, value in parse_qsl(query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in _VOLATILE_PARAMS or lowered.startswith(_VOLATILE_PARAM_PREFIXES):
            continue
        if lowered not in routing_params and _RECORD_VALUE_PATTERN.match(value):
            normalized.append(f"{lowered}={_MASKED_VALUE}")
        else:
            normalized.append(f"{lowered}={value}")
    return "&".join(sorted(normalized))


def _normalize_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, _normalize_query(parts.query), ""))


def _structure_signature(forms: tuple[FormData, ...]) -> str:
    normalized_forms = [
        {
            "action": _normalize_url(form.action),
            "method": form.method.lower(),
            "fields": [
                (field.field_type, field.name, field.required)
                for field in sorted(form.fields, key=_field_sort_key)
            ],
        }
        for form in forms
    ]
    return json.dumps(normalized_forms, ensure_ascii=False, separators=(",", ":"))


def _field_sort_key(field: FieldData) -> tuple[str, str, bool]:
    return (field.name, field.field_type, field.required)
