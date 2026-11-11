#!/usr/bin/env bash
# Runs the vendored Nitro client on http://localhost:3000, with /gamedata passed on to Turbo's
# gamedata host (deploy/client.vite.config.mts) so plugin client modules load from the client's own
# origin. Log in with a ticket from the admin panel (Players -> a player -> Login ticket):
# http://localhost:3000/?sso=<ticket>
. "$(dirname "$0")/common.sh"

cd "$NITRO/packages/nitro-react"
exec corepack yarn vite --config "$ROOT/deploy/client.vite.config.mts" --host --port 3000
