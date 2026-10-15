"""観点カタログ（RD-008 付録 A の 10 カテゴリ・61 観点）とテストレベル別の既定（RD 4.3.1）。

データのみを持つ。観点の増減は RD 付録 A が正であり、ここでは行わない。
技法名は ISO/IEC/IEEE 29119-4 の節番号付き。当てはまる技法が無い観点は「技法なし（経験ベース）」。
"""

# --- 技法名（FR-08-034） ---
EP = "同値分割（5.2.1）"
BVA = "境界値分析（5.2.3）"
CTD = "組合せテスト設計（5.2.5）"
DT = "デシジョンテーブル（5.2.6）"
ST = "状態遷移（5.2.8）"
SC = "シナリオテスト（5.2.9）"
EG = "エラー推測（5.4.1）"
NONE = "技法なし（経験ベース）"

# --- 期待値方式（RD 4.6）。human=True の観点は期待値を人が確定する（FR-08-032） ---
DBD, ALT, GLD, SCH = "db_diff", "alt_sql", "golden", "schema"

# --- 対象種別 ---
BATCH_KINDS = ("batch", "jobnet", "script")
ALL_KINDS = ("batch", "jobnet", "script", "api")

# --- テストレベル（RD 4.3.1）。キーは案件の level 値 ---
LEVEL_LABELS = {
    "integration_internal": "コンポーネント統合（内部結合）",
    "integration_external": "システム統合（外部結合）",
    "system": "システム",
    "acceptance": "受け入れ",
}

# only: カテゴリのうち、そのレベルで扱う観点番号だけに絞る（RD 4.3.1 の「月次・年度末」「業務通し」「現新比較」）
LEVEL_DEFAULTS = {
    "integration_internal": {"cats": ("A-1", "A-2", "A-5", "A-7"), "oracles": (DBD, ALT), "only": {}},
    "integration_external": {"cats": ("A-6", "A-9", "A-10"), "oracles": (GLD, SCH), "only": {}},
    "system": {
        "cats": ("A-1", "A-2", "A-3", "A-4", "A-5", "A-6", "A-7", "A-8", "A-9"),
        "oracles": (DBD, ALT, GLD),
        "only": {},
    },
    "acceptance": {
        "cats": ("A-4", "A-7", "A-10"),
        "oracles": (GLD,),
        "only": {
            "A-4": ("A-4-01", "A-4-04"),
            "A-7": ("A-7-04",),
            "A-10": ("A-10-06", "A-10-08"),
        },
    },
}

CATEGORIES = {
    "A-1": ("再実行・冪等性・リスタート", "1.1", BATCH_KINDS),
    "A-2": ("トランザクション・途中異常", "1.2", BATCH_KINDS),
    "A-3": ("ジョブネット依存・排他・同時実行", "1.3", BATCH_KINDS),
    "A-4": ("日付・時間", "1.4", BATCH_KINDS),
    "A-5": ("データ（件数・値・文字）", "1.5", BATCH_KINDS),
    "A-6": ("外部 IF ファイル検証", "1.6", BATCH_KINDS),
    "A-7": ("DB 前後比較・結果検証", "1.7", BATCH_KINDS),
    "A-8": ("ログ・通知・監査・運用", "1.8", BATCH_KINDS),
    "A-9": ("API 試験", "2", ("api",)),
    "A-10": ("外部結合テストの手順", "3", ALL_KINDS),
}

_PRI = {"M": "Must", "S": "Should", "C": "Could"}
_REL = {"M": "R1", "S": "R2", "C": "R3"}

