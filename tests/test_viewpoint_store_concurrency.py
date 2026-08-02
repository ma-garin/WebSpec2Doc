"""観点DBへの並行アクセスを検証する。

これまでの検証は単一プロセスに限られていた。実際には次の並行が起こる。

- AutoRun が背景スレッドで観点を読む間に、利用者が画面から編集する
- 開発サーバーと E2E が同じDBを開く（隔離前はこれが起きていた）
- 複数プロセスが同時に起動し、それぞれがマイグレーションを走らせる

SQLite は既定でファイルロックを使うため、同時書き込みは待つか失敗する。
待って成功するのか、黙って壊れるのかを確かめる。
"""

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from web.services.viewpoint_store import SCHEMA_VERSION, ViewpointStore


@pytest.fixture()
def seed(tmp_path: Path) -> Path:
    path = tmp_path / "seed.csv"
    path.write_text(
        "summary_type,name,count\ncategory_l2,既定観点,1\n", encoding="utf-8"
    )
    return path


class TestConcurrentMigration:
    """複数プロセスが同時にマイグレーションしても壊れないこと。

    開発サーバーと E2E、あるいは複数のワーカーが同時に起動しうる。
    片方が途中まで進めた状態を、もう片方が壊さないかを見る。
    """

    def test_parallel_initialize_converges(self, tmp_path: Path, seed: Path) -> None:
        db_path = tmp_path / "viewpoints.db"
        errors: list[Exception] = []

        def initialize() -> None:
            try:
                ViewpointStore(db_path, seed).initialize()
            except Exception as exc:  # noqa: BLE001 - 収集して後で検査する
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=8) as pool:
            for _ in range(8):
                pool.submit(initialize)

        assert not errors, f"同時初期化で失敗: {errors}"
        with sqlite3.connect(db_path) as conn:
            assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_VERSION

    def test_standard_set_is_seeded_once(self, tmp_path: Path, seed: Path) -> None:
        """同時初期化で既定セットが重複しないこと。

        重複すると、どちらが既定かがDBの並び順で決まる。
        """
        db_path = tmp_path / "viewpoints.db"
        with ThreadPoolExecutor(max_workers=8) as pool:
            for _ in range(8):
                pool.submit(lambda: ViewpointStore(db_path, seed).initialize())

        store = ViewpointStore(db_path, seed)
        store.initialize()
        names = [s["name"] for s in store.list_sets()]
        assert len(names) == len(set(names)), f"セットが重複した: {names}"
        assert len([s for s in store.list_sets() if s["is_default"]]) == 1


class TestConcurrentWrites:
    """同時書き込みが、黙って失われないこと。"""

    def test_parallel_item_creation_keeps_every_item(
        self, tmp_path: Path, seed: Path
    ) -> None:
        """並行して観点を足しても、書いた分がすべて残ること。

        片方の書き込みが黙って消えると、観点表に穴が空いたまま
        「作成しました」と表示される。
        """
        store = ViewpointStore(tmp_path / "viewpoints.db", seed)
        store.initialize()
        created = store.create_set({"name": "並行書き込みセット"})
        version = int(store.ensure_draft(created["id"])["version_number"])

        failures: list[Exception] = []
        lock = threading.Lock()

        def add(index: int) -> None:
            try:
                store.create_item(
                    created["id"],
                    {"name": f"観点{index:02d}", "category": "並行"},
                    version_number=version,
                )
            except Exception as exc:  # noqa: BLE001
                with lock:
                    failures.append(exc)

        with ThreadPoolExecutor(max_workers=8) as pool:
            for index in range(24):
                pool.submit(add, index)

        items = [
            item
            for item in store.list_items(created["id"], version, resolved=False)
            if item["node_type"] == "viewpoint"
        ]
        # 失敗したものは失敗として返っているはずで、黙って消えていない
        assert len(items) + len(failures) == 24, (
            f"書いた24件のうち {len(items)} 件しか残らず、"
            f"失敗も {len(failures)} 件しか報告されていない"
        )

    def test_only_one_default_survives_parallel_switching(
        self, tmp_path: Path, seed: Path
    ) -> None:
        """既定セットを同時に切り替えても、既定が1つに収まること。

        複数が既定になると、どれで AutoRun が走るかが偶然で決まる。
        """
        store = ViewpointStore(tmp_path / "viewpoints.db", seed)
        store.initialize()
        sets = [
            store.create_set({"name": f"セット{index}"}) for index in range(4)
        ]
        for created in sets:
            version = int(store.ensure_draft(created["id"])["version_number"])
            store.create_item(
                created["id"],
                {"name": f"観点-{created['name']}", "category": "並行"},
                version_number=version,
            )
            store.publish(created["id"], version, revision=None, change_reason="初回")

        def make_default(target: dict[str, Any]) -> None:
            try:
                current = store.get_set(target["id"])
                store.update_set(
                    target["id"], {"is_default": True, "revision": current["revision"]}
                )
            except Exception:  # noqa: BLE001 - 競合で弾かれるのは正しい
                pass

        with ThreadPoolExecutor(max_workers=4) as pool:
            for created in sets:
                pool.submit(make_default, created)

        defaults = [s for s in store.list_sets() if s["is_default"]]
        assert len(defaults) == 1, f"既定が {len(defaults)} 件ある: {[s['name'] for s in defaults]}"


