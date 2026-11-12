"""The live check script, against a fake Habbo. It must never harm a room or print what it promises not to."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

READ, WRITE, ROOM = "secret-read-key", "secret-write-key", "424242"
SCRIPT = Path(__file__).parents[2] / "scripts/live_check.py"


@pytest.fixture
def live() -> ModuleType:
    spec = importlib.util.spec_from_file_location("live_check", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["live_check"] = module
    spec.loader.exec_module(module)
    return module


class FakeRoom:
    def __init__(
        self, listed: tuple[str, ...] = ("wb_live_check",), users: tuple[str, ...] = ("secret_score",)
    ) -> None:
        self.definitions = {"users": list(users), "furni": [], "global": list(listed)}
        self.value = "77"
        self.requests: list[httpx.Request] = []
        self.fail_on: str | None = None
        self.limit_after: int | None = None
        self.fail_restore = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.limit_after is not None and len(self.requests) > self.limit_after:
            return httpx.Response(429, json={"error": "too-many"})
        path = request.url.path.split(ROOM, 1)[1]
        body = json.loads(request.content) if request.content else {}
        if self.fail_on is not None and body.get("value") == self.fail_on:
            self.fail_on = None
            raise httpx.ReadTimeout("timed out", request=request)
        if request.method == "GET" and request.headers.get("x-wired-read-key") != READ:
            return httpx.Response(403, json={"error": "wired.variables.key_invalid"})
        if path == "/variables":
            return httpx.Response(200, json=self.definitions)
        if path == "/variables/global/wb_live_check":
            if request.method == "GET":
                return httpx.Response(
                    200, json={"value": self.value, "creation_time": "t", "update_time": "t"}
                )
            if isinstance(body.get("value"), int) or body.get("value") == "77":
                if not self.fail_restore:
                    self.value = str(body["value"])
                return httpx.Response(200, json={"value": self.value})
            return httpx.Response(400, json={"error": "request-failed-non-200"})
        return httpx.Response(404, json={"error": "wired.variables.not_found"})

    def client(self) -> httpx.Client:
        return httpx.Client(base_url="https://habbo.test", transport=httpx.MockTransport(self))

    def sent(self, method: str, ending: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == method and r.url.path.endswith(ending)]


def check(live: ModuleType, room: FakeRoom) -> Any:
    return live.Check(room.client(), ROOM, READ, WRITE, pause=0)


def test_reading_sends_no_writes(live: ModuleType) -> None:
    room = FakeRoom()
    assert live.run(check(live, room), write=False) == 0
    assert {r.method for r in room.requests} == {"GET"}
    assert room.value == "77"


def test_a_refused_key_exits_with_failure(live: ModuleType) -> None:
    room = FakeRoom()
    assert live.run(live.Check(room.client(), ROOM, "wrong", WRITE, pause=0), write=False) == 1


def test_writes_put_the_value_back_and_confirm_it(live: ModuleType) -> None:
    room = FakeRoom()
    runner = check(live, room)
    assert live.run(runner, write=True) == 0
    assert room.value == "77"
    assert [line["check"] for line in runner.lines][-2:] == ["restore", "restore confirmed"]


def test_only_the_scratch_variable_can_change(live: ModuleType) -> None:
    room = FakeRoom(listed=("wb_live_check", "something_else"))
    live.run(check(live, room), write=True)
    patched = {r.url.path.rsplit("/", 1)[1] for r in room.requests if r.method == "PATCH"}
    assert patched == {"wb_live_check", "wb_no_such_variable"}
    assert not [r for r in room.requests if r.method in ("PUT", "DELETE")]
    for request in room.sent("POST", "/bulk-delete"):
        assert json.loads(request.content) == {"variables": []}
    for request in room.sent("POST", "/batch"):
        assert json.loads(request.content) == {"requests": []}


def test_an_unlisted_scratch_variable_skips_value_writes(live: ModuleType, capsys: Any) -> None:
    room = FakeRoom(listed=("other",))
    assert live.run(check(live, room), write=True) == 0
    assert not room.sent("PATCH", "/wb_live_check")
    assert "does not list wb_live_check" in capsys.readouterr().err


def test_batch_checks_use_a_scope_that_has_batches(live: ModuleType) -> None:
    room = FakeRoom()
    live.run(check(live, room), write=True)
    paths = {r.url.path for r in room.sent("POST", "/batch")}
    assert paths == {f"/api/public/rooms/{ROOM}/variables/user/secret_score/batch"}
    headers = [
        set(r.headers) & {"x-wired-read-key", "x-wired-write-key"} for r in room.sent("POST", "/batch")
    ]
    assert headers == [{"x-wired-read-key"}, {"x-wired-write-key"}, {"x-wired-read-key", "x-wired-write-key"}]


def test_no_user_or_furni_variable_skips_batch_checks(live: ModuleType, capsys: Any) -> None:
    room = FakeRoom(users=())
    assert live.run(check(live, room), write=True) == 0
    assert not room.sent("POST", "/batch")
    assert "Skipped batch checks" in capsys.readouterr().err


def test_a_failure_midway_still_puts_the_value_back(live: ModuleType) -> None:
    room = FakeRoom()
    room.fail_on = "abc"
    with pytest.raises(httpx.ReadTimeout):
        live.write_checks(check(live, room), room.definitions, wait=0)
    assert room.value == "77"


def test_a_failed_restore_is_reported(live: ModuleType, capsys: Any) -> None:
    room = FakeRoom()
    runner = check(live, room)
    original = live.restore

    def broken(*args: Any, **kwargs: Any) -> bool:
        room.fail_restore = True
        room.value = "1"
        return original(*args, **kwargs)

    live.restore = broken
    assert live.write_checks(runner, room.definitions, wait=0) is False
    assert "may not have its old value back" in capsys.readouterr().err


def test_a_rate_limit_stops_the_run(live: ModuleType) -> None:
    room = FakeRoom()
    room.limit_after = 2
    with pytest.raises(live.RateLimited):
        live.run(check(live, room), write=False)
    assert len(room.requests) == 3


def test_load_env_reads_export_lines_and_skips_others(
    live: ModuleType, tmp_path: Path, monkeypatch: Any
) -> None:
    for name in ("WB_LIVE_CHECK_ROOM_ID", "WB_LIVE_CHECK_READ_KEY", "WB_ADMIN"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / "e"
    env.write_text(
        "export WB_LIVE_CHECK_ROOM_ID=1\nWB_LIVE_CHECK_READ_KEY='k'\nWB_ADMIN=x\n# WB_LIVE_CHECK_HOTEL=com\n"
    )
    live.load_env(env)
    import os

    assert os.environ["WB_LIVE_CHECK_ROOM_ID"] == "1"
    assert os.environ["WB_LIVE_CHECK_READ_KEY"] == "k"
    assert "WB_ADMIN" not in os.environ
    assert "WB_LIVE_CHECK_HOTEL" not in os.environ or os.environ["WB_LIVE_CHECK_HOTEL"] != "com"
    monkeypatch.delenv("WB_LIVE_CHECK_ROOM_ID")
    monkeypatch.delenv("WB_LIVE_CHECK_READ_KEY")


@pytest.mark.parametrize("failure", ["refused", "offline"])
def test_output_never_shows_secrets(live: ModuleType, monkeypatch: Any, capsys: Any, failure: str) -> None:
    def transport(request: httpx.Request) -> httpx.Response:
        if failure == "offline":
            raise httpx.ConnectError(f"cannot reach {request.url}", request=request)
        return httpx.Response(403, json={"error": "wired.variables.key_invalid"})

    real_client = httpx.Client
    monkeypatch.setattr(
        live.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(transport), **kw)
    )
    monkeypatch.setattr(live, "PAUSE_SECONDS", 0)
    monkeypatch.setattr(sys, "argv", ["live_check", "--write"])
    monkeypatch.setenv("WB_LIVE_CHECK_ROOM_ID", ROOM)
    monkeypatch.setenv("WB_LIVE_CHECK_READ_KEY", READ)
    monkeypatch.setenv("WB_LIVE_CHECK_WRITE_KEY", WRITE)
    monkeypatch.setenv("WB_LIVE_CHECK_HOTEL", "com")
    assert live.main() == 1
    output = capsys.readouterr()
    for secret in (READ, WRITE, ROOM):
        assert secret not in output.out + output.err


def test_every_hotel_is_accepted(live: ModuleType, monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setenv("WB_LIVE_CHECK_ROOM_ID", ROOM)
    monkeypatch.setenv("WB_LIVE_CHECK_READ_KEY", READ)
    monkeypatch.setenv("WB_LIVE_CHECK_HOTEL", "nowhere")
    monkeypatch.setattr(sys, "argv", ["live_check"])
    assert live.main() == 2
    assert "com.br" in capsys.readouterr().err
