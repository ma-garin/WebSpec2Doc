"""オートヒーリングの git 操作が dulwich だけで動くことの unit テスト。

git コマンドを起動しない（PATH から git を外し subprocess も塞いだ状態で通る）。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from dulwich import porcelain
from dulwich.repo import Repo
from web.services.healing import git_ops

_WHO = b"t <t@t>"


@pytest.fixture(autouse=True)
def _no_external_commands(monkeypatch):
    def _blocked(*_a, **_k):
        raise AssertionError("外部コマンドを起動してはいけません")

    monkeypatch.setattr(shutil, "which", lambda *_a, **_k: None)
    monkeypatch.setattr(subprocess, "run", _blocked)
    monkeypatch.setattr(subprocess, "Popen", _blocked)
    monkeypatch.setenv("PATH", "")


def _commit(repo: Path, name: str, text: str, msg: str = "c") -> None:
    (repo / name).write_text(text)
    porcelain.add(str(repo), [str(repo / name)])
    with Repo(str(repo)) as r:
        r.hooks.clear()  # テストの準備コミットでもフック（外部プロセス）を走らせない
        porcelain.commit(r, message=msg.encode(), author=_WHO, committer=_WHO, no_verify=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    porcelain.init(str(r))
    _commit(r, "a.txt", "a\nb\nc\n", "init")
    return r


def test_read_ops(repo, tmp_path):
    assert git_ops.is_git_repo(repo)
    plain = tmp_path / "plain"
    plain.mkdir()
    assert git_ops.is_git_repo(plain) is False
    assert git_ops.current_branch(repo) == "master"
    assert git_ops.current_branch(plain) == ""
    assert git_ops.remote_url(repo) == ""
    porcelain.remote_add(str(repo), "origin", "https://github.com/o/n.git")
    assert git_ops.github_repo_from_remote(git_ops.remote_url(repo)) == "o/n"
    assert git_ops.branch_exists(repo, "master") and not git_ops.branch_exists(repo, "x")
    assert git_ops.create_branch(repo, "healing/x", "HEAD").ok
    assert git_ops.list_branches(repo) == ["healing/x", "master"]
    assert git_ops.list_branches(repo, prefix="healing/") == ["healing/x"]
    assert git_ops.branch_is_merged_into(repo, "healing/x", "master")
    assert git_ops.recent_changed_files(repo) == ["a.txt"]


def test_changed_files_and_status(repo):
    assert not git_ops.has_uncommitted_changes(repo)
    (repo / "a.txt").write_text("changed\n")
    (repo / "new.txt").write_text("n\n")
    assert set(git_ops.changed_files(repo)) == {"a.txt", "new.txt"}
    tracked = git_ops.status_porcelain(repo, include_untracked=False)
    assert tracked.ok and "new.txt" not in tracked.stdout and "a.txt" in tracked.stdout


def test_delete_branch_guards(repo):
    git_ops.create_branch(repo, "tmp", "HEAD")
    assert not git_ops.delete_branch(repo, "master").ok
    assert git_ops.delete_branch(repo, "tmp").ok
    assert "tmp" not in git_ops.list_branches(repo)


def test_worktree_cycle_leaves_main_clean(repo, tmp_path):
    wt = tmp_path / "wt" / "d1"
    (repo / "venv").mkdir()
    (repo / "venv" / "keep.txt").write_text("keep")
    assert git_ops.create_worktree(repo, "healing/d1", "master", wt).ok
    assert str(wt.resolve()) in [str(Path(p).resolve()) for p in git_ops.list_worktrees(repo)]
    (wt / "a.txt").write_text("a\nB\nc\n")
    (wt / "added.txt").write_text("new\n")
    diff = git_ops.worktree_diff(wt)
    assert "+B" in diff and "added.txt" in diff
    commit = git_ops.commit_all(wt, "fix: x")
    assert commit.ok, commit.stderr
    assert not git_ops.commit_all(wt, "again").ok  # 変更なし
    assert "venv" not in git_ops.recent_changed_files(wt)  # symlink はコミットされない
    assert git_ops.remove_worktree(repo, wt).ok
    assert not wt.exists()
    assert (repo / "venv" / "keep.txt").read_text() == "keep"  # 実体は消えない
    assert (repo / "a.txt").read_text() == "a\nb\nc\n"
    assert git_ops.changed_files(repo) == ["venv/"]  # 元から未追跡の venv 以外は汚れない


def test_merge_two_worktrees(repo, tmp_path):
    wts = {}
    for b in ("integ", "d1", "d2"):
        wts[b] = tmp_path / b
        assert git_ops.create_worktree(repo, b, "master", wts[b]).ok
    (wts["d1"] / "x.txt").write_text("1\n")
    (wts["d2"] / "y.txt").write_text("2\n")
    assert git_ops.commit_all(wts["d1"], "d1").ok and git_ops.commit_all(wts["d2"], "d2").ok
    assert git_ops.merge_branch_into_worktree(wts["integ"], "d1").ok
    assert git_ops.merge_branch_into_worktree(wts["integ"], "d2").ok
    assert (wts["integ"] / "x.txt").exists() and (wts["integ"] / "y.txt").exists()
    assert git_ops.branch_is_merged_into(repo, "d1", "integ")


def test_merge_conflict_restores_integration(repo, tmp_path, monkeypatch):
    integ, d1 = tmp_path / "integ", tmp_path / "d1"
    git_ops.create_worktree(repo, "integ", "master", integ)
    git_ops.create_worktree(repo, "d1", "master", d1)
    (d1 / "a.txt").write_text("ONE\n")
    git_ops.commit_all(d1, "d1")
    before = (integ / "a.txt").read_text()

    def _conflict(*_a, **_k):
        (integ / "a.txt").write_text("<<<<<<<\n")
        return None, [b"a.txt"]

    monkeypatch.setattr(porcelain, "merge", _conflict)
    res = git_ops.merge_branch_into_worktree(integ, "d1")
    assert not res.ok and "a.txt" in res.stderr
    assert (integ / "a.txt").read_text() == before

    def _no_merge3(*_a, **_k):
        raise ImportError("merge3 module is required")

    monkeypatch.setattr(porcelain, "merge", _no_merge3)
    assert not git_ops.merge_branch_into_worktree(integ, "d1").ok


def test_push_local_and_ssh_rejected(repo, tmp_path):
    git_ops.create_branch(repo, "feat", "HEAD")
    bare = tmp_path / "bare.git"
    porcelain.init(str(bare), bare=True)
    porcelain.remote_add(str(repo), "origin", str(bare))
    assert git_ops.push_branch(repo, "feat").ok
    assert b"feat" in porcelain.branch_list(str(bare))
    porcelain.remote_add(str(repo), "sshr", "git@github.com:o/n.git")
    res = git_ops.push_branch(repo, "feat", "sshr")
    assert not res.ok and "https" in res.stderr


def test_push_https_requires_token(repo, monkeypatch):
    porcelain.remote_add(str(repo), "origin", "https://github.com/o/n.git")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(
        "web.services.healing.github_client.github_config_from_env",
        lambda *_a, **_k: type("C", (), {"token": ""})(),
    )
    res = git_ops.push_branch(repo, "master")
    assert not res.ok and "GITHUB_TOKEN" in res.stderr


def test_clone_shallow_and_cleanup(repo, tmp_path):
    ok = git_ops.clone_shallow("file://" + str(repo), tmp_path / "c1", depth=1)
    assert ok.ok and (tmp_path / "c1" / "a.txt").exists()
    bad = git_ops.clone_shallow("file://" + str(tmp_path / "missing"), tmp_path / "c2")
    assert not bad.ok and not (tmp_path / "c2").exists()


def test_recent_files_for_localization(repo):
    from web.services.healing.localization import _get_recent_files

    _commit(repo, "m.py", "x=1\n", "py")
    assert _get_recent_files(repo) == ["m.py"]


def test_no_subprocess_import_in_git_modules():
    root = Path(git_ops.__file__).parent
    for name in ("git_common.py", "git_read.py", "git_write.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "import subprocess" not in text
