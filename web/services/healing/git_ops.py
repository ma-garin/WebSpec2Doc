"""オートヒーリング（System 05）向けの git 操作。

worktree による分離が中核。複数エージェントが同じリポジトリを同時に
書き換えても衝突しないよう、1 エージェント = 1 worktree = 1 ブランチにする。
他モジュール（orchestrator / agent）はここにしか git コマンドを直接叩かせない
ことで、実行方法（timeout・nosec・エラー表現）を一箇所に閉じ込める。
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

#: ブランチ名の最大長。長すぎる defect_id 由来の名前を切り詰めるための上限。
_BRANCH_NAME_MAX_LEN = 100
#: git のブランチ名規則に違反しうる文字。空白と ~ ^ : ? * [ \ を一括でハイフンへ置換する。
_UNSAFE_BRANCH_CHARS = re.compile(r"[\s~^:?*\[\\]")


@dataclass(frozen=True)
class GitResult:
    """git コマンド 1 回分の結果。

    例外を投げる代わりにこの型で失敗を表現する。呼び出し側（orchestrator）は
    try/except を書かずに ok を見るだけで分岐できる。
    """

    ok: bool
    stdout: str
    stderr: str
    exit_code: int


def run_git(repo: Path, args: Sequence[str], timeout: int = 120) -> GitResult:
    """`git -C <repo> <args>` を実行する。

    timeout 超過やプロセス起動失敗（git 未インストール等）でも例外を外へ
    伝播させず、GitResult(ok=False, ...) に畳んで返す。呼び出し側の分岐を
    「例外 or 正常」ではなく「ok or not ok」の 1 種類に統一するため。
    """
    cmd = ["git", "-C", str(repo), *args]
    try:
        proc = subprocess.run(  # nosec B603
            cmd, capture_output=True, text=True, timeout=timeout
        )
        # ANSI エスケープシーケンスをエラーメッセージから除去する。
        # 対象リポジトリの pre-commit フックが出力する色付けやフォーマット指示を
        # 画面表示用の結果から削る（worktree 環境での失敗メッセージをクリーンにするため）。
        clean_stderr = re.sub(r"\x1b\[[0-9;]*m", "", proc.stderr)
        return GitResult(
            ok=proc.returncode == 0,
            stdout=proc.stdout,
            stderr=clean_stderr,
            exit_code=proc.returncode,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        return GitResult(ok=False, stdout=stdout, stderr=f"timeout after {timeout}s", exit_code=-1)
    except OSError as exc:
        return GitResult(ok=False, stdout="", stderr=str(exc), exit_code=-1)


def is_git_repo(path: Path) -> bool:
    """path が git の作業ツリーの内側かどうか。"""
    result = run_git(path, ["rev-parse", "--is-inside-work-tree"], timeout=10)
    return result.ok and result.stdout.strip() == "true"


def current_branch(repo: Path) -> str:
    """現在チェックアウト中のブランチ名。取得できなければ空文字。"""
    result = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
    return result.stdout.strip() if result.ok else ""


def remote_url(repo: Path, remote: str = "origin") -> str:
    """remote の URL。未設定・取得失敗なら空文字。"""
    result = run_git(repo, ["remote", "get-url", remote], timeout=10)
    return result.stdout.strip() if result.ok else ""


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


def branch_exists(repo: Path, branch: str) -> bool:
    """ローカルブランチが既にあるか。"""
    result = run_git(repo, ["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], timeout=15)
    return result.ok and bool(result.stdout.strip())


def create_worktree(repo: Path, branch: str, base: str, workdir: Path) -> GitResult:
    """分離された作業ツリーを作る。1 エージェント = 1 worktree = 1 ブランチの単位そのもの。

    branch が未作成なら `-b` で base から切って作る。既にある場合は `-b` を付けない。
    呼び出し側が先に create_branch している経路と、worktree だけで作る経路の
    両方があり、`-b` 固定にすると前者が必ず "already exists" で落ちる
    （呼び出し順を呼び出し側に覚えさせるのではなく、ここで吸収する）。
    """
    # 相対パスを渡してはならない。run_git は `git -C <repo>` で実行するため、
    # git は相対パスを**対象リポジトリ基準**で解決し、作業ツリーが対象リポジトリの
    # 中に作られる（実測で output/.healing/... が対象リポジトリ内に作られた）。
    # 「利用者のリポジトリを汚さない・分離する」という前提が根元から壊れるので、
    # 呼び出し側に絶対パスを要求するのではなく、この境界で必ず絶対化する。
    target = Path(workdir).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if branch_exists(repo, branch):
        result = run_git(repo, ["worktree", "add", str(target), branch], timeout=60)
    else:
        result = run_git(
            repo, ["worktree", "add", "-b", branch, str(target), base], timeout=60
        )
    if result.ok:
        _link_untracked_dirs(Path(repo), target)
    return result


#: worktree へリンクする git 管理外のディレクトリ。
#: worktree には git が追跡していないものがコピーされないため、これらを
#: 前提にした検証コマンド（venv/bin/python -m pytest 等）が必ず起動に失敗する。
_LINKED_UNTRACKED_DIRS = ("venv", ".venv", "node_modules")


def _link_untracked_dirs(repo: Path, workdir: Path) -> None:
    """git 管理外の環境ディレクトリを worktree から辿れるようにする。

    worktree には venv や node_modules が無いため、相対パスの検証コマンドは
    「No such file or directory: 'venv/bin/python'」で必ず落ちる（2026-09-05 実測）。
    実体をコピーすると重いので symlink を張る。リンクに失敗しても実行は続ける
    （絶対パスの検証コマンドなら影響しないため、ここで止める必要はない）。
    """
    # リンク先は必ず絶対パスにする。相対パスのまま張ると、worktree の中から見て
    # 自分自身を指すリンクになり、venv/bin/python に到達できない（実測で確認）。
    repo_abs = Path(repo).expanduser().resolve()
    linked: list[str] = []
    for name in _LINKED_UNTRACKED_DIRS:
        src = repo_abs / name
        dst = workdir / name
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
    """張ったリンクを、この worktree の中だけで git の対象外にする。

    対象リポジトリの .gitignore が `node_modules/`（末尾スラッシュ）と書いていると
    ディレクトリしか無視されず、**シンボリックリンクはファイル扱いで無視されない**。
    その結果 `git add -A` でリンクがコミットされ、統合ブランチへのマージが
    「untracked working tree files would be overwritten」で必ず失敗する（実測）。

    対象リポジトリの .gitignore は書き換えない（利用者のファイルを勝手に変えない）。
    worktree 固有の .git/info/exclude に書けば、この作業ツリーの中でだけ効く。
    """
    try:
        # worktree では .git はファイルで、本体の gitdir を指している。
        info_dir = Path(
            run_git(workdir, ["rev-parse", "--git-path", "info"], timeout=10).stdout.strip()
        )
        if not info_dir.is_absolute():
            info_dir = workdir / info_dir
        info_dir.mkdir(parents=True, exist_ok=True)
        exclude = info_dir / "exclude"
        current = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
        add = [n for n in names if f"\n/{n}\n" not in f"\n{current}\n"]
        if add:
            exclude.write_text(
                current.rstrip("\n") + "\n" + "\n".join(f"/{n}" for n in add) + "\n",
                encoding="utf-8",
            )
    except OSError as exc:
        logger.warning("worktree の除外設定に失敗しました: %s", exc)


def remove_worktree(repo: Path, workdir: Path) -> GitResult:
    """worktree を削除する。

    --force を付けるのは、未コミット変更が残っていても片付けを完了させるため
    （エージェントが失敗して未コミットのまま終わるケースを想定）。呼び出し側は
    差分を先に回収済みの worktree だけを渡す前提。
    """
    # 追加時と同じ理由で絶対パスにする（相対だと別の場所を消しにいく）。
    target = Path(workdir).expanduser().resolve()
    return run_git(repo, ["worktree", "remove", "--force", str(target)], timeout=30)


def list_worktrees(repo: Path) -> list[str]:
    """現在の worktree のパス一覧を返す。取得失敗時は空リスト。"""
    result = run_git(repo, ["worktree", "list", "--porcelain"], timeout=10)
    if not result.ok:
        return []
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            paths.append(line[len("worktree ") :].strip())
    return paths


def worktree_diff(workdir: Path) -> str:
    """HEAD との差分を返す（未追跡ファイルも含める）。

    `git diff` は既定で未追跡ファイルを無視するため、先に `git add -N .`
    （intent-to-add）でインデックスに登録してから diff を取る。add -N は
    内容をステージしない（パスだけ登録する）ので、後続の commit_all が
    素直に `git add -A` できる状態を壊さない。
    """
    run_git(workdir, ["add", "-N", "."], timeout=30)
    result = run_git(workdir, ["diff", "HEAD"], timeout=30)
    return result.stdout if result.ok else ""


def changed_files(workdir: Path) -> list[str]:
    """変更されたファイルのパス一覧（未追跡・リネーム含む）。"""
    result = run_git(workdir, ["status", "--porcelain"], timeout=15)
    if not result.ok:
        return []
    files: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        # porcelain の各行は "XY path" 形式。リネームは "XY old -> new"。
        path_part = line[3:]
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[1]
        files.append(path_part.strip())
    return files


def commit_all(workdir: Path, message: str) -> GitResult:
    """worktree 内の全変更をコミットする。

    `git add -A` を使うのは worktree が分離済みで他エージェントの変更と
    混ざらないため（メイン作業ツリーに対しては絶対にこの関数を使わない）。
    """
    add_result = run_git(workdir, ["add", "-A"], timeout=30)
    if not add_result.ok:
        return add_result
    # worktree には git 管理外のファイル（venv/ など）がコピーされないため、
    # 対象リポジトリの pre-commit フックがそれを要求すると必ず失敗する。
    # このコミットは統合ブランチへの一時的なもので、品質は再検証（verify_after）で
    # 担保しているため、フックを飛ばしてよい。
    return run_git(workdir, ["commit", "--no-verify", "-m", message], timeout=30)


def create_branch(repo: Path, branch: str, base: str) -> GitResult:
    """base を起点に branch を作る（チェックアウトはしない）。"""
    return run_git(repo, ["branch", branch, base], timeout=15)


def push_branch(repo: Path, branch: str, remote: str = "origin") -> GitResult:
    """branch を remote へ push する。

    --force は絶対に使わない。main/master へ直接 push する関数もここには
    置かない（統合は PR 経由か merge_worktree_into 経由に限定するため）。
    """
    return run_git(repo, ["push", remote, branch], timeout=60)


def has_uncommitted_changes(repo: Path) -> bool:
    """作業ツリーに未コミットの変更があるか。"""
    result = run_git(repo, ["status", "--porcelain"], timeout=15)
    return result.ok and bool(result.stdout.strip())


def merge_branch_into_worktree(workdir: Path, source_branch: str) -> GitResult:
    """source_branch（各エージェントのブランチ）を workdir がチェックアウト中のブランチへ取り込む。

    マージは**統合 worktree の中で**行う。メインリポジトリ側で
    `git checkout <統合ブランチ>` してからマージすると 2 つ問題が起きる:
      1. 統合ブランチは統合 worktree が既にチェックアウトしているため git が拒否する
      2. 利用者が今作業しているブランチを黙って切り替えてしまう
    ヒーリングは「利用者の作業ツリーを触らない」ことが前提なので、
    メインリポジトリの HEAD は最後まで動かさない。

    --no-ff で必ずマージコミットを残す（どの defect 由来の変更かを履歴に残すため）。
    --no-edit は自動実行中にエディタが開いて止まるのを避けるだけで、マージの意味は変えない。
    競合したら `git merge --abort` で状態を戻し、ok=False と stderr（競合内容）を返す。
    """
    merge_result = run_git(workdir, ["merge", "--no-ff", "--no-edit", source_branch], timeout=60)
    if not merge_result.ok:
        run_git(workdir, ["merge", "--abort"], timeout=15)
    return merge_result


#: 削除を絶対に許さないブランチ名。利用者の主ブランチを消す事故を防ぐ最終防波堤。
_PROTECTED_BRANCHES = frozenset({"main", "master"})


def delete_branch(repo: Path, branch: str) -> GitResult:
    """統合・欠陥ブランチを削除する（後片付け用。利用者のブランチを消しうる唯一の関数）。

    main/master と、現在チェックアウト中のブランチは削除を実行せず即座に
    ok=False を返す。ここで弾かないと「片付けのつもりでメインリポジトリの
    作業中ブランチを消す」事故が起きうるため、ガードを他関数へ委譲しない。
    """
    if branch in _PROTECTED_BRANCHES or branch == current_branch(repo):
        return GitResult(
            ok=False, stdout="", stderr=f"保護されたブランチは削除しません: {branch}", exit_code=1
        )
    return run_git(repo, ["branch", "-D", branch], timeout=15)


def prune_worktrees(repo: Path) -> GitResult:
    """登録済みだが実体ディレクトリが既に消えた worktree を掃除する。

    remove_worktree を使わずディレクトリだけ消したケース（利用者による手動削除等）を
    ここで拾う。実体が残る worktree には触れない（prune は git 側で安全に保証される）。
    """
    return run_git(repo, ["worktree", "prune"], timeout=30)


def list_branches(repo: Path, prefix: str = "") -> list[str]:
    """ローカルブランチ名の一覧。prefix 指定時はその接頭辞のものだけに絞る。

    取得に失敗しても例外は投げず空リストを返す（後片付けの一覧取得を
    落ちない前提にするため。呼び出し側は「対象がなかった」と区別しなくてよい）。
    """
    result = run_git(repo, ["for-each-ref", "--format=%(refname:short)", "refs/heads/"], timeout=15)
    if not result.ok:
        return []
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not prefix:
        return names
    return [name for name in names if name.startswith(prefix)]


def branch_is_merged_into(repo: Path, branch: str, target: str) -> bool:
    """branch が target へ既に取り込まれているか（削除してよい判定に使う）。

    `merge-base --is-ancestor` の終了コードで判定する。取得失敗（比較不能）は
    False を返す。「マージ済みか分からないものは削除させない」という安全側に
    倒すためで、真偽不明を True 扱いにしない。
    """
    result = run_git(repo, ["merge-base", "--is-ancestor", branch, target], timeout=15)
    return result.ok
