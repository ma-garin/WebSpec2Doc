# WS2D-BF-001 業務フロー図

- 文書ID: WS2D-BF-001
- 版数: 1.0 / 作成日: 2026-08-02 / 準拠: IPA共通フレーム（業務フロー）
- 用語は `CONTEXT.md`、`WS2D-GL-001_用語集.md` を参照。

各フローは役割（利用者／システム／外部サイト／LLM）をスイムレーン相当で区別し、例外・エラー時の分岐を明記する。

## フロー1: 初期セットアップ（アカウント作成→テナント作成→ログイン）

```mermaid
sequenceDiagram
    actor U as 利用者
    participant S as システム（WebSpec2Doc）

    U->>S: /auth/setup にアクセス（初回）
    alt 利用者が1人も存在しない
        S-->>U: セットアップ画面を表示
        U->>S: ワークスペース名・オーナー情報を送信
        S->>S: ワークスペース作成 + オーナーアカウント作成
        S-->>U: 作成完了、/auth/login へ誘導
    else 既に利用者が存在する
        S-->>U: /auth/login へリダイレクト（403相当）
    end

    U->>S: /auth/login にメール・パスワードを送信
    alt 認証成功
        S->>S: セッション発行（ws2d_session、既定12時間）
        S-->>U: /systems（システム選択）へ遷移
    else 認証失敗
        S-->>U: エラー表示
        Note over S: 5回連続失敗で15分ロックアウト
    end
```

**例外・エラー分岐**

- 認証失敗の連続（ロックアウト）: 正しいパスワードでも15分間拒否。
- パスワード要件不備（10文字未満・メールと同一）: セットアップ時点で拒否。
- 2人目以降の利用者は `/auth/setup` に到達不可（管理者による招待が必要、`tenant_membership`）。

## フロー2: ドキュメント作成業務（対象サイト登録→クロール→解析→ドキュメント生成→レビュー→出力）

```mermaid
flowchart TD
    subgraph user_role["利用者"]
        A1[対象URLを入力]
        A5[生成結果をレビュー]
        A6[出力形式を選びエクスポート]
    end
    subgraph system_role["システム"]
        B1[ページ解析 discover]
        B2{ログイン必要?}
        B3[自動ログイン実行]
        B4[クロール実行 crawl]
        B5[画面仕様書/遷移図/テスト条件を生成]
    end
    subgraph site_role["対象Webサイト"]
        C1[(画面・フォーム)]
    end

    A1 --> B1
    B1 --> C1
    C1 --> B1
    B1 --> B2
    B2 -- Yes --> B3
    B3 --> C1
    B2 -- No --> B4
    B3 --> B4
    B4 --> C1
    C1 --> B4
    B4 --> B5
    B5 --> A5
    A5 --> A6

    B1 -. "失敗: invalid_url/timeout" .-> E1[エラー表示・中止]
    B3 -. "失敗: invalid_credentials/mfa_required" .-> E2[未ログイン範囲のみで継続 or 中止]
    B4 -. "失敗: robots_disallowed" .-> E3[該当ページをスキップしaudit.jsonlへ記録]
    B4 -. "失敗: timeout/cancel" .-> E4[チェックポイントから部分結果を保全]
```

**例外・エラー分岐**

- 対象サイト到達不可（`invalid_url`, `timeout`）: 解析段階で中止しエラー表示。
- ログイン失敗（`invalid_credentials`, `mfa_required`, `session_expired`）: 未ログイン範囲のみの結果として記録するか、`--require-login` 相当の設定時は中止。
- robots.txt 拒否（`robots_disallowed`）: 該当ページのみスキップし監査ログ（`audit.jsonl`）に理由を記録。
- タイムアウト・中止（`timeout`, `cancel`）: チェックポイントから再開可能な形で部分結果を保全。

## フロー3: AutoRunによるテスト設計・実行業務（目的設定→計画→観点→設計→ケース生成→実行→レポート）

