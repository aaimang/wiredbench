"""Behaviour comparison: the old Python engine against Turbo, room by room.

``docs/behaviour/scenarios.json`` is the old Python engine's answer, recorded on 2026-11-12 from every
room its own tests built that had a WIRED box: its furni, its boxes' settings as the client would send
them, its users and the inputs the test gave it, with what could be seen at checkpoints (just before
each input, and at the end). The engine is gone, so the file is kept as it was.

Turbo replays the same rooms in its own test harness and writes what it saw at the same checkpoints
to ``docs/behaviour/turbo.json``. The replay test is kept in ``tests/turbo-replay/``, not in turbo-cloud,
and is copied into ``vendor/turbo-cloud/Turbo.Tests/Rooms/`` to run.

``report`` compares the two and writes ``docs/behaviour/README.md`` and ``report.json``. It fixes
nothing: it says where the two engines disagree, so each case can be judged.

    cp tests/turbo-replay/WiredbenchBehaviourReplayTests.cs vendor/turbo-cloud/Turbo.Tests/Rooms/
    (cd vendor/turbo-cloud && WB_BEHAVIOUR_SCENARIOS=../../docs/behaviour/scenarios.json \\
        WB_BEHAVIOUR_OUT=../../docs/behaviour/turbo.json \\
        dotnet test Turbo.Tests --filter FullyQualifiedName~WiredbenchBehaviourReplay)
    uv run python scripts/behaviour.py report
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "behaviour"


def _differences(ours: dict[str, Any], theirs: dict[str, Any]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for category in ("users", "furni"):
        a, b = ours.get(category, {}), theirs.get(category, {})
        lines = [
            f"{k}: python {a.get(k)} turbo {b.get(k)}"
            for k in sorted(set(a) | set(b))
            if a.get(k) != b.get(k)
        ]
        if lines:
            found[category] = lines
    a_vars, b_vars = ours.get("variables", {}), theirs.get("variables", {})
    lines = []
    for name in sorted(set(a_vars) | set(b_vars)):
        a, b = a_vars.get(name, {}), b_vars.get(name, {})
        lines += [
            f"{name} on {k}: python {a.get(k, '-')} turbo {b.get(k, '-')}"
            for k in sorted(set(a) | set(b))
            if a.get(k) != b.get(k)
        ]
    if lines:
        found["variables"] = lines
    a_msg, b_msg = Counter(ours.get("messages", [])), Counter(theirs.get("messages", []))
    if a_msg != b_msg:
        found["messages"] = [f"python only: {m!r}" for m in (a_msg - b_msg).elements()] + [
            f"turbo only: {m!r}" for m in (b_msg - a_msg).elements()
        ]
    return found


def _compare(scenario: dict[str, Any], turbo: dict[str, Any] | None) -> dict[str, Any]:
    if turbo is None:
        return {"status": "not run", "detail": "Turbo has no result for it"}
    if turbo.get("error"):
        return {"status": "error", "detail": turbo["error"]}
    python, ours = scenario["python"], turbo.get("checkpoints", [])
    if len(python) != len(ours):
        return {"status": "error", "detail": f"{len(python)} checkpoints in Python, {len(ours)} in Turbo"}
    windows = []
    for i, (a, b) in enumerate(zip(python, ours, strict=True)):
        found = _differences(a, b)
        if found:
            windows.append(
                {"checkpoint": i, "at": a["at"], "after": _input_name(scenario, i), "differences": found}
            )
    return {
        "status": "differs" if windows else "same",
        "categories": sorted({c for w in windows for c in w["differences"]}),
        "windows": windows,
        "refused": turbo.get("refused", []),
    }


# Where the two disagree on what Turbo has from Habbo itself (every built-in variable and the
# placeholders boxes print), Turbo is the reference: the Python engine's reading is the one to correct.
REFERENCE_REASON = "Turbo is the reference: built-in variables and placeholders"


# Differences whose cause has been traced, by test: what each engine does and which is Habbo's.
# A test here is listed as "differs, known cause" with the reason, not as unexplained.
PYTHON_KEEPS_LEFT = (
    "Python is off: it keeps a user's room-active variables after the user leaves; in Habbo an active"
    " user variable goes with the user, and Turbo drops the user's store when they leave"
)
PYTHON_IGNORES_HAS_VALUE = (
    "Python is off: an API write stores a number on a variable whose 'has value' is off; Habbo keeps only"
    " that it is held, as Turbo does (RoomWiredSystem.WebApi: 'the number sent is not kept')"
)
KNOWN_CAUSES = {
    "test_leaving_without_standing_loses_up_to_ten_seconds": PYTHON_KEEPS_LEFT,
    "test_variable_age_can_measure_from_the_last_change": PYTHON_IGNORES_HAS_VALUE,
    "test_value_can_come_from_another_variable": PYTHON_IGNORES_HAS_VALUE,
    "test_defined_variables_are_listed_until_something_holds_them": (
        "The replay's: the API write is to a user who is not in the room (user:1), which the replay does not"
        " send; Turbo would keep it for the absent player, out of the room's sight"
    ),
    "test_place_and_remove_temporary_furni": (
        "Python is off: it copies any furni; Habbo lets Place Temporary Furni copy only Builders Club furni"
        " (official client capture: the player's own chair refused with furni_can_not_be_cloned), so Turbo"
        " refused the box's settings and placed nothing"
    ),
    "test_background_toner_colour_switching_and_smart_variables": (
        "The replay's: the test gives the user rights by editing the engine, which no input records, and"
        " sets toner colours, which the replay does not send; Turbo's user may switch the toner from the start"
    ),
    "test_a_named_bot_walks_to_furni_and_fires_bot_reached_furni": (
        "Open, needs a Habbo capture: Turbo walks a bot one step per avatar cycle from the next cycle and is"
        " a step short at 1.6 s; Python's bot is there already"
    ),
    "test_bot_follows_a_user_and_fires_reached_user_once_it_catches_up": (
        "Open, needs a Habbo capture: Turbo's bot goes to the first free side of the user in the order north,"
        " east, south, west (here east, walking through the user); Python's stops on the nearest side"
    ),
    "test_bot_gives_a_hand_item_and_talks": (
        "Open, needs a Habbo capture: Turbo's bot goes to the first free side of the user in the order north,"
        " east, south, west (here east, walking through the user); Python's stops on the nearest side"
    ),
}


def _known_cause(scenario_id: str) -> str | None:
    test = scenario_id.split("::", 1)[-1].split("[", 1)[0].split("#", 1)[0]
    return KNOWN_CAUSES.get(test)


def _uses_built_ins(scenario: dict[str, Any]) -> bool:
    """A box names a built-in (@) variable, Habbo's "-N" id (@position.x, @rotation, @state...)."""
    return any(v.startswith("-") for b in scenario["boxes"] for v in b["variables"])


