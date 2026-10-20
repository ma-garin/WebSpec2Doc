# サードパーティ通知

`requirements.txt` の直接依存のライセンス一覧。ライセンスは `venv` にインストールされたパッケージのメタデータ（License-Expression、License、無ければ License 分類子）から取得した。確認日は 2026-10-20。

## 要法務確認

| パッケージ | ライセンス | 論点 |
|---|---|---|
| psycopg（`psycopg[binary]`） | LGPL-3.0-only | LGPL。動的リンク（pip の別パッケージとして利用）で配布する限りは通常問題とされにくいが、同梱・再配布の形態によっては置換可能性などの義務が生じるため法務で確認すること。`binary` エクストラは libpq 等を同梱する |

GPL／AGPL の依存は確認できなかった。

## 直接依存

| パッケージ | requirements の指定 | 確認したバージョン | ライセンス |
|---|---|---|---|
| playwright | ==1.61.0 | 1.61.0 | Apache-2.0 |
| networkx | ==3.3 | 3.3 | BSD License（分類子による） |
| jinja2 | ==3.1.6 | 3.1.6 | BSD License（分類子による） |
| openpyxl | ==3.1.4 | 3.1.4 | MIT |
| pypdf | ==6.15.0 | 6.15.0 | BSD-3-Clause |
| PyYAML | ==6.0.1 | 6.0.1 | MIT |
| defusedxml | ==0.7.1 | 0.7.1 | PSFL（Python Software Foundation License） |
| pytest | ==9.0.3 | 9.0.3 | MIT |
| pytest-cov | ==5.0.0 | 5.0.0 | MIT |
| pytest-playwright | ==0.8.0 | 0.8.0 | Apache-2.0（Apache Software License） |
| pytest-timeout | ==2.3.1 | 2.3.1 | MIT |
| flask | ==3.1.3 | 3.1.3 | BSD-3-Clause |
| Pillow | >=11.0.0 | 13.0.0 | MIT-CMU |
| numpy | >=2.0.0 | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| python-dotenv | ==1.2.2 | 1.2.2 | BSD-3-Clause |
| prometheus-client | ==0.21.1 | 0.21.1 | Apache-2.0（Apache Software License） |
| Authlib | ==1.7.2 | 1.7.2 | BSD-3-Clause |
| python-docx | >=1.1 | 1.2.0 | MIT |
| pdfminer.six | >=20231228 | 20260107 | MIT |
| psycopg | ==3.3.6 | 3.3.6 | LGPL-3.0-only（要法務確認） |
| Faker | ==40.43.0 | 40.43.0 | MIT |

## 注記

- pytest、pytest-cov、pytest-playwright、pytest-timeout、Faker はテスト・開発用途。配布物に含めない構成なら再配布義務の対象外となる（`requirements.txt` には同居している）。
- 範囲指定（`>=`）のパッケージは、導入時期によりバージョンとライセンスが変わりうる。
- 推移的依存（間接依存）は本表の対象外。再配布する場合は別途洗い出すこと。
- playwright が取得する Chromium など、パッケージ外のバイナリには別のライセンスが適用される（未確認）。
- 表の "Apache-2.0" のうち pytest-playwright と prometheus-client は、License 欄の記述または分類子による判定。SPDX 表記への正規化は筆者による。
