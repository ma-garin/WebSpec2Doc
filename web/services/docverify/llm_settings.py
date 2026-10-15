"""AI の説明の送信先設定（System 06 R2）: 使わない／OpenAI／Ollama、接続先の検証、送信先の説明文。

契約: docs/sdlc/20_design/WS2D-DD-006_詳細設計書_System06_R2.md 3 章。
説明文（NFR-06-01・02）は ``_llm_disclosures.json`` を置くと上書きできる（出典と取得日を併記する）。
"""
from __future__ import annotations

import ipaddress
import json
import os
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from web import config
from web.tenancy import scoped_output_dir

DESTINATIONS = ("none", "openai", "ollama")
DEFAULT = {"destination": "none", "openai_model": "gpt-4o-mini",
           "ollama_url": "http://127.0.0.1:11434", "ollama_model": "qwen2.5:3b"}
_PRIVATE = tuple(ipaddress.ip_network(n) for n in ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
_LINK_LOCAL = ipaddress.ip_network("169.254.0.0/16")

ALLOWED_TEXT = ("この接続先は使えません。使える接続先は localhost・127.0.0.1・10.0.0.0/8・172.16.0.0/12・"
                "192.168.0.0/16 です（169.254.0.0/16 と本製品のポートは使えません）。アドレスを直してください。")
OLLAMA_DOWN = "Ollama に接続できません。起動とアドレスを確かめてください。"
NOT_ADMIN = "送信先を変えられるのはテナント管理者です。テナント管理者に依頼してください。"

DISCLOSURES = {
    "none": {"name": "使わない", "location": "外部へは送りません", "training": "送らないため学習には使われません",
             "retention": "送らないため送信先での保持はありません", "source": "本製品の設定", "retrieved": "2026-10-15"},
    "openai": {"name": "OpenAI API", "location": "国外で処理されます（国外で一時保存される場合があります）",
               "training": "既定で学習に使わないと OpenAI が公表しています",
               "retention": "不正利用の監視のため最大 30 日保持されます",
               "source": "https://developers.openai.com/api/docs/guides/your-data", "retrieved": "2026-10-15"},
    "ollama": {"name": "Ollama（社内）", "location": "この PC または社内のサーバーで処理します（国外へは送りません）",
               "training": "外部の事業者へ送らないため、事業者による学習はありません",
               "retention": "保持は接続先のサーバーの設定によります。管理者に確かめてください",
               "source": "本製品の設定（接続先は社内アドレスに限る）", "retrieved": "2026-10-15"},
}


def _root() -> Path:
    return scoped_output_dir(config.DATA_DIR) / "docverify"


def _read(name: str, default):
    path = _root() / name
    if not path.is_file():
        return json.loads(json.dumps(default))
    return json.loads(path.read_text(encoding="utf-8"))


def _write(name: str, data) -> None:
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=root, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, root / name)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load() -> dict:
    data = {**DEFAULT, **_read("_llm_settings.json", {})}
    return data if data.get("destination") in DESTINATIONS else {**data, "destination": "none"}


def disclosures() -> dict:
    """送信先ごとの説明文。設定ファイルの項目で既定を上書きする（出典・取得日が欠けた上書きは使わない）。"""
    override = _read("_llm_disclosures.json", {})
    out = {}
    for key, base in DISCLOSURES.items():
        extra = override.get(key) if isinstance(override, dict) else None
        ok = isinstance(extra, dict) and extra.get("source") and extra.get("retrieved")
        out[key] = {**base, **({k: str(v) for k, v in extra.items() if k in base} if ok else {})}
    return out


def _own_ports() -> set[int]:
    ports = {8765}
    for key in ("WEBSPEC2DOC_PORT", "PORT"):
        value = os.environ.get(key, "").strip()
        if value.isdigit():
            ports.add(int(value))
    return ports


def validate_ollama_url(url: str) -> str:
    """NFR-06-23: localhost と社内アドレスだけ。リンクローカルと製品自身のポートは拒否する。"""
    parts = urlsplit(str(url or "").strip())
    host = (parts.hostname or "").lower()
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise ValueError(ALLOWED_TEXT) from None
    if parts.scheme not in ("http", "https") or not host or parts.username or parts.password:
        raise ValueError(ALLOWED_TEXT)
    if host != "localhost":
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            raise ValueError(ALLOWED_TEXT) from None
        if ip.version != 4 or ip in _LINK_LOCAL or not any(ip in n for n in _PRIVATE):
            raise ValueError(ALLOWED_TEXT)
    if port in _own_ports():
        raise ValueError(ALLOWED_TEXT)
    return f"{parts.scheme}://{parts.netloc}"


def check_ollama(url: str, timeout: float = 3.0) -> bool:
    """Ollama の一覧 API に届くか（保存前の接続確認。FR-06-111）。"""
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/tags", timeout=timeout) as res:  # noqa: S310 検証済みの社内 URL
            return 200 <= res.status < 300
    except Exception:
        return False


def save(body: dict, probe=None) -> dict:
    if not isinstance(body, dict) or body.get("destination") not in DESTINATIONS:
        raise ValueError("送信先を「使わない」「OpenAI」「Ollama」から選んでください。")
    data = {**load(), "destination": body["destination"]}
    if body["destination"] == "ollama":
        model = str(body.get("ollama_model") or data["ollama_model"]).strip()
        if not model or len(model) > 100:
            raise ValueError("Ollama のモデル名を入力してください。")
        url = validate_ollama_url(body.get("ollama_url") or data["ollama_url"])
        if not (probe or check_ollama)(url):
            raise ConnectionError(OLLAMA_DOWN)
        data = {**data, "ollama_url": url, "ollama_model": model}
    if body["destination"] == "openai" and body.get("openai_model"):
        data = {**data, "openai_model": str(body["openai_model"]).strip()[:100]}
    _write("_llm_settings.json", data)
    return data


class OpenAICompatClient:
    """既存の src/llm/openai_client.request_structured_json を使う呼び出し口。"""

    def __init__(self, name: str, model: str, base_url: str, api_key: str) -> None:
        self.name, self.model, self._base, self._key = name, model, base_url, api_key

    def request(self, prompt: str, schema_name: str, schema: dict, timeout_sec: float) -> dict:
        try:
            from llm.openai_client import request_structured_json
        except ImportError:  # src が sys.path に無い起動形
            from src.llm.openai_client import request_structured_json
        return request_structured_json(self._key, self.model, prompt, schema_name, schema,
                                       timeout_sec=int(max(timeout_sec, 1)), base_url=self._base,
                                       purpose="docverify_explain")


def client_for(cfg: dict):
    """設定から呼び出し口を作る。「使わない」と、キーの無い OpenAI は None。"""
    dest = cfg.get("destination")
    if dest == "ollama":
        url = validate_ollama_url(cfg.get("ollama_url"))
        return OpenAICompatClient("ollama", cfg.get("ollama_model") or DEFAULT["ollama_model"], f"{url}/v1", "local")
    if dest == "openai":
        key = os.environ.get("WEBSPEC2DOC_LLM_API_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            return None
        return OpenAICompatClient("openai", cfg.get("openai_model") or DEFAULT["openai_model"],
                                  "https://api.openai.com/v1", key)
    return None
