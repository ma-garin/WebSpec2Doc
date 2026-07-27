# 欠陥タクソノミ文献レビュー（技法エンジン更新・R5）

作成日: 2026-07-28 / 対象: `src/autorun/error_guessing.py` の19分類への規格ID割り当て可否判断

## 結論(3行)

1. **WSTG実IDは一次確認できた**: 公式リポジトリのチェックリストで INPV-01〜20 / SESS-01〜11 / BUSL-01〜10 のID・名称対応を確認。v4.2（現行stable、2020-12-03公開）に存在するのは INPV-01〜19 / SESS-01〜09 / BUSL-01〜09 で、BUSL-08 は v4.2 個別ページで直接確認済み。
2. **現実装19分類のうち8分類にWSTG実IDを割り当て可能**（エスケープ・拡張子・多重実行・画面遷移・セッション等）。残りはODC/IEEE 1044系で、こちらは個別値の一次確認が取れなかったため現状の「カテゴリ単位」を維持すべき。
3. **ODC 8分類・Beizer分類・IEEE 1044 type値・Whittaker攻撃カタログはいずれも一次確認できず**（有料論文・書籍・有料規格）。これらの具体的列挙は引用禁止リストに載せた。

## WSTG実ID対応表（一次確認済みのみ。確認元URL付き）

### 確認元（すべてOWASP公式）

| # | 確認元 | URL | 確認内容 |
|---|---|---|---|
| S1 | WSTGプロジェクトページ | https://owasp.org/www-project-web-security-testing-guide/ | 現行stable = **v4.2、2020-12-03公開** |
| S2 | 公式リポジトリ checklist（latest/5.0開発版） | https://raw.githubusercontent.com/OWASP/wstg/master/checklists/checklist.md | ID↔名称の全対応 |
| S3 | stable版 目次 | https://owasp.org/www-project-web-security-testing-guide/stable/ | v4.2の収録数: INPV 19件（4.7.1〜4.7.19）/ SESS 9件（4.6.1〜4.6.9）/ BUSL 9件（4.10.1〜4.10.9）。名称・順序がS2と一致 |
| S4 | v4.2 個別テストページ | https://owasp.org/www-project-web-security-testing-guide/v42/4-Web_Application_Security_Testing/10-Business_Logic_Testing/08-Test_Upload_of_Unexpected_File_Types | ページ上に **WSTG-BUSL-08** の表記を直接確認（スポットチェック） |

注意: v4.2の「ID↔名称」対応を個別ページで直接確認したのは BUSL-08 のみ。他は S2 のID表と S3 の名称・順序一致から確定させた（すべて公式一次資料由来だが、確認方法の強度は BUSL-08 > その他）。

### 入力検証（WSTG-INPV）

| ID | 名称（原文） | v4.2 |
|---|---|---|
| WSTG-INPV-01 | Testing for Reflected Cross Site Scripting | あり |
| WSTG-INPV-02 | Testing for Stored Cross Site Scripting | あり |
| WSTG-INPV-03 | Testing for HTTP Verb Tampering | あり |
| WSTG-INPV-04 | Testing for HTTP Parameter Pollution | あり |
| WSTG-INPV-05 | Testing for SQL Injection | あり |
| WSTG-INPV-06 | Testing for LDAP Injection | あり |
| WSTG-INPV-07 | Testing for XML Injection | あり |
| WSTG-INPV-08 | Testing for SSI Injection | あり |
| WSTG-INPV-09 | Testing for XPath Injection | あり |
| WSTG-INPV-10 | Testing for IMAP SMTP Injection | あり |
| WSTG-INPV-11 | Testing for Code Injection | あり |
| WSTG-INPV-12 | Testing for Command Injection | あり |
| WSTG-INPV-13 | Testing for Format String Injection | あり |
| WSTG-INPV-14 | Testing for Incubated Vulnerabilities | あり |
| WSTG-INPV-15 | Testing for HTTP Splitting Smuggling | あり |
| WSTG-INPV-16 | Testing for HTTP Incoming Requests | あり |
| WSTG-INPV-17 | Testing for Host Header Injection | あり |
| WSTG-INPV-18 | Testing for Server-Side Template Injection | あり |
| WSTG-INPV-19 | Testing for Server-Side Request Forgery | あり |
| WSTG-INPV-20 | Testing for Mass Assignment | **latest(5.0開発版)のみ** |

### セッション管理（WSTG-SESS）

| ID | 名称（原文） | v4.2 |
|---|---|---|
| WSTG-SESS-01 | Testing for Session Management Schema | あり |
| WSTG-SESS-02 | Testing for Cookies Attributes | あり |
| WSTG-SESS-03 | Testing for Session Fixation | あり |
| WSTG-SESS-04 | Testing for Exposed Session Variables | あり |
| WSTG-SESS-05 | Testing for Cross Site Request Forgery | あり |
| WSTG-SESS-06 | Testing for Logout Functionality | あり |
| WSTG-SESS-07 | Testing Session Timeout | あり |
| WSTG-SESS-08 | Testing for Session Puzzling | あり |
| WSTG-SESS-09 | Testing for Session Hijacking | あり |
| WSTG-SESS-10 | Testing JSON Web Tokens | **latest(5.0開発版)のみ** |
| WSTG-SESS-11 | Testing for Concurrent Sessions | **latest(5.0開発版)のみ** |

