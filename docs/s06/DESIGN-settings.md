# S06 設定画面（/docverify#settings）設計

## 画面 × 状態
| 状態 | 表示 | 責任 |
|---|---|---|
| 読み込み中 | 状態帯「読み込み中…」 | settings.js |
| 通常 | 左に区分ナビ（sticky）・右にフォーム | settings.js |
| 未保存 | 状態帯 b-unsaved＋保存ボタン活性・離脱確認 | settings.js |
| 保存中 | 保存ボタン「保存中…」・無効 | settings.js |
| 成功 | トースト「設定を保存しました」 | DV.toast |
| 競合 409 | b-conflict「最新を読み直す／自分の変更を保持して保存」 | settings.js |
| 入力誤り 400 | b-error＋次の行動 1 行 | API 文言 |
| 失敗 5xx/通信 | b-error＋「読み直す」 | settings.js |
| 認証オフ | 役割は「利用者名の記録なし」で割当不可 | API users.enabled |

## 業務フロー
入口 /docverify#settings → GET /api/docverify/settings → settings_store.load()（既定値＋利用者設定・出典・マスク済みキー・利用者一覧・S10 承認規則）
→ 編集 → PUT /api/docverify/settings {rev, values, api_key?} → settings_store.save()（検証→flock→rev 照合→保存）
→ 保存先 data/docverify/_settings/<tenant|_none>/settings.json（秘密値は同じ場所の secret.json・0600・応答に含めない）
→ 判定: pair_review._judge が settings_store.effective() の上限・種別・変更分の規則を読む（/api/docverify/<iid>/pair/gate に反映）
→ 疎通: POST /api/docverify/settings/ai-check → OpenAI は GET /v1/models、Ollama は GET /api/tags（5 秒）。失敗は {ok:false, message, next}。

## 変える点
- 設定ビューを説明文の箇条書きから編集・保存できるフォームへ（4 区分）
- /api/docverify/settings を v2（rev・409・出典）へ置換。旧 _settings.json と settings.load_settings() は残す（他画面が参照）
- 対検査の出口基準を固定値から設定の上限へ（既定は重大 0・主要/軽微 上限なし＝従来と同じ判定）

## 変えない点
- 未検証を合格に数えない（固定）・本人承認禁止の判定ロジック（pair_review.approve）・S10 の approval_policy.json（読み取りのみ）

## 共通への変更要求
なし（共通ファイルは未編集）
