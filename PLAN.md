# Wiredbench plan

Wiredbench (working name) is a self-hosted browser sandbox for building, running and
debugging Habbo WIRED. It targets Habbo Classic by exporting setups to real rooms through
G-Presets.

- **Status:** Phases 1 and 2 merged. Phase 3 (engine) built. Phase 0 results are in
  [spikes/RESULTS.md](spikes/RESULTS.md).
- **Revision:** 2026-10-31, updated with Phase 3 results.

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

### Engine status after Phase 3

The engine runs on the server with a virtual clock and a seeded random source, and any run can be replayed
from its inputs. The browser polls it once a second over REST rather than using a WebSocket, which keeps
the permission and rate limit rules in one place.

No box is `verified in-game`, because nothing has been compared with a real room. The main assumptions:

- A tick is 500 ms, inferred from delay values in real presets.
- Execute In Order runs from the top of the stack down. Without it, the order is shuffled by the seed, so
  a stack that relies on order by accident shows up in testing.
- A signal carries one user, so sending to several users sends several signals. The article's per-user
  conditions need this.
- Stacks may run 100 times per second by default. The real limit is not public.
- Box settings are this project's own friendly fields under `wired`. Mapping them to G-Presets' raw
  `options` arrays is Phase 5 work, because the meaning of most option numbers is not documented.
- The time tracking example follows the article's text. Its screenshots hold exact settings that could not
  be read.

Not simulated yet, so logged as stubs: game boxes, bots, teams, chests, movement add-ons, Variable FX and
the rest of the catalogue outside Wave 1. Walking still runs in the browser, which reports each step.

### Exchange status

Import keeps each furni's and box's original data, and export changes only what was edited, so an untouched
file comes back identical. All three sample files pass this. Settings are read only where samples support
the meaning: `items`, `delay`, `config` and variable names. Option numbers stay unread, so boxes that are new
in Wiredbench use values seen in real files, or empty options and a warning. The product describes the file
format and links to neither G-Earth nor G-Presets, because of Fansite Policy 1.5.

**Real-room result (2026-10-31):** a Wiredbench export with two `wf_floor_switch1`, `wf_trg_state_changed` and
`wf_act_toggle_state` imported through G-Presets into a real room, and using one switch flipped the other. So the
file shape works, and `furniSources: [100]` with `items` behaved as picks. Only those two box types are shown as
tried in a real room, and other option values remain unproven.

The guide lists every box from the catalogue and the engine. Example rooms are added as editable rooms, rather
than the read-only ones first planned, because duplicating a read-only room added a step and no protection.

### Box options from the real client

Forms follow the options in screenshots of the real client, in Wiredbench's own styling (Fansite Policy 1.6).
Each box needs its own evidence, so this is being done as screenshots arrive. So far: User Says Keyword, Move
User to Furni and Variable placeholder. Options the engine does not act on are marked as saved only. The
meaning of each `options` number is still unknown, so export warns about settings it cannot write. Screenshots
were also seen for Furni Is Used's furni source, the Projectile add-on (cut off) and the box menu, which are not
built.

Screenshots of the client's Wired Creator Tools show more that is not built. Variables have properties: type
(created by user or internal), target, availability, has value, can write to, can create or delete, and can
intercept. Rooms also have read-only internal variables, such as `@id`, `@class_id`, `@height`, `@state`,
`@position.x`, `@rotation` and `@altitude` on furni, `@index`, `@level`, `@is_owner` and `@direction` on users, and
context ones such as `@selector_furni_count`. A variable can have no value, like `is_admin_dev`. The inspection
tab shows a furni's or user's variables with values, including `@height` 65 for a 0.65 height box.

### Reference for box options

`nitrodevco/nitro-next` is read only as a source of facts about option order and meaning, chosen on 2026-10-31.
It has no licence and says it is ported from Habbo's client, so no code is copied, it is not a dependency, and the
product does not link to it. `OPTION_FIELDS` in `services/exchange.py` is this project's own table. Each entry
is unverified until tried in a real room, though variable boxes and the filter also match real preset files.
Not mapped yet: variable effects and conditions, movement directions, and most boxes outside the engine.

### Coverage tracker

`docs/box-coverage.md` lists every box with its evidence, generated from `box_coverage.json`, and the Guide shows
the same. CI fails if a box Wiredbench knows is untracked or the document is stale. A catalogue box the tracker
has never seen shows as new. `scripts/box_coverage.py` adds evidence, and `scripts/proof_preset.py` writes a preset
with unusual values and a checklist for a real room. Habbo's Web API only covers variables, so it cannot check
options. Reference evidence only appears where its files name a classname, so some boxes it does cover show none.
Nothing rechecks the reference automatically yet.

### Mock comparison with a real room (2026-10-31)

36 read and write requests were compared with a `habbo.com` room, and the mock was changed to match. A successful
write has still not been compared, because the room's API did not list the scratch variable. Still assumed: the
mass deletion refusal, a read-only batch that is not empty, `429`, and the effect of API writes on triggers.

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
| 3. Engine (built) | Wave 1, stubs, inspector, debugger | Time tracking tutorial passes |
| 4. Control (built, real-room comparison open) | Mock API, dashboard, view-as, settings | Official wrappers work against the mock |
| 5. Exchange (built, one small setup proven) | Import, export, guide, tutorials | A preset imports into a real room and behaves the same |
| 6. Depth (stack checker built) | Wave 2, stack checker | Every box has an honest badge |
| 7. Launch | Security pass, landing page, Docker docs, `v1.0.0` | All release gates pass |

Real-room traces need a room on the sandbox hotel with the Web API add-on and its keys.

### Control status after Phase 4

- **Mock API:** the room ID is the sandbox ID, and a room must be running. Keys belong to the room, so they
  are managed on the dashboard rather than in Settings. All 19 WIRED operations in the official spec are
  routed. `wired-api-python` 0.1.4 passes `scripts/wrapper_check.py`, apart from its known batch bug.
- **Seen live (2026-10-31):** an unknown target kind gives `invalid_target` before the room is looked at, an
  unknown scope gives an empty 404, a non-numeric entity gives `not-found` before any key check, and a room
  with the add-on but apparently no saved keys gives `key_missing` for every key. The last meaning is inferred.
- **Still assumed:** invalid-value codes, the mass deletion refusal, read-only batch, `429`, and that an API
  write fires Variable Changed.
- **View as:** a flag on the login session, enforced in the guard with an allow list of routes. It tests what
  a visitor can reach, but it is not a separate account. Walking jumps to the tile rather than animating.
- **Dashboard:** counts cover running rooms only and reset with the run. Work is boxes visited.

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
| `WB_LIVE_CHECK_*` | Keys for `scripts/live_check.py`. Read by that script only, never by the app. |

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
- **Legal:** the [Habbo Fansite Policy](https://help.habbo.com/hc/en-us/articles/360011512480-Habbo-Fansite-Policy)
  is read. Every page shows its required disclaimer, and choosing a password warns against reusing a
  Habbo one. Keep to it: no money or donations, no links to cheats, hacks or retros (check this before
  linking G-Earth or G-Presets), and no copying the Habbo client's look. The policy describes websites,
  so whether it covers a self-hosted tool is unconfirmed. Habbo can revoke permission at any time.
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
