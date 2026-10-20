"""canonical.py・files.py（旧 rea_adapter から移設した共通部）の互換と、旧名の別名読込。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from reverse_analysis.canonical import (
    InvalidJsonInput,
    InvalidProviderOutput,
    canonical_digest,
    canonical_json,
    parse_json,
    parse_provider_json,
)
from reverse_analysis.files import (
    VerifiedFile,
    is_safe_relative_path,
    validate_input_directory,
    verify_file,
)
from reverse_analysis.models import (
    ANALYSIS_SNAPSHOT_KEY,
    ENGINE_VERSION_KEY,
    LEGACY_ANALYSIS_SNAPSHOT_KEY,
    LEGACY_ENGINE_VERSION_KEY,
    read_analysis_snapshot_sha,
    read_engine_version,
)

APP = Path(__file__).parent / "fixtures" / "reverse_analysis" / "app"


# ---------------------------------------------------------------- canonical


def test_canonical_json_sorts_keys_by_utf16_code_units_like_javascript() -> None:
    assert canonical_json({"": 1, "\U0001f600": 2, "a": 3}) == '{"a":3,"\U0001f600":2,"":1}'


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1e21, "1e+21"), (1e-7, "1e-7"), (1e-5, "0.00001"), (1.5, "1.5"), (100.0, "100"), (-0.0, "0")],
)
def test_canonical_json_formats_numbers_like_ecmascript(value: float, expected: str) -> None:
    assert canonical_json(value) == expected


def test_canonical_digest_keeps_the_golden_value_from_before_the_move() -> None:
    # 移設前の rea_adapter.canonical_digest と同一入力で同じ値（hashlib sha256 of canonical_json）
    assert canonical_digest({"b": [1, 2.5, "é"], "a": None, "c": 1e21}) == (
        "beba7e95bb521dfd4024e363662b5a52c431abfc5b128433962e9b337b78aabf"
    )
    assert canonical_digest({"a": 1}) == canonical_digest({"a": 1.0})


def test_parse_json_rejects_duplicate_keys_nan_and_truncated_input() -> None:
    for bad in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1', b"\xff"):
        with pytest.raises(InvalidJsonInput):
            parse_json(bad)


def test_old_names_remain_as_aliases() -> None:
    assert parse_provider_json is parse_json and InvalidProviderOutput is InvalidJsonInput


# ---------------------------------------------------------------- files


def test_validate_input_directory_accepts_plain_dir_and_rejects_symlink(tmp_path: Path) -> None:
    ok, problem = validate_input_directory(str(APP))
    assert ok == APP and problem is None
    link = tmp_path / "link"
    link.symlink_to(APP, target_is_directory=True)
    bad, problem = validate_input_directory(str(link))
    assert bad is None and problem is not None and problem.code == "invalid_static_input"
    assert validate_input_directory(str(APP / "dist" / "app.js"))[0] is None
    assert validate_input_directory("")[0] is None


def test_unsafe_tree_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "in"
    root.mkdir()
    (tmp_path / "outside.js").write_text("x")
    (root / "leak.js").symlink_to(tmp_path / "outside.js")
    assert validate_input_directory(str(root))[1] is not None
    (root / "leak.js").unlink()
    os.mkfifo(root / "pipe")
    assert validate_input_directory(str(root))[1] is not None


def test_verify_file_rejects_traversal_symlink_and_missing(tmp_path: Path) -> None:
    root = tmp_path / "in"
    (root / "dist").mkdir(parents=True)
    (root / "dist" / "app.js").write_text("a")
    (tmp_path / "outside.js").write_text("x")
    (root / "dist" / "escape.js").symlink_to(tmp_path / "outside.js")
    assert verify_file(root, "../outside.js").status == "unsafe"
    assert verify_file(root, "/etc/hosts").status == "unsafe"
    assert verify_file(root, "dist/escape.js").status == "unsafe"
    assert verify_file(root, "dist/none.js").status == "missing"
    assert verify_file(root, "dist").status == "not_regular"
    verified = verify_file(root, "dist/app.js")
    assert verified == VerifiedFile("dist/app.js", "verified", verified.sha256, 1)
    assert verified.sha256 is not None and len(verified.sha256) == 64


def test_verify_file_read_error_is_not_raised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "a.js").write_text("a")

    def broken_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(Path, "open", broken_open)
    assert verify_file(tmp_path, "a.js").status == "unreadable"


@pytest.mark.parametrize("bad", ["", "/abs", "a/../b", "a\\b", "a\x00b", "./a", "a//b"])
def test_is_safe_relative_path_rejects_unsafe(bad: str) -> None:
    assert is_safe_relative_path(bad) is False
    assert is_safe_relative_path("dist/app.js") is True


# ---------------------------------------------------------------- 旧名の別名読込


def test_engine_version_reads_new_name_and_falls_back_to_legacy() -> None:
    assert read_engine_version({ENGINE_VERSION_KEY: "webspec2doc-native/1"}) == "webspec2doc-native/1"
    assert read_engine_version({LEGACY_ENGINE_VERSION_KEY: "6.7.0"}) == "6.7.0"
    assert read_engine_version({ENGINE_VERSION_KEY: "n", LEGACY_ENGINE_VERSION_KEY: "o"}) == "n"
    assert read_engine_version({}) is None and read_engine_version(None) is None


def test_analysis_snapshot_reads_new_name_and_falls_back_to_legacy() -> None:
    assert read_analysis_snapshot_sha({ANALYSIS_SNAPSHOT_KEY: "a" * 64}) == "a" * 64
    assert read_analysis_snapshot_sha({LEGACY_ANALYSIS_SNAPSHOT_KEY: "b" * 64}) == "b" * 64
    assert read_analysis_snapshot_sha({}) is None
