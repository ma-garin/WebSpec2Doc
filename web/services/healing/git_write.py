"""git の書込操作（dulwich 実装。git コマンドは起動しない）。

1 エージェント = 1 worktree = 1 ブランチ。dulwich はフックを実行しない設定
（no_verify）で使う。失敗は例外でなく GitResult(ok=False) で返す。
"""

from __future__ import annotations

import io
import logging
import os
import re
from collections.abc import Sequence
from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo

from web.services.healing.git_common import (
    GitResult,
    describe_error,
    fail_result,
    ok_result,
    strip_ansi,
)
from web.services.healing.git_read import (
    branch_exists,
    current_branch,
    has_uncommitted_changes,
)

logger = logging.getLogger(__name__)

_DEFAULT_IDENTITY = b"WebSpec2Doc <healing@webspec2doc.local>"
#: ssh 形式の remote。dulwich は外部 ssh を起動するため対応しない。
_SSH_URL = re.compile(r"^(ssh://|git\+ssh://|[\w.\-]+@[\w.\-]+:)")
#: 削除を絶対に許さないブランチ名。
_PROTECTED_BRANCHES = frozenset({"main", "master"})
#: worktree へリンクする git 管理外のディレクトリ（検証コマンドが前提にする環境）。
_LINKED_UNTRACKED_DIRS = ("venv", ".venv", "node_modules")


def _identity(path: Path) -> bytes:
    """コミット者。git の user.name / user.email があればそれ、無ければ固定の名前。"""
    try:
        with Repo(str(path)) as r:
            cfg = r.get_config_stack()
            name = cfg.get((b"user",), b"name")
            email = cfg.get((b"user",), b"email")
            return name + b" <" + email + b">"
    except Exception:  # noqa: BLE001 - 未設定は既定値で続ける
        return _DEFAULT_IDENTITY


def _open(path: Path) -> Repo:
    """Repo を開き、フックを外す。dulwich は post-commit 等を外部プロセスで実行するため、
    利用者のフックを走らせない（git commit --no-verify 相当 + 外部プロセス不起動）。"""
    repo = Repo(str(path))
    repo.hooks.clear()
    return repo


def create_branch(repo: Path, branch: str, base: str) -> GitResult:
    """base を起点に branch を作る（チェックアウトはしない）。"""
    try:
        porcelain.branch_create(str(repo), branch, base)
    except Exception as exc:  # noqa: BLE001
        return fail_result(f"ブランチを作れませんでした ({branch}): {describe_error(exc)}")
    return ok_result()


def delete_branch(repo: Path, branch: str) -> GitResult:
    """統合・欠陥ブランチを削除する。main/master と現在のブランチは削除しない。"""
    if branch in _PROTECTED_BRANCHES or branch == current_branch(repo):
        return GitResult(
            ok=False, stdout="", stderr=f"保護されたブランチは削除しません: {branch}", exit_code=1
        )
    try:
        porcelain.branch_delete(str(repo), branch)
    except Exception as exc:  # noqa: BLE001
        return fail_result(f"ブランチを削除できませんでした ({branch}): {describe_error(exc)}")
    return ok_result()


def create_worktree(repo: Path, branch: str, base: str, workdir: Path) -> GitResult:
    """分離された作業ツリーを作る。branch が未作成なら base から切る。

    相対パスは対象リポジトリ基準で解釈されると利用者のリポジトリを汚すため、
    この境界で必ず絶対化する。
    """
    target = Path(workdir).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not branch_exists(repo, branch):
            porcelain.branch_create(str(repo), branch, base)
        porcelain.worktree_add(str(repo), str(target), branch=branch)
    except Exception as exc:  # noqa: BLE001
        return fail_result(f"作業ツリーを作れませんでした: {describe_error(exc)}")
    _link_untracked_dirs(Path(repo), target)
    return ok_result()


