#!/usr/bin/env bash
# Runs the vendored Turbo in Development with the Wiredbench plugin loaded from turbo-plugin/
# (hot-reloaded as its files change). Stop any other Turbo first: they share the database and ports.
# Its console takes commands (`help`), so run it in a terminal you can type into.
. "$(dirname "$0")/common.sh"

need_path WB_TURBO_SETTINGS file
need_path WB_ASSETS_DIR dir

if [ ! -f "$TURBO/appsettings.Development.json" ] && [ -n "${WB_TURBO_SETTINGS:-}" ]; then
    cp "$WB_TURBO_SETTINGS" "$TURBO/appsettings.Development.json"
fi

export DOTNET_ENVIRONMENT=Development
export TURBO__Turbo__Plugin__DevPluginPaths__0="$PLUGIN"

if [ -n "${WB_DB_CONNECTION:-}" ]; then
    export TURBO__Turbo__Database__ConnectionString="$WB_DB_CONNECTION"
fi

# The hotel's name (Turbo:Web:HotelName): the public site shows it, and gamedata variables bound to
# it in the panel take it. WB_HOTEL_NAME changes it.
export TURBO__Turbo__Web__HotelName="${WB_HOTEL_NAME:-Wiredbench}"

if [ -n "${WB_OWNER_NAME:-}" ]; then
    export TURBO__Turbo__Owner__Name="$WB_OWNER_NAME"
fi

if [ -n "${WB_ASSETS_DIR:-}" ]; then
    export TURBO__Turbo__Assets__Directory="$WB_ASSETS_DIR"
fi

# Where clients reach the gamedata host. Left empty, Turbo hands out addresses on the origin a
# request came to; deploy/client.sh proxies /gamedata there, so the client loads plugin modules from
# its own origin. Set it only when clients reach gamedata elsewhere (that origin must then be in
# the client's client.modules.hosts).
if [ -n "${WB_GAMEDATA_URL:-}" ]; then
    export TURBO__Turbo__Gamedata__PublicUrl="$WB_GAMEDATA_URL"
fi

cd "$TURBO"
exec dotnet run --no-build --project Turbo.Main/Turbo.Main.csproj
