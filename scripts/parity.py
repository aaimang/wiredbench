"""WIRED box parity: does every wired code the Habbo client knows have a box in Turbo, an editor
in nitro-next and furni in the hotel?

Four sources, per kind (trigger, action, condition, selector, addon, variable):

- the client: each editor class's ``code`` and ``negativeCode`` getters return a code from the
  kind's code table (``TriggerConfCodes`` ...). Read from a Habbo client SWF with ``--swf``, which
  also refreshes the committed list (``docs/parity/client-codes.json``); without it, that list is
  read. The SWF is never committed: only the code names and numbers are.
- Turbo (``vendor/turbo-cloud``): each box's ``WiredCode => (int)Enum.Member`` and the furni logic
  it is (``[RoomObjectLogic("wf_...")]``), as turbo-cloud's own ``scripts/wiredgap.py`` reads them.
- nitro-next (``vendor/nitro-next``): each editor's ``code`` / ``negativeCode`` from the kind's
  ``<kind>Codes.ts`` table, in any subfolder.
- the hotel, with ``--hotel-db``: which box logics have furni in its ``furniture_definitions``
  (the database named by ``WB_DB_CONNECTION`` or ``vendor/turbo-cloud/appsettings.Development.json``).

It writes the report the Wiredbench admin panel shows (``turbo-plugin/data/parity.json``) and a
summary (``docs/parity/README.md``). ``--check`` fails when a client code has no box or no editor,
or a code is claimed by two boxes: what CI runs.

    python scripts/parity.py --swf ~/Downloads/HabboAir.swf --hotel-db
    python scripts/parity.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TURBO = ROOT / "vendor" / "turbo-cloud"
NITRO = ROOT / "vendor" / "nitro-next" / "packages" / "nitro-react" / "src" / "wired" / "elements"
CLIENT_CODES = ROOT / "docs" / "parity" / "client-codes.json"
REPORT = ROOT / "turbo-plugin" / "data" / "parity.json"
SUMMARY = ROOT / "docs" / "parity" / "README.md"

CLIENT_PACKAGE = "com.sulake.habbo.roomevents.wired_setup"


@dataclass(frozen=True)
class Kind:
    name: str
    client_folder: str
    client_table: str
    turbo_enum: str


KINDS = (
    Kind("trigger", "triggerconfs", "TriggerConfCodes", "WiredTriggerType"),
    Kind("action", "actiontypes", "ActionTypeCodes", "WiredActionType"),
    Kind("condition", "conditions", "ConditionCodes", "WiredConditionType"),
    Kind("selector", "selectors", "SelectorCodes", "WiredSelectorType"),
    Kind("addon", "addons", "AddonCodes", "WiredAddonType"),
    Kind("variable", "variables", "VariableCodes", "WiredVariableBoxType"),
)

# An editor class declares its own code and, for a box that negates another, its twin's.
CODE_GETTERS = ("code", "negativeCode")


@dataclass
class TurboBox:
    box: str
    logic: str | None


@dataclass
class Sources:
    client: dict[str, dict[int, list[str]]]
    turbo: dict[str, dict[int, list[TurboBox]]]
    nitro: dict[str, dict[int, list[str]]]
    furni: set[str] | None = None
    client_source: dict[str, Any] = field(default_factory=dict)
    # Each code's name in nitro-next's tables: a readable one where the client's is obfuscated.
    names: dict[str, dict[int, str]] = field(default_factory=dict)


# --- the client ------------------------------------------------------------------------------


def client_codes_from_swf(path: Path) -> dict[str, dict[int, list[str]]]:
    """Each kind's codes the client's editors declare, to the code table names they use."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from swf_abc import read_classes  # type: ignore[import-not-found]

    classes = read_classes(path)
    out: dict[str, dict[int, list[str]]] = {}

    for kind in KINDS:
        package = f"{CLIENT_PACKAGE}.{kind.client_folder}"
        table = next(c for c in classes if c.name == kind.client_table and c.package == package)
        values = {name: value for name, value in table.statics.items() if isinstance(value, int)}
        codes: dict[int, list[str]] = {}

        for cls in classes:
            if not cls.package.startswith(package):
                continue

            for getter in CODE_GETTERS:
                body = [
                    op
                    for op in cls.methods.get(getter) or []
                    if not op.startswith(("getlocal0", "pushscope"))
                ]

                if (
                    len(body) >= 2
                    and body[0] == f"getlex {kind.client_table}"
                    and body[1].startswith("getproperty ")
                ):
                    name = body[1].split(" ", 1)[1]

                    if name in values and name not in codes.setdefault(values[name], []):
                        codes[values[name]].append(name)

        out[kind.name] = dict(sorted(codes.items()))

    return out


