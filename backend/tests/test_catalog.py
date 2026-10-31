from __future__ import annotations

import gzip
import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from conftest import PNG, Api, FakeHabbo, apply_update, furni, furnidata
from wiredbench.app import maintenance
from wiredbench.config import Settings
from wiredbench.services.upstream import Upstream


def status(api: Api, hotel: str = "sandbox") -> dict:
    return api.get("/api/catalog/status", params={"hotel": hotel}).json()


def classnames(api: Api, **params: str) -> list[str]:
    res = api.get("/api/catalog/items", params={"hotel": "sandbox", "scope": "all", **params}).json()
    return [item["classname"] for item in res["items"]]


def test_first_import_needs_review_before_it_applies(api: Api) -> None:
    assert classnames(api) == []
    res = api.post("/api/catalog/sync", json={"hotel": "sandbox"}).json()
    assert res["result"] == "first_import"
    assert classnames(api) == [], "nothing is visible until applied"
    assert res["status"]["pending"]["item_count"] == 2
    diff = api.get(f"/api/catalog/diff/0/{res['version_id']}").json()
    assert diff["summary"]["wired_new"] == 1 and diff["summary"]["other_new"] == 1
    assert api.post("/api/catalog/apply", json={"version_id": res["version_id"]}).status_code == 200
    assert classnames(api) == ["wf_trg_says_something", "chair"]


def test_check_sends_etag_and_304_means_up_to_date(api: Api, habbo: FakeHabbo) -> None:
    apply_update(api)
    res = api.post("/api/catalog/sync", json={"hotel": "sandbox"}).json()
    assert res["result"] == "up_to_date"
    assert habbo.requests[-1].headers["if-none-match"] == 'W/"v1"'
    assert status(api)["last_result"] == "up_to_date"
    assert status(api)["last_checked_at"]


def test_force_refresh_omits_etag(api: Api, habbo: FakeHabbo) -> None:
    apply_update(api)
    res = api.post("/api/catalog/sync", json={"hotel": "sandbox", "force": True}).json()
    assert "if-none-match" not in habbo.requests[-1].headers
    assert res["result"] == "up_to_date", "same content, so no new version"
    assert len(status(api)["versions"]) == 1


def test_same_content_with_new_etag_makes_no_version(api: Api, habbo: FakeHabbo) -> None:
    apply_update(api)
    habbo.etag = 'W/"v2"'
    assert api.post("/api/catalog/sync", json={"hotel": "sandbox"}).json()["result"] == "up_to_date"
    assert len(status(api)["versions"]) == 1
    assert api.post("/api/catalog/sync", json={"hotel": "sandbox"}).json()["result"] == "up_to_date"
    assert habbo.requests[-1].headers["if-none-match"] == 'W/"v2"'


def test_update_shows_correct_diff_then_applies(api: Api, habbo: FakeHabbo) -> None:
    first = apply_update(api)
    habbo.set(
        furnidata(
            furni("chair", name="Better Chair"),
            furni("wf_act_new_thing"),
            furni("sofa"),
        ),
        'W/"v2"',
    )
    res = api.post("/api/catalog/sync", json={"hotel": "sandbox"}).json()
    assert res["result"] == "update_available"
    second = res["version_id"]
    assert status(api)["updates_waiting"] == ["sandbox"]

    diff = api.get(f"/api/catalog/diff/{first}/{second}").json()
    assert diff["summary"] == {
        "wired_new": 1,
        "wired_changed": 0,
        "wired_removed": 1,
        "other_new": 1,
        "other_changed": 1,
        "other_removed": 0,
    }
    assert [e["classname"] for e in diff["entries"][:2]] == ["wf_act_new_thing", "wf_trg_says_something"]
    chair = next(e for e in diff["entries"] if e["classname"] == "chair")
    assert chair["fields"] == [{"field": "name", "old": "Chair", "new": "Better Chair"}]

    assert "wf_trg_says_something" in classnames(api), "old version stays until applied"
    api.post("/api/catalog/apply", json={"version_id": second})
    assert set(classnames(api)) == {"chair", "wf_act_new_thing", "sofa"}
    assert status(api)["updates_waiting"] == []
    new_item = api.get("/api/catalog/items/wf_act_new_thing", params={"hotel": "sandbox"}).json()
    assert new_item["is_new"] is True
    assert classnames(api, stage="new") == ["wf_act_new_thing", "sofa"]