# 行: (観点名, 技法, 既定の期待値方式, 優先度 M/S/C, 反映 FR, 出典, 未検証, 必要な事実, 人が確定)
# 必要な事実: "" なら条件なし。date / io / fixed / commit / jobnet / table（viewpoints.py が判定）
_ROWS = {
    "A-1": [
        ("正常終了後の再実行", NONE, DBD, "M", "FR-08-022", "[S2][S4]", False, "", False),
        ("途中失敗からの再実行", ST, ALT, "M", "FR-08-022", "[S2][S4]", False, "", False),
        ("再実行方式（全件やり直し／処理済みスキップ）の別", DT, DBD, "M", "FR-08-022", "[S2]", False, "", False),
        ("入力ファイルの破壊", NONE, DBD, "M", "FR-08-022", "[S1]", False, "", False),
        ("ジョブ管理製品の再実行起点", NONE, GLD, "M", "FR-08-022", "[S3]", False, "", False),
        ("同一パラメータの再実行拒否", EP, DBD, "M", "FR-08-022", "[S4]", False, "", False),
        ("リスタート状態の保持", ST, DBD, "M", "FR-08-022", "[S4]", False, "", False),
        ("前段バッチの完了確認", NONE, DBD, "M", "FR-08-022", "[S2]", False, "jobnet_kind", False),
    ],
    "A-2": [
        ("コミット単位", EG, DBD, "S", "FR-08-028", "[S1][S2]", False, "commit", False),
        ("長時間トランザクションとロック", NONE, GLD, "C", "FR-08-032", "[S1]", False, "", True),
        ("エラーレコードのスキップ・リトライ", EG, DBD, "S", "FR-08-028", "[S4]", False, "", False),
        ("外部呼び出しとの整合", EG, DBD, "S", "FR-08-028", "[S2]", False, "", False),
    ],
    "A-3": [
        ("先行ジョブ失敗時の後続", ST, DBD, "S", "FR-08-029", "[S3]", False, "jobnet", False),
        ("再実行中の状態遷移競合", ST, GLD, "S", "FR-08-029", "[S3]", False, "jobnet", False),
        ("多重起動防止", NONE, DBD, "C", "FR-08-032", "[S15]", False, "", True),
        ("バッチ・オンライン排他", NONE, DBD, "C", "FR-08-032", "[S15]", False, "", True),
        ("並列・直列の指定", CTD, DBD, "C", "FR-08-032", "[S1]（項目名のみ）", True, "", True),
    ],
    "A-4": [
        ("月末・うるう年", BVA, ALT, "M", "FR-08-024", "[S17]（規則は一般知識）", False, "date", False),
        ("月加算の存在しない日付", BVA, GLD, "M", "FR-08-024", "[S18]", False, "date", False),
        ("システム日付と業務日付の分離", EP, DBD, "M", "FR-08-024", "[一般]", True, "date", False),
        ("年度末・期末・営業日", BVA, ALT, "M", "FR-08-024", "[一般]", True, "date", False),
        ("日付またぎ・タイムゾーン・夏時間・うるう秒", BVA, GLD, "M", "FR-08-024", "[一般]", True, "date", False),
    ],
    "A-5": [
        ("件数境界（0 件・1 件・最大件数）", BVA, ALT, "M", "FR-08-025", "[S7]", False, "table_or_io", False),
        ("項目値境界（必須のみ・全項目・0/NULL・最大長）", BVA, GLD, "M", "FR-08-025", "[S7]", False, "table_or_io", False),
        ("文字コード・サロゲートペア", EG, GLD, "M", "FR-08-025", "[S20]（具体項目は一般知識）", False, "", False),
        ("NULL と空文字", EP, GLD, "M", "FR-08-025", "[一般]", True, "", False),
    ],
    "A-6": [
        ("規約確認（出力側）", EP, SCH, "M", "FR-08-026", "[S7][S8]", False, "io", False),
        ("項目マッピング", EP, ALT, "S", "FR-08-027", "[S8]", False, "io", False),
        ("固定長の桁・改行・文字コード", BVA, SCH, "M", "FR-08-026", "[一般]", True, "fixed", False),
        ("暗号化・パス", NONE, GLD, "S", "FR-08-027", "[S7]", False, "io", False),
    ],
    "A-7": [
        ("スキーマ・行数", NONE, DBD, "M", "FR-08-023", "[S6]", False, "", False),
        ("集計突合", NONE, ALT, "M", "FR-08-023", "[S6]", False, "", False),
        ("行単位ハッシュ", NONE, DBD, "M", "FR-08-023", "[S6]", False, "", False),
        ("現新比較", NONE, GLD, "M", "FR-08-023", "[S10]", False, "", False),
        ("開始・完了時点スナップショット", NONE, DBD, "M", "FR-08-023", "[S9]", False, "", False),
    ],
    "A-8": [
        ("ログの記録内容", NONE, GLD, "S", "FR-08-033", "[S1]", False, "", False),
        ("リターンコード・エラーコード・完了通知", DT, GLD, "S", "FR-08-033", "[S1]（項目名のみ）", True, "", False),
        ("ドライラン", NONE, DBD, "S", "FR-08-033", "[S1]", False, "", False),
        ("監査証跡", NONE, GLD, "S", "FR-08-033", "[一般]", True, "", False),
        ("タイムアウト・性能・メモリ・環境差異", NONE, GLD, "C", "FR-08-032", "[一般]", True, "", True),
    ],
    "A-9": [
        ("冪等キー: 同一キー再送", NONE, GLD, "S", "FR-08-030", "[S5]", False, "", False),
        ("冪等キー: 同一キー・異パラメータ", EP, GLD, "S", "FR-08-030", "[S5]", False, "", False),
        ("冪等キー: 同時 2 件送信", ST, GLD, "S", "FR-08-030", "[S12]", False, "", False),
        ("冪等キー: 保持期間・検証失敗", BVA, GLD, "S", "FR-08-030", "[S5]", False, "", False),
        ("冪等キー: 対象メソッド", EP, GLD, "S", "FR-08-030", "[S5]", False, "", False),
        ("タイムアウト後の再送", EG, DBD, "S", "FR-08-030", "[S12]", False, "", False),
        ("ページング", BVA, ALT, "S", "FR-08-030", "[S13]", False, "", False),
        ("レート制限", NONE, GLD, "S", "FR-08-030", "[S13]", False, "", False),
        ("認証・認可", DT, GLD, "S", "FR-08-030", "[S13]（出典が弱い）", False, "", False),
        ("スキーマ互換", NONE, SCH, "S", "FR-08-030", "[S13]（出典が弱い）", False, "", False),
        ("スタブ・モック", NONE, GLD, "S", "FR-08-030", "[S13]（出典が弱い）", False, "", False),
        ("エラー応答の網羅", EP, GLD, "S", "FR-08-030", "[一般]", True, "", False),
    ],
    "A-10": [
        ("相手先との事前合意", NONE, GLD, "C", "FR-08-031", "[S7][S16]", False, "", False),
        ("テストデータ受け渡し", NONE, GLD, "C", "FR-08-031", "[S16]", False, "", False),
        ("規約確認（単体相当）", BVA, SCH, "C", "FR-08-031", "[S7]", False, "", False),
        ("疎通確認", NONE, GLD, "C", "FR-08-031", "[S7]", False, "", False),
        ("スタブからの切替", NONE, GLD, "C", "FR-08-031", "[S13]（出典が弱い。切替手順は未確認）", False, "", False),
        ("業務通し・異常系", SC, GLD, "C", "FR-08-031", "[S7]", False, "", False),
        ("段階的拡大", NONE, GLD, "C", "FR-08-031", "[S16]", False, "", False),
        ("日次・月次サイクルの通し", SC, ALT, "C", "FR-08-031", "[一般]", True, "", False),
        ("簡易版項目書の運用", NONE, GLD, "C", "FR-08-031", "[S8]", False, "", False),
    ],
}


def _levels_of(cat, vid):
    """そのカテゴリ・観点番号が既定で扱われるテストレベルの tuple（LEVEL_DEFAULTS から導出）。"""
    out = []
    for level, d in LEVEL_DEFAULTS.items():
        if cat not in d["cats"]:
            continue
        only = d["only"].get(cat)
        if only is None or vid in only:
            out.append(level)
    return tuple(out)


def _make(cat, no, row):
    name, tech, oracle, pri, fr, src, unv, needs, human = row
    vid = f"{cat}-{no:02d}"
    cat_name, section, kinds = CATEGORIES[cat]
    return {
        "id": vid,
        "cat": cat,
        "cat_name": cat_name,
        "name": name,
        "technique": tech,
        "oracle": oracle,
        "human_oracle": human,
        "priority": _PRI[pri],
        "release": _REL[pri],
        "fr": fr,
        "levels": _levels_of(cat, vid),
        "kinds": kinds,
        "needs": needs,
        "basis": f"調査4 {section} {src}",
        "unverified": unv,
    }


CATALOG = tuple(
    _make(cat, i, row)
    for cat, rows in _ROWS.items()
    for i, row in enumerate(rows, start=1)
)
