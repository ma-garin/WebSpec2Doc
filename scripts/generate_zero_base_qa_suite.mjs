#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const contractPath = path.join(repoRoot, "quality", "feature_contracts.yml");
const outDir = path.join(
  repoRoot,
  "docs",
  "sdlc",
  "40_test",
  "zero-base-20260726",
);
const contract = JSON.parse(fs.readFileSync(contractPath, "utf8"));
const features = contract.features;

fs.mkdirSync(outDir, { recursive: true });

const VERSION = "1.0";
const CREATED = "2026-07-26";
const SUT_URL = "http://127.0.0.1:8766/systems";
const DATA_URL = "http://127.0.0.1:8767/index.html";
const viewports = ["1920×1080", "1366×768"];
const themes = ["light", "dark"];
const uiStates = ["初期", "処理中", "成功", "空／異常"];
const operationModes = ["ルールベース", "LLM有効"];
const recoveryModes = ["一次失敗", "再試行／回復"];
const roles = ["未認証", "一般利用者", "管理者", "期限切れセッション"];
const dataProfiles = ["標準デモ", "不整合・欠損"];
const autorunStages = [
  "テスト目的",
  "テスト計画",
  "テストフィーチャ分析",
  "テスト観点分析",
  "テスト基本設計",
  "テスト詳細設計",
  "テストケース",
  "Playwright自動化",
];
const stageEvents = ["開始", "承認", "差戻し", "再開", "取消", "失敗回復"];
const journeys = [
  "URLから画面候補を発見する",
  "クロールして仕様書を生成する",
  "ログイン後の画面を取得する",
  "AutoRunを段階承認して完了する",
  "生成成果物を確認し根拠へ遡る",
  "差分を検出して重要度を判断する",
  "文書と実測の不一致を確認する",
  "探索記録からテスト資産を逆生成する",
  "受入証跡パックを出力する",
  "設定を変更し再実行へ反映する",
  "テナントを跨がず履歴を再利用する",
  "失敗箇所から部分再実行する",
];

const riskOrder = { critical: 4, high: 3, medium: 2, low: 1 };
const riskJa = {
  critical: "最重要",
  high: "高",
  medium: "中",
  low: "低",
};
const priorityFor = (risk) =>
  risk === "critical" ? "P0" : risk === "high" ? "P1" : risk === "medium" ? "P2" : "P3";
