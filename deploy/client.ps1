# Windows twin of client.sh: runs the vendored Nitro client on http://localhost:3000, with /gamedata
# passed on to Turbo's gamedata host (deploy\client.vite.config.mts) so plugin client modules load
# from the client's own origin. Log in with a ticket from the admin panel (Players -> a player ->
# Login ticket): http://localhost:3000/?sso=<ticket>
#   pwsh -File deploy\client.ps1
. (Join-Path $PSScriptRoot 'common.ps1')

Set-Location (Join-Path $Nitro 'packages\nitro-react')
& corepack yarn vite --config (Join-Path $Root 'deploy\client.vite.config.mts') --host --port 3000
exit $LASTEXITCODE
