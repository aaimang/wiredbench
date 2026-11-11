#!/usr/bin/env bash
# Type-checks the plugin's client module against the vendored client-module SDK.
. "$(dirname "$0")/common.sh"

cd "$NITRO"
exec corepack yarn tsc -p "$PLUGIN/client/tsconfig.json"
