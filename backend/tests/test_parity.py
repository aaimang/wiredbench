"""scripts/parity.py: the WIRED box parity report (client codes against Turbo, nitro-next and the hotel)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("parity_script", ROOT / "scripts/parity.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["parity_script"] = module
    spec.loader.exec_module(module)
    return module


parity = _load()


def sources(**overrides: object) -> object:
    kinds = {kind.name: {} for kind in parity.KINDS}
    base: dict[str, object] = {
        "client": {**kinds, "trigger": {0: ["SAYS"], 1: ["WALKS_ON"]}},
        "turbo": {**kinds, "trigger": {0: [parity.TurboBox("WiredTriggerSays", "wf_trg_says")]}},
        "nitro": {**kinds, "trigger": {0: ["Says.ts"], 1: ["WalksOn.ts"]}},
        "names": {"trigger": {0: "AVATAR_SAYS_SOMETHING"}},
        "client_source": {"file": "client.swf", "sha256": "abc"},
    }
    base.update(overrides)
    return parity.Sources(**base)


def test_a_client_code_with_no_box_fails_the_check() -> None:
    report = parity.build_report(sources())

    assert report["summary"]["client"] == 2
    assert report["summary"]["boxes"] == 1
    assert report["summary"]["editors"] == 2
    assert report["gaps"]["clientWithoutBox"] == [{"kind": "trigger", "code": 1, "name": "WALKS_ON"}]
    assert parity.failures(report) == ["clientWithoutBox: trigger 1 WALKS_ON"]


def test_a_code_is_named_from_nitro_where_it_has_a_name() -> None:
    rows = parity.build_report(sources())["kinds"]["trigger"]["rows"]

    assert [row["name"] for row in rows] == ["AVATAR_SAYS_SOMETHING", "WALKS_ON"]


def test_two_boxes_on_one_code_fail_the_check() -> None:
    kinds = {kind.name: {} for kind in parity.KINDS}
    report = parity.build_report(
        sources(
            client={**kinds, "trigger": {0: ["SAYS"]}},
            turbo={**kinds, "trigger": {0: [parity.TurboBox("A", "wf_a"), parity.TurboBox("B", "wf_b")]}},
            nitro={**kinds, "trigger": {0: ["Says.ts"]}},
        )
    )

    assert report["gaps"]["codeClaimedTwice"][0]["boxes"] == ["A", "B"]
    assert len(parity.failures(report)) == 1


def test_the_hotel_s_furni_are_checked_only_when_asked() -> None:
    without = parity.build_report(sources())
    with_hotel = parity.build_report(sources(furni=set()))

    assert without["hotelChecked"] is False
    assert without["kinds"]["trigger"]["rows"][0]["furni"] is None
    assert with_hotel["gaps"]["boxWithoutFurni"] == [
        {"kind": "trigger", "code": 0, "name": "AVATAR_SAYS_SOMETHING", "logic": "wf_trg_says"}
    ]
    # Furni are reported, not failed on: a hotel may simply not have a box's furni yet.
    assert parity.failures(with_hotel) == ["clientWithoutBox: trigger 1 WALKS_ON"]


def test_nitro_editors_are_found_by_code_and_by_factory(tmp_path: Path) -> None:
    for kind in parity.KINDS:
        folder = tmp_path / kind.name
        folder.mkdir()
        (folder / f"{kind.name}Codes.ts").write_text(
            f"export const {kind.name}T = {{\n    A: 0,\n    B: 1,\n    C: 2,\n}};\n"
        )
    (tmp_path / "trigger" / "A.ts").write_text("export const a = { code: triggerT.A };\n")
    (tmp_path / "trigger" / "sub").mkdir()
    (tmp_path / "trigger" / "sub" / "B.ts").write_text(
        "export const b = noInputElement('trigger', triggerT.B);\n"
    )
    (tmp_path / "trigger" / "triggerElements.ts").write_text("// triggerT.C only listed here\n")

    found = parity.nitro_codes(tmp_path)

    assert found["trigger"] == {0: ["A.ts"], 1: ["sub/B.ts"]}
    assert parity.nitro_names(tmp_path)["trigger"] == {0: "A", 1: "B", 2: "C"}


def test_turbo_boxes_are_read_with_their_furni_logic(tmp_path: Path) -> None:
    enums = tmp_path / "Turbo.Primitives" / "Rooms" / "Enums" / "Wired"
    boxes = tmp_path / "Turbo.Rooms" / "Object" / "Logic" / "Furniture" / "Floor" / "Wired" / "Triggers"
    enums.mkdir(parents=True)
    boxes.mkdir(parents=True)

    for kind in parity.KINDS:
        (enums / f"{kind.turbo_enum}.cs").write_text(
            "public enum X\n{\n    SAYS = 0,\n    WALKS_ON = 1,\n}\n"
        )
    (boxes / "WiredTriggerSays.cs").write_text(
        '[RoomObjectLogic("wf_trg_says")]\npublic class WiredTriggerSays\n{\n'
        "    public override int WiredCode => (int)WiredTriggerType.SAYS;\n}\n"
    )

    found = parity.turbo_codes(tmp_path)

    assert found["trigger"] == {0: [parity.TurboBox("WiredTriggerSays", "wf_trg_says")]}
    assert found["action"] == {}


def test_the_client_code_list_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "client-codes.json"
    codes = {"trigger": {0: ["SAYS"], 17: ["RECEIVE_SIGNAL"]}}

    parity.write_client_codes(codes, {"file": "a.swf", "sha256": "x"}, path)

    assert parity.read_client_codes(path) == (codes, {"file": "a.swf", "sha256": "x"})


@pytest.mark.skipif(
    not (parity.TURBO / "Turbo.Rooms").exists() or not parity.NITRO.exists(),
    reason="the vendor submodules are not checked out",
)
def test_the_pinned_turbo_and_nitro_cover_every_committed_client_code() -> None:
    client, source = parity.read_client_codes()
    report = parity.build_report(
        parity.Sources(
            client=client,
            turbo=parity.turbo_codes(),
            nitro=parity.nitro_codes(),
            names=parity.nitro_names(),
            client_source=source,
        )
    )

    assert parity.failures(report) == []
    assert report["summary"]["client"] == json.loads(parity.REPORT.read_text())["summary"]["client"]