def _link_untracked_dirs(repo: Path, workdir: Path) -> None:
    """git 管理外の環境ディレクトリ（venv 等）を worktree から辿れるように symlink する。"""
    repo_abs = Path(repo).expanduser().resolve()
    linked: list[str] = []
    for name in _LINKED_UNTRACKED_DIRS:
        src, dst = repo_abs / name, workdir / name
        if not src.is_dir() or dst.exists():
            continue
        try:
            os.symlink(src, dst)
            linked.append(name)
        except OSError as exc:
            logger.warning("環境ディレクトリのリンクに失敗しました: %s (%s)", name, exc)
    if linked:
        _ignore_locally(workdir, linked)


def _ignore_locally(workdir: Path, names: Sequence[str]) -> None:
    """張ったリンクをこの worktree の中だけで git の対象外にする（利用者の .gitignore は触らない）。

    `node_modules/` のような末尾スラッシュの無視はシンボリックリンクに効かず、
    commit_all がリンクをコミットして統合マージが失敗するため。
    """
    try:
        with Repo(str(workdir)) as r:
            info_dir = Path(r.controldir()) / "info"  # worktree 固有の info/exclude
        info_dir.mkdir(parents=True, exist_ok=True)
        exclude = info_dir / "exclude"
        current = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
        add = [n for n in names if f"\n/{n}\n" not in f"\n{current}\n"]
        if add:
            exclude.write_text(
                current.rstrip("\n") + "\n" + "\n".join(f"/{n}" for n in add) + "\n",
                encoding="utf-8",
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("worktree の除外設定に失敗しました: %s", describe_error(exc))


def remove_worktree(repo: Path, workdir: Path) -> GitResult:
    """worktree を削除する（未コミット変更があっても片付ける）。symlink の先は消さない。"""
    target = Path(workdir).expanduser().resolve()
    try:
        for name in _LINKED_UNTRACKED_DIRS:  # 実体の venv 等を巻き込まないよう先に外す
            link = target / name
            if link.is_symlink():
                link.unlink()
        porcelain.worktree_remove(str(repo), str(target), force=True)
    except Exception as exc:  # noqa: BLE001
        return fail_result(f"作業ツリーを削除できませんでした: {describe_error(exc)}")
    return ok_result()


def list_worktrees(repo: Path) -> list[str]:
    """現在の worktree のパス一覧。取得失敗時は空リスト。"""
    try:
        return [str(info.path) for info in porcelain.worktree_list(str(repo))]
    except Exception:  # noqa: BLE001
        return []


def prune_worktrees(repo: Path) -> GitResult:
    """登録済みだが実体が消えた worktree を掃除する。"""
    try:
        porcelain.worktree_prune(str(repo))
    except Exception as exc:  # noqa: BLE001
        return fail_result(f"作業ツリーの掃除に失敗しました: {describe_error(exc)}")
    return ok_result()


def worktree_diff(workdir: Path) -> str:
    """HEAD との差分（未追跡ファイルも含む）。表示とレポート用で、再適用はしない。"""
    try:
        porcelain.add(str(workdir))
        buf = io.BytesIO()
        porcelain.diff(str(workdir), commit="HEAD", outstream=buf)
        return strip_ansi(buf.getvalue().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        logger.info("diff を取得できませんでした: %s", describe_error(exc))
        return ""


def commit_all(workdir: Path, message: str) -> GitResult:
    """worktree 内の全変更をコミットする（フックは実行しない = no-verify 相当）。"""
    try:
        porcelain.add(str(workdir))
        if not has_uncommitted_changes(workdir):
            return fail_result("コミットする変更がありません")
        who = _identity(workdir)
        with _open(workdir) as r:
            sha = porcelain.commit(
                r, message=message.encode("utf-8"), author=who, committer=who,
                no_verify=True, sign=False,
            )
    except Exception as exc:  # noqa: BLE001
        return fail_result(f"コミットに失敗しました: {describe_error(exc)}")
    return ok_result(sha.decode())


def merge_branch_into_worktree(workdir: Path, source_branch: str) -> GitResult:
    """source_branch を workdir がチェックアウト中のブランチへ取り込む（常にマージコミット）。

    メインリポジトリの HEAD は動かさない。競合・失敗時は統合側を元の状態へ戻し
    ok=False を返す。同一ファイルを双方が変えた場合の 3-way マージには merge3 が
    要り、無い環境では競合として扱う（安全側）。
    """
    try:
        with Repo(str(workdir)) as r:
            head_before = r.head()
    except Exception as exc:  # noqa: BLE001
        return fail_result(f"統合先を開けませんでした: {describe_error(exc)}")
    who = _identity(workdir)
    msg = f"Merge branch '{source_branch}'".encode()
    try:
        with _open(workdir) as r:
            _sha, conflicts = porcelain.merge(
                r, [source_branch], no_ff=True, message=msg, author=who, committer=who
            )
        if conflicts:
            _restore(workdir, head_before)
            names = ", ".join(c.decode("utf-8", "replace") for c in conflicts[:5])
            return fail_result(f"競合しました: {names}")
    except ImportError:
        _restore(workdir, head_before)
        return fail_result("同じファイルに双方の変更があり、自動で統合できません（競合として扱います）")
    except Exception as exc:  # noqa: BLE001
        _restore(workdir, head_before)
        return fail_result(f"統合に失敗しました: {describe_error(exc)}")
    return ok_result()


def _restore(workdir: Path, head: bytes) -> None:
    """統合前のコミットへ作業ツリーごと戻す（git merge --abort 相当）。"""
    try:
        porcelain.reset(str(workdir), "hard", head.decode())
    except Exception as exc:  # noqa: BLE001
        logger.warning("統合の巻き戻しに失敗しました: %s", describe_error(exc))


def push_branch(repo: Path, branch: str, remote: str = "origin") -> GitResult:
    """branch を remote へ push する。force はしない。https + GITHUB_TOKEN のみ（ssh は非対応）。"""
    from web.services.healing.git_read import remote_url

    url = remote_url(repo, remote)
    if not url:
        return fail_result(f"remote '{remote}' が設定されていません")
    if _SSH_URL.match(url):
        return fail_result("ssh の remote には対応していません。https の URL を指定してください")
    kwargs: dict[str, str] = {}
    if url.startswith("https://"):
        token = _github_token()
        if not token:
            return fail_result("GITHUB_TOKEN を設定してください（push に必要です）")
        kwargs = {"username": "x-access-token", "password": token}
    refspec = f"refs/heads/{branch}:refs/heads/{branch}"
    try:
        res = porcelain.push(
            str(repo), remote, [refspec], outstream=io.BytesIO(), errstream=io.BytesIO(), **kwargs
        )
    except Exception as exc:  # noqa: BLE001
        return fail_result(_redact(f"push に失敗しました: {describe_error(exc)}", kwargs))
    rejected = {
        ref: reason for ref, reason in (getattr(res, "ref_status", None) or {}).items() if reason
    }
    if rejected:
        reason = next(iter(rejected.values()))
        return fail_result(f"push が拒否されました: {_text(reason)}")
    return ok_result()


def _text(value: object) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def _github_token() -> str:
    try:
        from web.services.healing.github_client import github_config_from_env

        return github_config_from_env().token or ""
    except Exception:  # noqa: BLE001
        return os.environ.get("GITHUB_TOKEN", "")


def _redact(text: str, creds: dict[str, str]) -> str:
    secret = creds.get("password", "")
    return text.replace(secret, "***") if secret else text


def clone_shallow(url: str, dest: Path, depth: int = 1) -> GitResult:
    """url を dest へ浅く clone する。失敗時は途中の dest を残さない。認証プロンプトは出ない。"""
    import shutil

    try:
        porcelain.clone(url, str(dest), depth=depth, errstream=io.BytesIO()).close()
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(dest, ignore_errors=True)
        return fail_result(describe_error(exc))
    return ok_result()
