# Windows twin of check-client.sh: type-checks the plugin's client module against the vendored
# client-module SDK.
#   pwsh -File deploy\check-client.ps1
. (Join-Path $PSScriptRoot 'common.ps1')

Set-Location $Nitro
& corepack yarn tsc -p (Join-Path $Plugin 'client\tsconfig.json')
exit $LASTEXITCODE
