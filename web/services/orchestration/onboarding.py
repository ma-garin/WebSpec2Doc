"""初めてのサイトを 1 画面から始めるための下ごしらえ（オンボーディング）。

「保守下に置く」(onboard) 目標は healing 段で接続先（HealingProject）を要求する。
接続先が無いサイトを 01 で観測する前から始められるようにするのがここの役目——
url だけを受け取り、domain を導き、接続先が無ければリポジトリ（ローカルパス
または GitHub）から 1 件作る。

状態機械（conductor.py）には触らない。ここは「接続先を用意する」ことだけを行い、
run を起こすのは呼び出し側（routes/orchestration.py）の責任にする。
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from web.services.healing import project_store, verification
from web.services.healing.types import HealingError
from web.validation import _domain_of

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_MAX_URL_LEN = 2000
_MIN_ROUNDS = 1
_MAX_ROUNDS = 5

#: GitHub と判定する形。"https://github.com/owner/name"（.git・末尾スラッシュ・
#: それ以降の深いパスは許す）と "github.com/owner/name"。裸の "owner/name" は
#: 受けない——"myrepo/sub" のような相対パスを GitHub と誤解し、利用者が打った
#: 文字列がそのまま外部への git clone の引き金になるため。
_GITHUB_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/.*)?$",
    re.IGNORECASE,
)
#: "owner/name" 形式（_ensure_clone が受け取った値を再検証するためだけに使う）。
_OWNER_NAME_RE = re.compile(r"^[\w.-]+/[\w.-]+$")

#: GitHub からの取得（git clone）に許す時間。HTTP のリクエストスレッドで
#: 走るので、利用者を待たせてよい上限として短く取る。
_CLONE_TIMEOUT_SEC = 60

#: repo 入力の上限。長すぎるパスは OS が例外にする（Errno 63）ため、
#: ファイルシステムに触る前にここで断る。
_MAX_REPO_LEN = 1000
_MAX_VERIFY_LEN = 500

#: 絶対パスでない repo を断る 1 文。相対パスはサーバの作業ディレクトリ
#: （＝この製品自身のリポジトリ）に解決されてしまう。
_NOT_ABSOLUTE = "コードの場所は絶対パスか GitHub のリンクで指定してください"


@dataclass(frozen=True)
class OnboardPlan:
    """onboard 実行を起こす直前に決まっていること。"""

    domain: str
    project_id: str
    params: dict
    created_project: bool
    message: str


def parse_repo(raw: str) -> tuple[str, str]:
    """リポジトリ入力を (ローカルパス, github の "owner/name") に分ける。

    どちらも該当しなければローカルパスとして扱う（resolve_repo_path 側で
    許可ルート外なら弾く）。
    """
    text = str(raw or "").strip()
    if not text:
        return "", ""
    m = _GITHUB_RE.match(text)
    if m:
        return "", f"{m.group(1)}/{m.group(2)}"
    return text, ""


def _clone_dest(owner: str, name: str) -> Path:
    return project_store.worktree_root() / "clones" / f"{owner}-{name}"


def _ensure_clone(github_repo: str) -> Path:
    """GitHub リポジトリを worktree_root() 配下へ用意する（既にあれば使い回す）。"""
    m = _OWNER_NAME_RE.match(str(github_repo or "").strip())
    if not m:
        raise ValueError(f"GitHub リポジトリの指定が不正です: {github_repo}")
    owner, name = m.group(0).split("/", 1)
    dest = _clone_dest(owner, name)
    if (dest / ".git").exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{owner}/{name}.git"
    # 認証を聞かれてもプロンプトで止まらせない。止まると timeout まで
    # HTTP のレスポンスが返らず、利用者には「固まった」としか見えない。
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "echo"}
    try:
        subprocess.run(  # noqa: S603 - shell=False固定・引数は正規表現で検証済み
            ["git", "clone", "--depth", "1", url, str(dest)],
            check=True, capture_output=True, timeout=_CLONE_TIMEOUT_SEC,
            shell=False, env=env,
        )
    except (subprocess.CalledProcessError, subprocess.SubprocessError, OSError) as exc:
        # 途中まで置かれたものを残さない。次回「.git がある」と誤認して
        # 壊れた取得結果をそのまま接続先にしてしまう。
        shutil.rmtree(dest, ignore_errors=True)
        raise ValueError(f"GitHub から取得できませんでした: {exc}") from exc
    return dest


def _clamp_rounds(rounds: int) -> int:
    try:
        n = int(rounds)
    except (TypeError, ValueError):
        raise ValueError("rounds は 1〜5 の整数で指定してください。") from None
    if not (_MIN_ROUNDS <= n <= _MAX_ROUNDS):
        raise ValueError("rounds は 1〜5 の整数で指定してください。")
    return n


def prepare(
    out_dir: Path, *, url: str, repo: str = "", verify_command: str = "",
    rounds: int = 1, actor: str = "",
) -> OnboardPlan:
    """url から domain を導き、接続先が無ければ 1 件作る。

    既存の接続先（domain 一致）があればそれを使う。verify_command が渡され、
    既存側が空ならそこへ埋める。無ければ repo が必須で、ローカルパスは
    許可ルート検査、GitHub は未取得ならその場で clone する。
    """
    text_url = str(url or "").strip()
    if not text_url or not _URL_RE.match(text_url) or len(text_url) > _MAX_URL_LEN:
        raise ValueError("url は http:// か https:// で始まる 2000 字以内で指定してください。")
    domain = _domain_of(text_url)
    if not domain:
        raise ValueError("url からサイトを取り出せませんでした。")
    n = _clamp_rounds(rounds)

    verify_cmd = str(verify_command or "").strip()
    if len(verify_cmd) > _MAX_VERIFY_LEN:
        raise ValueError(f"verify_command は {_MAX_VERIFY_LEN} 字以内で指定してください。")

    existing = next(
        (p for p in project_store.list_projects(out_dir) if p.domain == domain), None
    )
    if existing is not None:
        if verify_cmd and not existing.verify_command:
            ok, reason = verification.is_command_allowed(verify_cmd)
            if not ok:
                raise ValueError(f"検証コマンドを使えません: {reason}")
            existing = project_store.update_project(
                out_dir, existing.project_id, {"verify_command": verify_cmd}
            )
        return OnboardPlan(
            domain=domain, project_id=existing.project_id,
            params={"url": text_url, "rounds": n}, created_project=False,
            message=f"既存の接続先「{existing.name}」を使います",
        )

    repo_text = str(repo or "").strip()
    if not repo_text:
        raise ValueError("修正するリポジトリを指定してください")
    if len(repo_text) > _MAX_REPO_LEN:
        raise ValueError(f"コードの場所は {_MAX_REPO_LEN} 字以内で指定してください。")

    local_path, github_repo = parse_repo(repo_text)
    if local_path:
        # 相対パスはサーバの作業ディレクトリ（この製品自身のリポジトリ）に
        # 解決される。許可ルート検査は絶対パス前提なので素通りしてしまう。
        if not Path(local_path).expanduser().is_absolute():
            raise ValueError(_NOT_ABSOLUTE)
        try:
            resolved = project_store.resolve_repo_path(local_path)
        except HealingError as exc:
            raise ValueError(str(exc)) from exc
        except OSError as exc:  # 長すぎる名前など。500 にしない
            raise ValueError(f"コードの場所を確認できませんでした: {exc.strerror or exc}") from exc
        repo_path = resolved
    else:
        repo_path = _ensure_clone(github_repo)

    if not verify_cmd:
        verify_cmd = project_store._suggest_verify_command(repo_path)
    ok, reason = verification.is_command_allowed(verify_cmd)
    if not ok:
        raise ValueError(f"検証コマンドを使えません: {reason}")

    try:
        project = project_store.create_project(
            out_dir, name=domain, domain=domain, repo_path=str(repo_path),
            github_repo=github_repo, verify_command=verify_cmd,
        )
    except HealingError as exc:
        raise ValueError(str(exc)) from exc

    logger.info("onboarding: 接続先を作成しました (domain=%s project_id=%s actor=%s)",
                domain, project.project_id, actor or "不明")
    return OnboardPlan(
        domain=domain, project_id=project.project_id,
        params={"url": text_url, "rounds": n}, created_project=True,
        message=f"接続先「{project.name}」を新規作成しました",
    )
