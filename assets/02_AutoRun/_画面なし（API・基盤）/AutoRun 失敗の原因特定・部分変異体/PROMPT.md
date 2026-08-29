# 別環境へ貼る指示文（AutoRun 失敗の原因特定・部分変異体）

以下をそのままコピーして、受け側の Claude Code / Codex に貼る。

---

この機能「AutoRun 失敗の原因特定・部分変異体」を、このリポジトリへ取り込んでほしい。
WebSpec2Doc からの機能アセットで、必要なファイルと手順は同じフォルダに揃っている。

このフォルダ（`PROMPT.md` が置かれているディレクトリ）がアセット本体。
システム: 02_AutoRun / 画面: _画面なし（API・基盤） / feature_id: `autorun_failure_triage` / 版: `20260829-81e4c84`

手順:

1. そのディレクトリの `INTEGRATION.md` を読む。組み込み手順はそこに全部書いてある。
2. 配置の前に完全性を検証する:
   ```
   python3 scripts/verify_feature_asset.py <このフォルダのパス> --against .
   ```
   `[NG]` が出たら配置せず、何が足りないかを報告すること。
3. 合格したら `files/` をリポジトリのルートへ配置する（相対パスはそのまま）:
   ```
   rsync -a <このフォルダのパス>/files/ ./
   ```
4. `INTEGRATION.md` 第 2 節に従って配線する（Blueprint 登録・`templates/index.html` への include / script / link）。
5. `INTEGRATION.md` 第 5 節の受け入れ確認を実行する。出力・永続化・失敗経路を実際に踏むこと。**送り側では未実行**。

注意:

- 同梱外の内部モジュールが 18 件ある（手順 2 の検証で受け側に無ければ `[NG]` として出る）
- 判断に迷ったら勝手に決めず、送り側（WebSpec2Doc 側）へ確認すること。
