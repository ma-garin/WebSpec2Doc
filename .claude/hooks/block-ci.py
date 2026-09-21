#!/usr/bin/env python3
"""CI の作成と自己ウェイクの仕組みを物理的に拒否する PreToolUse フック。

根拠: .claude/rules/no-ci-no-wakeup.md（2026-09-21 ユーザー指示）。
2026-09-21、1 時間ごとの自己チェックインが Fable の週間上限を月曜に使い切らせた。
規約の文章だけでは同じ判断を繰り返すため、ツール実行の段で止める。

止めるもの:
  1. .github/workflows/ への書き込み（Write / Edit / Bash のリダイレクト・cp・mv・tee）
  2. 自分を起こすツール（send_later / create_trigger / CronCreate / ScheduleWakeup）
  3. PR イベントの購読（subscribe_pr_activity）
削除（git rm / rm）は止めない。CI を消す方向の操作は常に許可する。
"""
import json
import re
import sys

_WAKE_TOOLS = re.compile(
    r"(send_later|create_trigger|update_trigger|fire_trigger|CronCreate|CronList"
    r"|ScheduleWakeup|subscribe_pr_activity|watch_url)$"
)
# 「.github/workflows」を書く側の操作だけを拾う（rm / git rm は対象外）
_WRITE_TO_WORKFLOWS = re.compile(
    r"(?:>{1,2}|cp\s|mv\s|tee\s|install\s|touch\s|mkdir\s[^|;&]*)"
    r"[^|;&\n]*\.github/workflows"
)
_HEREDOC_TO_WORKFLOWS = re.compile(r"cat\s*<<[^\n]*>\s*[^|;&\n]*\.github/workflows")

_REASON = (
    "CI 厳禁・自己ウェイク厳禁（.claude/rules/no-ci-no-wakeup.md・2026-09-21 ユーザー指示）。"
    "CI の作成、定期実行、PR 監視は例外なく禁止。"
    "手元で実行できない検証は『未検証』と明記して納品すること。"
)


def deny(reason: str) -> int:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))
    return 0


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    tool = str(data.get("tool_name") or "")
    tool_input = data.get("tool_input") or {}

    if _WAKE_TOOLS.search(tool):
        return deny(_REASON + " 自分を起こす仕組みは作らない。")

    if tool in ("Write", "Edit", "NotebookEdit"):
        path = str(tool_input.get("file_path") or "")
        if ".github/workflows" in path:
            return deny(_REASON + f" 対象: {path}")
        return 0

    if tool == "Bash":
        cmd = str(tool_input.get("command") or "")
        if ".github/workflows" not in cmd:
            return 0
        if _WRITE_TO_WORKFLOWS.search(cmd) or _HEREDOC_TO_WORKFLOWS.search(cmd):
            return deny(_REASON + " ワークフローファイルの作成・復元は禁止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
