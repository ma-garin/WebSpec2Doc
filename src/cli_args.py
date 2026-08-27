"""CLI 引数定義（argparse）。

src/main.py から分離した。ここには**引数の宣言だけ**を置き、実行時の分岐や
処理は main 側に残す。1500 行超の main.py で最も大きく、かつ他と結合していない
かたまりだったため最初に切り出した。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from crawler.page_crawler import DEFAULT_DEPTH, DEFAULT_MAX_PAGES

DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_FORMATS = "md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WebSpec2Doc web crawler")
    parser.add_argument("--url", help="クロール対象URL")
    parser.add_argument(
        "--urls",
        help="リンク追跡せず指定URLのみクロール（カンマ区切り）。--url の代わりに使用",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="リンク追跡で到達するページ一覧(URL+タイトル)をJSONでstdoutに出力して終了",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="--discover と組み合わせ、発見ページを NDJSON でリアルタイム出力する（GUI用）",
    )
    parser.add_argument("--login", help="ログインセッション保存モード: ログインページURL（CLI用）")
    parser.add_argument(
        "--login-signal",
        type=Path,
        help="GUI 手渡しログイン用: このファイルが出現したらセッションを保存する（廃止予定）",
    )
    parser.add_argument(
        "--login-simple", action="store_true", help="ID/PASSWORDをstdinのJSONで受取り自動ログイン"
    )
    parser.add_argument("--login-simple-url", help="--login-simple: ログインページURL")
    parser.add_argument(
        "--login-scrape", help="ログインURLのフォームフィールドを取得してJSONで出力"
    )
    parser.add_argument(
        "--login-submit",
        action="store_true",
        help="ログインフォーム自動送信（フィールド値はstdinからJSON受取）",
    )
    parser.add_argument("--login-current-url", help="--login-submit: フォーム送信先URL（MFA対応）")
    parser.add_argument("--login-temp-session", type=Path, help="MFA中間セッション保存パス")
    parser.add_argument(
        "--login-record",
        action="store_true",
        help=(
            "認証フローレコーダー起動: 見えるブラウザでログインし、"
            "シグナルファイル出現時にセッションを保存する（--login と --login-signal の統合入口）"
        ),
    )
    parser.add_argument("--login-record-url", help="--login-record: ログインページURL")
    parser.add_argument(
        "--login-status",
        type=Path,
        help="--login-record: 進行状態(JSON)の出力先。Web UI が1秒間隔でポーリングする",
    )
    parser.add_argument("--auth", type=Path, help="保存済みセッション(auth.json)を使ってクロール")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help="クロール深度")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help="最大クロールページ数",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="出力先")
    parser.add_argument("--llm", action="store_true", help="LLM解析を有効化")
    parser.add_argument(
        "--format", default=DEFAULT_FORMATS, help="出力形式: md,html,excel,pdf,json"
    )
    parser.add_argument("--compare", action="store_true", help="前回スナップショットとの差分を出力")
    parser.add_argument(
        "--viewports",
        help=(
            "マルチビューポート観測（カンマ区切り: desktop,tablet,mobile）。"
            "指定すると各画面幅でクロールし、ビューポート間差分を文書化する"
        ),
    )
    parser.add_argument(
        "--viewport-baseline",
        default="desktop",
        help="ビューポート差分の基準（既定: desktop）",
    )
    parser.add_argument(
        "--parallelism",
        type=int,
        default=1,
        help="クロールの並列数（明示URL・オートクローリング共通。GUI既定: 4、最大: 8）",
    )
    parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="差分検知時に exit code 1 で終了（CI/CDパイプライン用）",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI向け比較モード（--compare --fail-on-driftを含み、機械可読サマリをstdoutへ出力）",
    )
    parser.add_argument(
        "--reference-doc",
        type=Path,
        action="append",
        help=(
            "参考文書（既存の画面一覧・項目定義書など）。実測結果と突合し"
            "ギャップレポートと正式画面名の注入を行う。複数指定可。"
            "対応形式: xlsx/docx/pptx/pdf/md/txt/yaml/json"
        ),
    )
    parser.add_argument(
        "--record-session",
        action="store_true",
        help=(
            "探索セッション記録モード: --url のページを記録用ブラウザで開き、"
            "閉じられるまで操作（クリック・入力・遷移・画面状態）を記録する"
        ),
    )
    parser.add_argument(
        "--record-duration",
        type=float,
        default=None,
        help="--record-session の最大記録時間（秒）。未指定はブラウザを閉じるまで",
    )
    parser.add_argument(
        "--exploration-coverage",
        action="store_true",
        help=(
            "探索カバレッジ集計モード: クロール済み report.json と記録済み"
            "セッションから exploration_heatmap.html 等を生成する"
        ),
    )
    parser.add_argument(
        "--reverse-assets",
        action="store_true",
        help=(
            "リバース生成モード: クロール済み report.json と記録済みセッションから"
            "テストケース・記録フロー（recorded_assets.json / recorded_candidates.json）を"
            "逆生成する"
        ),
    )
    parser.add_argument(
        "--export-findings",
        action="store_true",
        help=(
            "気づき票エクスポートモード: 記録済みセッションの気づきマーク（finding イベント）を"
            "再現手順付きバグ票として findings.json / findings.csv に出力する"
        ),
    )
    parser.add_argument(
        "--doc-llm",
        action="store_true",
        help=(
            "--reference-doc の自由文形式（pdf/pptx/txt/docx 本文）から LLM で"
            "画面・項目・業務ルールを追加抽出する（既定 OFF。OPENAI_API_KEY 必須）"
        ),
    )
    parser.add_argument(
        "--test-plan",
        action="store_true",
        help=(
            "テスト計画ドラフト生成モード: クロール済み report.json から"
            "画面数×優先度の工数見積・スコープ表（test_plan.md / test_plan.xlsx）を生成する"
        ),
    )
    parser.add_argument(
        "--compare-old-urls",
        help=("現新比較モード: 現行側 URL（カンマ区切り）。--compare-new-urls と併用する"),
    )
    parser.add_argument(
        "--compare-new-urls",
        help=("現新比較モード: 新側 URL（カンマ区切り）。--compare-old-urls と併用する"),
    )
    parser.add_argument(
        "--compare-auth-old",
        type=Path,
        help="現新比較: 現行側の保存済みセッション(auth.json)",
    )
    parser.add_argument(
        "--compare-auth-new",
        type=Path,
        help="現新比較: 新側の保存済みセッション(auth.json)",
    )
    parser.add_argument(
        "--compare-mask-selector",
        action="append",
        help=(
            "現新比較: 動的領域として画像差分から除外する CSS セレクタ"
            "（広告枠など既知の動的領域）。複数指定可"
        ),
    )
    parser.add_argument(
        "--ux-review",
        action="store_true",
        help=(
            "UX自動エキスパートレビュー: axe-core によるWCAG違反検査とニールセン10原則の"
            "ヒューリスティック評価を行い ux_review.json / report.html「UX所見」タブを生成する"
            "（OPENAI_API_KEY 未設定時は rules ベースの評価で完走する）"
        ),
    )
    parser.add_argument(
        "--no-a11y-audit",
        action="store_true",
        help="標準の axe-core アクセシビリティ監査を明示的に無効化する",
    )
    parser.add_argument(
        "--refresh-doc",
        action="store_true",
        help=(
            "文書の再生: 参考文書の構造を骨格として維持したまま実測値で更新した"
            "新版仕様書（refreshed_spec.md）と変更ログ（refresh_log.json）を生成する"
            "（既定 OFF。--reference-doc と併用必須。単独指定は警告して無視）"
        ),
    )
    args = parser.parse_args()
    if args.ci:
        args.compare = True
        args.fail_on_drift = True
    return args
