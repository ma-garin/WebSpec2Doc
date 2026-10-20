"""二段目の検出: OpenAI 埋め込みによる余分な設計・用語ゆれ。

キー未設定・通信失敗のときは embed が None を返し、呼び出し側は何もしない（出力は一段目のまま）。
結果は sha256(model+text) をキーにディスクへ残し、同じ文で二重に課金せず結果を決定的にする。
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Callable

from llm.openai_client import request_embeddings, resolve_endpoint

from . import link
from . import terms as _terms
from .segment import Unit

MODEL = "text-embedding-3-small"
LOCAL_MODEL = "nomic-embed-text"
ENV_EMBED_MODEL = "WEBSPEC2DOC_EMBED_MODEL"
# 未調整（pair_v1 で調整予定）。キー設定後に pair_v1 の適合率・再現率で決める暫定値
T_EXTRA = 0.30
T_TERM = 0.60
BATCH = 96
OFF_ENV = "WEBSPEC2DOC_DOCVERIFY_SEMANTIC"
NO_KEY_ERROR = "未実行: LLM の接続先またはキーが未設定"

Embedder = Callable[[list[str]], "list[list[float]] | None"]
_override: Embedder | None = None


def set_embedder(fn: Embedder | None) -> None:
    """テスト用: 埋め込み関数を差し替える（None で戻す）。"""
    global _override
    _override = fn


def disabled() -> bool:
    return os.environ.get(OFF_ENV, "").strip().lower() == "off"


def _env() -> dict[str, str]:
    """接続先系は os.environ と .env（.env 優先）、OpenAI キーは .env を優先して合成する。"""
    env = dict(os.environ)
    try:
        from web.env_store import _read_env
        env.update({k: v for k, v in _read_env().items() if v})
    except Exception:
        pass
    return env


def _api_key() -> str:
    """埋め込みに使うキー。ローカル宛て（Ollama 等）は置き値、OpenAI 宛てでキー無しは空。"""
    return resolve_endpoint(env=_env()).api_key


def _model() -> str:
    """実効モデル。OpenAI 宛ては MODEL、ローカル宛ては WEBSPEC2DOC_EMBED_MODEL（無ければ既定）。"""
    env = _env()
    if resolve_endpoint(env=env).is_local:
        return (env.get(ENV_EMBED_MODEL) or "").strip() or LOCAL_MODEL
    return MODEL


def available() -> bool:
    return _override is not None or bool(_api_key())


def _cache_dir() -> Path:
    root = Path(__file__).resolve().parents[4] / ".runtime"  # .gitignore 済み
    d = root / "docverify_embed_cache"
    try:
        d.mkdir(parents=True, exist_ok=True)
        return d
    except OSError:
        d = Path.home() / ".cache" / "webspec2doc" / "docverify_embed"
        d.mkdir(parents=True, exist_ok=True)
        return d


def _ckey(text: str) -> str:
    return hashlib.sha256((_model() + text).encode("utf-8")).hexdigest()


def _post(texts: list[str], key: str) -> list[list[float]] | None:
    endpoint = resolve_endpoint(env=_env())
    try:
        return request_embeddings(
            texts, _model(), base_url=endpoint.base_url, api_key=key, purpose="docverify_semantic"
        )
    except Exception:
        return None


def embed(texts: list[str]) -> list[list[float]] | None:
    """各テキストの埋め込み。キー無し・通信失敗は None。"""
    if _override is not None:
        return _override(texts)
    key = _api_key()
    if not key:
        return None
    cdir = _cache_dir()
    vecs: dict[str, list[float]] = {}
    todo: list[str] = []
    for t in dict.fromkeys(texts):
        f = cdir / f"{_ckey(t)}.json"
        if f.exists():
            try:
                vecs[t] = json.loads(f.read_text(encoding="utf-8"))
                continue
            except (OSError, ValueError):
                pass
        todo.append(t)
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        got = _post(chunk, key)
        if got is None or len(got) != len(chunk):
            return None
        for t, v in zip(chunk, got):
            vecs[t] = v
            (cdir / f"{_ckey(t)}.json").write_text(json.dumps(v), encoding="utf-8")
    return [vecs[t] for t in texts]


def _cos(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def extra(design_units: list[Unit], req_units: list[Unit],
          links: list[tuple[Unit, Unit, float]]) -> list[Unit]:
    """link.extra と同じ候補のうち、どの要件とも類似度が T_EXTRA 未満の節。"""
    linked = {(s.start, s.end) for _, s, _ in links}
    reqs = link.targets(req_units)
    req_ids = {i for r in req_units for i in r.ids}
    req_norms = [link._norm(r.text) for r in reqs]
    secs = [s for s in link._candidates(design_units) if (s.start, s.end) not in linked
            and link._extra_candidate(s, req_ids, req_norms)]
    if not secs or not reqs:
        return secs
    vecs = embed([link._sec_text(s) for s in secs] + [r.text for r in reqs])
    if vecs is None:
        raise RuntimeError("埋め込みを取得できなかった")
    sv, rv = vecs[:len(secs)], vecs[len(secs):]
    return [s for s, v in zip(secs, sv) if max(_cos(v, r) for r in rv) < T_EXTRA]


def term_defects(req_units: list[Unit], design_units: list[Unit],
                 links: list[tuple[Unit, Unit, float]]) -> list[dict]:
    """リンク済みの要件⇔設計の組で、語が違い意味が近く、要件側の語が設計に出ない組。"""
    design_all = "\n".join(u.text for u in design_units)
    req_all = "\n".join(u.text for u in req_units)
    pairs: list[tuple[Unit, Unit, str, str]] = []
    for r, d, _ in links:
        rw = set(_terms._WORD.findall(r.text))
        dw = set(_terms._WORD.findall(d.text))
        for a in sorted(rw):
            if a in design_all:
                continue
            for b in sorted(dw - {a}):
                if b not in req_all:
                    pairs.append((r, d, a, b))
    if not pairs:
        return []
    words = sorted({w for p in pairs for w in p[2:]})
    vecs = embed(words)
    if vecs is None:
        raise RuntimeError("埋め込みを取得できなかった")
    vm = dict(zip(words, vecs))
    return [{"type": "TERM_INCONSISTENCY", "req_lines": [r.start, r.end],
             "design_lines": [d.start, d.end],
             "reason": f"要件の用語「{a}」を、設計では「{b}」と呼んでいる。"}
            for r, d, a, b in pairs if _cos(vm[a], vm[b]) >= T_TERM]
