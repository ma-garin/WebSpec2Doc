"""LLM アクティビティログのテスト。

生成 AI を使う経路（structured JSON・QA チャット）では、成功・退避・失敗を
問わず必ず llm_activity.jsonl に記録されることを検証する。
"""

from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import llm.openai_client as oc
from llm.activity_log import (
    ACTIVITY_LOG_DIR_ENV,
    ACTIVITY_LOG_FILE_NAME,
    llm_activity_context,
    record_llm_activity,
)


def _read_entries(directory: Path) -> list[dict]:
    path = directory / ACTIVITY_LOG_FILE_NAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class TestRecordLlmActivity:
    def test_writes_jsonl_entry(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv(ACTIVITY_LOG_DIR_ENV, str(tmp_path))
        record_llm_activity(
            purpose="unit_test",
            endpoint_url="http://127.0.0.1:11434/v1/chat/completions",
            model="qwen2.5:3b",
            outcome="ok",
            detail="json_schema",
            prompt_chars=42,
            duration_ms=120,
        )
        entries = _read_entries(tmp_path)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["purpose"] == "unit_test"
        assert entry["outcome"] == "ok"
        assert entry["model"] == "qwen2.5:3b"
        assert entry["prompt_chars"] == 42
        assert "timestamp" in entry

    def test_context_supplies_purpose_and_output_dir(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv(ACTIVITY_LOG_DIR_ENV, raising=False)
        with llm_activity_context(
            purpose="stage_suggest",
            domain="example.com",
            stage_id="viewpoints",
            output_dir=tmp_path,
        ):
            record_llm_activity(outcome="ok")
        entries = _read_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["purpose"] == "stage_suggest"
        assert entries[0]["domain"] == "example.com"
        assert entries[0]["stage_id"] == "viewpoints"

    def test_never_raises_on_write_failure(self, tmp_path, monkeypatch) -> None:
        blocked = tmp_path / "file"
        blocked.write_text("x", encoding="utf-8")
        # ディレクトリではなくファイルを出力先に指定 → mkdir/open が失敗するが例外は出ない
        monkeypatch.setenv(ACTIVITY_LOG_DIR_ENV, str(blocked))
        assert record_llm_activity(outcome="ok") is None


class TestRequestStructuredJsonAlwaysLogged:
    """choke point（request_structured_json）で全呼び出しが記録される。"""

    def _llm_payload(self, body: dict) -> dict:
        return {"choices": [{"message": {"content": json.dumps(body)}}]}

    def test_success_records_ok(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv(ACTIVITY_LOG_DIR_ENV, str(tmp_path))
        with patch.object(oc, "_post_json", return_value=self._llm_payload({"a": 1})):
            result = oc.request_structured_json(
                "key", "model-x", "prompt", "schema", {"type": "object"}, purpose="unit"
            )
        assert result == {"a": 1}
        entries = _read_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["outcome"] == "ok"
        assert entries[0]["detail"] == "json_schema"
        assert entries[0]["purpose"] == "unit"

    def test_unreachable_records_unavailable(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv(ACTIVITY_LOG_DIR_ENV, str(tmp_path))
        with patch.object(
            oc, "_post_json", side_effect=urllib.error.URLError("connection refused")
        ):
            with pytest.raises(oc.LLMUnavailableError):
                oc.request_structured_json("key", "model-x", "prompt", "schema", {"type": "object"})
        entries = _read_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["outcome"] == "unavailable"

    def test_schema_fallback_records_mode(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv(ACTIVITY_LOG_DIR_ENV, str(tmp_path))
        http_error = urllib.error.HTTPError("u", 400, "bad request", None, None)
        with patch.object(
            oc,
            "_post_json",
            side_effect=[http_error, self._llm_payload({"b": 2})],
        ):
            result = oc.request_structured_json(
                "key", "model-x", "prompt", "schema", {"type": "object"}
            )
        assert result == {"b": 2}
        entries = _read_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["outcome"] == "ok"
        assert entries[0]["detail"] == "json_object_fallback"

    def test_invalid_response_recorded(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv(ACTIVITY_LOG_DIR_ENV, str(tmp_path))
        with patch.object(
            oc, "_post_json", return_value={"choices": [{"message": {"content": "not-json"}}]}
        ):
            with pytest.raises(oc.LLMResponseError):
                oc.request_structured_json("key", "model-x", "prompt", "schema", {"type": "object"})
        entries = _read_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["outcome"] == "invalid_response"


class TestChatRouteAlwaysLogged:
    def _client(self):
        import app as appmod

        return appmod.app.test_client()

    def test_chat_not_configured_records(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv(ACTIVITY_LOG_DIR_ENV, str(tmp_path))
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("WEBSPEC2DOC_LLM_API_KEY", raising=False)
        monkeypatch.delenv("WEBSPEC2DOC_LLM_BASE_URL", raising=False)
        res = self._client().post("/api/llm/chat", json={"message": "テスト観点を教えて"})
        assert res.status_code == 503
        entries = _read_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["purpose"] == "qa_chat"
        assert entries[0]["outcome"] == "not_configured"

    def test_chat_success_records_ok(self, tmp_path, monkeypatch) -> None:
        import web.routes.llm_chat as chat_mod

        monkeypatch.setenv(ACTIVITY_LOG_DIR_ENV, str(tmp_path))
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        with patch.object(chat_mod, "_chat", return_value="境界値分析を推奨します"):
            res = self._client().post("/api/llm/chat", json={"message": "助言ください"})
        assert res.status_code == 200
        entries = _read_entries(tmp_path)
        assert len(entries) == 1
        assert entries[0]["outcome"] == "ok"
        assert entries[0]["purpose"] == "qa_chat"
