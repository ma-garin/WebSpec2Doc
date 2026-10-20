# PR #318 closure — 2026-10-20

判定: PASS（今回指定された製品化Acceptance Criteriaの範囲）。開始HEAD 6b91b86 / base b629130。
既存mainと既存分担worktreeは変更せず、origin/native/integrationから専用worktreeを作成。

## 実装と検証

- Accessibility重大FN 2件を汎用ARIA制約として修正。manifest・閾値・期待selectorは変更なし。
- 151 fixture: Precision 1.000 / Recall 1.000 / TP54 FP0 FN0。
- 重大A/AA: 50 fixture全評価、TP52 FN0、Recall 1.000。NOT_EVALUATEDをPASSに含めない。
- Native dependency provenanceのGUI読込を修正。実parser→保存JSON→System03→System02候補→System09で同一ID/出典位置/inferred/reach状態を保持。
- Pythonランナーが製品spec登録APIを読めない接続不具合を修正。別specの登録混入なし、0件ERRORを維持。
- 製品generate_spec_py→executor→Python runner→既存Chromeの実行: 1 PASS / 0 FAIL。
- a11y関連182 PASS、core関連257 PASS、Native接続59 PASS、runner関連91 PASS、Main独立接続レビュー38 PASS。重複を含むため合算しない。
- Chrome E2E 5 PASS、SVG 4 PASS。1920x1080/1366x768でtour next/Escape・SVG描画。JS/HTTPエラー0。
- 品質契約の旧axe/REA参照をNative実装へ更新し新規モジュールを登録。Functional Integrity Harness 72機能PASS。
- runtime静的境界: REA/claude/codex/gh/git固定依存0、Node/npm/npx別途導入要求0、runtime npm install/browser download0、production CDN0、対象vendor axe/Mermaid/driver.js残数0。
- OpenAI標準/Ollama構成は通信差替テストで宛先を確認。Ollama構成のapi.openai.com宛先0。有料API・実Ollamaへの生成要求は行っていない。
- browser unavailableは検出失敗注入テストでBLOCKED / browser unavailable / passed0を確認。
- Product Truth: 検証したfixture通し経路で違反0。候補/generatedとexecuted/verifiedは区別。

## 回収判断

未コミット差分の回収0。分担commitは包含、E1/E2a未追跡はSTUB、runtime案は限定的な旧別案。release-readinessのURL/SSRF hardeningは今回の退行ではなく別範囲として保存。判定不能な残存差分は削除しない。

## 検証範囲と限界

- docs.python.orgの公開JSをread-only取得: HTTP200、330B、Native complete、1module、0dependency、0.419秒。routeなしはlimitationに表示。実サイトの機能正しさを主張しない。
- example.com a11y比較は人手正解なし。landmark/heading一致、bypass Native追加1、regionは未宣言/未対応でaxe2/native0。fixture P/Rとは分離。
- System01→03→02→09のEvidence通しは実parser＋fixture navigator。実ChromeのSystem02実行は別検証。System09は候補リンクであり実行済み証明に変換しない。
- 全件verify-uiは未実行。必要範囲E2Eを実行。最終commit hookが全体回帰を要求し、初回4344 PASS / 6 FAIL / 14 skipped。旧契約テスト5件を追従し、SVG非決定性1件をcontent hash IDで修正。最終再実行結果はPR本文・hookログを参照。最初のbundled Chromium未導入setup errorはChrome指定で解消し、downloadなし。
- Python Playwright内部driverは許可済みpip依存の範囲。顧客指定verify_commandの任意外部ツール実行とnpm test候補提示は残るが、製品必須依存/自動fallbackではない。
- GUI商用化は本製品化変更のmerge後に再開可能。GUI全体の商用品質を今回承認したものではない。

詳細: 各JSON・review・test logを同ディレクトリに保存。

追加修正: SVGのglobal counter IDをcontent hashへ変更し、同一入力のHTML再現性と異なる図IDの分離を検証。旧vendor/TS/a11y引数テストは新製品契約へ追従し検査内容を維持。局所7/5/14 PASS。

最終全体回帰: 4351 passed, 14 skipped in 104.56s (0:01:44)。通常commit hookの全ゲートPASS。
