# Wiredbench plan

Wiredbench (working name) is a self-hosted browser sandbox for building, running and
debugging Habbo WIRED. It targets Habbo Classic by exporting setups to real rooms through
G-Presets.

- **Status:** Phase 1 released as `v0.2.0`. Phase 2 (room) built. Phase 0 results are in
  [spikes/RESULTS.md](spikes/RESULTS.md).
- **Revision:** 2026-10-31, updated with Phase 2 results.

## 1. Decisions

| Topic | Decision |
|---|---|
| Classic target | Browser sandbox styled like Classic. Setups export as G-Presets files. No Sulake client is patched or shipped. |
| API | Local mock of the official `/api/public`, plus CI comparison against `sandbox.habbo.com`. |
| Distribution | Public repo, self-hosted with Docker, one admin login per install, public landing page. |
| Habbo assets | Downloaded to each user's machine and cached there. Never redistributed. |
| v1.0.0 scope | Every WIRED classname catalogued and placeable. Core WIRED execute; others show their status. |
| Staff and in-development WIRED | In scope for testing, using public information only. Unknown behaviour stays a logging stub. |
| Language | English only, with all strings in one source. |
| GitHub account | `aaimang`, like the other Habbo projects. |

## 2. Research findings

| Finding | Effect on the plan |
|---|---|
| Furnidata has 284 `wf_*` classnames, the same on production and sandbox | It is the master catalogue. |
| Furni `id`, `offerid` and `bcofferid` differ per hotel; 3 names and 7 descriptions differ | Always key by classname. Keep names per hotel. |
| 29 `wf_*` boxes have no catalogue offer and `bc` false | Label them "not in catalogue". This is a candidate signal, not proof of staff-only. |
| `furnidata_json/1` always answers `307` to `furnidata_json/{hash}`, and only that URL returns an `ETag` and `304` (tested on 5 hotels, 2026-10-31) | Each redirect hop is followed by hand and checked against the host list. Tests mirror this. |
| Furnidata sends `max-age=604800` | A plain HTTP cache could hide updates for 7 days, so the button always revalidates. |
| Sulek's public API covers releases and packets, not furni | Classnames come from furnidata; Sulek is the packet name reference. |
| Habbo Classic is an Electron and JavaScript client using PixiJS, according to community reverse-engineering | Its look can be matched in a browser, but emulating it would be fragile. |
| `sirjonasxx/G-Presets` was updated 2026-10-26, supports variables and has no licence (the WiredSpast copy is older) | Target the sirjonasxx format without copying code. |
| Real presets keep room-specific variable IDs plus a `variables_map` of names | Import remaps variables by name. |
| Furni SWFs parse with no Flash tools: 786 of 786 tested | Convert on first use, in Python. |
| `habbo-imaging` gives 4 walk frames, 8 directions and common poses on 10 hotels, but `effect` has no effect | Enough for v1 avatars, without avatar effects. |
| `swagger-ui-init.js` is reachable by script, with identical specs on both hotels | CI can check the official API for drift. |
| `wired-api-python` 0.1.4 crashes on the live batch format | Keep the mock faithful. Don't rely on that wrapper for batch. |
| `nitro-renderer` is GPL-3.0; `scuti-renderer` shows no licence | Write a small PixiJS renderer of our own. |
| `habbo-imaging` works on `.com` and sandbox | Use it first for avatars. Other hotels still need checking. |
| `hof_furni/{revision}/{classname}.swf` and `_icon.png` both respond | These are the furni asset sources. |

## 3. Architecture

```
Browser: TypeScript + Vite + Web Components + PixiJS 8 + Lucide
   | REST + WebSocket
Python: FastAPI
   |- WIRED engine (server-side, deterministic)
   |- Workspace API
   |- Mock /api/public
   |- Gamedata sync and asset cache
   |- Metrics and audit log
SQLite (WAL) + /data volume
```

The engine runs on the server so that "view as" is real security, because config is never
sent to that session, and so the dashboard and mock API read the same state as the room.

Tooling: `uv`, SQLAlchemy 2, Alembic, Pydantic 2, strict TypeScript, Vitest, pytest,
Playwright.

## 4. Furnidata updates and caching

### Update button

An **Update furnidata** button on the Catalogue page. It turns into **Review update** when an
automatic check finds a new version.

