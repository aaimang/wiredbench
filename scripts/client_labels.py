#!/usr/bin/env python3
"""Names WIRED box positions from the setup forms in Habbo's own client, keeping only names.

uv run python scripts/client_labels.py --swf ~/Downloads/HabboAir.swf

The client stays outside this repository, and none of its code is copied. For each box this reads the form that
edits it, finds which number position each control reads, and keeps the control's text key (such as
`click_settings.user`) or, failing that, the name of the client field the number goes into. Both come from how the
form is built, not from a box being changed, so they are a lead rather than proof.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from swf_abc import AbcClass, read_classes

FACTS = Path(__file__).parents[1] / "backend/src/wiredbench/engine/box_facts.json"
LABELS = Path(__file__).parents[1] / "backend/src/wiredbench/engine/client_labels.json"
CODE_TABLES = {
    "trigger": "TriggerConfCodes",
    "condition": "ConditionCodes",
    "effect": "ActionTypeCodes",
    "selector": "SelectorCodes",
    "addon": "AddonCodes",
    "variable": "VariableCodes",
}
ONE_POP = {0x11, 0x12}  # iftrue, iffalse
TWO_POPS = set(range(0x0C, 0x1A)) - {0x10, *ONE_POP}
COUNTED = ("construct", "applytype", "newarray", "newobject", "call", "constructsuper")
UNARY = {
    "not",
    "negate",
    "increment",
    "decrement",
    "typeof",
    "bitnot",
    "increment_i",
    "decrement_i",
    "negate_i",
}
BINARY = {
    "add", "subtract", "multiply", "divide", "modulo", "equals", "strictequals", "lessthan", "lessequals",
    "greaterthan", "greaterequals", "bitand", "bitor", "bitxor", "lshift", "rshift", "urshift", "add_i",
    "subtract_i", "multiply_i", "istypelate", "astypelate", "instanceof", "in",
}  # fmt: skip
CALLS = {"callproperty", "callproplex", "constructprop", "callpropvoid", "callsuper", "callsupervoid"}
# Field names that say what a control is, not what the number means.
GENERIC = {
    "selected",
    "selectedId",
    "checked",
    "value",
    "text",
    "visible",
    "enabled",
    "selectedIndex",
    "index",
    "*",
}
# Fields that hold a whole group of controls, so they name no single position.
GROUPS = re.compile(r"^_?(section\d*|wiredContext)$")
PARAMS = "wiredfurni.params."
Expr = Any


def run(ops: list[str]) -> list[tuple[Any, ...]]:
    """Follows a method's stack without running it and returns its stores and void calls as expressions."""
    stack: list[Expr] = []
    local: dict[int, Expr] = {}
    out: list[tuple[Any, ...]] = []

    def pop() -> Expr:
        return stack.pop() if stack else "?"

    def pops(count: int) -> list[Expr]:
        return [pop() for _ in range(count)][::-1]

    for line in ops:
        op, _, arg = line.partition(" ")
        count = 0
        if counted := re.fullmatch(r"(.*) \((\d+)\)", arg):
            arg, count = counted.group(1), int(counted.group(2))
        elif op in COUNTED:
            count = int(arg)
        if op in ("pushbyte", "pushshort", "pushint", "pushuint"):
            stack.append(int(arg))
        elif op == "pushdouble":
            stack.append(float(arg))
        elif op == "pushstring":
            stack.append(("str", ast.literal_eval(arg)))
        elif op in ("pushtrue", "pushfalse", "pushnull", "pushundefined", "pushnan", "newactivation"):
            stack.append(op)
        elif op == "getlex":
            stack.append(("lex", arg))
        elif op in ("findpropstrict", "findproperty"):
            stack.append(("scope", arg))
        elif op == "getproperty":
            if arg == "*":
                key = pop()
                stack.append(("idx", pop(), key))
            else:
                stack.append(("prop", pop(), arg))
        elif op in ("setproperty", "initproperty"):
            value = pop()
            key = pop() if arg == "*" else arg
            out.append(("set", pop(), key, value))
        elif op in CALLS:
            args = pops(count)
            expr = ("call", pop(), arg, args)
            (out if op.endswith("void") else stack).append(expr)
        elif op == "construct":
            args = pops(count)
            stack.append(("new", pop(), args))
        elif op == "applytype":
            args = pops(count)
            stack.append(("type", pop(), args))
        elif op == "newarray":
            stack.append(("arr", pops(count)))
        elif op == "newobject":
            stack.append(("obj", pops(2 * count)))
        elif op == "call":
            args = pops(count)
            pop()
            stack.append(("fcall", pop(), args))
        elif op == "constructsuper":
            pops(count)
            pop()
        elif op.startswith("getlocal"):
            index = int(arg) if arg else int(op[-1])
            stack.append(local.get(index, ("local", index)))
        elif op.startswith("setlocal"):
            local[int(arg) if arg else int(op[-1])] = pop()
        elif op == "dup":
            value = pop()
            stack += [value, value]
        elif op == "swap":
            top, under = pop(), pop()
            stack += [top, under]
        elif op in ("pop", "returnvalue", "throw", "pushscope", "pushwith", "lookupswitch", "setslot"):
            pop()
            if op == "setslot":
                pop()
        elif op in UNARY:
            stack.append((op, pop()))
        elif op in BINARY:
            right, left = pop(), pop()
            stack.append((op, left, right))
        elif op == "branch":
            code = int(arg, 16)
            if code in ONE_POP:
                pop()
            elif code in TWO_POPS:
                pop(), pop()
        elif op == "getslot":
            stack.append(("slot", pop(), arg))
    return out


