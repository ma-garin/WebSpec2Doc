#!/usr/bin/env python3
"""ゲート実行（pytest / make test / verify-ui / lint 等）をユーザー要求時のみに制限する PreToolUse フック。

根拠: .claude/rules/speed-harness.md H-7（2026-08-22 ユーザー指示）。
ユーザーが明示的に要求した場合に限り、コマンドに GATES_REQUESTED=1 を含めて実行する。

誤検知対策: ヒアドキュメント本文と引用文字列を除去してから、コマンド開始位置
（文字列先頭・改行・&& / || / ; / | の直後）だけを照合する。
ドキュメントやコミットメッセージに「make test」と書くことまでは止めない。
"""
import json
import re
import sys

# コマンド開始位置 + 任意の環境変数代入列 + ゲート本体
_GATE_PATTERN = re.compile(
    r"(?:^|&&|\|\||;|\||\n)\s*"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*"
    r"(?:venv/bin/)?(?:python3?\s+-m\s+)?"
    r"(?:pytest\b|make\s+(?:test|verify-ui|verify-all|lint|coverage)\b)"
)
_HEREDOC = re.compile(r"<<-?\s*'?\"?(\w+)'?\"?.*?\n.*?\n\1\s*$", re.DOTALL | re.MULTILINE)
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if data.get("tool_name") != "Bash":
        return 0
    cmd = data.get("tool_input", {}).get("command", "")
    if "GATES_REQUESTED=1" in cmd:
        return 0
    stripped = _HEREDOC.sub("", cmd)
    stripped = _QUOTED.sub("", stripped)
    if not _GATE_PATTERN.search(stripped):
        return 0
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "H-7: pytest / make test / verify-ui / lint はユーザーが要求した時のみ実行する。"
                "ユーザーの明示要求がある場合に限り GATES_REQUESTED=1 を付けて実行すること。"
            ),
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
