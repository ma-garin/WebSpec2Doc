"""質問票 CSV の出力と回答の取り込み（DD-008）。"""
from __future__ import annotations

import csv
import io
from typing import Iterable

from web.vendor.reverse_doc.confidence import build_questions, finalize, map_statements
from web.vendor.reverse_doc.models import Question, Statement, UsdmDocument, replace

CSV_COLUMNS = ("質問ID", "質問", "関係する記述", "選択肢", "回答")
BOM = "﻿"
LIST_SEPARATOR = "; "
CHOICE_SEPARATOR = " / "


def export_csv(questions: Iterable[Question]) -> str:
    """質問票を UTF-8 BOM 付きの CSV 文字列にする。"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for q in questions:
        writer.writerow((q.id, q.text, LIST_SEPARATOR.join(q.related_ids), CHOICE_SEPARATOR.join(q.choices),
                         q.answer or ""))
    return BOM + buf.getvalue()


def import_csv(text: str) -> dict[str, str]:
    """質問ID → 回答（空の回答は除く）。質問ID か回答の列が無ければ ValueError。"""
    body = text[1:] if text.startswith(BOM) else text
    reader = csv.DictReader(io.StringIO(body))
    columns = reader.fieldnames or []
    missing = [c for c in (CSV_COLUMNS[0], CSV_COLUMNS[4]) if c not in columns]
    if missing:
        raise ValueError(f"質問票の列が足りない: {', '.join(missing)}。出力した質問票の 1 行目を変えずに回答を書き込んでください。")
    answers: dict[str, str] = {}
    for row in reader:
        qid = (row.get(CSV_COLUMNS[0]) or "").strip()
        answer = (row.get(CSV_COLUMNS[4]) or "").strip()
        if qid and answer:
            answers[qid] = answer
    return answers


def apply_answers(doc: UsdmDocument, answers: dict[str, str]) -> UsdmDocument:
    """回答のある質問の関係する記述を text=回答・origin="answer"・source="human" で置き換え、finalize した新しい文書を返す。"""
    questions = doc.questions or build_questions(doc)
    targets: dict[str, str] = {}
    for q in questions:
        if q.id in answers:
            targets.update({rid: answers[q.id] for rid in q.related_ids})

    def answer_statement(sid: str, st: Statement) -> Statement:
        # 事実の記述に関する問い（拒否の扱い・入力の上限など）の回答は質問に残し、事実の文は置き換えない
        if sid not in targets or st.confidence == "事実":
            return st
        return replace(st, text=targets[sid], source="human", origin="answer")

    answered = map_statements(doc, answer_statement)
    new_questions = tuple(replace(q, answer=answers[q.id]) if q.id in answers else q for q in questions)
    return finalize(replace(answered, questions=new_questions))


__all__ = ["CSV_COLUMNS", "export_csv", "import_csv", "apply_answers"]
