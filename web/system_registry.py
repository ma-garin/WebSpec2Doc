"""System 一覧の正本。

/systems のカード・CLI 案内の番号・切替メニューの名称はすべてここから出す。
番号や数を各テンプレートに直接書かない（食い違いの原因になる）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SystemInfo:
    key: str
    number: str  # "01" / "01 · app" / ""（指揮は番号なし）
    name: str
    short_name: str  # 切替メニュー用
    url: str
    description: str  # 一部 <b> を含む（テンプレートで |safe 出力。固定文言のみ）
    chips: tuple[str, ...]
    status: str = "implemented"  # "implemented" | "preview"(模擬)
    role: str = ""  # 空なら全員。"admin" なら管理者のみカードを出す
    badge: str = ""
    open_label: str = ""
    prototype: bool = False  # True ならシステム選択の主一覧に出さない（URL は残す）

    @property
    def label(self) -> str:
        """カード・kicker に出す番号表示。指揮は番号なしで「まとめ役」。"""
        return f"System {self.number}" if self.number else "まとめ役"

    @property
    def is_preview(self) -> bool:
        return self.status == "preview"


SYSTEMS: tuple[SystemInfo, ...] = (
    SystemInfo(
        key="cond", number="", name="指揮", short_name="指揮", url="/orchestration",
        description="全サイトを毎日見張り、直して、報告書を下書きする。複数のシステムを 1 本につないで回すので、あなたは<b>承認だけ</b>で済みます。",
        chips=("全サイト一覧", "毎日の見張り", "自動の修正", "報告書の下書き"),
        badge="新規", open_label="指揮を開く →",
    ),
    SystemInfo(
        key="doc", number="01", name="ドキュメント作成", short_name="ドキュメント作成", url="/dashboard",
        description="URL を渡すと、画面仕様書・遷移図・項目定義を生成します。認証・対象範囲・前回差分にも対応。既存サイトの仕様化に。",
        chips=("画面仕様書", "遷移図", "フォーム定義", "差分"),
        open_label="ドキュメント作成を開く →",
    ),
    SystemInfo(
        key="app", number="01 · app", name="ドキュメント作成(app)", short_name="ドキュメント作成(app)", url="/doc-app",
        description="スマホアプリ向けの画面の流れを、サンプルデータで再生する試作です（APK・.app の実解析はまだ行いません）",
        chips=("画面仕様書", "遷移図", "フォーム定義"),
        status="preview", badge="試作（サンプルデータ）", open_label="ドキュメント作成(app)を開く →", prototype=True,
    ),
    SystemInfo(
        key="test", number="02", name="テスト自動化", short_name="テスト自動化", url="/test-automation",
        description="解析結果とテストケース表からテストを組み立て、<b>自動テストコードの生成と実行</b>までを画面上で行います。対象サイトの変更は実行前に検知し、どのテストが壊れるかを先に示します。",
        chips=("テスト設計", "コード生成", "自動テスト実行", "変更の事前検知", "トレーサビリティ"),
        role="admin", badge="新規", open_label="テスト自動化を開く →",
    ),
    SystemInfo(
        key="autorun", number="03", name="AutoRun", short_name="AutoRun", url="/auto-run",
        description="ベテラン QA として、受領から実行完了レポートの納品まで。フル QA を止めずに回し、未検証は明記・不在は証明しません。",
        chips=("テスト計画", "設計・ケース", "実行・証跡", "カバレッジ"),
        badge="独立システム", open_label="AutoRun を開く →",
    ),
    SystemInfo(
        key="cli", number="04", name="CLI / API", short_name="CLI / API", url="/cli",
        description="ブラウザを開かずに解析・AutoRun・テスト実行まで回せます。CI パイプラインからの呼び出しに。",
        chips=("CI 組み込み", "REST API", "JSON 出力", "終了コード"),
        badge="画面なし", open_label="CLI / API の使い方を見る →",
    ),
    SystemInfo(
        key="heal", number="05", name="オートヒーリング", short_name="オートヒーリング", url="/healing",
        description="接続したリポジトリで検証を実行し、失敗を不具合として切り出して<b>修正差分</b>まで作ります。<b>マージは人が判断します</b>。",
        chips=("不具合の検出", "バグレポート", "コード修正", "PR 作成", "再テストのループ"),
        role="admin", badge="新規", open_label="オートヒーリングを開く →",
    ),
    SystemInfo(
        key="docverify", number="06", name="ドキュメント検証", short_name="ドキュメント検証", url="/docverify",
        description="仕様書のインスペクションを 1 画面で進めます。取り込むと<b>曖昧な表現・抜け・食い違い</b>の候補が根拠の位置付きで並び、<b>採用か却下を選ぶだけ</b>。質問票・版の差分・実画面との照合・終了判定まで。",
        chips=("インスペクション", "候補の採否", "質問票", "実画面との照合"),
        badge="新規", open_label="ドキュメント検証を開く →",
    ),
    SystemInfo(
        key="batch", number="07", name="バッチ・スクリプトのテスト", short_name="バッチ・スクリプトのテスト", url="/batch-test",
        description=".bat / .sh / .ps1 と仕様書を渡すと、<b>引数・入力ファイル・終了コード・出力・ログ</b>の観点でケース表を作り、<b>実行用のテストコード</b>まで生成します。画面のない処理のテストに。",
        chips=("テスト設計", "ケース表", "終了コード・出力", "コード生成"),
        badge="新規", open_label="バッチ・スクリプトのテストを開く →",
    ),
    SystemInfo(
        key="backend", number="08", name="バッチ・バックエンドのテスト", short_name="バッチ・バックエンドのテスト", url="/backend-test",
        description="バッチジョブ・API・DB を<b>結合・システム・受け入れ</b>のレベルで確かめます。観点からケース・テストデータ・テストコードを作り、<b>実行と判定</b>まで進めます。期待値は<b>前後比較・別経路・ゴールデン</b>で裏付けます。",
        chips=("テスト設計", "DB 前後比較", "実行と判定"),
        badge="新規", open_label="バッチ・バックエンドのテストを開く →",
    ),
    SystemInfo(
        key="impact", number="09", name="影響度分析", short_name="影響度分析", url="/impact",
        description="変更後の仕様書と変更内容を渡すと、<b>変更箇所</b>を抜き出して設計書・画面仕様書を検索し、<b>影響範囲</b>と<b>テストの優先度</b>を根拠の文書つきで示します。変更部分のテスト設計に。",
        chips=("変更箇所の抽出", "影響範囲", "テスト優先度", "根拠の文書"),
        badge="新規", open_label="影響度分析を開く →",
    ),
    SystemInfo(
        key="common", number="", name="共通", short_name="共通", url="/settings",
        description="設定・ガイド・組織・ユーザー・アカウント。どのシステムからも使う画面です。",
        chips=(), prototype=True,  # システム選択のカードには出さない
    ),
)

_BY_KEY = {s.key: s for s in SYSTEMS}


def system(key: str) -> SystemInfo:
    """key から System を返す。未登録の key は KeyError（テンプレートの typo を早く落とす）。"""
    return _BY_KEY[key]
