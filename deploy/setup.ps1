# Windows twin of setup.sh: fetches the pinned Turbo, admin panel and Nitro sources, builds Turbo
# and installs the two web apps' packages. Run again after the submodule pins move.
#   pwsh -File deploy\setup.ps1
. (Join-Path $PSScriptRoot 'common.ps1')

Assert-Command git 'https://git-scm.com'
Assert-Command dotnet '.NET SDK 10 (https://dotnet.microsoft.com)'
Assert-Command corepack 'Node 24 or newer, which ships corepack'

Invoke-Checked git -C $Root submodule update --init vendor/turbo-cloud vendor/nitro-next
Invoke-Checked git -C $Turbo submodule update --init turbo-admin

Invoke-Checked dotnet build (Join-Path $Turbo 'Turbo.Main\Turbo.Main.csproj')

$Panel = Join-Path $Turbo 'turbo-admin'
foreach ($app in @($Panel, $Nitro)) {
    Push-Location $app
    try { Invoke-Checked corepack yarn install } finally { Pop-Location }
}

Write-Host 'Done. Start the hotel with deploy\turbo.ps1, then deploy\client.ps1 and deploy\panel.ps1.'
