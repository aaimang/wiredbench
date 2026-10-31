"""Spike: run the official wired-api-python wrapper against the mock over real HTTP."""

from __future__ import annotations

import socket
import threading
import time

import uvicorn
from wired_api_python import HabboApiException, HabboPublicAPI, UserTargetKind

from mock_api import Room, create_app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    room = Room("r", "w", definitions={"user": {"score"}, "furni": set(), "global": {"clock"}})
    room.users["44"] = {"id": 44, "name": "SomeName", "unique_id": "hhus-abc"}
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_app({1: room}), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.02)

    api = HabboPublicAPI(f"http://127.0.0.1:{port}/")
    wired = api.variables(1, "r", "w")
    users = wired.user()
    checks = {}

    listed = wired.list_all()
    checks["list_all"] = listed
    checks["give_variable"] = users.give_variable("score", UserTargetKind.USERS, 44, 5)
    checks["change_variable"] = users.change_variable("score", UserTargetKind.USERS, 44, 9)
    checks["get_variable"] = users.get_variable("score", UserTargetKind.USERS, 44)
    checks["list_holders"] = users.list_holders("score", UserTargetKind.USERS)
    checks["count_holders"] = users.count_holders("score", UserTargetKind.USERS)
    checks["profile_by_name"] = users.get_profile_by_username("somename")
    batch = users.build_batch_request("score")
    batch.get_variable("a", UserTargetKind.USERS, 44)
    try:
        checks["batch"] = batch.execute_request()
    except TypeError as exc:
        # wired-api-python 0.1.4 parses "error": null, which the live hotel returns, as an error object.
        checks["batch"] = f"KNOWN WRAPPER BUG on successful ops: {exc}"
    checks["global_change"] = wired.global_().change_variable("clock", 3)
    checks["global_get"] = wired.global_().get_variable("clock")
    checks["global_profile"] = wired.global_().get_profile()

    try:
        api.variables(1, "wrong", "wrong").list_all()
        checks["bad_key"] = "NOT REFUSED"
    except HabboApiException as exc:
        checks["bad_key"] = f"refused: {exc}"

    users.remove_variable("score", UserTargetKind.USERS, 44)
    try:
        users.get_variable("score", UserTargetKind.USERS, 44)
        checks["after_remove"] = "STILL THERE"
    except HabboApiException as exc:
        checks["after_remove"] = f"gone: {exc}"

    for name, value in checks.items():
        print(f"{name}: {str(value)[:150]}")
    server.should_exit = True


if __name__ == "__main__":
    main()
