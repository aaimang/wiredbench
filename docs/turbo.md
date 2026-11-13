# Wiredbench on Turbo

Wiredbench runs as a Turbo plugin (`turbo-plugin/`) with a Nitro client module: you build and debug
WIRED in the hotel's own client and manage it from Turbo's admin panel. Its own room drawing,
Python engine and web app were removed in Phase 7 (2026-11-13); `docs/phase7-audit.md` says where
each of their parts went.

## What is where

| Folder | What |
|---|---|
| `turbo-plugin/manifest.json` | The plugin's key (`wiredbench`), version and sources |
| `turbo-plugin/server/` | C# the hotel compiles as it loads the plugin: messages, admin pages |
| `turbo-plugin/client/src/` | The client module the hotel builds into `wiredbench.js` |
| `turbo-plugin/wwwroot/`, `gamedata/` | Its icon and its texts |
| `turbo-plugin/data/` | The parity report, the wired kits and the tutorial rooms (`presets/`) |
| `tests/plugin/` | The plugin's tests, against Turbo's test doubles |
| `tests/turbo-replay/` | The behaviour replay test, copied into Turbo to run |
| `scripts/`, `tests/scripts/` | Parity, the plugin version, icons, the behaviour report, Web API checks |
| `vendor/turbo-cloud` | Turbo, the server and (nested) its admin panel, pinned by commit |
| `vendor/nitro-next` | The Nitro client, pinned by commit |
| `deploy/` | Scripts to set up and run all three |

`vendor/` holds git submodules, not copies: Turbo and Nitro carry no licence, so their code stays
in repositories of their own, and Wiredbench's MIT licence does not cover it. The submodules point
at private copies under `aaimang/` (`turbo-cloud` on `wiredbench-seams`, its `turbo-admin` on
`wiredbench-panel`, `nitro-next` on `wiredbench-ui`), which hold Wiredbench's changes to them;
cloning them needs read access to those repositories.

## Run it

Needs .NET SDK 10, Node 24 (with corepack) and MariaDB with a Turbo database.

```bash
git submodule update --init --recursive
cp deploy/.env.example deploy/.env   # then fill it in
deploy/setup.sh
```

Then, each in its own terminal (only one Turbo may run at a time: they share ports and the database):

```bash
deploy/turbo.sh
```

```bash
deploy/client.sh
```

```bash
deploy/panel.sh
```

In the panel (http://localhost:5173), the plugin's page is **Wiredbench**. Log in to the client with a
ticket from the panel (Players, a player, Login ticket): `http://localhost:3000/?sso=<ticket>`. The
Wiredbench icon on the toolbar opens its window.

The plugin is loaded from `turbo-plugin/` through `Turbo:Plugin:DevPluginPaths`, so the hotel
reloads it when its files change.

The hotel is named **Wiredbench** (`Turbo:Web:HotelName`, set by `deploy/turbo.sh`; `WB_HOTEL_NAME`
changes it), and the client's tab reads **Wiredbench: Local Sandbox for Habbo WIREDs**
(`deploy/client.vite.config.mts`; `WB_CLIENT_TITLE` changes it).

The client reads this hotel's furnidata and product data through the `/gamedata` proxy (the rest
of its gamedata still comes from nitrodev.co): the furnidata carries the hotel's own catalogue
offer ids, which the infostand's **Buy** and Builders Club **Place more** send. Set
`WB_HOTEL_GAMEDATA` before `deploy/client.sh` to change which files (`furnidata,productdata,texts`,
or `none`).

### On Windows

Each script has a PowerShell twin (`deploy\*.ps1`) that does the same, reading the same
`deploy\.env`. Install .NET SDK 10, Node 24 and MariaDB for Windows, then in PowerShell 7:

```powershell
git submodule update --init --recursive
Copy-Item deploy\.env.example deploy\.env   # then fill it in
pwsh -File deploy\setup.ps1
```

Then, each in its own terminal:

```powershell
pwsh -File deploy\turbo.ps1
```

```powershell
pwsh -File deploy\client.ps1
```

```powershell
pwsh -File deploy\panel.ps1
```

`deploy\check-client.ps1` type-checks the client module. Paths in `deploy\.env` are Windows paths
(`C:\turbo\assets`). CI's **Windows** job runs `setup.ps1`, `check-client.ps1` and the plugin's tests
on Windows.

## In the hotel

- **Toolbar**: the Wiredbench window opens the Wired trace, Sandbox, Presets and Check windows.
- **Pause and step**: the Wired trace window's Pause holds each stack's effects while triggers still
  fire and conditions are asked; Step runs the next held effect and Resume runs the rest. A held
  effect runs against the room as it is when stepped, and each step's execution budgets start afresh.