def _uses_placeholders(scenario: dict[str, Any]) -> bool:
    return any("$(" in b["string"] for b in scenario["boxes"])


def _turbo_is_reference(scenario: dict[str, Any], result: dict[str, Any]) -> bool:
    """Every difference is one Turbo is the reference for: a message where the room prints placeholders
    or reads built-ins, and a user, furni or variable where the room uses built-in variables."""
    if result.get("status") != "differs":
        return False
    built_ins, placeholders = _uses_built_ins(scenario), _uses_placeholders(scenario)
    for window in result["windows"]:
        for category in window["differences"]:
            if category == "messages" and not (placeholders or built_ins):
                return False
            if category != "messages" and not built_ins:
                return False
    return True


def _changes(scenario: dict[str, Any]) -> bool:
    """Whether anything a player could see happens in the Python run."""
    points = [{k: v for k, v in c.items() if k not in ("at", "messages")} for c in scenario["python"]]
    return any(c["messages"] for c in scenario["python"]) or any(p != points[0] for p in points)


def _input_name(scenario: dict[str, Any], checkpoint: int) -> str:
    if checkpoint == 0:
        return "room start"
    entry = scenario["inputs"][checkpoint - 1]
    detail = ", ".join(f"{k}={v}" for k, v in entry.items() if k not in ("type", "at_ms"))
    return f"{entry['type']} ({detail}) at {entry['at_ms']} ms"


