# S10 設定・監査・アカウント 設計（波 B）

## 設定 6 区分と現行タブの対応
基準: 03_SCREEN_DESIGN_CONTRACT §4「設定」。保存は区分ではなく全区分共通の振る舞い。

| 区分 | 現行の入口 | 今回 |
|---|---|---|
| 判定基準 | テスト設計・解析の既定値 | 変えない |
| 指摘分類 | 無し | 変更要求 |
| 役割・権限 | メンバー管理 | 変えない |
| 承認規則 | 承認と監査 | 新設 |
| AI送信先 | APIキー | 秘密値を返さない |
| 監査 | 承認と監査 | 検索を拡張 |

- タブの URL 一覧は web/routes/pages.py（S00 所有）にあるため、区分ごとの新タブは CR-10-1 で要求する。今回は既存の audit タブを「承認と監査」に改名して承認規則を置く。

## 画面 × 状態 9 種
| 状態 | 承認規則 | 監査ログ | 非該当の理由 |
|---|---|---|---|
| 通常 | normal | normal | — |
| 0件 | 既定値を表示 | empty | — |
| 検索0件 | 非該当 | no-match | 規則は検索しない |
| 読込中 | loading | loading | — |
| 失敗 | error | error | — |
| 権限不足 | forbidden | forbidden | — |
| 未保存 | dirty・invalid | 非該当 | 監査は読取専用 |
| 競合 | conflict（409） | 非該当 | 監査は追記のみ |
| 復元 | restored | 非該当 | 監査は追記のみ |

- 状態は form#approval-policy と tbody#admin-audit-events の data-state 属性。

## 業務フロー
- 承認規則: /settings/audit → GET/PUT /api/admin/approval-policy → web/services/approval_policy.py → instance（テナント別）approval_policy.json（新規キー。既存キーは変えない）→ 監査 policy.approval_updated（変更項目・版・理由）。
  - 入力誤り 400（field 付き。入力欄の下に原因と直し方）／版ずれ 409（最新値を表示し入力を残す）／書込失敗 500。
  - 既定は「起票者と承認者の同一を禁止」。少人数の例外は人数上限 1〜5 と理由 10 文字以上が必須。
- 監査検索: GET /api/admin/audit?actor&since&until&case&action&outcome&query → read_admin_audit → 表（いつ・誰が・何を・どの案件に・対象・結果・理由）。
- 監査出力: GET /api/admin/audit.csv（同じ条件・最大 1000 行）。出力自体を audit.exported として記録。
- 語彙は common-contract §4 の op（decision.draft/approve/revoke、review.adopt/reject/hold）を操作の選択肢と表示名に入れた。案件は target_type=case か detail.case。

## 秘密値
- /api/settings と /api/integrations の *_masked は先頭・末尾の文字も返さず「保存済み」だけを返す。
- 監査の detail は既存の除去規則（password/token/api_key 等）を通る。CSV も同じ。

## 変えない点
- web/auth.py・tenancy.py・pages.py・既存監査の行形式（version 1）・既存設定キー。
- 職務分離の実際の判定（承認 API での 403）は判断の承認 API を持つ担当が本規則を読む。S10 は規則の保存と提示まで。

## 共通への変更要求
- CR-10-1（pages.py のタブ追加）・CR-10-2（承認 API が本規則を読む）。
