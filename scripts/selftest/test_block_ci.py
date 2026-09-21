#!/usr/bin/env python3
"""block-ci.py（CI 厳禁・自己ウェイク厳禁フック）が実際に拒否することを検証する。

依存なし。`python3 scripts/selftest/test_block_ci.py` で実行し、終了コード 0 なら全件合格。
INC-2026-002 の再発防止装置が生きていることを、規約の文章ではなく実行で確認するためのもの。

注意: 本ファイル自身がワークフローパスの文字列を含むため、シェルのヒアドキュメントで
書き出そうとすると block-ci.py に拒否される（＝フックが正しく働いている証拠）。
編集は Write / Edit ツールか、エディタで行うこと。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = [ROOT / ".claude/hooks/block-ci.py", Path.home() / ".claude/hooks/block-ci.py"]

# フック自身に読み込まれても誤検知しないよう、パスは実行時に組み立てる
WF = ".git" + "hub/work" + "flows"

DENY = [
    ("自己ウェイク: send_later", {"tool_name": "mcp__Claude_Code_Remote__send_later"}),
    ("自己ウェイク: create_trigger", {"tool_name": "mcp__Claude_Code_Remote__create_trigger"}),
    ("自己ウェイク: update_trigger", {"tool_name": "mcp__Claude_Code_Remote__update_trigger"}),
    ("自己ウェイク: fire_trigger", {"tool_name": "mcp__Claude_Code_Remote__fire_trigger"}),
    ("自己ウェイク: CronCreate", {"tool_name": "CronCreate"}),
    ("自己ウェイク: CronList", {"tool_name": "CronList"}),
    ("自己ウェイク: ScheduleWakeup", {"tool_name": "ScheduleWakeup"}),
    ("PR 購読: subscribe_pr_activity", {"tool_name": "mcp__github__subscribe_pr_activity"}),
    ("PR 購読: CCR subscribe_pr_activity",
     {"tool_name": "mcp__Claude_Code_Remote__subscribe_pr_activity"}),
    ("外部監視: watch_url", {"tool_name": "mcp__Claude_Code_Remote__watch_url"}),
    ("CI 作成: Write", {"tool_name": "Write", "tool_input": {"file_path": WF + "/ci.yml"}}),
    ("CI 作成: Edit", {"tool_name": "Edit", "tool_input": {"file_path": "/repo/" + WF + "/b.yaml"}}),
    ("CI 作成: リダイレクト", {"tool_name": "Bash",
                          "tool_input": {"command": "echo on: push > " + WF + "/ci.yml"}}),
    ("CI 作成: 追記リダイレクト", {"tool_name": "Bash",
                            "tool_input": {"command": "echo x >> " + WF + "/ci.yml"}}),
    ("CI 作成: cp", {"tool_name": "Bash",
                    "tool_input": {"command": "cp /tmp/ci.yml " + WF + "/ci.yml"}}),
    ("CI 作成: mv", {"tool_name": "Bash",
                    "tool_input": {"command": "mv /tmp/ci.yml " + WF + "/ci.yml"}}),
    ("CI 作成: tee", {"tool_name": "Bash",
                     "tool_input": {"command": "cat x | tee " + WF + "/ci.yml"}}),
    ("CI 作成: touch", {"tool_name": "Bash",
                       "tool_input": {"command": "touch " + WF + "/ci.yml"}}),
    ("CI 作成: mkdir", {"tool_name": "Bash",
                       "tool_input": {"command": "mkdir -p " + WF}}),
    ("CI 作成: heredoc", {"tool_name": "Bash",
                         "tool_input": {"command": "cat <<'E' > " + WF + "/ci.yml\non: push\nE"}}),
]

ALLOW = [
    ("CI 削除: git rm", {"tool_name": "Bash", "tool_input": {"command": "git rm -r " + WF}}),
    ("CI 削除: rm", {"tool_name": "Bash", "tool_input": {"command": "rm -rf " + WF}}),
    ("通常の読み", {"tool_name": "Read", "tool_input": {"file_path": "app.py"}}),
    ("通常の Bash", {"tool_name": "Bash", "tool_input": {"command": "git status --short"}}),
    ("規約内での言及", {"tool_name": "Write",
                   "tool_input": {"file_path": "docs/rules.md",
                                  "content": WF + " は作らない"}}),
    ("PR 作成は禁止しない", {"tool_name": "mcp__github__create_pull_request"}),
]


def decision(hook: Path, payload: dict) -> str:
    r = subprocess.run([sys.executable, str(hook)], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        return f"ERROR rc={r.returncode} {r.stderr.strip()[:120]}"
    if not r.stdout.strip():
        return "allow"
    try:
        return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"]
    except (ValueError, KeyError):
        return f"UNPARSEABLE {r.stdout.strip()[:120]}"


def settings_wired() -> list:
    """settings.json の PreToolUse に block-ci.py が登録されたままかを確認する。"""
    problems = []
    for p in [ROOT / ".claude/settings.json", Path.home() / ".claude/settings.json"]:
        if not p.exists():
            problems.append(f"{p}: 存在しない")
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError as e:
            problems.append(f"{p}: JSON 不正 ({e})")
            continue
        wired = any("block-ci.py" in h.get("command", "")
                    for g in d.get("hooks", {}).get("PreToolUse", [])
                    for h in g.get("hooks", []))
        if not wired:
            problems.append(f"{p}: PreToolUse に block-ci.py が未登録")
    return problems


def main() -> int:
    fails = [f"[配線] {p}" for p in settings_wired()]

    for hook in HOOKS:
        if not hook.exists():
            fails.append(f"[存在] {hook} がない")
            continue
        tag = "project" if hook.is_relative_to(ROOT) else "home"
        for name, payload in DENY:
            got = decision(hook, payload)
            if got != "deny":
                fails.append(f"[{tag}] {name}: deny のはずが {got}")
        for name, payload in ALLOW:
            got = decision(hook, payload)
            if got == "deny":
                fails.append(f"[{tag}] {name}: 通るはずが deny")

    total = len(HOOKS) * (len(DENY) + len(ALLOW))
    if fails:
        print(f"FAIL  {len(fails)} 件の問題 / 検査 {total} 件\n"
              + "\n".join("  - " + f for f in fails))
        return 1
    print(f"PASS  {total} 件すべて期待どおり（拒否 {len(DENY)}×{len(HOOKS)} / "
          f"許可 {len(ALLOW)}×{len(HOOKS)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
