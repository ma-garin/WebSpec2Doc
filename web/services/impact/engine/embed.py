"""意味の近さ（DD-004 embed.py）。OpenAI 互換 /embeddings、使えないときは文字 2-gram の cosine に縮退。"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

from llm.openai_client import resolve_endpoint  # noqa: E402

from .text import cosine, ngrams  # noqa: E402

log = logging.getLogger(__name__)
ENV_MODEL = "WEBSPEC2DOC_EMBED_MODEL"
TIMEOUT_SEC = 30
BATCH = 64


def _dense_cosine(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class Embedder:
    """mode='embedding' は接続先のベクトル、mode='ngram' は文字 2-gram。"""

    def __init__(self, mode: str = "ngram", base_url: str = "", api_key: str = "", model: str = "", reason: str = ""):
        self.mode = mode
        self.base_url, self.api_key, self.model = base_url, api_key, model
        self.reason = reason

    @property
    def available(self) -> bool:
        return self.mode == "embedding"

    def _fallback(self, exc: Exception) -> None:
        log.info("埋め込みを使えないため文字 n-gram に切り替えます: %s", exc)
        self.mode = "ngram"
        self.reason = "埋め込みの接続先に失敗したため、文字の近さで探しました。"

    def _post(self, texts: list[str]) -> list[list[float]]:
        req = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/embeddings",
            data=json.dumps({"model": self.model, "input": texts}).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:  # nosec B310
            data = json.loads(resp.read().decode("utf-8"))
        rows = sorted(data.get("data", []), key=lambda r: r.get("index", 0))
        vecs = [r["embedding"] for r in rows]
        if len(vecs) != len(texts):
            raise ValueError("埋め込みの件数が入力と一致しません")
        return vecs

    def vectors(self, texts: list[str]) -> list:
        if self.mode == "embedding":
            try:
                out = []
                for i in range(0, len(texts), BATCH):
                    out += self._post([t or " " for t in texts[i:i + BATCH]])
                return out
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self._fallback(exc)
        return [ngrams(t) for t in texts]

    def similar(self, query: str, corpus_vectors: list, top_k: int = 30) -> list[tuple[int, float]]:
        """query に近い順に (corpus の添字, score) を返す。corpus_vectors は vectors() の戻り値。"""
        if not corpus_vectors:
            return []
        dense = not hasattr(corpus_vectors[0], "items")
        qv = self.vectors([query])[0]
        if dense and hasattr(qv, "items"):   # 途中で縮退した: 比較できないので空
            return []
        sim = _dense_cosine if dense else cosine
        scored = [(i, round(sim(qv, v), 4)) for i, v in enumerate(corpus_vectors)]
        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]


def make_embedder(policy: str) -> Embedder:
    """policy='none'、接続先・モデルが無い、'local' で外部の接続先なら ngram。"""
    if policy not in ("local", "external"):
        return Embedder(reason="外部送信しない設定のため、文字の近さで探しました。")
    model = os.environ.get(ENV_MODEL, "").strip()
    if not model:
        return Embedder(reason="埋め込みモデルが未設定のため、文字の近さで探しました。")
    ep = resolve_endpoint()
    if not ep.api_key:
        return Embedder(reason="接続先が無いため、文字の近さで探しました。")
    if policy == "local" and not ep.is_local:
        return Embedder(reason="ローカル限定の設定で接続先が外部のため、文字の近さで探しました。")
    return Embedder("embedding", ep.base_url, ep.api_key, model)
