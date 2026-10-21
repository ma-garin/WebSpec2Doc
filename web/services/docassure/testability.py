"""テスト可能性の決定論判定。LLM は使わない。原文は書き換えず、書き換え案は「提案（未承認）」で返す。"""
from __future__ import annotations

import re
import unicodedata

from .units import normalize_quantity
from dataclasses import asdict, is_dataclass
from typing import Any

CAN_TEST, PARTIAL, NOT_TESTABLE, UNKNOWN = "CAN_TEST", "PARTIALLY_TESTABLE", "NOT_TESTABLE", "UNKNOWN"

VAGUE_WORDS = ("高速", "迅速", "適切", "柔軟", "使いやすい", "なるべく", "十分", "快適", "素早", "スムーズ",
               "簡単", "すばやく", "できるだけ", "速やか", "安全に", "安定",
               # 評価者によって解釈が割れる形容・程度語、および定義のない基準への言及
               "直感的", "洗練", "美しい", "分かりやすい", "わかりやすい", "見やすい", "親しみ", "軽快", "堅牢", "効率的", "最適",
               "良好", "優れた", "心地", "手軽", "容易に", "所定", "一定", "閾値", "規定に", "連絡", "対処", "考慮", "配慮")
_UNITS = r"(?:ms|msec|秒|分|時間|日|歳|才|件|行|レコード|MB|KB|GB|TB|byte|バイト|%|％|回|文字|桁|人|ユーザー|ユーザ|個|ページ)"
RE_THRESHOLD = re.compile(r"\d+(?:\.\d+)?\s*" + _UNITS, re.I)
# 単位語は列挙せず、数量表現の正規化（units.py）と時刻・暦の数値でも閾値とみなす
RE_CLOCK = re.compile(r"\d+\s*(?:時|月|週|曜)")
RE_VOLUME = re.compile(r"\d+(?:\.\d+)?\s*(?:件|行|レコード|MB|GB|TB|人|ユーザー|ユーザ|個|ページ)|データ量|同時")
RE_CONDITION = re.compile(r"環境|負荷|ブラウザ|ネットワーク|回線|計測|測定|平均|パーセンタイル|95|のとき|時に|場合|において|以内に"
                          r"|とき|より前|より後|[^\s、]後に|てから|たら|ごとに|限り|以降|までに|に応じて|した[^\s、。]{1,12}(?:は|が)"
                          r"|前に|まで|であれば|[日月年週]前|前日|翌日|当日|月末|月次|日次|週次|毎[日週月年]|時点|必須"
                          r"|(?:した|された|される|れた)[^\s、。]{1,12}を|第\d+[章節項条]|別紙|別表|付録")
RE_INCOMPLETE = re.compile(r"未記載|未定|記載しない|定めない|TBD|別途")  # 自ら未完成と述べる文は列挙があっても検証できる定義とみなさない
RE_QUOTED_LIST = re.compile(r"[」』]\s*(?:、|・|,|または|もしくは|及び|および|と)?\s*[「『]")  # 値の並び（「A」「B」/「A」または「B」）
RE_REF_ID = re.compile(r"[A-Za-z]{2,}-?\d+")
# 「実行した」だけでは成功条件にならない動作語（条件・閾値・結果が別に要る）と、結果として観測できる語を分ける
RE_OUTCOME = re.compile(r"表示|返す|返却|出力|完了|成功")
RE_PERMISSION = re.compile(r"でき(?:る|ない|ません)|行え(?:る|ない)|可能|不可|禁止|のみ|に限る|に限り|許可")
RE_HUMAN_ACTOR = re.compile(r"^[^はが]{0,12}?(?:者|員|ユーザー|ユーザ|客|会員|ゲスト|アドミン|admin|オペレーター|担当|部長|課長)(?:は|が)", re.I)
RE_QUOTED = re.compile(r"[「『][^」』]*[」』]")
RE_SUCCESS = re.compile(r"表示|返す|返却|出力|完了|成功|保存|登録|遷移|通知|できる|更新|削除|送信|ログイン|検索")
RE_FAILURE = re.compile(r"失敗|エラー|異常|拒否|不正|無効|タイムアウト|リトライ|ロック")


RE_DEFINITION = re.compile(r"^(?:[A-Za-z]+-?\d+\s+)?[^。]{1,40}?[:：]\s*[^。]*(?:をいう|を指す|のこと)|(?:をいう|を指す|とは)[。]?\s*$")
RE_TRANSITION = re.compile(r"[^\s、。]+から[^\s、。]+へ")
# 観測できる動作語（記録・廃棄・送信など）。曖昧語がなく主語・目的語が文中にある文は、条件が弱くても検証手順を書ける
RE_ACTION = re.compile(r"(?:記録|廃棄|送信|通知|算出|計算|保管|保留|並べ|ソート|再検査|検査|処理|削除|登録|更新|用意|提出|承認|確認|表示|参照|取得|集計|採番|付与|変換|受け付け|受付|転送|差し戻|返却|出力|保存)(?:する|し|と|を|は|る)")
RE_BARE_SYSTEM = re.compile(r"^\s*(?:[A-Za-z]+-?\d+\s+)?(?:本)?システムは")
# 動作に添えられた修飾（時点・根拠・順序）。これがあれば検証手順の入口になる
RE_QUALIFIER = re.compile(r"(?:後|時|際|とき)[、はに]|従って|に基づ|過ぎた|順に|(?:降|昇)順|ごとに|以外|[A-Za-z]・[A-Za-z]")


