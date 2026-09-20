# SkyBook（検証用の航空券予約アプリ・Android 版）

WebSpec2Doc のスマホアプリ検証で使う対象アプリ。Web 版（`demo/flight_site/`）と画面・項目 ID・
バリデーションを一致させてある（10 画面、ログイン壁、モーダル / タブ / アコーディオン、
通常導線から到達できない DebugActivity）。

## ビルド（手元だけで完結する）

- Android Studio: このフォルダを開いて Run。エミュレータか実機に入る。
- コマンド: `./gradlew assembleDebug` → `app/build/outputs/apk/debug/app-debug.apk` → `adb install`。
  JDK 17 と Android SDK（platform 34 / build-tools 34）が必要。

## 使い方のメモ

- ログイン: メール形式なら何でも可。パスワードは `password123`。「ゲストとして続ける」でも進める。
- 検索: 便があるのは HND→CTS（3 便）/ HND→FUK / ITM→OKA / NRT→OKA。他は空状態。
- カード: `4242424242424242` のみ承認。クーポン `SKY10` で 10% 引き。
- 設定の「バージョン 1.0.0」を 7 回タップするとデバッグメニューが出る。
