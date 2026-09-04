"""オートヒーリング（System 05）。

検証を回して不具合を見つけ、コードを直し、PR を出して人の判断を待つまでを 1 系統で扱う。

構成:
    types.py          共通の型契約（ここだけは副作用を持たない）
    project_store.py  対象コードベースの登録・接続確認
    run_store.py      実行結果の永続化
    git_ops.py        worktree による分離と git 操作
    github_client.py  PR の作成・取得・マージ
    verification.py   検証コマンドの実行と失敗の構造化
    agents.py         修正エージェントの差し替え層（並列・切り出しの境界）
    orchestrator.py   ループエンジン（検証 → 欠陥 → 修正 → 再検証 → PR）

このパッケージは「直したかどうか」を自分で判定しない。判定は必ず
利用者が設定した検証コマンドの結果に委ねる（エージェントの自己申告を信用しない）。
"""

from __future__ import annotations
