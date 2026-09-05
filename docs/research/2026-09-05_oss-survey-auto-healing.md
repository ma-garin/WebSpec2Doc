# オートヒーリング — 類似 OSS 調査（2026-09-05）

調査方法: GitHub REST API（`/repos/{owner}/{repo}`、`/search/repositories`）を直接 curl で叩き、
Star数・最終 push 日時（`pushed_at`）・license・archived フラグを一次取得。各 README を
`raw.githubusercontent.com` から取得し grep で該当箇所を確認。すべて 2026-09-05 時点のスナップショット。

## 結論（3行以内）

並列オーケストレーション層は **Nimbalyst**（git worktree 分離＋赤緑diff承認＋Claude Code/Codex 差し替え可能、MIT・現役）を設計の型として最も参考にすべき。
修正エンジン層は **mini-swe-agent**（Docker任意・ローカル実行が一級市民、100行で改造しやすい）と **Aider**（コンテナ無しでローカル git を直接編集、OpenAI/Ollama含む任意LLM対応）の二択が Docker 禁止制約に直接適合する。
PR承認ゲートの参考は Dependabot/Renovate（「botがPRを出し人がマージ」型）。この分野は競合乱立の末に **Vibe Kanban・Crystal が2026年に相次いで sunset/deprecated** しており、OSS単体保守の継続性リスクとして明記が必要。

## 一覧（15件）