1. Send a conditional GET with the stored `ETag` for the selected hotel.
2. On `304`, show "Up to date, checked just now".
3. On `200`, validate the file, store it as a new version and calculate the differences.
4. Show the differences: new, changed and removed items, with WIRED listed first.
5. The admin applies the update, or dismisses it and stays on the current version.

A **Force refresh** option, under Versions, repeats the download without the `ETag`. Automatic checks are a
setting (off, on startup, daily). They only check and notify; applying stays manual.

### Cache layers

| Layer | Stored in | Refresh rule |
|---|---|---|
| Raw gamedata | `/data/cache/gamedata/{hotel}/{sha256}.json.gz` plus `ETag` and fetch time | Update button or automatic check |
| Normalised catalogue | SQLite `catalog_version`, `catalog_item`, indexed search by substring | Built once per raw version |
| Furni assets | `/data/cache/furni/{revision}/{classname}/` with SWF, sprite atlas and icon | Downloaded on first use; kept per revision because the path is versioned |
| Avatars | `/data/cache/avatars/{hotel}/{hash}.png` | Time limit set in Settings |
| Browser | `ETag` on catalogue API; hashed asset URLs marked immutable | Follows the server version |

Settings show the cache size, a size limit with least-recently-used cleanup, and **Clear
cache**. Clearing assets never removes sandboxes. Only WIRED and furni actually used are
downloaded, not the whole hotel.

### Safety rules

- Only a fixed list of Habbo hosts can be fetched, with no user-supplied URLs.
- Only admins can sync. Requests need a CSRF token and have a per-hotel cooldown and one
  running sync at a time.
- Downloads have a size limit and must pass schema validation. A failed sync changes nothing.
- The new version is swapped in atomically. The last 5 versions are kept for rollback.
- If Habbo is unreachable, the last good cache keeps working and the page says how old it is.
- Entries with an empty classname are skipped.

### Handling changes

- Our guides, config forms and simulation status live in the repo and join to furnidata by
  classname, so an update never overwrites them.
- A new WIRED appears straight away as `new`, placeable with raw config and a logging stub.
- A removed classname stays in existing sandboxes, marked "missing from catalogue", and is
  never deleted automatically.