class TestConcurrentReadDuringWrite:
    """書き込み中に読んでも、途中の状態が見えないこと。"""

    def test_snapshot_never_sees_partial_publish(self, tmp_path: Path, seed: Path) -> None:
        """公開の途中経過が、観点の選択に見えないこと。

        AutoRun は実行開始時に観点を固定する。途中の状態を掴むと、
        「どの観点でテストしたか」の記録が実際と食い違う。
        """
        store = ViewpointStore(tmp_path / "viewpoints.db", seed)
        store.initialize()
        seen: list[int] = []
        errors: list[Exception] = []

        def read() -> None:
            try:
                seen.append(store.select_snapshot({"url": "https://x.test"})["viewpoint_count"])
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        def write(index: int) -> None:
            try:
                created = store.create_set({"name": f"追加{index}"})
                version = int(store.ensure_draft(created["id"])["version_number"])
                store.create_item(
                    created["id"],
                    {"name": f"追加観点{index}", "category": "並行"},
                    version_number=version,
                )
                store.publish(created["id"], version, revision=None, change_reason="並行")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=6) as pool:
            for index in range(6):
                pool.submit(write, index)
                pool.submit(read)

        assert not errors, f"並行読み書きで失敗: {errors}"
        # 既定セットの観点数は書き込みの影響を受けない
        assert all(count > 0 for count in seen), f"0件のスナップショットを掴んだ: {seen}"


class TestCrossProcessMigration:
    """別プロセスから同時に初期化しても壊れないこと。

    スレッド並行では `_init_lock` が効くが、プロセスをまたぐと効かない。
    開発サーバーと E2E、複数ワーカーは別プロセスで動く。

    手元では 6プロセス × 20ラウンド（120回起動）で失敗ゼロを確認した。
    ここでは1ラウンドだけ回す（全体のテスト時間を延ばさないため）。
    タイミング依存の検証を1回で断定しない規律（AGENTS.md V-4）に従い、
    疑わしいときは同じ形で回数を増やして確かめる。
    """

    def test_parallel_processes_converge(self, tmp_path: Path, seed: Path) -> None:
        import subprocess
        import sys
        import textwrap

        script = tmp_path / "init_store.py"
        script.write_text(
            textwrap.dedent(
                f"""
                import sys
                sys.path.insert(0, {str(Path.cwd())!r})
                from web.services.viewpoint_store import ViewpointStore
                store = ViewpointStore({str(tmp_path / "viewpoints.db")!r}, {str(seed)!r})
                store.initialize()
                sets = store.list_sets()
                print(len(sets), sum(1 for s in sets if s["is_default"]))
                """
            ),
            encoding="utf-8",
        )
        processes = [
            subprocess.Popen(  # noqa: S603 - 生成した検証用スクリプトのみ実行する
                [sys.executable, str(script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(6)
        ]
        results = [proc.communicate() for proc in processes]

        for index, (out, err) in enumerate(results):
            assert processes[index].returncode == 0, f"プロセス{index}が失敗: {err[-400:]}"
            _sets, defaults = out.split()
            assert defaults == "1", f"プロセス{index}から見た既定セットが{defaults}件"
