from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from crawler.url_safety import domain_key_from_url
from web.config import ALLOWED_FORMATS, DOMAIN_RE, OUTPUT_DIR
from web.tenancy import scoped_output_dir

_HTTP_URL_RE = re.compile(r"^https?://.{3,}", re.IGNORECASE)

#: ブラウザから指定してよいリポジトリのホスト（カンマ区切り）。未設定なら GitHub のみ。
SOURCE_REPO_HOSTS_ENV = "WEBSPEC2DOC_SOURCE_REPO_HOSTS"
DEFAULT_SOURCE_REPO_HOSTS = ("github.com",)
#: 1 指定あたりの文字数上限（引数注入・ログ汚染の入口を狭める）
MAX_SOURCE_REPO_LEN = 512
#: ブランチ／タグ名に許可する文字
_SAFE_SOURCE_REF_RE = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")
#: 許可するリポジトリパスの形（/owner/repo または /owner/repo.git のみ）
_SOURCE_REPO_PATH_RE = re.compile(r"^/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+?(?:\.git)?$")


def _out() -> Path:
    """テナントスコープ済みの出力ディレクトリ（リクエスト毎に解決）。"""
    return scoped_output_dir(OUTPUT_DIR)


def _clean_int(value: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _clean_formats(raw: str) -> list[str]:
    picked = [f.strip().lower() for f in raw.split(",") if f.strip()]
    return [f for f in picked if f in ALLOWED_FORMATS]


def _valid_domain(domain: str) -> bool:
    """ドメイン文字列の妥当性を検証する（パストラバーサル防止）。"""
    return bool(domain) and ".." not in domain and bool(DOMAIN_RE.match(domain))


def _safe_auth_path(raw: str) -> str:
    """auth.json はプロジェクト配下のファイルのみ許可（任意ファイル読み取りを防ぐ）。

    テナントコンテキストがある場合は、他テナントのセッションを指せないよう
    自テナントの出力ディレクトリ配下に限定する。
    """
    if not raw:
        return ""
    try:
        target = Path(raw).resolve()
    except (OSError, ValueError, RuntimeError):
        return ""
    from web.tenancy import current_tenant

    if current_tenant() is not None:
        base = _out().resolve()
        if base in target.parents and target.is_file():
            return str(target)
        return ""
    base = Path.cwd().resolve()
    if (target == base or base in target.parents) and target.is_file():
        return str(target)
    return ""


def _safe_reference_doc_paths(raw: str | list[str], domain: str) -> list[str]:
    """参考文書パスを検証する（フォーム文字列またはJSON配列）。

    resolve 後に OUTPUT_DIR/{domain}/reference_docs/ 配下の実在ファイルのみ
    通す（_safe_auth_path と同じ resolve→parents 判定）。不正パスは黙って
    除外する（クロール自体は続行させる）。
    """
    if not raw or not _valid_domain(domain):
        return []
    base = (_out() / domain / "reference_docs").resolve()
    result: list[str] = []
    candidates = raw if isinstance(raw, list) else raw.split(",")
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            target = Path(candidate).resolve()
        except (OSError, ValueError, RuntimeError):
            continue
        if base in target.parents and target.is_file():
            result.append(str(target))
    return result


def _safe_output_path(raw: str) -> Path | None:
    """Resolve a path and ensure it stays inside the (tenant-scoped) output dir."""
    if not raw:
        return None
    try:
        target = Path(raw).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    base = _out().resolve()
    if target != base and base not in target.parents:
        return None
    return target if target.is_file() else None


def allowed_source_repo_hosts() -> tuple[str, ...]:
    """ブラウザから指定してよいリポジトリホストを都度環境変数から解決する。

    モジュール定数にすると import 時に一度だけ評価され、同一プロセス内で
    環境変数を変えても効かない（web/config.py の viewpoints_db_path と同じ理由）。
    """
    raw = os.environ.get(SOURCE_REPO_HOSTS_ENV, "")
    hosts = tuple(h.strip().lower() for h in raw.split(",") if h.strip())
    return hosts or DEFAULT_SOURCE_REPO_HOSTS


def _safe_source_repo(raw: str) -> tuple[str, str]:
    """ブラウザから来たソースリポジトリ指定を検証する。戻り値は (採用した指定, 却下理由)。

    CLI と違い、ブラウザからの指定は任意ホストへの git clone の入口になる。
    ssh はサーバの鍵を使わせることになるため受け付けず、https のみに限る。
    URL 内の資格情報は、ログ・実行履歴・他テナントへの露出面を増やすため拒否する。
    SSRF は egress_gateway.assert_target_allowed に委ねる（名前解決まで見るため、
    社内 DNS で github.com が内部 IP に解決される構成も弾ける）。

    _safe_reference_doc_paths と違い「黙って捨てる」を採らない。参考文書は
    アップロード時点で利用者に結果が出ているが、リポジトリ指定は利用者が
    打ち込んだ唯一の入力で、黙って落とすと「突合したつもりで突合していない」
    という最悪の誤解を生む。理由を呼び出し側へ返し、実行ログに出させる。
    """
    from ingest.repo_fetcher import (
        RepositoryFetchError,
        normalize_repo_url,
        split_repo_ref,
    )

    value = _sanitize(raw or "")
    if not value:
        return "", ""
    if len(value) > MAX_SOURCE_REPO_LEN:
        return "", f"指定が長すぎます（{MAX_SOURCE_REPO_LEN} 文字まで）"

    url_part, ref = split_repo_ref(value)
    if ref and not _SAFE_SOURCE_REF_RE.match(ref):
        return "", f"ブランチ／タグ名として使えない文字が含まれています: {ref}"

    try:
        normalized = normalize_repo_url(url_part)
    except RepositoryFetchError as exc:
        return "", str(exc)

    parts = urlsplit(normalized)
    if parts.scheme.lower() != "https":
        return "", "画面からは https のリポジトリのみ指定できます（ssh はコマンドラインで実行してください）"
    if "@" in parts.netloc:
        return "", "URL に利用者名やトークンを含めることはできません"
    if parts.query or parts.fragment:
        return "", "URL にクエリやフラグメントを含めることはできません"
    if parts.port is not None:
        return "", "ポート付きの URL は指定できません"
    if not _SOURCE_REPO_PATH_RE.match(parts.path):
        return "", "リポジトリの形（owner/repo）として解釈できません"

    host = (parts.hostname or "").lower()
    allowed = allowed_source_repo_hosts()
    if host not in allowed:
        return "", f"許可されていないホストです（許可: {', '.join(allowed)}）: {host}"

    from crawler.url_safety import _local_targets_allowed
    from web.services.egress_gateway import EgressDenied, EgressPolicy, assert_target_allowed

    try:
        assert_target_allowed(normalized, EgressPolicy(allow_local=_local_targets_allowed()))
    except EgressDenied as exc:
        return "", str(exc)

    return f"{normalized}@{ref}" if ref else normalized, ""


def _valid_url(url: str) -> bool:
    """http/https スキームを持つ URL かを確認する（SSRF 対策の最低限チェック）。"""
    return bool(url) and bool(_HTTP_URL_RE.match(url.strip()))


def error_json(message: str, code: int = 400) -> tuple[dict[str, str], int]:
    """統一エラーレスポンスを生成する。"""
    return {"error": message}, code


def _sanitize(value: str) -> str:
    return value.strip().replace("\n", "").replace("\r", "")


def _domain_of(url: str) -> str:
    return domain_key_from_url(url)
