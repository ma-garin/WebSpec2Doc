# WS2D-AT-006 受け入れ照合表 System 06 R1

- 判定者: （保守者が記入） / 判定日: （保守者が記入） / 判定: （保守者が記入）
- 証跡: 単体・結合テスト `tests/test_docverify_r1_unit.py`・`tests/test_docverify_r1_integration.py`（54 件合格）、システムテスト画面 `docs/design/docverify/st-r1/`、見切れ検査 `scripts/check_clipping.py`（0 件・26 画面 × 2 幅）

| 要件 | 確認方法 | 結果 |
|---|---|---|
| FR-06-015 読めなかった要素 | UT・ST（xlsx） | 合格 |
| FR-06-075 適用範囲 | UT（scope・xlsx） | 合格 |
| FR-06-100 レビュー内スコア | UT・ST（判定） | 合格 |
| FR-06-101 ホームのスコア | IT・ST（ホーム） | 合格 |
| FR-06-102 算出できない場合 | UT | 合格 |
| FR-06-103 計算式と限界 | ST（モーダル） | 合格 |
| FR-06-104 版ごとの推移 | UT・ST（2 版） | 合格 |
| SCR-06-21 実行中 | 未実施 | 未検証 |
| SCR-06-22 失敗 | ST（壊れた docx） | 合格 |
| SCR-06-23 0 件 | ST（ホーム） | 合格 |
| SCR-06-24 狭い画面 | ST（1280×720） | 合格 |
| SCR-06-25 モーダル | ST（Esc・戻り先） | 合格 |
| SCR-06-26 長文 | ST（200 字の名前） | 合格 |
| NFR-06-16 エラー文 | IT（例外名・パス無し） | 合格 |
| NFR-06-18 キーボード | Esc のみ確認 | 一部 |
| AC-06-05 全状態・見切れ | check_clipping | 合格 |

- 未検証: SCR-06-21（二重送信防止の操作試験）、NFR-06-18（Tab だけで作成から判定まで）、実際に Word/Excel で作った文書での取り込み
- 既知の残課題: `static/js/docverify-review.js` が 556 行（設計上限 400 行）。R2 で分割する
- 設計からの逸脱（DD に反映予定）: コメントの所在を `xl/comments/` 配下まで拡大、数えていない場合の文言を「数えていません（未確認）」に変更
- 範囲外で見つけた既存の不合格: `.github/workflows/spec-drift.yml` 不在（CI 禁止の規約による）、`backend_test_envs.py`・`impact.py` の機能契約未登録（他セッションの担当）
