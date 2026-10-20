"""System 05: 外部 CLI（claude / codex / gh）を使わない修正エージェントと GitHub 連携の契約テスト。"""

from __future__ import annotations

import ast
import io
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

import pytest

from web.services.healing import agents, git_ops
from web.services.healing import github_client as gh
from web.services.healing.types import AgentTask, Defect, HealingError, HealingProject

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def no_cli(monkeypatch):
    """PATH に claude / codex / gh / git が無い状態。外部プロセス起動は即失敗させる。"""
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)

    def _boom(*a, **k):
        raise AssertionError(f"subprocess を呼んではいけない: {a[:1]}")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)


# ───────────── edits の適用 ─────────────


def test_apply_edits_single_match_replaces(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    files = agents.apply_edits(tmp_path, [{"path": "a.py", "old": "x = 1", "new": "x = 10"}])
    assert files == ["a.py"]
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 10\ny = 2\n"


def test_apply_edits_no_match_reports_and_changes_nothing(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 1\n", encoding="utf-8")
    with pytest.raises(agents.EditError, match="一致する箇所がありません"):
        agents.apply_edits(
            tmp_path,
            [{"path": "b.py", "old": "y = 1", "new": "y = 2"}, {"path": "a.py", "old": "zzz", "new": "q"}],
        )
    # 全か無か: 先の edit も書かれていない
    assert (tmp_path / "b.py").read_text(encoding="utf-8") == "y = 1\n"


def test_apply_edits_multiple_matches_is_error(tmp_path):
    (tmp_path / "a.py").write_text("x\nx\n", encoding="utf-8")
    with pytest.raises(agents.EditError, match="2 箇所"):
        agents.apply_edits(tmp_path, [{"path": "a.py", "old": "x", "new": "z"}])
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x\nx\n"


def test_apply_edits_creates_new_file_only_when_absent(tmp_path):
    agents.apply_edits(tmp_path, [{"path": "sub/n.txt", "old": "", "new": "hi"}])
    assert (tmp_path / "sub" / "n.txt").read_text(encoding="utf-8") == "hi"
    with pytest.raises(agents.EditError, match="既に存在"):
        agents.apply_edits(tmp_path, [{"path": "sub/n.txt", "old": "", "new": "again"}])


def test_apply_edits_sequential_edits_on_same_file(tmp_path):
    (tmp_path / "a.txt").write_text("one two", encoding="utf-8")
    agents.apply_edits(
        tmp_path,
        [{"path": "a.txt", "old": "one", "new": "1"}, {"path": "a.txt", "old": "1 two", "new": "done"}],
    )
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "done"


@pytest.mark.parametrize("bad", ["../escape.txt", "/etc/passwd", "a/../../x", ".git/config", ""])
def test_apply_edits_rejects_path_traversal(tmp_path, bad):
    repo = tmp_path / "wt"
    (repo / ".git").mkdir(parents=True)
    with pytest.raises(agents.EditError):
        agents.apply_edits(repo, [{"path": bad, "old": "", "new": "pwn"}])
    assert not (tmp_path / "escape.txt").exists()


def test_apply_edits_rejects_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    repo = tmp_path / "wt"
    repo.mkdir()
    (repo / "link").symlink_to(outside)
    with pytest.raises(agents.EditError, match="外"):
        agents.apply_edits(repo, [{"path": "link/x.txt", "old": "", "new": "pwn"}])
    assert not (outside / "x.txt").exists()


def test_parse_edits_accepts_fence_and_rejects_garbage():
    body = '{"summary": "s", "edits": []}'
    assert agents._parse_edits("```json\n" + body + "\n```")["summary"] == "s"
    assert agents._parse_edits("前置き " + body + " 後書き")["edits"] == []
    with pytest.raises(agents.EditError):
        agents._parse_edits("not json")
    with pytest.raises(agents.EditError):
        agents._parse_edits('{"summary": "no edits key"}')


# ───────────── エージェント選択（PATH に CLI 無し） ─────────────


def test_registry_has_no_claude_or_codex(no_cli, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert agents.available_agents() == ["openai", "ollama", "dryrun"]
    names = {a["name"] for a in agents.describe_agents() if a["name"] != "ollama"}
    assert names == {"openai", "dryrun"}
    blob = json.dumps(agents.describe_agents(), ensure_ascii=False).lower()
    assert "claude" not in blob and "codex" not in blob


def test_legacy_agent_name_maps_to_openai(no_cli):
    assert isinstance(agents.get_agent("claude"), agents.OpenAIAgent)
    assert isinstance(agents.get_agent("codex"), agents.OpenAIAgent)
    with pytest.raises(HealingError):
        agents.get_agent("unknown")


def _make_project(agent: str) -> HealingProject:
    import dataclasses

    kwargs = {}
    for f in dataclasses.fields(HealingProject):
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            kwargs[f.name] = "x"
    return HealingProject(**{**kwargs, "agent": agent})


def test_saved_project_with_legacy_agent_runs_as_openai():
    assert _make_project("claude").agent == "openai"
    assert _make_project("codex").agent == "openai"
    assert _make_project("ollama").agent == "ollama"


# ───────────── OpenAI エージェントの 1 件修正（edits 契約） ─────────────


def _task(tmp_path: Path) -> AgentTask:
    return AgentTask(
        defect=Defect(defect_id="d1", title="t", message="m", suspect_files=("a.py",)),
        workdir=str(tmp_path),
        repo_root=str(tmp_path),
        verify_command="pytest",
        timeout_sec=5,
    )


@pytest.fixture
def fake_diff(monkeypatch):
    monkeypatch.setattr(git_ops, "worktree_diff", lambda p: "diff --git a/a.py b/a.py\n+x\n")
    monkeypatch.setattr(git_ops, "changed_files", lambda p: ["a.py"])


def _agent_with_replies(monkeypatch, replies):
    prompts: list[str] = []
    it = iter(replies)

    def _call(self, prompt, timeout):
        prompts.append(prompt)
        return next(it), "log"

    monkeypatch.setattr(agents.OpenAIAgent, "_call", _call)
    return agents.OpenAIAgent(), prompts


def test_openai_agent_applies_edits_without_any_cli(no_cli, fake_diff, tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("v = 1\n", encoding="utf-8")
    reply = json.dumps({"summary": "直した", "rationale": "原因: a\n対応: b", "edits": [{"path": "a.py", "old": "v = 1", "new": "v = 2"}]})
    agent, prompts = _agent_with_replies(monkeypatch, [reply])
    proposal = agent.propose_fix(_task(tmp_path))
    assert proposal.status == "applied"
    assert proposal.files_changed == ("a.py",)
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "v = 2\n"
    assert "edits" in prompts[0] and "unified diff" not in prompts[0]


def test_openai_agent_retries_once_with_reason_then_succeeds(no_cli, fake_diff, tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("v = 1\n", encoding="utf-8")
    bad = json.dumps({"edits": [{"path": "a.py", "old": "nope", "new": "x"}]})
    good = json.dumps({"edits": [{"path": "a.py", "old": "v = 1", "new": "v = 3"}]})
    agent, prompts = _agent_with_replies(monkeypatch, [bad, good])
    proposal = agent.propose_fix(_task(tmp_path))
    assert proposal.status == "applied"
    assert len(prompts) == 2 and "一致する箇所がありません" in prompts[1]


def test_openai_agent_fails_after_second_mismatch(no_cli, fake_diff, tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("v = 1\n", encoding="utf-8")
    bad = json.dumps({"edits": [{"path": "a.py", "old": "nope", "new": "x"}]})
    agent, prompts = _agent_with_replies(monkeypatch, [bad, bad, bad])
    proposal = agent.propose_fix(_task(tmp_path))
    assert proposal.status == "failed"
    assert len(prompts) == 2
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "v = 1\n"


def test_openai_agent_traversal_fails_and_writes_nothing(no_cli, fake_diff, tmp_path, monkeypatch):
    wd = tmp_path / "wt"
    wd.mkdir()
    bad = json.dumps({"edits": [{"path": "../pwn.txt", "old": "", "new": "x"}]})
    agent, _ = _agent_with_replies(monkeypatch, [bad, bad])
    proposal = agent.propose_fix(_task(wd))
    assert proposal.status == "failed"
    assert not (tmp_path / "pwn.txt").exists()


def test_openai_agent_empty_edits_is_skipped(no_cli, monkeypatch, tmp_path):
    monkeypatch.setattr(git_ops, "worktree_diff", lambda p: "")
    monkeypatch.setattr(git_ops, "changed_files", lambda p: [])
    agent, _ = _agent_with_replies(monkeypatch, [json.dumps({"summary": "不要", "edits": []})])
    assert agent.propose_fix(_task(tmp_path)).status == "skipped"


# ───────────── GitHub: REST のみ ─────────────


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def rest(no_cli, monkeypatch):
    calls: list[tuple[str, str, dict | None, str]] = []
    state = {"payload": {}}

    def _urlopen(req, timeout=None):
        body = json.loads(req.data) if req.data else None
        calls.append((req.get_method(), req.full_url, body, req.get_header("Authorization")))
        return _Resp(json.dumps(state["payload"]).encode())

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    return calls, state


CFG = gh.GitHubConfig(repo="o/r", token="tok-1234567890")


def test_create_pull_request_uses_rest_only(rest, tmp_path):
    calls, state = rest
    state["payload"] = {"number": 7, "html_url": "https://github.com/o/r/pull/7", "state": "open", "head": {"ref": "b"}, "title": "T"}
    ref = gh.create_pull_request(CFG, repo_path=tmp_path, head="b", base="main", title="T", body="B", draft=True)
    assert (ref.number, ref.url) == (7, "https://github.com/o/r/pull/7")
    method, url, body, auth = calls[0]
    assert (method, url) == ("POST", "https://api.github.com/repos/o/r/pulls")
    assert body["draft"] is True and auth == "Bearer tok-1234567890"


def test_get_merge_close_use_rest_only(rest, tmp_path):
    calls, state = rest
    state["payload"] = {"number": 7, "state": "open", "html_url": "u", "head": {"ref": "b"}}
    assert gh.get_pull_request(CFG, repo_path=tmp_path, number=7).number == 7
    state["payload"] = {"merged": True}
    assert gh.merge_pull_request(CFG, repo_path=tmp_path, number=7, method="rebase").state == "merged"
    state["payload"] = {"number": 7, "state": "closed", "html_url": "u", "head": {"ref": "b"}}
    assert gh.close_pull_request(CFG, repo_path=tmp_path, number=7).state == "closed"
    assert [c[0] for c in calls] == ["GET", "PUT", "PATCH"]
    assert calls[1][2] == {"merge_method": "rebase"}
    assert calls[2][2] == {"state": "closed"}


def test_verify_connection_ok_via_rest(rest, tmp_path):
    calls, state = rest
    state["payload"] = {"name": "r"}
    check = gh.verify_connection(CFG, tmp_path)
    assert check.ok and calls[0][:2] == ("GET", "https://api.github.com/repos/o/r")


def test_missing_token_fails_explicitly_with_next_action(no_cli, tmp_path):
    cfg = gh.GitHubConfig(repo="o/r", token="")
    check = gh.verify_connection(cfg, tmp_path)
    assert not check.ok and "GITHUB_TOKEN を設定してください" in check.detail
    assert not gh.github_token_check(cfg).ok
    with pytest.raises(HealingError, match="GITHUB_TOKEN を設定してください"):
        gh.create_pull_request(cfg, repo_path=tmp_path, head="b", base="main", title="T", body="B")


def test_token_never_in_error_message(no_cli, monkeypatch, tmp_path):
    def _urlopen(req, timeout=None):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    with pytest.raises(HealingError) as ei:
        gh.create_pull_request(CFG, repo_path=tmp_path, head="b", base="main", title="T", body="B")
    assert CFG.token not in str(ei.value)


# ───────────── 回帰ガード（静的） ─────────────

_BANNED_IMPORTS = {"subprocess", "shutil"}


@pytest.mark.parametrize("rel", ["web/services/healing/agents.py", "web/services/healing/github_client.py"])
def test_no_subprocess_in_agents_and_github(rel):
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & _BANNED_IMPORTS), imported & _BANNED_IMPORTS


def test_no_agent_cli_names_in_product_sources():
    for rel in ("web/services/healing/agents.py", "web/services/healing/github_client.py", "templates/healing.html"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for needle in ("ClaudeCodeAgent", "CodexAgent", '"gh"', "gh_cli_available", "use_cli"):
            assert needle not in text, f"{rel}: {needle}"


def test_project_default_agent_is_openai():
    assert HealingProject.__dataclass_fields__["agent"].default == "openai"
