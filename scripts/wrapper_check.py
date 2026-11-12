#!/usr/bin/env python3
"""Runs the official wired-api-python wrapper against Turbo's WIRED Web API over real HTTP.

uv run --no-project --with wired-api-python==0.1.4 --with httpx python scripts/wrapper_check.py

Set up a room in a running Turbo first: a "Variable Global Add-on: Web API" box (its keys), a user
variable box named score and a room variable box named clock, and a user standing in the room.
Then set WB_WRAPPER_ROOM_ID, WB_WRAPPER_READ_KEY, WB_WRAPPER_WRITE_KEY, WB_WRAPPER_USER_ID and
WB_WRAPPER_USER_NAME (that user), and WB_WRAPPER_BASE_URL when the public API is not at
http://127.0.0.1:8092. Exits 1 when a step fails.
"""

import os
import sys

from wired_api_python import HabboApiException, HabboPublicAPI, UserTargetKind

try:
    room = int(os.environ["WB_WRAPPER_ROOM_ID"])
    read_key = os.environ["WB_WRAPPER_READ_KEY"]
    write_key = os.environ["WB_WRAPPER_WRITE_KEY"]
    AVATAR = int(os.environ["WB_WRAPPER_USER_ID"])
    user_name = os.environ["WB_WRAPPER_USER_NAME"]
except KeyError as missing:
    raise SystemExit(f"Missing {missing.args[0]}") from None
base = os.environ.get("WB_WRAPPER_BASE_URL", "http://127.0.0.1:8092").rstrip("/")

api = HabboPublicAPI(base + "/")
wired = api.variables(room, read_key, write_key)
users = wired.user()
KIND = UserTargetKind.USERS


def batch() -> object:
    request = users.build_batch_request("score")
    request.get_variable("a", KIND, AVATAR)
    try:
        return request.execute_request()
    except TypeError as exc:
        # 0.1.4 parses "error": null, which real rooms send, as an error object. Known wrapper bug.
        return f"known wrapper bug: {exc}"


def refused() -> str:
    try:
        api.variables(room, "wrong", "wrong").list_all()
    except HabboApiException as exc:
        return f"refused: {exc}"
    raise AssertionError("A wrong key was accepted")


steps = {
    "list_all": wired.list_all,
    "give_variable": lambda: users.give_variable("score", KIND, AVATAR, 5),
    "change_variable": lambda: users.change_variable("score", KIND, AVATAR, 9),
    "get_variable": lambda: users.get_variable("score", KIND, AVATAR),
    "list_holders": lambda: users.list_holders("score", KIND),
    "count_holders": lambda: users.count_holders("score", KIND),
    "profile_by_name": lambda: users.get_profile_by_username(user_name),
    "batch": batch,
    "global_change": lambda: wired.global_().change_variable("clock", 3),
    "global_get": lambda: wired.global_().get_variable("clock"),
    "global_profile": lambda: wired.global_().get_profile(),
    "bad_key": refused,
    "remove_variable": lambda: users.remove_variable("score", KIND, AVATAR),
}
failed = 0
for name, step in steps.items():
    try:
        print("ok  ", name, repr(step())[:100])
    except Exception as exc:
        failed += 1
        print("FAIL", name, type(exc).__name__, str(exc)[:160])
sys.exit(1 if failed else 0)