```mermaid
flowchart TD
    subgraph user_role["利用者"]
        U1[目的・実行方針を設定]
        U2[各段階を承認]
        U3[実行結果レポートを確認]
    end
    subgraph system_role["システム"]
        S1[計画を生成]
        S2["FE（機能一覧）を生成"]
        S3[観点を生成]
        S4[設計/詳細設計を生成]
        S5["テストケース生成（QFカラム）"]
        S6[Playwright spec を生成]
        S7[テスト実行]
        S8[結果レポート作成]
    end
    subgraph llm_role["LLM（OpenAI、任意）"]
        L1[提案の補完]
    end
    subgraph site_role["外部サイト"]
        E0[(対象画面)]
    end

    U1 --> S1
    S1 --> S2
    S2 --> S3
    S3 --> S4
    S4 --> S5
    S5 --> S6
    S6 --> S7
    S7 --> S8
    S8 --> U3
    S1 -. "LLM設定時のみ" .-> L1
    L1 -. 提案 .-> S2
    U2 -. 各段階を承認 .-> S1
    U2 -. 各段階を承認 .-> S3
    U2 -. 各段階を承認 .-> S5
    S7 <--> E0

    S1 -. LLM未設定 .-> N1[ルールベースでフォールバック生成]
    N1 --> S2
    U2 -. "承認タイムアウト" .-> X1["approval_timeout: 保留のまま待機"]
    S7 -. "失敗: login_wait_timeout" .-> X2[ログイン待ち中止]
    S7 -. "失敗: execution_timeout" .-> X3[部分結果を保存して打ち切り]
```

**例外・エラー分岐**

- LLM未設定: ルールベースでフォールバック生成し、機能を損なわず継続する。
- 承認タイムアウト（`approval_timeout`）: 段階は保留のまま次に進まず、利用者の操作を待つ。
- ログイン待ちタイムアウト（`login_wait_timeout`）: 実行を中止。
- 実行タイムアウト（`execution_timeout_partial_result`）: 部分結果を保存して打ち切り、全件成功したかのように扱わない。
- 中止（`cancel`）: 実行中のジョブを安全に停止。

## フロー4: 定期監視・ドリフト検知業務（スケジュール登録→定期実行→差分検知→通知）

```mermaid
sequenceDiagram
    actor U as 利用者
    participant Sch as スケジューラ
    participant Sys as システム
    participant Site as 外部サイト
    participant N as 通知先（Slack）

    U->>Sys: /schedule/config でスケジュール登録（間隔・通知設定）
    loop 設定間隔ごと
        Sch->>Sys: 定期クロールを起動
        Sys->>Site: クロール実行（robots.txt尊重）
        alt 到達可能
            Site-->>Sys: ページ取得
            Sys->>Sys: スナップショット保存 + 前回との差分計算
            alt 初回実行
                Sys->>Sys: ベースラインとして保存（比較なし）
            else 差分あり
                Sys->>Sys: 重要度判定・誤検知フィルタ適用
                Sys->>N: 通知送信（SLACK_WEBHOOK_URL設定時）
                N-->>U: Slack通知を確認
            else 差分なし
                Sys->>Sys: no_change として記録
            end
        else 到達不可/セッション失効
            Sys->>Sys: エラー記録（exit code 2）、次回まで待機
        end
    end
```

**例外・エラー分岐**

- 対象サイト到達不可・セッション失効（`session_expired`, `missing_target`）: エラーとして記録し、判定結果は変えずに次回実行まで待機。
- Webhook未設定・通知送信エラー（`missing_webhook`, `notify_http_error`）: 通知は送られないが、ドリフト判定結果自体は変わらない。
- 初回実行（`first_run`）: 比較対象がないためベースラインとして保存するのみ。
- CI組み込み時: 差分ありは exit code 1 でジョブ失敗として扱う。

## 改訂履歴

| 版 | 日付 | 内容 | 作成者 |
|---|---|---|---|
| 1.0 | 2026-08-02 | 新規作成 | 開発チーム |
