# 別環境へ貼る指示文（差分 / 履歴 / 再クロール）

以下をそのままコピーして、受け側の Claude Code / Codex に貼る。

---

WebSpec2Doc から機能アセット `diff_history` を受け取った。このリポジトリへ組み込んでほしい。

アセットの場所: `assets/diff_history/20260829-a84288c/`
（GitHub の zip を展開したディレクトリの中にある）

手順:

1. そのディレクトリの `INTEGRATION.md` を読む。組み込み手順はそこに全部書いてある。
2. 配置の前に完全性を検証する:
   ```
   python3 scripts/verify_feature_asset.py assets/diff_history/20260829-a84288c --against .
   ```
   `[NG]` が出たら配置せず、何が足りないかを報告すること。
3. 合格したら `files/` をリポジトリのルートへ配置する（相対パスはそのまま）:
   ```
   rsync -a assets/diff_history/20260829-a84288c/files/ ./
   ```
4. `INTEGRATION.md` 第 2 節に従って配線する（Blueprint 登録・`templates/index.html` への include / script / link）。
5. `INTEGRATION.md` 第 5 節の受け入れ確認を実行する。出力・永続化・失敗経路を実際に踏むこと。**送り側では未実行**。

注意:

- 同梱外の内部モジュールが 12 件ある（手順 2 の検証で受け側に無ければ `[NG]` として出る）
- 判断に迷ったら勝手に決めず、送り側（WebSpec2Doc 側）へ確認すること。
