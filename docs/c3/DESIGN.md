# C3 状態・復帰・通知の共通部品（設計）

根拠: common-contract §2.3（状態 9 種の責任分担）。System は呼ぶだけ。

## 使い方（System 側は 1 呼び出し）
- 本文コンテナを `class="ui-state-root" data-state="normal"` にする（set が自動付与もする）
- `UIStates.set(root, state, {message, next, ...})`
- fetch 失敗は `UIStates.fromResponse(root, res, opts)`（403→権限不足、409→競合、401→再ログイン案内、他→失敗）
- 未保存判定は `UIStates.guard(() => 変更あり?)`。画面内の遷移前は `UIStates.confirmLeave()`
- 通知は `Notify.toast(msg, {kind, next})`（右上）と `Notify.band(container, msg, {kind, next, id})`（画面内の帯）
- partial は任意。`{% include 'partials/states/<名>.html' %}` を root 直下に置けば初期描画から文言が出る。無ければ JS が作る

## 状態 9 種

| 状態 | data-state | 表示 | System が渡す |
|---|---|---|---|
| 通常 | normal | 中身そのまま | 無し |
| 0件 | empty | 中身を隠し空表示 | 理由・次の行動・onAction |
| 検索0件 | no-match | 空表示＋条件 | conditions・onClear |
| 読込中 | loading | スケルトン | kind |
| 失敗 | error | 赤枠＋再試行 | 原因文・onRetry |
| 権限不足 | forbidden | 赤枠 | role（必要な役割） |
| 未保存 | dirty | 上部帯＋離脱確認 | onSave・guard |
| 競合 | conflict | 黄枠＋2択 | onReload・onKeep |
| 復元 | restored | 上部帯 | onDiscard |

- 0件（灰・枠無し）と失敗（赤枠）は見た目を分ける。参照切れは error で出す
- dirty / restored は本文を隠さない（作業を続けられる）
- 文言は textContent で入れる。既定文はすべて利用者向け日本語＋次の行動 1 行

## 通知 2 段
- トースト: success 4 秒・info 6 秒で消える。warning / error は自動で消さない。ホバー中は消さない。最大 4 件
- 帯: その画面に居る間は残す。id で差し替え・`clearBand` で消す
- 常時表示ログ（AutoRun）は通知に流さず `.notify-log`（高さ固定・内側スクロール・折りたたみ無し）

## 変えない点
- 既存の uiSkeleton / uiEmpty / uiError（history.js 等が使用）はそのまま残す
- events.js（AutoRun のイベント結線）・table-utils.js は変更なし（状態部品と責務が別）

## 共通への変更要求
- CR-C3-001: web/__init__.py に dev_states の登録（docs/change-requests/C3-1.md）
