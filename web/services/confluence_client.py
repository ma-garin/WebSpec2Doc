"""Confluence Cloud（REST API v2）への一方向連携クライアント。

WebSpec2Doc から Confluence へ「ページを作る」だけの片方向に限定する。取り込み
（Confluence 側の編集を戻す）を実装しないのは、レポートの正本が WebSpec2Doc 側に
あるためで、双方向にすると「どちらの数字が正しいか」を運用者が判断できなくなる。

認証・SSRF ガード・失敗の返し方は jira_client.py と同一である。Confluence は同じ
Atlassian Cloud で email + API トークンの Basic 認証も共通なため、同等の実装を
書き起こさず jira_client の内部ヘルパをそのまま再利用する（二重実装は、片方だけ
直されて秘密値の扱いがずれるのが最大の事故要因になる）。
"""

from __future__ import annotations

import html
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from web.env_store import _read_env
from web.services.jira_client import (
    ERROR_AUTH,
    ERROR_BASE_URL,
    ERROR_UNREACHABLE,
    _auth_header,
    _clean,
    _is_allowed_base_url,
    _is_success,
    _parse_json,
    _trim,
)

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10
_TITLE_MAX_LENGTH = 255
_BODY_MAX_LENGTH = 200_000

ENV_BASE_URL = "CONFLUENCE_BASE_URL"
ENV_EMAIL = "CONFLUENCE_EMAIL"
ENV_API_TOKEN = "CONFLUENCE_API_TOKEN"
ENV_SPACE_KEY = "CONFLUENCE_SPACE_KEY"

# 失敗理由は定型文へ丸める。API の応答本文をそのまま返すと内部エンドポイントや
# アカウント情報が画面へ漏れるため（jira_client と同じ方針）。
ERROR_SPACE_NOT_FOUND = "スペースが見つかりません（スペースキーを確認してください）"
ERROR_SPACE_UNRESOLVED = "スペースを特定できません"
ERROR_UNEXPECTED_BODY = "Confluence の応答を解釈できませんでした"
ERROR_EMPTY_TITLE = "タイトルが空のためページを作成できません"

# レポート集計値の日本語見出し。summary はドメインごとにキーが増減するため、
# ここに無いキーはキー名のまま出す（黙って捨てると欠落に気づけない）。
_SUMMARY_LABELS: dict[str, str] = {
    "generated_at": "生成日時",
    "crawled_at": "取得日時",
    "pages": "取得ページ数",
    "screens": "画面数",
    "features": "機能数",
    "cases": "テストケース数",
    "executed": "実行済みケース数",
    "passed": "成功",
    "failed": "失敗",
    "blocked": "ブロック",
    "skipped": "スキップ",
    "pass_rate": "成功率",
    "defects": "不具合件数",
    "duration_sec": "所要時間（秒）",
}


@dataclass(frozen=True)
class ConfluenceConfig:
    """Confluence 接続設定。生成後は書き換えない（秘密値の取り違えを防ぐため）。"""

    base_url: str
    email: str
    api_token: str
    space_key: str


def confluence_config_from_env(env: Mapping[str, str]) -> ConfluenceConfig | None:
    """.env の値から設定を組む。必須項目が 1 つでも欠けたら None。

    「部分的に設定済み」を有効扱いにすると、ページ作成時に初めて失敗して原因が
    分からなくなる。未設定は入口で None に倒す。
    """
    base_url = _clean(env.get(ENV_BASE_URL, "")).rstrip("/")
    email = _clean(env.get(ENV_EMAIL, ""))
    api_token = _clean(env.get(ENV_API_TOKEN, ""))
    space_key = _clean(env.get(ENV_SPACE_KEY, ""))
    if not (base_url and email and api_token and space_key):
        return None
    return ConfluenceConfig(
        base_url=base_url, email=email, api_token=api_token, space_key=space_key
    )


def load_confluence_config() -> ConfluenceConfig | None:
    """.env を読んで設定を組む。呼び出し側に env の読み方を持たせないための入口。"""
    return confluence_config_from_env(_read_env())


