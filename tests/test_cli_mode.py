"""CLI モード（System 03）のテスト。

画面を持たない実行経路のため、「端末から叩いて期待どおりの結果と終了コードが返るか」
を検証の中心にする。CI から成否を判定できることが要件のため、終了コードは特に厚く見る。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import app as appmod  # noqa: E402

# TestRunResult は pytest がテストクラスと誤認するため別名で取り込む
from web.services.cli_runner import AutoRunResult  # noqa: E402
from web.services.cli_runner import TestRunResult as RunResult  # noqa: E402

from cli import build_parser, cmd_review, cmd_show, cmd_sites, cmd_test  # noqa: E402

H = {"Host": "127.0.0.1"}


class TestExitCodes:
    """終了コードは CI の判定に直結する。取り違えると失敗を見逃す。"""

    @pytest.mark.parametrize(
        ("status", "ok", "error", "expected"),
        [
            ("complete", True, "", 0),
            ("complete", False, "", 1),
            ("failed", False, "落ちた", 2),
            ("cancelled", False, "", 130),
        ],
    )
    def test_autorun_exit_code(self, status, ok, error, expected) -> None:
        r = AutoRunResult(
            ok=ok,
            status=status,
            job_id="x",
            url="http://e.test/",
            domain="e.test",
            elapsed_sec=1.0,
            error=error,
        )
        assert r.exit_code() == expected

    @pytest.mark.parametrize(
        ("failed", "error", "expected"),
        [(0, "", 0), (3, "", 1), (0, "実行できません", 2)],
    )
    def test_test_exit_code(self, failed, error, expected) -> None:
        r = RunResult(ok=failed == 0, domain="e.test", failed=failed, error=error)
        assert r.exit_code() == expected


class TestParser:
    def test_subcommands_are_available(self) -> None:
        """GUI の 3 系統が端末から届くこと。"""
        p = build_parser()
        for argv in (
            ["autorun", "--url", "http://e.test/"],
            ["test", "--domain", "e.test"],
            ["sites"],
            ["show", "--domain", "e.test"],
            ["viewpoints"],
        ):
            assert p.parse_args(argv).command == argv[0]

    @pytest.mark.parametrize(
        "argv",
        [["sites", "--json"], ["--json", "sites"], ["show", "--domain", "e.test", "--json"]],
    )
    def test_common_options_accepted_before_and_after_subcommand(self, argv) -> None:
        """`sites --json` と `--json sites` のどちらでも通ること。

        サブコマンドの後ろに置くのが自然な書き方なのに弾かれ、
        自動化から JSON を受け取れないという不具合があった。
        """
        ns = build_parser().parse_args(argv)
        assert ns.json is True

    def test_output_option_after_subcommand_wins(self, tmp_path) -> None:
        ns = build_parser().parse_args(["sites", "--output", str(tmp_path)])
        assert str(ns.output) == str(tmp_path)

    def test_doc_delegates_help_to_main_cli(self) -> None:
        """`doc --help` は本体 CLI のヘルプを見せること。

        ラッパ自身のヘルプで止まると、実際に使える --format / --compare / --auth
        などが一切分からず、doc サブコマンドが使い物にならなかった。
        """
        import subprocess
        import sys as _sys

        r = subprocess.run(
            [_sys.executable, "src/cli.py", "doc", "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = r.stdout + r.stderr
        assert "--format" in out or "--compare" in out

    def test_unknown_option_is_rejected(self) -> None:
        """知らないオプションを黙って捨てると、指定が効かないのに成功に見える。"""
        from cli import main

        with pytest.raises(SystemExit) as exc:
            main(["sites", "--no-such-option"])
        assert exc.value.code != 0


class TestReadCommands:
    def _args(self, tmp_path: Path, **kw):
        ns = build_parser().parse_args(kw.pop("argv"))
        ns.output = tmp_path
        for k, v in kw.items():
            setattr(ns, k, v)
        return ns

    def test_sites_lists_analyzed_domains(self, tmp_path, capsys) -> None:
        (tmp_path / "a.test").mkdir()
        (tmp_path / "a.test" / "report.json").write_text(
            json.dumps({"screens": [{"forms": [{"fields": [1, 2]}]}]}), encoding="utf-8"
        )
        (tmp_path / ".hidden").mkdir()
        code = cmd_sites(self._args(tmp_path, argv=["sites"]), [])
        out = capsys.readouterr().out
        assert code == 0
        assert "a.test" in out
        assert ".hidden" not in out  # 隠しディレクトリはサイトではない

    def test_show_reports_missing_domain(self, tmp_path, capsys) -> None:
        """存在しないドメインを成功で返すと、成果物が無いのに有ると誤解される。"""
        code = cmd_show(self._args(tmp_path, argv=["show", "--domain", "nope"]), [])
        assert code == 2
        assert "見つかりません" in capsys.readouterr().out

    def test_show_lists_artifacts_and_run_result(self, tmp_path, capsys) -> None:
        d = tmp_path / "a.test"
        (d / "testcases").mkdir(parents=True)
        (d / "report.json").write_text("{}", encoding="utf-8")
        (d / "testcases" / "run_result.json").write_text(
            json.dumps({"summary": {"passed": 5, "failed": 1, "total": 6}}), encoding="utf-8"
        )
        code = cmd_show(self._args(tmp_path, argv=["show", "--domain", "a.test"]), [])
        out = capsys.readouterr().out
        assert code == 0
        assert "PASS 5" in out and "FAIL 1" in out

    @pytest.mark.parametrize(
        "domain",
        [
            "",  # 空文字は出力先そのものを指してしまう
            "   ",
            "../etc",  # 出力先の外
            "a/b",
            "a\\b",
            ".hidden",
        ],
    )
    def test_show_rejects_domain_that_is_not_a_domain(self, tmp_path, capsys, domain) -> None:
        """ドメインとして扱えない指定は、一覧が出て成功したように見せてはいけない。"""
        code = cmd_show(self._args(tmp_path, argv=["show", "--domain", domain]), [])
        assert code == 2
        assert "ドメイン名として扱えません" in capsys.readouterr().out

    def test_test_rejects_domain_that_is_not_a_domain(self, tmp_path, capsys) -> None:
        """テスト実行側も同じ入口で弾く（実行してから気づくのでは遅い）。"""
        code = cmd_test(self._args(tmp_path, argv=["test", "--domain", ""]), [])
        assert code == 2
        assert "ドメイン名として扱えません" in capsys.readouterr().out

    def test_bad_domain_is_reported_in_json_too(self, tmp_path, capsys) -> None:
        args = self._args(tmp_path, argv=["show", "--domain", ""])
        args.json = True
        assert cmd_show(args, []) == 2
        data = json.loads(capsys.readouterr().out)
        assert data["command"] == "show"
        assert data["error"] == "invalid domain"

    def test_json_output_is_machine_readable(self, tmp_path, capsys) -> None:
        (tmp_path / "a.test").mkdir()
        args = self._args(tmp_path, argv=["sites"])
        args.json = True
        cmd_sites(args, [])
        data = json.loads(capsys.readouterr().out)
        assert data["command"] == "sites"
        assert [s["domain"] for s in data["sites"]] == ["a.test"]


class TestCliModePage:
    """入り口に System 03 が並び、案内ページが開けること。"""

    @pytest.fixture
    def client(self):
        return appmod.app.test_client()

    def test_systems_page_offers_three_systems(self, client) -> None:
        html = client.get("/systems", headers=H).get_data(as_text=True)
        assert "System 01" in html
        assert "System 02" in html
        assert "System 03" in html
        assert 'href="/cli"' in html

    def test_cli_page_renders(self, client) -> None:
        res = client.get("/cli", headers=H)
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert "CLI モード" in html
        assert "src/cli.py" in html
        # 終了コードの説明は CI 組み込みの前提なので必ず載せる
        assert "130" in html


class TestViewpointAndReviewSubcommands:
    """GUI でしか行えなかった観点セットの版操作とレビュー更新を端末から使えること。

    移行元は PR #96（別 CLI として実装されていた）。入口を 2 つに増やすと
    利用者がどちらを使えばよいか分からなくなるため、既存の cli.py へ統合した。
    """

    def test_viewpoints_without_action_still_lists(self) -> None:
        """後方互換: 引数なしの `viewpoints` は従来どおり一覧。"""
        ns = build_parser().parse_args(["viewpoints"])
        assert ns.command == "viewpoints"
        assert ns.vp_action == "list"

    @pytest.mark.parametrize(
        "argv,action",
        [
            (["viewpoints", "show", "S1"], "show"),
            (["viewpoints", "versions", "S1"], "versions"),
            (["viewpoints", "items", "S1"], "items"),
            (["viewpoints", "diff", "S1", "--from", "1", "--to", "2"], "diff"),
            (["viewpoints", "export", "S1"], "export"),
            (["viewpoints", "import", "S1", "vp.csv"], "import"),
            (["viewpoints", "publish", "S1", "2"], "publish"),
            (["viewpoints", "rollback", "S1", "1"], "rollback"),
            (["viewpoints", "templates"], "templates"),
            (["viewpoints", "apply-template", "S1", "iso25010"], "apply-template"),
            (["viewpoints", "create", "--name", "新セット"], "create"),
        ],
    )
    def test_viewpoint_actions_are_reachable(self, argv, action) -> None:
        assert build_parser().parse_args(argv).vp_action == action

    def test_review_requires_an_action(self) -> None:
        """`review` だけでは何をするか決まらない。黙って 0 で返さず弾く。"""
        with pytest.raises(SystemExit) as e:
            build_parser().parse_args(["review"])
        assert e.value.code == 2

    def test_review_rejects_domain_that_is_not_a_domain(self, tmp_path, capsys) -> None:
        ns = build_parser().parse_args(["review", "cases", ""])
        ns.output = tmp_path
        assert cmd_review(ns, []) == 2
        assert "ドメイン名として扱えません" in capsys.readouterr().out

    def test_review_rejects_unknown_status(self, tmp_path, capsys) -> None:
        """状態を取り違えたまま成功で返すと、更新できていないことに気づけない。"""
        ns = build_parser().parse_args(["review", "update", "a.test", "TC-1", "--status", "bogus"])
        ns.output = tmp_path
        assert cmd_review(ns, []) == 2
        out = capsys.readouterr().out
        assert "指定できない状態です" in out
        assert "approved" in out  # 指定できる値を示すこと

    def test_review_update_then_cases_reflects_it(self, tmp_path, capsys) -> None:
        """更新した状態が一覧に出ること（保存されないと気づけないため）。"""
        domain = "review-cli.test"
        (tmp_path / domain).mkdir()
        (tmp_path / domain / "playwright_candidates.json").write_text(
            json.dumps([{"id": "PW-0001", "title": "画面表示スモーク"}]), encoding="utf-8"
        )

        ns = build_parser().parse_args(
            ["review", "update", domain, "PW-0001", "--status", "approved", "--comment", "OK"]
        )
        ns.output = tmp_path
        assert cmd_review(ns, []) == 0
        capsys.readouterr()

        ns = build_parser().parse_args(["review", "cases", domain, "--json"])
        ns.output = tmp_path
        assert cmd_review(ns, []) == 0
        cases = json.loads(capsys.readouterr().out)["cases"]
        assert cases[0]["status"] == "approved"
        assert cases[0]["comment"] == "OK"

    def test_frozen_advances_the_version(self, tmp_path, capsys) -> None:
        """frozen は『この内容で確定した』印なので版を進める。"""
        domain = "review-cli2.test"
        (tmp_path / domain).mkdir()
        (tmp_path / domain / "playwright_candidates.json").write_text(
            json.dumps([{"id": "PW-0001", "title": "x"}]), encoding="utf-8"
        )
        for status, want in (("approved", 1), ("frozen", 2)):
            ns = build_parser().parse_args(
                ["review", "update", domain, "PW-0001", "--status", status, "--json"]
            )
            ns.output = tmp_path
            assert cmd_review(ns, []) == 0
            assert json.loads(capsys.readouterr().out)["version"] == want
