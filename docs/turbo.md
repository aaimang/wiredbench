# Wiredbench on Turbo

Wiredbench is moving from its own room drawing to the Turbo hotel and its Nitro client. It runs as
a Turbo plugin (`turbo-plugin/`) with a client module, so you build and debug WIRED in the
hotel's own client and manage it from Turbo's admin panel.

## What is where

| Folder | What |
|---|---|
| `turbo-plugin/manifest.json` | The plugin's key (`wiredbench`), version and sources |
| `turbo-plugin/server/` | C# the hotel compiles as it loads the plugin: messages, admin pages |
| `turbo-plugin/client/src/` | The client module the hotel builds into `wiredbench.js` |
| `turbo-plugin/wwwroot/`, `gamedata/` | Its icon and its texts |
| `vendor/turbo-cloud` | Turbo, the server and (nested) its admin panel, pinned by commit |
| `vendor/nitro-next` | The Nitro client, pinned by commit |
| `deploy/` | Scripts to set up and run all three |

`vendor/` holds git submodules, not copies: Turbo and Nitro carry no licence, so their code stays
in their own repositories under their own terms, and Wiredbench's MIT licence does not cover it.

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

## Behaviour against the Python engine

`docs/behaviour/README.md` compares the old Python engine with Turbo on every room the engine's own
tests build: 271 rooms, of which 248 or 249 match (a room with random draws may match by chance).
Every one that differs has a cause written beside it:
Turbo is the reference (built-in variables and placeholders), a traced cause (which engine is off,
or open until a Habbo capture settles it), or a note on what the replay cannot carry (random draws,
inputs it does not send).

`docs/behaviour/scenarios.json` is the Python engine's answer for each room, recorded on 2026-11-12.
It is the reference Turbo is checked against once the Python engine is gone: only the last three
commands below need Turbo, and the first needs the Python engine. To write it all again:

```bash
uv run python scripts/behaviour.py record
```

The Turbo replay test is kept in `tests/turbo-replay/`, since turbo-cloud is a submodule this
repository does not commit to; copy it into the submodule before running it:

```bash
cp tests/turbo-replay/WiredbenchBehaviourReplayTests.cs vendor/turbo-cloud/Turbo.Tests/Rooms/
```

```bash
cd vendor/turbo-cloud && WB_BEHAVIOUR_SCENARIOS=$PWD/../../docs/behaviour/scenarios.json WB_BEHAVIOUR_OUT=$PWD/../../docs/behaviour/turbo.json dotnet test Turbo.Tests/Turbo.Tests.csproj --filter FullyQualifiedName~WiredbenchBehaviourReplay
```

```bash
uv run python scripts/behaviour.py report
```

## Check it

```bash
dotnet build turbo-plugin/server/Wiredbench.csproj
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
  `PARITY_SUBMODULES` is `true` (the pinned turbo-cloud commit has to be fetchable first).
