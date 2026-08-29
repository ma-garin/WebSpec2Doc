"""実行環境（dev / stg / prod）の正本ストア。

同じテストを「開発環境で流す」「ステージングで流す」ために必要なのは、
base_url と認証状態（storage state）の切り替えだけである。ここではその 2 つを
ドメイン単位の 1 ファイルに持ち、実行系が env_id を 1 つ受け取るだけで
接続先とログイン済みセッションを解決できるようにする。

保存先: output/<domain>/environments.json

    {"version": 1,
     "environments": [
       {"env_id": "stg", "name": "ステージング", "base_url": "https://stg.example.com",
        "auth_path": "auth_stg.json", "default": true,
        "created_at": "...", "updated_at": "..."}]}

方針は test_step_store.py と揃える:

- 壊れたファイルは黙って空にせず例外で知らせる（環境定義が消えると実行先が変わる）。
- 不正な入力はどこが悪いかを名指しして落とす。既定値へ倒すと、間違った環境へ
  テストが流れても利用者が気づけない。
- auth_path は output/<domain>/ からの相対パスのみ許可する。絶対パスや `..` を
  通すと、環境定義の 1 行で任意ファイルを storage state として読ませられる。
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

STORE_RELATIVE = "environments.json"
SCHEMA_VERSION = 1

# 環境の数。dev/stg/prod + 検証用の枝で 10 を超える運用は想定しない。
# 超過を切り詰めると「登録したのに選べない」になるため、拒否する。
MAX_ENVIRONMENTS = 10
MAX_NAME_LENGTH = 200
MAX_URL_LENGTH = 2000
MAX_AUTH_PATH_LENGTH = 500

# 英数字・ハイフン・アンダースコア 1〜32 文字。ディレクトリ名や CLI 引数に
# そのまま載せるため、記号を広げない。
_ENV_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

# 共通の storage state（環境ごとの auth_path が無いときの既定）。
_SHARED_AUTH_NAME = "auth.json"


class EnvironmentValidationError(ValueError):
    """環境定義が保存できない形をしている。どこが悪いかを必ず名指しする。

    組み込みの EnvironmentError（OSError の別名）と衝突しない名前にしている。
    """


# --------------------------------------------------------------------------
# 保存・読み込み
# --------------------------------------------------------------------------
def store_path(output_root: Path, domain: str) -> Path:
    """環境定義ファイルの保存先を返す。"""
    return Path(output_root) / domain / STORE_RELATIVE


def empty_document(domain: str) -> dict[str, Any]:
    """1 件も登録が無い状態のドキュメント。"""
    return {"version": SCHEMA_VERSION, "domain": domain, "environments": []}


def load(output_root: Path, domain: str) -> dict[str, Any]:
    """保存済みの環境定義を返す。未作成なら空のドキュメント。

    ファイルが読めない・形が違う場合は例外にする。空として返すと、次の save で
    既存の環境定義を丸ごと消してしまう。
    """
    path = store_path(output_root, domain)
    if not path.is_file():
        return empty_document(domain)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise EnvironmentValidationError(
            f"{path} を読めません。ファイルが壊れている可能性があります。"
        ) from None
    if not isinstance(data, dict) or "environments" not in data:
        raise EnvironmentValidationError(f"{path} の形式が想定と違います。")
    return validate(data, domain)


def save(output_root: Path, domain: str, document: dict[str, Any]) -> Path:
    """検証してから保存し、書き込んだパスを返す。"""
    normalized = validate(document, domain)
    path = store_path(output_root, domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 一時ファイル経由で置き換える。書き込み途中で落ちても、
    # 半端な JSON が正本として残らないようにする。
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(path)
    return path


# --------------------------------------------------------------------------
# 検証
# --------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_base_url(raw: Any, where: str) -> str:
    """base_url を検証し、末尾スラッシュを落として返す。"""
    url = str(raw or "").strip()
    if not url:
        raise EnvironmentValidationError(f"{where}.base_url が空です。")
    if len(url) > MAX_URL_LENGTH:
        raise EnvironmentValidationError(
            f"{where}.base_url が長すぎます（{MAX_URL_LENGTH} 文字以内）。"
        )
    if not url.lower().startswith(("http://", "https://")):
        raise EnvironmentValidationError(
            f"{where}.base_url は http:// か https:// で始まる必要があります: {url!r}"
        )
    # スキームだけの `https://` はホストが無く、実行時に無意味な URL になる。
    # 保存できてしまうと「設定したのに動かない」を後工程で調べる羽目になる。
    if not urlparse(url).netloc:
        raise EnvironmentValidationError(
            f"{where}.base_url にホスト名がありません: {url!r}"
        )
    # 末尾スラッシュを落とす。実行系で base_url + パスを連結したときに
    # `//` が生まれ、リダイレクトやセレクタ待ちが揺れるため。
    return url.rstrip("/")


def _normalize_auth_path(raw: Any, where: str) -> str:
    """auth_path を検証する。output/<domain>/ からの相対パスのみ許可。"""
    value = str(raw or "").strip()
    if not value:
        return ""
    if len(value) > MAX_AUTH_PATH_LENGTH:
        raise EnvironmentValidationError(
            f"{where}.auth_path が長すぎます（{MAX_AUTH_PATH_LENGTH} 文字以内）。"
        )
    # Windows 形式の区切りとドライブレターも弾く。POSIX 判定だけだと
    # `C:\\secrets\\auth.json` が「相対パス」として通ってしまう。
    # 改行・タブ・NUL などの制御文字を含むファイル名は、ログや外部コマンドへ
    # 渡ったときに行が割れる。ここで弾く。
    if any(ch < " " or ch == "\x7f" for ch in value):
        raise EnvironmentValidationError(
            f"{where}.auth_path に制御文字は使えません: {value!r}"
        )
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise EnvironmentValidationError(
            f"{where}.auth_path は output/<domain>/ からの相対パスで指定してください"
            f"（絶対パスは使えません）: {value!r}"
        )
    parts = PurePosixPath(normalized).parts
    if any(part == ".." for part in parts):
        raise EnvironmentValidationError(
            f"{where}.auth_path に '..' は使えません"
            f"（output/<domain>/ の外は参照できません）: {value!r}"
        )
    if not parts:
        return ""
    return str(PurePosixPath(*parts))


def validate(document: Any, domain: str) -> dict[str, Any]:
    """保存前の検証と正規化。壊れた入力はどこが悪いか名指しして落とす。"""
    if not isinstance(document, dict):
        raise EnvironmentValidationError("本体がオブジェクトではありません。")
    environments = document.get("environments")
    if not isinstance(environments, list):
        raise EnvironmentValidationError("environments は配列である必要があります。")
    if len(environments) > MAX_ENVIRONMENTS:
        raise EnvironmentValidationError(
            f"環境は {MAX_ENVIRONMENTS} 個までです（指定: {len(environments)} 個）。"
        )

    now = _now()
    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for i, env in enumerate(environments):
        where = f"environments[{i}]"
        if not isinstance(env, dict):
            raise EnvironmentValidationError(f"{where} がオブジェクトではありません。")

        env_id = str(env.get("env_id", "")).strip()
        if not _ENV_ID_RE.match(env_id):
            raise EnvironmentValidationError(
                f"{where}.env_id が不正です"
                f"（英数字・ハイフン・アンダースコア 1〜32 文字）: {env_id!r}"
            )
        if env_id in seen_ids:
            raise EnvironmentValidationError(f"env_id が重複しています: {env_id}")
        seen_ids.add(env_id)

        name = str(env.get("name", "")).strip()
        if not name:
            raise EnvironmentValidationError(f"{where}.name が空です。")
        if len(name) > MAX_NAME_LENGTH:
            raise EnvironmentValidationError(
                f"{where}.name が長すぎます（{MAX_NAME_LENGTH} 文字以内）: {len(name)} 文字"
            )

        created_at = str(env.get("created_at") or "").strip() or now
        normalized.append(
            {
                "env_id": env_id,
                "name": name,
                "base_url": _normalize_base_url(env.get("base_url"), where),
                "auth_path": _normalize_auth_path(env.get("auth_path"), where),
                "default": bool(env.get("default", False)),
                "created_at": created_at,
                "updated_at": now,
            }
        )

    _normalize_defaults(normalized)
    return {
        "version": SCHEMA_VERSION,
        "domain": domain,
        "environments": normalized,
    }


def _normalize_defaults(environments: list[dict[str, Any]]) -> None:
    """default が必ず 1 件だけになるよう整える（破壊的に書き換える）。

    複数 true は先頭のみ残す。1 件も無ければ先頭を default にする。
    「既定が無い／複数ある」状態を許すと、env_id 省略時の実行先が決まらない。
    """
    if not environments:
        return
    flagged = [env for env in environments if env["default"]]
    keep = flagged[0] if flagged else environments[0]
    for env in environments:
        env["default"] = env is keep


# --------------------------------------------------------------------------
# 参照
# --------------------------------------------------------------------------
def get_environment(output_root: Path, domain: str, env_id: str) -> dict[str, Any] | None:
    """env_id で 1 件取り出す。無ければ None。"""
    target = str(env_id or "").strip()
    if not target:
        return None
    for env in load(output_root, domain).get("environments", []):
        if env.get("env_id") == target:
            return env
    return None


def resolve(output_root: Path, domain: str, env_id: str = "") -> dict[str, Any] | None:
    """実行に使う環境を決める。

    - env_id 指定あり: その環境（存在しなければ None。既定へ倒さない。
      指定した環境と違う場所へテストが流れる方が危険なため）
    - env_id 指定なし: default 環境
    - 1 件も登録が無い: None（呼び出し側は従来どおりの単一環境動作へ）
    """
    target = str(env_id or "").strip()
    environments = load(output_root, domain).get("environments", [])
    if not environments:
        return None
    if target:
        return next((e for e in environments if e.get("env_id") == target), None)
    return next((e for e in environments if e.get("default")), environments[0])


def storage_state_path(
    output_root: Path, domain: str, env: dict[str, Any] | None
) -> Path | None:
    """ログイン済みセッション（storage state）の実パスを返す。

    優先順位は 環境ごとの auth_path → 共通の output/<domain>/auth.json → None。
    どちらも「ファイルが実在すること」を条件にする。存在しないパスを返すと
    Playwright 側が起動時に落ち、原因が環境設定だと分かりにくくなる。
    """
    base = Path(output_root) / domain
    if env:
        relative = _normalize_auth_path(env.get("auth_path"), f"environments[{env.get('env_id')}]")
        if relative:
            candidate = base / relative
            if _is_inside(candidate, base) and candidate.is_file():
                return candidate
    shared = base / _SHARED_AUTH_NAME
    return shared if _is_inside(shared, base) and shared.is_file() else None


def _is_inside(candidate: Path, base: Path) -> bool:
    """シンボリックリンクを解決したうえで、base 配下に収まっているか。

    `..` はパス文字列の検証で弾いているが、シンボリックリンクは素通りする。
    output/<domain>/auth.json → 他テナントの auth.json を指すリンクを置かれると、
    テナント分離（scoped_output_dir）を迂回して他人のログイン状態で実行できてしまう。
    リンクを辿った実体の位置で判定する。
    """
    try:
        resolved = candidate.resolve()
        base_resolved = base.resolve()
    except OSError:
        return False
    return resolved == base_resolved or base_resolved in resolved.parents
