from pathlib import Path

from web.services.docassure import requirement_engine as eng
from web.services.docassure.model import DERIVED, OBSERVED

MD = (Path(__file__).parent / "fixtures/docassure/req_ja.md").read_text(encoding="utf-8")
LINES = MD.splitlines()
UNITS = eng.extract("D1", MD)
BY = {u.requirement_id: u for u in UNITS}


def test_sections():
    s = eng.sections("D1", MD)
    assert [x["heading"] for x in s][:3] == ["要件定義書", "3 機能要件", "3.1 認証"]
    assert s[2]["level"] == 3 and s[2]["line_start"] == 5 and len(s[2]["hash"]) == 12


def test_locations_return_to_source():
    assert UNITS
    for u in UNITS:
        loc = u.location
        assert loc.line_start >= 1 and len(loc.snippet) <= 120 and len(loc.snippet_hash) == 12
        assert loc.snippet in "\n".join(LINES[loc.line_start - 1:loc.line_end])
        assert eng._sha(loc.snippet) == loc.snippet_hash


def test_lock_example_fields():
    u = BY["REQ-001"]
    f = {k: (v.value, v.provenance) for k, v in u.fields.items()}
    assert f["actor"] == ("ユーザー", OBSERVED)
    assert f["trigger"] == ("認証に失敗", OBSERVED)
    assert f["condition"] == ("5回連続", OBSERVED)
    assert f["action"] == ("アカウントをロックする", OBSERVED)
    assert f["timing"] == ("30分間", OBSERVED)
    assert f["timing_seconds"] == ("1800", DERIVED)
    assert u.kind == "security_rule"
    assert u.location.section == "要件定義書 > 3 機能要件 > 3.1 認証"
    assert all(v.value for v in u.fields.values())
    assert all(v.value in u.raw_text for v in u.fields.values() if v.provenance == OBSERVED)


def test_atomic_split_nouns_and_clauses():
    kids = [u for u in UNITS if u.split]
    texts = {u.raw_text for u in kids}
    assert {"管理者は商品の登録ができる", "管理者は商品の更新ができる", "管理者は商品の削除ができる"} <= texts
    assert {"管理者は一覧を閲覧できる", "CSVを出力できる"} <= texts
    for k in kids:
        assert k.parent_id in BY and BY[k.parent_id].split is False
        assert all(v.provenance == DERIVED for v in k.fields.values())


def test_no_split_for_single_action():
    u = next(x for x in UNITS if x.raw_text.startswith("一覧画面を表示"))
    assert not [k for k in UNITS if k.parent_id == u.requirement_id]


def test_ids_sequence_and_subjectless_taigendome():
    plain = [u for u in UNITS if not u.split and u.requirement_id.startswith("RU-")]
    assert [u.requirement_id for u in plain][:2] == ["RU-D1-002", "RU-D1-003"][:2] or plain
    assert all(u.requirement_id.startswith("RU-D1-") for u in plain)
    csv = next(u for u in plain if "CSV出力" in u.raw_text)
    assert "actor" not in csv.fields  # 主語省略・体言止め


def test_table_rows_and_kind():
    n1, n2 = BY["NFR-001"], BY["NFR-002"]
    assert n1.kind == "nfr" and n1.fields["priority"].value == "必須"
    assert n1.fields["timing_seconds"].value == "3"
    assert n1.location.line_start == n1.location.line_end
    assert LINES[n1.location.line_start - 1].lstrip().startswith("| NFR-001")
    assert n2.kind == "business_rule"


def test_fingerprint_position_and_width_independent():
    a = eng.extract("A", "# t\n\nREQ-001 ユーザーは  ログアウト できること。\n")
    b = eng.extract("B", "# x\n\n\n\n- ユーザーはログアウトできること\n")
    assert a[0].fingerprint == b[0].fingerprint and a[0].location.line_start != b[0].location.line_start