const esc = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
const idPart = (value) => {
  const raw = String(value ?? "none");
  const ascii = raw
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
  if (ascii) return ascii;
  let hash = 2166136261;
  for (const char of raw) {
    hash ^= char.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `u${(hash >>> 0).toString(36)}`;
};
const flatten = (key) => features.flatMap((feature) => feature[key] ?? []);
const countBy = (items, key) =>
  items.reduce((acc, item) => {
    const k = item[key] ?? "未設定";
    acc[k] = (acc[k] ?? 0) + 1;
    return acc;
  }, {});

const inventory = {
  features: features.length,
  symbols: flatten("symbols").length,
  uniqueSymbols: new Set(flatten("symbols")).size,
  failures: flatten("failure_modes").length,
  required: flatten("required_tests").length,
  outputs: flatten("outputs").length,
  persistence: flatten("persistence").length,
  uiRefs: flatten("ui_files").length,
  uniqueUiRefs: new Set(flatten("ui_files")).size,
  routeRefs: flatten("route_files").length,
  uniqueRouteRefs: new Set(flatten("route_files")).size,
  coreRefs: flatten("core_files").length,
  risk: countBy(features, "risk_level"),
};

function caseRow({
  id,
  feature,
  phase,
  category,
  quality,
  technique,
  condition,
  precondition,
  data,
  steps,
  expected,
  risk,
  automation,
  evidence,
  source,
}) {
  return {
    id,
    featureId: feature?.feature_id ?? "CROSS-CUT",
    featureName: feature?.name ?? "横断",
    phase,
    category,
    quality,
    technique,
    condition,
    precondition,
    data,
    steps,
    expected,
    risk: risk ?? feature?.risk_level ?? "high",
    priority: priorityFor(risk ?? feature?.risk_level ?? "high"),
    automation,
    evidence,
    source,
  };
}

function buildUnitCases() {
  const cases = [];
  for (const feature of features) {
    for (const symbol of feature.symbols ?? []) {
      cases.push(
        caseRow({
          id: `UT-${idPart(feature.feature_id)}-SYM-${idPart(symbol)}-N`,
          feature,
          phase: "単体",
          category: "シンボル契約",
          quality: "機能適合性／保守性",
          technique: "同値分割・ホワイトボックス",
          condition: `${symbol} の正常入力に対する公開契約`,
          precondition: "外部I/Oをテストダブルへ置換し、対象シンボルを単離する。",
          data: "最小の有効入力、代表的な通常入力。",
          steps: `1. ${symbol} を有効入力で呼ぶ。 2. 戻り値、状態変化、呼出し先を記録する。`,
          expected: "仕様化された型・値・副作用だけを返し、例外・隠れた外部送信・共有状態汚染がない。",
          automation: "必須",
          evidence: "アサーション、分岐カバレッジ、テストログ",
          source: `feature_contracts:${feature.feature_id}:symbols:${symbol}`,
        }),
        caseRow({
          id: `UT-${idPart(feature.feature_id)}-SYM-${idPart(symbol)}-I`,
          feature,
          phase: "単体",
          category: "シンボル防御",
          quality: "信頼性／安全性",
          technique: "境界値分析・エラー推測",
          condition: `${symbol} の欠損・型違反・境界外入力`,
          precondition: "対象シンボルを単離し、例外と副作用を観測可能にする。",
          data: "null相当、空、型違反、上限直前・上限・上限超過。",
          steps: `1. ${symbol} へ不正・境界入力を順に与える。 2. 例外、戻り値、副作用を確認する。`,
          expected: "契約化された失敗として制御され、秘密情報漏えい、破壊的副作用、未定義値の伝播がない。",
          automation: "必須",
          evidence: "例外アサーション、状態差分、ログ",
          source: `feature_contracts:${feature.feature_id}:symbols:${symbol}`,
        }),
      );
    }
    for (const failure of feature.failure_modes ?? []) {
      cases.push(
        caseRow({
          id: `UT-${idPart(feature.feature_id)}-FM-${idPart(failure)}`,
          feature,
          phase: "単体",
          category: "故障モード",
          quality: "信頼性／安全性",
          technique: "フォールトインジェクション",
          condition: `${failure} を局所的に発生させたときの封じ込め`,
          precondition: "対象依存先をテストダブル化し、指定故障を決定的に注入できる。",
          data: `故障プロファイル=${failure}`,
          steps: `1. ${failure} を注入する。 2. 対象ロジックを実行する。 3. 戻り値、例外、状態を確認する。`,
          expected: "失敗が分類され、上位層が処理可能な結果となる。部分データ破損、無限再試行、機密露出がない。",
          automation: "必須",
          evidence: "失敗分類、例外チェーン、状態差分",
          source: `feature_contracts:${feature.feature_id}:failure_modes:${failure}`,
        }),
      );
    }
    for (const output of feature.outputs ?? []) {
      cases.push(
        caseRow({
          id: `UT-${idPart(feature.feature_id)}-OUT-${idPart(output)}`,
          feature,
          phase: "単体",
          category: "成果物契約",
          quality: "機能完全性／データ品質",
          technique: "データフロー・スキーマ検証",
          condition: `${output} の生成契約と未定義値排除`,
          precondition: "固定入力と固定時刻で成果物生成器を単離する。",
          data: "完全データ、任意項目欠損データ、多言語文字列。",
          steps: `1. ${output} を生成する。 2. スキーマ、必須値、エスケープ、順序安定性を検証する。`,
          expected: "必須値が実値で埋まり、undefined、関数文字列、NaN、未エスケープ値が成果物へ混入しない。",
          automation: "必須",
          evidence: "スキーマ検証結果、ゴールデン差分",
          source: `feature_contracts:${feature.feature_id}:outputs:${output}`,
        }),
      );
    }
    for (const persistence of feature.persistence ?? []) {
      cases.push(
        caseRow({
          id: `UT-${idPart(feature.feature_id)}-PER-${idPart(persistence)}`,
          feature,
          phase: "単体",
          category: "永続化境界",
          quality: "信頼性／セキュリティ",
          technique: "境界・不変条件",
          condition: `${persistence} のパス・キー・原子性`,
          precondition: "一時領域を用い、他テナントと失敗注入用の境界を準備する。",
          data: "通常キー、衝突キー、 traversal文字列、中断書込み。",
          steps: `1. 保存する。 2. 再読込する。 3. 境界外指定と中断を注入する。`,
          expected: "同一データを復元でき、境界外アクセス・他テナント混入・半端なコミットが発生しない。",
          automation: "必須",
          evidence: "保存前後ハッシュ、パス検査、状態差分",
          source: `feature_contracts:${feature.feature_id}:persistence:${persistence}`,
        }),
      );
    }
    for (const required of feature.required_tests ?? []) {
      cases.push(
        caseRow({
          id: `UT-${idPart(feature.feature_id)}-REQ-${idPart(required)}`,
          feature,
          phase: "単体",
          category: "必須経路",
          quality: "機能正確性",
          technique: "条件網羅・デシジョンテーブル",
          condition: `${required} を成立させるドメイン規則`,
          precondition: "対象規則を外部依存から単離し、入力条件を直接制御できる。",
          data: `required_test=${required} の真・偽・境界条件`,
          steps: "1. 条件の成立・不成立を与える。 2. 判定結果と副作用を比較する。",
          expected: "各条件組合せが仕様どおりに分類され、未定義分岐と到達不能な必須分岐がない。",
          automation: "必須",
          evidence: "分岐表、MC/DCまたは条件カバレッジ",
          source: `feature_contracts:${feature.feature_id}:required_tests:${required}`,
        }),
      );
    }
  }
  return cases;
}

function buildIntegrationCases() {
  const cases = [];
  for (const feature of features) {
    for (const required of feature.required_tests ?? []) {
      for (const boundary of ["UI→Route", "Route→Core", "Core→Artifact"]) {
        cases.push(
          caseRow({
            id: `IT-${idPart(feature.feature_id)}-${idPart(required)}-${idPart(boundary)}`,
            feature,
            phase: "結合",
            category: "必須経路結合",
            quality: "機能正確性／互換性",
            technique: "インタフェース分析・デシジョンテーブル",
            condition: `${required} における ${boundary} の契約`,
            precondition: "下流の境界だけを実体または契約スタブとして接続する。",
            data: `${required} の代表入力、欠損入力、相関ID`,
            steps: `1. 上流から入力する。 2. ${boundary} の要求・応答・状態を捕捉する。 3. 相関を確認する。`,
            expected: "型、必須項目、ステータス、エラー分類、相関IDが境界間で一致し、情報欠落がない。",
            automation: "必須",
            evidence: "要求応答ログ、契約アサーション、相関ID",
            source: `feature_contracts:${feature.feature_id}:required_tests:${required}`,
          }),
        );
      }
    }
    for (const route of feature.route_files ?? []) {
      for (const protocol of ["正常要求", "入力違反", "未認証／権限不足", "下流障害"]) {
        cases.push(
          caseRow({
            id: `IT-${idPart(feature.feature_id)}-ROUTE-${idPart(route)}-${idPart(protocol)}`,
            feature,
            phase: "結合",
            category: "HTTP/API契約",
            quality: "機能適切性／セキュリティ",
            technique: "API契約・状態遷移",
            condition: `${route} への ${protocol}`,
            precondition: "Flaskアプリ、認証境界、下流サービスの観測点を準備する。",
            data: `${protocol} 用のHTTP要求、CSRF/Origin、セッション`,
            steps: "1. HTTP要求を送る。 2. ステータス、本文、ヘッダ、副作用を確認する。",
            expected: "HTTP意味論とアプリ契約が一致し、エラー時にHTML例外・秘密情報・不正な状態更新を返さない。",
            automation: "必須",
            evidence: "HTTPトランスクリプト、監査ログ",
            source: `feature_contracts:${feature.feature_id}:route_files:${route}`,
          }),
        );
      }
    }
    for (const output of feature.outputs ?? []) {
      for (const boundary of ["producer→store", "store→viewer"]) {
        cases.push(
          caseRow({
            id: `IT-${idPart(feature.feature_id)}-OUT-${idPart(output)}-${idPart(boundary)}`,
            feature,
            phase: "結合",
            category: "成果物パイプライン",
            quality: "機能完全性／データ品質",
            technique: "データフロー・ラウンドトリップ",
            condition: `${output} の ${boundary}`,
            precondition: "固定された生成入力と隔離済み保存領域を準備する。",
            data: "完全、部分、空、Unicode、長文の成果物データ。",
            steps: `1. ${output} を生成・保存する。 2. 表示側で再読込する。 3. 元データと比較する。`,
            expected: "値・型・順序・関連付けが保存前後で維持され、undefinedや実装関数表現を表示しない。",
            automation: "必須",
            evidence: "入出力ハッシュ、DOM/JSONアサーション",
            source: `feature_contracts:${feature.feature_id}:outputs:${output}`,
          }),
        );
      }
    }
    for (const persistence of feature.persistence ?? []) {
      for (const mode of ["commit/read", "rollback/retry", "tenant/concurrent"]) {
        cases.push(
          caseRow({
            id: `IT-${idPart(feature.feature_id)}-PER-${idPart(persistence)}-${idPart(mode)}`,
            feature,
            phase: "結合",
            category: "永続化結合",
            quality: "信頼性／セキュリティ",
            technique: "状態遷移・並行性",
            condition: `${persistence} の ${mode}`,
            precondition: "独立ワークスペース、競合セッション、故障注入点を準備する。",
            data: `${mode} の競合キー・中断時刻・テナントID`,
            steps: "1. 保存操作を開始する。 2. 競合または中断を発生させる。 3. 再読込と再試行を行う。",
            expected: "原子性・分離性・再実行安全性が保たれ、他テナントまたは半端な状態を観測しない。",
            automation: "必須",
            evidence: "トランザクションログ、保存状態差分",
            source: `feature_contracts:${feature.feature_id}:persistence:${persistence}`,
          }),
        );
      }
    }
  }
  return cases;
}

function buildSystemCases() {
  const cases = [];
  for (const feature of features) {
    for (const required of feature.required_tests ?? []) {
      for (const viewport of viewports) {
        for (const mode of operationModes) {
          cases.push(
            caseRow({
              id: `ST-${idPart(feature.feature_id)}-REQ-${idPart(required)}-${idPart(viewport)}-${idPart(mode)}`,
              feature,
              phase: "システム",
              category: "機能経路",
              quality: "機能適切性／相互作用能力",
              technique: "シナリオ・制約付き組合せ",
              condition: `${required} を ${viewport}・${mode} で完遂`,
              precondition: `SUT=${SUT_URL} が起動し、テストデータ=${DATA_URL} を参照できる。`,
              data: `viewport=${viewport}; mode=${mode}; feature=${feature.feature_id}`,
              steps: `1. 対象機能へ移動する。 2. ${required} の操作を行う。 3. 成果物から根拠へ遡る。`,
              expected: "利用者の目的が完了し、進捗・結果・次操作が一意に理解できる。機能契約と表示結果が一致する。",
              automation: "原則自動＋結果目視",
              evidence: "動画、ステップログ、スクリーンショット、成果物",
              source: `feature_contracts:${feature.feature_id}:required_tests:${required}`,
            }),
          );
        }
      }
    }
    for (const failure of feature.failure_modes ?? []) {
      for (const viewport of viewports) {
        for (const recovery of recoveryModes) {
          cases.push(
            caseRow({
              id: `ST-${idPart(feature.feature_id)}-FM-${idPart(failure)}-${idPart(viewport)}-${idPart(recovery)}`,
              feature,
              phase: "システム",
              category: "異常・回復",
              quality: "信頼性／安全性／相互作用能力",
              technique: "フォールトインジェクション・状態遷移",
              condition: `${failure} の ${recovery} を ${viewport} で観測`,
              precondition: "指定故障を安全に再現でき、処理前状態と証跡を保存済み。",
              data: `failure=${failure}; recovery=${recovery}; viewport=${viewport}`,
              steps: "1. 操作途中で故障を発生させる。 2. 表示と保存状態を確認する。 3. 再試行または再開する。",
              expected: "原因・影響・回復方法が表示され、既完了結果を失わず安全に再開できる。無限待機・無言失敗がない。",
              automation: "自動",
              evidence: "状態遷移ログ、障害前後スクリーンショット",
              source: `feature_contracts:${feature.feature_id}:failure_modes:${failure}`,
            }),
          );
        }
      }
    }
    for (const output of feature.outputs ?? []) {
      for (const viewport of viewports) {
        for (const theme of themes) {
          cases.push(
            caseRow({
              id: `ST-${idPart(feature.feature_id)}-OUT-${idPart(output)}-${idPart(viewport)}-${theme}`,
              feature,
              phase: "システム",
              category: "成果物表示",
              quality: "機能完全性／相互作用能力",
              technique: "視覚的回帰・オラクル比較",
              condition: `${output} を ${viewport}・${theme} で確認`,
              precondition: "完全・部分・空の成果物を生成済み。",
              data: `output=${output}; viewport=${viewport}; theme=${theme}`,
              steps: "1. 成果物一覧を開く。 2. 名称、要約、状態、操作を確認する。 3. 開いて根拠と突合する。",
              expected: "値が正しく表示され、undefined、関数文字列、重複、誤分類がない。重要成果物が先に発見できる。",
              automation: "自動＋目視",
              evidence: "DOMスナップショット、画面画像、リンク検証",
              source: `feature_contracts:${feature.feature_id}:outputs:${output}`,
            }),
          );
        }
      }
    }
    for (const uiFile of feature.ui_files ?? []) {
      for (const state of uiStates) {
        for (const viewport of viewports) {
          for (const theme of themes) {
            cases.push(
              caseRow({
                id: `ST-${idPart(feature.feature_id)}-UI-${idPart(uiFile)}-${idPart(state)}-${idPart(viewport)}-${theme}`,
                feature,
                phase: "システム",
                category: "画面状態・レイアウト",
                quality: "相互作用能力／柔軟性",
                technique: "状態モデル・ビジュアル回帰",
                condition: `${uiFile} の${state}状態を ${viewport}・${theme} で評価`,
                precondition: "対象状態へ決定的に遷移でき、基準画像とDOM観測を利用できる。",
                data: `state=${state}; viewport=${viewport}; theme=${theme}`,
                steps: "1. 指定状態へ遷移する。 2. 情報優先順位、余白、折返し、操作位置を確認する。 3. キーボード操作する。",
                expected: "主作業領域が利用可能幅を適切に使い、過大余白・切れ・重なり・水平スクロールがない。状態と次操作が明確。",
                automation: "画像差分＋目視",
                evidence: "全画面画像、DOM矩形、axe結果",
                source: `feature_contracts:${feature.feature_id}:ui_files:${uiFile}`,
              }),
            );
          }
        }
      }
    }
    for (const persistence of feature.persistence ?? []) {
      for (const mode of ["再表示整合", "テナント分離"]) {
        cases.push(
          caseRow({
            id: `ST-${idPart(feature.feature_id)}-PER-${idPart(persistence)}-${idPart(mode)}`,
            feature,
            phase: "システム",
            category: "永続状態",
            quality: "信頼性／セキュリティ",
            technique: "エンドツーエンド状態遷移",
            condition: `${persistence} の${mode}`,
            precondition: "異なるセッション／ワークスペースと保存前状態を準備する。",
            data: `persistence=${persistence}; mode=${mode}`,
            steps: "1. UIから保存する。 2. 再読込または別ワークスペースへ移動する。 3. 表示とAPIを確認する。",
            expected: "同一主体には正しく復元され、別主体には存在・内容とも漏えいしない。",
            automation: "自動",
            evidence: "画面、API応答、監査ログ",
            source: `feature_contracts:${feature.feature_id}:persistence:${persistence}`,
          }),
        );
      }
    }
  }
  const autorunFeature = features.find((feature) => feature.feature_id === "autorun_stage_approval") ??
    features.find((feature) => feature.feature_id === "autorun");
  for (const stage of autorunStages) {
    for (const event of stageEvents) {
      for (const viewport of viewports) {
        cases.push(
          caseRow({
            id: `ST-AUTORUN-${idPart(stage)}-${idPart(event)}-${idPart(viewport)}`,
            feature: autorunFeature,
            phase: "システム",
            category: "AutoRun時系列",
            quality: "信頼性／相互作用能力",
            technique: "状態遷移・N-switch",
            condition: `${stage} で${event}したときの遷移`,
            precondition: `対象ステージ直前まで完了し、${viewport}で表示する。`,
            data: `stage=${stage}; event=${event}; viewport=${viewport}`,
            steps: `1. ${stage} を開く。 2. ${event}を行う。 3. 前後ステージ、保存状態、操作可能性を確認する。`,
            expected: "許可遷移だけが成立し、承認前成果物は確定扱いにならない。再表示後も同一状態で、進捗と主操作が矛盾しない。",
            automation: "自動＋目視",
            evidence: "遷移表照合、画面、状態API",
            source: "src/autorun/stages.py:8-stage-model",
          }),
        );
      }
    }
  }
  for (const journey of journeys) {
    for (const viewport of viewports) {
      for (const role of roles) {
        for (const profile of dataProfiles) {
          cases.push(
            caseRow({
              id: `ST-XFLOW-${idPart(journey)}-${idPart(viewport)}-${idPart(role)}-${idPart(profile)}`,
              feature: null,
              phase: "システム",
              category: "横断ジャーニー",
              quality: "利用時品質につながる製品品質",
              technique: "多次元シナリオ・制約付き組合せ",
              condition: `${role}が${profile}で「${journey}」`,
              precondition: `SUTとテストサイトを起動し、role=${role}、viewport=${viewport}を設定する。`,
              data: `journey=${journey}; role=${role}; profile=${profile}; viewport=${viewport}`,
              steps: `1. ${journey}を開始する。 2. 中間判断を行う。 3. 成果物と根拠を確認する。 4. 再訪して継続する。`,
              expected: "権限内で目的を完遂でき、誤操作時も回復できる。画面間で用語・状態・件数・成果物が一致する。",
              risk: "critical",
              automation: "半自動",
              evidence: "通し動画、時系列ログ、成果物ハッシュ",
              source: "cross-functional-journey-model",
            }),
          );
        }
      }
    }
  }
  return cases;
}

function buildAcceptanceCases() {
  const cases = [];
  const personas = ["QAリード", "テスト設計者", "実行担当", "監査・検収担当", "システム管理者"];
  for (const journey of journeys) {
    for (const persona of personas) {
      for (const viewport of viewports) {
        cases.push(
          caseRow({
            id: `AT-GOAL-${idPart(journey)}-${idPart(persona)}-${idPart(viewport)}`,
            feature: null,
            phase: "受入",
            category: "業務目標",
            quality: "有益性／受容性",
            technique: "タスクベースUAT",
            condition: `${persona}が「${journey}」を初見で達成`,
            precondition: "役割に応じたアカウントのみ付与し、操作説明は製品内情報に限定する。",
            data: `persona=${persona}; viewport=${viewport}; source=${DATA_URL}`,
            steps: `1. 目的だけを提示する。 2. ${journey}を実施する。 3. 結果を説明し、確信度を回答する。`,
            expected: "重大支援なしに正しく完了し、結果と根拠を説明できる。完了率100%、致命的誤操作0。",
            risk: "high",
            automation: "人手",
            evidence: "観察票、所要時間、誤操作、発話、SUS補助値",
            source: "ISO/IEC 25019:2023 context-of-use",
          }),
        );
      }
    }
  }
  for (const feature of features) {
    cases.push(
      caseRow({
        id: `AT-FEATURE-${idPart(feature.feature_id)}`,
        feature,
        phase: "受入",
        category: "価値受入",
        quality: "適合性／有益性",
        technique: "例示による受入",
        condition: `${feature.name} が業務上の判断を改善する`,
        precondition: "代表利用者が期待する成果物と判断基準を合意済み。",
        data: `feature=${feature.feature_id}; source=${DATA_URL}`,
        steps: "1. 実データ相当で機能を利用する。 2. 成果物を用いて判断する。 3. 手作業との差を評価する。",
        expected: "意図した判断に必要な情報と根拠が揃い、重大な誤認を誘発せず、手戻りを増加させない。",
        automation: "人手",
        evidence: "受入署名、判断記録、差分",
        source: `feature_contracts:${feature.feature_id}`,
      }),
    );
  }
  const contexts = [
    "初回利用",
    "反復利用",
    "時間制約あり",
    "障害復旧中",
    "監査説明",
    "キーボードのみ",
    "低視力・拡大",
    "長時間セッション",
  ];
  const qiu = ["有益性", "リスク回避性", "受容性"];
  for (const quality of qiu) {
    for (const context of contexts) {
      cases.push(
        caseRow({
          id: `AT-QIU-${idPart(quality)}-${idPart(context)}`,
          feature: null,
          phase: "受入",
          category: "利用時品質",
          quality,
          technique: "文脈内評価",
          condition: `${context}における${quality}`,
          precondition: "利用者、目標、機器、環境、支援の有無を文脈票へ固定する。",
          data: `context=${context}; quality=${quality}`,
          steps: "1. 指定文脈で代表タスクを実施する。 2. 成功、時間、誤り、信頼、負担を測る。",
          expected: "合意した有効性・効率・満足・リスク・信頼の閾値を満たし、文脈固有の重大阻害がない。",
          risk: "high",
          automation: "人手",
          evidence: "文脈票、観察値、質問票、受入判断",
          source: "ISO/IEC 25019:2023",
        }),
      );
    }
  }
  for (const feature of features) {
    for (const output of feature.outputs ?? []) {
      cases.push(
        caseRow({
          id: `AT-OUT-${idPart(feature.feature_id)}-${idPart(output)}`,
          feature,
          phase: "受入",
          category: "成果物受入",
          quality: "有益性／信頼",
          technique: "専門家レビュー・サンプリング",
          condition: `${output} が第三者の検証判断に耐える`,
          precondition: "生成条件・版・根拠が固定され、レビュー担当者が原情報へアクセスできる。",
          data: `output=${output}; standard/edge/failure の代表サンプル`,
          steps: `1. ${output} を単独で読む。 2. 結論から根拠へ遡る。 3. 原情報と照合する。`,
          expected: "主語・対象・版・結論・根拠・限界が明示され、誤表示や根拠なき断定がなく、第三者が同じ判断を再現できる。",
          automation: "人手",
          evidence: "レビュー票、指摘、承認記録",
          source: `feature_contracts:${feature.feature_id}:outputs:${output}`,
        }),
      );
    }
  }
  return cases;
}

const phaseCases = {
  unit: buildUnitCases(),
  integration: buildIntegrationCases(),
  system: buildSystemCases(),
  acceptance: buildAcceptanceCases(),
};
const allCases = Object.values(phaseCases).flat();
const caseIdOccurrences = new Map();
for (const testCase of allCases) {
  const occurrence = (caseIdOccurrences.get(testCase.id) ?? 0) + 1;
  caseIdOccurrences.set(testCase.id, occurrence);
  if (occurrence > 1) testCase.id = `${testCase.id}-D${occurrence}`;
}
const allCaseIds = allCases.map((testCase) => testCase.id);
if (new Set(allCaseIds).size !== allCaseIds.length) {
  const seen = new Set();
  const duplicates = allCaseIds.filter((id) => seen.has(id) || !seen.add(id));
  throw new Error(`Duplicate case IDs: ${[...new Set(duplicates)].slice(0, 20).join(", ")}`);
}
for (const testCase of allCases) {
  for (const field of ["id", "condition", "steps", "expected", "source"]) {
    if (!String(testCase[field] ?? "").trim()) {
      throw new Error(`Empty ${field}: ${testCase.id}`);
    }
  }
}

const CSS = `
:root{--ink:#172033;--muted:#5c667a;--line:#dce2eb;--paper:#fff;--bg:#f4f6fa;--brand:#1456b8;--brand2:#eaf2ff;--good:#16794a;--warn:#9a5b00;--bad:#b42318;--shadow:0 10px 28px rgba(22,32,51,.08)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans JP",sans-serif;line-height:1.65}a{color:var(--brand)}.shell{display:grid;grid-template-columns:260px minmax(0,1fr);min-height:100vh}.side{position:sticky;top:0;height:100vh;overflow:auto;background:#0d1f3c;color:#fff;padding:28px 22px}.side h1{font-size:18px;margin:0 0 4px}.side p{color:#b8c7dd;font-size:12px;margin:0 0 24px}.side a{display:block;color:#dbe8fa;text-decoration:none;padding:9px 10px;border-radius:8px;margin:3px 0;font-size:13px}.side a:hover,.side a.active{background:#1d4f91;color:#fff}.main{min-width:0;padding:28px clamp(20px,3vw,52px) 80px}.page{max-width:1480px;margin:0 auto}.hero{background:linear-gradient(135deg,#0d2b55,#1763c5);color:#fff;padding:38px;border-radius:18px;box-shadow:var(--shadow)}.eyebrow{font-weight:800;letter-spacing:.08em;font-size:12px;text-transform:uppercase}.hero h2{font-size:clamp(28px,4vw,48px);line-height:1.18;margin:8px 0 12px}.hero p{max-width:900px;color:#dcecff}.badge{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:5px 10px;font-size:12px;font-weight:800;background:#fff;color:#154e98}.badge.wait{background:#fff1c7;color:#754400}.badge.risk-critical{background:#fee4e2;color:#912018}.badge.risk-high{background:#fff0d5;color:#7a4300}.badge.risk-medium{background:#e8f2ff;color:#174f93}.badge.risk-low{background:#e8f7ee;color:#17603c}.grid{display:grid;gap:16px}.stats{grid-template-columns:repeat(5,minmax(120px,1fr));margin:22px 0}.stat,.card,section{background:var(--paper);border:1px solid var(--line);border-radius:14px;box-shadow:0 4px 14px rgba(22,32,51,.04)}.stat{padding:18px}.stat strong{display:block;font-size:28px;line-height:1.2}.stat span{font-size:12px;color:var(--muted)}section{padding:26px;margin:20px 0}section h2{font-size:24px;margin:0 0 14px;color:#103f7d}section h3{font-size:18px;margin:24px 0 8px}.callout{border-left:4px solid var(--brand);background:var(--brand2);padding:14px 16px;border-radius:8px}.callout.warn{border-color:#e28a00;background:#fff8e8}.callout.bad{border-color:var(--bad);background:#fff0ef}.columns{grid-template-columns:repeat(2,minmax(0,1fr))}.four{grid-template-columns:repeat(4,minmax(0,1fr))}.card{padding:18px}.card h3{margin:0 0 8px;font-size:16px}.card p,.card li{font-size:13px}table{width:100%;border-collapse:separate;border-spacing:0;font-size:12px}th,td{border-right:1px solid var(--line);border-bottom:1px solid var(--line);padding:9px;vertical-align:top;background:#fff}th{position:sticky;top:0;z-index:1;background:#eef3fa;color:#30415c;text-align:left}tr:first-child th{border-top:1px solid var(--line)}th:first-child,td:first-child{border-left:1px solid var(--line)}tr:first-child th:first-child{border-top-left-radius:8px}tr:first-child th:last-child{border-top-right-radius:8px}.table-wrap{overflow:auto;max-height:70vh;border-radius:9px}.controls{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.controls input,.controls select{min-height:42px;border:1px solid #bfc9d8;border-radius:8px;padding:8px 12px;background:#fff}.controls input{min-width:min(480px,100%);flex:1}.metric-line{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.small{font-size:12px;color:var(--muted)}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}.flow{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;align-items:stretch}.flow div{position:relative;background:#eef4fd;border:1px solid #c9d8ec;border-radius:10px;padding:12px;text-align:center;font-size:12px;font-weight:700}.flow div:not(:last-child)::after{content:"→";position:absolute;right:-10px;top:35%;z-index:2;color:#3567a7}.toc a{display:block;margin:5px 0}.decision{border:2px solid #e0a400;background:#fffdf2}.footer{font-size:11px;color:var(--muted);margin-top:28px}.nowrap{white-space:nowrap}.case-id{font-weight:800;color:#154f96}.case-count{font-weight:800;color:var(--brand)}details{border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:10px 0;background:#fff}summary{cursor:pointer;font-weight:800}
@media(max-width:1000px){.shell{grid-template-columns:1fr}.side{position:relative;height:auto}.stats,.four{grid-template-columns:repeat(2,1fr)}.columns{grid-template-columns:1fr}.flow{grid-template-columns:repeat(3,1fr)}.main{padding:18px}.hero{padding:24px}}
@media(max-width:620px){.stats,.four,.flow{grid-template-columns:1fr}.hero h2{font-size:28px}}
@media print{body{background:#fff}.shell{display:block}.side,.controls{display:none}.main{padding:0}.page{max-width:none}.hero,section,.stat,.card{box-shadow:none;break-inside:avoid}.hero{color:#000;background:#fff;border:2px solid #000}.hero p{color:#333}.table-wrap{max-height:none;overflow:visible}th{position:static}a{color:#000;text-decoration:none}}
`;

const navItems = [
  ["index.html", "総合索引・マスタープラン", "index"],
  ["01_unit.html", `単体 — ${phaseCases.unit.length.toLocaleString()}件`, "unit"],
  ["02_integration.html", `結合 — ${phaseCases.integration.length.toLocaleString()}件`, "integration"],
  ["03_system.html", `システム — ${phaseCases.system.length.toLocaleString()}件`, "system"],
  ["04_acceptance.html", `受入 — ${phaseCases.acceptance.length.toLocaleString()}件`, "acceptance"],
  ["05_traceability.html", "トレーサビリティ・リスク", "trace"],
];

function layout({ title, active, hero, body, script = "" }) {
  const nav = navItems
    .map(([href, label, key]) => `<a class="${key === active ? "active" : ""}" href="${href}">${esc(label)}</a>`)
    .join("");
  return `<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)} | WebSpec2Doc 第三者検証</title><style>${CSS}</style></head>
<body><div class="shell"><aside class="side"><h1>WebSpec2Doc QA</h1><p>第三者検証・承認前テストウェア<br>版 ${VERSION} / ${CREATED}</p>${nav}</aside>
<main class="main"><div class="page">${hero}${body}<p class="footer">文書ID: WS2D-ZBQA-${active.toUpperCase()} / 状態: 承認待ち / テスト未実行 / 生成元: quality/feature_contracts.yml</p></div></main></div>${script}</body></html>`;
}

function hero(title, subtitle, count) {
  return `<header class="hero"><span class="badge wait">承認待ち・未実行</span><div class="eyebrow">Independent Verification Testware</div>
<h2>${esc(title)}</h2><p>${esc(subtitle)}</p>
${count == null ? "" : `<div class="badge">${count.toLocaleString()} concrete cases</div>`}</header>`;
}

function testArchitecture() {
  return `<div class="grid four">
  <div class="card"><h3>点</h3><p>局所欠陥を狙う。エラー推測、探索、静的レビュー。</p></div>
  <div class="card"><h3>線</h3><p>連続領域を切る。同値分割、境界値、負荷の変曲点。</p></div>
  <div class="card"><h3>面</h3><p>論理条件を組む。ドメイン分析、決定表、原因結果。</p></div>
  <div class="card"><h3>立体</h3><p>順序なし因子を扱う。HAYST、直交表、pairwise。</p></div>
  <div class="card"><h3>時間</h3><p>状態と履歴を追う。状態遷移、N-switch、並行性。</p></div>
  <div class="card"><h3>多次元</h3><p>利用文脈を通す。シナリオ、UAT、統計的サンプリング。</p></div>
  </div>`;
}

function phaseSummaryCards(cases) {
  const categories = countBy(cases, "category");
  return `<div class="grid four">${Object.entries(categories)
    .map(([name, count]) => `<div class="card"><h3>${esc(name)}</h3><strong>${count.toLocaleString()}</strong><p>導出済み具体ケース</p></div>`)
    .join("")}</div>`;
}

function caseTable(cases) {
  const rows = cases
    .map(
      (testCase) => `<tr data-case-row data-search="${esc(
        Object.values(testCase).join(" ").toLowerCase(),
      )}" data-risk="${esc(testCase.risk)}" data-category="${esc(testCase.category)}">
<td class="case-id mono">${esc(testCase.id)}</td>
<td><span class="badge risk-${esc(testCase.risk)}">${esc(testCase.priority)} ${esc(riskJa[testCase.risk])}</span></td>
<td><strong>${esc(testCase.featureId)}</strong><br>${esc(testCase.featureName)}</td>
<td>${esc(testCase.category)}<br><span class="small">${esc(testCase.quality)}</span></td>
<td>${esc(testCase.condition)}<br><span class="small">技法: ${esc(testCase.technique)}</span></td>
<td><strong>前提</strong> ${esc(testCase.precondition)}<br><strong>データ</strong> ${esc(testCase.data)}</td>
<td>${esc(testCase.steps)}</td>
<td>${esc(testCase.expected)}</td>
<td>${esc(testCase.automation)}<br><span class="small">${esc(testCase.evidence)}</span></td>
<td class="mono small">${esc(testCase.source)}</td>
</tr>`,
    )
    .join("");
  return `<div class="controls"><input data-case-search type="search" placeholder="ID・機能・観点・期待結果を検索">
<select data-risk-filter><option value="">全リスク</option><option value="critical">P0 最重要</option><option value="high">P1 高</option><option value="medium">P2 中</option><option value="low">P3 低</option></select>
<select data-category-filter><option value="">全カテゴリ</option>${[...new Set(cases.map((c) => c.category))]
    .map((name) => `<option>${esc(name)}</option>`)
    .join("")}</select>
<span class="small">表示 <strong data-visible-count>${cases.length.toLocaleString()}</strong> / ${cases.length.toLocaleString()}件</span></div>
<div class="table-wrap"><table><thead><tr><th>ID</th><th>優先度</th><th>対象</th><th>分類</th><th>テスト条件</th><th>前提・データ</th><th>手順</th><th>期待結果</th><th>実装・証跡</th><th>導出元</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

const filterScript = `<script>
const search=document.querySelector("[data-case-search]"),risk=document.querySelector("[data-risk-filter]"),category=document.querySelector("[data-category-filter]"),rows=[...document.querySelectorAll("[data-case-row]")],count=document.querySelector("[data-visible-count]");
function filter(){const q=(search?.value||"").trim().toLowerCase(),r=risk?.value||"",c=category?.value||"";let visible=0;for(const row of rows){const ok=(!q||row.dataset.search.includes(q))&&(!r||row.dataset.risk===r)&&(!c||row.dataset.category===c);row.hidden=!ok;if(ok)visible++}if(count)count.textContent=visible.toLocaleString()}
search?.addEventListener("input",filter);risk?.addEventListener("change",filter);category?.addEventListener("change",filter);
</script>`;

function phasePage({ key, title, subtitle, cases, plan, analysis, design, entry, exit, environment }) {
  return layout({
    title,
    active: key,
    hero: hero(title, subtitle, cases.length),
    body: `
<div class="grid stats"><div class="stat"><strong>${cases.length.toLocaleString()}</strong><span>具体ケース</span></div>
<div class="stat"><strong>${Object.keys(countBy(cases, "category")).length}</strong><span>ケース群</span></div>
<div class="stat"><strong>${new Set(cases.map((c)=>c.featureId)).size}</strong><span>対象ID</span></div>
<div class="stat"><strong>${cases.filter((c)=>c.priority==="P0").length.toLocaleString()}</strong><span>P0ケース</span></div>
<div class="stat"><strong>0</strong><span>実行済み（承認前）</span></div></div>
<section id="plan"><h2>1. テスト計画・方針</h2>${plan}
<div class="grid columns"><div class="card"><h3>開始基準</h3>${entry}</div><div class="card"><h3>終了基準</h3>${exit}</div></div>
<h3>環境・データ</h3>${environment}</section>
<section id="analysis"><h2>2. テスト分析</h2>${analysis}<div class="callout warn"><strong>分析上の原則:</strong> 要件文書の「33機能」「ISO 25010の8特性」「過去の合格件数」は現行品質契約と不一致のため、合格根拠に使用しない。40機能の機械可読契約と実行時観測を正とする。</div></section>
<section id="design"><h2>3. テストアーキテクチャ・設計</h2>${design}${testArchitecture()}<h3>ケース群と厚み</h3>${phaseSummaryCards(cases)}</section>
<section id="cases"><h2>4. 具体的テストケース</h2><p>全件に対象、テスト条件、前提、データ、手順、期待結果、証跡、導出元を付与した。検索・絞込みが可能。</p>${caseTable(cases)}</section>`,
    script: filterScript,
  });
}

const unitHtml = phasePage({
  key: "unit",
  title: "単体テスト仕様",
  subtitle: "関数・クラス・生成器・永続化境界を単離し、内部品質と局所的な機能契約を証明する。",
  cases: phaseCases.unit,
  plan: `<p><strong>目的:</strong> 164シンボル参照と40機能のドメイン規則を最小単位で検証し、欠陥を結合前に局所化する。</p>
  <p><strong>範囲:</strong> src/、web/の純粋ロジック、検証、変換、シリアライズ、エラー分類、パス・キー生成。UI描画と実ネットワークは対象外。</p>
  <p><strong>方針:</strong> 高リスクは正常・不正・故障注入・不変条件を必須化。行カバレッジだけでなく分岐、条件、ミューテーション生存を評価する。</p>`,
  entry: "<ul><li>対象シンボルと契約が特定済み</li><li>外部依存を制御可能</li><li>期待結果のオラクルがレビュー済み</li></ul>",
  exit: "<ul><li>P0/P1 100%実行・合格</li><li>全体合格率99%以上</li><li>変更コード分岐100%、全体分岐80%以上</li><li>重大ミューテーション生存0</li></ul>",
  environment: `<p>Pythonのプロジェクト固定版、pytest、隔離一時領域、固定時刻・乱数、ネットワーク遮断。テストデータは最小有効値、境界値、欠損、型違反、Unicode、パストラバーサルを使用する。</p>`,
  analysis: `<p>入力領域、出力スキーマ、副作用、例外、状態不変条件、セキュリティ境界をテスト条件へ分解した。母数はシンボル参照164×正常/不正、故障モード187、成果物128、永続化54、必須経路150。</p>`,
  design: `<p>同値分割・境界値分析・デシジョンテーブル・ホワイトボックス条件網羅・フォールトインジェクション・プロパティベース・ミューテーションを使い分ける。テストダブルは観測性・制御性のために使用し、実装詳細への過結合を避ける。</p>`,
});

const integrationHtml = phasePage({
  key: "integration",
  title: "結合テスト仕様",
  subtitle: "UI、HTTPルート、コア、永続化、成果物表示の接続契約と状態の受渡しを検証する。",
  cases: phaseCases.integration,
  plan: `<p><strong>目的:</strong> コンポーネント単体では見えない型・状態・認証・エラー・データ欠落を境界ごとに検出する。</p>
  <p><strong>範囲:</strong> UI→Route、Route→Core、Core→Artifact、33ルート参照、成果物パイプライン、永続化とテナント境界。実ブラウザの視覚品質はシステムへ委譲する。</p>
  <p><strong>方針:</strong> 各必須経路を3境界で追跡し、正常、入力違反、権限不足、下流障害、再試行、並行性を検証する。</p>`,
  entry: "<ul><li>関連単体P0/P1合格</li><li>契約・スキーマ・エラー分類が固定</li><li>テスト用ワークスペースを分離</li></ul>",
  exit: "<ul><li>P0/P1 100%実行・合格</li><li>契約違反0、未分類5xx 0</li><li>テナント越境0、未説明のデータ損失0</li><li>再試行非冪等欠陥0</li></ul>",
  environment: `<p>Flask test clientまたは隔離サーバ、実ファイル/DBの一時領域、契約スタブ、複数セッション。HTTP要求、CSRF/Origin、期限切れセッション、競合書込み、部分成果物を使用する。</p>`,
  analysis: `<p>150必須経路を3つの接続点へ展開し、33ルート参照×4プロトコル状態、128成果物×2受渡し、54永続化先×3状態として分析した。重点は認証・テナント・エラー意味論・ラウンドトリップ整合性。</p>`,
  design: `<p>インタフェース分析、API契約、データフロー、ラウンドトリップ、状態遷移、並行性、フォールトインジェクションを採用。境界ごとに相関IDと前後ハッシュを証跡化する。</p>`,
});

const systemHtml = phasePage({
  key: "system",
  title: "システムテスト仕様",
  subtitle: "40機能を稼働形態どおりに通し、機能・非機能・表示・状態・証跡を横断して評価する。",
  cases: phaseCases.system,
  plan: `<p><strong>目的:</strong> ${SUT_URL} を完成システムとして扱い、${DATA_URL} を統制テストデータに、利用者が価値を受け取れることと重大リスクが制御されることを証明する。</p>
  <p><strong>範囲:</strong> 全40機能、正常/異常/回復、成果物128種、49 UI参照、2解像度、light/dark、AutoRun 8段階、認証・テナント・横断ジャーニー、性能・互換・a11y・セキュリティ・信頼性。</p>
  <p><strong>方針:</strong> 機能別の縦割りだけでなく、画面×状態×データ×役割×解像度×操作経路を制約付きで横断する。スクリーンショット例の表示崩れは既知の種として扱い、同型欠陥を全画面から探索する。</p>`,
  entry: "<ul><li>対象版・構成・テストサイト版を凍結</li><li>単体/結合P0/P1合格</li><li>証跡取得と故障注入が利用可能</li><li>実行による外部破壊がないことを確認</li></ul>",
  exit: "<ul><li>P0/P1 100%実行・合格、P2 98%以上</li><li>Sev1/Sev2未解決0</li><li>要件・リスク・品質特性の追跡率100%</li><li>未説明skip/flaky/console error 0</li><li>性能・a11y・セキュリティ閾値合格</li></ul>",
  environment: `<p>SUT ${SUT_URL}、データ ${DATA_URL}、Chromium、1920×1080 / 1366×768、light/dark。必要に応じFirefox/WebKitは互換性主張の確認用に追加する。ネットワーク遅延・切断、LLM無効/有効、認証4状態、異なるワークスペースを制御する。</p>`,
  analysis: `<p>150必須経路、187故障モード、128成果物、49 UI参照、54永続化先、AutoRun 8段階、12横断ジャーニーを分析単位とした。特に「undefined/関数文字列」「成果物の優先順位」「広画面の過大余白」は、機能正確性・情報設計・相互作用能力・柔軟性にまたがる横断リスクとして定義した。</p>`,
  design: `<p>機能経路600件、異常回復748件、成果物表示512件、画面状態784件、永続状態108件、AutoRun時系列96件、横断ジャーニー192件。全直積は行わず、故障影響と利用文脈を保った制約付き組合せを採用する。</p>`,
});

const acceptanceHtml = phasePage({
  key: "acceptance",
  title: "受入テスト仕様",
  subtitle: "指定された利用文脈で、業務上の有益性、リスク回避性、受容性と検収可能性を判断する。",
  cases: phaseCases.acceptance,
  plan: `<p><strong>目的:</strong> 機能が動くことではなく、QA担当者・監査担当者・管理者が正しい判断を再現可能な根拠付きで行えることを受け入れる。</p>
  <p><strong>範囲:</strong> 12業務目標×5ペルソナ×2解像度、40機能の価値、ISO/IEC 25019の3特性×8文脈、128成果物の第三者レビュー。</p>
  <p><strong>方針:</strong> 初見タスク、反復タスク、障害時、監査説明、アクセシビリティ文脈を分離し、完了率・時間・誤操作・信頼・満足・重大リスクを測る。</p>`,
  entry: "<ul><li>システムテスト終了基準を満たす</li><li>代表利用者と受入権限者を確保</li><li>目的・文脈・閾値を事前合意</li><li>既知制約を開示</li></ul>",
  exit: "<ul><li>重要業務タスク完了率100%</li><li>重大誤判断・データ越境・証跡欠落0</li><li>成果物サンプルの再現可能率100%</li><li>PO/受入権限者が制約込みで署名</li></ul>",
  environment: `<p>代表利用者自身の通常端末または1920×1080 / 1366×768、支援技術を含む指定文脈。テストサイト ${DATA_URL} の標準・不整合・欠損を用い、操作説明は原則として製品内情報のみ。</p>`,
  analysis: `<p>直接利用者だけでなく、生成物を検収・監査する間接利用者を含めた。品質利用時モデルは2023年版の有益性、リスク回避性、受容性を採用し、文脈を前提条件として固定する。</p>`,
  design: `<p>タスクベースUAT、文脈内観察、専門家レビュー、証拠サンプリング、質問票を組み合わせる。自動テスト結果は受入オラクルの補助であり、人間の価値判断を代替しない。</p>`,
});

const riskRows = [
  ["R-01","根拠なき仕様・ケース生成","critical","成果物の誤判断、監査不能","evidence-only、原情報リンク、サンプル照合"],
  ["R-02","SSRF・破壊的クロール・外部送信","critical","情報漏えい、対象破壊","localhost/URL安全性、送信ゲート、非破壊データ"],
  ["R-03","認証情報・トークンの保持/露出","critical","アカウント侵害","即時破棄、ログマスキング、スコープ検証"],
  ["R-04","テナント／ワークスペース越境","critical","機密データ漏えい","主体×資源×操作、競合・履歴・出力を横断"],
  ["R-05","AutoRun承認状態の矛盾","critical","未承認成果物の確定、手戻り","8段階状態モデル、N-switch、再開・差戻し"],
  ["R-06","部分失敗・再試行による破損","high","成果物欠損、重複、無限待機","故障注入、冪等性、チェックポイント"],
  ["R-07","仕様文書と現行実装のドリフト","high","誤スコープ、誤合格","品質契約40機能を正本、差分台帳"],
  ["R-08","undefined・関数表現・件数不整合","high","結果解釈不能、信頼低下","出力スキーマ、ラウンドトリップ、全成果物表示"],
  ["R-09","過大余白・切れ・情報優先順位不良","high","作業効率・受容性低下","49 UI参照×状態×解像度×テーマ"],
  ["R-10","LLM変動・プロンプト注入・捏造","critical","誤成果物、外部漏えい","ルール/LLM比較、非信頼境界、再現性"],
  ["R-11","負荷・長時間実行・資源枯渇","high","タイムアウト、データ損失","容量境界、持久、キャンセル、回復"],
  ["R-12","観測不能・証跡欠落","high","不具合再現不能、検収不能","相関ID、構造化ログ、動画・ハッシュ"],
];

const standardsRows = [
  ["ISTQB CTFL v4.0.1","テスト活動、レベル/タイプ、リスク、監視・制御、構成・欠陥管理","用語と活動を整合。ISTQB自体は計画書様式を規定しない。"],
  ["ISO/IEC/IEEE 29119-2:2021","組織・管理・動的テストプロセス","計画→監視/制御→完了、分析→設計→実装→実行を採用。"],
  ["ISO/IEC/IEEE 29119-3:2021","テスト文書テンプレート","識別、文脈、リスク、戦略、環境、要員、日程、完了基準、成果物を収録。"],
  ["ISO/IEC/IEEE 29119-4:2021","テスト設計技法","仕様ベース、構造ベース、経験ベースの技法選択根拠を保持。"],
  ["ISO/IEC 25010:2023","製品品質9特性","機能適合性、性能効率性、互換性、相互作用能力、信頼性、セキュリティ、保守性、柔軟性、安全性。"],
  ["ISO/IEC 25019:2023","利用時品質3特性","有益性、リスク回避性、受容性を指定利用文脈で評価。"],
  ["ISO/IEC 25012:2008","データ品質モデル","生成仕様、証跡、トレーサビリティの正確性・完全性・一貫性を評価。"],
  ["ASTER テスト設計コンテスト'26","要求分析、アーキテクチャ、詳細設計、実装と一貫性","観点導出、関係、厚み、スコープ、ケース構造、カバレッジ説明を成果物化。"],
];

const masterHtml = layout({
  title: "ゼロベース第三者検証 マスターテスト計画",
  active: "index",
  hero: hero(
    "ゼロベース第三者検証",
    "WebSpec2Docの単体・結合・システム・受入を、内部品質・外部品質・利用時品質まで一貫したモデルで計画・分析・設計・具体化した承認前テストウェア。",
    allCases.length,
  ),
  body: `
<div class="grid stats"><div class="stat"><strong>${inventory.features}</strong><span>対象機能</span></div>
<div class="stat"><strong>${allCases.length.toLocaleString()}</strong><span>全具体ケース</span></div>
<div class="stat"><strong>${phaseCases.system.length.toLocaleString()}</strong><span>システムケース</span></div>
<div class="stat"><strong>${inventory.failures}</strong><span>故障モード</span></div>
<div class="stat"><strong>0</strong><span>実行済み（承認前）</span></div></div>
<section class="decision"><h2>承認依頼</h2><p>本成果物はテスト実行前のベースライン候補である。次の5点を承認後に、環境固定、ケースレビュー、実装、実行へ進む。</p>
<ol><li>対象を品質契約の全40機能とする。</li><li>テストデータとして ${esc(DATA_URL)} を使用し、外部サイトへ破壊的操作を行わない。</li><li>単体847・結合1,000・システム3,040・受入312、合計5,199件を初期フルスコープとする。</li><li>リスクベースでP0/P1を先行し、合格基準を緩和しない。</li><li>実行で得た事実と計画上の仮説を明確に分離する。</li></ol>
<div class="callout bad"><strong>重要:</strong> 現時点ではテストを実行していない。「passed」「準拠済み」「品質保証済み」とは判定しない。</div></section>
<section><h2>1. 文書体系と開発プロセス</h2>
<div class="flow"><div>テストベース</div><div>要求分析</div><div>アーキテクチャ</div><div>詳細設計</div><div>実装可能ケース</div><div>承認・実行</div></div>
<p>ASTERの成果物0〜4に相当する全体像、要求分析、アーキテクチャ、詳細設計、実装可能ケースを本HTML群で相互追跡する。フェーズ別ページは、ISO 29119-3の計画情報と、分析・設計・ケースを一体化している。</p>
<table><thead><tr><th>成果物</th><th>計画</th><th>分析</th><th>設計</th><th>ケース</th></tr></thead><tbody>
${navItems.slice(1,5).map(([href,label])=>`<tr><td><a href="${href}">${esc(label)}</a></td><td>目的・範囲・開始/終了</td><td>条件・リスク・母数</td><td>技法・構造・厚み</td><td>全件一覧・導出元</td></tr>`).join("")}
</tbody></table></section>
<section><h2>2. テスト対象・テストベース</h2>
<div class="grid columns"><div class="card"><h3>対象</h3><ul><li>SUT: ${esc(SUT_URL)}</li><li>テストデータ: ${esc(DATA_URL)}</li><li>品質契約: 40機能（critical 10 / high 15 / medium 13 / low 2）</li><li>参照母数: symbol ${inventory.symbols}, failure ${inventory.failures}, required ${inventory.required}, output ${inventory.outputs}, persistence ${inventory.persistence}</li></ul></div>
<div class="card"><h3>優先順位</h3><p>安全性・秘密性・テナント分離・証跡真正性・承認状態をP0、主要業務フロー・回復・表示判断をP1、補助機能をP2/P3とする。発生確率だけでなく影響、検出困難性、回復困難性を考慮する。</p></div></div>
<div class="callout warn"><strong>テストベースのドリフト:</strong> 要件定義は33機能、非機能要件は旧ISO 25010の8特性、既存計画は19機能を記載している。一方、現行品質契約は40機能である。本計画は40機能を基準にし、文書差異自体を品質リスクR-07として扱う。</div></section>
<section><h2>3. 準拠モデル</h2><table><thead><tr><th>規格・知識体系</th><th>採用範囲</th><th>本書での扱い</th></tr></thead><tbody>
${standardsRows.map((row)=>`<tr>${row.map((cell)=>`<td>${esc(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table>
<p class="small">本書は規格の認証取得や完全適合を宣言するものではない。公開された最新版情報とプロジェクトへのテーラリング方針を明示する。</p></section>
<section><h2>4. 品質モデル — 内部・外部・利用時</h2>
<table><thead><tr><th>品質層</th><th>定義</th><th>主な観測対象</th><th>主要フェーズ</th></tr></thead><tbody>
<tr><td><strong>内部品質</strong></td><td>実行せずに観測できるソース、構造、依存、テスト容易性、静的安全性。</td><td>複雑度、重複、依存方向、秘密情報、脆弱性、スキーマ、保守性。</td><td>静的レビュー・単体</td></tr>
<tr><td><strong>外部品質</strong></td><td>実行中の製品が示す振る舞いと品質特性。</td><td>ISO 25010:2023の9特性、API、画面、性能、回復、互換、セキュリティ。</td><td>単体・結合・システム</td></tr>
<tr><td><strong>利用時品質</strong></td><td>指定利用文脈で利用者・組織・社会にもたらす結果。</td><td>ISO 25019:2023の有益性、リスク回避性、受容性。</td><td>システム・受入</td></tr>
</tbody></table>
<h3>製品品質9特性</h3><p>機能適合性、性能効率性、互換性、相互作用能力、信頼性、セキュリティ、保守性、柔軟性、安全性を全体マトリクスに置く。UIの過大余白は装飾上の好みではなく、相互作用能力・柔軟性・効率に影響する外部品質条件である。</p>
<h3>指定利用文脈</h3><p>利用者（QAリード、設計者、実行者、監査者、管理者）×目標（12業務ジャーニー）×機器（2解像度・キーボード/支援技術）×環境（初回、反復、時間制約、障害、監査、長時間）を固定して評価する。</p></section>
<section><h2>5. テスト戦略 — 点・線・面・立体・時間・多次元</h2>${testArchitecture()}
<p>各層を独立した流行語として並べず、点で得た欠陥仮説を線の境界、面の論理、立体の因子、時間の状態、多次元の利用文脈へ拡張する。逆に受入で見つかった問題を、下位レベルの再発防止ケースへ還流する。</p></section>
<section><h2>6. フェーズ別規模と責務</h2><table><thead><tr><th>フェーズ</th><th>具体ケース</th><th>主目的</th><th>主オラクル</th><th>実行責任</th></tr></thead><tbody>
<tr><td>単体</td><td>${phaseCases.unit.length.toLocaleString()}</td><td>局所契約・分岐・不変条件</td><td>関数契約、プロパティ、スキーマ</td><td>開発＋独立QAレビュー</td></tr>
<tr><td>結合</td><td>${phaseCases.integration.length.toLocaleString()}</td><td>接続・状態受渡し・分離</td><td>API契約、データ差分、監査ログ</td><td>QA自動化</td></tr>
<tr><td>システム</td><td>${phaseCases.system.length.toLocaleString()}</td><td>完成系の機能・非機能・横断品質</td><td>要求、画面、成果物、計測値</td><td>独立検証チーム</td></tr>
<tr><td>受入</td><td>${phaseCases.acceptance.length.toLocaleString()}</td><td>業務価値・リスク・受容性</td><td>利用者判断、受入基準</td><td>PO/利用者＋第三者立会</td></tr>
</tbody></table></section>
<section><h2>7. リスク登録簿</h2><table><thead><tr><th>ID</th><th>リスク</th><th>水準</th><th>影響</th><th>テスト対策</th></tr></thead><tbody>
${riskRows.map((row)=>`<tr><td class="mono">${row[0]}</td><td>${esc(row[1])}</td><td><span class="badge risk-${row[2]}">${esc(riskJa[row[2]])}</span></td><td>${esc(row[3])}</td><td>${esc(row[4])}</td></tr>`).join("")}
</tbody></table></section>
<section><h2>8. テストデータ設計</h2><div class="grid four">
${[
["TD-0 標準","8767の正常到達・代表入力"],
["TD-1 不整合","文書/実装差、欠損画面、矛盾件数"],
["TD-2 境界","空、最小、最大±1、長文、Unicode"],
["TD-3 認証","未認証、一般、管理、期限切れ"],
["TD-4 障害","timeout、切断、5xx、部分失敗"],
["TD-5 攻撃","SSRF、XSS、注入、traversal、prompt injection"],
["TD-6 容量","多数画面、長時間、巨大成果物、並行実行"],
["TD-7 利用文脈","拡大、キーボード、初見、監査、復旧"],
].map(([name,desc])=>`<div class="card"><h3>${esc(name)}</h3><p>${esc(desc)}</p></div>`).join("")}</div>
<p>資格情報・個人情報は合成し、実データを保存しない。各ケースは入力データ版と生成物ハッシュを証跡へ記録する。</p></section>
<section><h2>9. 環境・構成・証跡</h2><ul><li>SUT版、commit、OS、Python、依存ロック、ブラウザ版、環境変数（秘密値を除く）を実行単位で固定する。</li><li>証跡はケースID、時刻、操作者、入力版、要求/応答、ログ、画面、成果物ハッシュ、判定、欠陥IDを持つ。</li><li>解像度は1920×1080と1366×768を必須とし、主作業領域の利用率、過大余白、切れ、重なり、可読行長を測る。</li><li>テストデータサイトへの操作は非破壊とし、送信が必要なケースは合成データと隔離環境のみで実施する。</li></ul></section>
<section><h2>10. 組織・日程・監視</h2><table><thead><tr><th>ゲート</th><th>活動</th><th>完了条件</th></tr></thead><tbody>
<tr><td>G0 承認</td><td>本計画、スコープ、リスク、閾値をレビュー</td><td>承認者、版、条件を記録</td></tr>
<tr><td>G1 準備</td><td>環境・データ・自動化・証跡を固定</td><td>再現性スモーク合格</td></tr>
<tr><td>G2 内部</td><td>静的、単体、結合を実行</td><td>P0/P1合格、重大欠陥0</td></tr>
<tr><td>G3 外部</td><td>システム機能・非機能・回帰を実行</td><td>システム終了基準合格</td></tr>
<tr><td>G4 利用時</td><td>UAT、文脈内評価、成果物レビュー</td><td>受入署名</td></tr>
<tr><td>G5 完了</td><td>残存リスク、逸脱、メトリクスを報告</td><td>サマリ承認、証跡保全</td></tr>
</tbody></table>
<p><strong>監視指標:</strong> 計画/実行/合格/阻害件数、要件・リスク・品質特性カバレッジ、欠陥密度、再オープン、漏出、flaky、平均復旧時間、タスク完了率、成果物再現率。ケース消化率だけで品質を判定しない。</p></section>
<section><h2>11. 中断・再開・完了基準</h2><div class="grid columns"><div class="card"><h3>中断</h3><ul><li>SUT/データ版を特定できない</li><li>破壊的送信または情報漏えいの兆候</li><li>Sev1または後続判定を無効化するSev2</li><li>証跡がケースへ結び付かない</li><li>環境不安定で再現性が得られない</li></ul></div>
<div class="card"><h3>再開・完了</h3><ul><li>原因と影響ケースを特定し、環境を再固定</li><li>P0/P1 100%実行・合格</li><li>Sev1/2未解決0、逸脱は承認済み</li><li>トレーサビリティ100%、未説明skip 0</li><li>受入権限者が残存リスク込みで署名</li></ul></div></div></section>
<section><h2>12. 参照情報</h2><ul>
<li><a href="https://www.istqb.org/certifications/certified-tester-foundation-level-ctfl-v4-0/">ISTQB CTFL v4.0.1</a></li>
<li><a href="https://www.iso.org/standard/79428.html">ISO/IEC/IEEE 29119-2:2021</a> / <a href="https://www.iso.org/standard/79429.html">29119-3:2021</a> / <a href="https://www.iso.org/standard/79430.html">29119-4:2021</a></li>
<li><a href="https://www.iso.org/standard/78176.html">ISO/IEC 25010:2023</a> / <a href="https://www.iso.org/standard/78177.html">ISO/IEC 25019:2023</a></li>
<li><a href="https://www.aster.or.jp/testcontest/open/">ASTER テスト設計コンテスト'26 OPEN審査基準</a> / <a href="https://www.aster.or.jp/testcontest/u30/">U-30成果物体系</a></li>
<li><a href="https://www.juse-p.co.jp/filemanager/source/Trial_Reading/2022/trial9784817197665.pdf">ソフトウェアテスト技法ドリル試読（点・線・面・立体・時間・多次元）</a></li>
</ul></section>`,
});

function traceTable() {
  const byFeature = new Map(features.map((feature) => [feature.feature_id, { feature }]));
  for (const [phase, cases] of Object.entries(phaseCases)) {
    for (const testCase of cases) {
      if (!byFeature.has(testCase.featureId)) continue;
      const record = byFeature.get(testCase.featureId);
      record[phase] = (record[phase] ?? 0) + 1;
    }
  }
  return [...byFeature.values()]
    .sort((a, b) => riskOrder[b.feature.risk_level] - riskOrder[a.feature.risk_level])
    .map(({ feature, unit = 0, integration = 0, system = 0, acceptance = 0 }) => `<tr>
<td class="mono">${esc(feature.feature_id)}</td><td>${esc(feature.name)}</td><td><span class="badge risk-${feature.risk_level}">${esc(riskJa[feature.risk_level])}</span></td>
<td>${unit}</td><td>${integration}</td><td>${system}</td><td>${acceptance}</td><td>${unit+integration+system+acceptance}</td>
<td>${(feature.failure_modes??[]).length}</td><td>${(feature.required_tests??[]).length}</td><td>${(feature.outputs??[]).length}</td></tr>`).join("");
}

const traceHtml = layout({
  title: "トレーサビリティ・リスク",
  active: "trace",
  hero: hero("トレーサビリティとリスク", "40機能から4フェーズ5,199件への双方向追跡と、品質リスク・テストベース差異を示す。", allCases.length),
  body: `<section><h2>1. 機能→フェーズ→ケース数</h2><div class="table-wrap"><table><thead><tr><th>機能ID</th><th>名称</th><th>リスク</th><th>単体</th><th>結合</th><th>システム</th><th>受入</th><th>計</th><th>故障</th><th>必須経路</th><th>成果物</th></tr></thead><tbody>${traceTable()}</tbody></table></div>
<p class="small">横断ケースは特定機能へ重複配賦せずCROSS-CUTとして管理するため、上表合計と全ケース総数には差がある。</p></section>
<section><h2>2. ケース生成規則</h2><table><thead><tr><th>フェーズ</th><th>算定式</th><th>件数</th></tr></thead><tbody>
<tr><td>単体</td><td>164 symbols×2 + 187 failures + 128 outputs + 54 persistence + 150 required</td><td>${phaseCases.unit.length}</td></tr>
<tr><td>結合</td><td>150 required×3 boundaries + 33 routes×4 protocols + 128 outputs×2 + 54 persistence×3</td><td>${phaseCases.integration.length}</td></tr>
<tr><td>システム</td><td>150×2 viewports×2 modes + 187×2×2 recovery + 128×2×2 theme + 49 UI×4 states×2×2 + 54×2 + 8 stages×6 events×2 + 12 journeys×2×4 roles×2 data</td><td>${phaseCases.system.length}</td></tr>
<tr><td>受入</td><td>12 journeys×5 personas×2 viewports + 40 features + 3 QIU×8 contexts + 128 outputs</td><td>${phaseCases.acceptance.length}</td></tr>
</tbody></table><p>算定式はカバレッジ義務の可視化であり、実行時に同一事象を重複検証する場合はケース統合せず、異なるオラクルと責任境界を保持する。</p></section>
<section><h2>3. 既知のテストベース差異</h2><table><thead><tr><th>ID</th><th>差異</th><th>計画上の扱い</th></tr></thead><tbody>
<tr><td>TB-GAP-01</td><td>要件定義33機能 vs 品質契約40機能</td><td>40機能を対象。7機能の要件レビューを開始基準に追加。</td></tr>
<tr><td>TB-GAP-02</td><td>非機能文書がISO 25010:2011の8特性</td><td>2023年版9特性と25019利用時品質へ再分類。</td></tr>
<tr><td>TB-GAP-03</td><td>既存計画の19機能・過去合格件数</td><td>現行版の合格証拠に流用しない。</td></tr>
<tr><td>TB-GAP-04</td><td>デモ文書と実装の入力制約・画面・遷移差</td><td>テストデータの不整合プロファイルとして期待値を二重化せず、差異そのものを検出対象にする。</td></tr>
<tr><td>TB-GAP-05</td><td>表示例にundefined、関数文字列、過大余白</td><td>個別画面だけでなく全成果物・全UI状態へ横展開。</td></tr>
</tbody></table></section>
<section><h2>4. リスク→ケース検索キー</h2><p>各フェーズのケース一覧で、次の語を検索する。</p><table><thead><tr><th>リスク</th><th>検索キー例</th><th>主フェーズ</th></tr></thead><tbody>
${riskRows.map((row)=>`<tr><td>${row[0]} ${esc(row[1])}</td><td>${esc(row[4])}</td><td>${row[2]==="critical"?"全フェーズ":"結合・システム・受入"}</td></tr>`).join("")}</tbody></table></section>`,
});

const files = {
  "index.html": masterHtml,
  "01_unit.html": unitHtml,
  "02_integration.html": integrationHtml,
  "03_system.html": systemHtml,
  "04_acceptance.html": acceptanceHtml,
  "05_traceability.html": traceHtml,
};
for (const [name, content] of Object.entries(files)) {
  fs.writeFileSync(path.join(outDir, name), content, "utf8");
}

const manifest = {
  document_id: "WS2D-ZBQA",
  version: VERSION,
  created: CREATED,
  status: "pending_approval",
  test_execution_started: false,
  sut: SUT_URL,
  test_data: DATA_URL,
  inventory,
  counts: {
    unit: phaseCases.unit.length,
    integration: phaseCases.integration.length,
    system: phaseCases.system.length,
    acceptance: phaseCases.acceptance.length,
    total: allCases.length,
  },
  files: Object.keys(files),
};
fs.writeFileSync(
  path.join(outDir, "manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  "utf8",
);

console.log(JSON.stringify(manifest, null, 2));
