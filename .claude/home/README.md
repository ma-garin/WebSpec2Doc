# ホーム側（`~/.claude/`）の正本

全セッション・全リポジトリに適用される設定の複製。実行環境は使い捨てのため、
ここを正本として保存し、新しい環境では次で反映する。

```bash
mkdir -p ~/.claude/hooks
cp .claude/home/CLAUDE.md    ~/.claude/CLAUDE.md
cp .claude/home/settings.json ~/.claude/settings.json
cp .claude/hooks/block-ci.py  ~/.claude/hooks/block-ci.py
```

`settings.json` の `command` はホーム側では `$HOME/.claude/hooks/block-ci.py` を指す。
内容の根拠は `docs/process/token-economics.md` と `.claude/rules/no-ci-no-wakeup.md`。
