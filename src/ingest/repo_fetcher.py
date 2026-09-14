"""Git リポジトリの取得層（Code Fusion の入力を GitHub URL まで広げる）。

`--source-dir` はローカルに clone 済みのフォルダを前提とするが、
利用者が最初に持っているのは多くの場合リポジトリの URL である。
ここで shallow clone して作業ディレクトリを作り、走査層（code_reader）へ渡す。

セキュリティ方針:
- **受け付けるのは https / ssh 形式のみ。** `file://` や `ext::` のような
  ローカル実行・任意コマンド実行につながるトランスポートは拒否する。
- **資格情報をログに出さない。** URL に含まれるユーザー情報は必ず伏字にする。
- **clone 先は呼び出し側が渡す一時ディレクトリに限る。**既存ディレクトリは上書きしない。
- サブモジュールは取得しない（取得対象が増え、意図しない外部リポジトリへ広がるため）。
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)

#: 既定のタイムアウト（秒）。大きなリポジトリでも shallow clone なら収まる想定。
DEFAULT_TIMEOUT_SEC = 180

#: 許可するトランスポート。ext:: / file:: 等はローカル実行につながるため含めない。
_ALLOWED_SCHEMES = frozenset({"https", "ssh", "git+ssh"})

#: scp 記法（git@github.com:owner/repo.git）
_SCP_LIKE_RE = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[^/].*$")

#: owner/repo だけの短縮指定
_SHORTHAND_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")

#: ref に許可する文字（シェル・オプション注入を防ぐ）
_SAFE_REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


class RepositoryFetchError(RuntimeError):
    """リポジトリの取得に失敗した（呼び出し側は警告に留めて継続する）。"""


@dataclass(frozen=True)
class FetchedRepository:
    """clone 済みリポジトリの所在。"""

    path: Path
    url: str  # 伏字済みの表示用 URL
    ref: str = ""


def redact(url: str) -> str:
    """URL の資格情報を伏字にする（ログ・レポート・例外メッセージ用）。"""
    if _SCP_LIKE_RE.match(url):
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<invalid url>"
    if not parts.netloc or "@" not in parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit((parts.scheme, f"***@{host}", parts.path, "", ""))


def normalize_repo_url(raw: str) -> str:
    """指定された文字列を clone 可能な URL に正規化する。

    `owner/repo` の短縮指定は GitHub の https URL とみなす。
    拒否するのは「トランスポートが許可外」の場合のみで、
    到達性そのものは clone の結果に委ねる。
    """
    value = raw.strip()
    if not value:
        raise RepositoryFetchError("リポジトリ URL が空です")
    if value.startswith("-"):
        # git のオプションとして解釈されるのを防ぐ
        raise RepositoryFetchError(f"リポジトリ URL として不正です: {value}")
    if _SHORTHAND_RE.match(value):
        return f"https://github.com/{value}"
    if _SCP_LIKE_RE.match(value):
        return value
    scheme = urlsplit(value).scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise RepositoryFetchError(
            f"許可されていない形式です（https / ssh / owner/repo のみ）: {redact(value)}"
        )
    return value


def _clone_command(url: str, dest: Path, ref: str) -> list[str]:
    """shallow clone のコマンドを組み立てる。"""
    command = [
        "git",
        "clone",
        "--depth",
        "1",
        "--single-branch",
        "--no-tags",
        # サブモジュールは意図しない外部リポジトリへ広がるため取得しない
        "--recurse-submodules=no",
    ]
    if ref:
        command += ["--branch", ref]
    command += ["--", url, str(dest)]
    return command


def fetch_repository(
    raw_url: str,
    dest: Path,
    *,
    ref: str = "",
    timeout: int = DEFAULT_TIMEOUT_SEC,
) -> FetchedRepository:
    """リポジトリを `dest` へ shallow clone する。

    `dest` は存在しないパスであること（既存ディレクトリは上書きしない）。
    失敗時は `RepositoryFetchError` を送出し、作りかけの `dest` を片付ける。
    """
    url = normalize_repo_url(raw_url)
    safe_url = redact(url)
    if ref and not _SAFE_REF_RE.match(ref):
        raise RepositoryFetchError(f"ブランチ／タグ名として不正です: {ref}")
    if dest.exists():
        raise RepositoryFetchError(f"clone 先が既に存在します: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    # 認証を対話で求められるとハングするため、非対話に固定する。
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GIT_ASKPASS", "true")

    logger.info("リポジトリを取得します: %s%s", safe_url, f" ({ref})" if ref else "")
    try:
        completed = subprocess.run(  # noqa: S603 - 引数は配列で渡し shell は使わない
            _clone_command(url, dest, ref),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        _cleanup(dest)
        raise RepositoryFetchError(f"取得がタイムアウトしました（{timeout}秒）: {safe_url}") from exc
    except OSError as exc:
        _cleanup(dest)
        raise RepositoryFetchError(f"git を実行できませんでした: {exc}") from exc

    if completed.returncode != 0:
        _cleanup(dest)
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        # stderr にも資格情報が載りうるため伏字にしてから返す
        tail = redact(detail[-1]) if detail else "詳細不明"
        raise RepositoryFetchError(f"取得に失敗しました: {safe_url}: {tail}")

    return FetchedRepository(path=dest, url=safe_url, ref=ref)


def _cleanup(dest: Path) -> None:
    """作りかけの clone 先を片付ける（失敗しても握りつぶす）。"""
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
