"""テスト側の不具合と判定された欠陥を、テストファイル自身を直して解消する。

triage.classify が kind="script" と判定した欠陥だけがここを通る。
製品コード（サイト側のリポジトリ）には一切触れない。触るのは .spec.ts の
該当 test ブロックだけで、書き換える前に必ずバックアップを取る
（元に戻せることを担保するため。エージェントによる修正と違い、これは
ロールバックの判断を人に預けない——1 行の文言置換なので機械的に戻せる）。
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from web.services.egress_gateway import EgressPolicy
from web.services.playwright_executor import run_playwright

try:
    from crawler.url_safety import _local_targets_allowed
except ImportError:  # noqa: BLE001 - src がまだ sys.path に無い実行経路への保険
    def _local_targets_allowed() -> bool:
        return False

#: test( の呼び出し検出。playwright_executor._count_tests_in_spec と同じ条件
#: （メソッド呼び出し `.test(` を誤検出しない）。
_NEXT_TEST_RE = re.compile(r"(?<![.\w])test\s*\(")


@dataclass(frozen=True)
class ScriptFix:
    """テストファイル 1 箇所の置換結果。"""

    ok: bool
    spec_path: str
    old: str
    new: str
    backup_path: str
    message: str = ""


def find_spec(out_dir: Path, domain: str) -> Path | None:
    """spec_path が分からないときのフォールバック探索。"""
    base = Path(out_dir) / domain
    for candidate in (
        base / "testcases" / "testcases.spec.ts",
        Path("qa_process") / "autorun.spec.ts",
    ):
        if candidate.is_file():
            return candidate
    return None


def _find_test_block(text: str, test_title: str) -> tuple[int, int] | None:
    """test_title を含む test( ... ) ブロックの (開始, 終了) 位置。

    test_title は TC-ID を含む場合も含まない場合もあるため、タイトル文字列の
    部分一致で `test("...")` の呼び出しを探す（先頭一致は要求しない）。
    次の test( 呼び出し、無ければファイル末尾までを 1 ブロックとする。
    """
    if not test_title:
        return None
    pattern = re.compile(
        r"""test\(\s*['"][^'"]*""" + re.escape(test_title) + r"""[^'"]*['"]"""
    )
    match = pattern.search(text)
    if not match:
        return None
    start = match.start()
    next_match = _NEXT_TEST_RE.search(text, match.end())
    end = next_match.start() if next_match else len(text)
    return start, end


def replace_in_test(
    spec_path: Path, test_title: str, old: str, new: str, *, backup_dir: Path
) -> ScriptFix:
    """test_title のブロック内だけで old → new に置き換える。

    ブロックが見つからない・old がブロック内に無い場合は ok=False を返す
    （書き換えない。「見つからないので何もしなかった」を隠さない）。
    """
    spec_key = str(spec_path)
    if not test_title or not old:
        return ScriptFix(False, spec_key, old, new, "", "テスト名または置換元の文言が空です")
    try:
        text = spec_path.read_text(encoding="utf-8")
    except OSError as exc:
        return ScriptFix(False, spec_key, old, new, "", f"テストファイルを読めません: {exc}")

    bounds = _find_test_block(text, test_title)
    if bounds is None:
        return ScriptFix(False, spec_key, old, new, "", f"テスト「{test_title}」が見つかりません")
    start, end = bounds
    block = text[start:end]
    if old not in block:
        return ScriptFix(False, spec_key, old, new, "", f"テスト内に「{old}」が見つかりません")

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"{spec_path.name}.{stamp}.ts"
    shutil.copy2(spec_path, backup_path)

    new_text = text[:start] + block.replace(old, new) + text[end:]
    spec_path.write_text(new_text, encoding="utf-8")
    return ScriptFix(True, spec_key, old, new, str(backup_path), f"「{old}」→「{new}」に置き換えました")


def restore(fix: ScriptFix) -> None:
    """backup を対象ファイルへ戻す。backup が無ければ何もしない。"""
    if not fix.backup_path:
        return
    backup = Path(fix.backup_path)
    if backup.is_file():
        shutil.copy2(backup, Path(fix.spec_path))


def rerun_single(spec_path: Path, output_dir: Path, test_title: str) -> tuple[bool, str]:
    """その test_title の 1 件だけを再実行する。

    返り値の文字列は report_doc._verify_text と同じ「通過 1 / 1」の形にし、
    そのまま報告書の検証欄へ出せるようにする。
    """
    grep = re.escape(test_title)
    # 対象がローカル開発サーバ（127.0.0.1 等）のとき、K1 送信ゲートウェイの既定
    # （allow_local=False）のままだと再実行そのものが net::ERR_FAILED で必ず失敗する。
    # 02/03 と同じ判断（WEBSPEC2DOC_ALLOW_LOCAL）に揃える。
    policy = EgressPolicy(allow_local=_local_targets_allowed())
    result = run_playwright(spec_path, output_dir, grep=grep, egress_policy=policy)
    total = int(result.get("total") or 0)
    passed = int(result.get("passed") or 0)
    failed = int(result.get("failed") or 0)
    if total == 0:
        error = str(result.get("error") or "結果を取得できませんでした")
        return False, f"実行できませんでした（{error}）"
    if failed:
        return False, f"失敗 {failed} / {total}"
    return True, f"通過 {passed} / {total}"