def test_diff_paging_and_hotel_check(api: Api, habbo: FakeHabbo) -> None:
    first = apply_update(api)
    habbo.set(furnidata(*[furni(f"item{i}") for i in range(10)]), 'W/"v2"')
    second = api.post("/api/catalog/sync", json={"hotel": "sandbox"}).json()["version_id"]
    page = api.get(f"/api/catalog/diff/{first}/{second}", params={"offset": 2, "limit": 3}).json()
    assert page["total"] == 12
    assert len(page["entries"]) == 3
    other = apply_update(api, "com")
    assert api.get(f"/api/catalog/diff/{other}/{second}").status_code == 400
    assert api.get("/api/catalog/diff/999/1").status_code == 404


def test_dismiss_keeps_current_and_manual_check_offers_it_again(api: Api, habbo: FakeHabbo) -> None:
    first = apply_update(api)
    habbo.set(furnidata(furni("sofa")), 'W/"v2"')
    second = api.post("/api/catalog/sync", json={"hotel": "sandbox"}).json()["version_id"]
    assert api.post("/api/catalog/dismiss", json={"version_id": second}).status_code == 204
    assert status(api)["pending"] is None
    assert status(api)["current"]["id"] == first
    res = api.post("/api/catalog/sync", json={"hotel": "sandbox"}).json()
    assert res["result"] == "update_available"
    assert res["version_id"] == second
    assert api.post("/api/catalog/dismiss", json={"version_id": first}).status_code == 409


def test_rollback(api: Api, habbo: FakeHabbo) -> None:
    first = apply_update(api)
    habbo.set(furnidata(furni("sofa")), 'W/"v2"')
    second = apply_update(api)
    assert classnames(api) == ["sofa"]
    assert api.post("/api/catalog/rollback", json={"version_id": first}).status_code == 200
    assert "chair" in classnames(api)
    assert status(api)["current"]["id"] == first
    versions = {v["id"]: v["status"] for v in status(api)["versions"]}
    assert versions == {first: "current", second: "archived"}
    assert api.post("/api/catalog/rollback", json={"version_id": first}).status_code == 409
    assert api.post("/api/catalog/apply", json={"version_id": second}).status_code == 409


def test_only_recent_versions_are_kept_with_their_files(
    api: Api, habbo: FakeHabbo, settings: Settings
) -> None:
    for number in range(8):
        habbo.set(furnidata(furni(f"item{number}")), f'W/"v{number}"')
        apply_update(api)
    versions = status(api)["versions"]
    assert len(versions) == 5
    assert sum(v["status"] == "current" for v in versions) == 1
    files = list((settings.gamedata_dir / "sandbox").glob("*.json.gz"))
    assert {f.name.split(".")[0] for f in files} == {v["sha256"] for v in versions}


def test_raw_file_is_stored_gzipped(api: Api, settings: Settings) -> None:
    apply_update(api)
    current = status(api)["current"]
    raw = settings.gamedata_dir / "sandbox" / f"{current['sha256']}.json.gz"
    assert json.loads(gzip.decompress(raw.read_bytes()))["roomitemtypes"]


def test_failures_change_nothing_and_say_so(api: Api, habbo: FakeHabbo, settings: Settings) -> None:
    first = apply_update(api)

    def assert_failed(code: str) -> None:
        res = api.post("/api/catalog/sync", json={"hotel": "sandbox", "force": True})
        assert res.status_code == 502
        assert res.json()["error"] == code
        assert "not changed" in res.json()["message"]
        current = status(api)
        assert current["current"]["id"] == first
        assert len(current["versions"]) == 1
        assert current["last_result"] == "failed"
        assert current["last_error"]
        assert "chair" in classnames(api)

    habbo.fail = True
    assert_failed("upstream_unavailable")
    habbo.fail = False
    habbo.status = 500
    assert_failed("upstream_unavailable")
    habbo.status = None
    habbo.set(b"<html>blocked</html>", 'W/"bad"')
    assert_failed("invalid_furnidata")
    habbo.set(furnidata(), 'W/"empty"')
    assert_failed("invalid_furnidata")
    assert len(list((settings.gamedata_dir / "sandbox").glob("*"))) == 1, "no stray files"


