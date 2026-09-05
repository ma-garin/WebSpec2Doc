"""オートヒーリング（System 05）の GitHub 連携。

gh CLI があればそれを優先し、無ければ GITHUB_TOKEN で REST API を直接叩く
（依存追加を避けるため requests は使わず urllib のみを使う）。トークンは
ログにもレスポンスにも生で出さない（エラーメッセージへ埋め込まない）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from web.services.healing.types import ConnectionCheck, HealingError, PullRequestRef

ENV_GITHUB_TOKEN = "GITHUB_TOKEN"
ENV_GITHUB_REPO = "GITHUB_REPO"

_API_BASE = "https://api.github.com"
#: gh CLI・REST API 呼び出し共通のタイムアウト秒数。PR 作成は重くないため短め。
_TIMEOUT = 30


@dataclass(frozen=True)
class GitHubConfig:
    """GitHub 連携 1 件分の設定。token は REST API フォールバック時のみ使う。"""

    repo: str
    token: str = ""
    use_cli: bool = True


def github_config_from_env(repo: str = "") -> GitHubConfig:
    """環境変数 → .env の順で GITHUB_TOKEN / GITHUB_REPO を探して設定を組み立てる。

    env_store.py が既存の設定保存先（.env）なので、そこと同じ探索順序に
    揃える。use_cli は gh コマンドの有無で自動判定する（無ければ REST に
    フォールバックする合図として False にはしない。CLI が無ければ呼び出し側の
    分岐で自然に REST 経路へ落ちる）。
    """
    from web.env_store import _read_env

    env_repo = os.environ.get(ENV_GITHUB_REPO, "")
    env_token = os.environ.get(ENV_GITHUB_TOKEN, "")
    if not env_repo or not env_token:
        stored = _read_env()
        env_repo = env_repo or stored.get(ENV_GITHUB_REPO, "")
        env_token = env_token or stored.get(ENV_GITHUB_TOKEN, "")
    return GitHubConfig(repo=repo or env_repo, token=env_token, use_cli=True)


def _gh_cli_path() -> str | None:
    return shutil.which("gh")


def gh_cli_available() -> ConnectionCheck:
    """gh CLI が入っていて認証済みかを確認する。"""
    path = _gh_cli_path()
    if path is None:
        return ConnectionCheck(key="github", label="gh CLI", ok=False, detail="gh コマンドが見つかりません")
    try:
        proc = subprocess.run(  # nosec B603
            [path, "auth", "status"], capture_output=True, text=True, timeout=15
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return ConnectionCheck(key="github", label="gh CLI", ok=False, detail=f"gh auth status の実行に失敗しました: {exc}")
    if proc.returncode != 0:
        return ConnectionCheck(key="github", label="gh CLI", ok=False, detail="gh CLI が未認証です（gh auth login が必要）")
    return ConnectionCheck(key="github", label="gh CLI", ok=True, detail="認証済みです")


def verify_connection(cfg: GitHubConfig, repo_path: Path) -> ConnectionCheck:
    """「gh がある／認証済み／対象 repo にアクセスできる」を 1 つの結果に畳む。

    画面には「押したら動くのか」を 1 項目で見せたいため、内部で複数回
    確認しても呼び出し側には ConnectionCheck 1 個だけを返す。
    """
    if not cfg.repo:
        return ConnectionCheck(key="github", label="GitHub", ok=False, detail="github_repo が未設定です")

    if cfg.use_cli and _gh_cli_path() is not None:
        cli_check = gh_cli_available()
        if not cli_check.ok:
            return ConnectionCheck(key="github", label="GitHub", ok=False, detail=cli_check.detail)
        try:
            proc = subprocess.run(  # nosec B603
                ["gh", "repo", "view", cfg.repo, "--json", "name"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return ConnectionCheck(key="github", label="GitHub", ok=False, detail=f"gh repo view の実行に失敗しました: {exc}")
        if proc.returncode != 0:
            return ConnectionCheck(
                key="github", label="GitHub", ok=False, detail=f"リポジトリ {cfg.repo} にアクセスできません"
            )
        return ConnectionCheck(key="github", label="GitHub", ok=True, detail=f"gh CLI 経由で {cfg.repo} を確認しました")

    if not cfg.token:
        return ConnectionCheck(
            key="github",
            label="GitHub",
            ok=False,
            detail="GitHub 連携が未設定です。gh CLI か GITHUB_TOKEN が必要です",
        )
    try:
        _api_request(cfg, "GET", f"/repos/{cfg.repo}")
    except HealingError as exc:
        return ConnectionCheck(key="github", label="GitHub", ok=False, detail=str(exc))
    return ConnectionCheck(key="github", label="GitHub", ok=True, detail=f"REST API 経由で {cfg.repo} を確認しました")


def _pr_number_from_url(url: str) -> int:
    if not url:
        return 0
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def _pr_ref_from_api(data: dict[str, Any]) -> PullRequestRef:
    head = data.get("head") or {}
    return PullRequestRef(
        number=int(data.get("number") or 0),
        url=str(data.get("html_url") or ""),
        state="draft" if data.get("draft") else str(data.get("state") or "open"),
        title=str(data.get("title") or ""),
        branch=str(head.get("ref") or ""),
        created_at=str(data.get("created_at") or ""),
    )


def create_pull_request(
    cfg: GitHubConfig,
    *,
    repo_path: Path,
    head: str,
    base: str,
    title: str,
    body: str,
    draft: bool = False,
) -> PullRequestRef:
    """PR を作る。gh CLI 優先、無ければ REST API。

    body は標準入力（--body-file -）経由で渡す。引数に長文（不具合レポート
    全文）を載せるとコマンド長制限に当たるため。
    """
    if cfg.use_cli and _gh_cli_path() is not None:
        cmd = [
            "gh",
            "pr",
            "create",
            "--repo",
            cfg.repo,
            "--head",
            head,
            "--base",
            base,
            "--title",
            title,
            "--body-file",
            "-",
        ]
        if draft:
            cmd.append("--draft")
        try:
            proc = subprocess.run(  # nosec B603
                cmd, cwd=str(repo_path), input=body, capture_output=True, text=True, timeout=_TIMEOUT
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise HealingError(f"gh pr create の実行に失敗しました: {exc}") from exc
        if proc.returncode != 0:
            raise HealingError(f"PR 作成に失敗しました: {(proc.stderr or proc.stdout).strip()}")
        url = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        return PullRequestRef(
            number=_pr_number_from_url(url), url=url, state="draft" if draft else "open", title=title, branch=head
        )

    payload = {"title": title, "head": head, "base": base, "body": body, "draft": draft}
    data = _api_request(cfg, "POST", f"/repos/{cfg.repo}/pulls", payload)
    return _pr_ref_from_api(data)


def get_pull_request(cfg: GitHubConfig, *, repo_path: Path, number: int) -> PullRequestRef | None:
    """PR の現在状態を取得する。取得できなければ None（例外は投げない）。"""
    if cfg.use_cli and _gh_cli_path() is not None:
        try:
            proc = subprocess.run(  # nosec B603
                [
                    "gh",
                    "pr",
                    "view",
                    str(number),
                    "--repo",
                    cfg.repo,
                    "--json",
                    "number,url,state,title,headRefName,isDraft,createdAt",
                ],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        if proc.returncode != 0:
            return None
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return None
        return PullRequestRef(
            number=int(data.get("number") or 0),
            url=str(data.get("url") or ""),
            state="draft" if data.get("isDraft") else str(data.get("state") or "open").lower(),
            title=str(data.get("title") or ""),
            branch=str(data.get("headRefName") or ""),
            created_at=str(data.get("createdAt") or ""),
        )

    try:
        data = _api_request(cfg, "GET", f"/repos/{cfg.repo}/pulls/{number}")
    except HealingError:
        return None
    return _pr_ref_from_api(data)


def merge_pull_request(cfg: GitHubConfig, *, repo_path: Path, number: int, method: str = "squash") -> PullRequestRef:
    """PR をマージする。

    人の明示操作（画面のマージボタン）からしか呼ばれない前提で、ここでは
    実行するだけ。呼び出し順序のガード（承認済みか等）は呼び出し側の責務。
    """
    if cfg.use_cli and _gh_cli_path() is not None:
        flag = {"squash": "--squash", "merge": "--merge", "rebase": "--rebase"}.get(method, "--squash")
        try:
            proc = subprocess.run(  # nosec B603
                ["gh", "pr", "merge", str(number), "--repo", cfg.repo, flag],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise HealingError(f"gh pr merge の実行に失敗しました: {exc}") from exc
        if proc.returncode != 0:
            raise HealingError(f"PR #{number} のマージに失敗しました: {(proc.stderr or proc.stdout).strip()}")
        return get_pull_request(cfg, repo_path=repo_path, number=number) or PullRequestRef(number=number, state="merged")

    data = _api_request(cfg, "PUT", f"/repos/{cfg.repo}/pulls/{number}/merge", {"merge_method": method})
    return PullRequestRef(number=number, state="merged" if data.get("merged") else "open")


def close_pull_request(cfg: GitHubConfig, *, repo_path: Path, number: int) -> PullRequestRef:
    """PR をクローズする（マージせず却下する用）。"""
    if cfg.use_cli and _gh_cli_path() is not None:
        try:
            proc = subprocess.run(  # nosec B603
                ["gh", "pr", "close", str(number), "--repo", cfg.repo],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise HealingError(f"gh pr close の実行に失敗しました: {exc}") from exc
        if proc.returncode != 0:
            raise HealingError(f"PR #{number} のクローズに失敗しました: {(proc.stderr or proc.stdout).strip()}")
        return get_pull_request(cfg, repo_path=repo_path, number=number) or PullRequestRef(number=number, state="closed")

    data = _api_request(cfg, "PATCH", f"/repos/{cfg.repo}/pulls/{number}", {"state": "closed"})
    return _pr_ref_from_api(data)


def _api_request(cfg: GitHubConfig, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """REST API フォールバック経路。トークンが無ければここで HealingError にする。"""
    if not cfg.token:
        raise HealingError("GitHub 連携が未設定です。gh CLI か GITHUB_TOKEN が必要です")
    url = f"{_API_BASE}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {cfg.token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:  # nosec B310
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        # エラー本文にトークンは含まれないが、念のためログ相当の詳細も短く切る。
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise HealingError(f"GitHub API 呼び出しに失敗しました（{exc.code}）: {detail}") from exc
    except urllib.error.URLError as exc:
        raise HealingError(f"GitHub API に接続できません: {exc.reason}") from exc


def _verify_summary(result: Any) -> str:
    """VerifyResult 1 件を PR 本文の表セル用に要約する。None（未実行）も安全に扱う。"""
    if result is None:
        return "未実行"
    ok = bool(getattr(result, "ok", False))
    total = getattr(result, "total", 0) or 0
    passed = getattr(result, "passed", 0) or 0
    failed = getattr(result, "failed", 0) or 0
    if not total and not passed and not failed:
        return "成功" if ok else "失敗"
    label = "成功" if ok else "失敗"
    count = passed if ok else failed
    return f"{label} {count} / 全 {total}"


def build_pr_body(
    *,
    run_id: str,
    project_name: str,
    defects: Sequence[Any],
    proposals: Sequence[Any],
    verify_before: Any,
    verify_after: Any,
) -> str:
    """PR 本文を組み立てる。これ自体がバグレポートになる。

    Defect（事実）と FixProposal.rationale（判断）を分けて書く方針は
    types.py のドキュメント方針と揃える。verify_after が None（再検証が
    まだ走っていない）でも例外を出さない。
    """
    lines: list[str] = ["## 概要"]
    fixed_count = sum(1 for p in proposals if getattr(p, "status", "") == "applied")
    failed_before = getattr(verify_before, "failed", 0) if verify_before is not None else 0
    lines.append(
        f"{project_name or 'プロジェクト'} の検証で {failed_before} 件失敗し、"
        f"うち {fixed_count} 件を自動修正しました。"
    )
    lines.append("")

    lines.append("## 検出した不具合")
    lines.append("| # | 重大度 | 事象 | 該当箇所 |")
    lines.append("|---|---|---|---|")
    for i, defect in enumerate(defects, start=1):
        title = getattr(defect, "title", "") or getattr(defect, "message", "")
        severity = getattr(defect, "severity", "")
        suspect_files = getattr(defect, "suspect_files", ()) or ()
        files = ", ".join(suspect_files) or "-"
        lines.append(f"| {i} | {severity} | {title} | {files} |")
    lines.append("")

    lines.append("## 修正内容")
    proposal_by_defect = {getattr(p, "defect_id", ""): p for p in proposals}
    for i, defect in enumerate(defects, start=1):
        title = getattr(defect, "title", "") or getattr(defect, "message", "")
        lines.append(f"### {i}. {title}")
        proposal = proposal_by_defect.get(getattr(defect, "defect_id", ""))
        if proposal is None:
            lines.append("- **原因の判断**: 未着手（対応する修正案なし）")
            lines.append("- **修正**: 未着手")
            lines.append("- **変更ファイル**: なし")
        else:
            lines.append(f"- **原因の判断**: {getattr(proposal, 'rationale', '') or '未記載'}")
            lines.append(f"- **修正**: {getattr(proposal, 'summary', '') or '未記載'}")
            files_changed = getattr(proposal, "files_changed", ()) or ()
            files_md = ", ".join(f"`{f}`" for f in files_changed) or "なし"
            lines.append(f"- **変更ファイル**: {files_md}")
        lines.append("")

    lines.append("## 検証結果")
    lines.append("| | 実行前 | 実行後 |")
    lines.append("|---|---|---|")
    lines.append(f"| 結果 | {_verify_summary(verify_before)} | {_verify_summary(verify_after)} |")
    lines.append("")

    lines.append("## 未検証の事項")
    lines.append(
        "- 自動検証コマンドの実行結果のみに基づく判断です。UI での手動確認、"
        "および検証コマンドの対象外にある機能への影響は確認していません。"
    )
    lines.append("")

    lines.append("---")
    lines.append(
        f"WebSpec2Doc オートヒーリング（run: {run_id}）が自動生成しました。"
        "**マージ前に人のレビューが必要です。**"
    )
    return "\n".join(lines)
