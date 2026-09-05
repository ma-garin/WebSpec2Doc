"""オートヒーリング（System 05）対象プロジェクトの永続化。

登録済みプロジェクトを out_dir/".healing"/"projects.json" に保存する。
テナント分離のため out_dir は必ず引数で受け取る（defect_store.py と同じ方針。
グローバルに解決しない）。

allowed_roots() がローカル任意ディレクトリ読み取りを防ぐ唯一のガードなので、
resolve_repo_path() での検証を弱めてはならない。
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Mapping
from dataclasses import fields, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from web.services.healing.types import ConnectionCheck, HealingError, HealingProject

#: 保存先ルートのディレクトリ名。先頭のドットは必須
#: （web/routes/pages.py の cli_mode がドット始まり以外を「解析済みドメイン」として
#: 列挙してしまうため、ここを変えると一覧画面が壊れる）。
HEALING_DIR_NAME = ".healing"

#: ヒーリング対象として許可するリポジトリの親ディレクトリ一覧（os.pathsep 区切り）。
ENV_ALLOWED_ROOTS = "WEBSPEC2DOC_HEALING_ROOTS"

_PROJECTS_FILE = "projects.json"
_PROJECT_FIELDS = {f.name for f in fields(HealingProject)}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def healing_dir(out_dir: Path) -> Path:
    """テナント分離済み出力先の下にあるヒーリング用ルート。"""
    return Path(out_dir) / HEALING_DIR_NAME


def _projects_path(out_dir: Path) -> Path:
    return healing_dir(out_dir) / _PROJECTS_FILE


ENV_WORKTREE_DIR = "WEBSPEC2DOC_HEALING_WORKTREE_DIR"


def worktree_root() -> Path:
    """ヒーリング用の作業ツリーを置く場所。

    **WebSpec2Doc 自身のディレクトリの中に置いてはならない。**
    worktree の中で対象リポジトリのテストを走らせるため、置き場所が
    WebSpec2Doc のリポジトリ内（例: output/.healing/worktrees/…）だと、
    pytest の rootdir 判定・conftest.py・pyproject.toml が WebSpec2Doc 側の
    ものを拾い、対象リポジトリのテストが「別のプロジェクトの中」で動く。
    実測では WebSpec2Doc の app.py が対象の app パッケージを覆い隠し、
    収集エラーになった。

    既定は OS の一時ディレクトリ配下。WEBSPEC2DOC_HEALING_WORKTREE_DIR で変えられる。
    実行結果の JSON（run_store）は従来どおりテナント別の output/.healing に残す。
    ここに置くのは作業ツリーの実体だけ。
    """
    import tempfile

    raw = os.environ.get(ENV_WORKTREE_DIR, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path(tempfile.gettempdir()) / "webspec2doc-healing").resolve()


def allowed_roots() -> list[Path]:
    """ヒーリング対象として登録してよいディレクトリの一覧。

    WEBSPEC2DOC_HEALING_ROOTS（os.pathsep 区切り）を読む。未設定ならカレント
    ディレクトリのみを許可する。ローカル任意ディレクトリ読み取りを防ぐ唯一の
    ガードなので、ここを甘くしない。
    """
    raw = os.environ.get(ENV_ALLOWED_ROOTS, "")
    if not raw.strip():
        return [Path.cwd().resolve()]
    roots = [
        Path(part.strip()).expanduser().resolve()
        for part in raw.split(os.pathsep)
        if part.strip()
    ]
    return roots or [Path.cwd().resolve()]


def resolve_repo_path(raw: str) -> Path:
    """入力を許可ルート配下の git リポジトリとして検証し、絶対パスで返す。

    違反時は日本語で理由と許可ルート一覧を入れた HealingError を投げる。
    """
    text = str(raw or "").strip()
    if not text:
        raise HealingError("リポジトリパスが空です")
    if "\x00" in text:
        raise HealingError(f"リポジトリパスに不正な文字が含まれています: {raw!r}")

    path = Path(text).expanduser().resolve()
    roots = allowed_roots()
    if not any(path == root or root in path.parents for root in roots):
        root_list = "\n".join(f"- {root}" for root in roots)
        raise HealingError(
            f"許可されていないディレクトリです: {path}\n許可ルート:\n{root_list}\n"
            f"（{ENV_ALLOWED_ROOTS} で許可ルートを追加できます）"
        )
    if not (path / ".git").exists():
        raise HealingError(f"git リポジトリではありません（.git が見つかりません）: {path}")
    return path


# ─────────────────────────── 入出力 ───────────────────────────


def _read_all(out_dir: Path) -> list[dict[str, Any]]:
    path = _projects_path(out_dir)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("projects") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _write_all(out_dir: Path, items: list[dict[str, Any]]) -> None:
    path = _projects_path(out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": _now(), "projects": items}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # 実行中に読まれるため原子的に置換する


def _to_project(data: Mapping[str, Any]) -> HealingProject:
    filtered = {k: v for k, v in data.items() if k in _PROJECT_FIELDS}
    return HealingProject(**filtered)


# ─────────────────────────── CRUD ───────────────────────────


def list_projects(out_dir: Path) -> list[HealingProject]:
    """登録済みプロジェクトを作成順に返す。未作成・破損時は空リスト。"""
    projects: list[HealingProject] = []
    for item in _read_all(out_dir):
        try:
            projects.append(_to_project(item))
        except TypeError:
            continue  # 壊れた 1 件で一覧全体を落とさない
    return projects


def get_project(out_dir: Path, project_id: str) -> HealingProject | None:
    for project in list_projects(out_dir):
        if project.project_id == project_id:
            return project
    return None


def create_project(out_dir: Path, **fields_: Any) -> HealingProject:
    """プロジェクトを 1 件登録する。repo_path は resolve_repo_path を通した絶対パスにする。"""
    resolved = resolve_repo_path(fields_.get("repo_path", ""))
    name = str(fields_.get("name") or "").strip() or resolved.name
    now = _now()

    filtered = {k: v for k, v in fields_.items() if k in _PROJECT_FIELDS}
    filtered.update(
        project_id=uuid.uuid4().hex[:12],
        repo_path=str(resolved),
        name=name,
        created_at=now,
        updated_at=now,
    )
    project = HealingProject(**filtered)

    items = _read_all(out_dir)
    items.append(project.to_dict())
    _write_all(out_dir, items)
    return project


def update_project(out_dir: Path, project_id: str, updates: Mapping[str, Any]) -> HealingProject:
    """既存プロジェクトを更新する。project_id 自体は書き換えられない。"""
    items = _read_all(out_dir)
    idx = next((i for i, item in enumerate(items) if item.get("project_id") == project_id), None)
    if idx is None:
        raise HealingError(f"プロジェクトが見つかりません: {project_id}")

    current = _to_project(items[idx])
    changes = {k: v for k, v in updates.items() if k in _PROJECT_FIELDS and k != "project_id"}
    if "repo_path" in changes:
        changes["repo_path"] = str(resolve_repo_path(changes["repo_path"]))
    changes["updated_at"] = _now()

    updated = replace(current, **changes)
    items[idx] = updated.to_dict()
    _write_all(out_dir, items)
    return updated


def delete_project(out_dir: Path, project_id: str) -> bool:
    items = _read_all(out_dir)
    remaining = [item for item in items if item.get("project_id") != project_id]
    if len(remaining) == len(items):
        return False
    _write_all(out_dir, remaining)
    return True


# ─────────────────────────── 接続確認 ───────────────────────────


def _mask_home(text: str) -> str:
    """表示用にホームディレクトリを ~ へ置き換える（判定は必ず実パスで行う）。"""
    home = str(Path.home())
    return text.replace(home, "~") if home else text


def _short_path(path: Path | None) -> str:
    """画面で切れないよう、末尾 3 セグメントだけを残した表示用パスを返す。"""
    if path is None:
        return "(未設定)"
    masked = _mask_home(str(path))
    parts = Path(masked).parts
    if len(parts) <= 3:
        return masked
    return "…/" + "/".join(parts[-3:])


def _with_action(detail: str, action: str) -> str:
    """原因の後ろに対処を 1 文だけ足す。長い説明は書かない。"""
    text = _mask_home(str(detail or "")).strip()
    if not text:
        return action
    if not text.endswith(("。", ".", "!", "?")):
        text += "。"
    return f"{text}{action}"


def _check_repo(repo_path: Path | None) -> ConnectionCheck:
    """パスが存在し、許可ルート配下かどうか（NG なら実行できない）。"""
    label = "リポジトリパス"
    try:
        roots = allowed_roots()
        exists = bool(repo_path and repo_path.exists())
        in_roots = bool(repo_path) and any(
            repo_path == root or root in repo_path.parents for root in roots
        )
        if exists and in_roots:
            detail = f"リポジトリを確認しました: {_short_path(repo_path)}"
        elif not exists:
            detail = _with_action(
                f"パスが見つかりません: {_short_path(repo_path)}",
                "接続の編集で正しいリポジトリパスを入力してください。",
            )
        else:
            detail = _with_action(
                f"許可ルートの外です: {_short_path(repo_path)}",
                f"{ENV_ALLOWED_ROOTS} に親ディレクトリを追加してください。",
            )
        return ConnectionCheck(
            key="repo", label=label, ok=exists and in_roots, detail=detail, severity="required"
        )
    except Exception as exc:  # noqa: BLE001 - 1項目の失敗で全体を落とさない
        detail = _with_action(str(exc), "接続の編集でリポジトリパスを確認してください。")
        return ConnectionCheck(key="repo", label=label, ok=False, detail=detail, severity="required")


def _check_git(repo_path: Path | None) -> ConnectionCheck:
    """git リポジトリとして読めるか（NG なら実行できない）。"""
    label = "git リポジトリ"
    try:
        from web.services.healing import git_ops

        is_repo = bool(repo_path) and git_ops.is_git_repo(repo_path)
        branch = str(git_ops.current_branch(repo_path) or "") if is_repo else ""
        if is_repo:
            detail = (
                f"git リポジトリを確認しました（現在のブランチ {branch}）"
                if branch
                else "git リポジトリを確認しました"
            )
        else:
            detail = _with_action(
                f"git リポジトリではありません: {_short_path(repo_path)}",
                "git init 済みのディレクトリを指定してください。",
            )
        return ConnectionCheck(key="git", label=label, ok=is_repo, detail=detail, severity="required")
    except Exception as exc:  # noqa: BLE001
        detail = _with_action(str(exc), "git コマンドが使えるかを確認してください。")
        return ConnectionCheck(key="git", label=label, ok=False, detail=detail, severity="required")


def _check_remote(repo_path: Path | None, remote: str) -> ConnectionCheck:
    """リモートから owner/name が取れるか（NG でもループは動く。PR だけ困る）。"""
    label = "リモート"
    try:
        from web.services.healing import git_ops

        url = str(git_ops.remote_url(repo_path, remote) or "") if repo_path else ""
        owner_name = str(git_ops.github_repo_from_remote(url) or "") if url else ""
        if url and owner_name:
            detail = f"リモート '{remote}' を確認しました（{owner_name}）"
        elif url:
            detail = _with_action(
                f"リモート '{remote}' から owner/name を取り出せません",
                "接続の編集で github_repo を直接入力してください。",
            )
        else:
            detail = _with_action(
                f"remote '{remote}' が見つかりません",
                "PR を作るにはリモートの設定が必要です。",
            )
        return ConnectionCheck(
            key="remote", label=label, ok=bool(url and owner_name), detail=detail, severity="optional"
        )
    except Exception as exc:  # noqa: BLE001
        detail = _with_action(str(exc), "PR を作るにはリモートの設定が必要です。")
        return ConnectionCheck(key="remote", label=label, ok=False, detail=detail, severity="optional")


def _check_github(github_repo: str, repo_path: Path | None) -> ConnectionCheck:
    """GitHub へ到達できるか（NG でもループは動く。PR だけ困る）。"""
    label = "GitHub"
    action = "接続の編集で owner/name を入れるか、リモートを設定してください。"
    try:
        from web.services.healing import github_client

        config = github_client.github_config_from_env(github_repo)
        result = github_client.verify_connection(config, repo_path)
        ok = bool(result.ok) if isinstance(result, ConnectionCheck) else bool(result)
        raw = result.detail if isinstance(result, ConnectionCheck) else str(result)
        if isinstance(result, ConnectionCheck) and result.label:
            label = result.label
        detail = _mask_home(str(raw or "")) if ok else _with_action(str(raw or ""), action)
        return ConnectionCheck(key="github", label=label, ok=ok, detail=detail, severity="optional")
    except Exception as exc:  # noqa: BLE001
        return ConnectionCheck(
            key="github", label=label, ok=False, detail=_with_action(str(exc), action), severity="optional"
        )


def _check_verify_command(verify_command: str) -> ConnectionCheck:
    """検証コマンドが設定されているか（NG なら実行できない）。"""
    command = str(verify_command or "").strip()
    detail = (
        f"検証コマンドを確認しました: {_mask_home(command)}"
        if command
        else _with_action(
            "検証コマンドが未設定です",
            "接続の編集で pytest などの実行コマンドを入力してください。",
        )
    )
    return ConnectionCheck(
        key="verify_command", label="検証コマンド", ok=bool(command), detail=detail, severity="required"
    )


def check_connection(project: HealingProject) -> list[ConnectionCheck]:
    """「押したら動くのか」を先に見せるための 5 項目チェック。

    severity="required" が 1 つでも NG なら実行そのものが成立しない。
    severity="optional"（remote / github）は NG でも検証・修正ループは動き、
    PR を作るときにだけ効いてくる。detail は必ず「原因 + 対処 1 文」で書く。

    git_ops / github_client の import 失敗・実行時例外は 1 項目ずつ握りつぶし、
    他の項目の判定に波及させない。
    """
    repo_path = Path(project.repo_path) if project.repo_path else None
    return [
        _check_repo(repo_path),
        _check_git(repo_path),
        _check_remote(repo_path, project.remote),
        _check_github(project.github_repo, repo_path),
        _check_verify_command(project.verify_command),
    ]