class Tree:
    """Walks expressions, including what later statements pushed into a list built step by step."""

    def __init__(self, statements: list[tuple[Any, ...]]) -> None:
        self.pushed: dict[int, list[Expr]] = {}
        for statement in statements:
            if statement[0] == "call" and statement[2] == "push" and isinstance(statement[1], tuple):
                self.pushed.setdefault(id(statement[1]), []).extend(statement[3])

    def walk(self, expr: Expr, seen: set[int] | None = None) -> Iterator[Expr]:
        seen = set() if seen is None else seen
        if id(expr) in seen:
            return
        seen.add(id(expr))
        yield expr
        for extra in self.pushed.get(id(expr), []):
            yield from self.walk(extra, seen)
        if isinstance(expr, tuple):
            for part in expr[1:]:
                for item in part if isinstance(part, list) else [part]:
                    yield from self.walk(item, seen)


def _key(text: str) -> str | None:
    if text.startswith("${" + PARAMS) and text.endswith("}"):
        return text[len(PARAMS) + 2 : -1]
    if text.startswith(PARAMS):
        return text[len(PARAMS) :]
    return None


def text_keys(tree: Tree, expr: Expr) -> list[str]:
    """Text keys given to the form's l() and loc() helpers, or written out in full."""
    keys: list[str] = []
    for node in tree.walk(expr):
        if not isinstance(node, tuple):
            continue
        key = None
        if node[0] == "call" and node[2] in ("l", "loc") and node[3] and isinstance(node[3][0], tuple):
            if node[3][0][0] == "str":
                key = _key(node[3][0][1]) or (node[3][0][1] if node[2] == "l" else None)
        elif node[0] == "str":
            key = _key(node[1]) if node[1].startswith("${") else None
        if key and key not in keys:
            keys.append(key)
    return keys


def controls(statements: list[tuple[Any, ...]]) -> dict[str, dict[str, Any]]:
    """Each form field with its text key, its section's key and its options' keys."""
    tree = Tree(statements)
    found: dict[str, dict[str, Any]] = {}
    for statement in statements:
        if statement[0] != "set" or not isinstance(statement[2], str):
            continue
        info: dict[str, Any] = {"label": None, "options": {}, "section": None}
        for node in tree.walk(statement[3]):
            if not (isinstance(node, tuple) and node[0] == "call"):
                continue
            args = node[3]
            made_here = isinstance(node[1], tuple) and node[1][0] == "scope"
            if made_here and node[2] == "CheckboxOptionParam" and len(args) >= 2 and isinstance(args[1], int):
                keys = text_keys(tree, args[0])
                info["options"][args[1]] = keys[0] if keys else None
            elif made_here and node[2] in ("RadioButtonParam", "ExpandableDropdownOption", "DropdownOption"):
                if args and isinstance(args[0], int):
                    keys = text_keys(tree, ("args", args[1:]))
                    info["options"][args[0]] = keys[0] if keys else None
            elif made_here and node[2].endswith("Param") and info["label"] is None and args:
                keys = text_keys(tree, args[0])
                info["label"] = keys[0] if keys else None
            elif node[2].startswith("create") and info["label"] is None and args:
                first = args[0]
                if isinstance(first, tuple) and first[0] == "str":
                    info["label"] = _key(first[1])
        found.setdefault(statement[2], info)
    for statement in statements:
        root = statement if statement[0] == "call" else statement[3]
        for node in tree.walk(root):
            if (
                isinstance(node, tuple)
                and node[0] == "call"
                and node[2] == "createSection"
                and len(node[3]) >= 2
            ):
                keys = text_keys(tree, node[3][0])
                for inner in tree.walk(node[3][1]):
                    if keys and isinstance(inner, tuple) and inner[0] == "lex" and inner[1] in found:
                        found[inner[1]]["section"] = found[inner[1]]["section"] or keys[0]
    return found


def position(tree: Tree, expr: Expr, params_argument: bool) -> int | None:
    """The number position an expression reads, if it reads one."""
    for node in tree.walk(expr):
        if not isinstance(node, tuple):
            continue
        if node[0] == "idx" and isinstance(node[2], int):
            from_params = any(
                isinstance(part, tuple) and part[0] == "prop" and part[2] == "intParams"
                for part in tree.walk(node[1])
            )
            if from_params or (params_argument and node[1] == ("local", 1)):
                return node[2]
        if node[0] == "call" and node[2] == "getInt" and node[3] and isinstance(node[3][0], int):
            return int(node[3][0])
    return None


