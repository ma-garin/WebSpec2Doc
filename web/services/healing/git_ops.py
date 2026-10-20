"""オートヒーリング（System 05）向けの git 操作の入口。

実装は dulwich（読取: git_read.py / 書込: git_write.py）で、製品の実行時に
git コマンドは起動しない。公開関数と GitResult は従来のまま再エクスポートする。
worktree による分離が中核で、1 エージェント = 1 worktree = 1 ブランチにする。
"""

from __future__ import annotations

import logging
import re

from web.services.healing.git_common import GitResult  # noqa: F401 - 再エクスポート
from web.services.healing.git_read import (  # noqa: F401 - 再エクスポート
    branch_exists,
    branch_is_merged_into,
    changed_files,
    current_branch,
    has_uncommitted_changes,
    is_git_repo,
    list_branches,
    recent_changed_files,
    remote_url,
    status_porcelain,
)
from web.services.healing.git_write import (  # noqa: F401 - 再エクスポート
    clone_shallow,
    commit_all,
    create_branch,
    create_worktree,
    delete_branch,
    list_worktrees,
    merge_branch_into_worktree,
    prune_worktrees,
    push_branch,
    remove_worktree,
    worktree_diff,
)

logger = logging.getLogger(__name__)

#: ブランチ名の最大長。長すぎる defect_id 由来の名前を切り詰めるための上限。
_BRANCH_NAME_MAX_LEN = 100
#: git のブランチ名規則に違反しうる文字。空白と ~ ^ : ? * [ \ を一括でハイフンへ置換する。
_UNSAFE_BRANCH_CHARS = re.compile(r"[\s~^:?*\[\\]")


def github_repo_from_remote(url: str) -> str:
    """remote URL から "owner/name" を取り出す。取れなければ空文字。

    対応形式:
        git@github.com:owner/name.git
        https://github.com/owner/name.git
        https://github.com/owner/name
    """
    if not url:
        return ""
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    if not match:
        return ""
    owner, name = match.group(1), match.group(2)
    if not owner or not name:
        return ""
    return f"{owner}/{name}"


def safe_branch_name(raw: str) -> str:
    """git のブランチ名規則違反を除去して安全な名前にする。

    ".." と空白・~^:?*[\\ を取り除き、連続する "/" を 1 つに畳み、先頭末尾の
    "/" を外し、長さ 100 に切る。すべて除去して空になったら "healing" を返す
    （空文字のブランチ名は git が受け付けないため、呼び出し側を必ず動かす）。
    """
    name = (raw or "").replace("..", "-")
    name = _UNSAFE_BRANCH_CHARS.sub("-", name)
    name = re.sub(r"/{2,}", "/", name)
    name = name.strip("/")
    name = name[:_BRANCH_NAME_MAX_LEN]
    name = name.strip("/")
    return name or "healing"
