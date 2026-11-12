# Phase 7 audit: what the old app does, and where each part goes

Phase 7 removes `frontend/` (about 11,600 lines of TypeScript) and `backend/` (FastAPI, the
Python engine, about 13,500 lines, plus 27 test files). This lists everything they do, with
everything that depends on them, and proposes for each one **covered** (Turbo, nitro-next or
the plugin already does it), **port** (move it into the plugin or the panel), **keep** (keep the
file, moved or frozen) or **drop**.

Audited 2026-11-13 on `feat/turbo-sandbox` at `e991717`; questions A to C were answered as proposed,
and section 6 says how it went.

## 1. The app's features

| Old feature (where) | What it does | Today | Proposal |
|---|---|---|---|
| Sign-in, password, "view as" (`api/auth.py`, login page) | One admin account; a read-only viewer role | The panel's accounts and passkeys; the hotel's own sign-in and permissions | **Drop** (covered) |
| Catalogue page, furnidata update (`api/catalog.py`, `services/furnidata.py`, `update-dialog.ts`) | Fetch Habbo's furnidata, show a diff, apply, roll back | Turbo's release watcher finds new furnidata, texts and assets; the panel imports them | **Drop** (covered). Roll back is not checked in Turbo. |
| Furni, effect and avatar art (`api/assets.py`, `services/swf.py`, `figures.py`, `effects.py`) | Converts SWFs to sprite atlases for the old renderer | Turbo's asset sync, drawn by nitro-next | **Drop** (covered) |
| Workspace page (`api/workspace.py`) | Folders of sandboxes, versions with restore, trash | Rooms are the sandboxes; the Sandbox window saves and resets a room; presets are the library | **Drop**. No folders, version history or trash in the plugin; see question A. |
| Sandbox editor (`room/editor.ts`, `renderer.ts`, `iso.ts`) | Draws the room and edits it | The hotel itself, through nitro-next | **Drop** (covered; this was the reason for the move) |
| Run panel (`api/engine.py`, `api/view.py`, `run-panel.ts`) | Runs the Python engine; advance, input, commands, built-ins | Turbo runs WIRED itself; the Wired trace window shows each stack run | **Drop** (covered). Pause and step is Phase 8. |
| Dashboard page (`/dashboard`) | Load figures of the running sandboxes | The panel's Wiredbench page: WIRED use across loaded rooms | **Drop** (covered) |
| Room checker (`engine/checker.py`, `GET /check`) | Finds stacks that cannot work, without running them: 10 checks (missing furni, no picks, no keyword, no antenna, undefined or clashing variables, no effect, no sender or receiver) | Nothing like it | **Port** to the plugin: a "Check room" button in the Wiredbench window, and the same on the panel page |
| Guide page (`engine/guide.py`) | One plain line per box: what it does, and an idea for using it | The client shows Habbo's own box texts | **Drop**; see question B |
| Tutorials (`engine/tutorials.py`) | 5 lesson rooms: switch, signal relay, score counter, visitor view, time tracking | Presets can hold rooms like these | **Port** as 5 G-Presets files in the library (keep the lessons, lose the Python) |
| WIRED Web API mock (`api/mock.py`) | Habbo's room variables over REST, for testing bots and sites | Turbo's own WIRED Web API (`Turbo.Web`, with Habbo's rate limits) | **Drop** (covered) |
| Settings page (`api/system.py`) | App settings, cache, audit log | The panel's settings and logs | **Drop** (covered) |
| G-Presets import and export (`services/exchange.py`) | Read and write G-Presets files | The plugin (`Presets/`), with its own tests | **Drop** (covered). The Python version's test notes stay quoted in `GPresetFileTests.cs`. |
| `wiredbench check-upstream` (CLI, nightly CI) | Checks Habbo's furnidata can still be read | Turbo's release watcher logs this every 30 minutes | **Drop** (covered) |

## 2. Scripts

| Script | Needs the backend? | Proposal |
|---|---|---|
| `parity.py` (+ `test_parity.py`) | No | **Keep** |
| `plugin_version.py` (+ `test_plugin_version.py`) | No | **Keep** |
| `swf_abc.py` (used by `parity.py`) | No | **Keep** |
| `make_icons.py` | Reads `frontend/public/favicon.svg` | **Keep**, with the logo moved to `turbo-plugin/` |
| `behaviour.py`, `behaviour_recorder.py` (+ `test_behaviour.py`) | Yes: records the Python engine | **Keep the answer, drop the recorder.** `docs/behaviour/scenarios.json` is the frozen Python answer and `tests/turbo-replay/` replays it; `behaviour.py` keeps only the compare-and-report part, so needs a small rewrite |
| `box_coverage.py` (+ `test_coverage.py`) | Writes `backend/.../box_coverage.json` | **Keep** the evidence: move the JSON to `data/` and keep `docs/box-coverage.md` |
| `gen_docs.py` | Yes | **Drop**; its README sections become plain text. `docs/box-fields.md` (G-Presets fields) stays as a frozen document. |
| `box_facts.py`, `client_labels.py`, `internal_variables.py`, `vending_facts.py`, `effect_facts.py` | Write facts the Python engine reads | **Drop** with the engine; Turbo has its own. Their JSON goes too. |
| `avatar_check.py` | Yes (old avatar drawing) | **Drop** |
| `proof_preset.py` | Yes | **Drop**, or port later if the plugin needs a test preset |
| `live_check.py`, `wrapper_check.py` | Yes (the mock API) | **Port** cheaply: point them at Turbo's WIRED Web API instead of the mock |
| `docker_smoke.sh` | The app's Docker image | **Drop** |

## 3. Build, CI and release

| Item | Proposal |
|---|---|
| CI "Backend" job (ruff, mypy, `gen_docs --check`, pytest with coverage) | **Shrink** to ruff and pytest on `scripts/` and their tests |
| CI "Frontend", "Browser tests", "Docker build and smoke test" | **Drop** |
| CI: the plugin's C# tests (`tests/plugin`, 60 tests) | **Add.** No CI job runs them today. It needs the turbo-cloud submodule, so the `SUBMODULES_TOKEN` secret. |
| CI "WIRED box parity", "Plugin version" | **Keep** |
| Nightly (`check-upstream`) | **Drop** |
| Security: npm audit, container scan | **Drop**; keep Semgrep, the secret scan and CodeQL (switch CodeQL's languages to C# and Python) |
| Release (release-please, Python package and Docker image) | **Re-aim** at the plugin's version (`manifest.json`), or drop; see question C |
| `Dockerfile`, `compose.yaml` | **Drop**; `deploy/` runs Turbo and the client |
| `pyproject.toml`, `uv.lock` | **Shrink** to what the kept scripts need |
| Pre-commit hooks | Drop mypy on `backend/`, `gen_docs`, the frontend hooks; point pytest at the kept tests |
| `README.md`, `PLAN.md`, `CHANGELOG.md` | **Rewrite** the README for the plugin; mark `PLAN.md` as history and add the Turbo phases; keep the old changelog as history |

## 4. Questions for you

- **A. Sandbox history.** The old app kept versions of a sandbox with restore, and a trash. The
  plugin keeps one save per room. Drop it (proposed), or port "keep the last N saves"?
- **B. Box guide.** Drop the one-line box explanations (proposed), or keep them as a doc page?
- **C. Releases.** Re-aim release-please at the plugin version (proposed), or drop releases until
  the plugin is published somewhere?

## 5. Proposed order

1. Port what is kept: the room checker and the 5 tutorial presets, and point `live_check.py` and
   `wrapper_check.py` at Turbo's WIRED Web API. Each comes with tests.
2. Move the files that stay (`box_coverage.json`, the logo) and rewrite `behaviour.py` to drop the
   engine.
3. Add the CI job for the plugin's C# tests.
4. One commit removing `frontend/`, `backend/`, the dropped scripts, Docker and their CI, with the
   README and `PLAN.md` updated.

## 6. Outcome (2026-11-13)

Done as proposed, except where this says otherwise.

- **Room check:** `turbo-plugin/server/RoomCheck.cs` and the Check window. It reads Turbo's stored
  box settings, which do not say which of a box's slots it uses, so a box that names a variable has
  its slots left alone (its variable decides them). Two Python checks were not ported: a variable
  defined with two types cannot happen in Turbo, and "no variable chosen" needs to know which
  boxes take one.
- **Tutorials:** exported once with the old app's G-Presets export into
  `turbo-plugin/data/presets/`; all five import whole in the plugin's tests and pass the room
  check.
- **Box coverage:** kept as the frozen `docs/box-coverage.md` rather than moving its JSON and
  script: it measured the Python engine, and parity now tracks Turbo.
- **Logo:** moved to `docs/wiredbench-logo.svg`, not `turbo-plugin/`: it is only the drawing
  `make_icons.py` follows.
- **Also removed:** `spikes/` (Phase 0 experiments for the old app) and the old tests of the
  backend's own SWF reading.
- **Not removed:** `.env.example` (the old app's two settings), which a local safety hook would not
  let this session delete; and the untracked `data/` folder (the old app's local data), left on
  disk for its owner.
- **CI:** the plugin tests and parity run once the repository variable `SUBMODULES` is `true` and
  the secret `SUBMODULES_TOKEN` can read the private submodules.
- **Releases:** a plugin version reaching `main` is released as `v<version>`, continuing the old
  app's numbering (its last was v0.11.0, so the plugin's first is v0.12.0), with its changelog
  section and the plugin as a zip.
