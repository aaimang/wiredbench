from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, update

from conftest import Api
from wiredbench.app import maintenance
from wiredbench.models import AuditEvent, Folder, Sandbox, utcnow


def folder(api: Api, name: str, parent_id: int | None = None) -> int:
    res = api.post("/api/folders", json={"name": name, "parent_id": parent_id})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def sandbox(api: Api, name: str, folder_id: int | None = None) -> int:
    res = api.post("/api/sandboxes", json={"name": name, "folder_id": folder_id})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def tree(api: Api) -> dict:
    return api.get("/api/workspace/tree").json()


def test_nested_folders_and_sandboxes(api: Api) -> None:
    root = folder(api, "Games")
    child = folder(api, "Maze", root)
    box = sandbox(api, "Prototype", child)
    data = tree(api)
    assert {f["name"]: f["parent_id"] for f in data["folders"]} == {"Games": None, "Maze": root}
    assert data["sandboxes"][0]["id"] == box
    assert data["sandboxes"][0]["folder_id"] == child
    assert data["sandboxes"][0]["hotel"] == "sandbox"


def test_names_are_cleaned_and_must_be_unique_per_folder(api: Api) -> None:
    assert api.post("/api/folders", json={"name": "   "}).status_code == 422
    assert api.post("/api/folders", json={"name": "a\nb"}).status_code == 422
    assert api.post("/api/folders", json={"name": "x" * 121}).status_code == 422
    first = folder(api, "  Games ")
    assert tree(api)["folders"][0]["name"] == "Games"
    res = api.post("/api/folders", json={"name": "games"})
    assert res.status_code == 409
    assert res.json()["error"] == "name_taken"
    folder(api, "Games", first)  # A different parent is fine.
    sandbox(api, "Games")  # So is a different kind.


def test_rename_and_move(api: Api) -> None:
    a, b = folder(api, "A"), folder(api, "B")
    assert api.patch(f"/api/folders/{a}", json={"name": "Renamed"}).json()["name"] == "Renamed"
    assert api.patch(f"/api/folders/{b}", json={"parent_id": a}).json()["parent_id"] == a
    assert api.patch(f"/api/folders/{b}", json={"name": "B2"}).json()["parent_id"] == a, (
        "not moved by a rename"
    )
    assert api.patch(f"/api/folders/{b}", json={"parent_id": None}).json()["parent_id"] is None
    box = sandbox(api, "S")
    moved = api.patch(f"/api/sandboxes/{box}", json={"folder_id": a, "description": "Notes"}).json()
    assert moved["folder_id"] == a
    assert moved["description"] == "Notes"
    assert api.patch(f"/api/sandboxes/{box}", json={"folder_id": 999}).status_code == 404


def test_folder_cannot_move_inside_itself(api: Api) -> None:
    a = folder(api, "A")
    b = folder(api, "B", a)
    c = folder(api, "C", b)
    for target in (a, b, c):
        res = api.patch(f"/api/folders/{a}", json={"parent_id": target})
        assert res.status_code == 400
        assert res.json()["error"] == "folder_cycle"


def test_nesting_has_a_limit(api: Api) -> None:
    parent = None
    for level in range(12):
        parent = folder(api, f"L{level}", parent)
    res = api.post("/api/folders", json={"name": "deep", "parent_id": parent})
    assert res.status_code == 400
    assert res.json()["error"] == "too_deep"
    top = folder(api, "top")
    folder(api, "below", top)
    assert api.patch(f"/api/folders/{top}", json={"parent_id": parent}).status_code == 400


