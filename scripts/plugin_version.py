"""The Turbo plugin's version: every change to ``turbo-plugin/`` raises it, and its changelog says why.

Checks, against a base git ref (``origin/main`` by default):

- when any file under ``turbo-plugin/`` differs from the base, ``turbo-plugin/manifest.json``'s
  ``Version`` is higher than the base's;
- the newest ``## <version>`` heading of ``turbo-plugin/CHANGELOG.md`` is that version.

``--bump patch|minor|major`` raises the version and adds an empty changelog heading for it, for
the person making the change.

    python scripts/plugin_version.py --check --base origin/main
    python scripts/plugin_version.py --bump patch
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = "turbo-plugin"
MANIFEST = f"{PLUGIN}/manifest.json"
CHANGELOG = f"{PLUGIN}/CHANGELOG.md"

_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_HEADING = re.compile(r"^## (\d+\.\d+\.\d+)\b", re.MULTILINE)


def parse(version: str) -> tuple[int, int, int]:
    """``"1.2.3"`` as ``(1, 2, 3)``; ValueError for anything else."""
    match = _VERSION.match(version.strip())
    if not match:
        raise ValueError(f"{version!r} is not a MAJOR.MINOR.PATCH version")
    major, minor, patch = (int(x) for x in match.groups())
    return major, minor, patch


def bumped(version: str, part: str) -> str:
    major, minor, patch = parse(version)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def manifest_version(text: str) -> str:
    version = json.loads(text).get("Version")
    if not isinstance(version, str):
        raise ValueError("the manifest has no Version")
    return version


def changelog_version(text: str) -> str | None:
    """The newest ``## <version>`` heading, or None when there is none."""
    match = _HEADING.search(text)
    return match.group(1) if match else None


def problems(*, changed: list[str], version: str, base_version: str | None, changelog: str) -> list[str]:
    """What is wrong with the plugin's version for a change touching ``changed``."""
    found: list[str] = []
    try:
        current = parse(version)
    except ValueError as ex:
        return [f"{MANIFEST}: {ex}"]

    plugin_changed = [x for x in changed if x.startswith(f"{PLUGIN}/")]
    if plugin_changed and base_version is not None and current <= parse(base_version):
        found.append(
            f"{len(plugin_changed)} plugin file(s) changed but {MANIFEST} is still {version} "
            f"(base {base_version}): raise it, e.g. python scripts/plugin_version.py --bump patch"
        )

    newest = changelog_version(changelog)
    if newest != version:
        found.append(f"{CHANGELOG}'s newest heading is {newest or 'missing'}, not the manifest's {version}")
    return found


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def _base_file(base: str, path: str) -> str | None:
    try:
        return _git("show", f"{base}:{path}")
    except subprocess.CalledProcessError:
        return None


def check(base: str) -> list[str]:
    # Committed and working-tree changes alike, so it also catches an unbumped local change.
    changed = _git("diff", "--name-only", base, "--", PLUGIN).split()
    base_manifest = _base_file(base, MANIFEST)
    return problems(
        changed=changed,
        version=manifest_version((ROOT / MANIFEST).read_text()),
        base_version=manifest_version(base_manifest) if base_manifest else None,
        changelog=(ROOT / CHANGELOG).read_text() if (ROOT / CHANGELOG).exists() else "",
    )


def bump(part: str) -> str:
    path = ROOT / MANIFEST
    manifest = json.loads(path.read_text())
    manifest["Version"] = bumped(manifest["Version"], part)
    path.write_text(json.dumps(manifest, indent=4) + "\n")

    log = ROOT / CHANGELOG
    text = log.read_text() if log.exists() else "# Wiredbench plugin changelog\n"
    heading = f"## {manifest['Version']} ({date.today().isoformat()})\n\n- \n\n"
    at = text.find("\n## ")
    text = text[: at + 1] + heading + text[at + 1 :] if at >= 0 else text.rstrip() + "\n\n" + heading
    log.write_text(text)
    return str(manifest["Version"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="fail when the version was not raised")
    group.add_argument("--bump", choices=["patch", "minor", "major"])
    parser.add_argument("--base", default="origin/main", help="git ref to compare with")
    args = parser.parse_args(argv)

    if args.bump:
        print(f"{MANIFEST}: {bump(args.bump)}; describe it in {CHANGELOG}")
        return 0

    found = check(args.base)
    for problem in found:
        print(problem, file=sys.stderr)
    if not found:
        print(f"{MANIFEST}: {manifest_version((ROOT / MANIFEST).read_text())} ok")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
