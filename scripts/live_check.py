#!/usr/bin/env python3
"""Records how a real room's WIRED Web API answers, so the mock can be compared with it.

Reads WB_LIVE_CHECK_ROOM_ID, WB_LIVE_CHECK_READ_KEY, WB_LIVE_CHECK_WRITE_KEY and optionally
WB_LIVE_CHECK_HOTEL (default sandbox) from the environment or --env-file. Reads only, unless --write
is given. Prints status codes and response shapes: never keys, values, names or the room ID.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

HOSTS = {"sandbox": "sandbox.habbo.com", "com": "www.habbo.com"}
SCRATCH = "wb_live_check"  # A global variable the room must define for --write. It is removed again.


def load_env(path: Path | None) -> None:
    if path is None:
        return
    for line in path.read_text().splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip().startswith("WB_LIVE_CHECK_"):
            os.environ.setdefault(name.strip(), value.strip().strip("'\""))


def shape(value: Any) -> Any:
    """Keeps a response's structure and drops everything it says."""
    if isinstance(value, dict):
        return {k if k in KNOWN else "<name>": shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return type(value).__name__


KNOWN = {
    "body",
    "count",
    "creation_time",
    "error",
    "furni",
    "global",
    "id",
    "items",
    "message",
    "name",
    "op_id",
    "page",
    "results",
    "size",
    "status",
    "unique_id",
    "update_time",
    "user",
    "users",
    "value",
    "variable",
    "variables",
}


class Check:
    def __init__(self, client: httpx.Client, room: str, read: str, write: str) -> None:
        self.client, self.room, self.read, self.write = client, room, read, write
        self.lines: list[dict[str, Any]] = []

    def call(self, label: str, method: str, path: str, keys: str = "read", **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}))
        if "read" in keys:
            headers["X-Wired-Read-Key"] = self.read
        if "write" in keys:
            headers["X-Wired-Write-Key"] = self.write
        if keys == "bad":
            headers["X-Wired-Read-Key"] = "0" * 32
        response = self.client.request(
            method, f"/api/public/rooms/{self.room}{path}", headers=headers, **kwargs
        )
        try:
            body = shape(response.json())
            error = response.json().get("error") if isinstance(response.json(), dict) else None
        except ValueError:
            body, error = None, None
        self.lines.append(
            {
                "check": label,
                "status": response.status_code,
                "error": error if isinstance(error, str) else None,
                "etag": "etag" in response.headers,
                "shape": body,
            }
        )
        return response


def read_checks(check: Check) -> None:
    definitions = check.call("definitions", "GET", "/variables")
    check.call("no key", "GET", "/variables", keys="")
    check.call("wrong key", "GET", "/variables", keys="bad")
    check.call("write key on a read", "GET", "/variables", keys="write")
    etag = definitions.headers.get("etag")
    if etag:
        check.call("revalidate", "GET", "/variables", headers={"If-None-Match": etag})
    check.call("unknown global", "GET", "/variables/global/wb_no_such_variable")
    check.call("bad target", "GET", "/variables/user/wb_no_such_variable/nothing")
    check.call("unknown holders", "GET", "/variables/user/wb_no_such_variable/users")
    check.call("no profile", "GET", "/variables_profile/user/users/1")
    check.call("non-numeric entity", "GET", "/variables_profile/user/users/abc")
    check.call("global profile", "GET", "/variables_profile/global")
    check.call(
        "lookup without match", "GET", "/variables_profile/user/users", params={"name": "wb-no-such-user"}
    )
    check.call("bad scope", "GET", "/variables/nothing/x/users")
    if definitions.status_code != 200:
        return
    data = definitions.json()
    for scope, plural, kind in (("user", "users", "users"), ("furni", "furni", "furni")):
        names = data.get(plural) or []
        if not names:
            continue
        name = names[0]
        check.call(f"{scope} holders", "GET", f"/variables/{scope}/{name}/{kind}")
        check.call(f"{scope} count", "GET", f"/variables/{scope}/{name}/{kind}/count")
        check.call(f"{scope} page 0", "GET", f"/variables/{scope}/{name}/{kind}", params={"page": 0})
        check.call(f"{scope} size 1000", "GET", f"/variables/{scope}/{name}/{kind}", params={"size": 1000})
        check.call(f"{scope} bad order", "GET", f"/variables/{scope}/{name}/{kind}", params={"order_by": "x"})
    if data.get("global"):
        check.call("global value", "GET", f"/variables/global/{data['global'][0]}")


def write_checks(check: Check) -> None:
    """Only touches SCRATCH, and only the assumed behaviours. Needs a global variable named SCRATCH."""
    path = f"/variables/global/{SCRATCH}"
    before = check.call("scratch before", "GET", path)
    check.call(
        "undefined global write",
        "PATCH",
        "/variables/global/wb_no_such_variable",
        keys="write",
        json={"value": 1},
    )
    for label, value in (
        ("write number", 1),
        ("write text", "abc"),
        ("write decimal", 1.5),
        ("write bool", True),
        ("write null", None),
        ("write too big", str(2**63)),
    ):
        check.call(label, "PATCH", path, keys="write", json={"value": value})
    check.call("write no body", "PATCH", path, keys="write")
    check.call("batch read key only", "POST", f"{path}/batch", keys="read", json={"requests": []})
    check.call("batch empty", "POST", f"{path}/batch", keys="read write", json={"requests": []})
    check.call(
        "bulk delete of nothing", "POST", "/variables/bulk-delete", keys="write", json={"variables": []}
    )
    if before.status_code == 200:
        check.call("restore", "PATCH", path, keys="write", json={"value": before.json()["value"]})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--write", action="store_true", help="Also send writes to the scratch variable.")
    parser.add_argument("--out", type=Path, help="Save the results as JSON.")
    args = parser.parse_args()
    load_env(args.env_file)
    try:
        room = os.environ["WB_LIVE_CHECK_ROOM_ID"]
        read = os.environ["WB_LIVE_CHECK_READ_KEY"]
    except KeyError as missing:
        print(f"Missing {missing.args[0]}", file=sys.stderr)
        return 2
    write = os.environ.get("WB_LIVE_CHECK_WRITE_KEY", "")
    hotel = os.environ.get("WB_LIVE_CHECK_HOTEL", "sandbox")
    if hotel not in HOSTS:
        print(f"WB_LIVE_CHECK_HOTEL must be one of {sorted(HOSTS)}", file=sys.stderr)
        return 2
    headers = {"User-Agent": "wiredbench-live-check"}
    with httpx.Client(
        base_url=f"https://{HOSTS[hotel]}", headers=headers, timeout=20, follow_redirects=False
    ) as client:
        check = Check(client, room, read, write)
        read_checks(check)
        if args.write:
            if not write:
                print("--write needs WB_LIVE_CHECK_WRITE_KEY", file=sys.stderr)
                return 2
            write_checks(check)
    text = json.dumps(check.lines, indent=1)
    if args.out:
        args.out.write_text(text)
    for line in check.lines:
        print(f"{line['status']} {line['check']}: {line['error'] or ''} {json.dumps(line['shape'])[:140]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
