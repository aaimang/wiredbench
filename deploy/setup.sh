#!/usr/bin/env bash
# Fetches the pinned Turbo, admin panel and Nitro sources, builds Turbo and installs the two web
# apps' packages. Run again after the submodule pins move.
. "$(dirname "$0")/common.sh"

need git "https://git-scm.com"
need dotnet ".NET SDK 10 (https://dotnet.microsoft.com)"
need corepack "Node 24 or newer, which ships corepack"

git -C "$ROOT" submodule update --init vendor/turbo-cloud vendor/nitro-next
git -C "$TURBO" submodule update --init turbo-admin

dotnet build "$TURBO/Turbo.Main/Turbo.Main.csproj"

(cd "$TURBO/turbo-admin" && corepack yarn install)
(cd "$NITRO" && corepack yarn install)
# The install rewrites the pinned lockfile; keep the submodule at its pinned commit.
git -C "$NITRO" checkout -- yarn.lock
git -C "$TURBO/turbo-admin" checkout -- yarn.lock

echo "Done. Start the hotel with deploy/turbo.sh, then deploy/client.sh and deploy/panel.sh."