- **Check room** reads every wired box in the room and lists what cannot work as built, without
  running it: errors (picks of furni no longer in the room, a slot or antenna with nothing picked,
  a keyword trigger with no keyword, a variable no box makes) and warnings (a stack nothing starts
  or that does nothing, a selector's or a signal's targets read without one, a signal no one sends
  or receives). A box that names a variable has its slots left alone: which it reads depends on
  the variable.
- **Tutorials**: the preset library gets five example rooms (`turbo-plugin/data/presets`) as the
  plugin loads, any it lacks by name, so a deleted one comes back at the next load.
- **`:copy <name> [COM|BR|TR|DE|ES|FI|FR|IT|NL]`** wears a Habbo's look, read from that hotel's
  public API, and keeps it in your wardrobe (the first empty slot). `:copy help` whispers how.
  The lookup runs after the command answers, with an 8 second limit, so the room never waits on
  it; what goes wrong is whispered. Ranks lose it with a denial of `wiredbench.command.copy`.
- **Panel**: the Wiredbench page shows WIRED use across loaded rooms (boxes, stacks, usage against
  the cap, executions, running time, errors), with a room filter. G-Presets takes a `.json` upload
  or a paste; a preset's page renames it, replaces its file or deletes it.

## Behaviour against the Python engine

`docs/behaviour/README.md` compares the old Python engine with Turbo on every room the engine's own
tests build: 271 rooms, of which 248 or 249 match (a room with random draws may match by chance).
Every one that differs has a cause written beside it:
Turbo is the reference (built-in variables and placeholders), a traced cause (which engine is off,
or open until a Habbo capture settles it), or a note on what the replay cannot carry (random draws,
inputs it does not send).

`docs/behaviour/scenarios.json` is the Python engine's answer for each room, recorded on 2026-11-12.
The engine is gone, so the file is kept as it was: it is what Turbo is checked against. The Turbo
replay test is kept in `tests/turbo-replay/`, not in turbo-cloud; copy it into the submodule before
running it:

```bash
cp tests/turbo-replay/WiredbenchBehaviourReplayTests.cs vendor/turbo-cloud/Turbo.Tests/Rooms/
```

```bash
cd vendor/turbo-cloud && WB_BEHAVIOUR_SCENARIOS=$PWD/../../docs/behaviour/scenarios.json WB_BEHAVIOUR_OUT=$PWD/../../docs/behaviour/turbo.json dotnet test Turbo.Tests/Turbo.Tests.csproj --filter FullyQualifiedName~WiredbenchBehaviourReplay
```

```bash
uv run python scripts/behaviour.py report
```

## Versions

Every change under `turbo-plugin/` raises `manifest.json`'s `Version` and adds its heading to
`turbo-plugin/CHANGELOG.md`:

```bash
uv run python scripts/plugin_version.py --bump patch
```

CI runs `scripts/plugin_version.py --check`; the plugin's tests check the client and server name
the same messages and that the changelog names the version.

## Check it

```bash
dotnet build turbo-plugin/server/Wiredbench.csproj
```

```bash
dotnet test tests/plugin/Wiredbench.Tests
```

```bash
uv run pytest
```

```bash
deploy/check-client.sh
```

## WIRED box parity

`python scripts/parity.py` checks every wired code the Habbo client knows against the pinned Turbo's
boxes, nitro-next's editors and (with `--hotel-db`) the hotel's furni. It writes the report the
admin panel's **Wiredbench → Parity** page shows (`turbo-plugin/data/parity.json`) and a summary
(`docs/parity/README.md`).

- After a new Habbo client build: `uv run python scripts/parity.py --swf path/to/HabboAir.swf --hotel-db`.
  This refreshes the committed client code list (`docs/parity/client-codes.json`); the SWF itself is
  never committed.
- `uv run python scripts/parity.py --check` only reads, and fails when a client code has no Turbo box
  or no nitro-next editor, or two boxes claim one code. CI runs it once the repository variable
  `SUBMODULES` is `true` and the secret `SUBMODULES_TOKEN` can read the private submodules; the plugin
tests run in CI on the same terms.

## WIRED Web API

Turbo answers Habbo's WIRED Web API on its public API (`http://127.0.0.1:8092/api/public/rooms/<id>`).
`scripts/live_check.py` records how a room's API answers, a Habbo hotel's or, with
`WB_LIVE_CHECK_BASE_URL=http://127.0.0.1:8092`, Turbo's, so the two can be compared.
`scripts/wrapper_check.py` runs the official `wired-api-python` wrapper against a Turbo room; each
script's top says what to set up.
