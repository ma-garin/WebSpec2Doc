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


def check_connection(project: HealingProject) -> list[ConnectionCheck]:
    """「押したら動くのか」を先に見せるための 5 項目チェック。

    git_ops / github_client は別エージェントが並行実装中のため、ここでは
    契約として渡された署名だけを信じて呼ぶ。import 失敗・実行時例外は
    1 項目ずつ握りつぶし、他の項目の判定に波及させない。
    """
    checks: list[ConnectionCheck] = []
    repo_path = Path(project.repo_path) if project.repo_path else None

    # repo: パスが存在し許可ルート配下か
    try:
        roots = allowed_roots()
        exists = bool(repo_path and repo_path.exists())
        in_roots = bool(repo_path) and any(
            repo_path == root or root in repo_path.parents for root in roots
        )
        ok = exists and in_roots
        checks.append(
            ConnectionCheck(
                key="repo",
                label="リポジトリパス",
                ok=ok,
                detail=str(repo_path) if ok else f"存在={exists} 許可ルート内={in_roots}",
            )
        )
    except Exception as exc:  # noqa: BLE001 - 1項目の失敗で全体を落とさない
        checks.append(ConnectionCheck(key="repo", label="リポジトリパス", ok=False, detail=str(exc)))

    # git: is_git_repo と現在ブランチ
    try:
        from web.services.healing import git_ops

        is_repo = bool(repo_path) and git_ops.is_git_repo(repo_path)
        branch = git_ops.current_branch(repo_path) if is_repo else ""
        checks.append(
            ConnectionCheck(key="git", label="git リポジトリ", ok=is_repo, detail=str(branch or ""))
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(ConnectionCheck(key="git", label="git リポジトリ", ok=False, detail=str(exc)))

    # remote: remote_url が取れるか、そこから owner/name が取れるか
    try:
        from web.services.healing import git_ops

        url = git_ops.remote_url(repo_path, project.remote) if repo_path else ""
        owner_name = git_ops.github_repo_from_remote(url) if url else ""
        ok = bool(url and owner_name)
        detail = f"{url} -> {owner_name}" if url else f"remote '{project.remote}' が見つかりません"
        checks.append(ConnectionCheck(key="remote", label="リモート", ok=ok, detail=detail))
    except Exception as exc:  # noqa: BLE001
        checks.append(ConnectionCheck(key="remote", label="リモート", ok=False, detail=str(exc)))

    # github: verify_connection の結果をそのまま使う
    try:
        from web.services.healing import github_client

        config = github_client.github_config_from_env(project.github_repo)
        result = github_client.verify_connection(config, repo_path)
        if isinstance(result, ConnectionCheck):
            checks.append(replace(result, key="github", label=result.label or "GitHub"))
        else:
            checks.append(ConnectionCheck(key="github", label="GitHub", ok=bool(result), detail=str(result)))
    except Exception as exc:  # noqa: BLE001
        checks.append(ConnectionCheck(key="github", label="GitHub", ok=False, detail=str(exc)))

    # verify_command: 空なら検証できない
    has_command = bool(str(project.verify_command or "").strip())
    checks.append(
        ConnectionCheck(
            key="verify_command",
            label="検証コマンド",
            ok=has_command,
            detail=project.verify_command if has_command else "検証コマンドが未設定です",
        )
    )

    return checks