def _is_concrete(bare: str) -> bool:
    """曖昧語を含まず観測できる動作語を持つ文。主語が素の「システム」で修飾も無い文は、何を確かめるか決まらない。
    状態遷移の羅列は動作ではない（網羅性は別の検査が見る）。"""
    n_tr = len(RE_TRANSITION.findall(bare))
    if n_tr:
        return n_tr >= 3 or "または" in bare
    if RE_DEFINITION.search(bare):
        return True
    if not RE_ACTION.search(bare):
        return False
    return not (RE_BARE_SYSTEM.search(bare) and not RE_QUALIFIER.search(bare))


def to_dict(obj: Any) -> dict:
    """dict / dataclass / to_dict() 持ちを dict に正規化（元は変更しない）。"""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if is_dataclass(obj):
        return asdict(obj)
    return dict(obj)


def unit_view(unit: Any) -> dict:
    """{requirement_id, kind, raw_text, fields:{名:値}, text} を返す。INFERRED の値は事実として使わない。"""
    d = to_dict(unit)
    fields: dict[str, str] = {}
    for k, f in (d.get("fields") or {}).items():
        if isinstance(f, dict):
            if f.get("provenance") == "INFERRED":
                continue
            v = f.get("value", "")
        else:
            v = getattr(f, "value", f)
            if getattr(f, "provenance", "") == "INFERRED":
                continue
        if v:
            fields[k] = str(v)
    raw = str(d.get("raw_text") or "")
    text = unicodedata.normalize("NFKC", " ".join([raw, *fields.values()]))
    return {"requirement_id": d.get("requirement_id", ""), "kind": d.get("kind", "functional"),
            "raw_text": raw, "fields": fields, "text": text,
            "document_id": d.get("document_id", "")}


def assess(unit: Any) -> dict:
    v = unit_view(unit)
    text, fields = v["text"], v["fields"]
    if not text.strip():
        return {"verdict": UNKNOWN, "reasons": ["原文が空のため判定できない"], "missing": [], "rewrite_proposal": None}
    vague = [w for w in VAGUE_WORDS if w in text]
    has_threshold = bool(RE_THRESHOLD.search(text) or RE_CLOCK.search(text) or normalize_quantity(text))
    bare = RE_QUOTED.sub("", text)  # 「完了」のような状態名は結果ではない
    has_failure = bool(fields.get("exception") or RE_FAILURE.search(text))
    quoted = RE_QUOTED.findall(text)
    enumerated = (len(set(quoted)) >= 3 or bool(RE_QUOTED_LIST.search(text))) and not RE_INCOMPLETE.search(text)  # 「受付」「完了」のように値を列挙している＝観測できる状態の定義
    has_ref = bool(RE_REF_ID.search(re.sub(r"^\s*[A-Za-z]+-?\d+(?:\.\d+)*\s+", "", bare)))  # 他の要件 ID への参照（先頭の自分の ID は除く）
    has_condition = bool(enumerated or has_ref or fields.get("condition") or fields.get("constraint") or RE_CONDITION.search(bare))
    # 成功条件: 明示の期待結果、観測できる結果語、可否の定義（権限）、人が行う操作、条件付きの動作のいずれか
    er = fields.get("expected_result", "")
    er_new = bool(er) and er != fields.get("action", "")  # 抽出が動作文をそのまま写した値は「期待結果」とみなさない
    has_success = bool(enumerated or er_new or fields.get("acceptance_criteria") or RE_OUTCOME.search(bare)
                       or RE_PERMISSION.search(bare) or RE_HUMAN_ACTOR.search(re.sub(r"^[A-Za-z]+-?\d+\s+", "", bare))
                       or (has_condition and RE_SUCCESS.search(bare)))
    has_volume = bool(RE_VOLUME.search(text))
    missing: list[str] = []
    reasons: list[str] = []
    if not has_success:
        missing.append("成功条件")
    if not has_failure:
        missing.append("失敗時の挙動")
    if not has_threshold:
        missing.append("閾値・単位")
    if not has_condition:
        missing.append("測定条件")
    if not has_volume:
        missing.append("対象データ量")
    for w in vague:
        reasons.append(f"「{w}」の定義がない")
    if not has_threshold:
        reasons.append("閾値・単位がない")
    if vague and not has_threshold:
        verdict = NOT_TESTABLE
    elif not has_success and not has_threshold and not has_condition and not _is_concrete(bare):
        verdict = NOT_TESTABLE
        reasons.append("成功条件も閾値もない")
    elif has_success and has_threshold and not vague and (has_failure or has_condition):
        verdict = CAN_TEST
    else:
        verdict = PARTIAL
    if verdict == CAN_TEST:
        reasons = ["成功条件と閾値があり、判定基準を機械的に決められる"]
    elif verdict == PARTIAL and not reasons:
        reasons = ["一部の判定基準が不足している"]
    proposal = None
    if verdict != CAN_TEST:
        proposal = ("提案（未承認・原文は変更しない）: 次を確定して書き足す -> "
                    + " / ".join(missing or ["判定基準"])
                    + "。例: 「<条件>のとき、<対象>を<N>件のデータで<M>秒以内に表示する。失敗時は<エラー>を返す」")
    return {"verdict": verdict, "reasons": reasons, "missing": missing, "rewrite_proposal": proposal}
