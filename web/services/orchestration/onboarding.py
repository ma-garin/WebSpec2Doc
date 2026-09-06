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
import re
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

#: "https://github.com/owner/name" または "https://github.com/owner/name.git"。
_GITHUB_URL_RE = re.compile(
    r"^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", re.IGNORECASE
)
#: "owner/name" 形式（スラッシュ 1 つ・両側とも git の識別子として妥当な文字だけ）。
_OWNER_NAME_RE = re.compile(r"^[\w.-]+/[\w.-]+$")

#: GitHub からの取得（git clone）に許す時間。
_CLONE_TIMEOUT_SEC = 120


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
    m = _GITHUB_URL_RE.match(text)
    if m:
        return "", f"{m.group(1)}/{m.group(2)}"
    if _OWNER_NAME_RE.match(text):
        return "", text
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
    try:
        subprocess.run(  # noqa: S603 - shell=False固定・引数は正規表現で検証済み
            ["git", "clone", "--depth", "1", url, str(dest)],
            check=True, capture_output=True, timeout=_CLONE_TIMEOUT_SEC, shell=False,
        )
    except (subprocess.CalledProcessError, subprocess.SubprocessError, OSError) as exc:
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
    if len(verify_cmd) > 500:
        raise ValueError("verify_command は 500 字以内で指定してください。")

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

    local_path, github_repo = parse_repo(repo_text)
    if local_path:
        try:
            resolved = project_store.resolve_repo_path(local_path)
        except HealingError as exc:
            raise ValueError(str(exc)) from exc
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