def _markdown(results: list[dict[str, Any]], scenarios: dict[str, dict[str, Any]]) -> str:
    status = Counter(r["status"] for r in results)
    categories = Counter(c for r in results if r["status"] == "differs" for c in r.get("categories", []))
    clean = [r for r in results if r["status"] == "differs" and not scenarios[r["id"]]["notes"]]
    active = sum(1 for r in results if r["status"] == "same" and _changes(scenarios[r["id"]]))
    suspects = Counter(c for r in clean for c in scenarios[r["id"]]["classes"])
    agree = Counter(c for r in results if r["status"] == "same" for c in scenarios[r["id"]]["classes"])
    refused = Counter(c for r in results for c in r.get("refused", []))

    lines = [
        "# Behaviour comparison: Python engine against Turbo",
        "",
        "Written by `scripts/behaviour.py report`; do not edit by hand. Every room the old Python engine's tests",
        "build (`backend/tests/test_engine.py`, `test_guide.py`) with a WIRED box is replayed in both engines,",
        "and what a player could see is compared just before each input and at the end: where users and bots",
        "stand, each furni's tile, turn and state, user-made variables on each holder, and Show Message",
        "whispers. Neither engine has been changed to agree: this lists where they disagree.",
        "",
        "Turbo stands the room on a flat floor, saves each box as the client would (the G-Presets export of",
        "the room), moves users straight onto a tile as the Python engine does (not when frozen), stands bots",
        "and hand items, writes API values through the room's Web API, and runs wired every 50 ms and the",
        "avatar cycle every 500 ms, on a clock where the Python engine's time 0 is the same instant.",
        "Some differences are the replay's, not Turbo's; the notes on a scenario say which:",
        "inputs Turbo does not replay (game, detail and toner inputs), user details other than a hand item,",
        "random draws, settings the client's params cannot carry, and floor heights.",
        "",
        "Turbo is the reference where it has Habbo's own list: every built-in variable (`@position.x`,",
        "`@position.y`, `@rotation`, `@state` and the rest) and the placeholders boxes print. A difference",
        "only in those is marked *differs, Turbo is the reference*: the Python engine is the one that is",
        "off, and it is not counted as unexplained.",
        "",
        "A difference whose cause has been traced is marked *differs, known cause*, with the cause: which",
        "engine is off, or that it is open until a Habbo capture settles it.",
        "",
        "## Summary",
        "",
        "| Result | Scenarios |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in sorted(status.items())],
        f"| **total** | **{len(results)}** |",
        "",
        "Scenarios that differ (Turbo's reference ones and known causes left out), by what differs:",
        "",
        "| What | Scenarios |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in categories.most_common()],
        "",
        f"{len(clean)} of the differing scenarios have no note: nothing in the replay explains them.",
        "",
        f"{active} of the {status.get('same', 0)} matching scenarios show something happening in Python (a",
        "message, a variable, a user or furni changing); the rest are rooms where neither engine changes",
        "anything visible, which match trivially.",
        "",
    ]
    if refused:
        lines += [
            "## Settings Turbo refused",
            "",
            "Boxes whose saved settings (the G-Presets export) Turbo's room would not take; the box then runs as",
            "it stood. Often the export's reading of a field, not Turbo.",
            "",
            "| Box | Refusals |",
            "|---|---|",
            *[f"| `{k}` | {v} |" for k, v in refused.most_common()],
            "",
        ]
    lines += [
        "## Boxes in unexplained differences",
        "",
        *(
            [
                "How many un-noted differing scenarios hold each box, beside how many matching ones do. A box",
                "high on the left and low on the right is the first place to look.",
                "",
                "| Box | In differing | In matching |",
                "|---|---|---|",
                *[f"| `{k}` | {v} | {agree.get(k, 0)} |" for k, v in suspects.most_common(40)],
            ]
            if suspects
            else ["None: every differing scenario has a note."]
        ),
        "",
        "## Scenarios",
        "",
    ]
    order = {
        "differs": 0,
        "error": 1,
        "not run": 2,
        "differs, known cause": 3,
        "differs, Turbo is the reference": 4,
    }
    for r in sorted(results, key=lambda r: (order.get(r["status"], 9), r["id"])):
        s = scenarios[r["id"]]
        if r["status"] == "same":
            continue
        lines.append(f"### `{r['id']}` ({r['status']})")
        lines.append("")
        if s["notes"]:
            lines.append("Notes: " + "; ".join(s["notes"]) + ".")
            lines.append("")
        if r.get("reason"):
            lines.append(f"Cause: {r['reason']}.")
            lines.append("")
        lines.append("Boxes: " + ", ".join(f"`{c}`" for c in s["classes"]))
        lines.append("")
        if r.get("refused"):
            lines.append("Turbo refused the settings of: " + ", ".join(f"`{c}`" for c in r["refused"]))
            lines.append("")
        if not r["status"].startswith("differs"):
            lines.append(f"- {r['detail']}")
            lines.append("")
            continue
        first = r["windows"][0]
        lines.append(
            f"First difference at checkpoint {first['checkpoint']} ({first['at']} ms, after {first['after']}),"
            f" {len(r['windows'])} checkpoint(s) differ in all:"
        )
        lines.append("")
        for category, found in first["differences"].items():
            for line in found[:6]:
                lines.append(f"- {category}: {line}")
            if len(found) > 6:
                lines.append(f"- {category}: and {len(found) - 6} more")
        lines.append("")
    same = sorted(r["id"] for r in results if r["status"] == "same")
    lines += ["## Scenarios that match", "", *[f"- `{x}`" for x in same], ""]
    return "\n".join(lines)


def report() -> int:
    scenarios = {s["id"]: s for s in json.loads((OUT / "scenarios.json").read_text())}
    turbo_path = OUT / "turbo.json"
    turbo = {t["id"]: t for t in json.loads(turbo_path.read_text())} if turbo_path.exists() else {}
    results = [{"id": i, **_compare(s, turbo.get(i))} for i, s in scenarios.items()]
    for result in results:
        if _turbo_is_reference(scenarios[result["id"]], result):
            result["status"] = "differs, Turbo is the reference"
            result["reason"] = REFERENCE_REASON
        elif result["status"] == "differs" and (cause := _known_cause(result["id"])):
            result["status"] = "differs, known cause"
            result["reason"] = cause
    (OUT / "report.json").write_text(json.dumps(results, indent=1) + "\n")
    (OUT / "README.md").write_text(_markdown(results, scenarios))
    status = Counter(r["status"] for r in results)
    print(", ".join(f"{v} {k}" for k, v in sorted(status.items())) + f" -> {OUT / 'README.md'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["report"])
    parser.parse_args(argv)
    return report()


if __name__ == "__main__":
    sys.exit(main())