def test_oversized_download_is_refused(api: Api, habbo: FakeHabbo, settings: Settings) -> None:
    habbo.set(b"x" * (settings.max_gamedata_mb * 2**20 + 1), 'W/"big"')
    res = api.post("/api/catalog/sync", json={"hotel": "sandbox"})
    assert res.status_code == 502
    assert "limit" in res.json()["message"]


def test_cooldown(api: Api, settings: Settings) -> None:
    settings.sync_cooldown_seconds = 60
    assert api.post("/api/catalog/sync", json={"hotel": "sandbox"}).status_code == 200
    res = api.post("/api/catalog/sync", json={"hotel": "sandbox"})
    assert res.status_code == 429
    assert res.json()["error"] == "sync_cooldown"
    assert int(res.headers["retry-after"]) > 0
    assert status(api)["cooldown_seconds"] > 0
    assert api.post("/api/catalog/sync", json={"hotel": "com"}).status_code == 200, "per hotel"


def test_one_sync_at_a_time(api: Api) -> None:
    lock = api.services.catalog._lock_for("sandbox")
    lock.acquire()
    try:
        res = api.post("/api/catalog/sync", json={"hotel": "sandbox"})
        assert res.status_code == 409
        assert res.json()["error"] == "sync_running"
    finally:
        lock.release()


def test_only_habbo_hosts_can_be_contacted(habbo: FakeHabbo) -> None:
    from pytest import raises

    from wiredbench.services.upstream import UpstreamError

    upstream = Upstream(httpx.MockTransport(habbo))
    for url in (
        "https://evil.example/x",
        "http://www.habbo.com/x",
        "https://www.habbo.com.evil.example/x",
        "https://www.habbo.com@evil.example/x",
        "https://169.254.169.254/latest",
    ):
        with raises(UpstreamError):
            upstream.get(url, 1000)
    assert habbo.requests == []


