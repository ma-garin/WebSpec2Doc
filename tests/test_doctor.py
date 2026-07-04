"""環境ドクター（src/doctor.py）のユニットテスト。"""

from __future__ import annotations

from doctor import (
    SUPPORTED_PYTHON_MAX_EXCLUSIVE,
    SUPPORTED_PYTHON_MIN,
    check_dependency_pins,
    check_python_version,
    parse_requirement_pins,
    run_all_checks,
)


class TestPythonVersionCheck:
    def test_supported_versions_pass(self) -> None:
        assert check_python_version((3, 11, 15)).ok is True
        assert check_python_version((3, 12, 13)).ok is True

    def test_too_new_fails_with_fix(self) -> None:
        """playwright 1.44 の wheel が無い 3.13+ は FAIL と修正手順を出す。"""
        result = check_python_version((3, 13, 0))
        assert result.ok is False
        assert "3.12" in result.fix

    def test_too_old_fails(self) -> None:
        assert check_python_version((3, 10, 0)).ok is False

    def test_bounds_are_playwright_144_range(self) -> None:
        assert SUPPORTED_PYTHON_MIN == (3, 11)
        assert SUPPORTED_PYTHON_MAX_EXCLUSIVE == (3, 13)


class TestRequirementPins:
    def test_parses_pins_and_ignores_comments(self) -> None:
        pins = parse_requirement_pins(
            "\n".join(
                [
                    "# クローリング",
                    "playwright==1.44.0",
                    "PyYAML==6.0.1  # コメント付き",
                    "Pillow>=11.0.0",  # 範囲指定はピンでないため対象外
                    "",
                ]
            )
        )
        assert pins == {"playwright": "1.44.0", "PyYAML": "6.0.1"}

    def test_installed_pin_match_passes(self) -> None:
        """この環境に導入済みの playwright はピンと一致して PASS になる。"""
        results = check_dependency_pins({"playwright": "1.44.0"})
        assert len(results) == 1
        assert results[0].ok is True

    def test_pin_mismatch_fails_with_fix_command(self) -> None:
        results = check_dependency_pins({"playwright": "9.99.9"})
        assert results[0].ok is False
        assert "playwright==9.99.9" in results[0].fix

    def test_missing_package_reported(self) -> None:
        results = check_dependency_pins({"PyYAML": "6.0.1", "flask": "0.0.0"})
        # flask は導入済みだがバージョン不一致、PyYAML は一致
        by_name = {r.name: r for r in results}
        assert by_name["依存: PyYAML"].ok is True
        assert by_name["依存: flask"].ok is False


class TestRunAllChecks:
    def test_all_checks_run_in_this_environment(self) -> None:
        """この環境（正しくセットアップ済み）では致命 FAIL が出ない。"""
        results = run_all_checks()
        names = [r.name for r in results]
        assert "Python バージョン" in names
        assert "Chromium ランタイム" in names
        assert "ローカルURLガード" in names
        assert all(r.ok for r in results), [r.detail for r in results if not r.ok]
