# Langfuse セルフホスト（ローカルサーバ）

Weave相当のトレース・観測・データセット・LLM-as-judge UI を自前運用する。MITライセンス・課金ゼロ。

## 前提
- 任意の常時稼働ローカルサーバにDocker
- Langfuse v3はPostgres + ClickHouse + Redis + MinIOを含む（docker-composeで一括起動）
- 全コンテナのタイムゾーンはUTCで動かす（公式要件）

## セットアップ
```bash
git clone https://github.com/langfuse/langfuse.git
cd langfuse

# .env を作成（秘密鍵を生成）
cat > .env << 'EOF'
NEXTAUTH_SECRET=<openssl rand -base64 32 の出力>
SALT=<openssl rand -base64 32 の出力>
ENCRYPTION_KEY=<openssl rand -hex 32 の出力>
NEXTAUTH_URL=http://localhost:3000
EOF

docker compose up -d
# → http://localhost:3000 でUI。初回にプロジェクト作成しAPIキー取得
```

## VPN経由でモバイル端末からアクセス
- ローカルサーバは必要に応じてVPN経由でアクセス可能にする
- モバイル端末から `http://<local-server-ip>:3000` でトレースUIを外出先から確認できる

## アプリ側の計装（business_agent / multi-agent research system）
```python
from langfuse.decorators import observe
from langfuse.openai import openai  # OpenAI/互換SDKを自動計装

@observe()
def call_llm(prompt: str) -> dict:
    # この関数の入出力・レイテンシ・トークンが自動でトレースされる
    resp = openai.chat.completions.create(...)
    return resp

@observe()
def pmo_decision_pipeline(situation: str):
    # RAG検索 → 判定 → の各ステップがspanとしてツリー表示される
    context = retrieve(situation)   # @observe付き
    return call_llm(build_prompt(situation, context))
```

## eval/データセット連携
- 本番トレースから「良い例/悪い例」をLangfuse UIでデータセットに追加
- そのデータセットをDeepEvalのゴールデンデータとしてエクスポートし回帰evalに使う
- Langfuse側のLLM-as-judge（faithfulness等）を定期バッチで回し、スコア推移をダッシュボードで監視

## 注意（無料運用の落とし穴）
- 長いエージェント実行（多数のツール呼び出し）はobservation数が膨らむ → セルフホストなので課金はないがストレージは消費。古いトレースの保持期間を設定する
- セルフホストHobby構成でもPlayground/Experimentsは使える（クラウド無料枠の制限はセルフホストには無関係）
