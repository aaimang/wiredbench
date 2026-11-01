from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from wiredbench.api.deps import Services, get_services, viewer
from wiredbench.config import Hotel
from wiredbench.errors import ApiError, not_found
from wiredbench.services.assets import FIGURE, HABBO_NAME
from wiredbench.services.upstream import UpstreamError

router = APIRouter(prefix="/api", tags=["assets"])

IMMUTABLE = {"Cache-Control": "private, max-age=31536000, immutable"}
# A pose with what the avatar is doing on top, such as sit,sig=6 or wlk,crr=1.
ACTION_PART = r"(?:std|wlk|sit|lay|wav|blw|lgh|respect|crr(?:=\d{1,4})?|drk(?:=\d{1,4})?|sig(?:=\d{1,2})?)"
ACTION = rf"^{ACTION_PART}(?:,{ACTION_PART}){{0,3}}$"
Gesture = Literal["std", "sml", "agr", "sad", "srp", "spk", "eyb"]


async def _furni(revision: int, classname: str, services: Services) -> tuple[str, str]:
    # Only what the catalogue lists can reach Habbo, so this is not an open proxy.
    if not await run_in_threadpool(services.catalog.item_exists, classname, revision):
        raise not_found("Furni")
    try:
        paths = await run_in_threadpool(services.assets.furni, revision, classname)
    except UpstreamError as exc:
        raise ApiError(502, "upstream_unavailable", "Could not download this furni.") from exc
    if paths is None:
        raise not_found("Furni images")
    return str(paths[0]), str(paths[1])


@router.get("/furni/{revision}/{classname}/manifest")
@viewer
async def furni_manifest(
    revision: int, classname: str, services: Services = Depends(get_services)
) -> FileResponse:
    manifest, _ = await _furni(revision, classname, services)
    return FileResponse(manifest, media_type="application/json", headers=IMMUTABLE)


@router.get("/furni/{revision}/{classname}/atlas")
@viewer
async def furni_atlas(
    revision: int, classname: str, services: Services = Depends(get_services)
) -> FileResponse:
    _, atlas = await _furni(revision, classname, services)
    return FileResponse(atlas, media_type="image/png", headers=IMMUTABLE)


@router.get("/avatars/{hotel}/lookup")
@viewer
async def avatar_lookup(
    hotel: Hotel, name: str = Query(max_length=32), services: Services = Depends(get_services)
) -> dict[str, str]:
    if not HABBO_NAME.fullmatch(name):
        raise ApiError(422, "invalid_request", "That is not a valid Habbo name.")
    try:
        found = await run_in_threadpool(services.assets.lookup_figure, hotel, name)
    except UpstreamError as exc:
        raise ApiError(502, "upstream_unavailable", "Could not reach this hotel.") from exc
    if found is None:
        raise ApiError(404, "not_found", "No Habbo has that name on this hotel.")
    return found


@router.get("/avatars/{hotel}/image")
@viewer
async def avatar_image(
    hotel: Hotel,
    figure: str = Query(max_length=400),
    action: str = Query("std", pattern=ACTION, max_length=40),
    gesture: Gesture = "std",
    direction: int = Query(2, ge=0, le=7),
    frame: int = Query(0, ge=0, le=3),
    services: Services = Depends(get_services),
) -> FileResponse:
    if not FIGURE.fullmatch(figure):
        raise ApiError(422, "invalid_request", "That is not a valid avatar look.")
    try:
        path = await run_in_threadpool(
            services.assets.avatar, hotel, figure, action, gesture, direction, frame
        )
    except UpstreamError as exc:
        raise ApiError(502, "upstream_unavailable", "Could not download this avatar.") from exc
    if path is None:
        raise not_found("Avatar")
    return FileResponse(path, media_type="image/png", headers=IMMUTABLE)