- Each sandbox records the catalogue version it was last saved with.
- The same mechanism covers `figuredata` and external texts.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/catalog/status` | Current version, last check, whether an update is waiting |
| POST | `/api/catalog/sync` | Check a hotel for an update |
| GET | `/api/catalog/diff/{from}/{to}` | Differences between versions |
| POST | `/api/catalog/apply` | Make a downloaded version current |
| POST | `/api/catalog/dismiss` | Keep the current version |
| POST | `/api/catalog/rollback` | Return to an earlier version |
| GET | `/api/catalog/items` | Search and filter |
| GET | `/api/catalog/icons/{revision}/{classname}` | Cached furni icon |

## 5. Features

### Room and avatars

- Isometric builder using furnidata items, with placing, stacking, rotating and auto Z.
- Avatars chosen by hotel and Habbo name.
- Walking, sitting, waving and chat using cached `habbo-imaging` frames. Avatar effects are not
  available this way, and direction 7 needs more testing.

### Editor layout (from the sample video)

These are interaction ideas from the WiredSnippets editor. No art or code is reused.

- **Left panel:** Objects, Resources and Catalog tabs; search; groups for Avatars, Utilities,
  Triggers, Effects, Conditions, Selectors, Add-ons and Variables; a tooltip per box; Library,
  Import and Export at the bottom.
- **Top toolbar:** undo, redo, room options, editor options, clear room, Run/Stop, console.
- **Right inspector:** preview, name, description, classname, chips (`1x1`, height, `wired`,
  `walk`), Track ID, editable X, Y and Z, state buttons, saved or unsaved status with age.
- **Selection bar:** four isometric arrows (disabled when blocked), rotate, delete.
- **Config dialog:** floating, in-game style, with `Select Furni [n/20]` by clicking in the
  room, a delay slider and advanced settings.
- **Room feedback:** picked furni tinted, and a ghost with footprint outline for move targets.

Improvements on the sample: labelled status badges rather than dim icons alone, a live trace
and variables during Run, and our own warm visual style.

Built in Phase 2: the left panel (avatars and furni search), toolbar, inspector, selection bar and
placement ghost. Build and Play modes replace Run and Stop until the engine exists. The rest of this
list arrives with the features it belongs to: Library, Import and Export in Phase 5, and the config
dialog and console in Phase 3.

Known limits from testing with real art, which later phases should revisit:

- Walking runs in the browser for now. It moves to the server with the engine in Phase 3, where the
  path rules can be checked against real-room traces.
- Sit and lay heights, the footprint rotation rule and draw order for large furni were matched by eye
  or from memory of how the game behaves, not measured in a real room.
- A bed lets you lie on any of its tiles, while the game uses its head tile.
- Furni show the first frame of each state, without animation playback.
- Wall furni and room walls are not drawn. Large rooms need panning, because there is no zoom yet.

### Inspector and commands

Commands use a fixed grammar and never run as code.

| Command | Purpose |
|---|---|
| `:vars user <name>` | User variables |
| `:vars furni <id>` | Furni variables |
| `:vars global` | Global variables |
| `:set <scope> <target> <name> <value>` | Change a value |
| `:trace on\|off` | Execution trace |
| `:pause`, `:step` | Debugger controls |
| `:as <user>` | Act as another user |

### Other pages

- **Guide:** classname, official name, purpose, example and status for each WIRED.
- **Workspace:** nested folders of sandboxes and read-only tutorials you can duplicate, with
  create, rename, move, delete, version history and a 30-day trash.
- **Dashboard:** runs per box, slowest stacks, signal activity, errors and execution-limit hits.
  Labelled as simulated cost, not hotel performance.
- **Settings:** hotel, tick rate, gamedata checks, cache limit, API keys, rate limits, log
  retention, session timeout, theme.
- **View as normal user:** walk and trigger things, but never open WIRED config. Hides staff and
  in-development boxes. A banner shows the mode and the server enforces it.

### Import and export

- A lossless native JSON format, plus G-Presets import and export.
- Boxes store G-Presets' raw fields (`options`, `config`, `items`, `secondItems`, `furniSources`,
  `userSources`, `variableIds`, `variableId`, `delay`, `quantifier`, `filter`, `inverse`), and
  unknown fields survive a round trip, so friendly forms cannot corrupt them.
- Files may also carry `variables_map`, furni `variables`, `floorplan`, `recolorables` and
  `adsBackgrounds`. Partial files with no `furni` are accepted.
- Presets reference furni by classname, never by hotel-specific ID. Variables are remapped by name.
- Export gives a furni shopping list and warns about boxes that may not be obtainable.
- Exports never contain API keys.
- Golden test files come from the `g-presets_presets` folder, which already round-trips losslessly.

### Debugging additions

- Fidelity badge per WIRED: `verified in-game`, `documented` or `assumed`.
- Pause, step and replay using a seeded random source and a virtual clock.
- Stack checker for problems like a signal with no receiver or a likely loop.

## 6. WIRED coverage

| Wave | Includes | Status in v1.0.0 |
|---|---|---|
| 1. Core | Walk, chat, click, signal and variable triggers; move, teleport, message and variable effects; conditions; selectors; `wf_xtra_random`, `wf_xtra_exec_in_order`, filters; text connector; username and variable placeholders; Time Utilities; Level Up; Web API add-on; user, furni, global and context variables; antennas, arrow plates, tiles, buttons, chairs | Runs |
| 2. Games and visuals | Game start and end, score, teams, clocks, Variable FX, highlight, visibility, physics, curves, carry users | Runs where it passes in-game checks, otherwise badged |
| 3. Advanced | Contracts and chests, room links, leaderboards | Placeable with logging stub |
| Not in catalogue | The 29 candidates below | Placeable with raw config and logging stub, real behaviour once documented |

Every box has a `release_stage`: `live`, `sandbox_only`, `not_in_catalogue`, `staff`,
`in_development` or `removed`. Use `staff` only with evidence. Phase 1 assigns only `live` and
`not_in_catalogue`, which marks the 29 candidates below on real data. `sandbox_only` is not assigned yet,
because the WIRED list is the same on both hotels today.

Candidates (`offerid` <= 0 and `bc` false), grouped by my reading of the names:

- **Test and custom:** `wf_test_act`, `wf_test_cnd`, `wf_test_slc`, `wf_test_trg`, `wf_test_var`,
  `wf_test_xtra`, `wf_test_26secret1`, `wf_test_26secret2`
- **Newest, unfinished names:** `wf_act_progress_ach`, `wf_var_dailytask`,
  `wf_xtra_achievement_enabler`
- **Quests:** `wf_var_quest`, `wf_var_quest_chain`
- **Rewards and events:** `wf_act_give_reward`, `wf_act_mute_triggerer`, `wf_trg_at_time_long`,
  `wf_cnd_wearing_badge`, `wf_cnd_not_wearing_b`, `wf_cnd_wearing_effect`,
  `wf_cnd_not_wearing_fx`
- **Ancient and prototype:** `wf_ltdproto_act_toggle_state`, `wf_proto_cnd_trggrer_on_frn`,
  `wf_proto_pyramid`, `wf_proto_trg_at_given_time`
- **Other:** `wf_blob_invis`, `wf_blob2_vis`, `wf_colorwheel`, `wf_screenseparator`,
  `wf_storage_furni_starter`

Also catalogue `conf_wired_disable` (Wired Disabler), which a `wf_` filter would miss.

The **glittering effect** is not identified yet and needs an example or in-game reference.

**First tutorial and acceptance test:** the time tracking system from baikal's article, using
`seconds`, `on_duty`, `last_duty` and `tmp`, with signals, an antenna and Execute in Order. It
also covers the 10-second worst-case loss when a user leaves without standing up.

## 7. Build phases

| Phase | Work | Done when |
|---|---|---|
| 0. Spikes (done, real-room checks open) | Convert SWF to sprites; check avatar frames; round-trip real G-Presets files; test a mock against the official spec | Results in `spikes/RESULTS.md` |
| 1. Foundation (built) | Repo, CI, admin login, folders, furnidata sync, update button, cache | All WIRED browsable behind login; update shows a correct diff |
| 2. Room (built) | Renderer, asset cache, placement, avatars, pathfinding, editor layout | An avatar walks and sits in a saved room |
| 3. Engine | Wave 1, stubs, inspector, debugger | Time tracking tutorial passes |
| 4. Control | Mock API, dashboard, view-as, settings | Official wrappers work against the mock |
| 5. Exchange | Import, export, guide, tutorials | A preset imports into a real room and behaves the same |
| 6. Depth | Wave 2, stack checker | Every box has an honest badge |
| 7. Launch | Security pass, landing page, Docker docs, `v1.0.0` | All release gates pass |

Real-room traces need a room on the sandbox hotel with the Web API add-on and its keys.

## 8. CI/CD

1. **Worktree:** after the initial commit, every feature or fix gets its own worktree and branch.
2. **Pre-commit:** fast format, lint, type and secret checks.
3. **Pull request (the real gate, since local hooks can be skipped):**
   - Unit and engine tests on macOS, Windows and Ubuntu.
   - Playwright browser tests.
   - Security scans, catalogue check and a stale-docs check.
   - Docker build and smoke test on Ubuntu.
4. **Merge:** squash into a protected `main` using Conventional Commits.
5. **Release:** `release-please` proposes the SemVer bump and notes. Merging its PR creates the
   tag, a GitHub release titled with the bare tag (like `v1.2.0`), and a container image with
   its SBOM.
6. **Nightly:** furnidata can still be fetched and parsed. The sandbox API comparison joins in Phase 4
   and the ZAP scan in Phase 7.

The README is not regenerated on every build, because that adds a commit each time and can
retrigger CI. Generated sections (environment variables, API table) must be current for a PR to
pass, and coverage and build details go in the Actions summary.

Actions are pinned to commit hashes and base images to digests, because tags can be moved.

Commits carry no Claude co-author footer.

### Docker

`docker compose up`, listening on `127.0.0.1` by default, with data in a `/data` volume. Runs as
non-root with a read-only filesystem and dropped capabilities.

| Variable | Purpose |
|---|---|
The README lists every current variable, generated from the code. Still to come:

| Variable | Purpose |
|---|---|
| `WB_TICK_MS` | Engine tick length (Phase 3) |
| `WB_LIVE_CHECK_*` | Optional keys for the sandbox API comparison (Phase 4) |

There is no signing key: sessions are random tokens stored hashed in the database, so nothing is signed.

## 9. Security

- **Login:** Argon2id passwords, `HttpOnly` and `SameSite=Strict` cookies, CSRF tokens and login
  throttling. Optional TOTP is planned for Phase 7.
- **Permissions:** every route is denied by default. CI lists all routes and checks that
  outsiders get `401` and writes without a CSRF token get `403`. View-as sessions join these checks in
  Phase 4.
- **Mock API keys:** separate read and write keys per sandbox, stored hashed. Real Habbo keys
  stay in environment variables or CI secrets.
- **SQL injection:** parameterised queries only, enforced with Ruff and Semgrep.
- **XSS and imports:** strict CSP, untrusted text rendered as plain text, schema-checked imports
  with size limits, and classnames checked against the catalogue.
- **Outbound requests:** only a fixed list of Habbo hosts.
- **Rate limits:** login, writes, sync, imports, the mock API and WebSocket messages each have
  their own limit. No published Habbo limits were found, so the mock's are configurable.
- **Prompt injection:** does not apply while the project has no AI features. If one is added,
  imported text is treated as untrusted.
- **Scanning:** CodeQL, Semgrep, pip-audit, npm audit, gitleaks, Trivy and ZAP.

## 10. UI and sharing

- **Look:** an electrician's bench. Putty surfaces and dark ink, with an olive-charcoal dark mode and
  no blue. Each WIRED type has one wire colour used everywhere, and each catalogue group is drawn as an
  unbroken wire with a tick to every row. Dense, tool-like panels, Hanken Grotesk and Lucide icons. This
  replaces the earlier bone and terracotta idea, which reads as a common AI default.
- **Sharing:** the favicon and page description exist. The share banner and landing page are Phase 7.
- **Favicon:** original isometric tile with a small spark connector, using no Sulake assets.
- **Share banner:** a 1200×630 Open Graph image with a short summary, from original art.
- **SEO:** canonical URL, JSON-LD and a sitemap on the landing page. The app itself is `noindex`.
- **Title:** Wiredbench: Habbo WIRED Sandbox and Debugger
- **Description:** Build, run and debug Habbo WIRED stacks in a local sandbox. Inspect variables,
  test signals and export setups for G-Presets.

## 11. Risks

- **Fidelity:** the engine is only as accurate as what can be tested, so traces and badges matter.
- **Staff boxes:** furnidata gives identity, not behaviour, so many stay stubs.
- **Classic:** whether G-Earth and G-Presets work on the Classic client is untested. The fallback
  is importing through the AIR client, because rooms are stored on the server. Sulek lists the
  newest Classic builds under Sandbox, so production availability needs checking.
- **Legal:** Sulake's fansite policy was not found, though WiredClub cites one. Read it before
  launch. The app and site carry a non-affiliation notice.
- **Avatar animation:** `habbo-imaging` covers v1, but not avatar effects, and direction 7 looked
  wrong in testing.
- **Preset import:** `config` strings or `options` may embed IDs, and writing a file that imports into
  a real room is unproven.
- **Automated downloads:** the Habbo Swagger page blocks scripts with HTTP 463 while gamedata
  currently allows them. This could change, so sync failures are clear and non-destructive, and the
  nightly check reports it.

## 12. Sources

- [Time tracking article](https://baikal-de.medium.com/habbo-wired-time-tracking-system-c32286da1195)
- [habbo-wired-api skill](https://github.com/aaimang/habbo-gearth-dev-skills/tree/main/skills/habbo-wired-api)
- [WiredSnippets](https://wiredsnippets.com)
- [WiredClub](https://www.wiredclub.com.br)
- [Wired Wiki list](https://wired.fandom.com/wiki/List_of_Wired)
- [Production furnidata](https://www.habbo.com/gamedata/furnidata_json/1)
- [Sandbox furnidata](https://sandbox.habbo.com/gamedata/furnidata_json/1)
- [Sulek API](https://sulek.dev/api)
- [HabboAssets SWF packs](https://www.habboassets.com/swfs/packs?page=2)
- [G-Presets, sirjonasxx](https://github.com/sirjonasxx/G-Presets)
- [G-Presets, WiredSpast copy](https://github.com/WiredSpast/G-Presets)
- [HabboHTML5](https://github.com/Lorenzune/HabboHTML5)
- [habbo-decompiled](https://github.com/SimoLeoLife/habbo-decompiled)
- [nitro-renderer on npm](https://www.npmjs.com/package/%40nitrots%2Fnitro-renderer)
- [scuti-renderer on npm](https://www.npmjs.com/package/scuti-renderer)
