"""normalize.py に残した純関数と型の契約（REA 形式の入力は持たない）。

守るべきは「静的構文の事実を実測や確定仕様に昇格させないこと」。同位置の候補を捨てない・
同じ endpoint を 1 件に縮めない・検証できないファイルを黙って受け入れない。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from reverse_analysis import normalize
from reverse_analysis.files import VerifiedFile
from reverse_analysis.models import Coverage, SourceLocation, StaticCandidate, make_id
from reverse_analysis.normalize import (
    LIMIT_DIGEST_MISMATCH,
    LIMIT_FILE_NOT_VERIFIED,
    LIMIT_LOCATION_COLLISION,
    LIMIT_SHARED_ENDPOINT,
    StaticNormalization,
    _collision_diagnostics,
    _file_diagnostics,
    _file_limits,
    _mark_shared_endpoints,
    _separate_collisions,
)


def cand(cid: str, path: str, line: int, *, limits: tuple[str, ...] = ()) -> StaticCandidate:
    return StaticCandidate(
        id=cid, kind="api", artifact_path="dist/app.js", artifact_sha256="a" * 64,
        location=SourceLocation("dist/app.js", "line_column_utf16", line, 0, line, 5),
        resolution="exact", epistemic_state="observed", authority="syntax",
        method="GET", path=path, limitations=limits,
    )  # fmt: skip


def test_normalize_does_not_import_the_removed_adapter() -> None:
    sys.modules.pop("reverse_analysis.rea_adapter", None)
    importlib.reload(normalize)
    assert "reverse_analysis.rea_adapter" not in sys.modules
    source = Path(normalize.__file__).read_text(encoding="utf-8")
    assert "rea_adapter" not in source


def test_colliding_candidates_at_one_location_are_all_kept() -> None:
    a, b = cand("sc_x", "/api/a", 3), cand("sc_x", "/api/b", 3)
    out = _separate_collisions({"sc_x": [(a, "n1#o1"), (b, "n2#o1")]})
    assert len(out) == 2 and len({c.id for c in out}) == 2
    assert out[0].id == make_id("sc", "sc_x", "n1#o1")
    assert all(any(lim.startswith(LIMIT_LOCATION_COLLISION + ":2") for lim in c.limitations) for c in out)
    assert [d.code for d in _collision_diagnostics(tuple(out))] == ["static_candidate_location_collision"]


def test_single_member_is_untouched() -> None:
    a = cand("sc_1", "/api/a", 1)
    assert _separate_collisions({"sc_1": [(a, "n#o")]}) == [a]
    assert _collision_diagnostics((a,)) == []


def test_same_path_at_different_locations_keeps_ambiguity_count() -> None:
    out = _mark_shared_endpoints([cand("sc_b", "/api/a", 9), cand("sc_a", "/api/a", 3), cand("sc_c", "/api/z", 1)])
    assert [c.id for c in out] == ["sc_a", "sc_b", "sc_c"]  # id 順で決定的
    assert f"{LIMIT_SHARED_ENDPOINT}:2" in out[0].limitations and f"{LIMIT_SHARED_ENDPOINT}:2" in out[1].limitations
    assert not any(LIMIT_SHARED_ENDPOINT in lim for lim in out[2].limitations)


def test_file_limits_distinguish_unverified_and_changed_files() -> None:
    sha = "a" * 64
    files = {"dist/app.js": VerifiedFile("dist/app.js", "verified", sha, 10)}
    assert _file_limits("dist/app.js", sha, files) == ()
    assert _file_limits("dist/app.js", "b" * 64, files) == (LIMIT_DIGEST_MISMATCH,)
    assert _file_limits("dist/none.js", sha, files) == (LIMIT_FILE_NOT_VERIFIED,)
    unsafe = {"x.js": VerifiedFile("x.js", "unsafe")}
    assert _file_limits("x.js", sha, unsafe) == (LIMIT_FILE_NOT_VERIFIED,)


def test_file_diagnostics_have_next_action_and_no_rea_wording() -> None:
    diags = _file_diagnostics((cand("sc_1", "/a", 1, limits=(LIMIT_DIGEST_MISMATCH, LIMIT_FILE_NOT_VERIFIED)),))
    assert [d.code for d in diags] == ["static_artifact_digest_mismatch", "static_artifact_not_verified"]
    assert all(d.next_action and "REA" not in d.message for d in diags)


def test_static_normalization_exposes_engine_version_with_legacy_alias() -> None:
    n = StaticNormalization("complete", "webspec2doc-native/1", None, (), (), Coverage("complete", False, 0, ()), (), ())
    assert n.engine_version == "webspec2doc-native/1" and n.provider_version == n.engine_version
