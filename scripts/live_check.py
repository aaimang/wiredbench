#!/usr/bin/env python3
"""Records how a real room's WIRED Web API answers, so the mock can be compared with it.

Reads WB_LIVE_CHECK_ROOM_ID, WB_LIVE_CHECK_READ_KEY, WB_LIVE_CHECK_WRITE_KEY and optionally
WB_LIVE_CHECK_HOTEL (default sandbox) from the environment or --env-file. Reads only, unless --write
is given. Prints status codes and response shapes: never keys, values, names or the room ID.

--write only changes a permanent global variable named wb_live_check, and puts its value back. Reload the room
after adding it, or the API may not list it. Exits 0 when every step ran, and 1 when the room refused the key,
limited the requests, could not be reached, or the value could not be put back.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from wiredbench.config import HOTELS

SCRATCH = "wb_live_check"  # The global variable --write may change. Its value is put back afterwards.
PAUSE_SECONDS = 0.2  # Habbo publishes no limits, so requests stay gentle.
RESTORE_TRIES = 3
RESTORE_WAIT_SECONDS = 5


class RateLimited(Exception):
    """The room answered 429, so nothing more should be sent."""


def load_env(path: Path | None) -> None:
    if path is None:
        return
    for line in path.read_text().splitlines():
        name, separator, value = line.partition("=")
        name = name.strip().removeprefix("export ").strip()
        if separator and name.startswith("WB_LIVE_CHECK_"):
            os.environ.setdefault(name, value.strip().strip("'\""))


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
    def __init__(
        self, client: httpx.Client, room: str, read: str, write: str, pause: float = PAUSE_SECONDS
    ) -> None:
        self.client, self.room, self.read, self.write, self.pause = client, room, read, write, pause
        self.lines: list[dict[str, Any]] = []

    def call(self, label: str, method: str, path: str, keys: str = "read", **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}))
        if "read" in keys:
            headers["X-Wired-Read-Key"] = self.read
        if "write" in keys:
            headers["X-Wired-Write-Key"] = self.write
        if keys == "bad":
            headers["X-Wired-Read-Key"] = "0" * 32
        if self.pause:
            time.sleep(self.pause)
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
        if response.status_code == 429:
            raise RateLimited
        return response


def read_checks(check: Check) -> dict[str, Any] | None:
    """Returns the room's variable names, or None if it would not list them."""
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
        return None
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
    return data


def batch_checks(check: Check, definitions: dict[str, Any]) -> None:
    """Empty batches change nothing. Batches exist for user and furni variables, so one of those is needed."""
    for scope, plural in (("user", "users"), ("furni", "furni")):
        names = definitions.get(plural) or []
        if names:
            path = f"/variables/{scope}/{names[0]}/batch"
            check.call("batch read key only", "POST", path, keys="read", json={"requests": []})
            check.call("batch write key only", "POST", path, keys="write", json={"requests": []})
            check.call("batch empty", "POST", path, keys="read write", json={"requests": []})
            return
    print("Skipped batch checks: the room lists no user or furni variable.", file=sys.stderr)


def restore(check: Check, path: str, value: str, wait: float = RESTORE_WAIT_SECONDS) -> bool:
    """Puts the value back and reads it again. It tries harder than other requests, even after a limit."""
    for attempt in range(RESTORE_TRIES):
        if attempt and wait:
            time.sleep(wait)
        try:
            check.call("restore", "PATCH", path, keys="write", json={"value": value})
            confirmed = check.call("restore confirmed", "GET", path)
            if confirmed.status_code == 200 and confirmed.json().get("value") == value:
                return True
        except (RateLimited, httpx.HTTPError):
            continue
    return False


def write_checks(check: Check, definitions: dict[str, Any], wait: float = RESTORE_WAIT_SECONDS) -> bool:
    """Returns False if the variable's value could not be put back. Only SCRATCH can change."""
    batch_checks(check, definitions)
    check.call(
        "bulk delete of nothing", "POST", "/variables/bulk-delete", keys="write", json={"variables": []}
    )
    check.call(
        "undefined global write",
        "PATCH",
        "/variables/global/wb_no_such_variable",
        keys="write",
        json={"value": 1},
    )
    if SCRATCH not in (definitions.get("global") or []):
        print(
            f"Skipped value writes: the API does not list {SCRATCH}. Make it a permanent global variable "
            "with a value, press Ready, and reload the room.",
            file=sys.stderr,
        )
        return True
    path = f"/variables/global/{SCRATCH}"
    before = check.call("scratch before", "GET", path)
    if before.status_code != 200:
        print(f"Skipped value writes: {SCRATCH} has no value to put back afterwards.", file=sys.stderr)
        return True
    original = before.json()["value"]
    try:
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
    finally:
        restored = restore(check, path, original, wait)
        if not restored:
            print(
                f"WARNING: {SCRATCH} may not have its old value back. Check it in the room.", file=sys.stderr
            )
    return restored


def run(check: Check, write: bool) -> int:
    definitions = read_checks(check)
    if definitions is None:
        print("The room would not list its variables, so the key or room ID needs checking.", file=sys.stderr)
        return 1
    if write and not write_checks(check, definitions):
        return 1
    return 0


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
    if args.write and not write:
        print("--write needs WB_LIVE_CHECK_WRITE_KEY", file=sys.stderr)
        return 2
    hotel = os.environ.get("WB_LIVE_CHECK_HOTEL", "sandbox")
    if hotel not in HOTELS:
        print(f"WB_LIVE_CHECK_HOTEL must be one of {sorted(HOTELS)}", file=sys.stderr)
        return 2
    headers = {"User-Agent": "wiredbench-live-check"}
    with httpx.Client(
        base_url=f"https://{HOTELS[hotel]}", headers=headers, timeout=20, follow_redirects=False
    ) as client:
        check = Check(client, room, read, write)
        try:
            code = run(check, args.write)
        except RateLimited:
            print("Stopped: the room is limiting requests. Try again later.", file=sys.stderr)
            code = 1
        except httpx.HTTPError as error:
            # Only the type: the message holds the address, which contains the room ID and variable names.
            print(f"Stopped: could not reach the room ({type(error).__name__}).", file=sys.stderr)
            code = 1
    text = json.dumps(check.lines, indent=1)
    if args.out:
        args.out.write_text(text)
    for line in check.lines:
        print(f"{line['status']} {line['check']}: {line['error'] or ''} {json.dumps(line['shape'])[:140]}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
