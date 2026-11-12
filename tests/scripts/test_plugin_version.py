"""scripts/plugin_version.py: a change to the Turbo plugin raises its version."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "plugin_version.py"
_SPEC = importlib.util.spec_from_file_location("plugin_version", _PATH)
assert _SPEC and _SPEC.loader
pv = importlib.util.module_from_spec(_SPEC)
sys.modules["plugin_version"] = pv
_SPEC.loader.exec_module(pv)

LOG = "# Wiredbench plugin changelog\n\n## 0.2.0 (2026-11-12)\n\n- x\n\n## 0.1.0\n"


def test_versions_compare_as_numbers() -> None:
    assert pv.parse("0.10.0") > pv.parse("0.9.9")
    with pytest.raises(ValueError):
        pv.parse("1.2")


@pytest.mark.parametrize(("part", "expected"), [("patch", "1.2.4"), ("minor", "1.3.0"), ("major", "2.0.0")])
def test_bumped(part: str, expected: str) -> None:
    assert pv.bumped("1.2.3", part) == expected


def test_a_plugin_change_without_a_new_version_is_refused() -> None:
    found = pv.problems(
        changed=["turbo-plugin/server/X.cs"], version="0.2.0", base_version="0.2.0", changelog=LOG
    )
    assert len(found) == 1
    assert "still 0.2.0" in found[0]


def test_a_raised_version_with_its_changelog_passes() -> None:
    assert not pv.problems(
        changed=["turbo-plugin/server/X.cs"], version="0.2.0", base_version="0.1.0", changelog=LOG
    )


def test_changes_outside_the_plugin_need_no_new_version() -> None:
    assert not pv.problems(changed=["backend/app.py"], version="0.2.0", base_version="0.2.0", changelog=LOG)


def test_the_changelog_names_the_manifest_s_version() -> None:
    found = pv.problems(changed=[], version="0.3.0", base_version="0.2.0", changelog=LOG)
    assert any("newest heading is 0.2.0" in x for x in found)


def test_the_repository_s_plugin_version_and_changelog_agree() -> None:
    root = _PATH.parents[1]
    version = pv.manifest_version((root / pv.MANIFEST).read_text())
    assert pv.changelog_version((root / pv.CHANGELOG).read_text()) == version