def test_document_revisions_and_conflict(api: Api) -> None:
    box = sandbox(api, "S")
    saved = api.put(f"/api/sandboxes/{box}/document", json={"document": {"a": 1}, "base_revision": 1})
    assert saved.json()["revision"] == 2
    stale = api.put(f"/api/sandboxes/{box}/document", json={"document": {"a": 2}, "base_revision": 1})
    assert stale.status_code == 409
    assert stale.json()["error"] == "revision_conflict"
    assert api.get(f"/api/sandboxes/{box}").json()["document"] == {"a": 1}
    versions = api.get(f"/api/sandboxes/{box}/versions").json()
    assert [v["revision"] for v in versions] == [2, 1]
    restored = api.post(f"/api/sandboxes/{box}/versions/1/restore").json()
    assert restored["revision"] == 3
    assert restored["document"] == {}
    assert api.post(f"/api/sandboxes/{box}/versions/99/restore").status_code == 404


def test_history_is_capped(api: Api) -> None:
    box = sandbox(api, "S")
    for revision in range(1, 55):
        res = api.put(
            f"/api/sandboxes/{box}/document", json={"document": {"r": revision}, "base_revision": revision}
        )
        assert res.status_code == 200
    versions = api.get(f"/api/sandboxes/{box}/versions").json()
    assert len(versions) == 50
    assert versions[0]["revision"] == 55


def test_oversized_document_is_refused(api: Api) -> None:
    box = sandbox(api, "S")
    res = api.put(
        f"/api/sandboxes/{box}/document", json={"document": {"a": "x" * 1_600_000}, "base_revision": 1}
    )
    assert res.status_code == 413


def test_duplicate(api: Api) -> None:
    box = sandbox(api, "S")
    api.put(f"/api/sandboxes/{box}/document", json={"document": {"a": 1}, "base_revision": 1})
    copy = api.post(f"/api/sandboxes/{box}/duplicate").json()
    assert copy["name"] == "S (copy)"
    assert copy["document"] == {"a": 1}
    assert copy["revision"] == 1
    assert api.post(f"/api/sandboxes/{box}/duplicate").json()["name"] == "S (copy 2)"


def test_trash_folder_takes_contents_and_restore_brings_them_back(api: Api) -> None:
    root = folder(api, "Root")
    child = folder(api, "Child", root)
    box = sandbox(api, "Box", child)
    assert api.delete(f"/api/folders/{root}").status_code == 204
    assert tree(api) == {"folders": [], "sandboxes": []}
    assert api.get(f"/api/sandboxes/{box}").status_code == 404
    trash = api.get("/api/trash").json()
    assert [(t["kind"], t["id"]) for t in trash] == [("folder", root)], "only the top item is listed"
    assert trash[0]["purge_at"] > trash[0]["deleted_at"]
    assert api.post(f"/api/trash/folder/{root}/restore").status_code == 204
    assert api.get(f"/api/sandboxes/{box}").status_code == 200
    assert len(tree(api)["folders"]) == 2
    assert api.get("/api/trash").json() == []


def test_item_trashed_earlier_stays_trashed_when_its_folder_is_restored(api: Api) -> None:
    root = folder(api, "Root")
    box = sandbox(api, "Box", root)
    api.delete(f"/api/sandboxes/{box}")
    api.delete(f"/api/folders/{root}")
    api.post(f"/api/trash/folder/{root}/restore")
    assert tree(api)["sandboxes"] == []
    assert [t["id"] for t in api.get("/api/trash").json()] == [box]


def test_restore_when_parent_is_gone_or_name_is_taken(api: Api) -> None:
    root = folder(api, "Root")
    box = sandbox(api, "Box", root)
    api.delete(f"/api/sandboxes/{box}")
    api.delete(f"/api/folders/{root}")
    api.post(f"/api/trash/sandbox/{box}/restore")
    assert api.get(f"/api/sandboxes/{box}").json()["folder_id"] is None
    keep = sandbox(api, "Twin")
    api.delete(f"/api/sandboxes/{keep}")
    sandbox(api, "Twin")
    api.post(f"/api/trash/sandbox/{keep}/restore")
    assert api.get(f"/api/sandboxes/{keep}").json()["name"] == "Twin (restored)"


