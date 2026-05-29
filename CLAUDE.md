# WebSpec2Doc — 開発ガイド

URL を渡すと QA テストインプット文書を自動生成する Python ツール。
第三者検証会社が「ドキュメントなし現場」で初日からテスト設計を始めるためのツール。

## プロジェクト構成

```
008_CrateSpec2HTML/
├── docs/               ← ビジネス文書（HTML / ベリサーブデザイン）+ ユーザーガイド
├── src/                ← Pythonアプリケーション
│   ├── main.py         ← CLI エントリポイント
│   ├── crawler/        ← Playwright クローラー（page_crawler / link_extractor）
│   ├── analyzer/       ← HTML 構造解析（html_analyzer / form_analyzer）
│   ├── graph/          ← 画面遷移グラフ（networkx.DiGraph）
│   ├── generator/      ← 文書生成（markdown / mermaid / html_reporter / diff_reporter）
│   ├── diff/           ← 仕様ドリフト検知（snapshot 保存・差分比較）
│   └── llm/            ← LLM テスト観点生成（未実装：__init__ のみ）
├── app.py              ← ブラウザ GUI（Flask / ポート 8765）
├── scripts/            ← Codex 協働 harness（verify.sh / codex-task.sh / task-template.md）
├── AGENTS.md           ← Codex 実装契約書（Codex が自動読込）
├── tests/              ← テストスイート（pytest 144件）
└── output/             ← 生成された QA 文書（Git 除外）
```

## セットアップ

```bash
# Python は 3.12 を使う（3.13 は greenlet がビルド失敗するため不可）
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## 使い方

```bash
# 基本
python src/main.py --url https://example.com

# 仕様ドリフト検知（前回スナップショットと差分比較）
python src/main.py --url https://example.com --compare

# オプション全指定
python src/main.py \
  --url https://example.com \
  --depth 3 \
  --max-pages 50 \
  --output ./output \
  --format html,md,excel \
  --compare
```

`--llm` フラグは受け付けるが未実装（警告を出して無視）。

## 出力ファイル

| ファイル | 内容 |
|---------|------|
| `output/{domain}/screens.md` | 画面一覧表（Markdown） |
| `output/{domain}/forms.md` | フォーム・入力項目一覧（Markdown） |
| `output/{domain}/transition.mmd` | 画面遷移図（Mermaid） |
| `output/{domain}/report.html` | HTML レポート（提出物向け） |
| `output/{domain}/spec.xlsx` | Excel 仕様書（テスト管理ツール転記用） |
| `output/{domain}/screenshots/` | 各画面スクリーンショット |
| `output/{domain}/snapshots/*.json` | クロール結果スナップショット（差分検知用） |
| `output/{domain}/diff_report.html` | 仕様ドリフト差分レポート（`--compare` 時） |

## 開発ルール

- 言語：Python 3.12（3.13 は greenlet ビルド失敗のため不可）
- クローラー：Playwright（同期 API）
- グラフ：networkx.DiGraph
- テスト：pytest（現在 144件）/ カバレッジ 80% 以上
- イミュータブル：データ変換は新しいオブジェクトを返す（in-place 変更禁止）。データクラスは `@dataclass(frozen=True)`
- ファイルサイズ：800行以内
- 関数サイズ：50行以内
- データクラスにフィールドを追加したら `src/diff/snapshot.py` の (de)serialize も必ず更新

## Codex 協働 harness

Codex に実装を委任する場合の決定的なループ：

1. `scripts/task-template.md` を雛形にタスク指示書を作る
2. `./scripts/codex-task.sh <task.md>` で委任 → `codex exec`(workspace-write)→ 自動で `verify.sh`
3. green でも Claude が `git diff` をレビューしてから **commit する（コミットは必ず Claude）**

- `AGENTS.md`：Codex が自動読込する契約書（禁止事項・完了条件・規約）
- `scripts/verify.sh`：検証ゲート（py_compile→pytest→実クロール2回→成果物チェック）。commit 前に必ず実行
- コミット前は `bash scripts/verify.sh` が `ALL GREEN` であることを確認

## セキュリティ

- `.env` は絶対に Git にコミットしない
- `output/` は Git 除外（クライアント情報が含まれる可能性）
- API キーはハードコード禁止
