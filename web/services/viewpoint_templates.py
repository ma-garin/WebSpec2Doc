from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from web.config import VIEWPOINT_TEMPLATES_DIR
from web.services.viewpoint_blueprints import (
    ViewpointGeneratorError,
    generate,
    list_domains,
)
from web.services.viewpoint_store import ViewpointStoreError, get_viewpoint_store


class TemplateNotFoundError(ViewpointStoreError):
    status_code = 404


def _templates_dir() -> Path:
    return VIEWPOINT_TEMPLATES_DIR


def _load_template_file(key: str) -> dict[str, Any]:
    path = _templates_dir() / f"{key}.json"
    if not path.is_file():
        raise TemplateNotFoundError(f"観点プリセットが見つかりません: {key}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TemplateNotFoundError(f"観点プリセットの読み込みに失敗しました: {key}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("folders"), list):
        raise TemplateNotFoundError(f"観点プリセットの形式が不正です: {key}")
    return data


def list_templates() -> list[dict[str, Any]]:
    """利用可能な観点プリセットの一覧をメタ情報付きで返す。

    出どころが2種類ある:
    - `file`   … data/viewpoint_templates/*.json に手で書いたもの
    - `domain` … 観点定義 × 領域プロファイルから生成するもの（60領域）
    利用者にとっては「どれを土台にするか」の選択肢でしかないため、同じ形にして返す。
    """
    return _file_templates() + _domain_templates()


def _file_templates() -> list[dict[str, Any]]:
    directory = _templates_dir()
    if not directory.is_dir():
        return []
    templates: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = _load_template_file(path.stem)
        except TemplateNotFoundError:
            continue
        folders = data.get("folders", [])
        item_count = sum(len(folder.get("items", [])) for folder in folders)
        templates.append(
            {
                "key": path.stem,
                "source": "file",
                "category": "手書きプリセット",
                "name": data.get("name", path.stem),
                "description": data.get("description", ""),
                "folder_count": len(folders),
                "item_count": item_count,
            }
        )
    return templates


def _domain_templates() -> list[dict[str, Any]]:
    try:
        domains = list_domains()
    except ViewpointGeneratorError:
        return []
    return [
        {
            "key": domain["key"],
            "source": "domain",
            "category": domain["category"],
            "name": domain["name"],
            "description": (
                f"{domain['applied_definitions']}/{domain['total_definitions']} の観点定義が適用。"
                f"想定リスク: {domain['critical_risk']}"
            ),
            "folder_count": 0,
            "item_count": domain["item_count"],
            "excluded_definitions": domain["excluded_definitions"],
        }
        for domain in domains
    ]


def create_set_from_template(template_key: str, name: str = "") -> dict[str, Any]:
    """テンプレートから観点セットを新規作成し、中身を投入して返す。

    既存の apply_template は「今開いているセットに足す」動作で、
    テンプレートを選んでもセット一覧は増えない。用意した観点を使い始めるのに
    「セットを作る → テンプレートを選ぶ」の2手が要り、テンプレートの存在が
    セット一覧から見えなかった。1操作でセットとして現れるようにする。
    """
    if template_key in _domains_by_key():
        return _create_set_from_domain(template_key, name)
    data = _load_template_file(template_key)
    store = get_viewpoint_store()
    created = store.create_set(
        {
            "name": (name or str(data.get("name", template_key))).strip(),
            "description": str(data.get("description", "")),
        }
    )
    result = apply_template(created["id"], template_key)
    published = _publish_initial_version(store, created["id"], str(data.get("name", template_key)))
    return {"set": store.get_set(created["id"]), "published": published, **result}


@lru_cache(maxsize=1)
def _domains_by_key() -> dict[str, Any]:
    """領域キーから領域メタを引く。

    テンプレート適用のたびに 60領域 × 99定義 の適用判定を回すのは無駄。
    カタログはプロセス起動中に変わらないので1回で足りる。
    """
    try:
        return {domain["key"]: domain for domain in list_domains()}
    except ViewpointGeneratorError:
        return {}