def test_purge_is_permanent(api: Api) -> None:
    root = folder(api, "Root")
    box = sandbox(api, "Box", root)
    api.put(f"/api/sandboxes/{box}/document", json={"document": {"a": 1}, "base_revision": 1})
    assert api.delete(f"/api/trash/folder/{root}").status_code == 404, "must be in the trash first"
    api.delete(f"/api/folders/{root}")
    assert api.delete(f"/api/trash/folder/{root}").status_code == 204
    assert api.get("/api/trash").json() == []
    with api.services.sessions() as db:
        assert db.scalars(select(Sandbox)).all() == []
        assert db.scalars(select(Folder)).all() == []


def test_trash_empties_after_30_days(api: Api) -> None:
    old, recent = sandbox(api, "Old"), sandbox(api, "Recent")
    api.delete(f"/api/sandboxes/{old}")
    api.delete(f"/api/sandboxes/{recent}")
    with api.services.sessions.begin() as db:
        db.execute(update(Sandbox).where(Sandbox.id == old).values(deleted_at=utcnow() - timedelta(days=31)))
    maintenance(api.services)
    assert [t["id"] for t in api.get("/api/trash").json()] == [recent]


def test_tutorials_are_read_only_but_can_be_duplicated(api: Api) -> None:
    box = sandbox(api, "Tutorial")
    with api.services.sessions.begin() as db:
        db.execute(update(Sandbox).where(Sandbox.id == box).values(kind="tutorial"))
    for res in (
        api.patch(f"/api/sandboxes/{box}", json={"name": "x"}),
        api.put(f"/api/sandboxes/{box}/document", json={"document": {}, "base_revision": 1}),
        api.delete(f"/api/sandboxes/{box}"),
    ):
        assert res.status_code == 403
        assert res.json()["error"] == "tutorial_read_only"
    copy = api.post(f"/api/sandboxes/{box}/duplicate").json()
    assert copy["kind"] == "sandbox"
    assert api.patch(f"/api/sandboxes/{copy['id']}", json={"name": "Mine"}).status_code == 200


def test_writes_are_audited(api: Api) -> None:
    folder(api, "Games")
    rows = api.get("/api/audit").json()
    assert rows[0]["action"] == "folder_create"
    assert rows[0]["target"] == "Games"
    assert rows[0]["actor"] == "admin"
    assert any(r["action"] == "login" for r in rows)


def test_old_audit_events_are_removed(api: Api) -> None:
    with api.services.sessions.begin() as db:
        db.execute(update(AuditEvent).values(at=utcnow() - timedelta(days=91)))
    maintenance(api.services)
    assert api.get("/api/audit").json() == []


def test_settings_round_trip_and_validation(api: Api) -> None:
    settings = api.get("/api/settings").json()
    assert settings["default_hotel"] == "sandbox"
    assert settings["gamedata_check"] == "off"
    assert "sandbox" in settings["hotels"]
    updated = api.patch("/api/settings", json={"theme": "dark", "cache_max_mb": 64}).json()
    assert updated["theme"] == "dark"
    assert updated["cache_max_mb"] == 64
    assert api.get("/api/settings").json()["theme"] == "dark"
    assert api.patch("/api/settings", json={"cache_max_mb": 1}).status_code == 422
    assert api.patch("/api/settings", json={"default_hotel": "evil"}).status_code == 422


def test_default_timezone_setting(api: Api) -> None:
    settings = api.get("/api/settings").json()
    assert settings["default_timezone"] == "Europe/London"
    assert settings["time_zones"][:2] == ["Australia/Perth", "Europe/London"]
    assert all(ZoneInfo(zone) for zone in settings["time_zones"])
    saved = api.patch("/api/settings", json={"default_timezone": "Australia/Perth"})
    assert saved.json()["default_timezone"] == "Australia/Perth"
    assert api.patch("/api/settings", json={"default_timezone": "Mars/Olympus"}).status_code == 422
    slug = api.get("/api/tutorials").json()[0]["slug"]
    tutorial = api.post(f"/api/tutorials/{slug}", json={})
    assert tutorial.status_code == 201, tutorial.text
    assert tutorial.json()["document"]["room"]["timezone"] == "Australia/Perth"