def test_search_filters_and_etag(api: Api, habbo: FakeHabbo) -> None:
    habbo.set(
        furnidata(
            furni("chair", name="Plain Chair"),
            furni("wf_trg_click", name="Click", description="Fires on click"),
            furni("wf_act_move", name="Move"),
            furni("wf_test_act", offerid=-1, bc=False),
            furni("wf_antenna1"),
        ),
        'W/"v1"',
    )
    apply_update(api)
    params = {"hotel": "sandbox"}
    wired = api.get("/api/catalog/items", params=params).json()
    assert wired["total"] == 4
    assert [i["classname"] for i in wired["items"]] == [
        "wf_trg_click",
        "wf_act_move",
        "wf_test_act",
        "wf_antenna1",
    ]
    assert wired["facets"] == {"trigger": 1, "effect": 2, "utility": 1}

    assert classnames(api, q="fires click") == ["wf_trg_click"]
    assert classnames(api, q="CHAIR") == ["chair"]
    assert classnames(api, q="wf_act") == ["wf_act_move"], "underscore is literal"
    assert classnames(api, wired_type="effect", stage="not_in_catalogue") == ["wf_test_act"]
    assert len(classnames(api, limit="2")) == 2

    first = api.get("/api/catalog/items", params=params)
    again = api.get("/api/catalog/items", params=params, headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
    other = api.get(
        "/api/catalog/items", params={**params, "q": "x"}, headers={"If-None-Match": first.headers["etag"]}
    )
    assert other.status_code == 200


def test_etag_changes_after_apply(api: Api, habbo: FakeHabbo) -> None:
    apply_update(api)
    first = api.get("/api/catalog/items", params={"hotel": "sandbox"})
    habbo.set(furnidata(furni("wf_act_z")), 'W/"v2"')
    apply_update(api)
    res = api.get(
        "/api/catalog/items", params={"hotel": "sandbox"}, headers={"If-None-Match": first.headers["etag"]}
    )
    assert res.status_code == 200


def test_item_detail_has_raw_data(api: Api) -> None:
    apply_update(api)
    item = api.get("/api/catalog/items/chair", params={"hotel": "sandbox"}).json()
    assert item["data"]["classname"] == "chair"
    assert api.get("/api/catalog/items/ghost", params={"hotel": "sandbox"}).status_code == 404


def test_hotels_are_separate(api: Api, habbo: FakeHabbo) -> None:
    apply_update(api, "sandbox")
    habbo.set(furnidata(furni("sofa")), 'W/"com"')
    apply_update(api, "com")
    assert api.get("/api/catalog/items", params={"hotel": "com", "scope": "all"}).json()["total"] == 1
    assert "chair" in classnames(api)
    assert {"www.habbo.com", "sandbox.habbo.com"} <= {r.url.host for r in habbo.requests}


def test_icons_are_cached_and_limited_to_the_catalogue(
    api: Api, habbo: FakeHabbo, settings: Settings
) -> None:
    habbo.set(furnidata(furni("chair_plasto*1"), furni("no_icon")), 'W/"v1"')
    apply_update(api)
    habbo.icons["chair_plasto_1_icon.png"] = PNG

    res = api.get("/api/catalog/icons/100/chair_plasto*1")
    assert res.status_code == 200
    assert res.content == PNG
    assert res.headers["content-type"] == "image/png"
    assert "immutable" in res.headers["cache-control"]
    count = len(habbo.requests)
    assert api.get("/api/catalog/icons/100/chair_plasto*1").status_code == 200
    assert len(habbo.requests) == count, "second read comes from the cache"

    assert api.get("/api/catalog/icons/100/no_icon").status_code == 404
    count = len(habbo.requests)
    assert api.get("/api/catalog/icons/100/no_icon").status_code == 404
    assert len(habbo.requests) == count, "a missing icon is remembered"

    count = len(habbo.requests)
    assert api.get("/api/catalog/icons/999/chair_plasto*1").status_code == 404
    assert api.get("/api/catalog/icons/100/not_listed").status_code == 404
    assert len(habbo.requests) == count, "not in the catalogue, so Habbo is not contacted"


def test_icon_that_is_not_png_is_refused(api: Api, habbo: FakeHabbo) -> None:
    apply_update(api)
    habbo.icons["chair_icon.png"] = b"<svg onload=alert(1)>"
    assert api.get("/api/catalog/icons/100/chair").status_code == 502


def test_cache_limit_and_clear(api: Api, habbo: FakeHabbo, settings: Settings) -> None:
    import os

    habbo.set(furnidata(furni("a"), furni("b")), 'W/"v1"')
    apply_update(api)
    habbo.icons |= {"a_icon.png": PNG, "b_icon.png": PNG}
    api.get("/api/catalog/icons/100/a")
    api.get("/api/catalog/icons/100/b")
    old = settings.furni_dir / "100" / "a" / "icon.png"
    os.utime(old, (1, 1))

    info = api.get("/api/cache").json()
    assert info["assets_bytes"] == len(PNG) * 2
    assert info["gamedata_bytes"] > 0

    assets = api.services.assets
    assert assets.enforce_limit(len(PNG)) == 1
    assert not old.exists(), "least recently used goes first"
    assert (settings.furni_dir / "100" / "b" / "icon.png").exists()

    assert api.post("/api/cache/clear").json()["removed"] == 1
    assert api.get("/api/cache").json()["assets_bytes"] == 0
    assert classnames(api) == ["a", "b"], "catalogue is untouched"


def test_automatic_check_only_notifies(api: Api, habbo: FakeHabbo) -> None:
    first = apply_update(api)
    habbo.set(furnidata(furni("sofa")), 'W/"v2"')
    services = api.services

    count = len(habbo.requests)
    maintenance(services, startup=True)
    assert len(habbo.requests) == count, "off by default, so Habbo is not contacted"

    api.patch("/api/settings", json={"gamedata_check": "startup"})
    maintenance(services, startup=False)
    assert len(habbo.requests) == count
    maintenance(services, startup=True)
    assert status(api)["updates_waiting"] == ["sandbox"]
    assert status(api)["current"]["id"] == first, "applying stays manual"


def test_daily_check_runs_once_a_day(api: Api, habbo: FakeHabbo) -> None:
    apply_update(api)
    api.patch("/api/settings", json={"gamedata_check": "daily"})
    count = len(habbo.requests)
    maintenance(api.services)
    assert len(habbo.requests) > count
    count = len(habbo.requests)
    maintenance(api.services)
    assert len(habbo.requests) == count


def test_status_uses_default_hotel(client: TestClient, api: Api) -> None:
    assert api.get("/api/catalog/status").json()["hotel"] == "sandbox"
    api.patch("/api/settings", json={"default_hotel": "de"})
    assert api.get("/api/catalog/status").json()["hotel"] == "de"


def test_no_raw_data_outside_data_dir(api: Api, settings: Settings, tmp_path: Path) -> None:
    apply_update(api)
    assert (settings.data_dir / "cache" / "gamedata").is_dir()
