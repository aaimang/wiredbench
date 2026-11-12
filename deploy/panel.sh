#!/usr/bin/env bash
# Runs the vendored Turbo admin panel on http://localhost:5173. Wiredbench's pages are under
# Plugins once the hotel has loaded the plugin.
. "$(dirname "$0")/common.sh"

cd "$TURBO/turbo-admin"
exec corepack yarn dev
