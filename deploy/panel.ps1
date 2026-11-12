# Windows twin of panel.sh: runs the vendored Turbo admin panel on http://localhost:5173.
# Wiredbench's pages are under Plugins once the hotel has loaded the plugin.
#   pwsh -File deploy\panel.ps1
. (Join-Path $PSScriptRoot 'common.ps1')

Set-Location (Join-Path $Turbo 'turbo-admin')
& corepack yarn dev
exit $LASTEXITCODE