def read_client_codes(path: Path = CLIENT_CODES) -> tuple[dict[str, dict[int, list[str]]], dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    codes = {
        kind: {int(code): names for code, names in by_code.items()} for kind, by_code in data["codes"].items()
    }

    return codes, data.get("source", {})


def write_client_codes(
    codes: dict[str, dict[int, list[str]]], source: dict[str, Any], path: Path = CLIENT_CODES
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "source": source,
        "codes": {
            kind: {str(code): names for code, names in by_code.items()} for kind, by_code in codes.items()
        },
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# --- Turbo -----------------------------------------------------------------------------------


def turbo_codes(root: Path = TURBO) -> dict[str, dict[int, list[TurboBox]]]:
    """Each kind's codes Turbo's boxes return, to the boxes (and their furni logic) returning them."""
    enums = root / "Turbo.Primitives" / "Rooms" / "Enums" / "Wired"
    boxes = root / "Turbo.Rooms" / "Object" / "Logic" / "Furniture" / "Floor" / "Wired"
    sources = {
        path: path.read_text(encoding="utf-8", errors="replace") for path in sorted(boxes.rglob("*.cs"))
    }
    out: dict[str, dict[int, list[TurboBox]]] = {}

    for kind in KINDS:
        values = {
            name: int(value)
            for name, value in re.findall(
                r"^\s*(\w+)\s*=\s*(-?\d+)",
                (enums / f"{kind.turbo_enum}.cs").read_text(encoding="utf-8"),
                re.M,
            )
        }
        codes: dict[int, list[TurboBox]] = {}

        for path, text in sources.items():
            logic = re.search(r'\[RoomObjectLogic\("([^"]+)"\)\]', text)

            for member in re.findall(r"WiredCode\s*=>\s*\(int\)\s*" + kind.turbo_enum + r"\.(\w+)", text):
                if member in values:
                    codes.setdefault(values[member], []).append(
                        TurboBox(path.stem, logic.group(1) if logic else None)
                    )

        out[kind.name] = dict(sorted(codes.items()))

    return out


# --- nitro-next ------------------------------------------------------------------------------


def nitro_names(root: Path = NITRO) -> dict[str, dict[int, str]]:
    """Each kind's code names in nitro-next's code tables, by code."""
    out: dict[str, dict[int, str]] = {}

    for kind in KINDS:
        text = (root / kind.name / f"{kind.name}Codes.ts").read_text(encoding="utf-8")
        out[kind.name] = {
            int(value): name for name, value in reversed(re.findall(r"^\s*(\w+)\s*:\s*(-?\d+)", text, re.M))
        }

    return out


def nitro_codes(root: Path = NITRO) -> dict[str, dict[int, list[str]]]:
    """Each kind's codes nitro-next has an editor for, to the editor files declaring them."""
    out: dict[str, dict[int, list[str]]] = {}

    for kind in KINDS:
        folder = root / kind.name
        table_file = folder / f"{kind.name}Codes.ts"
        table_text = table_file.read_text(encoding="utf-8")
        table_name = re.search(r"export const (\w+)\s*=", table_text).group(1)  # type: ignore[union-attr]
        table = {name: int(value) for name, value in re.findall(r"^\s*(\w+)\s*:\s*(-?\d+)", table_text, re.M)}
        codes: dict[int, list[str]] = {}

        # An editor names its code from the table: as its `code` / `negativeCode`, or handed to a
        # shared factory (`createInAreaSelector(SelectorCodes.USERS_IN_AREA)`).
        for path in sorted(folder.rglob("*.ts*")):
            if path == table_file or path.name == f"{kind.name}Elements.ts":
                continue

            for name in re.findall(r"\b" + table_name + r"\.(\w+)", path.read_text(encoding="utf-8")):
                if name in table:
                    editor = str(path.relative_to(folder))

                    if editor not in codes.setdefault(table[name], []):
                        codes[table[name]].append(editor)

        out[kind.name] = dict(sorted(codes.items()))

    return out


# --- the hotel -------------------------------------------------------------------------------


def _connection() -> dict[str, str]:
    raw = os.environ.get("WB_DB_CONNECTION", "")

    if not raw:
        settings = json.loads((TURBO / "appsettings.Development.json").read_text(encoding="utf-8"))

        def find(node: Any) -> str:
            if isinstance(node, dict):
                for key, value in node.items():
                    if "onnection" in key and isinstance(value, str):
                        return value
                    if found := find(value):
                        return found
            return ""

        raw = find(settings)

    return {
        k.strip().lower(): v.strip() for k, _, v in (p.partition("=") for p in raw.split(";") if "=" in p)
    }


def hotel_furni_logics() -> set[str]:
    """The wired logics the hotel has furni for (read only)."""
    conn = _connection()
    env = {**os.environ, "MYSQL_PWD": conn.get("password", "")}
    result = subprocess.run(
        [
            "mysql",
            f"-h{conn.get('server', '127.0.0.1')}",
            f"-P{conn.get('port', '3306')}",
            f"-u{conn.get('user', conn.get('user id', ''))}",
            conn.get("database", "turbo"),
            "-N",
            "-B",
            "-e",
            r"select distinct logic from furniture_definitions where logic like 'wf\_%'",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


# --- the report ------------------------------------------------------------------------------


def build_report(sources: Sources) -> dict[str, Any]:
    kinds: dict[str, Any] = {}
    gaps: dict[str, list[dict[str, Any]]] = {
        "clientWithoutBox": [],
        "clientWithoutEditor": [],
        "boxWithoutClient": [],
        "editorWithoutClient": [],
        "codeClaimedTwice": [],
        "boxWithoutFurni": [],
    }

    for kind in KINDS:
        client = sources.client.get(kind.name, {})
        turbo = sources.turbo.get(kind.name, {})
        nitro = sources.nitro.get(kind.name, {})
        rows = []

        for code in sorted(set(client) | set(turbo) | set(nitro)):
            boxes = turbo.get(code, [])
            logics = sorted({b.logic for b in boxes if b.logic})
            furni = None if sources.furni is None else [logic for logic in logics if logic in sources.furni]
            row = {
                "code": code,
                "client": client.get(code, []),
                "editors": nitro.get(code, []),
                "boxes": [{"box": b.box, "logic": b.logic} for b in boxes],
                "furni": furni,
            }
            name = sources.names.get(kind.name, {}).get(code) or (client.get(code) or [None])[0]
            row["name"] = name
            rows.append(row)
            where = {"kind": kind.name, "code": code, "name": name}

            if code in client and not boxes:
                gaps["clientWithoutBox"].append(where)
            if code in client and code not in nitro:
                gaps["clientWithoutEditor"].append(where)
            if boxes and code not in client:
                gaps["boxWithoutClient"].append({**where, "boxes": [b.box for b in boxes]})
            if code in nitro and code not in client:
                gaps["editorWithoutClient"].append({**where, "editors": nitro[code]})
            if len(boxes) > 1:
                gaps["codeClaimedTwice"].append({**where, "boxes": [b.box for b in boxes]})
            if furni is not None:
                for logic in logics:
                    if logic not in sources.furni:  # type: ignore[operator]
                        gaps["boxWithoutFurni"].append({**where, "logic": logic})

        kinds[kind.name] = {
            "client": len(client),
            "boxes": len([c for c in client if c in turbo]),
            "editors": len([c for c in client if c in nitro]),
            "rows": rows,
        }

    return {
        "clientSource": sources.client_source,
        "hotelChecked": sources.furni is not None,
        "summary": {
            "client": sum(k["client"] for k in kinds.values()),
            "boxes": sum(k["boxes"] for k in kinds.values()),
            "editors": sum(k["editors"] for k in kinds.values()),
            "gaps": {name: len(found) for name, found in gaps.items()},
        },
        "kinds": kinds,
        "gaps": gaps,
    }


def failures(report: dict[str, Any]) -> list[str]:
    """What --check fails on: a client code with no box or no editor, or a code two boxes claim."""
    out = []

    for gap in ("clientWithoutBox", "clientWithoutEditor", "codeClaimedTwice"):
        for found in report["gaps"][gap]:
            out.append(
                f"{gap}: {found['kind']} {found['code']} {found.get('name') or ''} {found.get('boxes') or ''}".rstrip()
            )

    return out


def summary_markdown(report: dict[str, Any]) -> str:
    source = report["clientSource"]
    lines = [
        "# WIRED box parity",
        "",
        "Generated by `python scripts/parity.py`: every wired code the Habbo client has an editor for, against",
        "Turbo's boxes, nitro-next's editors"
        + (
            " and the hotel's furni."
            if report["hotelChecked"]
            else ". The hotel's furni were not checked (`--hotel-db`)."
        ),
        "",
        f"Client: `{source.get('file', '?')}` (sha256 `{source.get('sha256', '?')}`).",
        "",
        "| Kind | Client codes | With a Turbo box | With a Nitro editor |",
        "|---|---|---|---|",
    ]

    for name, kind in report["kinds"].items():
        lines.append(f"| {name} | {kind['client']} | {kind['boxes']} | {kind['editors']} |")

    total = report["summary"]
    lines += [f"| **all** | **{total['client']}** | **{total['boxes']}** | **{total['editors']}** |", ""]
    titles = {
        "clientWithoutBox": "Client codes with no Turbo box",
        "clientWithoutEditor": "Client codes with no nitro-next editor",
        "codeClaimedTwice": "Codes two Turbo boxes claim",
        "boxWithoutFurni": "Turbo boxes the hotel has no furni for",
        "boxWithoutClient": "Turbo boxes for codes the client does not know",
        "editorWithoutClient": "nitro-next editors for codes the client does not know",
    }

    for gap, title in titles.items():
        found = report["gaps"][gap]
        lines.append(f"## {title}: {len(found)}")
        lines.append("")
        lines += [
            f"- {f['kind']} {f['code']}"
            + (f" `{f['name']}`" if f.get("name") else "")
            + (f" ({f['logic']})" if f.get("logic") else "")
            + (f" ({', '.join(f['boxes'])})" if f.get("boxes") else "")
            for f in found
        ] or ["None."]
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--swf",
        type=Path,
        help="a Habbo client SWF to read the client's codes from (refreshes the committed list)",
    )
    parser.add_argument("--hotel-db", action="store_true", help="check the hotel's furni in its database")
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail on a client code with no box or editor, or a code claimed twice",
    )
    parser.add_argument("--no-write", action="store_true", help="print the summary only")
    args = parser.parse_args(argv)

    # A check (CI) only reads: the committed report is the full run's, the hotel's furni included.
    write = not (args.no_write or args.check)

    if args.swf:
        client = client_codes_from_swf(args.swf)
        source = {"file": args.swf.name, "sha256": hashlib.sha256(args.swf.read_bytes()).hexdigest()[:12]}

        if write:
            write_client_codes(client, source)
    else:
        client, source = read_client_codes()

    report = build_report(
        Sources(
            client=client,
            turbo=turbo_codes(),
            nitro=nitro_codes(),
            names=nitro_names(),
            furni=hotel_furni_logics() if args.hotel_db else None,
            client_source=source,
        )
    )

    if write:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        SUMMARY.write_text(summary_markdown(report) + "\n", encoding="utf-8")

    total = report["summary"]
    print(
        f"client {total['client']} codes: {total['boxes']} with a Turbo box, {total['editors']} with a nitro-next editor"
    )

    for gap, count in total["gaps"].items():
        print(f"  {gap}: {count}")

    if args.check and (found := failures(report)):
        print("\n".join(found), file=sys.stderr)

        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