| # | OSS | カテゴリ | Star | 最終コミット(pushed_at) | ライセンス | 言語 | 何をするか |
|---|---|---|---|---|---|---|---|
| 1 | [SWE-agent/SWE-agent](https://github.com/SWE-agent/SWE-agent) | (a) 自動修正 | 20,222 | 2026-08-31 | MIT | Python | GitHub issueをLMに自動修正させるACIエージェント。**README冒頭で後継の mini-swe-agent への移行を公式推奨**（開発リソースをそちらに集中） |
| 2 | [SWE-agent/mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) | (a) 自動修正 | 6,959 | 2026-09-03 | MIT | Python | SWE-agentの後継。エージェント本体100行。ローカル環境／Docker／Podman／Singularity／bubblewrapを対等にサポートし`subprocess.run`を`docker exec`に差し替えるだけで分離実行に切替可能 |
| 3 | [SWE-agent/SWE-ReX](https://github.com/SWE-agent/SWE-ReX) | (d) サンドボックス実行基盤 | 583 | 2026-08-31 | MIT | Python | mini-swe-agent系のサンドボックス実行レイヤー。ローカル/クラウドで大量並列実行可能と自称 |
| 4 | [Aider-AI/aider](https://github.com/Aider-AI/aider) | (a) 自動修正 | 48,749 | 2026-05-22 | Apache-2.0 | Python | ターミナル常駐のAIペアプログラマ。ローカルgitを直接編集し**自動コミット**（undo容易）。Claude/OpenAI/Ollama等ほぼ任意のLLMに接続可 |
| 5 | [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands)（旧OpenDevin） | (a) 自動修正 | 86,199 | 2026-09-04 | MIT | TypeScript | フルスタックのAI開発エージェント基盤。最もStar数が多く、更新頻度も最高水準 |
| 6 | [nus-apr/auto-code-rover](https://github.com/nus-apr/auto-code-rover) | (a) 自動修正 | 3,100 | 2025-04-24 | NOASSERTION | Python | プロジェクト構造認識型の自律修正エージェント（SWE-bench系研究成果）。**1年以上更新停止気味** |
| 7 | [OpenAutoCoder/Agentless](https://github.com/OpenAutoCoder/Agentless) | (a) 自動修正 | 2,110 | 2024-12-22| MIT | Python | 「エージェントを使わない」定型パイプライン方式のバグ修正。**約1年10ヶ月更新なし**、研究成果物として凍結気味 |
| 8 | [aorwall/moatless-tools](https://github.com/aorwall/moatless-tools) | (a) 自動修正 | 643 | 2025-09-01 | MIT | Python | コードベース探索とパッチ生成をツール分離した自動修正フレームワーク。Star少・約1年更新なし |
| 9 | [sweepai/sweep](https://github.com/sweepai/sweep) | (a) 自動修正 | 7,708 | 2025-09-18 | NOASSERTION | Jupyter Notebook | 元はGitHub Appとして issue→PR を自動生成する構想だったが、現在の説明文は「JetBrends向けAIコーディング補助」に変化しており**プロダクトの方向転換／実質停滞**が疑われる |
| 10 | [gpt-engineer-org/gpt-engineer](https://github.com/gpt-engineer-org/gpt-engineer) | (a) 自動修正 | 55,109 | 2025-05-14 | MIT | Python | 自然言語からのコード生成CLI。**`archived: true`（アーカイブ済み）**。後継はSaaSのlovable.dev |
| 11 | [stitionai/devika](https://github.com/stitionai/devika) | (a) 自動修正 | 19,558 | 2025-09-25 | MIT | Python | Devin類似のOSS自律エージェント。Star数は大きいが**約1年更新停止** |
| 12 | [dependabot/dependabot-core](https://github.com/dependabot/dependabot-core) | (b) CI駆動ボット | 5,755 | 2026-09-05（当日） | MIT | Ruby | 依存関係更新PRを自動生成するコアロジック。GitHub組み込み、人がPRをレビュー/マージ |
| 13 | [renovatebot/renovate](https://github.com/renovatebot/renovate) | (b) CI駆動ボット | 22,414 | 2026-09-05（当日） | AGPL-3.0 | TypeScript | Dependabot類似の依存更新PR自動化。設定の柔軟性が高く自己ホスト可能 |
| 14 | [eclipse-repairnator/repairnator](https://github.com/eclipse-repairnator/repairnator) | (b)/(a) CI駆動の自動バグ修復 | 391 | 2026-08-14 | MIT | — | CIのビルド失敗を検知し自動修正パッチを試みSubmit botとしてPRを出す学術発の先駆的プロジェクト。**現在もpush継続中（活性）** |
| 15 | [healenium/healenium](https://github.com/healenium/healenium) | (c) テスト自己修復 | 167 | 2026-03-31 | Apache-2.0 | Shell | Selenium系UIテストのロケータ自己修復ライブラリ。テスト実行環境をラップし壊れたロケータをMLベースで自動修復（README詳細は本調査では未確認） |
| 16 | [BloopAI/vibe-kanban](https://github.com/BloopAI/vibe-kanban) | (d) 並列オーケストレーション | 28,013 | 2026-04-24 | Apache-2.0 | Rust | Claude Code/Codex等10以上のコーディングエージェントをworktree分離で並列実行するKanban UI。**README冒頭に "Vibe Kanban is sunsetting" と明記（サービス終了告知済み）** |
| 17 | [stravu/crystal](https://github.com/stravu/crystal) | (d) 並列オーケストレーション | 3,115 | 2026-02-26 | MIT | TypeScript | 複数のClaude Code/Codexセッションをgit worktreeで並列管理。**2026年2月付で非推奨化・後継Nimbalystへ移行済み**（README全体が移行案内に置き換わっている） |
| 18 | [nimbalyst/nimbalyst](https://github.com/nimbalyst/nimbalyst) | (d) 並列オーケストレーション | 1,649 | 2026-09-03 | MIT | — | Crystalの後継。Claude Code/Codex/OpenCode/Copilotをworktree分離で並列実行し、赤緑diffで人間が承認するデスクトップUI。**現役で活発に更新中** |

## 最も参考になる 3 件の分析

### 1. Nimbalyst（https://github.com/nimbalyst/nimbalyst）
- 解決している課題: 複数のコーディングエージェント（Claude Code / Codex / OpenCode / Copilot）を人が並行監督するためのビジュアルワークスペース。セッション＝1worktreeで完全分離し、Kanbanボードで進捗管理、diffは赤緑表示で1件ずつ承認/却下できる。
- 対象ユーザー: ローカルPCでコーディングエージェントを複数走らせたい開発者個人〜小チーム（macOS/Windows/Linuxデスクトップアプリ＋iOS companion）。
- 技術構成: プレーンファイル主義（コンテンツはmarkdown、ワークフローはslash commands、すべてgitリポジトリ内に保存し「囲い込みストアなし」を明言）。MCPクライアント/サーバー対応。エディタは共通の`EditorHost`契約で拡張可能（Extension SDK）。
- 安全性の扱い（サンドボックス・権限・破壊防止・人の承認）: **コンテナではなくgit worktreeによる分離**。エージェントの提案は red/green diff で提示され、人間が1件ずつ承認するまで確定しない。gitがそのままログ／取り消し手段になる。Docker前提の記述はREADMEになし（=Docker不要で動く設計）。
- 更新状況（最終コミット・コミット頻度・メンテ体制）: 2026-09-03 push（実質当日近辺）、Star 1,649。前身Crystal（2026年2月非推奨化）からの正統後継として明確な移行文書あり。ただし本調査は`pushed_at`の1点観測であり、コミット頻度の時系列は**未確認**。
- **再利用すべき設計**: (1) 「セッション=1 git worktree」で並列実行単位を切る境界の取り方。(2) diffの逐次承認UI（全体一括ではなく1件ずつ人が判断）。(3) エージェント種別を`EditorHost`相当の共通契約で差し替え可能にする「切り出し・差し替え」構造そのもの。(4) 生成物をプレーンファイル/gitに留め、専用DBに囲い込まない方針。
- **避けるべき点**: デスクトップアプリ＋モバイルcompanionという構成はWebSpec2Doc（Flask Web UI・PCのみ）の前提とは形態が異なるため、UI実装をそのまま持ち込むのではなく「worktree分離＋逐次承認」という設計思想だけを移植すべき。またVibe Kanban・Crystalが短期間で相次ぎsunsetした領域であり、**この種のOSS単体は事業継続リスクが高い**（自作前提の参考実装として扱い、外部依存にしない）。
- 本件（Docker 禁止・ローカル PC・Flask）との適合性: 高い。Docker不要、PC単体、worktree分離という制約に技術的に一致。ただしNimbalyst自体はデスクトップアプリでありFlask Webアプリへの組み込みは不可なので、**設計パターンの輸入元**として位置づける。

### 2. mini-swe-agent（https://github.com/SWE-agent/mini-swe-agent）
- 解決している課題: GitHub issue（＝検証で見つかった不具合）をLLMエージェントに自動修正させる中核ループそのもの。前身SWE-agentが複雑化しすぎた反省から「100行のエージェント本体」に絞り込んだ設計。
- 対象ユーザー: 研究者・自動修正パイプラインを自前で組み込みたい開発者。
- 技術構成: エージェント本体は`subprocess.run`で全アクションを完全ステートレスに実行（シェルセッションを保持しない設計を明示的に選択）。実行環境（Environment）はローカル／docker・podman／singularity・apptainer／bubblewrap／“contree”などを**対等な差し替え可能バックエンド**として提供し、`LocalEnvironment()`のようにローカル実行がファーストクラス。LM非依存（litellm相当の抽象化で任意モデル接続）。
- 安全性の扱い: 実行環境の選択によりサンドボックス強度を調整できる設計（=Docker必須ではなく、ローカル直実行も一級市民）。人間承認フローは本体に組み込まれておらず、**PR作成・承認ゲートは利用側で別途実装が必要**（本体はissue→パッチ生成のコアループのみを担う）。
- 更新状況: 2026-09-03 push（当日近辺）、Star 6,959。SWE-agent本体（Star 20,222、2026-08-31 push）の開発チームが**公式に「今後はmini-swe-agentを使うことを推奨」**とREADME冒頭で明言しており、事実上の後継・本流。
- **再利用すべき設計**: (1) 「全アクションを`subprocess.run`で独立実行し、ステートフルなシェルセッションを持たない」設計により、ローカル実行とサンドボックス実行の切替が"関数を差し替えるだけ"で済む点（既存`web/services/healing/`のagents層に応用可能）。(2) Environment抽象を薄く保つことで、Docker禁止環境でもロジックを変えずローカル実行に固定できる。
- **避けるべき点**: 本体はベンチマーク（SWE-bench）向けの「1タスク1回実行」の思想が強く、人間承認・再実行ループ・PR発行は含まれない。そのまま使うと今回要件の「検証→欠陥→修正→PR→人の判断→再テスト」ループの後半は自作が必要（＝コアの修正エンジン部分としてのみ有用）。
- 本件との適合性: 高い。Docker前提でない設計思想、シンプルな行数、任意LLM対応（OpenAI/ローカルLLM含む）が要件に直結する。既存 `web/services/healing/agents` の実行モデル（stateless action実行）を見直す際の一次参考にできる。

### 3. Aider（https://github.com/Aider-AI/aider）
- 解決している課題: ターミナル上でLLMと対話しながらローカルのgitリポジトリを直接編集・自動コミットする「ペアプログラミング」ツール。オートヒーリングの「該当コードを特定して修正」ステップを、既存の枯れたCLIとして代替できる。
- 対象ユーザー: 個人開発者〜チームでのインタラクティブなAIコーディング利用者。非対話（スクリプトからの呼び出し）にも対応（`--yes`系フラグで自動承認運用が可能、README確認済み文言: "Aider automatically commits changes with sensible commit messages. Use familiar git tools to easily diff, manage and undo AI changes."）。
- 技術構成: Pythonパッケージ。Claude/OpenAI/DeepSeek/Geminiに加え「ほぼ任意のLLM、ローカルモデル含む」と明記（README該当行）。リポジトリのtopicsに`ollama`は無いが「local models」表記でOllama等ローカルLLM運用にも開いている。コンテナ実行を前提とした記述はREADMEになし＝**素のローカル実行が標準**。
- 安全性の扱い: **自動コミットがデフォルト**（＝直接ワーキングツリー/gitを変更する。破壊防止は「git履歴によるundo容易性」に依存し、実行前に人間が承認するゲートは標準搭載されていない）。sandboxやコンテナ隔離の概念はなし。
- 更新状況: Star 48,749、`pushed_at`は2026-05-22で**調査時点（2026-09-05）から約3.5ヶ月前**。他候補（OpenHands 2026-09-04、mini-swe-agent 2026-09-03、Renovate/Dependabot当日）と比べ相対的に更新間隔が空いている。archivedフラグはfalse（凍結ではない）。ただし本調査は最終push日時のみの確認であり、コミット頻度の傾向やメンテ体制の実態は**未確認**。
- **再利用すべき設計**: (1) 「LLMバックエンドを差し替え可能にする」設計（OpenAI/Ollama/Claude Code CLI相当を後段で挿げ替え可能にする今回の要件と直接一致）。(2) 変更は必ずgitコミット単位で残し、人間が`git diff`/`git log`でいつでも遡れるようにする破壊防止の考え方。
- **避けるべき点**: **自動コミットをデフォルトにする設計はそのまま踏襲しない**。今回の要件は「PR作成→人間が承認/却下/マージするまでシステム画面上で完結」であり、Aiderの「エージェントが直接ローカルにコミットする」流儀は人間承認ゲートより前に変更を確定させてしまう。修正エンジンとして呼び出す場合も、コミット先はメインの作業ツリーではなく隔離したworktree/ブランチに限定し、PR化前の自動コミットが本流のgit履歴を汚さないようにする必要がある。
- 本件との適合性: 中〜高。Docker不要・ローカルgit直接編集・多様なLLM対応という点は適合するが、既定の「即コミット」挙動は今回のゲート必須要件と衝突するため、呼び出し方（隔離ブランチでの実行、承認前は非表示）を設計側で補う前提での採用となる。

## 本件に効く設計の抽出

- **並列化と切り出しの境界の置き方**: Nimbalyst/mini-swe-agentとも「1タスク=1 git worktree（または1 Environment）」を最小分離単位にしている。既存`web/services/healing/`のagents層も、修正1件=1 worktree=1エージェントプロセスという境界に合わせるのが最も既存OSSの実績に沿う。
- **人間の判断ゲートの置き方**: Nimbalystは「diffを1件ずつ赤緑表示→承認/却下」、Dependabot/Renovateは「PRを人がGitHub上でレビューしマージ」という2段階の型がある。今回要件は後者（PR単位での承認）が本流だが、Nimbalystの「diff粒度での逐次承認」をPR説明文の中に折り込む（変更点ごとの説明を付す）UXは流用価値が高い。
- **検証と「直ったか」の判定方法**: 本調査で確認した範囲では、SWE-agent/mini-swe-agent・Agentless・auto-code-roverはいずれも「テストスイートの再実行結果（pass/fail）」で修正成否を判定する設計（SWE-bench系ベンチマーク文化に由来）。Repairnatorも同様にCIのビルド/テスト失敗検知起点。**「テストが通るまで再試行」をヒーリングループの成否判定の一次基準にする**設計は複数の独立系統で共通しており、既存実装(`web/services/healing/verification`)の方向性を裏付ける。
- **破壊防止（利用者の作業ツリーを壊さない方法）**: 共通して「メインの作業ツリーを直接触らずworktree/ブランチを切って隔離し、PRを経由してのみ本流に反映する」設計（Nimbalyst、mini-swe-agentのEnvironment分離、Dependabot/Renovateのブランチ+PR運用）。Aiderのような「直接コミット」型は個人の対話利用では合理的だが、自動化・並列実行の文脈では今回採用しない方が安全という比較結果になった。

## 引用してはいけない数値

- 各READMEに記載のSWE-bench等ベンチマークスコア（例: 「mini-SWE-Agentが65%達成」等のブログ/X投稿引用）は一次ベンチマークレポートを本調査では未確認のため引用不可。
- Vibe Kanban / Crystal の "Get 10X more out of Claude Code" 等のマーケティング文言は自称値であり未検証。
- Healenium のロケータ自己修復のML精度・アルゴリズム詳細は本調査でREADME本文まで未確認（トップメタデータのみ取得）。
- Aider・vibe-kanban等の「Star数」「pushed_at」は2026-09-05時点の1回のAPIスナップショットであり、コミット頻度・コントリビューター数・Issue対応速度など「メンテ体制」の実態は未確認。

## 見つからなかったもの（どう検索したか）

- **RepairAgent**（学術プロジェクト）の実運用・保守された公式リポジトリ: GitHub検索`RepairAgent in:name`で確認できたのは `sola-st/RepairAgent`（Star 105、pushed 2026-05-31）のみで、他はハンドル名衝突の無関係リポジトリ。継続的なメンテ体制（Issue対応・リリース頻度）は確認できず、参考程度の位置づけに留めた。
- **Repairnator の現行フォーク以外の後継プロダクト**: `repairnator`検索で見つかったのは`eclipse-repairnator/repairnator`本体のみで、商用・コミュニティ後継は確認できなかった（本体自体は2026-08-14 pushで活性を維持）。
- **Moatless Tools の後継/フォーク**: 検索範囲内（GitHub検索・API直参照）では有力な後継プロジェクトは見つからず、本体が2025-09時点で更新停止気味という結果のみ。
- **Healenium 以外のテスト自己修復OSS**: 探索を1件（Healenium）に絞ったため、類似ツール（例: 他言語/他フレームワークの自己修復テストライブラリ）の横比較は未実施（ツール実行回数上限内での優先度判断として割愛）。
