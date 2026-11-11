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

## Check it

```bash
dotnet build turbo-plugin/server/Wiredbench.csproj
```

```bash
deploy/check-client.sh
```