def verify_connection(config: ConfluenceConfig) -> tuple[bool, str]:
    """スペースを 1 件取得して接続確認する。成功時はスペース名を返す。

    保存前に確かめられないと、ページ作成が必要になった時点で初めて誤設定に気づく。
    """
    if not _is_allowed_base_url(config.base_url):
        return False, ERROR_BASE_URL
    ok, info = _fetch_space(config)
    if not ok:
        return False, info.get("error", ERROR_UNREACHABLE)
    return True, info.get("name") or config.space_key


def create_page(
    config: ConfluenceConfig, *, title: str, body_html: str, parent_id: str = ""
) -> tuple[bool, dict[str, Any]]:
    """ページを 1 件作成する。成功時は page_id / page_url を返す。

    失敗は例外ではなく (False, {"error": 理由}) で返す。jira_client と同じ作法に
    揃え、呼び出し側が握りつぶしを書かなくて済むようにするため。
    """
    if not _is_allowed_base_url(config.base_url):
        return False, {"error": ERROR_BASE_URL}
    page_title = _trim(_clean(title), _TITLE_MAX_LENGTH)
    if not page_title:
        return False, {"error": ERROR_EMPTY_TITLE}

    # spaceId は数値 ID で、画面に出る space_key（例: QA）とは別物。
    # key のまま送ると 400 になるので、必ず解決してから組み立てる。
    space_id = _resolve_space_id(config)
    if not space_id:
        return False, {"error": ERROR_SPACE_UNRESOLVED}

    payload: dict[str, Any] = {
        "spaceId": space_id,
        "status": "current",
        "title": page_title,
        "body": {
            "representation": "storage",
            "value": _trim(str(body_html or ""), _BODY_MAX_LENGTH),
        },
    }
    if _clean(parent_id):
        payload["parentId"] = _clean(parent_id)

    status, data = _send(config, "POST", "/wiki/api/v2/pages", payload)
    if not _is_success(status):
        return False, {"error": _message_for_status(status)}
    page_id = _clean(data.get("id"))
    if not page_id:
        return False, {"error": ERROR_UNEXPECTED_BODY}
    base = config.base_url.rstrip("/")
    space_key = urllib.parse.quote(config.space_key, safe="")
    return True, {
        "page_id": page_id,
        "page_url": f"{base}/wiki/spaces/{space_key}/pages/{page_id}",
    }


def build_page_from_report(*, domain: str, summary: Mapping[str, Any]) -> tuple[str, str]:
    """ドメインと集計値から (タイトル, storage 形式 HTML) を組む。引数は書き換えない。

    Confluence 側で読む人は WebSpec2Doc を開いていない前提なので、対象ドメインを
    タイトルにも本文にも残す。値が空のキーは行ごと落とす（空欄の羅列は、集計が
    失敗したのか元々無いのかを読み手が区別できず、判断を誤らせるため）。
    """
    target = _clean(domain) or "(不明なドメイン)"
    stamp = _clean(summary.get("generated_at", "")) or _clean(summary.get("crawled_at", ""))
    # 同一スペース内でタイトルが重複すると作成が失敗するため、日時があれば付ける。
    suffix = f"（{stamp}）" if stamp else ""
    title = _trim(f"WebSpec2Doc レポート: {target}{suffix}", _TITLE_MAX_LENGTH)

    rows: list[str] = []
    for key, value in summary.items():
        text = _format_value(value)
        if not text:
            continue
        label = _SUMMARY_LABELS.get(str(key), str(key))
        rows.append(f"<tr><th>{html.escape(label)}</th><td>{html.escape(text)}</td></tr>")

    parts = [f"<h2>{html.escape(target)} の検査結果</h2>"]
    if rows:
        parts.append("<table><tbody>" + "".join(rows) + "</tbody></table>")
    else:
        parts.append("<p>集計値がありません。</p>")
    return title, _trim("".join(parts), _BODY_MAX_LENGTH)


