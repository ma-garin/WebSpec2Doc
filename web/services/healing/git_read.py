"""git の読取操作（dulwich 実装。git コマンドは起動しない）。

失敗しても例外を外へ出さず、空文字・空リスト・False に畳む。
"""

from __future__ import annotations

import logging
from pathlib import Path

from dulwich import porcelain
from dulwich.diff_tree import tree_changes
from dulwich.errors import NotGitRepository
from dulwich.objectspec import parse_commit
from dulwich.repo import Repo

from web.services.healing.git_common import GitResult, describe_error, fail_result, ok_result

logger = logging.getLogger(__name__)

_HEADS = b"refs/heads/"


def _text(value: bytes | str) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def is_git_repo(path: Path) -> bool:
    """path が git の作業ツリーの内側かどうか。"""
    try:
        with Repo.discover(str(path)) as repo:
            return not repo.bare
    except (NotGitRepository, OSError, ValueError):
        return False


def current_branch(repo: Path) -> str:
    """現在チェックアウト中のブランチ名。detached は "HEAD"、取得できなければ空文字。"""
    try:
        with Repo(str(repo)) as r:
            chain, _sha = r.refs.follow(b"HEAD")
            target = chain[-1]
            if not target.startswith(_HEADS):
                return "HEAD"
            if target not in r.refs:
                return ""  # コミット前（unborn）
            return _text(target[len(_HEADS) :])
    except Exception as exc:  # noqa: BLE001 - 読取は落とさない
        logger.debug("current_branch 失敗: %s", describe_error(exc))
        return ""


def remote_url(repo: Path, remote: str = "origin") -> str:
    """remote の URL。未設定・取得失敗なら空文字。"""
    try:
        with Repo(str(repo)) as r:
            return _text(r.get_config().get((b"remote", remote.encode()), b"url")).strip()
    except Exception:  # noqa: BLE001
        return ""


def branch_exists(repo: Path, branch: str) -> bool:
    """ローカルブランチが既にあるか。"""
    try:
        with Repo(str(repo)) as r:
            return _HEADS + branch.encode() in r.refs
    except Exception:  # noqa: BLE001
        return False


def list_branches(repo: Path, prefix: str = "") -> list[str]:
    """ローカルブランチ名の一覧。prefix 指定時はその接頭辞のものだけに絞る。失敗時は空。"""
    try:
        names = sorted(_text(b) for b in porcelain.branch_list(str(repo)))
    except Exception:  # noqa: BLE001
        return []
    return [n for n in names if n.startswith(prefix)] if prefix else names


def branch_is_merged_into(repo: Path, branch: str, target: str) -> bool:
    """branch が target へ既に取り込まれているか（祖先判定）。比較不能は False（安全側）。"""
    try:
        with Repo(str(repo)) as r:
            b = parse_commit(r, branch).id
            t = parse_commit(r, target).id
            if b == t:
                return True
            return b in porcelain.merge_base(r, [b, t])
    except Exception:  # noqa: BLE001
        return False


def status_porcelain(repo: Path, include_untracked: bool = True) -> GitResult:
    """`git status --porcelain` 相当。stdout は "XY path" 形式の行。"""
    try:
        st = porcelain.status(str(repo), untracked_files="normal" if include_untracked else "no")
    except Exception as exc:  # noqa: BLE001
        return fail_result(f"状態を取得できませんでした: {describe_error(exc)}")
    lines: list[str] = []
    for kind, code in (("add", "A "), ("modify", "M "), ("delete", "D ")):
        lines += [f"{code} {_text(p)}" for p in sorted(st.staged.get(kind, []))]
    for p in sorted(st.unstaged):
        deleted = not (Path(repo) / _text(p)).exists()
        lines.append(f" {'D' if deleted else 'M'} {_text(p)}")
    if include_untracked:
        lines += [f"?? {_text(p)}" for p in sorted(st.untracked)]
    return ok_result("\n".join(lines) + ("\n" if lines else ""))


def changed_files(workdir: Path) -> list[str]:
    """変更されたファイルのパス一覧（未追跡含む）。"""
    result = status_porcelain(workdir)
    if not result.ok:
        return []
    seen: list[str] = []
    for line in result.stdout.splitlines():
        path = line[3:].strip()
        if path and path not in seen:
            seen.append(path)
    return seen


def has_uncommitted_changes(repo: Path) -> bool:
    """作業ツリーに未コミットの変更があるか。"""
    result = status_porcelain(repo)
    return result.ok and bool(result.stdout.strip())


def recent_changed_files(repo: Path, limit: int = 20) -> list[str]:
    """直近 limit 件のコミットで変更されたファイル（`git log -n --name-only` 相当）。失敗時は空。"""
    try:
        with Repo(str(repo)) as r:
            names: list[str] = []
            for entry in r.get_walker(max_entries=limit):
                commit = entry.commit
                if len(commit.parents) > 1:
                    continue  # git log --name-only は merge の差分を出さない
                old_tree = r[commit.parents[0]].tree if commit.parents else None
                for change in tree_changes(r.object_store, old_tree, commit.tree):
                    new = change.new.path
                    if new:
                        names.append(_text(new))
            return names
    except Exception:  # noqa: BLE001
        return []