def _create_set_from_domain(domain_key: str, name: str = "") -> dict[str, Any]:
    """領域から観点を生成してセットにする。

    生成物は保存するが、生成の元（観点定義と領域プロファイル）は掛け算した形では
    保持しない。定義を直したときに再生成できる形を保つため。
    """
    generated = generate(domain_key)
    domain = generated["domain"]
    store = get_viewpoint_store()
    created = store.create_set(
        {
            "name": (name or str(domain["name"])).strip(),
            "description": (
                f"{domain['category']} / {domain['name']}。"
                f"想定リスク: {domain['critical_risk']}"
            ),
            "applicability": {
                "source": "domain_blueprint",
                "domain_key": domain_key,
                "applied": generated["applied_definitions"],
                "excluded": generated["excluded_definitions"],
            },
        }
    )
    set_id = created["id"]
    version_number = int(store.ensure_draft(set_id)["version_number"])

    folder_keys: dict[str, str] = {}
    for folder_name in generated["folders"]:
        folder = store.create_folder(set_id, {"name": folder_name}, version_number=version_number)
        folder_keys[folder_name] = folder["persistent_key"]
    for item in generated["items"]:
        payload = {
            **{k: v for k, v in item.items() if k != "folder"},
            "node_type": "viewpoint",
            "parent_key": folder_keys[item["folder"]],
        }
        store.create_item(set_id, payload, version_number=version_number)

    published = _publish_initial_version(store, set_id, str(domain["name"]))
    return {
        "set": store.get_set(set_id),
        "published": published,
        "template_key": domain_key,
        "template_name": domain["name"],
        "created_folders": len(generated["folders"]),
        "created_items": len(generated["items"]),
        "excluded_definitions": generated["excluded_definitions"],
    }


def _publish_initial_version(store: Any, set_id: str, template_name: str) -> bool:
    """作成直後の版を公開する。公開できなければ下書きのまま False を返す。

    観点の選択（select_snapshot・選択API）も、セット一覧の件数集計も、
    published 版しか見ない。下書きのままだと「250観点を入れたのに 0 件と表示され、
    QA実行の候補にも出てこない」状態になり、テンプレートが使えない。
    テンプレートは中身が確定した状態で配布するものなので、作成と同時に v1 とする。
    """
    draft = store.ensure_draft(set_id)
    try:
        store.publish(
            set_id,
            int(draft["version_number"]),
            revision=None,
            change_reason=f"テンプレート「{template_name}」から作成",
        )
    except ViewpointStoreError:
        return False
    return True


def apply_template(set_id: str, template_key: str) -> dict[str, Any]:
    """プリセットのフォルダ・観点アイテムを、指定セットの下書き版に投入する。

    フォルダ→アイテムの順に既存の create_folder/create_item を呼び出すだけで、
    バージョン管理・整合性検証は ViewpointStore 側の既存ロジックにそのまま乗る
    （プリセット投入専用の別経路を作らない）。

    同じテンプレートを二度適用しても中身は増えない。既にある同名のフォルダ・観点は
    飛ばし、足りないものだけを足す。テンプレートは「この内容を揃える」ものであって
    「押した回数だけ積む」ものではない。防いでいなかったため、47回押した既定セットに
    同名フォルダが47組・観点469件溜まり、分類ツリーが読めなくなった。
    """
    data = _load_template_file(template_key)
    store = get_viewpoint_store()
    draft = store.ensure_draft(set_id)
    version_number = int(draft["version_number"])

    existing = store.list_items(set_id, version_number, resolved=False)
    folder_keys = {
        str(i["name"]): str(i["persistent_key"]) for i in existing if i["node_type"] == "folder"
    }
    existing_names = {str(i["name"]) for i in existing if i["node_type"] == "viewpoint"}

    created_folders = 0
    created_items = 0
    skipped_items = 0
    for folder in data.get("folders", []):
        folder_name = str(folder.get("name", "")).strip()
        if not folder_name:
            continue
        parent_key = folder_keys.get(folder_name)
        if parent_key is None:
            parent_key = store.create_folder(
                set_id, {"name": folder_name}, version_number=version_number
            )["persistent_key"]
            folder_keys[folder_name] = parent_key
            created_folders += 1
        for item in folder.get("items", []):
            name = str(item.get("name", "")).strip()
            if name in existing_names:
                skipped_items += 1
                continue
            payload = {**item, "node_type": "viewpoint", "parent_key": parent_key}
            store.create_item(set_id, payload, version_number=version_number)
            existing_names.add(name)
            created_items += 1

    return {
        "template_key": template_key,
        "template_name": data.get("name", template_key),
        "skipped_items": skipped_items,
        "created_folders": created_folders,
        "created_items": created_items,
    }
