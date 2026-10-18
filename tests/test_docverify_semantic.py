"""二段目（埋め込み）の単体テスト。スタブの埋め込みを注入し、API は呼ばない。"""
from collections import Counter

import pytest

from web.services.docverify.pair import engine, semantic

REQ = """# 要件

## 機能要件
- 申請者は経費を申請できる。
- 管理者は承認者を一覧で確認できる。

## 用語
| 用語 | 意味 |
| --- | --- |
| 申請者 | 経費を申請する人 |
"""
DES = """# 設計

## 機能設計
### 申請機能
- 申込者は経費を申請する画面から入力する。
- 申請者は承認者を一覧で確認する。

### 天気表示
- 画面右上に今日の天気予報を表示する。
"""


def _stub(texts):
    keys = sorted({t[i:i + 2] for t in texts for i in range(len(t) - 1)})
    idx = {k: n for n, k in enumerate(keys)}
    out = []
    for t in texts:
        v = [0.0] * len(keys)
        for k, n in Counter(t[i:i + 2] for i in range(len(t) - 1)).items():
            v[idx[k]] = float(n)
        out.append(v)
    return out


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("WEBSPEC2DOC_DOCVERIFY_SEMANTIC", raising=False)
    yield
    semantic.set_embedder(None)


def test_stub_runs_second_stage(monkeypatch):
    monkeypatch.setattr(semantic, "T_TERM", 0.3)
    semantic.set_embedder(_stub)
    res = engine.inspect(REQ, DES)
    assert not [e for e in res["errors"] if e["detector"].startswith("semantic")]
    types = {d["type"] for d in res["defects"]}
    assert "EXTRA_IN_DESIGN" in types


def test_no_key_adds_error(monkeypatch):
    monkeypatch.setattr(semantic, "_api_key", lambda: "")
    res = engine.inspect(REQ, DES)
    assert {"detector": "semantic", "error": semantic.NO_KEY_ERROR} in res["errors"]


def test_off_adds_no_error(monkeypatch):
    monkeypatch.setattr(semantic, "_api_key", lambda: "")
    monkeypatch.setenv("WEBSPEC2DOC_DOCVERIFY_SEMANTIC", "off")
    res = engine.inspect(REQ, DES)
    assert not [e for e in res["errors"] if e["detector"] == "semantic"]


def test_embed_none_without_key(monkeypatch):
    monkeypatch.setattr(semantic, "_api_key", lambda: "")
    assert semantic.embed(["a"]) is None