### ビジネスロジック（WSTG-BUSL）

| ID | 名称（原文） | v4.2 |
|---|---|---|
| WSTG-BUSL-01 | Test Business Logic Data Validation | あり |
| WSTG-BUSL-02 | Test Ability to Forge Requests | あり |
| WSTG-BUSL-03 | Test Integrity Checks | あり |
| WSTG-BUSL-04 | Test for Process Timing | あり |
| WSTG-BUSL-05 | Test Number of Times a Function Can Be Used Limits | あり |
| WSTG-BUSL-06 | Testing for the Circumvention of Work Flows | あり |
| WSTG-BUSL-07 | Test Defenses Against Application Misuse | あり |
| WSTG-BUSL-08 | Test Upload of Unexpected File Types | あり（**v4.2ページで直接確認**） |
| WSTG-BUSL-09 | Test Upload of Malicious Files | あり |
| WSTG-BUSL-10 | Test Payment Functionality | **latest(5.0開発版)のみ** |

依頼のあった注目3点の実ID: ファイルアップロード = **BUSL-08 / BUSL-09**、プロセスタイミング = **BUSL-04**、多重送信（回数制限） = **BUSL-05**。

## 実証された知見（出典必須）

| # | 知見 | 出典 |
|---|---|---|
| E1 | WSTGの現行stableは v4.2（2020-12-03）。テストIDは `WSTG-<カテゴリ>-<番号>` 形式で個別ページに明記される | S1, S4（上表） |
| E2 | v4.2 と latest でID収録範囲が異なる（INPV-20 / SESS-10,11 / BUSL-10 はlatestのみ）。IDを引用する際は版の明記が必須 | S2 と S3 の突合 |
| E3 | ODCの原典は Chillarege et al. "Orthogonal defect classification—a concept for in-process measurements", IEEE TSE, 1992, DOI: 10.1109/32.177364（OpenAlex被引用789、2026-07-28時点）。closed accessで、abstractにはdefect typeの列挙は無い | https://api.openalex.org/works/doi:10.1109/32.177364 |
| E4 | **否定的結果**: 「error guessing」を題名・抄録に含む学術文献はOpenAlex全体で11件のみ。最大被引用は教科書（Naik & Tripathy 2009, 被引用138）で、エラー推測単独の実証研究（効果量を測ったもの）は見つからなかった。エラー推測は「教科書的技法として言及されるが、学術的実証はほぼ無い」領域である | https://api.openalex.org/works?filter=title_and_abstract.search:%22error%20guessing%22%20software%20testing |
| E5 | **否定的結果**: Whittaker "How to Break Software" はOpenAlexで書籍レコード・攻撃カタログを記述した論文とも発見できず（検索結果はすべて無関係分野） | https://api.openalex.org/works?search=How%20to%20Break%20Software%20Whittaker |

## 主張どまりの知見

- ODCのdefect typeは「8分類（Function / Assignment / Interface / Checking / Timing/Serialization / Build/Package/Merge / Documentation / Algorithm）」とする記述が教科書・解説記事に広く流通しているが、**1992年原文での正確な文言・分類数は未確認**（原文はclosed access、著者サイト・OA索引でも本文入手不可）。
- Whittakerの攻撃カタログが「UI入力への攻撃を番号付きで列挙する」形式であることは二次資料（書評・教科書での言及）レベルの通説。**具体的な攻撃番号・攻撃名の一覧は一次入手できなかった**（書籍のみ。二次資料しか無い旨をここに明記する）。
- Beizer "Software Testing Techniques" (1990) のbug taxonomy大分類（4桁コード体系）も同様に通説レベル。**今回のレビューでは一次・二次とも未調査**（書籍のみで、20回上限内で入手経路が無かった）。

## 未確認・引用禁止リスト

以下は本レビューで一次確認できなかった。**確認が取れるまで、コード・ドキュメント・営業資料のいずれにも書かないこと。**

1. ODC 8分類の具体名（Function, Assignment, ... の列挙）— 原文未確認
2. Beizer bug taxonomyの大分類名・コード体系 — 未調査
3. IEEE 1044-2009 の分類軸・type値の一覧 — 有料規格で未入手。**現実装が参照する「IEEE 1044: Data / Logic」等の値も規格原文で未検証**である点に注意
4. Whittakerの攻撃番号（attack 1〜n）と各攻撃名 — 書籍未入手
5. WSTG-INPV-20 / SESS-10 / SESS-11 / BUSL-10 を「v4.2のID」として引用すること（latestのみに存在）
6. WSTG v4.2のID↔名称対応のうちBUSL-08以外を「個別ページで確認済み」と表現すること（確認方法はS2+S3の突合）

## 現実装とのギャップ（19分類にWSTG実IDを割れるか、Whittaker攻撃で追加すべき項目）

