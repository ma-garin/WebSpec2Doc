---
name: test-automation
description: 成果物に対する実際のテストコードを生成・実行するスキル。「動作確認」「テストを書いて」「スモークテスト」「E2E」「pytest」「Playwright」「回帰テスト」への言及、done-gateで「動作確認した」を人力でなくCI判定に置き換えたい場合は必ずこのスキルを使うこと。PWA/HTMLツールはPlaywright、Streamlit/PythonはpytestをベースにYukiの規約で生成する。
---

# テスト自動化

「動いた」を主観でなくテスト実行で判定する。種別ごとに最小構成を用意し、done-gateとpre-commitに接続する。

## 種別別の方針

| 種別 | フレームワーク | 配置 |
|---|---|---|
| PWA / 単一HTML | Playwright (Python) | `tests/test_smoke.py` |
| Streamlit | pytest + streamlit AppTest | `tests/test_app.py` |
| 純Pythonロジック | pytest | `tests/` |

scaffoldは references/ を参照（playwright_smoke.py / pytest_streamlit.py）。

## Playwright（PWA/HTML）の最小スモーク観点
- ページがエラーなくロードされる（console.errorゼロ）
- 主要操作（保存・追加・エクスポート）が動く
- localStorageにデータが永続化される（reload後も残る）
- Fold5カバー幅（360px）でレイアウトが崩れない（viewport指定）
- オフライン（offline=true）で主要機能が動く

## Streamlit（pmo_agent系）の観点
- st.AppTestでアプリが例外なく起動する
- 各モジュールのsession_stateキーが衝突しない
- LLMラッパーをモックして、UI遷移ロジックを独立検証
- マルチテナント: テナントIDフィルタが効いている（越境データが出ない）

## 実行とゲート接続
```bash
# ローカル
pytest tests/ -v                      # Python/Streamlit
pytest tests/test_smoke.py            # Playwright（要 playwright install）

# done-gate: 「動作確認した」項目はこのテストのpassで代替する
# pre-commit: 軽量スモークのみ実行（重いE2EはCIで）
```

## LLMを含むロジックの扱い
- LLM呼び出しは必ずモック化してロジックを単体テスト（応答の非決定性をテストに持ち込まない）
- LLM出力の品質そのものはこのスキルでなく agent-eval スキルで評価する（責務分離）

## 注意
- テストは実装と独立に書く（Verifier原則）。実装に合わせてテストを緩めない
- flaky test（待ち時間依存）はexpect/wait_forで明示的に待つ。time.sleep禁止
