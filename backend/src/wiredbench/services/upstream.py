"""The only code that talks to Habbo. It can reach a fixed list of hosts and nothing else."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from wiredbench import __version__
from wiredbench.config import HOTELS

IMAGE_HOST = "images.habbo.com"
ALLOWED_HOSTS = frozenset(HOTELS.values()) | {IMAGE_HOST}
MAX_REDIRECTS = 3
REDIRECTS = {301, 302, 303, 307, 308}


class UpstreamError(Exception):
    """Habbo could not be reached, or sent something unusable."""


@dataclass(frozen=True)
class Fetched:
    status: int
    body: bytes
    etag: str | None
    content_type: str


class Upstream:
    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(30, connect=10),
            follow_redirects=False,  # See get().
            headers={"User-Agent": f"Wiredbench/{__version__} (self-hosted WIRED sandbox)"},
        )

    def close(self) -> None:
        self._client.close()

    def get(self, url: str, max_bytes: int, etag: str | None = None) -> Fetched:
        # Redirects are followed by hand, because every hop must pass the host check. Habbo's furnidata
        # URL always answers 307 to a URL containing a content hash, and only that URL answers 304.
        for _ in range(MAX_REDIRECTS + 1):
            fetched, location = self._get_once(url, max_bytes, etag)
            if location is None:
                return fetched
            url = urljoin(url, location)
        raise UpstreamError("Too many redirects.")

    def _get_once(self, url: str, max_bytes: int, etag: str | None) -> tuple[Fetched, str | None]:
        if urlsplit(url).hostname not in ALLOWED_HOSTS or not url.startswith("https://"):
            raise UpstreamError("Refused to contact a host outside the Habbo list.")
        headers = {"If-None-Match": etag} if etag else {}
        try:
            with self._client.stream("GET", url, headers=headers) as res:
                location = res.headers.get("location") if res.status_code in REDIRECTS else None
                body = bytearray()
                if res.status_code == 200:
                    # iter_bytes decompresses, so this also limits a compressed bomb.
                    for chunk in res.iter_bytes():
                        body += chunk
                        if len(body) > max_bytes:
                            raise UpstreamError(f"Download is larger than the {max_bytes // 2**20} MB limit.")
                fetched = Fetched(
                    res.status_code, bytes(body), res.headers.get("etag"), res.headers.get("content-type", "")
                )
                return fetched, location
        except httpx.HTTPError as exc:
            raise UpstreamError(f"Could not reach {urlsplit(url).hostname}: {type(exc).__name__}.") from exc


def furnidata_url(hotel: str) -> str:
    return f"https://{HOTELS[hotel]}/gamedata/furnidata_json/1"


def icon_url(revision: int, classname: str) -> str:
    # Colour variants are written name*2 in furnidata and name_2 in asset paths.
    return f"https://{IMAGE_HOST}/dcr/hof_furni/{revision}/{classname.replace('*', '_')}_icon.png"