対象: `/Users/fujimagariyuki/dev/active/webspec2doc/src/autorun/error_guessing.py` の `CATEGORY_STANDARD`（現在すべてカテゴリ単位表記）。

### WSTG実IDを割り当て可能な分類（8/19）

| 現分類 | 現表記 | 割り当て可能な実ID（v4.2確認済み範囲） |
|---|---|---|
| エスケープ | WSTG: Input Validation (INPV) | WSTG-INPV-01, 02（XSS）, 05（SQLi） |
| 形式 | ODC: Checking / WSTG: INPV | カテゴリ維持が妥当（形式不正は特定IDに収束しない） |
| 拡張子 | WSTG: BUSL — ファイルアップロード | **WSTG-BUSL-08**（直接確認済み） |
| サイズ | WSTG: BUSL — ファイルアップロード | BUSL-08/09近縁だが「サイズ上限」専用IDは無い → カテゴリ維持 |
| 多重実行 | ODC: Timing / WSTG: BUSL | **WSTG-BUSL-05** |
| 画面遷移 | WSTG: BUSL | **WSTG-BUSL-06**（ワークフロー迂回） |
| セッション | WSTG: SESS | WSTG-SESS-06（ログアウト）, SESS-07（タイムアウト）を項目内容に応じて |
| 再読込 | WSTG: BUSL | BUSL-05近縁（再送信）。CSRF文脈なら SESS-05 |

残り11分類（入力値の正規化・文字種・数値表記・桁あふれ・小数・暦・長さ・区切り・文字・並行更新ほか）はODC/IEEE 1044系であり、**その個別値が未検証のため現状のカテゴリ単位表記が正しい状態**。無理にID化しない。

### Whittaker攻撃由来の追加候補

攻撃カタログ自体が未一次確認のため、**「Whittaker準拠」を根拠として項目追加してはならない**。ただしWSTG v4.2で一次確認できた次の観点は現19分類に対応が無く、追加候補になる:

| 追加候補 | 根拠ID（一次確認済み） |
|---|---|
| プロセスタイミング（処理途中の放置・順序前後） | WSTG-BUSL-04 |
| リクエスト偽装（隠しパラメータ・値書き換え） | WSTG-BUSL-02 |
| 悪意あるファイル内容（拡張子偽装・二重拡張子） | WSTG-BUSL-09 |

## WebSpec2Docへの適用判断（表)

| # | 施策 | 判断 | 根拠 |
|---|---|---|---|
| 1 | 上記8分類へのWSTG実ID付与（`CATEGORY_STANDARD` 拡張） | **採用** | 本レビューの一次確認表（S1〜S4） |
| 2 | ID引用時に「WSTG v4.2」と版を明記 | **採用（必須）** | E2: 版でID範囲が異なる |
| 3 | INPV-20 / SESS-10,11 / BUSL-10 の使用 | **不採用**（latestのみ。使うなら「latest」明記） | S2/S3突合 |
| 4 | ODC 8分類名・IEEE 1044 type値の表記追加 | **保留** | 一次未確認（引用禁止リスト1,3） |
| 5 | 「Whittaker攻撃準拠」の主張 | **不採用** | 一次入手不可（E5） |
| 6 | BUSL-04/02/09由来の3項目追加 | **採用候補**（実装コスト小、根拠は一次確認済み） | ギャップ節 |
| 7 | confidence 0.9（カタログ由来）の維持 | **維持** | エラー推測に学術的実証が無い（E4）以上、実測1.0との区別は妥当 |
| 8 | 「エラー推測は実証済み技法」との営業的主張 | **不採用** | E4の否定的結果 |

## 検索方法（再現手順)

| 項目 | 内容 |
|---|---|
| WSTG版確認 | https://owasp.org/www-project-web-security-testing-guide/ で stable版番号・公開日を確認 |
| WSTG ID一覧 | 公式repo `OWASP/wstg` の `checklists/checklist.md`（raw.githubusercontent.com経由）。※`v4.2`タグ直下に同ファイルは無く404（チェックリストは後年追加のため）。v4.2該当範囲は stable目次（S3）との名称・順序突合で確定 |
| v4.2スポットチェック | v42個別ページ（S4）でページ内ID表記を直接確認 |
| 論文メタデータ | OpenAlex API（`api.openalex.org/works`）。ODCはDOI直接参照、error guessing / Whittaker は `search` / `title_and_abstract.search` + `cited_by_count:desc` |
| 試行して失敗した経路 | chillarege.com のODC概念ページ（本文リスト無し）、CUHK Lyu本 chap9.pdf（404）、`v4.2`タグのchecklist（404） |
| ツール実行回数 | 19回（上限20回以内）。実行時間 約8分（08:04開始） |

## 引用時の注意（このファイルの信頼度)

- WSTG表のv4.2在否は「stable目次の名称・順序一致」による判定。個別ページを全件開いての確認ではない（直接確認はBUSL-08のみ）。
- OpenAlexの被引用数は2026-07-28時点の値。
- 本レビューでabstract以上を読んだ文献はゼロ（ODCはabstract再構成まで）。「実証された知見」E1〜E2はOWASP公式サイトの記載そのものであり文献解釈を含まない。