# =========================================================================
# 内部ヘルパ
# =========================================================================
def _format_value(value: Any) -> str:
    """表示用の文字列にする。0 や False は「値がある」として残す。

    _clean（jira_client）は falsy をすべて空へ倒すため、そのまま使うと
    「失敗 0 件」の行が消え、読み手が集計漏れと見分けられなくなる。
    """
    if value is None or isinstance(value, str):
        return _clean(value)
    if isinstance(value, bool):
        return "はい" if value else "いいえ"
    if isinstance(value, int | float):
        return str(value)
    return _clean(value)


def _resolve_space_id(config: ConfluenceConfig) -> str | None:
    """space_key から数値の spaceId を引く。解決できなければ None。"""
    ok, info = _fetch_space(config)
    if not ok:
        return None
    return info.get("id") or None


def _fetch_space(config: ConfluenceConfig) -> tuple[bool, dict[str, str]]:
    """スペースを 1 件引き (成否, {"id","name"} または {"error"}) を返す。

    verify_connection と _resolve_space_id で同じ経路を使う。別々に書くと、
    片方だけ v1 フォールバックを持つ状態になり挙動が食い違うため。
    """
    query = urllib.parse.urlencode({"keys": config.space_key})
    status, data = _send(config, "GET", f"/wiki/api/v2/spaces?{query}")
    if status == 404:
        # v2 API は Confluence Cloud 専用で、Server / Data Center には
        # /wiki/api/v2/* 自体が存在せず 404 になる。「スペースが無い」ではなく
        # 「API が無い」ケースなので、この時だけ v1 へ落とす。
        # 401/403 では落とさない。資格情報の問題は v1 でも同じ結果になり、
        # 認証エラーを「スペースなし」と誤表示してしまうため。
        return _fetch_space_v1(config)
    if not _is_success(status):
        return False, {"error": _message_for_status(status)}
    results = data.get("results")
    first = results[0] if isinstance(results, list) and results else None
    if not isinstance(first, dict):
        # v2 は存在しないキーでも 200 + 空配列を返すため、ここで未検出に倒す。
        return False, {"error": ERROR_SPACE_NOT_FOUND}
    space_id = _clean(first.get("id"))
    if not space_id:
        return False, {"error": ERROR_UNEXPECTED_BODY}
    return True, {"id": space_id, "name": _clean(first.get("name")) or config.space_key}


def _fetch_space_v1(config: ConfluenceConfig) -> tuple[bool, dict[str, str]]:
    """v1 API（/wiki/rest/api/space/{key}）でスペースを引く。v2 が 404 の時のみ使う。"""
    path = f"/wiki/rest/api/space/{urllib.parse.quote(config.space_key, safe='')}"
    status, data = _send(config, "GET", path)
    if not _is_success(status):
        return False, {"error": _message_for_status(status)}
    space_id = _clean(data.get("id"))
    if not space_id:
        return False, {"error": ERROR_UNEXPECTED_BODY}
    return True, {"id": space_id, "name": _clean(data.get("name")) or config.space_key}


def _send(
    config: ConfluenceConfig, method: str, path: str, payload: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any]]:
    """Confluence を 1 回叩き (HTTP ステータス, JSON) を返す。通信不能は status=0。

    ログにはメソッドとステータスだけ出す。URL 全体やトークンを出すと監査ログ・
    アプリログの双方に秘密値が残るため。jira_client._send と同型だが、障害時に
    どちらの連携先で失敗したか切り分けられるようログ文言だけ分けている。
    """
    url = f"{config.base_url.rstrip('/')}{path}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Authorization": _auth_header(config), "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as response:  # nosec B310
            return int(getattr(response, "status", 0) or 0), _parse_json(response.read())
    except urllib.error.HTTPError as exc:
        logger.error(
            "Confluence API responded with an error: method=%s status=%s", method, exc.code
        )
        return int(exc.code), {}
    except (urllib.error.URLError, OSError, ValueError):
        logger.error("Confluence API request failed: method=%s kind=network_error", method)
        return 0, {}


def _message_for_status(status: int) -> str:
    if status in (401, 403):
        return ERROR_AUTH
    if status == 404:
        return ERROR_SPACE_NOT_FOUND
    return ERROR_UNREACHABLE