def target(expr: Expr) -> tuple[str, int | None] | None:
    """The form field a store goes to, and which of its options when it is a group."""
    if not isinstance(expr, tuple):
        return None
    if expr[0] == "lex":
        return expr[1], None
    if expr[0] == "call" and expr[2] in ("get", "getAt") and expr[3] and isinstance(expr[3][0], int):
        inner = target(expr[1])
        return (inner[0], expr[3][0]) if inner else None
    if expr[0] == "prop" and isinstance(expr[1], tuple) and expr[1][0] in ("scope", "local"):
        return expr[2], None
    if expr[0] in ("prop", "call"):
        return target(expr[1])
    return None


def readable(name: Any) -> bool:
    return (
        isinstance(name, str)
        and name not in GENERIC
        and not name.startswith(("Unknown", "_o_", "_a_"))
        and not GROUPS.match(name)
    )


class Client:
    def __init__(self, classes: list[AbcClass]) -> None:
        self.by_name = {cls.name: cls for cls in classes}
        tables = {name: self.by_name[name].statics for name in CODE_TABLES.values()}
        self.by_code: dict[tuple[str, int], list[AbcClass]] = {}
        for cls in classes:
            for method in ("code", "negativeCode"):
                ops = [op for op in cls.methods.get(method, []) if op not in ("getlocal0", "pushscope")]
                if len(ops) >= 2 and ops[0].startswith("getlex ") and ops[1].startswith("getproperty "):
                    table, constant = ops[0].split()[1], ops[1].split()[1]
                    if table in tables and constant in tables[table]:
                        self.by_code.setdefault((table, tables[table][constant]), []).append(cls)

    def method(self, cls: AbcClass | None, name: str) -> list[str]:
        while cls is not None:
            if cls.methods.get(name):
                return cls.methods[name]
            cls = self.by_name.get(cls.parent or "")
        return []

    def positions(self, cls: AbcClass) -> dict[int, dict[str, Any]]:
        build: list[tuple[Any, ...]] = []
        for name in ("buildInputs", "createInputs", "<init>"):
            build += run(self.method(cls, name))
        fields = controls(build)
        reads = [(s, False) for s in run(self.method(cls, "onEditStart"))]
        reads += [(s, True) for s in run(self.method(cls, "readIntParams"))]
        tree = Tree([s for s, _ in reads])
        found: dict[int, dict[str, Any]] = {}
        for statement, params_argument in reads:
            if statement[0] == "set":
                index = position(tree, statement[3], params_argument)
                store = statement[2]
                bare = statement[1] == "?" or (isinstance(statement[1], tuple) and statement[1][0] == "scope")
                where = (store, None) if bare else target(statement[1])
            else:
                index = next(
                    (i for a in statement[3] if (i := position(tree, a, params_argument)) is not None), None
                )
                where, store = target(statement[1]), None
            if index is None:
                continue
            control, option = where if where else (None, None)
            info = fields.get(control or "", {})
            label = info.get("options", {}).get(option) if option is not None else None
            label = label or info.get("label") or info.get("section")
            field = store if readable(store) and store != control else control if readable(control) else None
            if label or field:
                entry = {"label": label, "field": field.lstrip("_") if field else None}
                options = (
                    {str(k): v for k, v in info.get("options", {}).items() if v} if option is None else {}
                )
                if options and label:
                    entry["options"] = options
                found.setdefault(index, entry)
        return found


def build(swf: Path) -> dict[str, Any]:
    client = Client(read_classes(swf))
    facts = json.loads(FACTS.read_text(encoding="utf-8"))["boxes"]
    boxes: dict[str, Any] = {}
    for name, fact in facts.items():
        merged: dict[int, dict[str, Any]] = {}
        for cls in client.by_code.get((CODE_TABLES[fact["section"]], fact["code"]), []):
            for index, entry in client.positions(cls).items():
                if index < len(fact["numbers"]):
                    merged.setdefault(index, entry)
        if merged:
            boxes[name] = {str(index): merged[index] for index in sorted(merged)}
    return {
        "client": {
            "file": swf.name,
            "sha256": hashlib.sha256(swf.read_bytes()).hexdigest(),
            "read": datetime.now(UTC).date().isoformat(),
        },
        "boxes": boxes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--swf", type=Path, required=True, help="Habbo's AIR client, HabboAir.swf")
    args = parser.parse_args()
    data = build(args.swf.expanduser())
    LABELS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    named = sum(len(slots) for slots in data["boxes"].values())
    print(f"Wrote {named} positions across {len(data['boxes'])} boxes to {LABELS}")


if __name__ == "__main__":
    main()
