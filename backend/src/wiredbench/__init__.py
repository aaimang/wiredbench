"""Wiredbench: a self-hosted Habbo WIRED sandbox."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("wiredbench")
except PackageNotFoundError:
    __version__ = "0.0.0"
