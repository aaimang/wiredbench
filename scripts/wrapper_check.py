#!/usr/bin/env python3
"""Runs the official wired-api-python wrapper against the app's mock API over real HTTP.

uv run --with wired-api-python==0.1.4 python scripts/wrapper_check.py
"""

import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from wired_api_python import HabboApiException, HabboPublicAPI, UserTargetKind

from wiredbench.app import create_app
from wiredbench.config import Settings
from wiredbench.engine.tutorials import AVATAR

with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
tmp = Path(tempfile.mkdtemp())
base = f"http://127.0.0.1:{port}"
settings = Settings(_env_file=None, data_dir=tmp / "d", public_url=base)
app = create_app(settings)  # Generates the first admin password, which is all this needs.
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
threading.Thread(target=server.run, daemon=True).start()
while not server.started:
    time.sleep(0.02)

admin = httpx.Client(base_url=base)
admin.headers["X-CSRF-Token"] = admin.post(
    "/api/auth/login",
    json={"username": "admin", "password": settings.initial_password_path.read_text().strip()},
).json()["csrf_token"]
room = admin.post("/api/tutorials/time-tracking", json={}).json()["id"]
document = admin.get(f"/api/sandboxes/{room}").json()["document"]
document["furni"] += [
    {"id": 901, "classname": "wf_var_user", "x": 1, "y": 9, "z": 0, "wired": {"variable": "score"}},
    {"id": 903, "classname": "wf_var_room", "x": 3, "y": 9, "z": 0, "wired": {"variable": "clock"}},
]
saved = admin.put(f"/api/sandboxes/{room}/document", json={"document": document, "base_revision": 2})
if saved.status_code != 200:
    raise SystemExit(saved.text)
keys = admin.post(f"/api/sandboxes/{room}/api-keys", json={}).json()
admin.post(f"/api/sandboxes/{room}/run", json={"seed": 1})

api = HabboPublicAPI(base + "/")
wired = api.variables(room, keys["read_key"], keys["write_key"])
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
    "profile_by_name": lambda: users.get_profile_by_username("worker"),
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
server.should_exit = True
sys.exit(1 if failed else 0)
