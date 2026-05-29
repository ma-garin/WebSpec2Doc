# AGENTS.md — Codex 実装契約書

このファイルは Codex が自動で読み込む契約書です。**全ルールを厳守すること。**
WebSpec2Doc は URL から QA テストインプット文書を自動生成する Python ツールです。

---

## 役割分担

| 担当 | 範囲 |
|------|------|
| **Claude**（設計者） | アーキテクチャ・タスク分解・指示書作成・diff レビュー・**commit** |
| **Codex**（実装者） | 渡された指示書の範囲だけを実装。`scripts/verify.sh` を green にする |

あなた（Codex）は実装者です。指示書に書かれたことだけを行います。

---

## 絶対禁止（違反した時点でタスク失敗）

1. **スタブ/モックの捏造で「動くフリ」をしない。**
   - playwright 等が import できない場合に偽の代替モジュールを作るのは厳禁。
   - 過去にこれで本物のクラッシュが隠蔽された。動かないなら「動かない」と報告する。
2. **`venv/` を編集・削除しない。** 依存問題は報告のみ。勝手に再構築しない。
3. **`.env` / API キー / 秘密情報を読まない・書かない・コミットしない。**
4. **git 操作をしない。** `git add` / `git commit` / `git checkout` / `git reset` 一切禁止。コミットは Claude が行う。
5. **指示書のスコープ外を変更しない。** 「ついでにリファクタ」「ついでに整形」禁止。
6. **テストを通すためにテストを書き換えない。** テストが間違っている場合は報告する（実装を直すのが原則）。
7. **`output/` のクライアント生成物をコミット対象にしない。**

---

## 完了条件（Definition of Done）

タスクは以下を**全て**満たして初めて完了：

1. `scripts/verify.sh` を実行して末尾に `ALL GREEN` が出る。
2. 変更が指示書のスコープ内に収まっている。
3. 最終メッセージに「何を・どのファイルで変更したか」と「verify.sh の結果」を報告する。

verify.sh が落ちたまま「完了」と報告してはいけない。

---

## 実行環境（重要）

- **Python は `venv/bin/python`（3.12）を使う。** システムの python3.13 は greenlet がビルド失敗する。
- テスト実行: `venv/bin/python -m pytest tests/ -q`
- 構文チェック: `venv/bin/python -m py_compile <file>`
- 検証ゲート: `bash scripts/verify.sh`

---

## コード規約

- **イミュータブル必須**: データは `@dataclass(frozen=True)`。変更は `dataclasses.replace()` で新オブジェクトを返す。in-place 変更禁止。
- **型注釈必須**（全関数シグネチャ）。`from __future__ import annotations` を使う。
- **関数 50 行以内 / ファイル 800 行以内。** 超えるなら分割。
- **ネスト 4 段以内。** 早期 return を使う。
- **PEP 8 準拠。** import は標準 → サードパーティ → ローカルの順。
- **`print()` 禁止。** ログは `logging` を使う。
- **エラーは握り潰さない。** 境界で検証し、明確なメッセージで fail-fast。
- **ハードコード禁止。** 定数はモジュール先頭に定義。

---

## アーキテクチャ（変更時の触る場所）

```
src/
├── main.py            CLI エントリ。crawl→analyze→graph→generate→snapshot/compare の流れ
├── crawler/           Playwright クローラー。PageData/FormData/FieldData (全て frozen)
│   ├── page_crawler.py     データクラス定義 + crawl_site()
│   └── link_extractor.py   リンク/フォーム/ボタン抽出 (JS injection)
├── analyzer/          HTML 構造解析。page_id 付与・フォーム集計
├── graph/             networkx.DiGraph で画面遷移グラフ
├── generator/         文書生成 (markdown / mermaid / html_reporter / diff_reporter)
├── diff/              スナップショット保存・比較 (snapshot.py / differ.py)
└── llm/               (未実装) 将来の LLM テスト観点生成
```

| 変更したいもの | 触るレイヤ |
|---------------|-----------|
| クロールで取得する項目を追加 | `crawler/link_extractor.py` の JS + `page_crawler.py` のデータクラス + `diff/snapshot.py` の (de)serialize |
| 差分検知のルール | `diff/differ.py` |
| HTML レポートの見た目 | `generator/html_reporter.py` |
| 新しい出力形式 | `generator/` に追加 + `main.py` の `--format` |

**データクラスにフィールドを足したら、`diff/snapshot.py` の `_*_from_dict` も必ず更新すること**（でないと差分検知でデータが欠落する）。

---

## 既知の落とし穴

- GUI (`app.py`) のポートは **8765**（5000 は macOS AirPlay と衝突）。
- python は必ず **3.12 venv**（3.13 は greenlet ビルド失敗）。
- Mermaid の自己ループエッジは除去する慣習。
- スナップショットは `output/{domain}/snapshots/*.json` にタイムスタンプ名で保存される。

---

## タスクの受け取り方

タスクは指示書（Markdown）で渡される。指示書には「ゴール / 触るファイル / 完了条件 / スコープ外」が書かれている。
不明点があれば実装を始める前に質問する（推測で広範囲を変えない）。
