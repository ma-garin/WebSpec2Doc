"""QAプロセス生成ルートのテスト"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.qa_process as qa_mod


def _client():
    return appmod.app.test_client()


def _write_report(base: Path, domain: str = "example.com") -> Path:
    domain_dir = base / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "meta": {"target_url": f"https://{domain}/", "page_count": 2, "crawled_at": "2026-06-01"},
        "screens": [
            {
                "page_id": "P001",
                "url": f"https://{domain}/",
                "title": "トップ",
                "headings": ["トップ"],
                "buttons": ["検索"],
                "forms": [
                    {
                        "action": "/search",
                        "method": "get",
                        "fields": [
                            {
                                "name": "q",
                                "element_id": "query",
                                "field_type": "text",
                                "required": True,
                                "placeholder": "キーワード",
                                "test_conditions": ["必須入力"],
                            }
                        ],
                    }
                ],
                "transitions": {"to": ["P002"], "from": []},
            },
            {
                "page_id": "P002",
                "url": f"https://{domain}/about",
                "title": "会社概要",
                "headings": ["会社概要"],
                "buttons": [],
                "forms": [],
                "transitions": {"to": [], "from": ["P001"]},
            },
        ],
    }
    (domain_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (domain_dir / "report.html").write_text("<html></html>", encoding="utf-8")
    (domain_dir / "spec.xlsx").write_bytes(b"fake")
    return domain_dir


def test_input_returns_summary_and_input_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(qa_mod, "OUTPUT_DIR", tmp_path)
    _write_report(tmp_path)

    res = _client().get("/api/qa-process/input?domain=example.com")
    data = res.get_json()

    assert res.status_code == 200
    assert data["summary"]["screens"] == 2
    assert data["summary"]["fields"] == 1
    assert data["summary"]["required"] == 1
    assert data["input_files"]["report_json"].endswith("report.json")
    assert len(data["screens"]) == 2
    assert data["screens"][0]["raw_forms"][0]["fields"][0]["name"] == "q"
    assert any(vp["name"] == "セキュリティ" for vp in data["viewpoints"])


def test_generate_creates_all_qa_process_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(qa_mod, "OUTPUT_DIR", tmp_path)
    domain_dir = _write_report(tmp_path)

    res = _client().post(
        "/api/qa-process/generate", data={"domain": "example.com", "step": "test_cases"}
    )
    data = res.get_json()

    assert res.status_code == 200
    assert data["ok"] is True
    assert data["selected"].endswith("test_cases.md")
    qa_dir = domain_dir / "qa_process"
    for filename in (
        "test_plan.md",
        "test_analysis.md",
        "test_design.md",
        "test_cases.md",
        "cross_review.md",
        "qa_process_report.html",
        "screen_transition_graph.json",
        "model_graph.html",
        "coverage_metrics.json",
        "playwright_candidates.json",
        "playwright_candidates.html",
        "quality_viewpoints.json",
        "quality_viewpoints.html",
        "testcases.html",
    ):
        assert (qa_dir / filename).exists()
    assert "P001-F01-I01" in (qa_dir / "test_cases.md").read_text(encoding="utf-8")
    assert "外部LLM API未使用" in (qa_dir / "qa_process_report.html").read_text(encoding="utf-8")
    assert "CSV観点" in (qa_dir / "test_design.md").read_text(encoding="utf-8")
    assert "セキュリティ" in (qa_dir / "qa_process_report.html").read_text(encoding="utf-8")
    assert (
        json.loads((qa_dir / "screen_transition_graph.json").read_text(encoding="utf-8"))["edges"][
            0
        ]["trace_id"]
        == "P001->P002"
    )
    assert "Playwright" in (qa_dir / "playwright_candidates.html").read_text(encoding="utf-8")
    assert "OWASP" in (qa_dir / "quality_viewpoints.html").read_text(encoding="utf-8")


def test_advanced_endpoint_returns_model_candidates_and_quality(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(qa_mod, "OUTPUT_DIR", tmp_path)
    _write_report(tmp_path)

    res = _client().get("/api/qa-process/advanced?domain=example.com")
    data = res.get_json()

    assert res.status_code == 200
    assert data["transition_graph"]["nodes"][0]["id"] == "P001"
    assert data["coverage_metrics"]["rates"]["screen_trace_rate"] == 100
    assert data["playwright_candidates"]["execution_policy"].startswith("候補生成のみ")
    assert any(
        item["category"] == "OWASP WSTG/ASVS" for item in data["quality_viewpoints"]["items"]
    )


def test_generate_advanced_creates_preview_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(qa_mod, "OUTPUT_DIR", tmp_path)
    domain_dir = _write_report(tmp_path)

    res = _client().post("/api/qa-process/generate-advanced", data={"domain": "example.com"})
    data = res.get_json()

    assert res.status_code == 200
    assert data["ok"] is True
    qa_dir = domain_dir / "qa_process"
    assert (qa_dir / "model_graph.html").exists()
    assert (qa_dir / "coverage_metrics.json").exists()
    assert data["outputs"]["model_graph"].endswith("model_graph.html")


def test_testcases_endpoint_returns_low_level_cases(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(qa_mod, "OUTPUT_DIR", tmp_path)
    _write_report(tmp_path)

    res = _client().get("/api/testcases?domain=example.com")
    data = res.get_json()

    assert res.status_code == 200
    assert data["domain"] == "example.com"
    assert data["count"] == len(data["cases"])
    assert data["count"] > 0
    smoke_case = next(c for c in data["cases"] if c["trace_id"] == "P001")
    assert smoke_case["preconditions"][0].startswith("ブラウザで")
    assert "page.goto(" not in smoke_case["preconditions"][0]
    assert smoke_case["expected_result"]
    # HTML成果物が未生成の状態では空文字（生成後は generate-advanced 経由でパスが入る）
    assert data["html_path"] == ""


def test_testcases_endpoint_requires_report_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(qa_mod, "OUTPUT_DIR", tmp_path)

    res = _client().get("/api/testcases?domain=no-such-domain.example")

    assert res.status_code == 404


def test_generate_advanced_creates_testcases_html(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(qa_mod, "OUTPUT_DIR", tmp_path)
    domain_dir = _write_report(tmp_path)

    res = _client().post("/api/qa-process/generate-advanced", data={"domain": "example.com"})
    data = res.get_json()

    assert res.status_code == 200
    qa_dir = domain_dir / "qa_process"
    assert (qa_dir / "testcases.html").exists()
    html_content = (qa_dir / "testcases.html").read_text(encoding="utf-8")
    assert "テストケース一覧" in html_content
    assert "page.goto(" not in html_content
    assert data["outputs"]["testcases_html"].endswith("testcases.html")

    # 生成後は /api/testcases のレスポンスにも html_path が入る
    res2 = _client().get("/api/testcases?domain=example.com")
    assert res2.get_json()["html_path"].endswith("testcases.html")


def test_generate_with_ai_requested_without_key_falls_back(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(qa_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(qa_mod, "has_openai_api_key", lambda: False)
    _write_report(tmp_path)

    res = _client().post(
        "/api/qa-process/generate", data={"domain": "example.com", "use_ai": "true"}
    )
    data = res.get_json()

    assert res.status_code == 200
    assert data["ai"]["requested"] is True
    assert data["ai"]["used"] is False
    assert data["ai"]["fallback"] is True
    assert data["ai_artifact"] is None


def test_generate_with_ai_success_writes_structured_artifact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(qa_mod, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(qa_mod, "has_openai_api_key", lambda: True)
    domain_dir = _write_report(tmp_path)

    def fake_generate(domain, report, viewpoints):
        assert domain == "example.com"
        assert any(vp["name"] == "セキュリティ" for vp in viewpoints)
        return {
            "mode_version": "qa-process-v1",
            "model": "gpt-test",
            "test_plan": {
                "scope": ["P001を対象にする"],
                "levels": ["画面仕様確認"],
                "risks": ["検索条件の欠落"],
                "entry_criteria": ["report.jsonが存在する"],
                "exit_criteria": ["Trace IDが付く"],
                "questions": ["対応ブラウザ"],
            },
            "test_analysis": {
                "source_inventory": [
                    {
                        "screen_id": "P001",
                        "title": "トップ",
                        "observations": ["検索フォーム"],
                        "risk": "必須入力",
                        "trace_id": "P001",
                    }
                ],
                "risk_items": [
                    {
                        "risk_id": "R-001",
                        "description": "未入力",
                        "impact": "検索不可",
                        "trace_id": "P001-F01-I01",
                    }
                ],
                "questions": ["権限"],
            },
            "test_design": {
                "viewpoints": [
                    {
                        "viewpoint_id": "TD-001",
                        "target": "検索",
                        "technique": "同値分割",
                        "design_note": "必須確認",
                        "trace_id": "P001-F01-I01",
                    }
                ],
                "coverage_matrix": [
                    {
                        "trace_id": "P001-F01-I01",
                        "covered_by": "TC-0001",
                        "coverage_note": "正常/異常",
                    }
                ],
                "questions": ["境界値"],
            },
            "test_cases": {
                "expected_case_yield": "1件",
                "case_expansion_ledger": ["必須項目から展開"],
                "cases": [
                    {
                        "case_id": "TC-0001",
                        "title": "検索必須",
                        "precondition": "トップ表示",
                        "steps": ["qを空にする"],
                        "expected": "必須エラー",
                        "execution_type": "自動化候補",
                        "automation_candidate": "Playwright",
                        "status": "生成済み",
                        "trace_id": "P001-F01-I01",
                    }
                ],
                "questions": ["エラーメッセージ"],
            },
            "cross_review": {
                "findings": ["Trace IDあり"],
                "gaps": ["権限別期待結果"],
                "recommendations": ["質問待ちを解消"],
                "questions": ["リリース判定"],
            },
            "qa_process_report": {"summary": "AI補完済み", "next_actions": ["レビュー"]},
        }

    monkeypatch.setattr(qa_mod, "generate_openai_qa", fake_generate)

    res = _client().post(
        "/api/qa-process/generate", data={"domain": "example.com", "use_ai": "true"}
    )
    data = res.get_json()

    assert res.status_code == 200
    assert data["ai"]["used"] is True
    assert data["ai_artifact"]["model"] == "gpt-test"
    assert (domain_dir / "qa_process" / "ai_artifacts.json").exists()
    assert "OpenAI API補完" in (domain_dir / "qa_process" / "qa_process_report.html").read_text(
        encoding="utf-8"
    )


def test_result_returns_generated_output_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(qa_mod, "OUTPUT_DIR", tmp_path)
    _write_report(tmp_path)
    _client().post("/api/qa-process/generate", data={"domain": "example.com"})

    data = _client().get("/api/qa-process/result?domain=example.com").get_json()

    assert data["outputs"]["test_plan"].endswith("test_plan.md")
    assert data["outputs"]["qa_process_report"].endswith("qa_process_report.html")


def test_input_rejects_invalid_domain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(qa_mod, "OUTPUT_DIR", tmp_path)
    res = _client().get("/api/qa-process/input?domain=../etc")
    assert res.status_code == 404


def test_generate_requires_report_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(qa_mod, "OUTPUT_DIR", tmp_path)
    (tmp_path / "example.com").mkdir()
    res = _client().post("/api/qa-process/generate", data={"domain": "example.com"})
    assert res.status_code == 404


def test_generate_rejects_invalid_report_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(qa_mod, "OUTPUT_DIR", tmp_path)
    domain_dir = tmp_path / "example.com"
    domain_dir.mkdir()
    (domain_dir / "report.json").write_text("{", encoding="utf-8")
    res = _client().post("/api/qa-process/generate", data={"domain": "example.com"})
    assert res.status_code == 400
