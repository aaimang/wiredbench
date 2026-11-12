"""A pytest plugin: every Engine the tests build, with what it was given and the inputs it took.

Loaded by scripts/behaviour.py (``pytest -p behaviour_recorder``); it changes nothing the tests see.
At the end of the session it writes what it saw to the file named by ``WB_BEHAVIOUR_RECORD``.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import pytest

from wiredbench.engine import core

_seen: list[tuple[str, Any, dict[str, Any]]] = []
_current = ["(collection)"]
_original_init = core.Engine.__init__


def _recording_init(self: Any, document: dict[str, Any], *args: Any, **kwargs: Any) -> None:
    names = ("heights", "seed", "tick_ms", "furni_states", "not_standable", "furni_facts", "clock_start_ms")
    given = dict(zip(names, args, strict=False)) | kwargs
    _seen.append((_current[0], self, {"document": copy.deepcopy(document), **copy.deepcopy(given)}))
    _original_init(self, document, *args, **kwargs)


core.Engine.__init__ = _recording_init  # type: ignore[method-assign]


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    _current[0] = item.nodeid


def pytest_sessionfinish(session: pytest.Session) -> None:
    out = os.environ.get("WB_BEHAVIOUR_RECORD")
    if not out:
        return
    rows = []
    for test, engine, given in _seen:
        not_standable = given.get("not_standable")
        rows.append(
            {
                "test": test,
                **{k: v for k, v in given.items() if k != "not_standable"},
                "not_standable": sorted(not_standable) if not_standable else [],
                "inputs": copy.deepcopy(engine.inputs),
                "until_ms": engine.now_ms,
            }
        )
    Path(out).write_text(json.dumps(rows, default=str))
